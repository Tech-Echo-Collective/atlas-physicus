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


class RorConnector(SourceConnector):
    provider = "ror"
    source_version = "ROR API v2 / schema 2.1"
    min_interval_seconds = 0.2

    def _records(self, payload: dict[str, Any]) -> list[SourceRecord]:
        records = []
        for item in payload.get("items", []):
            identifier_pair = external_id("ror", item.get("id"))
            if identifier_pair:
                records.append(
                    SourceRecord(
                        provider=self.provider,
                        source_record_id=identifier_pair[1],
                        raw=item,
                        updated_at=parse_provider_datetime(
                            item.get("admin", {}).get("last_modified", {}).get("date")
                        ),
                    )
                )
        return records

    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        del limit  # ROR v2 has a fixed, bounded page size.
        checkpoint = self.get_checkpoint()
        until = (
            provider_date(checkpoint.get("until"))
            or datetime.now(UTC).date().isoformat()
        )
        since = (
            provider_date(checkpoint.get("since") or cursor)
            or (datetime.now(UTC) - timedelta(days=7)).date().isoformat()
        )
        page = int(checkpoint.get("page", 1))
        payload = self.transport.get_json(
            f"{self.base_url}/organizations",
            params={
                "page": page,
                "all_status": "true",
                "query.advanced": (f"admin.last_modified.date:[{since} TO {until}]"),
            },
        )
        records = self._records(payload)
        total = int(payload.get("meta", {}).get("number_of_results", len(records)))
        if page * 20 < total:
            return self._complete(
                records,
                cursor,
                {"since": since, "until": until, "page": page + 1},
                raw_payload=[{"contentType": "application/json", "body": payload}],
            )
        return self._complete(
            records,
            until,
            raw_payload=[{"contentType": "application/json", "body": payload}],
        )

    def fetch_record(self, record_id: str) -> SourceRecord | None:
        identifier = external_id("ror", record_id)
        if identifier is None:
            return None
        payload = self.transport.get_json(
            f"{self.base_url}/organizations/{identifier[1]}"
        )
        records = self._records({"items": [payload]})
        return records[0] if records else None

    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        raw = record.raw
        names = raw.get("names", [])
        display = next(
            (
                item.get("value")
                for item in names
                if "ror_display" in item.get("types", [])
            ),
            None,
        )
        canonical_name = display or next(
            (item.get("value") for item in names if item.get("value")),
            record.source_record_id,
        )
        aliases = [
            item.get("value")
            for item in names
            if item.get("value") and item.get("value") != canonical_name
        ]
        locations = raw.get("locations") or []
        geonames = (locations[0].get("geonames_details") if locations else {}) or {}
        links = raw.get("links") or []
        return NormalizedRecord(
            provider=self.provider,
            kind="institution",
            source_record_id=record.source_record_id,
            canonical_name=canonical_name,
            external_ids=compact_ids(external_id("ror", record.source_record_id)),
            attributes={
                "aliases": aliases,
                "country_code": geonames.get("country_code"),
                "city": geonames.get("name"),
                "latitude": geonames.get("lat"),
                "longitude": geonames.get("lng"),
                "official_websites": [
                    item.get("value")
                    for item in links
                    if "website" in item.get("types", [])
                ],
                "external_ids": raw.get("external_ids", []),
            },
            raw=raw,
            updated_at=record.updated_at,
            provenance={
                "source": "Research Organization Registry (ROR)",
                "sourceType": "external-api",
                "version": self.source_version,
                "status": "unverified",
                "sourceRecordId": record.source_record_id,
                "retrievedAt": record.updated_at.isoformat()
                if record.updated_at
                else None,
            },
        )
