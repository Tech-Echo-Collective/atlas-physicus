"""HTTP response capture with bounded provider lineage.

The normal connector transport intentionally returns only decoded response
content.  Historical evidence capture additionally needs the request interval
and a small, stable subset of provider response headers.  This module adds
that behavior without changing the production connector transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from .connectors.http import ProviderHttpTransport


def _utc_timestamp(value: datetime, *, field: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class HttpCaptureLineage:
    """Inspectable timing and HTTP identity for one preserved response body."""

    request_started_at: datetime
    response_received_at: datetime
    request_url: str
    response_url: str
    status_code: int
    provider_date: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    content_type: str | None = None

    def __post_init__(self) -> None:
        _utc_timestamp(self.request_started_at, field="request_started_at")
        _utc_timestamp(self.response_received_at, field="response_received_at")
        if self.response_received_at < self.request_started_at:
            raise ValueError("response_received_at precedes request_started_at")
        if not self.request_url or not self.response_url:
            raise ValueError("HTTP capture URLs must not be empty")
        if not 100 <= self.status_code <= 599:
            raise ValueError("status_code is outside the HTTP status range")
        for name, value in (
            ("provider_date", self.provider_date),
            ("etag", self.etag),
            ("last_modified", self.last_modified),
            ("content_type", self.content_type),
        ):
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{name} must be text when present")

    def as_dict(self) -> dict[str, object]:
        return {
            "request_started_at": _utc_timestamp(
                self.request_started_at, field="request_started_at"
            ),
            "response_received_at": _utc_timestamp(
                self.response_received_at, field="response_received_at"
            ),
            "request_url": self.request_url,
            "response_url": self.response_url,
            "status_code": self.status_code,
            "provider_date": self.provider_date,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "content_type": self.content_type,
        }


@dataclass(frozen=True)
class CapturedTextResponse:
    body: str
    lineage: HttpCaptureLineage


class CaptureTextTransport(Protocol):
    """Minimum transport surface used by the paired evidence acquirer."""

    def get_captured_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> CapturedTextResponse: ...


class LineageProviderHttpTransport(ProviderHttpTransport):
    """Provider transport that retains final-response HTTP evidence.

    The inherited request path supplies the existing origin checks, redirect
    policy, pacing, retry limits, timeouts, and status validation.
    """

    def get_captured_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> CapturedTextResponse:
        request_started_at = datetime.now(UTC)
        response = self._request(url, params=params, headers=headers)
        response_received_at = datetime.now(UTC)
        return CapturedTextResponse(
            body=response.text,
            lineage=HttpCaptureLineage(
                request_started_at=request_started_at,
                response_received_at=response_received_at,
                request_url=str(response.request.url),
                response_url=str(response.url),
                status_code=response.status_code,
                provider_date=response.headers.get("Date"),
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
                content_type=response.headers.get("Content-Type"),
            ),
        )
