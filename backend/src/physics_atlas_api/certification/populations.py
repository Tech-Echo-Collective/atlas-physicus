from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from .contracts import (
    CERTIFICATION_POLICY_VERSION,
    CertificationError,
    EvidenceCertificationDecision,
    canonical_digest,
)
from .years import CertifiedMetricWindow

METRIC_POPULATION_SUBJECT_TYPE = "metric-population"
METRIC_POPULATION_CERTIFICATION_VERSION = "metric-population-certification-v1"
MetricPopulationStatus = Literal["included", "excluded", "unresolved"]
MetricPopulationCoverageStatus = Literal["known", "unresolved"]


@dataclass(frozen=True)
class CategoryUniverseEvidence:
    """Reviewed category universe used by Diversity for one canonical field."""

    field_id: str
    dataset_version: str
    acquisition_scope: str
    category_universe_version: str
    category_ids: tuple[str, ...]
    source_manifest_digest: str
    review_state: str
    reviewed_by: str
    reviewed_at: datetime

    @property
    def content_digest(self) -> str:
        return canonical_digest(
            (
                self.field_id,
                self.dataset_version,
                self.acquisition_scope,
                self.category_universe_version,
                tuple(sorted(self.category_ids)),
            )
        )


@dataclass(frozen=True)
class CertifiedCategoryUniverse:
    evidence: CategoryUniverseEvidence
    certification_digest: str

    def __post_init__(self) -> None:
        _validate_category_universe(self.evidence)
        if self.certification_digest != canonical_digest(self.evidence):
            raise CertificationError("category-universe proof does not reconstruct")


def _validate_category_universe(evidence: CategoryUniverseEvidence) -> None:
    if not isinstance(evidence, CategoryUniverseEvidence):
        raise CertificationError("category universe requires exact reviewed evidence")
    identifiers = (
        evidence.field_id,
        evidence.dataset_version,
        evidence.acquisition_scope,
        evidence.category_universe_version,
        evidence.reviewed_by,
    )
    if any(not item.strip() for item in identifiers):
        raise CertificationError("category-universe identifiers must be non-empty")
    if (
        not isinstance(evidence.category_ids, tuple)
        or len(evidence.category_ids) < 2
        or len(set(evidence.category_ids)) != len(evidence.category_ids)
        or any(not item.strip() for item in evidence.category_ids)
    ):
        raise CertificationError(
            "Diversity category universe must contain at least two unique categories"
        )
    if (
        evidence.review_state != "reviewed-approved"
        or evidence.reviewed_at.tzinfo is None
        or evidence.reviewed_at.utcoffset() is None
    ):
        raise CertificationError("category universe requires dated reviewed approval")
    if evidence.source_manifest_digest != evidence.content_digest:
        raise CertificationError(
            "category-universe manifest does not match reviewed content"
        )


def certify_category_universe(
    evidence: CategoryUniverseEvidence,
) -> CertifiedCategoryUniverse:
    _validate_category_universe(evidence)
    return CertifiedCategoryUniverse(evidence, canonical_digest(evidence))


@dataclass(frozen=True)
class MetricPopulationProjection:
    """One source-window paper's eligibility for an entity/field partition."""

    paper_id: str
    publication_date: date
    entity_type: str
    entity_id: str
    field_id: str
    status: MetricPopulationStatus
    entity_attribution_weight: float
    field_weight: float
    attribution_weight: float
    coverage_weight: float
    reason: str | None = None

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.paper_id,
                self.entity_type,
                self.entity_id,
                self.field_id,
            )
        ):
            raise ValueError("metric population identifiers must be non-empty")
        if self.entity_type not in {"researcher", "institution", "country"}:
            raise ValueError("metric population entity type is unsupported")
        if any(
            not math.isfinite(value) or not 0 <= value <= 1
            for value in (
                self.entity_attribution_weight,
                self.field_weight,
                self.attribution_weight,
                self.coverage_weight,
            )
        ):
            raise ValueError("metric population weights must be within [0,1]")
        if not math.isclose(
            self.attribution_weight,
            self.entity_attribution_weight * self.field_weight,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "metric population weight must equal entity share times field share"
            )
        if self.coverage_weight < self.attribution_weight:
            raise ValueError(
                "metric population coverage weight cannot omit known attribution"
            )
        if self.status == "included":
            if self.attribution_weight <= 0 or self.reason is not None:
                raise ValueError(
                    "included population rows need positive weight and no reason"
                )
        elif self.attribution_weight != 0 or not self.reason or not self.reason.strip():
            raise ValueError(
                "excluded/unresolved population rows need zero weight and a reason"
            )
        if self.status == "excluded" and self.coverage_weight != 0:
            raise ValueError("excluded population rows cannot retain possible mass")
        if self.status == "unresolved" and self.coverage_weight <= 0:
            raise ValueError("unresolved population rows require possible mass")

    @property
    def value_digest(self) -> str:
        return canonical_digest(self)


@dataclass(frozen=True)
class MetricPopulationCoverageUnit:
    """One exact known or unresolved mass unit in a metric population."""

    unit_id: str
    paper_id: str
    status: MetricPopulationCoverageStatus
    mass: float

    def __post_init__(self) -> None:
        expected_id = metric_population_coverage_unit_id(self.paper_id, self.status)
        if self.unit_id != expected_id:
            raise ValueError("metric population coverage unit id does not reconstruct")
        if not math.isfinite(self.mass) or self.mass <= 0:
            raise ValueError("metric population coverage unit mass must be positive")


def metric_population_coverage_unit_id(
    paper_id: str,
    status: MetricPopulationCoverageStatus,
) -> str:
    """Return a collision-resistant id for one paper's known/unresolved mass."""

    if not paper_id.strip():
        raise ValueError("metric population coverage paper id must be non-empty")
    return f"metric-coverage-{canonical_digest((paper_id, status))}"


def metric_population_coverage_ledger(
    evidence: MetricPopulationEvidence,
) -> tuple[MetricPopulationCoverageUnit, ...]:
    """Derive the full denominator ledger from the reviewed metric population."""

    units: list[MetricPopulationCoverageUnit] = []
    for projection in sorted(evidence.projections, key=lambda item: item.paper_id):
        if projection.attribution_weight > 0:
            units.append(
                MetricPopulationCoverageUnit(
                    unit_id=metric_population_coverage_unit_id(
                        projection.paper_id, "known"
                    ),
                    paper_id=projection.paper_id,
                    status="known",
                    mass=projection.attribution_weight,
                )
            )
        unresolved_mass = projection.coverage_weight - projection.attribution_weight
        if unresolved_mass > 1e-12:
            units.append(
                MetricPopulationCoverageUnit(
                    unit_id=metric_population_coverage_unit_id(
                        projection.paper_id, "unresolved"
                    ),
                    paper_id=projection.paper_id,
                    status="unresolved",
                    mass=unresolved_mass,
                )
            )
    return tuple(units)


@dataclass(frozen=True)
class MetricPopulationEvidence:
    metric_id: str
    terminal_year: int
    dataset_version: str
    acquisition_scope: str
    entity_type: str
    entity_id: str
    field_id: str
    source_manifest_digest: str
    review_state: str
    reviewed_by: str
    reviewed_at: datetime
    source_year_certification_ids: tuple[str, ...]
    projections: tuple[MetricPopulationProjection, ...]
    decisions: tuple[EvidenceCertificationDecision, ...]
    category_universe: CertifiedCategoryUniverse | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.projections, tuple) or any(
            not isinstance(item, MetricPopulationProjection)
            for item in self.projections
        ):
            raise CertificationError("metric population requires exact projections")
        if not isinstance(self.decisions, tuple) or any(
            not isinstance(item, EvidenceCertificationDecision)
            for item in self.decisions
        ):
            raise CertificationError("metric population requires exact decisions")
        if self.metric_id == "research_diversity":
            if not isinstance(self.category_universe, CertifiedCategoryUniverse):
                raise CertificationError(
                    "Diversity requires a certified reviewed category universe"
                )
        elif self.category_universe is not None:
            raise CertificationError(
                "only Diversity metric populations may carry a category universe"
            )
        if self.review_state != "reviewed-approved":
            raise ValueError("metric population requires explicit reviewed approval")
        if not self.reviewed_by.strip():
            raise ValueError("metric population reviewer is required")
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("metric population review timestamp must include timezone")
        if len(self.source_manifest_digest) != 64:
            raise ValueError("metric population source manifest must be SHA-256")
        try:
            int(self.source_manifest_digest, 16)
        except ValueError as error:
            raise ValueError(
                "metric population source manifest must be hexadecimal"
            ) from error


@dataclass(frozen=True)
class MetricPopulationCertification:
    evidence: MetricPopulationEvidence
    state: Literal["certified"]
    projection_digest: str
    decision_ids: tuple[str, ...]
    source_population_digest: str
    rule_version: str = METRIC_POPULATION_CERTIFICATION_VERSION

    @property
    def certification_id(self) -> str:
        return f"metric-population-{canonical_digest(self)}"


def certify_metric_population(
    evidence: MetricPopulationEvidence,
    window: CertifiedMetricWindow,
) -> MetricPopulationCertification:
    """Bind exact entity/field inclusion and exclusion to a certified source window."""

    if not isinstance(evidence, MetricPopulationEvidence):
        raise CertificationError("metric population requires exact reviewed evidence")
    if not isinstance(window, CertifiedMetricWindow):
        raise CertificationError("metric population requires a certified window proof")
    if window.state != "certified":
        raise CertificationError("metric window is not certified")
    identifiers = (
        evidence.metric_id,
        evidence.dataset_version,
        evidence.acquisition_scope,
        evidence.entity_type,
        evidence.entity_id,
        evidence.field_id,
    )
    if any(not value.strip() for value in identifiers):
        raise CertificationError("metric population identifiers must be non-empty")
    window_certification = window.certification
    if (
        evidence.metric_id != window_certification.metric_id
        or evidence.terminal_year != window_certification.terminal_year
        or evidence.dataset_version != window_certification.dataset_version
        or evidence.acquisition_scope != window_certification.acquisition_scope
        or evidence.entity_type != window_certification.entity_type
        or evidence.source_year_certification_ids
        != window_certification.source_year_certification_ids
    ):
        raise CertificationError("metric population lineage differs from its window")
    if evidence.metric_id == "research_diversity":
        category_universe = evidence.category_universe
        if category_universe is None:
            raise CertificationError(
                "Diversity requires a reviewed exact category universe"
            )
        category_evidence = category_universe.evidence
        if (
            category_evidence.field_id != evidence.field_id
            or category_evidence.dataset_version != evidence.dataset_version
            or category_evidence.acquisition_scope != evidence.acquisition_scope
        ):
            raise CertificationError(
                "Diversity category universe targets another evidence partition"
            )
    elif evidence.category_universe is not None:
        raise CertificationError(
            "only Diversity metric populations may carry a category universe"
        )

    source_projections = {
        projection.paper_id: projection
        for source_year in window.source_years
        for projection in source_year.evidence.paper_projections
    }
    source_count = sum(
        len(source_year.evidence.paper_projections)
        for source_year in window.source_years
    )
    if len(source_projections) != source_count:
        raise CertificationError("source window repeats canonical paper identities")
    projections = {item.paper_id: item for item in evidence.projections}
    if len(projections) != len(evidence.projections) or set(projections) != set(
        source_projections
    ):
        raise CertificationError(
            "metric population must decide every source-window paper exactly once"
        )
    projection_digest = canonical_digest(
        tuple(sorted(evidence.projections, key=lambda item: item.paper_id))
    )
    if evidence.source_manifest_digest != projection_digest:
        raise CertificationError(
            "metric population reviewed manifest does not match its projections"
        )
    if any(
        item.publication_date != source_projections[paper_id].publication_date
        or item.entity_type != evidence.entity_type
        or item.entity_id != evidence.entity_id
        or item.field_id != evidence.field_id
        for paper_id, item in projections.items()
    ):
        raise CertificationError("metric population projection context differs")

    for paper_id, item in projections.items():
        source = source_projections[paper_id]
        source_entity_weight = math.fsum(
            weight
            for entity_type, entity_id, weight in source.entity_shares
            if entity_type == evidence.entity_type and entity_id == evidence.entity_id
        )
        source_field_weight = dict(source.field_weights).get(evidence.field_id, 0.0)
        expected_weight = source_entity_weight * source_field_weight
        unresolved_entity_mass = math.fsum(
            weight
            for entity_type, weight in source.unresolved_entity_mass
            if entity_type == evidence.entity_type
        )
        possible_weight = (source_entity_weight + unresolved_entity_mass) * (
            source_field_weight + source.unmapped_field_mass
        )
        expected_status: MetricPopulationStatus
        if expected_weight > 0:
            expected_status = "included"
        elif possible_weight > 0:
            expected_status = "unresolved"
        else:
            expected_status = "excluded"
        if (
            item.status != expected_status
            or not math.isclose(
                item.entity_attribution_weight,
                source_entity_weight,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or not math.isclose(
                item.field_weight,
                source_field_weight,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or not math.isclose(
                item.attribution_weight,
                expected_weight,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or not math.isclose(
                item.coverage_weight,
                possible_weight,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            raise CertificationError(
                "metric population eligibility does not derive from the conserved "
                "source field/entity ledger"
            )

    decisions = {item.subject_id: item for item in evidence.decisions}
    if len(decisions) != len(evidence.decisions) or set(decisions) != set(projections):
        raise CertificationError(
            "metric population requires one decision per source-window paper"
        )
    for paper_id, decision in decisions.items():
        projection = projections[paper_id]
        if (
            decision.subject_type != METRIC_POPULATION_SUBJECT_TYPE
            or decision.evidence_kind != "provenance-completeness"
            or decision.rule_version != CERTIFICATION_POLICY_VERSION
            or decision.dataset_version != evidence.dataset_version
            or decision.acquisition_scope != evidence.acquisition_scope
            or decision.certified_value_digest != projection.value_digest
            or decision.reviewed_by != evidence.reviewed_by
            or decision.reviewed_at != evidence.reviewed_at
            or (projection.status == "unresolved")
            != (decision.state == "insufficient_evidence")
            or (projection.status != "unresolved" and decision.state != "certified")
        ):
            raise CertificationError(
                "metric population decision does not bind its eligibility projection"
            )

    return MetricPopulationCertification(
        evidence=evidence,
        state="certified",
        projection_digest=projection_digest,
        decision_ids=tuple(sorted(item.decision_id for item in evidence.decisions)),
        source_population_digest=canonical_digest(
            tuple(
                sorted(
                    (
                        item.paper_id,
                        item.publication_date,
                        source_year.certification.certification_id,
                    )
                    for source_year in window.source_years
                    for item in source_year.evidence.paper_projections
                )
            )
        ),
    )


@dataclass(frozen=True)
class CertifiedMetricPopulation:
    certification: MetricPopulationCertification
    window: CertifiedMetricWindow

    def __post_init__(self) -> None:
        if not isinstance(self.certification, MetricPopulationCertification):
            raise CertificationError(
                "metric population proof requires an exact certification result"
            )
        rebuilt = certify_metric_population(self.certification.evidence, self.window)
        if rebuilt != self.certification:
            raise CertificationError("metric population proof does not reconstruct")


def wrap_certified_metric_population(
    evidence: MetricPopulationEvidence,
    window: CertifiedMetricWindow,
) -> CertifiedMetricPopulation:
    return CertifiedMetricPopulation(
        certify_metric_population(evidence, window), window
    )
