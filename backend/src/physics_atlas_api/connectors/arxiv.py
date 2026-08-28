from datetime import UTC, datetime, timedelta
from typing import Any
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as ET

from .base import (
    ConnectorBatch,
    ConnectorError,
    NormalizedRecord,
    SourceConnector,
    SourceRecord,
    compact_ids,
    external_id,
    parse_provider_datetime,
)
from .field_mapping import map_provider_categories

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


class ArxivConnector(SourceConnector):
    provider = "arxiv"
    source_version = "arXiv Query API Atom 1.0 / submittedDate stream"
    min_interval_seconds = 3.0

    @staticmethod
    def _text(entry: Element, name: str) -> str:
        element = entry.find(f"{ATOM}{name}")
        return " ".join((element.text or "").split()) if element is not None else ""

    def _records(self, xml: str) -> list[SourceRecord]:
        root = ET.fromstring(xml)
        records: list[SourceRecord] = []
        for entry in root.findall(f"{ATOM}entry"):
            identifier_url = self._text(entry, "id")
            title = self._text(entry, "title")
            if title.casefold() == "error" or "/api/errors#" in identifier_url:
                message = self._text(entry, "summary") or "unknown arXiv API error"
                raise ConnectorError(f"arXiv API returned an error feed: {message}")
            identifier_pair = external_id("arxiv", identifier_url)
            if identifier_pair is None:
                raise ConnectorError("arXiv API returned an entry without a valid ID")
            identifier = identifier_pair[1]
            authors = [
                self._text(author, "name") for author in entry.findall(f"{ATOM}author")
            ]
            categories = [
                category.attrib.get("term", "")
                for category in entry.findall(f"{ATOM}category")
                if category.attrib.get("term")
            ]
            doi_element = entry.find(f"{ARXIV}doi")
            raw: dict[str, Any] = {
                "id": identifier,
                "title": title,
                "summary": self._text(entry, "summary"),
                "published": self._text(entry, "published"),
                "updated": self._text(entry, "updated"),
                "authors": authors,
                "categories": categories,
                "doi": doi_element.text.strip()
                if doi_element is not None and doi_element.text
                else None,
            }
            records.append(
                SourceRecord(
                    provider=self.provider,
                    source_record_id=identifier,
                    raw=raw,
                    updated_at=parse_provider_datetime(raw["updated"]),
                )
            )
        return records

    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        # Provider categories are acquisition filters, not the Atlas field taxonomy.
        query = (
            "cat:physics.* OR cat:hep-* OR cat:gr-qc OR cat:quant-ph OR cat:cond-mat.*"
        )
        checkpoint = self.get_checkpoint()
        current_minute = datetime.now(UTC).replace(second=0, microsecond=0)
        until = str(checkpoint.get("until") or current_minute.isoformat())
        since = str(
            checkpoint.get("since")
            or cursor
            or (datetime.now(UTC) - timedelta(days=1)).isoformat()
        )
        start = int(checkpoint.get("start", 0))

        def compact_timestamp(value: str) -> str:
            parsed = parse_provider_datetime(value)
            if parsed is None:
                raise ConnectorError(f"Invalid arXiv checkpoint timestamp: {value}")
            return parsed.astimezone(UTC).strftime("%Y%m%d%H%M")

        query = (
            f"({query}) AND submittedDate:[{compact_timestamp(since)} "
            f"TO {compact_timestamp(until)}]"
        )
        page_size = min(limit, 100)
        xml = self.transport.get_text(
            self.base_url,
            params={
                "search_query": query,
                "start": start,
                "max_results": page_size,
                "sortBy": "submittedDate",
                "sortOrder": "ascending",
            },
        )
        records = self._records(xml)
        if len(records) >= page_size:
            return self._complete(
                records,
                cursor,
                {"since": since, "until": until, "start": start + len(records)},
                raw_payload=[{"contentType": "application/atom+xml", "body": xml}],
            )
        return self._complete(
            records,
            until,
            raw_payload=[{"contentType": "application/atom+xml", "body": xml}],
        )

    def fetch_updated_records(
        self, cursor: str | None, limit: int = 100
    ) -> ConnectorBatch:
        """Return new submissions; Query API dates cannot enumerate all revisions."""
        return self.fetch_new_records(cursor, limit)

    def fetch_record(self, record_id: str) -> SourceRecord | None:
        identifier = external_id("arxiv", record_id)
        if identifier is None:
            return None
        records = self._records(
            self.transport.get_text(
                self.base_url, params={"id_list": identifier[1], "max_results": 1}
            )
        )
        return records[0] if records else None

    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        raw = record.raw
        mapping = map_provider_categories("arxiv", raw.get("categories", []))
        return NormalizedRecord(
            provider=self.provider,
            kind="paper",
            source_record_id=record.source_record_id,
            canonical_name=raw["title"],
            external_ids=compact_ids(
                external_id("arxiv", record.source_record_id),
                external_id("doi", raw.get("doi")),
            ),
            attributes={
                "title": raw["title"],
                "abstract": raw.get("summary", ""),
                "publication_year": int(raw["published"][:4])
                if raw.get("published")
                else None,
                "authors": raw.get("authors", []),
                "raw_categories": raw.get("categories", []),
                "atlas_field_candidates": list(mapping.atlas_field_ids),
                "field_mapping_confidence": mapping.confidence,
                "field_mapping_method": mapping.method,
                "field_mapping_uncertainty": mapping.uncertainty_note,
            },
            raw=raw,
            updated_at=record.updated_at,
            provenance={
                "source": "arXiv API",
                "sourceType": "external-api",
                "version": self.source_version,
                "status": "unverified",
                "sourceRecordId": record.source_record_id,
                "retrievedAt": record.updated_at.isoformat()
                if record.updated_at
                else None,
            },
        )
