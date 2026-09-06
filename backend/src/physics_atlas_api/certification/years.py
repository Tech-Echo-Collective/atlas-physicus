from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Literal

from ..attribution import FRACTIONAL_ATTRIBUTION_V1
from ..backfill import HistoricalPartition, build_partitions
from ..fields import FIELD_WEIGHTING_POLICY_VERSION, PHYSICS_FIELD_ONTOLOGY_V1
from .citations import (
    CITATION_CERTIFICATION_RULE_VERSION,
    IMPACT_REFERENCE_COHORT_MINIMUM_V1,
    CitationCohortCertification,
)
from .contracts import (
    CertificationError,
    CertificationState,
    CertifiedCitationCohort,
    CoverageCertification,
    EvidenceCertificationDecision,
    EvidenceKind,
    EvidenceReference,
    MetricWindowCertification,
    SourceYearCertification,
    canonical_digest,
)
from .coverage import COVERAGE_SUBJECT_TYPE, validate_coverage_certification
from .field_mass import SourceFieldMassPopulation
from .launch_scope import BoundedLaunchSourcePlan
from .rules import (
    coverage_minimum,
    evidence_decision_is_current,
    required_coverage_evidence,
    required_window_years,
)
from .source_pages import SourceRecordPageReceipt

if TYPE_CHECKING:
    from .measurement_windows import CertifiedSessionCitationCohort

SOURCE_YEAR_CERTIFICATION_RULE_VERSION = "complete-source-year-certification-v1"
METRIC_WINDOW_CERTIFICATION_RULE_VERSION = "metric-window-certification-v1"
SourceEntityType = Literal["researcher", "institution", "country"]

_STRUCTURAL_YEAR_KINDS: frozenset[EvidenceKind] = frozenset(
    {
        "canonical-paper-identity",
        "publication-metric-date",
        "field-weight-conservation",
        "provenance-completeness",
    }
)


def _sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def source_record_inventory_digest(
    references: tuple[EvidenceReference, ...],
) -> str:
    return canonical_digest(
        tuple(
            sorted(
                (
                    item.provider,
                    item.source_record_id,
                    item.checksum,
                    item.source_snapshot_id,
                )
                for item in references
            )
        )
    )


@dataclass(frozen=True)
class SourcePartitionEvidence:
    partition_id: str
    provider: str
    expected_unique_records: int
    observed_records: int
    observed_unique_records: int
    duplicate_records: int
    truncated: bool
    page_checksums: tuple[str, ...]
    record_inventory_digest: str
    complete: bool

    def __post_init__(self) -> None:
        if not self.partition_id.strip() or not self.provider.strip():
            raise ValueError("source partition identifiers must be non-empty")
        counts = (
            self.expected_unique_records,
            self.observed_records,
            self.observed_unique_records,
            self.duplicate_records,
        )
        if any(value < 0 for value in counts):
            raise ValueError("source partition counts must be nonnegative")
        if len(set(self.page_checksums)) != len(self.page_checksums):
            raise ValueError("source partition page checksums must be unique")
        if not _sha256(self.record_inventory_digest):
            raise ValueError("source partition record inventory digest must be SHA-256")

    @property
    def reconciles(self) -> bool:
        return (
            self.complete
            and not self.truncated
            and bool(self.page_checksums)
            and all(_sha256(checksum) for checksum in self.page_checksums)
            and self.expected_unique_records == self.observed_unique_records
            and self.observed_records - self.observed_unique_records
            == self.duplicate_records
        )


@dataclass(frozen=True, kw_only=True)
class RecordPageSourcePartitionEvidence(SourcePartitionEvidence):
    """Opt-in exact record/page bridge; legacy partition hashes remain unchanged."""

    pages: tuple[SourceRecordPageReceipt, ...]

    def __post_init__(self) -> None:
        SourcePartitionEvidence.__post_init__(self)
        if not self.pages or any(
            not isinstance(item, SourceRecordPageReceipt) for item in self.pages
        ):
            raise CertificationError(
                "record/page partition requires typed captured pages"
            )
        for item in self.pages:
            item.__post_init__()
        pairs = tuple(pair for page in self.pages for pair in page.record_checksums)
        records = dict(pairs)
        if (
            any(
                page.provider != self.provider or page.partition_id != self.partition_id
                for page in self.pages
            )
            or tuple(page.page_checksum for page in self.pages) != self.page_checksums
            or len(pairs) != self.observed_records
            or len(records) != self.observed_unique_records
            or any(records[record_id] != checksum for record_id, checksum in pairs)
            or self.record_inventory_digest
            != source_record_inventory_digest(
                tuple(
                    EvidenceReference(
                        self.provider, record_id, checksum, self.partition_id
                    )
                    for record_id, checksum in sorted(records.items())
                )
            )
        ):
            raise CertificationError(
                "record/page partition differs from captured inventory"
            )

    @property
    def reconciles(self) -> bool:
        try:
            self.__post_init__()
        except ValueError:
            return False
        return super().reconciles


@dataclass(frozen=True)
class SourceAcquisitionPlanEvidence:
    """Dated reviewed plan defining the exact provider partitions for one year."""

    calendar_year: int
    cutoff: datetime
    dataset_version: str
    acquisition_scope: str
    partitions: tuple[tuple[str, str], ...]
    source_manifest_digest: str
    review_state: str
    reviewed_by: str
    reviewed_at: datetime

    def __post_init__(self) -> None:
        if self.calendar_year < 1900:
            raise ValueError("source acquisition plan year is invalid")
        if self.cutoff.tzinfo is None or self.cutoff.utcoffset() is None:
            raise ValueError("source acquisition plan cutoff must include timezone")
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("source acquisition review must include timezone")
        if (
            self.review_state != "reviewed-approved"
            or not self.reviewed_by.strip()
            or not self.dataset_version.strip()
            or not self.acquisition_scope.strip()
        ):
            raise ValueError("source acquisition plan requires reviewed identifiers")
        partition_ids = [partition_id for partition_id, _ in self.partitions]
        if (
            not partition_ids
            or len(set(partition_ids)) != len(partition_ids)
            or any(
                not partition_id.strip() or not provider.strip()
                for partition_id, provider in self.partitions
            )
        ):
            raise ValueError(
                "source acquisition plan partitions must be non-empty and unique"
            )
        if self.source_manifest_digest != self.content_digest:
            raise ValueError(
                "source acquisition plan manifest does not match reviewed content"
            )

    @property
    def content_digest(self) -> str:
        return canonical_digest(
            (
                self.calendar_year,
                self.cutoff,
                self.dataset_version,
                self.acquisition_scope,
                tuple(sorted(self.partitions)),
            )
        )


@dataclass(frozen=True)
class AutomaticSourceAcquisitionPlanEvidence:
    """Verify an existing fixed query recipe, not scientific completeness.

    The explicit query versions retain INSPIRE earliest-record and arXiv
    submission-year axes. No automatic publication-year equivalence is implied.
    Separate type preserves every legacy reviewed-plan serialization/digest.
    """

    calendar_year: int
    cutoff: datetime
    dataset_version: str
    acquisition_scope: str
    query_partitions: tuple[HistoricalPartition, ...]
    rule_version: str = "fixed-source-acquisition-plan-assessment-v1"

    def __post_init__(self) -> None:
        if self.rule_version != "fixed-source-acquisition-plan-assessment-v1":
            raise CertificationError("automatic source acquisition rule is unsupported")
        if self.cutoff.tzinfo is None or self.cutoff.utcoffset() is None:
            raise ValueError("automatic source plan cutoff must include timezone")
        if not self.dataset_version.strip() or self.calendar_year >= self.cutoff.year:
            raise ValueError("automatic source plan requires a version and closed year")
        expected = tuple(
            item
            for item in build_partitions(scope=self.acquisition_scope)
            if item.year == self.calendar_year
        )
        if not expected or self.query_partitions != expected:
            raise CertificationError(
                "automatic source plan differs from the exact fixed query recipe"
            )

    @property
    def partitions(self) -> tuple[tuple[str, str], ...]:
        return tuple((item.id, item.provider) for item in self.query_partitions)

    @property
    def content_digest(self) -> str:
        return canonical_digest(self)

    @property
    def source_manifest_digest(self) -> str:
        return self.content_digest


def automatic_source_acquisition_plan(
    *,
    calendar_year: int,
    cutoff: datetime,
    dataset_version: str,
    acquisition_scope: str,
) -> AutomaticSourceAcquisitionPlanEvidence:
    """Derive an existing bounded plan without acquisition or approval flags."""
    return AutomaticSourceAcquisitionPlanEvidence(
        calendar_year=calendar_year,
        cutoff=cutoff,
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        query_partitions=tuple(
            item
            for item in build_partitions(scope=acquisition_scope)
            if item.year == calendar_year
        ),
    )


@dataclass(frozen=True)
class SourceYearPaperProjection:
    """Canonical paper and exact provider occurrences for one closed year."""

    paper_id: str
    publication_date: date
    occurrence_references: tuple[EvidenceReference, ...]
    field_weights: tuple[tuple[str, float], ...]
    unmapped_field_mass: float
    field_weight_total: float
    field_weighting_policy_version: str
    entity_shares: tuple[tuple[SourceEntityType, str, float], ...]
    unresolved_entity_mass: tuple[tuple[SourceEntityType, float], ...]
    attribution_policy_version: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(item, EvidenceReference)
            for item in self.occurrence_references
        ):
            raise ValueError(
                "source-year paper occurrences require exact evidence references"
            )
        if any(
            not value.strip()
            for value in (
                self.paper_id,
                self.field_weighting_policy_version,
                self.attribution_policy_version,
            )
        ):
            raise ValueError("source-year paper projection identifiers are required")
        if not self.occurrence_references or len(
            set(self.occurrence_references)
        ) != len(self.occurrence_references):
            raise ValueError(
                "source-year paper occurrences must be non-empty and unique"
            )
        fields = dict(self.field_weights)
        if (
            len(fields) != len(self.field_weights)
            or any(
                not PHYSICS_FIELD_ONTOLOGY_V1.contains(field_id)
                or PHYSICS_FIELD_ONTOLOGY_V1.get(field_id).node_kind != "field"
                or not math.isfinite(weight)
                or weight <= 0
                or weight > 1
                for field_id, weight in fields.items()
            )
            or not math.isfinite(self.unmapped_field_mass)
            or not 0 <= self.unmapped_field_mass <= 1
            or not math.isfinite(self.field_weight_total)
        ):
            raise ValueError("source-year field ledger is invalid")
        conserved_field_mass = math.fsum(fields.values()) + self.unmapped_field_mass
        if not math.isclose(
            conserved_field_mass, 1.0, rel_tol=0.0, abs_tol=1e-9
        ) or not math.isclose(
            self.field_weight_total,
            conserved_field_mass,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "source-year field weights and unmapped mass must total one"
            )

        share_keys = [
            (entity_type, entity_id) for entity_type, entity_id, _ in self.entity_shares
        ]
        unresolved = dict(self.unresolved_entity_mass)
        allowed_entity_types = {"researcher", "institution", "country"}
        if (
            len(set(share_keys)) != len(share_keys)
            or len(unresolved) != len(self.unresolved_entity_mass)
            or any(
                entity_type not in allowed_entity_types
                or not entity_id.strip()
                or not math.isfinite(weight)
                or weight <= 0
                or weight > 1
                for entity_type, entity_id, weight in self.entity_shares
            )
            or any(
                entity_type not in allowed_entity_types
                or not math.isfinite(weight)
                or not 0 <= weight <= 1
                for entity_type, weight in unresolved.items()
            )
        ):
            raise ValueError("source-year entity attribution ledger is invalid")
        represented_types = {
            entity_type for entity_type, _, _ in self.entity_shares
        } | set(unresolved)
        if not represented_types or any(
            not math.isclose(
                math.fsum(
                    weight
                    for share_type, _, weight in self.entity_shares
                    if share_type == entity_type
                )
                + unresolved.get(entity_type, 0.0),
                1.0,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            for entity_type in represented_types
        ):
            raise ValueError(
                "source-year entity shares plus unresolved mass must total one"
            )

    def decision_value_digest(self, evidence_kind: EvidenceKind) -> str:
        values: dict[EvidenceKind, object] = {
            "canonical-paper-identity": {"paper_id": self.paper_id},
            "publication-metric-date": {
                "paper_id": self.paper_id,
                "publication_date": self.publication_date,
            },
            "field-weight-conservation": {
                "paper_id": self.paper_id,
                "field_weights": tuple(sorted(self.field_weights)),
                "unmapped_field_mass": self.unmapped_field_mass,
                "field_weight_total": self.field_weight_total,
                "field_weighting_policy_version": (self.field_weighting_policy_version),
            },
            "provenance-completeness": {
                "paper_id": self.paper_id,
                "occurrence_references": self.occurrence_references,
                "entity_shares": tuple(sorted(self.entity_shares)),
                "unresolved_entity_mass": tuple(sorted(self.unresolved_entity_mass)),
                "attribution_policy_version": self.attribution_policy_version,
            },
        }
        try:
            return canonical_digest(values[evidence_kind])
        except KeyError as error:
            raise ValueError(
                f"{evidence_kind} is not a source-year structural dimension"
            ) from error


@dataclass(frozen=True)
class SourceYearEvidence:
    calendar_year: int
    entity_type: str
    cutoff: datetime
    dataset_version: str
    acquisition_scope: str
    acquisition_plan: (
        SourceAcquisitionPlanEvidence
        | AutomaticSourceAcquisitionPlanEvidence
        | BoundedLaunchSourcePlan
    )
    required_partition_ids: tuple[str, ...]
    required_coverage_kinds: tuple[EvidenceKind, ...]
    paper_projections: tuple[SourceYearPaperProjection, ...]
    partitions: tuple[SourcePartitionEvidence, ...]
    structural_decisions: tuple[EvidenceCertificationDecision, ...]
    coverage_decisions: tuple[EvidenceCertificationDecision, ...]

    def __post_init__(self) -> None:
        if not isinstance(
            self.acquisition_plan,
            (
                SourceAcquisitionPlanEvidence,
                AutomaticSourceAcquisitionPlanEvidence,
                BoundedLaunchSourcePlan,
            ),
        ):
            raise ValueError("source-year evidence requires an exact acquisition plan")
        if isinstance(
            self.acquisition_plan,
            (AutomaticSourceAcquisitionPlanEvidence, BoundedLaunchSourcePlan),
        ):
            self.acquisition_plan.__post_init__()
        if any(
            not isinstance(item, SourceYearPaperProjection)
            for item in self.paper_projections
        ):
            raise ValueError("source-year evidence requires exact paper projections")
        if any(
            not isinstance(item, SourcePartitionEvidence) for item in self.partitions
        ):
            raise ValueError("source-year evidence requires exact source partitions")
        if any(
            not isinstance(item, EvidenceCertificationDecision)
            for item in (*self.structural_decisions, *self.coverage_decisions)
        ):
            raise ValueError(
                "source-year evidence requires exact certification decisions"
            )
        if not self.dataset_version.strip() or not self.acquisition_scope.strip():
            raise ValueError("source-year evidence versions must be non-empty")
        if (
            self.acquisition_plan.calendar_year != self.calendar_year
            or self.acquisition_plan.cutoff != self.cutoff
            or self.acquisition_plan.dataset_version != self.dataset_version
            or self.acquisition_plan.acquisition_scope != self.acquisition_scope
        ):
            raise ValueError("source-year acquisition plan lineage does not match")
        if self.entity_type not in {"researcher", "institution", "country"}:
            raise ValueError("source-year evidence entity type is unsupported")
        if len(set(self.required_partition_ids)) != len(self.required_partition_ids):
            raise ValueError("required source-year partitions must be unique")
        if not self.required_coverage_kinds or len(
            set(self.required_coverage_kinds)
        ) != len(self.required_coverage_kinds):
            raise ValueError(
                "required source-year coverage kinds must be non-empty/unique"
            )
        paper_ids = [item.paper_id for item in self.paper_projections]
        if not paper_ids or len(set(paper_ids)) != len(paper_ids):
            raise ValueError(
                "source-year canonical paper population must be non-empty/unique"
            )
        partition_ids = [item.partition_id for item in self.partitions]
        if len(set(partition_ids)) != len(partition_ids):
            raise ValueError("source-year partition evidence must be unique")
        structural_ids = [item.decision_id for item in self.structural_decisions]
        if not structural_ids or len(set(structural_ids)) != len(structural_ids):
            raise ValueError(
                "source-year structural decisions must be non-empty/unique"
            )
        if any(
            item.dataset_version != self.dataset_version
            or item.acquisition_scope != self.acquisition_scope
            for item in self.structural_decisions
        ):
            raise ValueError("source-year structural decision lineage does not match")
        coverage_ids = [item.decision_id for item in self.coverage_decisions]
        if not coverage_ids or len(set(coverage_ids)) != len(coverage_ids):
            raise ValueError("source-year coverage decisions must be non-empty/unique")
        if any(
            item.subject_type != COVERAGE_SUBJECT_TYPE
            or item.dataset_version != self.dataset_version
            or item.acquisition_scope != self.acquisition_scope
            for item in self.coverage_decisions
        ):
            raise ValueError(
                "source-year coverage decisions must match its purpose and lineage"
            )


@dataclass(frozen=True)
class CertifiedSourceYear:
    evidence: SourceYearEvidence
    coverage: tuple[CoverageCertification, ...]
    certification: SourceYearCertification

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, SourceYearEvidence):
            raise CertificationError(
                "source-year proof requires exact source-year evidence"
            )
        if not isinstance(self.certification, SourceYearCertification):
            raise CertificationError(
                "source-year proof requires an exact certification result"
            )
        if any(not isinstance(item, CoverageCertification) for item in self.coverage):
            raise CertificationError(
                "source-year proof requires exact coverage certifications"
            )
        if _evaluate_source_year(self.evidence, self.coverage) != self.certification:
            raise CertificationError(
                "source-year certification does not reconstruct from its evidence"
            )

    @property
    def calendar_year(self) -> int:
        return self.certification.calendar_year

    @property
    def cutoff(self) -> datetime:
        return self.certification.cutoff

    @property
    def dataset_version(self) -> str:
        return self.certification.dataset_version

    @property
    def acquisition_scope(self) -> str:
        return self.certification.acquisition_scope

    @property
    def state(self) -> CertificationState:
        return self.certification.state

    @property
    def rule_version(self) -> str:
        return self.certification.rule_version

    @property
    def required_coverage_kinds(self) -> tuple[EvidenceKind, ...]:
        return self.certification.required_coverage_kinds

    @property
    def verified_partition_ids(self) -> tuple[str, ...]:
        return self.certification.verified_partition_ids

    @property
    def certification_id(self) -> str:
        return self.certification.certification_id


def _evaluate_source_year(
    evidence: SourceYearEvidence,
    coverage: tuple[CoverageCertification, ...],
) -> SourceYearCertification:
    from .launch_metric_coverage import SourceAttributionMassPopulation

    if isinstance(
        evidence.acquisition_plan,
        (AutomaticSourceAcquisitionPlanEvidence, BoundedLaunchSourcePlan),
    ):
        evidence.acquisition_plan.__post_init__()
    reasons: list[str] = []
    state: CertificationState = "certified"
    if evidence.calendar_year >= evidence.cutoff.year:
        state = "withheld"
        reasons.append("calendar year is not closed at the certification cutoff")
    partitions = {item.partition_id: item for item in evidence.partitions}
    required = set(evidence.required_partition_ids)
    planned = dict(evidence.acquisition_plan.partitions)
    if not required:
        if state == "certified":
            state = "insufficient_evidence"
        reasons.append("source year declares no required provider partitions")
    if set(partitions) != required:
        if state == "certified":
            state = "insufficient_evidence"
        reasons.append("source-year provider partition set is incomplete or unexpected")
    if required != set(planned) or any(
        partition_id in partitions
        and partitions[partition_id].provider != planned[partition_id]
        for partition_id in required & set(planned)
    ):
        state = "conflicted"
        reasons.append(
            "source-year required partitions differ from the reviewed acquisition plan"
        )
    if any(not item.reconciles for item in evidence.partitions):
        if state == "certified":
            state = "conflicted"
        reasons.append(
            "one or more provider partitions fail completeness reconciliation"
        )
    canonical_count = len(evidence.paper_projections)
    provider_counts = [item.observed_unique_records for item in evidence.partitions]
    if provider_counts and not (
        max(provider_counts) <= canonical_count <= sum(provider_counts)
    ):
        state = "conflicted"
        reasons.append(
            "canonical paper population is inconsistent with provider record counts"
        )

    structural_by_kind = {
        kind: tuple(
            item for item in evidence.structural_decisions if item.evidence_kind == kind
        )
        for kind in _STRUCTURAL_YEAR_KINDS
    }
    projections_by_id = {item.paper_id: item for item in evidence.paper_projections}
    canonical_paper_ids = set(projections_by_id)
    if any(
        item.publication_date.year != evidence.calendar_year
        or item.field_weighting_policy_version != FIELD_WEIGHTING_POLICY_VERSION
        or item.attribution_policy_version != FRACTIONAL_ATTRIBUTION_V1.version
        or not math.isclose(item.field_weight_total, 1.0, rel_tol=0.0, abs_tol=1e-9)
        or evidence.entity_type
        not in {entity_type for entity_type, _, _ in item.entity_shares}
        | {entity_type for entity_type, _ in item.unresolved_entity_mass}
        for item in evidence.paper_projections
    ):
        state = "conflicted"
        reasons.append(
            "canonical paper projections do not match the year or field policy"
        )

    occurrences_by_partition: dict[str, list[EvidenceReference]] = {
        partition_id: [] for partition_id in required
    }
    captured_record_checksums = {
        partition_id: dict(
            pair for page in partition.pages for pair in page.record_checksums
        )
        for partition_id, partition in partitions.items()
        if isinstance(partition, RecordPageSourcePartitionEvidence)
    }
    invalid_occurrence = False
    occurrence_keys: set[tuple[str, str]] = set()
    for projection in evidence.paper_projections:
        for reference in projection.occurrence_references:
            partition = partitions.get(reference.source_snapshot_id or "")
            key = (reference.provider, reference.source_record_id)
            if (
                partition is None
                or partition.provider != reference.provider
                or (
                    reference.checksum
                    != captured_record_checksums[partition.partition_id].get(
                        reference.source_record_id
                    )
                    if isinstance(partition, RecordPageSourcePartitionEvidence)
                    else reference.checksum not in partition.page_checksums
                )
                or key in occurrence_keys
            ):
                invalid_occurrence = True
                continue
            occurrence_keys.add(key)
            occurrences_by_partition[partition.partition_id].append(reference)
    for partition_id, partition in partitions.items():
        references = occurrences_by_partition.get(partition_id, [])
        inventory = source_record_inventory_digest(tuple(references))
        if (
            len(references) != partition.observed_unique_records
            or inventory != partition.record_inventory_digest
        ):
            invalid_occurrence = True
    if invalid_occurrence:
        state = "conflicted"
        reasons.append(
            "canonical paper projections do not bind the exact provider inventory"
        )
    missing_structural = {
        kind for kind, decisions in structural_by_kind.items() if not decisions
    }
    if missing_structural:
        if state == "certified":
            state = "insufficient_evidence"
        reasons.append("required structural evidence certifications are missing")
    if any(
        item.state != "certified" or not evidence_decision_is_current(item)
        for decisions in structural_by_kind.values()
        for item in decisions
    ):
        if state == "certified":
            state = "insufficient_evidence"
        reasons.append("required structural evidence is not fully certified")
    if any(
        len(decisions) != len(canonical_paper_ids)
        or {item.subject_id for item in decisions} != canonical_paper_ids
        or any(item.subject_type != "paper" for item in decisions)
        or any(item.certified_value_digest is None for item in decisions)
        for decisions in structural_by_kind.values()
    ):
        state = "conflicted"
        reasons.append(
            "structural certifications do not bind the exact canonical paper population"
        )
    if any(
        item.certified_value_digest
        != projections_by_id[item.subject_id].decision_value_digest(item.evidence_kind)
        for decisions in structural_by_kind.values()
        for item in decisions
        if item.subject_id in projections_by_id
    ):
        state = "conflicted"
        reasons.append(
            "structural decision values do not reconstruct from paper projections"
        )
    from .automation import (
        AutomaticPaperIdentityDecision,
        verify_automatic_source_binding,
    )

    automatic_dates = tuple(
        item
        for item in evidence.structural_decisions
        if isinstance(item, AutomaticPaperIdentityDecision)
        and item.evidence_kind == "publication-metric-date"
    )
    if isinstance(evidence.acquisition_plan, BoundedLaunchSourcePlan) and (
        len(automatic_dates) != len(canonical_paper_ids)
        or any(
            item.source_facts.declared_date_basis
            != evidence.acquisition_plan.declared_date_basis
            for item in automatic_dates
        )
        or any(
            not isinstance(item, RecordPageSourcePartitionEvidence)
            for item in evidence.partitions
        )
    ):
        state = "conflicted"
        reasons.append(
            "bounded launch year lacks exact source-bound dates or record/page receipts"
        )
    if automatic_dates:
        # The legacy type has no axis field. Never silently mix an explicit
        # opt-in basis with an unlabelled legacy date or another source basis.
        if (
            len(automatic_dates) != len(canonical_paper_ids)
            or len({item.source_facts.declared_date_basis for item in automatic_dates})
            != 1
        ):
            state = "conflicted"
            reasons.append(
                "automatic source-year dates lack one complete explicit basis"
            )
        for item in automatic_dates:
            try:
                verify_automatic_source_binding(
                    item, projections_by_id.get(item.subject_id)
                )
            except ValueError:
                state = "conflicted"
                reasons.append(
                    "automatic date does not bind the exact source-year occurrence"
                )
    if not coverage:
        if state == "certified":
            state = "insufficient_evidence"
        reasons.append("source year has no required evidence coverage certifications")
    coverage_kinds = [item.evidence_kind for item in coverage]
    if len(set(coverage_kinds)) != len(coverage_kinds):
        state = "conflicted"
        reasons.append("source-year evidence coverage kinds are duplicated")
    if set(coverage_kinds) != set(evidence.required_coverage_kinds):
        if state == "certified":
            state = "insufficient_evidence"
        reasons.append("source-year required evidence coverage set is incomplete")
    try:
        stale_coverage = any(
            not math.isclose(
                item.minimum,
                coverage_minimum(item.evidence_kind),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            for item in coverage
        )
    except ValueError:
        stale_coverage = True
    if stale_coverage:
        state = "conflicted"
        reasons.append("source-year coverage does not use the v1 certification policy")
    if any(item.state != "certified" for item in coverage):
        if state == "certified":
            state = "insufficient_evidence"
        reasons.append("one or more required evidence coverage gates failed")
    coverage_decisions_by_kind = {
        kind: tuple(
            item for item in evidence.coverage_decisions if item.evidence_kind == kind
        )
        for kind in evidence.required_coverage_kinds
    }
    source_population_digest = canonical_digest(
        tuple(sorted(evidence.paper_projections, key=lambda item: item.paper_id))
    )
    for certificate in coverage:
        decisions = coverage_decisions_by_kind.get(certificate.evidence_kind, ())
        if set(certificate.decision_ids) != {item.decision_id for item in decisions}:
            state = "conflicted"
            reasons.append(
                "source-year coverage omits or references an unrelated decision"
            )
            continue
        try:
            validate_coverage_certification(certificate, decisions)
        except ValueError:
            state = "conflicted"
            reasons.append("source-year coverage proof cannot be reconstructed")
            continue
        population = certificate.population
        decision_by_subject = {item.subject_id: item for item in decisions}
        expected_formula_inputs = tuple(
            (paper_id, 1.0)
            for paper_id in sorted(canonical_paper_ids)
            if decision_by_subject.get(paper_id) is not None
            and decision_by_subject[paper_id].state == "certified"
        )
        if isinstance(population, SourceFieldMassPopulation):
            if tuple(
                sorted(population.source_projections, key=lambda item: item.paper_id)
            ) != tuple(
                sorted(evidence.paper_projections, key=lambda item: item.paper_id)
            ) or any(
                item.context.dataset_version != evidence.dataset_version
                or item.context.acquisition_scope != evidence.acquisition_scope
                for item in population.source_field_evidence
            ):
                state = "conflicted"
                reasons.append(
                    "source-year field mass does not bind its full canonical universe"
                )
        elif isinstance(population, SourceAttributionMassPopulation):
            if (
                tuple(
                    sorted(
                        population.source_projections, key=lambda item: item.paper_id
                    )
                )
                != tuple(
                    sorted(evidence.paper_projections, key=lambda item: item.paper_id)
                )
                or population.entity_type != evidence.entity_type
                or any(
                    item.dataset_version != evidence.dataset_version
                    or item.acquisition_scope != evidence.acquisition_scope
                    for item in population.source_proofs
                )
            ):
                state = "conflicted"
                reasons.append(
                    "source-year attribution mass does not bind "
                    "its full canonical universe"
                )
        elif (
            population.source_manifest_digest != source_population_digest
            or population.formula_inputs != expected_formula_inputs
            or set(unit_id for unit_id, _ in population.units) != canonical_paper_ids
            or not math.isclose(
                math.fsum(mass for _, mass in population.units),
                float(canonical_count),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            state = "conflicted"
            reasons.append(
                "source-year coverage population is not the conserved paper universe"
            )
        population_masses = dict(population.units)
        certificate_masses = {
            item.decision_id: item.denominator_mass
            for item in certificate.decision_masses
        }
        if (
            len(decision_by_subject) != len(decisions)
            or set(decision_by_subject) != set(population_masses)
            or any(
                not math.isclose(
                    certificate_masses.get(decision.decision_id, -1.0),
                    population_masses[subject_id],
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
                for subject_id, decision in decision_by_subject.items()
            )
        ):
            state = "conflicted"
            reasons.append(
                "source-year coverage does not bind its exact declared population"
            )

    verified = tuple(
        sorted(
            item.partition_id
            for item in evidence.partitions
            if item.reconciles and item.partition_id in required
        )
    )
    return SourceYearCertification(
        calendar_year=evidence.calendar_year,
        entity_type=evidence.entity_type,
        cutoff=evidence.cutoff,
        dataset_version=evidence.dataset_version,
        acquisition_scope=evidence.acquisition_scope,
        state=state,
        required_partition_ids=tuple(sorted(required)),
        verified_partition_ids=verified,
        required_coverage_kinds=tuple(sorted(evidence.required_coverage_kinds)),
        canonical_paper_count=canonical_count,
        canonical_paper_population_digest=source_population_digest,
        coverage_population_digests=tuple(
            sorted(
                (
                    item.evidence_kind,
                    item.population.population_digest,
                )
                for item in coverage
            )
        ),
        coverage=coverage,
        decision_ids=tuple(
            sorted(item.decision_id for item in evidence.structural_decisions)
        ),
        input_digest=canonical_digest((evidence, coverage)),
        rule_version=SOURCE_YEAR_CERTIFICATION_RULE_VERSION,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def certify_source_year(
    evidence: SourceYearEvidence,
    coverage: tuple[CoverageCertification, ...],
) -> CertifiedSourceYear:
    return CertifiedSourceYear(
        evidence=evidence,
        coverage=coverage,
        certification=_evaluate_source_year(evidence, coverage),
    )


@dataclass(frozen=True)
class CertifiedMetricWindow:
    source_years: tuple[CertifiedSourceYear, ...]
    citation_cohorts: tuple[
        CertifiedCitationCohort[object] | CertifiedSessionCitationCohort, ...
    ]
    certification: MetricWindowCertification

    def __post_init__(self) -> None:
        from .measurement_windows import CertifiedSessionCitationCohort

        if not isinstance(self.certification, MetricWindowCertification):
            raise CertificationError(
                "metric-window proof requires an exact certification result"
            )
        if any(not isinstance(item, CertifiedSourceYear) for item in self.source_years):
            raise CertificationError(
                "metric-window proof requires reconstructable source years"
            )
        if any(
            not isinstance(
                item, (CertifiedCitationCohort, CertifiedSessionCitationCohort)
            )
            for item in self.citation_cohorts
        ):
            raise CertificationError(
                "metric-window proof requires reconstructable citation cohorts"
            )
        from .automation import AutomaticPaperIdentityDecision

        date_decisions = tuple(
            decision
            for year in self.source_years
            for decision in year.evidence.structural_decisions
            if decision.evidence_kind == "publication-metric-date"
        )
        automatic_dates = tuple(
            item
            for item in date_decisions
            if isinstance(item, AutomaticPaperIdentityDecision)
        )
        if automatic_dates and (
            len(automatic_dates) != len(date_decisions)
            or len({item.source_facts.declared_date_basis for item in automatic_dates})
            != 1
        ):
            raise CertificationError(
                "metric window mixes declared and unlabelled metric date bases"
            )
        expected = _evaluate_metric_window(
            metric_id=self.certification.metric_id,
            entity_type=self.certification.entity_type,
            terminal_year=self.certification.terminal_year,
            source_years=tuple(item.certification for item in self.source_years),
            threshold_version=self.certification.threshold_version,
            citation_cohorts=self.citation_cohorts,
        )
        if expected != self.certification:
            raise CertificationError(
                "metric-window certification does not reconstruct from its proofs"
            )

    @property
    def state(self) -> CertificationState:
        return self.certification.state

    @property
    def cutoff(self) -> datetime:
        return self.certification.cutoff

    @property
    def citation_cohort_certification_ids(self) -> tuple[str, ...]:
        return self.certification.citation_cohort_certification_ids

    @property
    def reasons(self) -> tuple[str, ...]:
        return self.certification.reasons


def _evaluate_metric_window(
    *,
    metric_id: str,
    entity_type: str,
    terminal_year: int,
    source_years: tuple[SourceYearCertification, ...],
    threshold_version: str,
    citation_cohorts: tuple[
        CertifiedCitationCohort[object] | CertifiedSessionCitationCohort, ...
    ] = (),
) -> MetricWindowCertification:
    from .measurement_windows import (
        CertifiedSessionCitationCohort,
        require_session_cohort,
        session_comparison_key,
    )

    required_years = required_window_years(metric_id, terminal_year)
    required_coverage = required_coverage_evidence(metric_id, entity_type)
    years = {item.calendar_year: item for item in source_years}
    if len(years) != len(source_years):
        raise ValueError("metric-window source years must be unique")
    reasons: list[str] = []
    state: CertificationState = "certified"
    if set(years) != set(required_years):
        state = "insufficient_evidence"
        reasons.append("metric window does not contain its exact required source years")
    selected = tuple(years[year] for year in required_years if year in years)
    if any(item.state != "certified" for item in selected):
        state = "insufficient_evidence"
        reasons.append("metric window contains a non-certified source year")
    if any(item.entity_type != entity_type for item in selected):
        state = "conflicted"
        reasons.append("metric-window source years target another entity type")
    if any(
        not set(required_coverage).issubset(item.required_coverage_kinds)
        for item in selected
    ):
        if state == "certified":
            state = "insufficient_evidence"
        reasons.append(
            "metric-window source years omit required evidence coverage dimensions"
        )
    if any(
        item.rule_version != SOURCE_YEAR_CERTIFICATION_RULE_VERSION for item in selected
    ):
        state = "conflicted"
        reasons.append("metric window contains a stale source-year certification")
    coverage_policies = {item.required_coverage_kinds for item in selected}
    if len(coverage_policies) > 1:
        state = "conflicted"
        reasons.append("metric-window source years use incompatible coverage purposes")
    versions = {
        (item.dataset_version, item.acquisition_scope, item.rule_version)
        for item in selected
    }
    if len(versions) > 1:
        state = "conflicted"
        reasons.append("metric-window source-year versions are incompatible")
    cutoffs = {item.cutoff for item in selected}
    if len(cutoffs) > 1:
        state = "conflicted"
        reasons.append("metric-window source years do not share one evidence cutoff")
    dataset_version = selected[0].dataset_version if selected else "unavailable"
    acquisition_scope = selected[0].acquisition_scope if selected else "unavailable"
    cutoff = selected[0].cutoff if selected else datetime.min.replace(tzinfo=UTC)
    cohort_ids = tuple(item.certification_id for item in citation_cohorts)
    if len(set(cohort_ids)) != len(cohort_ids):
        state = "conflicted"
        reasons.append("Impact window contains duplicate citation cohort proofs")
    if metric_id == "research_impact":
        if not citation_cohorts:
            if state == "certified":
                state = "insufficient_evidence"
            reasons.append(
                "Impact window has no certified common-cutoff citation cohorts"
            )
        session_cohorts = tuple(
            item
            for item in citation_cohorts
            if isinstance(item, CertifiedSessionCitationCohort)
        )
        legacy_cohorts = tuple(
            item
            for item in citation_cohorts
            if isinstance(item, CertifiedCitationCohort)
        )
        if session_cohorts and legacy_cohorts:
            state = "conflicted"
            reasons.append(
                "Impact cannot mix atomic-cutoff and measurement-window cohorts"
            )
        elif session_cohorts:
            try:
                for item in session_cohorts:
                    require_session_cohort(
                        item,
                        dataset_version=dataset_version,
                        acquisition_scope=acquisition_scope,
                        evaluation_horizon=cutoff.date(),
                    )
                    if item.ended_at > cutoff:
                        raise CertificationError(
                            "measurement session extends beyond the evaluation horizon"
                        )
                    populations = dict(item.source_year_population_digests)
                    if any(
                        populations.get(year.calendar_year)
                        != year.canonical_paper_population_digest
                        for year in selected
                    ):
                        raise CertificationError(
                            "measurement session uses a different canonical "
                            "source population"
                        )
                session_comparison_key(session_cohorts)
            except ValueError:
                state = "conflicted"
                reasons.append(
                    "Impact measurement-window cohorts fail exact "
                    "session/population validation"
                )
        else:
            if any(
                item.rule_version != CITATION_CERTIFICATION_RULE_VERSION
                for item in legacy_cohorts
            ):
                state = "conflicted"
                reasons.append("Impact window contains a stale citation cohort proof")
            if any(
                not isinstance(item.certification_proof, CitationCohortCertification)
                or item.certification_proof.minimum_paper_count
                != IMPACT_REFERENCE_COHORT_MINIMUM_V1
                or item.certification_proof.paper_count
                < IMPACT_REFERENCE_COHORT_MINIMUM_V1
                for item in legacy_cohorts
            ):
                if state == "certified":
                    state = "insufficient_evidence"
                reasons.append(
                    "Impact citation cohort does not meet the v1 size policy"
                )
        if any(
            item.dataset_version != dataset_version
            or item.acquisition_scope != acquisition_scope
            for item in citation_cohorts
        ):
            state = "conflicted"
            reasons.append("Impact citation cohort lineage does not match source years")
        if any(item.cutoff != cutoff for item in legacy_cohorts):
            state = "conflicted"
            reasons.append(
                "Impact citation cohorts do not share the source-year cutoff"
            )
    elif citation_cohorts:
        state = "conflicted"
        reasons.append("non-Impact metric windows cannot carry citation cohorts")
    return MetricWindowCertification(
        metric_id=metric_id,
        entity_type=entity_type,
        terminal_year=terminal_year,
        required_years=required_years,
        source_year_certification_ids=tuple(item.certification_id for item in selected),
        citation_cohort_certification_ids=tuple(sorted(cohort_ids)),
        cutoff=cutoff,
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        threshold_version=threshold_version,
        state=state,
        input_digest=canonical_digest((source_years, citation_cohorts)),
        rule_version=METRIC_WINDOW_CERTIFICATION_RULE_VERSION,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def certify_metric_window(
    *,
    metric_id: str,
    entity_type: str,
    terminal_year: int,
    source_years: tuple[CertifiedSourceYear, ...],
    threshold_version: str,
    citation_cohorts: tuple[
        CertifiedCitationCohort[object] | CertifiedSessionCitationCohort, ...
    ] = (),
) -> CertifiedMetricWindow:
    from .measurement_windows import CertifiedSessionCitationCohort

    if any(not isinstance(item, CertifiedSourceYear) for item in source_years):
        raise CertificationError(
            "metric windows require reconstructable source-year proofs"
        )
    if any(
        not isinstance(item, (CertifiedCitationCohort, CertifiedSessionCitationCohort))
        for item in citation_cohorts
    ):
        raise CertificationError(
            "Impact windows require reconstructable citation-cohort proofs"
        )
    certification = _evaluate_metric_window(
        metric_id=metric_id,
        entity_type=entity_type,
        terminal_year=terminal_year,
        source_years=tuple(item.certification for item in source_years),
        threshold_version=threshold_version,
        citation_cohorts=citation_cohorts,
    )
    return CertifiedMetricWindow(
        source_years=source_years,
        citation_cohorts=citation_cohorts,
        certification=certification,
    )
