import hashlib
from datetime import UTC, datetime
from typing import Any

from .acquisition import HEP_TH_V1, AcquisitionScope
from .base import (
    ConnectorBatch,
    ConnectorConfigurationError,
    ConnectorError,
    NormalizedRecord,
    SourceConnector,
    SourceRecord,
    SourceTransport,
    compact_ids,
    external_id,
    parse_provider_datetime,
)


class RorConnector(SourceConnector):
    provider = "ror"
    source_version = "ROR API v2 / schema 2.1 / targeted records"
    min_interval_seconds = 0.2

    def __init__(
        self,
        transport: SourceTransport,
        base_url: str,
        *,
        record_ids: tuple[str, ...] = (),
        acquisition_scope: AcquisitionScope = HEP_TH_V1,
    ):
        canonical_ids: list[str] = []
        for value in record_ids:
            identifier = external_id("ror", value)
            if identifier is None:
                raise ConnectorConfigurationError(
                    f"Configured ROR record ID is invalid: {value!r}"
                )
            if identifier[1] not in canonical_ids:
                canonical_ids.append(identifier[1])
        canonical_ids.sort()
        target_digest = hashlib.sha256("\n".join(canonical_ids).encode()).hexdigest()[
            :16
        ]
        super().__init__(
            transport,
            base_url,
            cursor_scope=(
                acquisition_scope.cursor_scope(
                    self.provider, f"targeted-records-v1-{target_digest}"
                )
            ),
            dataset_scope=acquisition_scope.id,
        )
        self.acquisition_scope = acquisition_scope
        self.record_ids = tuple(canonical_ids)

    @property
    def enabled(self) -> bool:
        return bool(self.record_ids)

    def _records(self, payload: dict[str, Any]) -> list[SourceRecord]:
        items = payload.get("items")
        if not isinstance(items, list):
            raise ConnectorError("ROR response is missing the items collection")
        records = []
        for item in items:
            if not isinstance(item, dict):
                raise ConnectorError("ROR response contains a malformed organization")
            identifier_pair = external_id("ror", item.get("id"))
            if identifier_pair is None:
                raise ConnectorError(
                    "ROR response contains an organization without a valid ID"
                )
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
        if not self.record_ids:
            return self._complete([], cursor)

        checkpoint = self.get_checkpoint()
        until = str(checkpoint.get("until") or datetime.now(UTC).isoformat())
        target_index = int(checkpoint.get("targetIndex", 0))
        if target_index < 0 or target_index > len(self.record_ids):
            raise ConnectorError("ROR checkpoint contains an invalid target index")
        page_size = max(1, min(limit, 100))
        targets = self.record_ids[target_index : target_index + page_size]
        replay_checkpoint = {"until": until, "targetIndex": target_index}
        self.set_replay_checkpoint(replay_checkpoint)
        records: list[SourceRecord] = []
        payloads: list[dict[str, Any]] = []
        for record_id in targets:
            payload = self.transport.get_json(
                f"{self.base_url}/organizations/{record_id}"
            )
            payloads.append(payload)
            candidates = (
                self._records(payload)
                if isinstance(payload.get("items"), list)
                else self._records({"items": [payload]})
            )
            if len(candidates) != 1 or candidates[0].source_record_id != record_id:
                raise ConnectorError(
                    f"ROR response did not match targeted record {record_id}"
                )
            records.append(candidates[0])

        next_index = target_index + len(targets)
        raw_payload = [
            {"contentType": "application/json", "body": payload} for payload in payloads
        ]
        if next_index < len(self.record_ids):
            return self._complete(
                records,
                cursor,
                {"until": until, "targetIndex": next_index},
                raw_payload=raw_payload,
                replay_checkpoint=replay_checkpoint,
            )
        return self._complete(
            records,
            until,
            raw_payload=raw_payload,
            replay_checkpoint=replay_checkpoint,
        )

    def fetch_record(self, record_id: str) -> SourceRecord | None:
        identifier = external_id("ror", record_id)
        if identifier is None:
            return None
        payload = self.transport.get_json(
            f"{self.base_url}/organizations/{identifier[1]}"
        )
        records = (
            self._records(payload)
            if isinstance(payload.get("items"), list)
            else self._records({"items": [payload]})
        )
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
