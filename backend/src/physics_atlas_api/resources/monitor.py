import ipaddress
import logging
import socket
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger("physics_atlas_api.resources")

HealthStatus = Literal[
    "reachable", "redirect", "permanent-redirect", "broken", "timeout", "unknown"
]


@dataclass(frozen=True)
class ResourceResponse:
    status_code: int
    location: str | None = None


class ResourceTransport(Protocol):
    def request(
        self, method: str, url: str, *, timeout_seconds: float
    ) -> ResourceResponse: ...


class HttpResourceTransport:
    def __init__(self) -> None:
        self.client = httpx.Client(
            follow_redirects=False,
            headers={"User-Agent": "PhysicsAtlasResourceMonitor/3.0.4-alpha"},
        )

    def request(
        self, method: str, url: str, *, timeout_seconds: float
    ) -> ResourceResponse:
        headers = {"Range": "bytes=0-0"} if method == "GET" else None
        with self.client.stream(
            method, url, timeout=timeout_seconds, headers=headers
        ) as response:
            return ResourceResponse(
                response.status_code, response.headers.get("Location")
            )


@dataclass(frozen=True)
class ResourceMonitorResult:
    checked: int
    reachable: int
    redirects: int
    broken: int
    temporary_failures: int


def validate_resource_url(
    url: str,
    *,
    resolve_dns: bool = True,
    allowed_hosts: set[str] | None = None,
) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    expected_port = 80 if parsed.scheme == "http" else 443
    if port is not None and port != expected_port:
        return False
    hostname = parsed.hostname.casefold().rstrip(".")
    normalized_allowed_hosts = (
        {allowed.casefold().rstrip(".") for allowed in allowed_hosts}
        if allowed_hosts is not None
        else None
    )
    if normalized_allowed_hosts is not None and not any(
        hostname == allowed or hostname.endswith(f".{allowed}")
        for allowed in normalized_allowed_hosts
    ):
        return False
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(
        ".local"
    ):
        return False
    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        if not resolve_dns:
            return True
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(hostname, port or expected_port)
            }
        except (OSError, ValueError):
            return False
    return bool(addresses) and all(address.is_global for address in addresses)


class ResourceMonitor:
    """Bounded link checker. It never crawls content or deletes resource records."""

    def __init__(
        self,
        session: Session,
        transport: ResourceTransport,
        *,
        timeout_seconds: float = 8,
        max_attempts: int = 3,
        minimum_interval_seconds: float = 0.1,
        cache_for: timedelta = timedelta(days=7),
        url_validator: Callable[[str], bool] = validate_resource_url,
    ):
        self.session = session
        self.transport = transport
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.minimum_interval_seconds = minimum_interval_seconds
        self.cache_for = cache_for
        self.url_validator = url_validator

    def run(
        self, *, limit: int = 100, now: datetime | None = None
    ) -> ResourceMonitorResult:
        checked_at = now or datetime.now(UTC)
        stale_before = checked_at - self.cache_for
        resources = list(
            self.session.scalars(
                select(models.ExternalResource)
                .where(
                    or_(
                        models.ExternalResource.last_checked_at.is_(None),
                        models.ExternalResource.last_checked_at < stale_before,
                    )
                )
                .order_by(models.ExternalResource.last_checked_at.asc().nullsfirst())
                .limit(min(max(limit, 1), 1000))
            )
        )
        reachable = redirects = broken = temporary = 0
        for resource in resources:
            status, http_status, target, error, attempts = self._check(resource.url)
            resource.health_status = status
            resource.last_checked_at = checked_at
            resource.http_status = http_status
            resource.redirect_target = target
            if status in {"reachable", "redirect", "permanent-redirect"}:
                resource.verified = True
                resource.verification_method = "bounded-http-health-check"
                if status == "reachable":
                    reachable += 1
                else:
                    redirects += 1
            elif status == "broken":
                resource.verified = False
                resource.verification_method = "bounded-http-health-check"
                broken += 1
            else:
                # A transient failure does not revoke prior verification.
                temporary += 1
            self.session.add(
                models.ResourceCheck(
                    id=f"resource-check-{uuid.uuid4()}",
                    resource_id=resource.id,
                    checked_at=checked_at,
                    status=status,
                    http_status=http_status,
                    redirect_target=target,
                    error=error,
                    attempt_count=attempts,
                )
            )
            time.sleep(self.minimum_interval_seconds)
        self.session.commit()
        return ResourceMonitorResult(
            len(resources), reachable, redirects, broken, temporary
        )

    def _check(
        self, url: str
    ) -> tuple[HealthStatus, int | None, str | None, str | None, int]:
        if not self.url_validator(url):
            return "unknown", None, None, "URL failed public HTTP(S) validation", 1
        last_error: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                # Re-resolve immediately before each network attempt. This narrows
                # the DNS-validation window; production still needs an egress
                # policy because application checks cannot pin the connection IP.
                if not self.url_validator(url):
                    return (
                        "unknown",
                        None,
                        None,
                        "URL failed public HTTP(S) validation before request",
                        attempt,
                    )
                response = self.transport.request(
                    "HEAD", url, timeout_seconds=self.timeout_seconds
                )
                if response.status_code in {405, 501}:
                    if not self.url_validator(url):
                        return (
                            "unknown",
                            None,
                            None,
                            "URL failed public HTTP(S) validation before GET fallback",
                            attempt,
                        )
                    response = self.transport.request(
                        "GET", url, timeout_seconds=self.timeout_seconds
                    )
                if 200 <= response.status_code < 300:
                    return "reachable", response.status_code, None, None, attempt
                if response.status_code in {302, 303, 307}:
                    target = (
                        urljoin(url, response.location)
                        if response.location is not None
                        else None
                    )
                    if target is None or not self.url_validator(target):
                        return (
                            "unknown",
                            response.status_code,
                            None,
                            "Redirect target failed public HTTP(S) validation",
                            attempt,
                        )
                    return (
                        "redirect",
                        response.status_code,
                        target,
                        None,
                        attempt,
                    )
                if response.status_code in {301, 308}:
                    target = (
                        urljoin(url, response.location)
                        if response.location is not None
                        else None
                    )
                    if target is None or not self.url_validator(target):
                        return (
                            "unknown",
                            response.status_code,
                            None,
                            "Redirect target failed public HTTP(S) validation",
                            attempt,
                        )
                    return (
                        "permanent-redirect",
                        response.status_code,
                        target,
                        None,
                        attempt,
                    )
                if response.status_code in {404, 410}:
                    return "broken", response.status_code, None, None, attempt
                if response.status_code in {408, 425, 429, 500, 502, 503, 504}:
                    last_error = f"temporary HTTP status {response.status_code}"
                else:
                    return "unknown", response.status_code, None, None, attempt
            except (httpx.TimeoutException, TimeoutError) as error:
                last_error = str(error) or "request timed out"
            except (httpx.HTTPError, OSError) as error:
                last_error = str(error)
            if attempt < self.max_attempts:
                time.sleep(min(0.25 * 2 ** (attempt - 1), 4))
        timed_out = bool(last_error and "tim" in last_error.casefold())
        return (
            ("timeout" if timed_out else "unknown"),
            None,
            None,
            last_error,
            self.max_attempts,
        )
