from datetime import UTC, datetime
from typing import Any

from .base import (
    ConnectorBatch,
    ConnectorConfigurationError,
    NormalizedRecord,
    SourceConnector,
    SourceRecord,
    SourceTransport,
    compact_ids,
    external_id,
    parse_provider_datetime,
)


class OrcidConnector(SourceConnector):
    provider = "orcid"
    source_version = "ORCID Public API v3.0"
    min_interval_seconds = 1.0

    def __init__(
        self,
        transport: SourceTransport,
        base_url: str,
        *,
        access_token: str | None = None,
        require_credentials: bool = False,
    ):
        super().__init__(transport, base_url)
        self.require_credentials = require_credentials
        self.access_token = access_token
        self.headers = {"Accept": "application/json"}
        if access_token:
            self.headers["Authorization"] = f"Bearer {access_token}"

    @staticmethod
    def _record(payload: dict[str, Any]) -> SourceRecord | None:
        identifier = payload.get("orcid-identifier", {}).get("path") or payload.get(
            "orcid"
        )
        if not identifier:
            return None
        updated = payload.get("history", {}).get("last-modified-date", {}).get("value")
        updated_at: datetime | None
        if isinstance(updated, int):
            updated_at = datetime.fromtimestamp(updated / 1000, tz=UTC)
        else:
            updated_at = parse_provider_datetime(updated)
        return SourceRecord(
            provider="orcid",
            source_record_id=identifier,
            raw=payload,
            updated_at=updated_at,
        )

    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        del cursor, limit
        raise ConnectorConfigurationError(
            "ORCID is targeted identity enrichment only; use fetch_record() for "
            "an already-known ORCID iD"
        )

    def fetch_record(self, record_id: str) -> SourceRecord | None:
        if self.require_credentials and not self.access_token:
            raise ConnectorConfigurationError(
                "ORCID Public API access requires a configured access token"
            )
        return self._record(
            self.transport.get_json(
                f"{self.base_url}/{record_id}/record", headers=self.headers
            )
        )

    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        raw = record.raw
        person = raw.get("person", raw)
        name = person.get("name", {})
        given = name.get("given-names", {}).get("value", "")
        family = name.get("family-name", {}).get("value", "")
        canonical_name = (
            " ".join(value for value in (given, family) if value).strip()
            or record.source_record_id
        )
        other_names = [
            item.get("content")
            for item in person.get("other-names", {}).get("other-name", [])
            if item.get("content")
        ]
        return NormalizedRecord(
            provider=self.provider,
            kind="researcher",
            source_record_id=record.source_record_id,
            canonical_name=canonical_name,
            external_ids=compact_ids(external_id("orcid", record.source_record_id)),
            attributes={"aliases": other_names},
            raw=raw,
            updated_at=record.updated_at,
            provenance={
                "source": "ORCID Public API",
                "sourceType": "external-api",
                "version": self.source_version,
                "status": "unverified",
                "sourceRecordId": record.source_record_id,
                "retrievedAt": record.updated_at.isoformat()
                if record.updated_at
                else None,
            },
        )
