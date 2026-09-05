from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Literal

from ..fields import PHYSICS_FIELD_ONTOLOGY_V1, PHYSICS_FIELD_ONTOLOGY_VERSION
from .contracts import (
    CERTIFICATION_POLICY_VERSION,
    CertificationError,
    EvidenceCertificationDecision,
    canonical_digest,
)
from .years import CertifiedMetricWindow

METRIC_POPULATION_SUBJECT_TYPE = "metric-population"
METRIC_POPULATION_CERTIFICATION_VERSION = "metric-population-certification-v1"
AUTOMATIC_CATEGORY_UNIVERSE_VERSION = "ontology-category-universe-v1"
AUTOMATIC_METRIC_POPULATION_VERSION = "source-window-metric-population-v1"
_AUTOMATIC_UNRESOLVED_REASON = (
    "source-window affiliation or field mass remains unresolved"
)
_AUTOMATIC_EXCLUDED_REASON = (
    "source-window paper has no attribution to this entity and field"
)
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


def _ontology_category_ids(field_id: str) -> tuple[str, ...]:
    ontology = PHYSICS_FIELD_ONTOLOGY_V1
    if field_id == ontology.domain_id:
        return tuple(
            sorted(item.id for item in ontology.fields if item.node_kind == "field")
        )
    if not ontology.contains(field_id):
        raise CertificationError(
            "automatic category universe has an unknown ontology root"
        )
    categories = tuple(
        sorted(
            item.id
            for item in ontology.fields
            if item.node_kind == "field"
            and any(parent.id == field_id for parent in ontology.ancestors_of(item.id))
        )
    )
    if len(categories) < 2:
        raise CertificationError(
            "automatic Diversity needs at least two frozen ontology subfields; "
            "leaf-field subcategories cannot be invented"
        )
    return categories


@dataclass(frozen=True)
class AutomaticCategoryUniverseEvidence:
    """Exact frozen ontology membership, never a caller-selected category subset.

    This removes a human-signature requirement for catalog enumeration only.
    It does not certify acquisition breadth or supply absent leaf subfields.
    """

    field_id: str
    dataset_version: str
    acquisition_scope: str
    category_ids: tuple[str, ...]
    source_manifest_digest: str
    assessed_at: datetime
    category_universe_version: str = PHYSICS_FIELD_ONTOLOGY_VERSION
    assessment_version: str = AUTOMATIC_CATEGORY_UNIVERSE_VERSION

    @property
    def content_digest(self) -> str:
        return canonical_digest(
            (
                self.field_id,
                self.dataset_version,
                self.acquisition_scope,
                self.category_universe_version,
                self.category_ids,
                self.assessment_version,
            )
        )


type CategoryEvidence = CategoryUniverseEvidence | AutomaticCategoryUniverseEvidence


@dataclass(frozen=True)
class CertifiedCategoryUniverse:
    evidence: CategoryEvidence
    certification_digest: str

    def __post_init__(self) -> None:
        _validate_category_universe(self.evidence)
        if self.certification_digest != canonical_digest(self.evidence):
            raise CertificationError("category-universe proof does not reconstruct")


def _validate_category_universe(evidence: CategoryEvidence) -> None:
    if isinstance(evidence, AutomaticCategoryUniverseEvidence):
        if (
            not evidence.dataset_version.strip()
            or not evidence.acquisition_scope.strip()
            or evidence.category_universe_version != PHYSICS_FIELD_ONTOLOGY_VERSION
            or evidence.assessment_version != AUTOMATIC_CATEGORY_UNIVERSE_VERSION
            or not isinstance(evidence.assessed_at, datetime)
            or evidence.assessed_at.tzinfo is None
            or evidence.assessed_at.utcoffset() is None
            or evidence.category_ids != _ontology_category_ids(evidence.field_id)
            or evidence.source_manifest_digest != evidence.content_digest
        ):
            raise CertificationError("automatic category universe does not reconstruct")
        return
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
    evidence: CategoryEvidence,
) -> CertifiedCategoryUniverse:
    _validate_category_universe(evidence)
    return CertifiedCategoryUniverse(evidence, canonical_digest(evidence))


def derive_category_universe(
    *,
    field_id: str,
    dataset_version: str,
    acquisition_scope: str,
    assessed_at: datetime,
) -> CertifiedCategoryUniverse:
    """Bind all Physics leaves or a branch's complete descendant-leaf catalog."""
    evidence = AutomaticCategoryUniverseEvidence(
        field_id=field_id,
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        category_ids=_ontology_category_ids(field_id),
        source_manifest_digest="",
        assessed_at=assessed_at,
    )
    return certify_category_universe(
        replace(evidence, source_manifest_digest=evidence.content_digest)
    )


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
    evidence: PopulationEvidence,
) -> tuple[MetricPopulationCoverageUnit, ...]:
    """Derive the full denominator ledger from the exact metric population."""

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
class AutomaticMetricPopulationEvidence:
    """Mechanically derived eligibility over one exact certified source window.

    No review fields or success flag are serialized. Certification below repeats
    all existing inclusion, exclusion, conservation and provenance checks.
    """

    metric_id: str
    terminal_year: int
    dataset_version: str
    acquisition_scope: str
    entity_type: str
    entity_id: str
    field_id: str
    source_manifest_digest: str
    source_window_certification_id: str
    source_year_certification_ids: tuple[str, ...]
    projections: tuple[MetricPopulationProjection, ...]
    decisions: tuple[EvidenceCertificationDecision, ...]
    assessed_at: datetime
    category_universe: CertifiedCategoryUniverse | None = None
    assessment_version: str = AUTOMATIC_METRIC_POPULATION_VERSION

    def __post_init__(self) -> None:
        if (
            self.assessment_version != AUTOMATIC_METRIC_POPULATION_VERSION
            or not isinstance(self.assessed_at, datetime)
            or self.assessed_at.tzinfo is None
            or self.assessed_at.utcoffset() is None
            or not self.source_window_certification_id.strip()
            or not isinstance(self.projections, tuple)
            or any(
                not isinstance(item, MetricPopulationProjection)
                for item in self.projections
            )
            or not isinstance(self.decisions, tuple)
            or any(
                not isinstance(item, EvidenceCertificationDecision)
                for item in self.decisions
            )
        ):
            raise CertificationError(
                "automatic metric population requires exact typed evidence"
            )
        if self.metric_id == "research_diversity":
            if not isinstance(
                self.category_universe, CertifiedCategoryUniverse
            ) or not isinstance(
                self.category_universe.evidence, AutomaticCategoryUniverseEvidence
            ):
                raise CertificationError(
                    "automatic Diversity requires the frozen ontology universe"
                )
        elif self.category_universe is not None:
            raise CertificationError(
                "only Diversity metric populations may carry a category universe"
            )

    @property
    def reviewed_by(self) -> None:
        return None

    @property
    def reviewed_at(self) -> None:
        return None


type PopulationEvidence = MetricPopulationEvidence | AutomaticMetricPopulationEvidence


@dataclass(frozen=True)
class MetricPopulationCertification:
    evidence: PopulationEvidence
    state: Literal["certified"]
    projection_digest: str
    decision_ids: tuple[str, ...]
    source_population_digest: str
    rule_version: str = METRIC_POPULATION_CERTIFICATION_VERSION

    @property
    def certification_id(self) -> str:
        return f"metric-population-{canonical_digest(self)}"


def certify_metric_population(
    evidence: PopulationEvidence,
    window: CertifiedMetricWindow,
) -> MetricPopulationCertification:
    """Bind exact entity/field inclusion and exclusion to a certified source window."""

    if not isinstance(
        evidence, (MetricPopulationEvidence, AutomaticMetricPopulationEvidence)
    ):
        raise CertificationError("metric population requires exact reviewed evidence")
    if not isinstance(window, CertifiedMetricWindow):
        raise CertificationError("metric population requires a certified window proof")
    if window.state != "certified":
        raise CertificationError("metric window is not certified")
    if isinstance(evidence, AutomaticMetricPopulationEvidence):
        evidence.__post_init__()
        window.__post_init__()
        for source_year in window.source_years:
            source_year.__post_init__()
        for cohort in window.citation_cohorts:
            cohort.__post_init__()
        if (
            evidence.source_window_certification_id
            != window.certification.certification_id
            or evidence.assessed_at < window.cutoff
        ):
            raise CertificationError(
                "automatic metric population targets another window or cutoff"
            )
        _validate_automatic_population_field(evidence.field_id)
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
        if isinstance(evidence, AutomaticMetricPopulationEvidence):
            expected_reason = (
                None
                if expected_status == "included"
                else _AUTOMATIC_UNRESOLVED_REASON
                if expected_status == "unresolved"
                else _AUTOMATIC_EXCLUDED_REASON
            )
            if item.reason != expected_reason:
                raise CertificationError(
                    "automatic population reason does not derive from source evidence"
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
        if isinstance(evidence, AutomaticMetricPopulationEvidence) and (
            decision.evidence != source_projections[paper_id].occurrence_references
            or decision.reasons
            != (
                (_AUTOMATIC_UNRESOLVED_REASON,)
                if projection.status == "unresolved"
                else ()
            )
            or decision.supersedes_decision_id is not None
        ):
            raise CertificationError(
                "automatic population decision loses source provenance"
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
        rule_version=(
            AUTOMATIC_METRIC_POPULATION_VERSION
            if isinstance(evidence, AutomaticMetricPopulationEvidence)
            else METRIC_POPULATION_CERTIFICATION_VERSION
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
    evidence: PopulationEvidence,
    window: CertifiedMetricWindow,
) -> CertifiedMetricPopulation:
    return CertifiedMetricPopulation(
        certify_metric_population(evidence, window), window
    )


def derive_metric_population(
    window: CertifiedMetricWindow,
    *,
    entity_id: str,
    field_id: str,
    assessed_at: datetime,
) -> CertifiedMetricPopulation:
    """Derive every source-paper decision; never accept a favorable subset.

    Source windows still need their existing scientific certifications. This
    factory does not acquire, certify or modify their underlying facts.
    """
    if not isinstance(window, CertifiedMetricWindow) or window.state != "certified":
        raise CertificationError(
            "automatic population requires a certified source window"
        )
    if not isinstance(entity_id, str) or not entity_id.strip():
        raise CertificationError("automatic population entity identifier is invalid")
    _validate_automatic_population_field(field_id)
    context = window.certification
    projections: list[MetricPopulationProjection] = []
    decisions: list[EvidenceCertificationDecision] = []
    for year in window.source_years:
        for source in year.evidence.paper_projections:
            entity_weight = math.fsum(
                weight
                for entity_type, source_entity_id, weight in source.entity_shares
                if entity_type == context.entity_type and source_entity_id == entity_id
            )
            field_weight = dict(source.field_weights).get(field_id, 0.0)
            weight = entity_weight * field_weight
            unresolved = math.fsum(
                mass
                for entity_type, mass in source.unresolved_entity_mass
                if entity_type == context.entity_type
            )
            possible = (entity_weight + unresolved) * (
                field_weight + source.unmapped_field_mass
            )
            status: MetricPopulationStatus = (
                "included"
                if weight > 0
                else "unresolved"
                if possible > 0
                else "excluded"
            )
            projection = MetricPopulationProjection(
                paper_id=source.paper_id,
                publication_date=source.publication_date,
                entity_type=context.entity_type,
                entity_id=entity_id,
                field_id=field_id,
                status=status,
                entity_attribution_weight=entity_weight,
                field_weight=field_weight,
                attribution_weight=weight,
                coverage_weight=possible,
                reason=(
                    None
                    if status == "included"
                    else _AUTOMATIC_UNRESOLVED_REASON
                    if status == "unresolved"
                    else _AUTOMATIC_EXCLUDED_REASON
                ),
            )
            projections.append(projection)
            decisions.append(
                EvidenceCertificationDecision(
                    subject_type=METRIC_POPULATION_SUBJECT_TYPE,
                    subject_id=source.paper_id,
                    evidence_kind="provenance-completeness",
                    state=(
                        "insufficient_evidence"
                        if status == "unresolved"
                        else "certified"
                    ),
                    rule_version=CERTIFICATION_POLICY_VERSION,
                    dataset_version=context.dataset_version,
                    acquisition_scope=context.acquisition_scope,
                    evidence=source.occurrence_references,
                    certified_value_digest=projection.value_digest,
                    reasons=(
                        (_AUTOMATIC_UNRESOLVED_REASON,)
                        if status == "unresolved"
                        else ()
                    ),
                )
            )
    ordered = tuple(sorted(projections, key=lambda item: item.paper_id))
    category = (
        derive_category_universe(
            field_id=field_id,
            dataset_version=context.dataset_version,
            acquisition_scope=context.acquisition_scope,
            assessed_at=assessed_at,
        )
        if context.metric_id == "research_diversity"
        else None
    )
    return wrap_certified_metric_population(
        AutomaticMetricPopulationEvidence(
            metric_id=context.metric_id,
            terminal_year=context.terminal_year,
            dataset_version=context.dataset_version,
            acquisition_scope=context.acquisition_scope,
            entity_type=context.entity_type,
            entity_id=entity_id,
            field_id=field_id,
            source_manifest_digest=canonical_digest(ordered),
            source_window_certification_id=context.certification_id,
            source_year_certification_ids=context.source_year_certification_ids,
            projections=ordered,
            decisions=tuple(sorted(decisions, key=lambda item: item.subject_id)),
            assessed_at=assessed_at,
            category_universe=category,
        ),
        window,
    )


def _validate_automatic_population_field(field_id: str) -> None:
    if not PHYSICS_FIELD_ONTOLOGY_V1.contains(field_id):
        raise CertificationError("automatic population canonical field is invalid")
    if PHYSICS_FIELD_ONTOLOGY_V1.get(field_id).node_kind != "field":
        raise CertificationError(
            "metric populations require canonical leaf-field weights"
        )
