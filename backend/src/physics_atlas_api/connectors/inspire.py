from datetime import UTC, datetime, timedelta
from typing import Any

from .base import (
    ConnectorBatch,
    NormalizedRecord,
    SourceConnector,
    SourceRecord,
    compact_ids,
    external_id,
    parse_provider_datetime,
    provider_date,
)
from .field_mapping import map_provider_categories


class InspireConnector(SourceConnector):
    provider = "inspire"
    source_version = "INSPIRE REST API"
    min_interval_seconds = 1.0

    def _records(self, payload: dict[str, Any]) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        for hit in payload.get("hits", {}).get("hits", []):
            metadata = hit.get("metadata", {})
            identifier_pair = external_id(
                "inspire", hit.get("id") or metadata.get("control_number")
            )
            if identifier_pair:
                records.append(
                    SourceRecord(
                        provider=self.provider,
                        source_record_id=identifier_pair[1],
                        raw=metadata,
                        updated_at=parse_provider_datetime(
                            hit.get("updated") or metadata.get("last_updated")
                        ),
                    )
                )
        return records

    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        checkpoint = self.get_checkpoint()
        until = (
            provider_date(checkpoint.get("until"))
            or datetime.now(UTC).date().isoformat()
        )
        since = (
            provider_date(checkpoint.get("since") or cursor)
            or (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
        )
        next_url = checkpoint.get("nextUrl")
        if isinstance(next_url, str) and next_url:
            payload = self.transport.get_json(next_url)
        else:
            payload = self.transport.get_json(
                f"{self.base_url}/literature",
                params={
                    "q": f"document_type:article and du >= {since} and du <= {until}",
                    "sort": "mostrecent",
                    "size": min(limit, 250),
                },
            )
        records = self._records(payload)
        following = payload.get("links", {}).get("next")
        if isinstance(following, str) and following:
            return self._complete(
                records,
                cursor,
                {"since": since, "until": until, "nextUrl": following},
                raw_payload=[{"contentType": "application/json", "body": payload}],
            )
        return self._complete(
            records,
            until,
            raw_payload=[{"contentType": "application/json", "body": payload}],
        )

    def fetch_record(self, record_id: str) -> SourceRecord | None:
        identifier = external_id("inspire", record_id)
        if identifier is None:
            return None
        payload = self.transport.get_json(f"{self.base_url}/literature/{identifier[1]}")
        if "metadata" in payload:
            payload = {"hits": {"hits": [payload]}}
        records = self._records(payload)
        return records[0] if records else None

    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        raw = record.raw
        titles = raw.get("titles") or []
        title = (
            titles[0].get("title")
            if titles
            else f"INSPIRE record {record.source_record_id}"
        )
        arxiv = (raw.get("arxiv_eprints") or [{}])[0].get("value")
        doi = (raw.get("dois") or [{}])[0].get("value")
        categories = [
            value.get("term")
            for value in raw.get("inspire_categories", [])
            if value.get("term")
        ]
        mapping = map_provider_categories("inspire", categories)
        return NormalizedRecord(
            provider=self.provider,
            kind="paper",
            source_record_id=record.source_record_id,
            canonical_name=title,
            external_ids=compact_ids(
                external_id("inspire", record.source_record_id),
                external_id("arxiv", arxiv),
                external_id("doi", doi),
            ),
            attributes={
                "title": title,
                "abstract": (raw.get("abstracts") or [{}])[0].get("value", ""),
                "publication_year": raw.get("publication_info", [{}])[0].get("year"),
                "raw_categories": categories,
                "atlas_field_candidates": list(mapping.atlas_field_ids),
                "field_mapping_confidence": mapping.confidence,
                "field_mapping_method": mapping.method,
                "field_mapping_uncertainty": mapping.uncertainty_note,
                "authors": raw.get("authors", []),
                "citation_count": raw.get("citation_count"),
            },
            raw=raw,
            updated_at=record.updated_at,
            provenance={
                "source": "INSPIRE REST API",
                "sourceType": "external-api",
                "version": self.source_version,
                "status": "unverified",
                "sourceRecordId": record.source_record_id,
                "retrievedAt": record.updated_at.isoformat()
                if record.updated_at
                else None,
            },
        )
