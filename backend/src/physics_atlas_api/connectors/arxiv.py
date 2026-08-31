from datetime import UTC, datetime, timedelta
from typing import Any
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as ET

from .acquisition import HEP_TH_V1, AcquisitionScope
from .base import (
    ConnectorBatch,
    ConnectorError,
    NormalizedRecord,
    SourceConnector,
    SourceRecord,
    SourceTransport,
    compact_ids,
    external_id,
    parse_provider_datetime,
)
from .field_mapping import (
    ARXIV_CATEGORY_TAXONOMY,
    ProviderCategoryEvidence,
    map_provider_categories,
)

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
ARXIV_CATEGORY_SCHEME = "http://arxiv.org/schemas/atom"


class ArxivConnector(SourceConnector):
    provider = "arxiv"
    source_version = "arXiv Query API Atom 1.0 / submittedDate stream"
    min_interval_seconds = 3.0

    def __init__(
        self,
        transport: SourceTransport,
        base_url: str,
        *,
        acquisition_scope: AcquisitionScope = HEP_TH_V1,
    ):
        super().__init__(
            transport,
            base_url,
            cursor_scope=acquisition_scope.cursor_scope(
                self.provider, "submitted-date-v1"
            ),
            dataset_scope=acquisition_scope.id,
        )
        self.acquisition_scope = acquisition_scope

    @staticmethod
    def _text(entry: Element, name: str) -> str:
        element = entry.find(f"{ATOM}{name}")
        return " ".join((element.text or "").split()) if element is not None else ""

    def _records(self, xml: str) -> list[SourceRecord]:
        root = ET.fromstring(xml)
        if root.tag != f"{ATOM}feed":
            raise ConnectorError("arXiv response is not an Atom feed")
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
            authors: list[dict[str, Any]] = []
            for author in entry.findall(f"{ATOM}author"):
                name = self._text(author, "name")
                affiliations = [
                    " ".join((item.text or "").split())
                    for item in author.findall(f"{ARXIV}affiliation")
                    if (item.text or "").strip()
                ]
                authors.append(
                    {
                        "name": name,
                        "full_name": name,
                        "affiliations": [{"value": value} for value in affiliations],
                        "raw_affiliations": [
                            {"value": value} for value in affiliations
                        ],
                    }
                )
            category_elements = entry.findall(f"{ATOM}category")
            categories = [
                category.attrib.get("term", "")
                for category in category_elements
                if category.attrib.get("term")
            ]
            primary_element = entry.find(f"{ARXIV}primary_category")
            primary_category = (
                primary_element.attrib.get("term")
                if primary_element is not None
                else None
            )
            primary_scheme = (
                primary_element.attrib.get("scheme")
                if primary_element is not None
                else None
            )
            category_evidence: list[dict[str, str | None]] = []
            for category in category_elements:
                term = category.attrib.get("term")
                if not term:
                    continue
                scheme = category.attrib.get("scheme")
                is_arxiv_taxonomy = scheme in (None, ARXIV_CATEGORY_SCHEME)
                is_primary = (
                    primary_category == term
                    and is_arxiv_taxonomy
                    and primary_scheme in (None, scheme, ARXIV_CATEGORY_SCHEME)
                )
                role = (
                    "primary"
                    if is_primary
                    else "secondary"
                    if primary_category is not None and is_arxiv_taxonomy
                    else "unspecified"
                )
                category_evidence.append(
                    {
                        "category": term,
                        "role": role,
                        "taxonomy": ARXIV_CATEGORY_TAXONOMY
                        if is_arxiv_taxonomy
                        else (scheme or "unspecified-category-scheme"),
                        "scheme": scheme,
                    }
                )
            if primary_category and not any(
                item["category"] == primary_category and item["role"] == "primary"
                for item in category_evidence
            ):
                category_evidence.insert(
                    0,
                    {
                        "category": primary_category,
                        "role": "primary",
                        "taxonomy": ARXIV_CATEGORY_TAXONOMY,
                        "scheme": primary_scheme,
                    },
                )
            doi_element = entry.find(f"{ARXIV}doi")
            journal_reference_element = entry.find(f"{ARXIV}journal_ref")
            raw: dict[str, Any] = {
                "id": identifier,
                "title": title,
                "summary": self._text(entry, "summary"),
                "published": self._text(entry, "published"),
                "updated": self._text(entry, "updated"),
                "authors": authors,
                "categories": categories,
                "primary_category": primary_category,
                "category_evidence": category_evidence,
                "doi": doi_element.text.strip()
                if doi_element is not None and doi_element.text
                else None,
                "journal_reference": journal_reference_element.text.strip()
                if journal_reference_element is not None
                and journal_reference_element.text
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
        query = self.acquisition_scope.arxiv_query
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
        replay_checkpoint = {"since": since, "until": until, "start": start}
        self.set_replay_checkpoint(replay_checkpoint)
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
                replay_checkpoint=replay_checkpoint,
            )
        return self._complete(
            records,
            until,
            raw_payload=[{"contentType": "application/atom+xml", "body": xml}],
            replay_checkpoint=replay_checkpoint,
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
        category_evidence = [
            ProviderCategoryEvidence(
                category=item["category"],
                role=item.get("role", "unspecified"),
                taxonomy=item.get("taxonomy"),
                scheme=item.get("scheme"),
            )
            for item in raw.get("category_evidence", [])
            if item.get("category")
        ]
        mapping = map_provider_categories(
            "arxiv", category_evidence or raw.get("categories", [])
        )
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
                "publication_date": raw.get("published"),
                "document_type": "preprint",
                "journal_reference": raw.get("journal_reference"),
                "authors": raw.get("authors", []),
                "raw_categories": raw.get("categories", []),
                "raw_category_evidence": raw.get("category_evidence", []),
                "atlas_field_candidates": list(mapping.atlas_field_ids),
                "field_mapping_confidence": mapping.confidence,
                "field_mapping_coverage": mapping.mapping_coverage,
                "field_mapping_method": mapping.method,
                "field_ontology_version": mapping.ontology_version,
                "field_weighting_policy_version": mapping.weighting_policy_version,
                "atlas_field_assignments": [
                    {
                        "field_id": assignment.field_id,
                        "weight": assignment.weight,
                    }
                    for assignment in mapping.assignments
                ],
                "field_mapping_provenance": mapping.provenance_payload(),
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
