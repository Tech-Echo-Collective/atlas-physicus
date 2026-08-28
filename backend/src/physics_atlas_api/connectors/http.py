import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
        max_attempts: int = 3,
    ):
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        )
        self.minimum_intervals = minimum_intervals or {}
        self.max_attempts = max_attempts
        self._last_request: dict[str, float] = {}

    def _request(
        self,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
    ) -> httpx.Response:
        host = urlparse(url).hostname or ""
        wait = self.minimum_intervals.get(host, 0) - (
            time.monotonic() - self._last_request.get(host, 0)
        )
        if wait > 0:
            time.sleep(wait)
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.client.get(url, params=params, headers=headers)
                self._last_request[host] = time.monotonic()
                if (
                    response.status_code in {429, 500, 502, 503, 504}
                    and attempt < self.max_attempts
                ):
                    retry_after = response.headers.get("Retry-After")
                    delay = (
                        float(retry_after)
                        if retry_after and retry_after.isdigit()
                        else 0.5 * 2 ** (attempt - 1)
                    )
                    time.sleep(min(delay, 10))
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPError as error:
                if attempt == self.max_attempts:
                    raise ConnectorError(
                        f"Provider request failed for {host}"
                    ) from error
                time.sleep(min(0.5 * 2 ** (attempt - 1), 10))
        raise ConnectorError(f"Provider request failed for {host}")

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
