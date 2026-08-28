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
from .field_mapping import map_provider_categories


class CrossrefConnector(SourceConnector):
    provider = "crossref"
    source_version = "Crossref REST API v1"
    min_interval_seconds = 1.0

    def __init__(
        self,
        transport: SourceTransport,
        base_url: str,
        *,
        mailto: str | None = None,
    ):
        super().__init__(transport, base_url)
        self.mailto = mailto

    def _records(self, payload: dict[str, Any]) -> list[SourceRecord]:
        message = payload.get("message", {})
        items = message.get("items", [message] if message.get("DOI") else [])
        records = []
        for item in items:
            identifier = item.get("DOI")
            if identifier:
                records.append(
                    SourceRecord(
                        provider=self.provider,
                        source_record_id=identifier,
                        raw=item,
                        updated_at=parse_provider_datetime(
                            item.get("indexed", {}).get("date-time")
                        ),
                    )
                )
        return records

    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        del cursor, limit
        raise ConnectorConfigurationError(
            "Crossref is targeted DOI enrichment only; use fetch_record() after "
            "a physics source supplies a DOI"
        )

    def fetch_record(self, record_id: str) -> SourceRecord | None:
        records = self._records(
            self.transport.get_json(
                f"{self.base_url}/works/{record_id}",
                params={"mailto": self.mailto} if self.mailto else None,
            )
        )
        return records[0] if records else None

    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        raw = record.raw
        title_values = raw.get("title") or []
        title = title_values[0] if title_values else record.source_record_id
        issued = raw.get("issued", {}).get("date-parts", [[None]])
        year = issued[0][0] if issued and issued[0] else None
        arxiv_id = next(
            (value for value in raw.get("alternative-id", []) if "." in str(value)),
            None,
        )
        mapping = map_provider_categories("crossref", raw.get("subject", []))
        return NormalizedRecord(
            provider=self.provider,
            kind="paper",
            source_record_id=record.source_record_id,
            canonical_name=title,
            external_ids=compact_ids(
                external_id("doi", record.source_record_id),
                external_id("arxiv", arxiv_id),
            ),
            attributes={
                "title": title,
                "publication_year": year,
                "authors": raw.get("author", []),
                "raw_categories": raw.get("subject", []),
                "atlas_field_candidates": list(mapping.atlas_field_ids),
                "field_mapping_confidence": mapping.confidence,
                "field_mapping_method": mapping.method,
                "field_mapping_uncertainty": mapping.uncertainty_note,
                "resource_url": raw.get("URL"),
                "metadata_type": raw.get("type"),
            },
            raw=raw,
            updated_at=record.updated_at or datetime.now(UTC),
            provenance={
                "source": "Crossref REST API",
                "sourceType": "external-api",
                "version": self.source_version,
                "status": "unverified",
                "sourceRecordId": record.source_record_id,
                "retrievedAt": record.updated_at.isoformat()
                if record.updated_at
                else None,
            },
        )
