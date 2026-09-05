"""Bounded retrospective citation measurement, not an upstream snapshot.

Actual page request/response times are retained. Contiguous pagination with stable
totals cannot prove a provider snapshot under concurrent edits. A session must
match an independently frozen identity inventory exactly; the caller must bind
that inventory reference to authoritative canonical evidence before activation.
The reference checksum proves content integrity, not scientific authority.
No network requests, raw payload retention, date inference or metric activation.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlsplit

from ..connectors.inspire import InspireConnector
from .automatic_citations import (
    MAX_SINGLE_RESPONSE_RECORDS,
    CitationResponseRecord,
    _aware,
    _compact_citation_records,
    _derive_citation_observations,
    _sha256,
    _validate_compact_citation_records,
    citation_population_query,
)
from .automation import AutomaticDateEvidence
from .citations import CitationObservationCertification
from .contracts import CertificationError, EvidenceReference, canonical_digest

CITATION_MEASUREMENT_WINDOW_VERSION = "citation-measurement-window-v1"
# Operational acquisition bound, NOT a claim that counts are simultaneous.
MAX_MEASUREMENT_WINDOW_SECONDS = 30 * 60
MAX_MEASUREMENT_SESSION_PAGES = 100
# Pre-parse allocation bound only. The transport must bound streaming acquisition
# separately; this does not enforce the whole build's 2 GB temporary-disk quota.
MAX_CITATION_RESPONSE_BYTES = 8 * 1024 * 1024
CAPTURED_MEMBERSHIP_SEMANTICS = "captured-population-not-provider-snapshot"
RETROSPECTIVE_MEASUREMENT_INTERPRETATION = "retrospective-citation-measurement"


def explicit_citation_id_query(source_ids: tuple[str, ...]) -> str:
    """Only exact provider record IDs; no mutable field/date sort population."""
    if (
        not 1 <= len(source_ids) <= MAX_SINGLE_RESPONSE_RECORDS
        or len(set(source_ids)) != len(source_ids)
        or any(
            not item.isascii()
            or not item.isdigit()
            or str(int(item)) != item
            or int(item) < 1
            for item in source_ids
        )
    ):
        raise CertificationError(
            "explicit citation batch requires unique canonical INSPIRE IDs"
        )
    return (
        "(" + " or ".join(f"recid:{item}" for item in sorted(source_ids, key=int)) + ")"
    )


def _page_request(url: str) -> dict[str, str]:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "inspirehep.net"
        or parsed.path.rstrip("/") != "/api/literature"
        or parsed.fragment
    ):
        raise CertificationError("citation page left the INSPIRE endpoint")
    values = parse_qs(parsed.query, keep_blank_values=True)
    if (
        set(values) - {"q", "page", "size", "sort", "fields"}
        or any(len(items) != 1 for items in values.values())
        or not values.get("q", [""])[0].strip()
        or "size" not in values
    ):
        raise CertificationError("citation page request is ambiguous or unbounded")
    result = {key: items[0] for key, items in values.items()}
    result.setdefault("page", "1")
    try:
        page, size = int(result["page"]), int(result["size"])
    except ValueError as error:
        raise CertificationError("citation page/size is not an integer") from error
    if not 1 <= page <= MAX_MEASUREMENT_SESSION_PAGES or not (
        1 <= size <= MAX_SINGLE_RESPONSE_RECORDS
    ):
        raise CertificationError("citation page/size exceeds bounded acquisition")
    result["page"], result["size"] = str(page), str(size)
    return result


@dataclass(frozen=True)
class FrozenCitationPopulationEvidence:
    """Compact identity inventory frozen independently BEFORE citation capture.

    Upstream authority must be checked by the population-certification caller.
    This type only verifies the inventory reference, lineage and exact identities.
    """

    reference: EvidenceReference
    dataset_version: str
    acquisition_scope: str
    declared_date_basis: str
    frozen_at: datetime
    provider_to_canonical: tuple[tuple[str, str], ...]

    @property
    def inventory_digest(self) -> str:
        return canonical_digest(tuple(sorted(self.provider_to_canonical)))

    def validate(self) -> None:
        pairs = self.provider_to_canonical
        if (
            not isinstance(self.reference, EvidenceReference)
            or not self.reference.source_snapshot_id
            or self.reference.checksum != self.inventory_digest
            or not _aware(self.frozen_at)
            or not self.dataset_version.strip()
            or not self.acquisition_scope.strip()
            or not self.declared_date_basis.strip()
            or not pairs
            or len({provider_id for provider_id, _ in pairs}) != len(pairs)
            or len({paper_id for _, paper_id in pairs}) != len(pairs)
            or any(
                not provider_id.strip() or not paper_id.strip()
                for provider_id, paper_id in pairs
            )
        ):
            raise CertificationError(
                "frozen citation population identity/reference is invalid"
            )


@dataclass(frozen=True)
class CitationSessionPage:
    request_url: str
    requested_at: datetime
    received_at: datetime
    dataset_version: str
    acquisition_scope: str
    calendar_year: int
    end_calendar_year: int | None
    declared_date_basis: str
    source_snapshot_id: str
    response_sha256: str
    reported_total: int
    records: tuple[CitationResponseRecord, ...]
    next_url: str | None
    source: str = "inspire"
    source_version: str = "INSPIRE REST API"
    expected_source_ids: tuple[str, ...] | None = None

    def validate(self) -> None:
        request = _page_request(self.request_url)
        scope_query = citation_population_query(
            self.acquisition_scope, self.calendar_year, self.end_calendar_year
        )
        expected_query = (
            scope_query
            if self.expected_source_ids is None
            else explicit_citation_id_query(self.expected_source_ids)
        )
        if (
            request["q"] != expected_query
            or self.source != "inspire"
            or self.source_version != InspireConnector.source_version
            or not self.dataset_version.strip()
            or not self.source_snapshot_id.strip()
            or not self.declared_date_basis.strip()
            or not _sha256(self.response_sha256)
            or not _aware(self.requested_at)
            or not _aware(self.received_at)
            or self.requested_at > self.received_at
        ):
            raise CertificationError(
                "citation page lineage/query/timestamps are invalid"
            )
        size, page = int(request["size"]), int(request["page"])
        if (
            isinstance(self.reported_total, bool)
            or not isinstance(self.reported_total, int)
            or not 1 <= self.reported_total <= size * MAX_MEASUREMENT_SESSION_PAGES
            or len(self.records) != min(size, self.reported_total - (page - 1) * size)
            or not self.records
        ):
            raise CertificationError("citation page count/total is inconsistent")
        has_more = page * size < self.reported_total
        if has_more != (self.next_url is not None):
            raise CertificationError(
                "citation page continuation does not match its total"
            )
        if self.next_url is not None and _page_request(self.next_url) != {
            **request,
            "page": str(page + 1),
        }:
            raise CertificationError(
                "citation next link changed query or skipped a page"
            )
        if self.expected_source_ids is not None and (
            page != 1
            or self.next_url is not None
            or self.reported_total != len(self.expected_source_ids)
            or {row.source_record_id for row in self.records}
            != set(self.expected_source_ids)
        ):
            raise CertificationError(
                "explicit citation batch lost or added requested IDs"
            )
        _validate_compact_citation_records(
            self.records,
            dataset_version=self.dataset_version,
            acquisition_scope=self.acquisition_scope,
            declared_date_basis=self.declared_date_basis,
        )


def capture_citation_session_page(
    response_bytes: bytes,
    *,
    connector: InspireConnector,
    request_url: str,
    requested_at: datetime,
    received_at: datetime,
    dataset_version: str,
    calendar_year: int,
    declared_date_basis: str,
    source_snapshot_id: str,
    canonical_paper_ids: Mapping[str, str],
    end_calendar_year: int | None = None,
    canonical_date_evidence: Mapping[str, AutomaticDateEvidence] | None = None,
    expected_source_ids: tuple[str, ...] | None = None,
) -> CitationSessionPage:
    """Parse one actual transport response; never manufacture a common cutoff."""
    if len(response_bytes) > MAX_CITATION_RESPONSE_BYTES:
        raise CertificationError("citation response exceeds the 8 MiB parsing bound")
    request = _page_request(request_url)
    if type(connector) is not InspireConnector or connector.base_url != (
        "https://inspirehep.net/api"
    ):
        raise CertificationError(
            "citation measurement requires the existing INSPIRE parser"
        )
    payload = json.loads(response_bytes)
    if not isinstance(payload, dict) or not isinstance(payload.get("hits"), dict):
        raise CertificationError("citation response has no provider hits envelope")
    total = payload["hits"].get("total")
    if isinstance(total, dict):
        if total.get("relation") != "eq":
            raise CertificationError("citation measurement total is not exact")
        total = total.get("value")
    hits = payload["hits"].get("hits")
    if (
        not isinstance(total, int)
        or isinstance(total, bool)
        or not 1 <= total <= int(request["size"]) * MAX_MEASUREMENT_SESSION_PAGES
        or not isinstance(hits, list)
        or not 1 <= len(hits) <= int(request["size"])
    ):
        raise CertificationError("citation response exceeds the declared bounded page")
    links = payload.get("links")
    if not isinstance(links, dict):
        raise CertificationError("citation response lacks pagination evidence")
    following = links.get("next")
    if following is not None and not isinstance(following, str):
        raise CertificationError("citation response next link is malformed")
    page = CitationSessionPage(
        request_url=request_url,
        requested_at=requested_at,
        received_at=received_at,
        dataset_version=dataset_version,
        acquisition_scope=connector.acquisition_scope.id,
        calendar_year=calendar_year,
        end_calendar_year=end_calendar_year,
        declared_date_basis=declared_date_basis,
        source_snapshot_id=source_snapshot_id,
        response_sha256=hashlib.sha256(response_bytes).hexdigest(),
        reported_total=total,
        records=_compact_citation_records(
            connector._records(payload),
            connector=connector,
            source_snapshot_id=source_snapshot_id,
            dataset_version=dataset_version,
            canonical_paper_ids=canonical_paper_ids,
            declared_date_basis=declared_date_basis,
            canonical_date_evidence=canonical_date_evidence,
        ),
        next_url=urljoin(request_url, following) if following else None,
        expected_source_ids=expected_source_ids,
    )
    page.validate()
    return page


@dataclass(frozen=True)
class CitationMeasurementSession:
    pages: tuple[CitationSessionPage, ...]
    frozen_population: FrozenCitationPopulationEvidence
    version: str = CITATION_MEASUREMENT_WINDOW_VERSION
    membership_semantics: str = CAPTURED_MEMBERSHIP_SEMANTICS
    interpretation: str = RETROSPECTIVE_MEASUREMENT_INTERPRETATION

    def __post_init__(self) -> None:
        self.validate()

    @property
    def session_id(self) -> str:
        return f"citation-session-{canonical_digest(self)}"

    @property
    def measurement_started_at(self) -> datetime:
        return self.pages[0].requested_at

    @property
    def measurement_finished_at(self) -> datetime:
        return self.pages[-1].received_at

    def validate(self) -> None:
        if (
            self.version != CITATION_MEASUREMENT_WINDOW_VERSION
            or self.membership_semantics != CAPTURED_MEMBERSHIP_SEMANTICS
            or self.interpretation != RETROSPECTIVE_MEASUREMENT_INTERPRETATION
            or not 1 <= len(self.pages) <= MAX_MEASUREMENT_SESSION_PAGES
        ):
            raise CertificationError(
                "citation session version or page bound is invalid"
            )
        self.frozen_population.validate()
        first = self.pages[0]
        baseline = _page_request(first.request_url)
        explicit_batches = first.expected_source_ids is not None
        if baseline["page"] != "1":
            raise CertificationError("citation session must begin with page one")
        identities: list[tuple[str, str]] = []
        for index, page in enumerate(self.pages):
            page.validate()
            request = _page_request(page.request_url)
            request_matches = (
                {key: value for key, value in request.items() if key != "q"}
                == {key: value for key, value in baseline.items() if key != "q"}
                if explicit_batches
                else request == {**baseline, "page": str(index + 1)}
            )
            if (
                not request_matches
                or (page.expected_source_ids is not None) != explicit_batches
                or (
                    not explicit_batches and page.reported_total != first.reported_total
                )
                or page.dataset_version != first.dataset_version
                or page.acquisition_scope != first.acquisition_scope
                or page.declared_date_basis != first.declared_date_basis
                or page.calendar_year != first.calendar_year
                or page.end_calendar_year != first.end_calendar_year
                or page.source_version != first.source_version
            ):
                raise CertificationError(
                    "citation session page lineage or provider total drifted"
                )
            previous = self.pages[index - 1] if index else None
            if previous is not None and (
                previous.received_at > page.requested_at
                or (
                    not explicit_batches
                    and (
                        previous.next_url is None
                        or _page_request(previous.next_url) != request
                    )
                )
            ):
                raise CertificationError(
                    "citation session pages are interrupted or not sequential"
                )
            identities.extend(
                (row.source_record_id, row.paper_id) for row in page.records
            )
        if (
            self.pages[-1].next_url is not None
            or (not explicit_batches and len(identities) != first.reported_total)
            or len({item[0] for item in identities}) != len(identities)
            or len({item[1] for item in identities}) != len(identities)
            or len({page.source_snapshot_id for page in self.pages}) != len(self.pages)
            or len({page.response_sha256 for page in self.pages}) != len(self.pages)
        ):
            raise CertificationError(
                "citation session lost, duplicated or omitted source records"
            )
        frozen = self.frozen_population
        if (
            tuple(sorted(identities)) != tuple(sorted(frozen.provider_to_canonical))
            or frozen.dataset_version != first.dataset_version
            or frozen.acquisition_scope != first.acquisition_scope
            or frozen.declared_date_basis != first.declared_date_basis
            or frozen.frozen_at > self.measurement_started_at
        ):
            raise CertificationError(
                "citation capture differs from the independently frozen population"
            )
        if (
            self.measurement_finished_at - self.measurement_started_at
        ).total_seconds() > MAX_MEASUREMENT_WINDOW_SECONDS:
            raise CertificationError(
                "citation session exceeds its operational measurement window"
            )


def derive_session_citation_observations(
    session: CitationMeasurementSession,
    cohort_key: tuple[str, int, str],
) -> tuple[CitationObservationCertification, ...]:
    session.validate()
    return tuple(
        sorted(
            (
                observation
                for page in session.pages
                for observation in _derive_citation_observations(
                    page.records,
                    cohort_key,
                    dataset_version=page.dataset_version,
                    acquisition_scope=page.acquisition_scope,
                    source=page.source,
                    observed_at=page.received_at,
                    source_snapshot_id=page.source_snapshot_id,
                    response_sha256=page.response_sha256,
                )
            ),
            key=lambda item: item.paper_id,
        )
    )


def build_citation_measurement_session(
    pages: tuple[CitationSessionPage, ...],
    frozen_population: FrozenCitationPopulationEvidence,
) -> CitationMeasurementSession:
    return CitationMeasurementSession(pages, frozen_population)


@dataclass(frozen=True)
class CitationSessionPopulation:
    """Derived captured membership; separate authority is required for activation."""

    session: CitationMeasurementSession
    cohort_key: tuple[str, int, str]

    def __post_init__(self) -> None:
        if not self.observations:
            raise CertificationError(
                "citation session contains no target cohort members"
            )

    @property
    def observations(self) -> tuple[CitationObservationCertification, ...]:
        return derive_session_citation_observations(self.session, self.cohort_key)

    @property
    def eligible_paper_ids(self) -> tuple[str, ...]:
        return tuple(item.paper_id for item in self.observations)

    @property
    def content_digest(self) -> str:
        return canonical_digest(self)


def derive_session_citation_population(
    session: CitationMeasurementSession,
    cohort_key: tuple[str, int, str],
) -> CitationSessionPopulation:
    return CitationSessionPopulation(session, cohort_key)
