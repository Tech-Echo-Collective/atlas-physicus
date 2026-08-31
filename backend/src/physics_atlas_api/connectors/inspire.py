from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

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
    provider_date,
)
from .field_mapping import (
    INSPIRE_CATEGORY_TAXONOMY,
    ProviderCategoryEvidence,
    map_provider_categories,
)


def _publication_year(raw: dict[str, Any]) -> int | None:
    publication_info = raw.get("publication_info")
    if isinstance(publication_info, list) and publication_info:
        first = publication_info[0]
        if isinstance(first, dict):
            value = first.get("year")
            if isinstance(value, int) and not isinstance(value, bool):
                return value

    earliest_date = raw.get("earliest_date")
    if not isinstance(earliest_date, str):
        return None
    normalized = earliest_date.strip()[:10]
    try:
        if len(normalized) == 4 and normalized.isdigit():
            return int(normalized)
        if len(normalized) == 7:
            return datetime.fromisoformat(f"{normalized}-01").year
        if len(normalized) == 10:
            return datetime.fromisoformat(normalized).year
    except ValueError:
        return None
    return None


class InspireConnector(SourceConnector):
    provider = "inspire"
    source_version = "INSPIRE REST API"
    min_interval_seconds = 1.0

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
                self.provider, "updated-articles-v1"
            ),
            dataset_scope=acquisition_scope.id,
        )
        self.acquisition_scope = acquisition_scope

    @staticmethod
    def _origin(url: str) -> tuple[str, str, int]:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme not in {"http", "https"} or not host:
            raise ConnectorError(
                "INSPIRE pagination URL must use HTTP(S) and include a host"
            )
        if parsed.username is not None or parsed.password is not None:
            raise ConnectorError("INSPIRE pagination URL must not include user info")
        try:
            port = parsed.port
        except ValueError as error:
            raise ConnectorError(
                "INSPIRE pagination URL has an invalid port"
            ) from error
        return parsed.scheme, host, port or (443 if parsed.scheme == "https" else 80)

    def _article_query(self, since: str, until: str) -> str:
        return (
            "document_type:article and "
            f"{self.acquisition_scope.inspire_query} and "
            f"du >= {since} and du <= {until}"
        )

    def _pagination_url(
        self,
        value: str,
        *,
        since: str,
        until: str,
        maximum_size: int,
    ) -> str:
        resolved = urljoin(f"{self.base_url}/", value)
        if self._origin(resolved) != self._origin(self.base_url):
            raise ConnectorError("INSPIRE pagination URL crossed its provider origin")
        parsed = urlparse(resolved)
        expected_path = urlparse(
            urljoin(f"{self.base_url}/", "literature")
        ).path.rstrip("/")
        if parsed.path.rstrip("/") != expected_path or parsed.fragment:
            raise ConnectorError(
                "INSPIRE pagination URL left the bounded literature endpoint"
            )
        query = parse_qs(parsed.query, keep_blank_values=True)
        expected_query = " ".join(self._article_query(since, until).split())
        supplied_queries = query.get("q", [])
        if len(supplied_queries) != 1 or (
            " ".join(supplied_queries[0].split()) != expected_query
        ):
            raise ConnectorError(
                "INSPIRE pagination URL changed the bounded acquisition query"
            )
        for value in query.get("size", []):
            try:
                page_size = int(value)
            except ValueError as error:
                raise ConnectorError(
                    "INSPIRE pagination URL contains an invalid page size"
                ) from error
            if page_size < 1 or page_size > maximum_size:
                raise ConnectorError(
                    "INSPIRE pagination URL exceeds the bounded page size"
                )
        return resolved

    def _records(self, payload: dict[str, Any]) -> list[SourceRecord]:
        hits = payload.get("hits")
        if not isinstance(hits, dict) or not isinstance(hits.get("hits"), list):
            raise ConnectorError("INSPIRE response is missing the hits.hits collection")
        records: list[SourceRecord] = []
        for hit in hits["hits"]:
            if not isinstance(hit, dict) or not isinstance(hit.get("metadata"), dict):
                raise ConnectorError("INSPIRE response contains a malformed hit")
            metadata = hit["metadata"]
            identifier_pair = external_id(
                "inspire", hit.get("id") or metadata.get("control_number")
            )
            if identifier_pair is None:
                raise ConnectorError(
                    "INSPIRE response contains a hit without a valid ID"
                )
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
        if next_url is not None and not isinstance(next_url, str):
            raise ConnectorError("INSPIRE checkpoint contains a malformed next URL")
        replay_checkpoint: dict[str, Any] = {"since": since, "until": until}
        maximum_size = min(limit, 250)
        if isinstance(next_url, str) and next_url:
            current_page_url = self._pagination_url(
                next_url,
                since=since,
                until=until,
                maximum_size=maximum_size,
            )
            replay_checkpoint["nextUrl"] = current_page_url
            self.set_replay_checkpoint(replay_checkpoint)
            payload = self.transport.get_json(current_page_url)
        else:
            self.set_replay_checkpoint(replay_checkpoint)
            payload = self.transport.get_json(
                f"{self.base_url}/literature",
                params={
                    "q": self._article_query(since, until),
                    "sort": "mostrecent",
                    "size": maximum_size,
                },
            )
        records = self._records(payload)
        if "links" not in payload:
            raise ConnectorError(
                "INSPIRE response is missing the pagination links envelope"
            )
        links = payload["links"]
        if not isinstance(links, dict):
            raise ConnectorError("INSPIRE response contains malformed pagination links")
        following = links.get("next")
        if following is not None and not isinstance(following, str):
            raise ConnectorError("INSPIRE response contains a malformed next link")
        if isinstance(following, str) and following:
            following = self._pagination_url(
                following,
                since=since,
                until=until,
                maximum_size=maximum_size,
            )
            return self._complete(
                records,
                cursor,
                {"since": since, "until": until, "nextUrl": following},
                raw_payload=[{"contentType": "application/json", "body": payload}],
                replay_checkpoint=replay_checkpoint,
            )
        return self._complete(
            records,
            until,
            raw_payload=[{"contentType": "application/json", "body": payload}],
            replay_checkpoint=replay_checkpoint,
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
        category_evidence = [
            ProviderCategoryEvidence(
                category=value["term"],
                role="unspecified",
                taxonomy=INSPIRE_CATEGORY_TAXONOMY,
                source=value.get("source"),
            )
            for value in raw.get("inspire_categories", [])
            if isinstance(value, dict) and value.get("term")
        ]
        categories = [item.category for item in category_evidence]
        mapping = map_provider_categories("inspire", category_evidence)
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
                "publication_year": _publication_year(raw),
                "publication_date": raw.get("earliest_date"),
                "document_type": (
                    (raw.get("document_type") or ["article"])[0]
                    if isinstance(raw.get("document_type"), list)
                    else raw.get("document_type") or "article"
                ),
                "raw_categories": categories,
                "raw_category_evidence": [
                    {
                        "category": item.category,
                        "role": item.role,
                        "taxonomy": item.taxonomy,
                        "source": item.source,
                    }
                    for item in category_evidence
                ],
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
                "authors": raw.get("authors", []),
                "citation_count": raw.get("citation_count"),
                "citation_count_without_self_citations": raw.get(
                    "citation_count_without_self_citations"
                ),
                "citation_evidence_method": "provider-reported-aggregate-counts",
                "citation_evidence_version": "inspire-citation-evidence-v1",
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
