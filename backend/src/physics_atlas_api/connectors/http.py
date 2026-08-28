import json
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self
from urllib.parse import urljoin, urlparse

import httpx

from .base import ConnectorError


class ProviderHttpTransport:
    """Bounded HTTP transport with per-host pacing and exponential retry."""

    is_fixture = False

    def __init__(
        self,
        *,
        timeout_seconds: float = 15,
        user_agent: str = "PhysicsAtlas/3.0.4-alpha (open scientific infrastructure)",
        minimum_intervals: dict[str, float] | None = None,
        allowed_hosts: set[str] | None = None,
        max_attempts: int = 3,
        max_redirects: int = 5,
        max_retry_delay_seconds: float = 60,
    ):
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            headers={"User-Agent": user_agent},
        )
        self.minimum_intervals = minimum_intervals or {}
        self.allowed_hosts = {
            host.casefold().rstrip(".") for host in (allowed_hosts or set()) if host
        }
        self.max_attempts = max_attempts
        self.max_redirects = max_redirects
        self.max_retry_delay_seconds = max_retry_delay_seconds
        self._last_request: dict[str, float] = {}

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def _validated_origin(self, url: str) -> tuple[str, str, int]:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme not in {"http", "https"} or not host:
            raise ConnectorError("Provider URL must use HTTP(S) and include a host")
        if parsed.username is not None or parsed.password is not None:
            raise ConnectorError("Provider URL must not include user information")
        try:
            port = parsed.port
        except ValueError as error:
            raise ConnectorError("Provider URL contains an invalid port") from error
        if self.allowed_hosts and host not in self.allowed_hosts:
            raise ConnectorError(f"Provider host is not allowed: {host}")
        return parsed.scheme, host, port or (443 if parsed.scheme == "https" else 80)

    def _validated_host(self, url: str) -> str:
        return self._validated_origin(url)[1]

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After", "").strip()
        if retry_after.isdigit():
            return float(retry_after)
        if retry_after:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(
                    0.0,
                    (retry_at.astimezone(UTC) - datetime.now(UTC)).total_seconds(),
                )
            except (TypeError, ValueError, OverflowError):
                pass
        return float(min(0.5 * 2 ** (attempt - 1), 10))

    def _request_url(
        self,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
    ) -> httpx.Response:
        host = self._validated_host(url)
        for attempt in range(1, self.max_attempts + 1):
            last_request = self._last_request.get(host)
            if last_request is not None:
                wait = self.minimum_intervals.get(host, 0) - (
                    time.monotonic() - last_request
                )
                if wait > 0:
                    time.sleep(wait)
            try:
                response = self.client.get(url, params=params, headers=headers)
            except httpx.HTTPError as error:
                # Record failed attempts before applying backoff. The next loop
                # then enforces whichever is longer: backoff already elapsed or
                # the provider's remaining minimum interval.
                self._last_request[host] = time.monotonic()
                if attempt == self.max_attempts:
                    raise ConnectorError(
                        f"Provider request failed for {host}"
                    ) from error
                time.sleep(min(0.5 * 2 ** (attempt - 1), 10))
                continue
            else:
                # Successful HTTP round trips share the same pacing clock.
                self._last_request[host] = time.monotonic()

            if response.status_code in {429, 500, 502, 503, 504}:
                if attempt < self.max_attempts:
                    delay = self._retry_delay(response, attempt)
                    if delay > self.max_retry_delay_seconds:
                        raise ConnectorError(
                            "Provider requested a retry delay beyond the bounded "
                            "request budget; checkpoint was preserved"
                        )
                    time.sleep(delay)
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPError as error:
                    raise ConnectorError(
                        f"Provider request failed for {host}"
                    ) from error

            if response.status_code not in {301, 302, 303, 307, 308}:
                try:
                    response.raise_for_status()
                except httpx.HTTPError as error:
                    raise ConnectorError(
                        f"Provider request failed for {host}"
                    ) from error
            return response

        raise ConnectorError(f"Provider request failed for {host}")

    def _request(
        self,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
    ) -> httpx.Response:
        current_url = url
        current_params = params
        request_origin = self._validated_origin(url)
        for redirect_count in range(self.max_redirects + 1):
            response = self._request_url(
                current_url, params=current_params, headers=headers
            )
            response_origin = self._validated_origin(str(response.url))
            if response_origin != request_origin:
                raise ConnectorError("Provider response crossed its configured origin")
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response

            location = response.headers.get("Location")
            if not location:
                raise ConnectorError("Provider redirect omitted its target")
            if redirect_count == self.max_redirects:
                raise ConnectorError("Provider exceeded the redirect limit")
            current_url = urljoin(str(response.url), location)
            redirect_origin = self._validated_origin(current_url)
            if redirect_origin != request_origin:
                raise ConnectorError("Provider redirect crossed its configured origin")
            current_params = None

        raise ConnectorError("Provider exceeded the redirect limit")

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = self._request(url, params=params, headers=headers).json()
        if not isinstance(payload, dict):
            raise ConnectorError("Provider returned a non-object JSON response")
        return payload

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        return self._request(url, params=params, headers=headers).text


class FixtureTransport:
    """Network-free transport used by the standard suite and fixture-mode worker."""

    is_fixture = True

    def __init__(self, fixture_directory: Path):
        self.fixture_directory = fixture_directory

    def close(self) -> None:
        """Match the live transport lifecycle without owning network resources."""

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()

    @staticmethod
    def _fixture_name(url: str) -> str:
        host = urlparse(url).hostname or url
        if "inspirehep" in host:
            return "inspire.json"
        if "arxiv" in host:
            return "arxiv.xml"
        if "ror.org" in host:
            return "ror.json"
        if "orcid" in host:
            return "orcid.json"
        if "crossref" in host:
            return "crossref.json"
        raise ConnectorError(f"No deterministic fixture is configured for {host}")

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del params, headers
        path = self.fixture_directory / self._fixture_name(url)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ConnectorError(f"Fixture {path.name} must contain a JSON object")
        return payload

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        del params, headers
        path = self.fixture_directory / self._fixture_name(url)
        return path.read_text(encoding="utf-8")
