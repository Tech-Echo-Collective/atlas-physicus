from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import Literal

CERTIFICATION_POLICY_VERSION = "scientific-evidence-certification-v1"

CertificationState = Literal[
    "certified",
    "needs_review",
    "withheld",
    "conflicted",
    "insufficient_evidence",
]
EvidenceKind = Literal[
    "canonical-paper-identity",
    "publication-metric-date",
    "researcher-identity",
    "paper-time-affiliation",
    "canonical-institution",
    "field-classification",
    "field-weight-conservation",
    "citation-observation",
    "citation-cutoff-compatibility",
    "collaboration-relationship",
    "provenance-completeness",
]
CERTIFICATION_COVERAGE_MINIMUMS_V1: dict[EvidenceKind, float] = {
    "paper-time-affiliation": 0.90,
    "canonical-institution": 0.95,
    "citation-observation": 0.90,
    "field-classification": 0.90,
    "collaboration-relationship": 0.90,
}

_ALLOWED_STATES = frozenset(
    {
        "certified",
        "needs_review",
        "withheld",
        "conflicted",
        "insufficient_evidence",
    }
)


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


class CertificationError(ValueError):
    """Raised when evidence is presented as certified without a valid proof."""


def _canonical_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _canonical_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (Decimal, Fraction)):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        canonical_items = [_canonical_value(item) for item in value]
        return sorted(
            canonical_items,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CertificationError("certification inputs must be finite")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise CertificationError(
        f"unsupported certification digest value: {type(value).__name__}"
    )


def canonical_digest(value: object) -> str:
    """Return a stable digest for immutable certification inputs."""

    payload = json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, order=True)
class EvidenceReference:
    provider: str
    source_record_id: str
    checksum: str
    source_snapshot_id: str | None = None
    storage_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.source_record_id.strip():
            raise ValueError("evidence provider and source record id must be non-empty")
        if not _is_sha256(self.checksum):
            raise ValueError("evidence checksum must be a SHA-256 hex digest")


@dataclass(frozen=True)
class EvidenceCertificationDecision:
    subject_type: str
    subject_id: str
    evidence_kind: EvidenceKind
    state: CertificationState
    rule_version: str
    dataset_version: str
    acquisition_scope: str
    evidence: tuple[EvidenceReference, ...]
    certified_value_digest: str | None = None
    reasons: tuple[str, ...] = ()
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    supersedes_decision_id: str | None = None

    def __post_init__(self) -> None:
        if any(not isinstance(item, EvidenceReference) for item in self.evidence):
            raise ValueError(
                "certification decisions require exact evidence references"
            )
        identifiers = (
            self.subject_type,
            self.subject_id,
            self.rule_version,
            self.dataset_version,
            self.acquisition_scope,
        )
        if any(not value.strip() for value in identifiers):
            raise ValueError("certification identifiers must be non-empty")
        if self.state not in _ALLOWED_STATES:
            raise ValueError(f"unsupported certification state: {self.state}")
        if self.state == "certified" and not self.evidence:
            raise ValueError(
                "certified evidence must retain at least one source reference"
            )
        if self.state != "certified" and not self.reasons:
            raise ValueError("non-certified evidence must include an explicit reason")
        if (self.reviewed_by is None) != (self.reviewed_at is None):
            raise ValueError("reviewer identity and review timestamp must be paired")
        if self.reviewed_at is not None and (
            self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None
        ):
            raise ValueError("review timestamp must include a timezone")
        if len(set(self.evidence)) != len(self.evidence):
            raise ValueError("certification evidence references must be unique")
        if self.certified_value_digest is not None and not _is_sha256(
            self.certified_value_digest
        ):
            raise ValueError("certified evidence value digest must be SHA-256")

    @property
    def decision_id(self) -> str:
        return f"cert-{canonical_digest(self)}"


@dataclass(frozen=True)
class CoverageDecisionMass:
    """One indivisible evidence decision's contribution to a coverage denominator."""

    decision_id: str
    certified_mass: float
    denominator_mass: float

    def __post_init__(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("coverage decision id must be non-empty")
        if not math.isfinite(self.certified_mass) or not math.isfinite(
            self.denominator_mass
        ):
            raise ValueError("coverage decision mass must be finite")
        if self.denominator_mass <= 0:
            raise ValueError("coverage denominator mass must be positive")
        if not (
            math.isclose(self.certified_mass, 0.0, rel_tol=0.0, abs_tol=1e-12)
            or math.isclose(
                self.certified_mass,
                self.denominator_mass,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            raise ValueError(
                "one evidence decision must contribute either zero or its full mass"
            )


@dataclass(frozen=True)
class CoveragePopulationEvidence:
    """Checksum-bound full review universe, including unresolved/excluded mass."""

    evidence_kind: EvidenceKind
    units: tuple[tuple[str, float], ...]
    formula_inputs: tuple[tuple[str, float], ...]
    source_manifest_digest: str

    def __post_init__(self) -> None:
        unit_ids = [unit_id for unit_id, _ in self.units]
        if not unit_ids or len(set(unit_ids)) != len(unit_ids):
            raise ValueError("coverage population units must be non-empty and unique")
        if any(
            not unit_id.strip() or not math.isfinite(mass) or mass <= 0
            for unit_id, mass in self.units
        ):
            raise ValueError("coverage population units require positive finite mass")
        formula_ids = [paper_id for paper_id, _ in self.formula_inputs]
        if len(set(formula_ids)) != len(formula_ids) or any(
            not paper_id.strip() or not math.isfinite(mass) or mass <= 0
            for paper_id, mass in self.formula_inputs
        ):
            raise ValueError(
                "coverage formula inputs must have unique ids and positive mass"
            )
        if not _is_sha256(self.source_manifest_digest):
            raise ValueError("coverage population source manifest must be SHA-256")

    @property
    def population_digest(self) -> str:
        return canonical_digest(
            (
                self.evidence_kind,
                tuple(sorted(self.units)),
                tuple(sorted(self.formula_inputs)),
                self.source_manifest_digest,
            )
        )


@dataclass(frozen=True)
class CoverageCertification:
    evidence_kind: EvidenceKind
    numerator: float
    denominator: float
    minimum: float
    state: CertificationState
    population: CoveragePopulationEvidence
    decision_ids: tuple[str, ...]
    decision_masses: tuple[CoverageDecisionMass, ...]
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.population, CoveragePopulationEvidence):
            raise CertificationError("coverage requires exact population evidence")
        if not isinstance(self.decision_masses, tuple) or any(
            not isinstance(item, CoverageDecisionMass) for item in self.decision_masses
        ):
            raise CertificationError("coverage requires exact decision masses")
        values = (self.numerator, self.denominator, self.minimum)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("coverage inputs must be finite")
        if self.numerator < 0 or self.denominator < 0:
            raise ValueError("coverage mass must be nonnegative")
        if self.numerator > self.denominator:
            raise ValueError("coverage numerator cannot exceed its denominator")
        if not 0 <= self.minimum <= 1:
            raise ValueError("coverage minimum must be within [0,1]")
        expected_minimum = CERTIFICATION_COVERAGE_MINIMUMS_V1.get(self.evidence_kind)
        if expected_minimum is None or not math.isclose(
            self.minimum,
            expected_minimum,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "coverage certification minimum must match the v1 evidence policy"
            )
        if self.state == "certified" and (
            self.ratio is None or self.ratio < self.minimum
        ):
            raise ValueError("certified coverage must satisfy its declared minimum")
        if self.state != "certified" and not self.reasons:
            raise ValueError("non-certified coverage must retain a reason")
        if self.population.evidence_kind != self.evidence_kind:
            raise ValueError("coverage population evidence kind does not match")
        if not self.decision_ids or len(set(self.decision_ids)) != len(
            self.decision_ids
        ):
            raise ValueError("coverage decision ids must be non-empty and unique")
        mass_ids = tuple(item.decision_id for item in self.decision_masses)
        if (
            not mass_ids
            or len(set(mass_ids)) != len(mass_ids)
            or tuple(sorted(mass_ids)) != self.decision_ids
        ):
            raise ValueError(
                "coverage decision masses must bind the exact sorted decision ids"
            )
        measured_numerator = math.fsum(
            item.certified_mass for item in self.decision_masses
        )
        measured_denominator = math.fsum(
            item.denominator_mass for item in self.decision_masses
        )
        if not math.isclose(
            self.numerator, measured_numerator, rel_tol=0.0, abs_tol=1e-12
        ) or not math.isclose(
            self.denominator, measured_denominator, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError(
                "coverage totals must be derived from their bound decision masses"
            )
        formula_mass = math.fsum(mass for _, mass in self.population.formula_inputs)
        if not math.isclose(self.numerator, formula_mass, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(
                "coverage numerator must equal exact formula-input projection mass"
            )

    @property
    def ratio(self) -> float | None:
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator


@dataclass(frozen=True)
class PaperEvidenceCertification:
    paper_id: str
    projection_digest: str
    decided_kinds: tuple[EvidenceKind, ...]
    certified_kinds: tuple[EvidenceKind, ...]
    decision_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise ValueError("certified paper id must be non-empty")
        if not _is_sha256(self.projection_digest):
            raise ValueError("certified paper projection digest must be SHA-256")
        if len(set(self.certified_kinds)) != len(self.certified_kinds):
            raise ValueError("certified paper evidence kinds must be unique")
        if len(set(self.decided_kinds)) != len(self.decided_kinds):
            raise ValueError("decided paper evidence kinds must be unique")
        if not set(self.certified_kinds).issubset(self.decided_kinds):
            raise ValueError("certified paper kinds must have certification decisions")
        if not self.decision_ids or len(set(self.decision_ids)) != len(
            self.decision_ids
        ):
            raise ValueError(
                "paper certification decision ids must be non-empty/unique"
            )
        if len(self.decision_ids) != len(self.decided_kinds):
            raise ValueError(
                "paper certification requires one decision per evidence kind"
            )


@dataclass(frozen=True)
class SourceYearCertification:
    calendar_year: int
    entity_type: str
    cutoff: datetime
    dataset_version: str
    acquisition_scope: str
    state: CertificationState
    required_partition_ids: tuple[str, ...]
    verified_partition_ids: tuple[str, ...]
    required_coverage_kinds: tuple[EvidenceKind, ...]
    canonical_paper_count: int
    canonical_paper_population_digest: str
    coverage_population_digests: tuple[tuple[EvidenceKind, str], ...]
    coverage: tuple[CoverageCertification, ...]
    decision_ids: tuple[str, ...]
    input_digest: str
    rule_version: str
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.calendar_year < 1900:
            raise ValueError("source year is outside the supported historical range")
        if any(
            not value.strip()
            for value in (
                self.dataset_version,
                self.acquisition_scope,
                self.entity_type,
                self.input_digest,
                self.rule_version,
            )
        ):
            raise ValueError("source-year certification identifiers must be non-empty")
        if not _is_sha256(self.input_digest):
            raise ValueError("source-year input digest must be SHA-256")
        if self.entity_type not in {"researcher", "institution", "country"}:
            raise ValueError("source-year entity type is unsupported")
        if self.canonical_paper_count < 0 or not _is_sha256(
            self.canonical_paper_population_digest
        ):
            raise ValueError("source-year canonical paper population is invalid")
        if len({kind for kind, _ in self.coverage_population_digests}) != len(
            self.coverage_population_digests
        ) or any(
            not _is_sha256(digest) for _, digest in self.coverage_population_digests
        ):
            raise ValueError("source-year coverage population digests are invalid")
        if self.cutoff.tzinfo is None or self.cutoff.utcoffset() is None:
            raise ValueError("source-year cutoff must include a timezone")
        if len(set(self.required_partition_ids)) != len(self.required_partition_ids):
            raise ValueError("required source partitions must be unique")
        if len(set(self.verified_partition_ids)) != len(self.verified_partition_ids):
            raise ValueError("verified source partitions must be unique")
        if not self.required_coverage_kinds or len(
            set(self.required_coverage_kinds)
        ) != len(self.required_coverage_kinds):
            raise ValueError(
                "required source-year coverage kinds must be non-empty/unique"
            )
        if self.state == "certified" and (
            not self.required_partition_ids
            or self.canonical_paper_count <= 0
            or set(self.required_partition_ids) != set(self.verified_partition_ids)
            or self.calendar_year >= self.cutoff.year
        ):
            raise ValueError("certified source years must be closed and complete")
        if self.state != "certified" and not self.reasons:
            raise ValueError("non-certified source years must retain a reason")

    @property
    def certification_id(self) -> str:
        return f"source-year-{canonical_digest(self)}"


@dataclass(frozen=True)
class MetricWindowCertification:
    metric_id: str
    entity_type: str
    terminal_year: int
    required_years: tuple[int, ...]
    source_year_certification_ids: tuple[str, ...]
    citation_cohort_certification_ids: tuple[str, ...]
    cutoff: datetime
    dataset_version: str
    acquisition_scope: str
    threshold_version: str
    state: CertificationState
    input_digest: str
    rule_version: str
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.metric_id,
                self.entity_type,
                self.dataset_version,
                self.acquisition_scope,
                self.threshold_version,
                self.input_digest,
                self.rule_version,
            )
        ):
            raise ValueError(
                "metric-window certification identifiers must be non-empty"
            )
        if not _is_sha256(self.input_digest):
            raise ValueError("metric-window input digest must be SHA-256")
        if self.entity_type not in {"researcher", "institution", "country"}:
            raise ValueError("metric-window entity type is unsupported")
        if self.cutoff.tzinfo is None or self.cutoff.utcoffset() is None:
            raise ValueError("metric-window cutoff must include a timezone")
        if not self.required_years or len(set(self.required_years)) != len(
            self.required_years
        ):
            raise ValueError("metric-window years must be non-empty and unique")
        if self.state == "certified" and len(self.source_year_certification_ids) != len(
            self.required_years
        ):
            raise ValueError(
                "certified metric windows require one proof per source year"
            )
        if len(set(self.citation_cohort_certification_ids)) != len(
            self.citation_cohort_certification_ids
        ):
            raise ValueError("citation cohort certification ids must be unique")
        if (
            self.state == "certified"
            and self.metric_id == "research_impact"
            and not self.citation_cohort_certification_ids
        ):
            raise ValueError("certified Impact windows require citation cohort proofs")
        if (
            self.metric_id != "research_impact"
            and self.citation_cohort_certification_ids
        ):
            raise ValueError("only Impact windows may carry citation cohort proofs")
        if self.state != "certified" and not self.reasons:
            raise ValueError("non-certified metric windows must retain a reason")

    @property
    def certification_id(self) -> str:
        return f"metric-window-{canonical_digest(self)}"


@dataclass(frozen=True)
class MetricPartitionCertification:
    metric_id: str
    dataset_version: str
    acquisition_scope: str
    threshold_version: str
    state: CertificationState
    input_digest: str
    evidence_cutoff: datetime
    window_certification_id: str
    population_certification_id: str
    citation_cohort_certification_ids: tuple[str, ...]
    evidence_decisions: tuple[EvidenceCertificationDecision, ...]
    paper_certifications: tuple[PaperEvidenceCertification, ...]
    coverage: tuple[CoverageCertification, ...]
    decision_ids: tuple[str, ...]
    rule_version: str = CERTIFICATION_POLICY_VERSION
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_decisions, tuple) or any(
            not isinstance(item, EvidenceCertificationDecision)
            for item in self.evidence_decisions
        ):
            raise CertificationError(
                "metric partition requires exact evidence decisions"
            )
        if not isinstance(self.paper_certifications, tuple) or any(
            not isinstance(item, PaperEvidenceCertification)
            for item in self.paper_certifications
        ):
            raise CertificationError(
                "metric partition requires exact paper certifications"
            )
        if not isinstance(self.coverage, tuple) or any(
            not isinstance(item, CoverageCertification) for item in self.coverage
        ):
            raise CertificationError(
                "metric partition requires exact coverage certifications"
            )
        if any(
            not value.strip()
            for value in (
                self.metric_id,
                self.dataset_version,
                self.acquisition_scope,
                self.threshold_version,
                self.input_digest,
                self.window_certification_id,
                self.population_certification_id,
                self.rule_version,
            )
        ):
            raise ValueError("metric-partition certification ids must be non-empty")
        if not _is_sha256(self.input_digest):
            raise ValueError("metric-partition input digest must be SHA-256")
        if (
            self.evidence_cutoff.tzinfo is None
            or self.evidence_cutoff.utcoffset() is None
        ):
            raise ValueError("metric-partition evidence cutoff must include a timezone")
        paper_ids = [item.paper_id for item in self.paper_certifications]
        if len(set(paper_ids)) != len(paper_ids):
            raise ValueError("metric partition may certify each paper only once")
        coverage_kinds = [item.evidence_kind for item in self.coverage]
        if len(set(coverage_kinds)) != len(coverage_kinds):
            raise ValueError("metric partition coverage kinds must be unique")
        if len(set(self.citation_cohort_certification_ids)) != len(
            self.citation_cohort_certification_ids
        ):
            raise ValueError("metric partition citation cohort ids must be unique")
        if (
            self.state == "certified"
            and self.metric_id == "research_impact"
            and not self.citation_cohort_certification_ids
        ):
            raise ValueError(
                "certified Impact partitions require citation cohort proofs"
            )
        if (
            self.metric_id != "research_impact"
            and self.citation_cohort_certification_ids
        ):
            raise ValueError("only Impact partitions may carry citation cohort proofs")
        if self.state != "certified" and not self.reasons:
            raise ValueError("non-certified metric partitions must retain a reason")
        evidence_decision_ids = tuple(
            sorted(item.decision_id for item in self.evidence_decisions)
        )
        if (
            not evidence_decision_ids
            or len(set(evidence_decision_ids)) != len(evidence_decision_ids)
            or evidence_decision_ids != self.decision_ids
        ):
            raise ValueError(
                "metric partition decision ids must bind exact evidence decisions"
            )

    @property
    def certification_digest(self) -> str:
        return canonical_digest(self)

    @property
    def certification_id(self) -> str:
        return f"metric-partition-{self.certification_digest}"


@dataclass(frozen=True)
class CertifiedMetricPartition[PartitionT]:
    partition: PartitionT
    certification: MetricPartitionCertification
    window_proof: object
    population_proof: object

    def __post_init__(self) -> None:
        if not isinstance(self.certification, MetricPartitionCertification):
            raise CertificationError(
                "metric partition proof requires an exact certification result"
            )
        if self.certification.state != "certified":
            raise CertificationError("metric calculators require certified evidence")
        if self.certification.rule_version != CERTIFICATION_POLICY_VERSION:
            raise CertificationError("metric partition certification rule is stale")
        if canonical_digest(self.partition) != self.certification.input_digest:
            raise CertificationError("metric partition input digest does not match")
        from .citations import impact_comparable_paper_ids
        from .coverage import COVERAGE_SUBJECT_TYPE, validate_coverage_certification
        from .populations import (
            CertifiedMetricPopulation,
            metric_population_coverage_ledger,
        )
        from .projections import paper_evidence_value_digest
        from .rules import (
            evidence_decision_is_current,
            required_coverage_evidence,
            required_paper_evidence,
        )
        from .years import CertifiedMetricWindow

        if not isinstance(self.window_proof, CertifiedMetricWindow):
            raise CertificationError("metric partition lacks a certified window proof")
        if not isinstance(self.population_proof, CertifiedMetricPopulation):
            raise CertificationError(
                "metric partition lacks a certified population proof"
            )
        if (
            self.window_proof.certification.certification_id
            != self.certification.window_certification_id
        ):
            raise CertificationError("metric partition window proof does not match")
        if (
            self.certification.citation_cohort_certification_ids
            != self.window_proof.certification.citation_cohort_certification_ids
        ):
            raise CertificationError(
                "metric partition citation cohort proofs differ from its window"
            )
        if (
            self.population_proof.certification.certification_id
            != self.certification.population_certification_id
            or self.population_proof.window != self.window_proof
        ):
            raise CertificationError("metric partition population proof does not match")
        metric_id = self.certification.metric_id
        entity_type = getattr(self.partition, "entity_type", None)
        entity_id = getattr(self.partition, "entity_id", None)
        field_id = getattr(self.partition, "field_id", None)
        terminal_year = getattr(self.partition, "terminal_year", None)
        papers = getattr(self.partition, "papers", None)
        if (
            not isinstance(entity_type, str)
            or not isinstance(entity_id, str)
            or not isinstance(field_id, str)
            or not isinstance(terminal_year, int)
            or isinstance(terminal_year, bool)
            or not isinstance(papers, tuple)
        ):
            raise CertificationError("metric partition structure is invalid")
        if (
            self.window_proof.certification.metric_id != metric_id
            or self.window_proof.certification.entity_type != entity_type
            or self.window_proof.certification.terminal_year != terminal_year
            or self.window_proof.certification.threshold_version
            != self.certification.threshold_version
            or self.window_proof.certification.dataset_version
            != self.certification.dataset_version
            or self.window_proof.certification.acquisition_scope
            != self.certification.acquisition_scope
            or self.window_proof.certification.cutoff
            != self.certification.evidence_cutoff
        ):
            raise CertificationError("metric partition window lineage differs")
        if (
            getattr(self.partition, "dataset_version", None)
            != self.certification.dataset_version
            or getattr(self.partition, "acquisition_scope", None)
            != self.certification.acquisition_scope
            or getattr(self.partition, "as_of_date", None)
            != self.certification.evidence_cutoff.date()
        ):
            raise CertificationError("metric partition certification lineage differs")
        complete_source_years = getattr(self.partition, "complete_source_years", None)
        if not isinstance(complete_source_years, tuple) or not set(
            self.window_proof.certification.required_years
        ).issubset(complete_source_years):
            raise CertificationError(
                "metric partition lacks its certified complete source years"
            )
        expected_paper_ids = {getattr(item, "paper_id", None) for item in papers}
        window_projections = {
            projection.paper_id: projection
            for source_year in self.window_proof.source_years
            for projection in source_year.evidence.paper_projections
        }
        if len(window_projections) != sum(
            len(source_year.evidence.paper_projections)
            for source_year in self.window_proof.source_years
        ):
            raise CertificationError(
                "metric window repeats canonical papers across source years"
            )
        for paper in papers:
            paper_id = getattr(paper, "paper_id", None)
            if not isinstance(paper_id, str):
                raise CertificationError("metric partition paper id is invalid")
            projection = window_projections.get(paper_id)
            if projection is None or projection.publication_date != getattr(
                paper, "publication_date", None
            ):
                raise CertificationError(
                    "metric partition paper is absent from its certified source window"
                )
        certified_paper_ids = {
            item.paper_id for item in self.certification.paper_certifications
        }
        if None in expected_paper_ids or expected_paper_ids != certified_paper_ids:
            raise CertificationError(
                "metric partition paper certifications are incomplete"
            )
        included_population = {
            item.paper_id: item
            for item in self.population_proof.certification.evidence.projections
            if item.status == "included"
        }
        population_evidence = self.population_proof.certification.evidence
        if (
            population_evidence.metric_id != metric_id
            or population_evidence.terminal_year != terminal_year
            or population_evidence.dataset_version != self.certification.dataset_version
            or population_evidence.acquisition_scope
            != self.certification.acquisition_scope
            or population_evidence.entity_type != entity_type
            or population_evidence.entity_id != entity_id
            or population_evidence.field_id != field_id
            or population_evidence.source_year_certification_ids
            != self.window_proof.certification.source_year_certification_ids
        ):
            raise CertificationError(
                "metric partition population proof targets another context"
            )
        if metric_id == "research_diversity":
            category_universe = population_evidence.category_universe
            eligible_category_ids = getattr(
                self.partition, "eligible_category_ids", None
            )
            if (
                category_universe is None
                or not isinstance(eligible_category_ids, tuple)
                or tuple(sorted(category_universe.evidence.category_ids))
                != tuple(sorted(eligible_category_ids))
            ):
                raise CertificationError(
                    "Diversity partition lacks its reviewed category universe"
                )
        elif population_evidence.category_universe is not None:
            raise CertificationError(
                "non-Diversity partitions cannot carry a category universe"
            )
        if set(included_population) != expected_paper_ids or any(
            included_population[paper.paper_id].publication_date
            != paper.publication_date
            or not math.isclose(
                included_population[paper.paper_id].attribution_weight,
                float(paper.attribution_weight),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            for paper in papers
        ):
            raise CertificationError(
                "metric partition differs from its exact eligibility population"
            )
        paper_requirements = required_paper_evidence(metric_id, entity_type)
        if any(
            item.decided_kinds != paper_requirements
            for item in self.certification.paper_certifications
        ):
            raise CertificationError("metric partition paper evidence is incomplete")
        papers_by_id = {getattr(item, "paper_id", None): item for item in papers}
        if any(
            item.projection_digest != canonical_digest(papers_by_id[item.paper_id])
            for item in self.certification.paper_certifications
        ):
            raise CertificationError(
                "metric partition paper projection proof does not match"
            )
        decisions = self.certification.evidence_decisions
        if any(
            not evidence_decision_is_current(item)
            or item.dataset_version != self.certification.dataset_version
            or item.acquisition_scope != self.certification.acquisition_scope
            for item in decisions
        ):
            raise CertificationError("metric partition evidence decision is stale")
        decisions_by_id = {item.decision_id: item for item in decisions}
        used_decision_ids: set[str] = set()
        for paper_certification in self.certification.paper_certifications:
            paper_decisions = tuple(
                decisions_by_id.get(decision_id)
                for decision_id in paper_certification.decision_ids
            )
            if (
                any(decision is None for decision in paper_decisions)
                or {
                    decision.evidence_kind
                    for decision in paper_decisions
                    if decision is not None
                }
                != set(paper_requirements)
                or any(
                    decision is None
                    or decision.subject_type != "paper"
                    or decision.subject_id != paper_certification.paper_id
                    for decision in paper_decisions
                )
            ):
                raise CertificationError(
                    "metric partition paper proof does not match its subject"
                )
            paper_value = papers_by_id[paper_certification.paper_id]
            for decision in paper_decisions:
                assert decision is not None
                used_decision_ids.add(decision.decision_id)
                if decision.certified_value_digest != paper_evidence_value_digest(
                    self.partition,
                    paper_value,
                    decision.evidence_kind,
                ):
                    raise CertificationError(
                        "paper evidence decision does not bind its formula input"
                    )
                if decision.evidence_kind in paper_certification.certified_kinds:
                    if decision.state != "certified":
                        raise CertificationError(
                            "paper certified kinds differ from their decisions"
                        )
                    continue
                explicit_missing = (
                    metric_id == "research_impact"
                    and decision.evidence_kind == "citation-observation"
                    and getattr(paper_value, "citation_count", None) is None
                ) or (
                    metric_id == "research_impact"
                    and decision.evidence_kind == "citation-cutoff-compatibility"
                    and getattr(paper_value, "citation_observed_at", None) is None
                )
                if metric_id == "collaboration" and decision.evidence_kind == (
                    "collaboration-relationship"
                ):
                    relationship_attribute = {
                        "researcher": "collaborative",
                        "institution": "cross_institution",
                        "country": "international",
                    }[entity_type]
                    explicit_missing = (
                        getattr(paper_value, relationship_attribute, None) is None
                    )
                if decision.state != "insufficient_evidence" or not explicit_missing:
                    raise CertificationError(
                        "non-certified paper evidence is not an explicit missing value"
                    )
        expected_coverage = required_coverage_evidence(metric_id, entity_type)
        if tuple(item.evidence_kind for item in self.certification.coverage) != (
            expected_coverage
        ):
            raise CertificationError("metric partition coverage proof is incomplete")
        for coverage in self.certification.coverage:
            population = tuple(
                item
                for item in decisions
                if item.subject_type == COVERAGE_SUBJECT_TYPE
                and item.evidence_kind == coverage.evidence_kind
            )
            validate_coverage_certification(coverage, population)
            used_decision_ids.update(coverage.decision_ids)
        if used_decision_ids != set(self.certification.decision_ids):
            raise CertificationError(
                "metric partition contains unrelated or omitted evidence decisions"
            )
        coverage_ledger = metric_population_coverage_ledger(population_evidence)
        expected_population_units = tuple(
            (item.unit_id, item.mass) for item in coverage_ledger
        )
        expected_coverage_mass = math.fsum(item.mass for item in coverage_ledger)
        if expected_coverage_mass <= 0:
            raise CertificationError("metric partition coverage universe is empty")
        coverage_value = getattr(self.partition, "coverage", None)
        coverage_attributes = {
            "paper-time-affiliation": "paper_time_affiliation",
            "canonical-institution": "canonical_institution",
            "citation-observation": "citation",
            "field-classification": "field_attribution",
            "collaboration-relationship": "collaboration_relationship",
        }
        comparable_citation_ids = (
            frozenset(
                impact_comparable_paper_ids(
                    self.partition, self.window_proof.citation_cohorts
                )
            )
            if metric_id == "research_impact"
            else frozenset()
        )
        for coverage in self.certification.coverage:
            relationship_attribute = {
                "researcher": "collaborative",
                "institution": "cross_institution",
                "country": "international",
            }[entity_type]
            observed_mass = math.fsum(
                float(getattr(paper, "attribution_weight", 0.0))
                for paper in papers
                if (
                    coverage.evidence_kind != "citation-observation"
                    or getattr(paper, "paper_id", None) in comparable_citation_ids
                )
                and (
                    coverage.evidence_kind != "collaboration-relationship"
                    or getattr(paper, relationship_attribute, None) is not None
                )
            )
            expected_formula_inputs = tuple(
                sorted(
                    (
                        str(paper.paper_id),
                        float(getattr(paper, "attribution_weight", 0.0)),
                    )
                    for paper in papers
                    if (
                        coverage.evidence_kind != "citation-observation"
                        or getattr(paper, "paper_id", None) in comparable_citation_ids
                    )
                    and (
                        coverage.evidence_kind != "collaboration-relationship"
                        or getattr(paper, relationship_attribute, None) is not None
                    )
                )
            )
            if (
                coverage.population.source_manifest_digest
                != self.population_proof.certification.projection_digest
                or coverage.population.units != expected_population_units
            ):
                raise CertificationError(
                    "metric partition coverage population differs from the exact "
                    "reviewed metric population"
                )
            if coverage.population.formula_inputs != expected_formula_inputs:
                raise CertificationError(
                    "metric partition formula-input coverage projection differs"
                )
            if not math.isclose(
                coverage.numerator,
                observed_mass,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise CertificationError(
                    "metric partition certified mass differs from formula evidence"
                )
            if not math.isclose(
                coverage.denominator,
                expected_coverage_mass,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise CertificationError(
                    "metric partition coverage omits or adds reviewed source mass"
                )
            supplied = getattr(
                coverage_value,
                coverage_attributes[coverage.evidence_kind],
                None,
            )
            if (
                not isinstance(supplied, (int, float))
                or isinstance(supplied, bool)
                or coverage.ratio is None
                or not math.isclose(
                    float(supplied),
                    coverage.ratio,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
            ):
                raise CertificationError(
                    "metric partition coverage value differs from its proof"
                )
        from ..attribution import FRACTIONAL_ATTRIBUTION_V1
        from ..fields import (
            PHYSICS_FIELD_ONTOLOGY_VERSION,
            PROVIDER_FIELD_MAPPING_VERSION,
        )
        from .measurement_windows import partition_citation_policy_is_current

        if (
            getattr(self.partition, "attribution_policy_version", None)
            != FRACTIONAL_ATTRIBUTION_V1.version
            or getattr(self.partition, "ontology_version", None)
            != PHYSICS_FIELD_ONTOLOGY_VERSION
            or getattr(self.partition, "mapping_policy_version", None)
            != PROVIDER_FIELD_MAPPING_VERSION
            or not partition_citation_policy_is_current(
                self.partition, metric_id, self.window_proof.citation_cohorts
            )
        ):
            raise CertificationError(
                "metric partition uses an unapproved scientific policy version"
            )


@dataclass(frozen=True)
class CertifiedCitationCohort[CohortT]:
    cohort: CohortT
    certification_proof: object
    certification_id: str
    dataset_version: str
    acquisition_scope: str
    cutoff: datetime
    evidence_digest: str
    state: CertificationState = "certified"
    rule_version: str = CERTIFICATION_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.state != "certified":
            raise CertificationError("Impact requires a certified citation cohort")
        if any(
            not value.strip()
            for value in (
                self.certification_id,
                self.dataset_version,
                self.acquisition_scope,
                self.evidence_digest,
                self.rule_version,
            )
        ):
            raise ValueError("citation cohort certification ids must be non-empty")
        if not _is_sha256(self.evidence_digest):
            raise ValueError("citation cohort evidence digest must be SHA-256")
        if self.cutoff.tzinfo is None or self.cutoff.utcoffset() is None:
            raise ValueError("citation cohort cutoff must include a timezone")
        if canonical_digest(self.cohort) != self.evidence_digest:
            raise CertificationError("citation cohort evidence digest does not match")
        from .citations import CitationCohortCertification

        proof = self.certification_proof
        if not isinstance(proof, CitationCohortCertification):
            raise CertificationError("citation cohort lacks its certification proof")
        if (
            proof.state != "certified"
            or proof.certification_id != self.certification_id
            or proof.dataset_version != self.dataset_version
            or proof.acquisition_scope != self.acquisition_scope
            or proof.cutoff != self.cutoff
            or proof.rule_version != self.rule_version
        ):
            raise CertificationError("citation cohort certification proof differs")
        key = getattr(self.cohort, "key", None)
        observed_at = getattr(self.cohort, "observed_at", None)
        citations = getattr(self.cohort, "citations", None)
        certified_values = {
            item.paper_id: item.non_self_citation_count
            for item in proof.observations
            if item.state == "certified"
        }
        if (
            key != proof.cohort_key
            or observed_at != proof.cutoff.date()
            or not isinstance(citations, tuple)
            or len(dict(citations)) != len(citations)
            or dict(citations) != certified_values
        ):
            raise CertificationError(
                "citation cohort values do not match certification proof"
            )


def require_certified_partition[PartitionValueT](
    value: CertifiedMetricPartition[PartitionValueT],
    *,
    metric_id: str,
    threshold_version: str,
) -> PartitionValueT:
    if not isinstance(value, CertifiedMetricPartition):
        raise CertificationError(
            "raw metric partitions are not calculation-eligible; certify evidence first"
        )
    if value.certification.metric_id != metric_id:
        raise CertificationError(
            "metric partition certification targets another metric"
        )
    if value.certification.threshold_version != threshold_version:
        raise CertificationError("metric certification threshold version is stale")
    from .rules import coverage_minimum

    for item in value.certification.coverage:
        if item.state != "certified" or not math.isclose(
            item.minimum,
            coverage_minimum(item.evidence_kind),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise CertificationError("metric coverage certification policy is stale")
    if canonical_digest(value.partition) != value.certification.input_digest:
        raise CertificationError("metric partition changed after certification")
    return value.partition


def require_certified_citation_cohort[CohortValueT](
    value: CertifiedCitationCohort[CohortValueT],
    *,
    dataset_version: str,
    acquisition_scope: str,
    cutoff: date,
    rule_version: str,
) -> CohortValueT:
    if not isinstance(value, CertifiedCitationCohort):
        raise CertificationError(
            "raw citation cohorts are not Impact-eligible; certify evidence first"
        )
    if (
        value.dataset_version != dataset_version
        or value.acquisition_scope != acquisition_scope
        or value.cutoff.date() != cutoff
        or value.rule_version != rule_version
    ):
        raise CertificationError("citation cohort lineage does not match the partition")
    if canonical_digest(value.cohort) != value.evidence_digest:
        raise CertificationError("citation cohort changed after certification")
    return value.cohort
