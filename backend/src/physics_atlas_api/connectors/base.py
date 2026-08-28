import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Literal, Protocol, Self
from urllib.parse import unquote, urlparse

ProviderName = Literal["inspire", "arxiv", "ror", "orcid", "crossref"]
RecordKind = Literal["paper", "institution", "researcher"]


class SourceTransport(Protocol):
    def close(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str: ...


@dataclass(frozen=True)
class SourceRecord:
    provider: ProviderName
    source_record_id: str
    raw: dict[str, Any]
    updated_at: datetime | None = None

    @property
    def checksum(self) -> str:
        payload = json.dumps(self.raw, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class NormalizedRecord:
    provider: ProviderName
    kind: RecordKind
    source_record_id: str
    canonical_name: str
    external_ids: tuple[tuple[str, str], ...]
    attributes: dict[str, Any]
    raw: dict[str, Any]
    provenance: dict[str, Any]
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ConnectorBatch:
    records: tuple[SourceRecord, ...]
    next_cursor: str | None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    checkpoint: dict[str, Any] = field(default_factory=dict)
    replay_checkpoint: dict[str, Any] | None = None
    raw_payload: tuple[dict[str, Any], ...] = field(default_factory=tuple)


class ConnectorError(RuntimeError):
    pass


class ConnectorConfigurationError(ConnectorError):
    pass


class SourceConnector(ABC):
    provider: ProviderName
    source_version: str
    min_interval_seconds: float

    def __init__(
        self,
        transport: SourceTransport,
        base_url: str,
        *,
        cursor_scope: str | None = None,
        dataset_scope: str = "targeted-known-id-v1",
    ):
        self.transport = transport
        self.base_url = base_url.rstrip("/")
        self.cursor_scope = cursor_scope or f"{self.provider}:targeted-record-v1"
        self.dataset_scope = dataset_scope
        self._cursor: str | None = None
        self._checkpoint: dict[str, Any] = {}
        self._replay_checkpoint: dict[str, Any] | None = None

    @property
    def enabled(self) -> bool:
        return True

    @abstractmethod
    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        """Return records created after a provider checkpoint."""

    def fetch_updated_records(
        self, cursor: str | None, limit: int = 100
    ) -> ConnectorBatch:
        """Use the provider's shared modified-time stream by default."""
        return self.fetch_new_records(cursor, limit)

    @abstractmethod
    def fetch_record(self, record_id: str) -> SourceRecord | None:
        """Fetch one source record without mutating canonical data."""

    @abstractmethod
    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        """Normalize source syntax without resolving canonical identity."""

    def get_cursor(self) -> str | None:
        return self._cursor

    def set_checkpoint(self, checkpoint: dict[str, Any] | None) -> None:
        self._checkpoint = dict(checkpoint or {})
        self._replay_checkpoint = None

    def get_checkpoint(self) -> dict[str, Any]:
        return dict(self._checkpoint)

    def set_replay_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        self._replay_checkpoint = dict(checkpoint)

    def get_replay_checkpoint(self) -> dict[str, Any] | None:
        return (
            dict(self._replay_checkpoint)
            if self._replay_checkpoint is not None
            else None
        )

    def _complete(
        self,
        records: list[SourceRecord],
        next_cursor: str | None,
        checkpoint: dict[str, Any] | None = None,
        raw_payload: list[dict[str, Any]] | None = None,
        replay_checkpoint: dict[str, Any] | None = None,
    ) -> ConnectorBatch:
        self._cursor = next_cursor
        self._checkpoint = dict(checkpoint or {})
        self._replay_checkpoint = (
            dict(replay_checkpoint) if replay_checkpoint is not None else None
        )
        return ConnectorBatch(
            tuple(records),
            next_cursor,
            checkpoint=self.get_checkpoint(),
            replay_checkpoint=self.get_replay_checkpoint(),
            raw_payload=tuple(raw_payload or ()),
        )


def parse_provider_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return result if result.tzinfo else result.replace(tzinfo=UTC)


def provider_date(value: Any) -> str | None:
    """Convert a persisted provider cursor to a UTC calendar date."""
    if value is None or not str(value).strip():
        return None
    parsed = parse_provider_datetime(str(value).strip())
    if parsed is None:
        raise ConnectorError(f"Invalid provider date checkpoint: {value}")
    return parsed.astimezone(UTC).date().isoformat()


def _strip_identifier_url(value: str, expected_host: str, path_marker: str = "") -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme.casefold() in {"http", "https"}
        and (parsed.hostname or "").casefold().rstrip(".") == expected_host
    ):
        path = unquote(parsed.path).strip("/")
        if path_marker and path.casefold().startswith(f"{path_marker.casefold()}/"):
            path = path[len(path_marker) + 1 :]
        return path
    return value


def _valid_orcid(value: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-[\dX]{4}", value):
        return False
    digits = value.replace("-", "")
    total = 0
    for character in digits[:-1]:
        total = (total + int(character)) * 2
    check_value = (12 - total % 11) % 11
    expected = "X" if check_value == 10 else str(check_value)
    return digits[-1] == expected


def normalize_external_id(scheme: str, value: Any) -> tuple[str, str] | None:
    """Return a provider-independent authority identifier or reject invalid input."""
    normalized_scheme = scheme.strip().casefold()
    identifier = unquote(str(value).strip()) if value is not None else ""
    if not normalized_scheme or not identifier:
        return None

    if normalized_scheme == "doi":
        identifier = re.sub(
            r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)",
            "",
            identifier,
            flags=re.IGNORECASE,
        ).strip()
        identifier = identifier.casefold()
        if not identifier.startswith("10.") or "/" not in identifier:
            return None
    elif normalized_scheme == "orcid":
        identifier = _strip_identifier_url(identifier, "orcid.org")
        identifier = re.sub(r"^orcid:\s*", "", identifier, flags=re.IGNORECASE)
        identifier = identifier.strip("/").upper()
        if not _valid_orcid(identifier):
            return None
    elif normalized_scheme == "ror":
        identifier = _strip_identifier_url(identifier, "ror.org")
        identifier = re.sub(r"^ror:\s*", "", identifier, flags=re.IGNORECASE)
        identifier = identifier.strip("/").casefold()
        if not re.fullmatch(r"[0-9a-z]{9}", identifier):
            return None
    elif normalized_scheme == "arxiv":
        parsed = urlparse(identifier)
        if parsed.scheme.casefold() in {"http", "https"} and (
            parsed.hostname or ""
        ).casefold().rstrip(".") in {"arxiv.org", "export.arxiv.org"}:
            identifier = unquote(parsed.path).strip("/")
            if identifier.casefold().startswith(("abs/", "pdf/")):
                identifier = identifier.split("/", 1)[1]
        identifier = re.sub(r"^arxiv:\s*", "", identifier, flags=re.IGNORECASE)
        identifier = re.sub(r"\.pdf$", "", identifier, flags=re.IGNORECASE)
        identifier = re.sub(r"v\d+$", "", identifier, flags=re.IGNORECASE)
        identifier = identifier.strip("/").casefold()
        if not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z.-]+/\d{7})", identifier):
            return None
    elif normalized_scheme == "inspire":
        identifier = _strip_identifier_url(identifier, "inspirehep.net", "literature")
        identifier = re.sub(r"^inspire:\s*", "", identifier, flags=re.IGNORECASE)
        identifier = identifier.strip("/")
        if not identifier.isdigit():
            return None
    elif normalized_scheme == "inspire-author":
        identifier = _strip_identifier_url(identifier, "inspirehep.net", "authors")
        identifier = re.sub(
            r"^inspire(?:-author)?:\s*", "", identifier, flags=re.IGNORECASE
        ).strip("/")
        if not identifier:
            return None

    return normalized_scheme, identifier


def external_id(scheme: str, value: Any) -> tuple[str, str] | None:
    return normalize_external_id(scheme, value)


def compact_ids(*values: tuple[str, str] | None) -> tuple[tuple[str, str], ...]:
    return tuple(dict.fromkeys(value for value in values if value is not None))
