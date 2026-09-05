"""Automatic citation population evidence for one complete provider response.

Completeness here means the complete declared INSPIRE query, not a complete
canonical publication year or a multi-year metric window. The trusted caller
supplies the actual live transport response, receipt timestamp and existing
canonical identity mapping. A checksum detects changes; it does not authenticate
an arbitrary caller or turn supplied facts into provider evidence. Counts and
field candidates use the existing INSPIRE normalizer. Metric dates require an
explicit source-field basis through AutomaticDateEvidence, never earliest_date.
No network access, payload persistence, human reviewer or metric activation occurs.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime

from ..connectors.acquisition import COND_MAT_HISTORICAL_VALIDATION_V1, HEP_TH_V1
from ..connectors.base import normalize_external_id
from ..connectors.inspire import InspireConnector
from ..fields import PHYSICS_FIELD_ONTOLOGY_V1
from .automation import (
    AutomaticCertification,
    AutomaticDateEvidence,
    AutomaticEvidenceContext,
    ProviderDateFact,
    ResolvedDateBasis,
)
from .citations import (
    CITATION_POLICY_VERSION,
    CitationCohortPopulationEvidence,
    CitationObservationCertification,
    CitationObservationEvidence,
    certify_citation_observation,
)
from .contracts import CertificationError, EvidenceReference, canonical_digest

AUTOMATIC_CITATION_POPULATION_VERSION = "complete-query-citation-population-v1"
MAX_SINGLE_RESPONSE_RECORDS = 1_000
MAX_QUERY_YEARS = 6
_SCOPES = {scope.id: scope for scope in (HEP_TH_V1, COND_MAT_HISTORICAL_VALIDATION_V1)}


def citation_population_query(
    acquisition_scope: str,
    calendar_year: int,
    end_calendar_year: int | None = None,
) -> str:
    final_year = calendar_year if end_calendar_year is None else end_calendar_year
    if (
        acquisition_scope not in _SCOPES
        or not 1900 <= calendar_year <= final_year <= 9998
        or final_year - calendar_year >= MAX_QUERY_YEARS
    ):
        raise CertificationError("unsupported citation acquisition scope or year")
    return (
        f"document_type:article and {_SCOPES[acquisition_scope].inspire_query} "
        f"and date >= {calendar_year}-01-01 and date <= {final_year}-12-31"
    )


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


@dataclass(frozen=True)
class CitationResponseRecord:
    source_record_id: str
    paper_id: str
    source_record_checksum: str
    publication_date: date | None
    field_ids: tuple[str, ...]
    document_type: str | None
    raw_citation_count: int | None
    non_self_citation_count: int | None
    date_evidence: AutomaticDateEvidence
    unresolved_membership: tuple[str, ...] = ()


@dataclass(frozen=True)
class SingleResponseCitationReceipt:
    acquisition_scope: str
    dataset_version: str
    calendar_year: int
    query: str
    observed_at: datetime
    source_snapshot_id: str
    response_sha256: str
    reported_total: int
    records: tuple[CitationResponseRecord, ...]
    declared_date_basis: str
    end_calendar_year: int | None = None
    source: str = "inspire"
    source_version: str = "INSPIRE REST API"
    endpoint: str = "https://inspirehep.net/api/literature"
    page: int = 1
    next_page: str | None = None
    version: str = AUTOMATIC_CITATION_POPULATION_VERSION

    def __post_init__(self) -> None:
        validate_single_response_receipt(self)

    @property
    def content_digest(self) -> str:
        return canonical_digest(self)


def validate_single_response_receipt(receipt: SingleResponseCitationReceipt) -> None:
    if (
        receipt.version != AUTOMATIC_CITATION_POPULATION_VERSION
        or receipt.source != "inspire"
        or receipt.source_version != InspireConnector.source_version
        or receipt.endpoint != "https://inspirehep.net/api/literature"
        or receipt.query
        != citation_population_query(
            receipt.acquisition_scope, receipt.calendar_year, receipt.end_calendar_year
        )
        or not receipt.dataset_version.strip()
        or not receipt.source_snapshot_id.strip()
        or not _aware(receipt.observed_at)
        or not _sha256(receipt.response_sha256)
        or not receipt.declared_date_basis.strip()
    ):
        raise CertificationError("citation response source/query/version is invalid")
    if (
        isinstance(receipt.reported_total, bool)
        or not isinstance(receipt.reported_total, int)
        or not 1 <= receipt.reported_total <= MAX_SINGLE_RESPONSE_RECORDS
        or receipt.reported_total != len(receipt.records)
        or isinstance(receipt.page, bool)
        or receipt.page != 1
        or receipt.next_page is not None
    ):
        raise CertificationError(
            "citation query is not complete in one bounded response"
        )
    if len({row.source_record_id for row in receipt.records}) != len(
        receipt.records
    ) or len({row.paper_id for row in receipt.records}) != len(receipt.records):
        raise CertificationError(
            "citation source or canonical identities are duplicated"
        )
    for row in receipt.records:
        if (
            not row.source_record_id.strip()
            or not row.paper_id.strip()
            or not _sha256(row.source_record_checksum)
            or len(set(row.field_ids)) != len(row.field_ids)
            or any(
                not PHYSICS_FIELD_ONTOLOGY_V1.contains(field_id)
                or PHYSICS_FIELD_ONTOLOGY_V1.get(field_id).node_kind != "field"
                for field_id in row.field_ids
            )
        ):
            raise CertificationError("citation response canonical record is invalid")
        for count in (row.raw_citation_count, row.non_self_citation_count):
            if count is not None and (
                isinstance(count, bool) or not isinstance(count, int) or count < 0
            ):
                raise CertificationError("citation counts must be nonnegative integers")
        date_evidence = row.date_evidence
        if (
            not isinstance(date_evidence, AutomaticDateEvidence)
            or date_evidence.context
            != AutomaticEvidenceContext(
                paper_id=row.paper_id,
                dataset_version=receipt.dataset_version,
                acquisition_scope=receipt.acquisition_scope,
            )
            or date_evidence.declared_basis != receipt.declared_date_basis
        ):
            raise CertificationError("citation date evidence does not bind the record")
        expected_date, _ = _assessed_date(date_evidence)
        if row.publication_date != expected_date:
            raise CertificationError(
                "citation date differs from its declared source basis"
            )


def _assessed_date(
    evidence: AutomaticDateEvidence,
) -> tuple[date | None, tuple[str, ...]]:
    assessment = AutomaticCertification(evidence)
    value = assessment.value
    if not isinstance(value, ResolvedDateBasis):
        raise CertificationError(
            "citation date assessment returned the wrong value type"
        )
    return (
        value.exact_date if assessment.decision.state == "certified" else None,
        assessment.decision.reasons,
    )


def capture_single_response_citations(
    response_bytes: bytes,
    *,
    connector: InspireConnector,
    query: str,
    calendar_year: int,
    observed_at: datetime,
    source_snapshot_id: str,
    dataset_version: str,
    canonical_paper_ids: Mapping[str, str],
    declared_date_basis: str,
    end_calendar_year: int | None = None,
    canonical_date_evidence: Mapping[str, AutomaticDateEvidence] | None = None,
) -> SingleResponseCitationReceipt:
    """Compact the entire received response using the existing provider parser.

    The caller must bind these bytes/query/time to its real transport acquisition
    and supply identities from canonicalization, not an arbitrary user upload.
    Unknown membership facts are retained explicitly and prevent an exact cohort.
    A provider earliest-date query is never asserted to cover canonical dates.
    Without upstream date evidence, only explicit INSPIRE preprint_date facts
    are available. A caller requesting journal dates must supply source-bound
    canonical date evidence from the supported journal date certification path.
    Multi-year queries still require one complete response and one exact cutoff;
    combining separately acquired yearly responses is not supported.
    """
    if type(connector) is not InspireConnector or connector.base_url != (
        "https://inspirehep.net/api"
    ):
        raise CertificationError("automatic citation capture requires INSPIRE parser")
    payload = json.loads(response_bytes)
    if not isinstance(payload, dict) or not isinstance(payload.get("hits"), dict):
        raise CertificationError("citation response has no provider hits envelope")
    total = payload["hits"].get("total")
    if isinstance(total, dict):
        if total.get("relation") != "eq":
            raise CertificationError("citation response total is not exact")
        total = total.get("value")
    if not isinstance(total, int) or isinstance(total, bool):
        raise CertificationError("citation response requires an exact reported total")
    hits = payload["hits"].get("hits")
    if (
        not 1 <= total <= MAX_SINGLE_RESPONSE_RECORDS
        or not isinstance(hits, list)
        or len(hits) != total
    ):
        raise CertificationError(
            "citation query is not complete in one bounded response"
        )
    links = payload.get("links")
    if not isinstance(links, dict) or links.get("next"):
        raise CertificationError("citation response is incomplete or has another page")
    records = connector._records(payload)
    if set(canonical_paper_ids) != {record.source_record_id for record in records}:
        raise CertificationError(
            "canonical identity mapping must cover all source records"
        )
    if canonical_date_evidence is not None and set(canonical_date_evidence) != set(
        canonical_paper_ids
    ):
        raise CertificationError(
            "canonical date evidence must cover all source records"
        )
    compact: list[CitationResponseRecord] = []
    for record in records:
        normalized = connector.normalize_record(record)
        attributes = normalized.attributes
        source_reference = EvidenceReference(
            provider="inspire",
            source_record_id=record.source_record_id,
            checksum=record.checksum,
            source_snapshot_id=source_snapshot_id,
        )
        preprint_value = record.raw.get("preprint_date")
        preprint_facts = (
            (
                ProviderDateFact(
                    reference=source_reference,
                    basis="inspire-preprint-date",
                    source_field="preprint_date",
                    value=preprint_value,
                ),
            )
            if isinstance(preprint_value, str)
            else ()
        )
        date_evidence = (
            canonical_date_evidence[record.source_record_id]
            if canonical_date_evidence is not None
            else AutomaticDateEvidence(
                context=AutomaticEvidenceContext(
                    paper_id=canonical_paper_ids[record.source_record_id],
                    dataset_version=dataset_version,
                    acquisition_scope=connector.acquisition_scope.id,
                ),
                declared_basis=declared_date_basis,
                facts=preprint_facts,
            )
        )
        # Supplied canonical dates may cite a journal source, but any facts
        # attributed to this INSPIRE response must match its actual preprint field.
        if any(
            fact.reference.provider == "inspire" and fact not in preprint_facts
            for fact in date_evidence.facts
        ):
            raise CertificationError(
                "citation date fact differs from the INSPIRE source"
            )
        for fact in date_evidence.facts:
            if fact.reference.provider == "inspire":
                continue
            scheme = {"crossref": "doi", "arxiv": "arxiv"}.get(fact.reference.provider)
            if (
                scheme is None
                or normalize_external_id(scheme, fact.reference.source_record_id)
                not in normalized.external_ids
            ):
                raise CertificationError(
                    "external citation date evidence does not bind a source paper ID"
                )
        publication_date, date_reasons = _assessed_date(date_evidence)
        fields = tuple(sorted(attributes.get("atlas_field_candidates", ())))
        # The legacy normalizer defaults a missing document type to article;
        # that display convenience is not evidence for cohort membership.
        raw_types = record.raw.get("document_type")
        document_type = (
            raw_types[0]
            if isinstance(raw_types, list)
            and len(raw_types) == 1
            and isinstance(raw_types[0], str)
            and raw_types[0].strip()
            else raw_types
            if isinstance(raw_types, str) and raw_types.strip()
            else None
        )
        unresolved = date_reasons + tuple(
            reason
            for condition, reason in (
                (publication_date is None, "exact publication date is missing"),
                (not fields, "mapped provider field is missing"),
                (
                    attributes.get("field_mapping_coverage") != 1.0,
                    "provider field classification has unmapped mass",
                ),
                (
                    document_type is None,
                    "explicit document type is missing or ambiguous",
                ),
            )
            if condition
        )
        compact.append(
            CitationResponseRecord(
                source_record_id=record.source_record_id,
                paper_id=canonical_paper_ids[record.source_record_id],
                source_record_checksum=record.checksum,
                publication_date=publication_date,
                field_ids=fields,
                document_type=document_type,
                raw_citation_count=attributes.get("citation_count"),
                non_self_citation_count=attributes.get(
                    "citation_count_without_self_citations"
                ),
                date_evidence=date_evidence,
                unresolved_membership=unresolved,
            )
        )
    return SingleResponseCitationReceipt(
        acquisition_scope=connector.acquisition_scope.id,
        dataset_version=dataset_version,
        calendar_year=calendar_year,
        query=query,
        observed_at=observed_at,
        source_snapshot_id=source_snapshot_id,
        response_sha256=hashlib.sha256(response_bytes).hexdigest(),
        reported_total=total,
        records=tuple(compact),
        declared_date_basis=declared_date_basis,
        end_calendar_year=end_calendar_year,
    )


def derive_citation_observations(
    receipt: SingleResponseCitationReceipt,
    cohort_key: tuple[str, int, str],
) -> tuple[CitationObservationCertification, ...]:
    validate_single_response_receipt(receipt)
    if any(
        row.unresolved_membership
        or row.publication_date is None
        or not row.field_ids
        or row.document_type is None
        for row in receipt.records
    ):
        raise CertificationError(
            "unresolved source records prevent exact cohort membership"
        )
    field_id, year, document_type = cohort_key
    if (
        not PHYSICS_FIELD_ONTOLOGY_V1.contains(field_id)
        or PHYSICS_FIELD_ONTOLOGY_V1.get(field_id).node_kind != "field"
        or year < 1900
        or not document_type.strip()
    ):
        raise CertificationError("automatic citation cohort key is invalid")
    observations: list[CitationObservationCertification] = []
    for row in receipt.records:
        assert row.publication_date is not None
        if (
            field_id not in row.field_ids
            or row.publication_date.year != year
            or row.document_type != document_type
        ):
            continue
        observations.append(
            certify_citation_observation(
                CitationObservationEvidence(
                    paper_id=row.paper_id,
                    dataset_version=receipt.dataset_version,
                    acquisition_scope=receipt.acquisition_scope,
                    citation_source=receipt.source,
                    raw_citation_count=row.raw_citation_count,
                    non_self_citation_count=row.non_self_citation_count,
                    observed_at=receipt.observed_at,
                    selected_cutoff=receipt.observed_at,
                    publication_date=row.publication_date,
                    field_id=field_id,
                    document_type=document_type,
                    source_reference=EvidenceReference(
                        provider=receipt.source,
                        source_record_id=row.source_record_id,
                        checksum=row.source_record_checksum,
                        source_snapshot_id=receipt.source_snapshot_id,
                        storage_reference=f"citation-response:{receipt.response_sha256}",
                    ),
                    citation_policy_version=CITATION_POLICY_VERSION,
                )
            )
        )
    return tuple(sorted(observations, key=lambda item: item.paper_id))


@dataclass(frozen=True)
class AutomaticCitationCohortPopulationEvidence(CitationCohortPopulationEvidence):
    receipt: SingleResponseCitationReceipt
    automatic_rule_version: str = AUTOMATIC_CITATION_POPULATION_VERSION

    @property
    def content_digest(self) -> str:
        return canonical_digest(
            (
                super().content_digest,
                self.receipt.content_digest,
                self.automatic_rule_version,
            )
        )


def build_automatic_citation_population(
    receipt: SingleResponseCitationReceipt,
    cohort_key: tuple[str, int, str],
) -> AutomaticCitationCohortPopulationEvidence:
    observations = derive_citation_observations(receipt, cohort_key)
    if not observations:
        raise CertificationError("declared query contains no target cohort members")
    evidence = AutomaticCitationCohortPopulationEvidence(
        cohort_key=cohort_key,
        cutoff=receipt.observed_at,
        dataset_version=receipt.dataset_version,
        acquisition_scope=receipt.acquisition_scope,
        eligible_paper_ids=tuple(item.paper_id for item in observations),
        source_manifest_digest="0" * 64,
        review_state="automatic-evidence-derived",
        reviewed_by=None,
        reviewed_at=None,
        receipt=receipt,
    )
    return replace(evidence, source_manifest_digest=evidence.content_digest)


def validate_automatic_citation_population(
    evidence: AutomaticCitationCohortPopulationEvidence,
) -> None:
    expected = build_automatic_citation_population(
        evidence.receipt, evidence.cohort_key
    )
    if evidence != expected:
        raise CertificationError(
            "automatic citation population differs from source derivation"
        )


def validate_automatic_citation_observations(
    evidence: AutomaticCitationCohortPopulationEvidence,
    observations: tuple[CitationObservationCertification, ...],
) -> None:
    validate_automatic_citation_population(evidence)
    expected = derive_citation_observations(evidence.receipt, evidence.cohort_key)
    if tuple(sorted(observations, key=lambda item: item.paper_id)) != expected:
        raise CertificationError(
            "citation observations differ from the complete response"
        )
