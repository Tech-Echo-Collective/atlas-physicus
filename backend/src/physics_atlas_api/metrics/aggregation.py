import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import cast

from ..certification import CertificationError, canonical_digest
from ..fields import PHYSICS_FIELD_ONTOLOGY_V1, PHYSICS_FIELD_ONTOLOGY_VERSION
from ..fields.ontology import FieldDefinition
from .calculators import MetricCalculationResult, citation_session_normalization_key
from .presentation import AtlasScaleObservation
from .thresholds import (
    METRIC_VALIDATION_THRESHOLDS_V1,
    MetricValidationThresholds,
)

AUTOMATIC_FIELD_POPULATION_VERSION = "automatic-physics-field-population-v1"
ONTOLOGY_BRANCH_AGGREGATION_VERSION = "ontology-branch-equal-field-coverage-aware-v1"


@dataclass(frozen=True)
class FieldPopulationEvidence:
    """Reviewed, content-addressed field universe for one Physics aggregation."""

    entity_id: str
    metric_id: str
    period: str
    dataset_version: str
    acquisition_scope: str
    ontology_version: str
    field_weights: tuple[tuple[str, float], ...]
    source_manifest_digest: str
    review_state: str
    reviewed_by: str | None
    reviewed_at: datetime | None

    @property
    def content_digest(self) -> str:
        return canonical_digest(
            (
                self.entity_id,
                self.metric_id,
                self.period,
                self.dataset_version,
                self.acquisition_scope,
                self.ontology_version,
                tuple(sorted(self.field_weights)),
            )
        )


@dataclass(frozen=True)
class AutomaticFieldPopulationEvidence(FieldPopulationEvidence):
    """Exact ontology catalog, bound to certified inputs; not coverage approval."""

    observations: tuple[AtlasScaleObservation, ...]
    automatic_rule_version: str = AUTOMATIC_FIELD_POPULATION_VERSION

    @property
    def content_digest(self) -> str:
        return canonical_digest(
            (
                super().content_digest,
                self.automatic_rule_version,
                _field_observation_bindings(self.observations),
            )
        )


@dataclass(frozen=True, kw_only=True)
class OntologyBranchPopulationEvidence(AutomaticFieldPopulationEvidence):
    """A named, fixed ontology branch, never a caller-selected leaf subset."""

    branch_id: str
    automatic_rule_version: str = ONTOLOGY_BRANCH_AGGREGATION_VERSION

    @property
    def content_digest(self) -> str:
        return canonical_digest((super().content_digest, self.branch_id))


def _branch_leaf_ids(branch_id: str) -> tuple[str, ...]:
    ontology = PHYSICS_FIELD_ONTOLOGY_V1
    if (
        not ontology.contains(branch_id)
        or ontology.get(branch_id).node_kind != "branch"
    ):
        raise CertificationError(
            "aggregation target must be an existing ontology branch"
        )
    return tuple(
        sorted(
            item.id
            for item in ontology.fields
            if item.node_kind == "field"
            and branch_id
            in {ancestor.id for ancestor in ontology.ancestors_of(item.id)}
        )
    )


def derive_ontology_branch_population(
    branch: FieldDefinition,
    observations: tuple[AtlasScaleObservation, ...],
) -> OntologyBranchPopulationEvidence:
    """Bind existing leaf-normalized observations to their named branch catalog."""
    if (
        not isinstance(branch, FieldDefinition)
        or not PHYSICS_FIELD_ONTOLOGY_V1.contains(branch.id)
        or branch != PHYSICS_FIELD_ONTOLOGY_V1.get(branch.id)
    ):
        raise CertificationError("branch definition must match the frozen ontology")
    leaves = _branch_leaf_ids(branch.id)
    if not observations or any(
        not isinstance(item, AtlasScaleObservation) for item in observations
    ):
        raise CertificationError(
            "branch aggregation requires certified Atlas observations"
        )
    baseline = observations[0].calculation
    evidence = OntologyBranchPopulationEvidence(
        entity_id=baseline.entity_id,
        metric_id=baseline.metric_id,
        period=baseline.period,
        dataset_version=baseline.dataset_version,
        acquisition_scope=baseline.acquisition_scope,
        ontology_version=PHYSICS_FIELD_ONTOLOGY_VERSION,
        field_weights=tuple((field_id, 1.0) for field_id in leaves),
        source_manifest_digest="0" * 64,
        review_state="automatic-evidence-derived",
        reviewed_by=None,
        reviewed_at=None,
        branch_id=branch.id,
        observations=tuple(
            sorted(observations, key=lambda item: item.calculation.field_id)
        ),
    )
    evidence = replace(evidence, source_manifest_digest=evidence.content_digest)
    _validate_field_population(evidence)
    return evidence


def _field_observation_bindings(
    observations: tuple[AtlasScaleObservation, ...],
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (
                item.calculation.field_id,
                item.certification_manifest_digest,
                canonical_digest(item.calculation),
            )
            for item in observations
        )
    )


def derive_automatic_field_population(
    observations: tuple[AtlasScaleObservation, ...],
) -> AutomaticFieldPopulationEvidence:
    """Freeze the existing full Physics catalog; absent fields stay missing."""
    if not observations or any(
        not isinstance(item, AtlasScaleObservation) for item in observations
    ):
        raise CertificationError(
            "automatic field population requires certified Atlas observations"
        )
    baseline = observations[0].calculation
    evidence = AutomaticFieldPopulationEvidence(
        entity_id=baseline.entity_id,
        metric_id=baseline.metric_id,
        period=baseline.period,
        dataset_version=baseline.dataset_version,
        acquisition_scope=baseline.acquisition_scope,
        ontology_version=PHYSICS_FIELD_ONTOLOGY_VERSION,
        field_weights=tuple(
            sorted(
                (item.id, 1.0)
                for item in PHYSICS_FIELD_ONTOLOGY_V1.fields
                if item.node_kind == "field"
            )
        ),
        source_manifest_digest="0" * 64,
        review_state="automatic-evidence-derived",
        reviewed_by=None,
        reviewed_at=None,
        observations=tuple(
            sorted(observations, key=lambda item: item.calculation.field_id)
        ),
    )
    evidence = replace(evidence, source_manifest_digest=evidence.content_digest)
    _validate_field_population(evidence)
    return evidence


def _validate_automatic_field_population(
    evidence: AutomaticFieldPopulationEvidence,
) -> None:
    from .presentation import CertifiedMetricCalculation

    if (
        evidence.automatic_rule_version
        != (
            ONTOLOGY_BRANCH_AGGREGATION_VERSION
            if isinstance(evidence, OntologyBranchPopulationEvidence)
            else AUTOMATIC_FIELD_POPULATION_VERSION
        )
        or evidence.review_state != "automatic-evidence-derived"
        or evidence.reviewed_by is not None
        or evidence.reviewed_at is not None
        or not evidence.observations
    ):
        raise CertificationError(
            "automatic field population rule or authority is invalid"
        )
    keys: set[tuple[str, ...]] = set()
    observed_fields: set[str] = set()
    for observation in evidence.observations:
        if not isinstance(observation, AtlasScaleObservation) or not isinstance(
            observation.certification_proof, CertifiedMetricCalculation
        ):
            raise CertificationError(
                "automatic population requires field-level certified observations"
            )
        observation.certification_proof.__post_init__()
        observation.__post_init__()
        result = observation.calculation
        if result.field_id in observed_fields:
            raise CertificationError(
                "automatic field population contains duplicate fields"
            )
        observed_fields.add(result.field_id)
        keys.add(
            (
                result.entity_type,
                result.entity_id,
                result.metric_id,
                result.period,
                result.dataset_version,
                result.acquisition_scope,
                result.ontology_version,
                result.metric_definition_version,
                result.algorithm_version,
                result.normalization_version,
                result.evidence_cutoff,
                result.threshold_version,
                result.attribution_policy_version,
                result.mapping_policy_version,
                result.citation_policy_version,
            )
            + citation_session_normalization_key(result)
        )
    first = evidence.observations[0].calculation
    if isinstance(
        evidence, OntologyBranchPopulationEvidence
    ) and first.metric_id not in {
        "research_activity_score",
        "research_impact",
        "collaboration",
        "momentum",
    }:
        raise CertificationError(
            "branch averaging does not replace within-branch Diversity"
        )
    if (
        len(keys) != 1
        or (
            evidence.entity_id,
            evidence.metric_id,
            evidence.period,
            evidence.dataset_version,
            evidence.acquisition_scope,
            evidence.ontology_version,
        )
        != (
            first.entity_id,
            first.metric_id,
            first.period,
            first.dataset_version,
            first.acquisition_scope,
            first.ontology_version,
        )
        or not observed_fields.issubset(dict(evidence.field_weights))
    ):
        raise CertificationError(
            "automatic field population target or observation lineage differs"
        )


@dataclass(frozen=True)
class CertifiedFieldPopulation:
    evidence: FieldPopulationEvidence
    certification_digest: str

    def __post_init__(self) -> None:
        _validate_field_population(self.evidence)
        if self.certification_digest != canonical_digest(self.evidence):
            raise CertificationError("field population proof does not reconstruct")


def _validate_field_population(evidence: FieldPopulationEvidence) -> None:
    identifiers = (
        evidence.entity_id,
        evidence.metric_id,
        evidence.period,
        evidence.dataset_version,
        evidence.acquisition_scope,
        evidence.ontology_version,
    )
    if any(not item.strip() for item in identifiers):
        raise CertificationError("field population identifiers must be non-empty")
    if isinstance(evidence, AutomaticFieldPopulationEvidence):
        _validate_automatic_field_population(evidence)
    elif (
        evidence.review_state != "reviewed-approved"
        or not evidence.reviewed_by
        or not evidence.reviewed_by.strip()
        or evidence.reviewed_at is None
        or evidence.reviewed_at.tzinfo is None
        or evidence.reviewed_at.utcoffset() is None
    ):
        raise CertificationError("field population requires dated reviewed approval")
    if evidence.ontology_version != PHYSICS_FIELD_ONTOLOGY_VERSION:
        raise CertificationError("field population ontology is stale")
    fields = dict(evidence.field_weights)
    expected_fields = (
        set(_branch_leaf_ids(evidence.branch_id))
        if isinstance(evidence, OntologyBranchPopulationEvidence)
        else {
            item.id
            for item in PHYSICS_FIELD_ONTOLOGY_V1.fields
            if item.node_kind == "field"
        }
    )
    if (
        not fields
        or len(fields) != len(evidence.field_weights)
        or set(fields) != expected_fields
        or any(
            not PHYSICS_FIELD_ONTOLOGY_V1.contains(field_id)
            or not math.isfinite(weight)
            or not math.isclose(weight, 1.0, rel_tol=0.0, abs_tol=1e-12)
            for field_id, weight in fields.items()
        )
    ):
        raise CertificationError(
            "field population must cover the exact Physics leaf-field universe"
        )
    if evidence.source_manifest_digest != evidence.content_digest:
        raise CertificationError(
            "field population source manifest does not match reviewed content"
        )


def certify_field_population(
    evidence: FieldPopulationEvidence,
) -> CertifiedFieldPopulation:
    _validate_field_population(evidence)
    return CertifiedFieldPopulation(evidence, canonical_digest(evidence))


def _validate_weights(
    field_evidence_weights: Mapping[tuple[str, str], float],
) -> None:
    for key, value in field_evidence_weights.items():
        if not all(part.strip() for part in key):
            raise ValueError("field evidence keys must be non-empty")
        if not math.isfinite(value) or value < 0:
            raise ValueError("field evidence weights must be finite and nonnegative")


def _aggregate_group(
    results: tuple[MetricCalculationResult, ...],
    field_evidence_weights: Mapping[tuple[str, str], float],
    thresholds: MetricValidationThresholds,
) -> MetricCalculationResult:
    if not results:
        raise ValueError("Physics aggregation requires field calculations")
    entity_id = results[0].entity_id
    by_field = {result.field_id: result for result in results}
    if len(by_field) != len(results):
        raise ValueError("a Physics aggregation may contain one result per field")
    version_tuples = {
        (
            result.entity_type,
            result.entity_id,
            result.metric_id,
            result.period,
            result.metric_definition_version,
            result.algorithm_version,
            result.normalization_version,
            result.threshold_version,
            result.dataset_version,
            result.acquisition_scope,
            result.evidence_cutoff,
            result.attribution_policy_version,
            result.ontology_version,
            result.mapping_policy_version,
            result.citation_policy_version,
        )
        + citation_session_normalization_key(result)
        for result in results
    }
    if len(version_tuples) != 1:
        raise ValueError("Physics aggregation inputs must use identical versions")

    expected = {
        field_id: weight
        for (expected_entity_id, field_id), weight in field_evidence_weights.items()
        if expected_entity_id == entity_id and weight > 0
    }
    if set(by_field) - set(expected):
        raise ValueError("Physics aggregation contains a field outside its proof")
    available = {
        field_id: result
        for field_id, result in by_field.items()
        if field_id in expected and result.eligible_for_observation
    }
    coverage = len(available) / len(expected) if expected else None
    reasons: tuple[str, ...] = ()
    score: float | None = None
    if not expected:
        reasons = ("no expected canonical field evidence is available",)
    elif coverage is None or coverage < thresholds.coverage.field_attribution:
        reasons = ("Physics-wide field evidence coverage is below the v1 threshold",)
    elif not available:
        reasons = ("no eligible field-normalized observations are available",)
    else:
        score = math.fsum(
            result.normalized_value or 0.0 for result in available.values()
        ) / len(available)

    baseline = results[0]
    session_key = citation_session_normalization_key(baseline)
    digest_payload = "|".join(
        sorted(result.input_manifest_digest for result in results)
    )
    digest = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()
    certification_digest = canonical_digest(
        tuple(sorted(result.certification_manifest_digest for result in results))
    )
    return replace(
        baseline,
        field_id="physics",
        raw_value=score,
        raw_unit="equal-field mean of field-normalized observations",
        normalized_value=score,
        components={
            "included_field_ids": ",".join(sorted(available)),
            "expected_field_ids": ",".join(sorted(expected)),
            "included_field_count": len(available),
            "expected_field_count": len(expected),
            "field_evidence_coverage": coverage,
            "publication_volume_used_as_final_weight": False,
            **(
                {
                    "citation_cutoff": None,
                    "citation_session_id": session_key[0],
                    "citation_measurement_started_at": session_key[1],
                    "citation_measurement_ended_at": session_key[2],
                    "citation_measurement_semantics": (
                        "retrospective-measurement-window"
                    ),
                }
                if session_key
                else {}
            ),
        },
        normalization_parameters={
            "physics_aggregation_version": ("physics-field-balanced-coverage-aware-v1"),
            "field_weighting": "equal-across-eligible-fields",
            "coverage_threshold": thresholds.coverage.field_attribution,
            "threshold_version": thresholds.version,
        },
        input_count=sum(result.input_count for result in available.values()),
        input_manifest_digest=digest,
        certification_manifest_digest=certification_digest,
        missing_reasons=reasons,
    )


def _aggregate_branch_group(
    results: tuple[MetricCalculationResult, ...],
    evidence: OntologyBranchPopulationEvidence,
    thresholds: MetricValidationThresholds,
) -> MetricCalculationResult:
    """Same arithmetic/coverage gate, with an explicit branch—not Physics—target."""
    result = _aggregate_group(
        results,
        {
            (evidence.entity_id, field_id): weight
            for field_id, weight in evidence.field_weights
        },
        thresholds,
    )
    parameters = dict(result.normalization_parameters)
    parameters.pop("physics_aggregation_version", None)
    parameters.update(
        {
            "ontology_branch_aggregation_version": ONTOLOGY_BRANCH_AGGREGATION_VERSION,
            "aggregation_target_kind": "ontology-branch",
            "aggregation_target_id": evidence.branch_id,
            "aggregation_ontology_version": evidence.ontology_version,
        }
    )
    return replace(
        result,
        field_id=evidence.branch_id,
        normalization_parameters=parameters,
        # Preserve the reason while avoiding a false Physics-wide coverage claim.
        missing_reasons=tuple(
            reason.replace("Physics-wide", "Ontology-branch")
            for reason in result.missing_reasons
        ),
    )


@dataclass(frozen=True)
class CertifiedPhysicsAggregation:
    """A Physics-domain result reconstructable from certified field results."""

    calculation: MetricCalculationResult
    field_observations: tuple[AtlasScaleObservation, ...]
    field_population_proof: CertifiedFieldPopulation
    thresholds: MetricValidationThresholds
    proof_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.calculation, MetricCalculationResult):
            raise CertificationError(
                "Physics aggregation requires an exact calculation result"
            )
        if any(
            not isinstance(item, AtlasScaleObservation)
            for item in self.field_observations
        ):
            raise CertificationError(
                "Physics aggregation requires certified Atlas field observations"
            )
        if not isinstance(self.field_population_proof, CertifiedFieldPopulation):
            raise CertificationError(
                "Physics aggregation requires a certified field-population proof"
            )
        if not isinstance(self.thresholds, MetricValidationThresholds):
            raise CertificationError(
                "Physics aggregation requires exact validation thresholds"
            )
        if not self.field_observations:
            raise CertificationError(
                "Physics aggregation requires certified field calculations"
            )
        if any(item.thresholds != self.thresholds for item in self.field_observations):
            raise CertificationError(
                "Physics aggregation threshold proof differs from field inputs"
            )
        evidence = self.field_population_proof.evidence
        is_branch = isinstance(evidence, OntologyBranchPopulationEvidence)
        if is_branch != isinstance(self, CertifiedOntologyBranchAggregation):
            raise CertificationError("branch population cannot be relabeled as Physics")
        if isinstance(evidence, AutomaticFieldPopulationEvidence):
            _validate_field_population(evidence)
            if _field_observation_bindings(
                self.field_observations
            ) != _field_observation_bindings(evidence.observations):
                raise CertificationError(
                    "Physics aggregation differs from automatic population inputs"
                )
        baseline = self.field_observations[0].calculation
        if (
            evidence.entity_id != baseline.entity_id
            or evidence.metric_id != baseline.metric_id
            or evidence.period != baseline.period
            or evidence.dataset_version != baseline.dataset_version
            or evidence.acquisition_scope != baseline.acquisition_scope
        ):
            raise CertificationError(
                "Physics field-population proof targets another calculation"
            )
        weights = {
            (evidence.entity_id, field_id): weight
            for field_id, weight in evidence.field_weights
        }
        expected = (
            _aggregate_branch_group(
                tuple(item.calculation for item in self.field_observations),
                evidence,
                self.thresholds,
            )
            if isinstance(evidence, OntologyBranchPopulationEvidence)
            else _aggregate_group(
                tuple(item.calculation for item in self.field_observations),
                weights,
                self.thresholds,
            )
        )
        if expected != self.calculation:
            raise CertificationError(
                "Physics aggregation does not reconstruct from certified fields"
            )
        expected_digest = canonical_digest(
            (
                tuple(
                    item.calculation.certification_manifest_digest
                    for item in self.field_observations
                ),
                self.field_population_proof,
                self.thresholds,
                self.calculation,
            )
        )
        if expected_digest != self.proof_digest:
            raise CertificationError("Physics aggregation proof digest differs")


@dataclass(frozen=True)
class CertifiedOntologyBranchAggregation(CertifiedPhysicsAggregation):
    """Typed scoped aggregation; inherited proof reconstruction enforces target."""


def aggregate_physics_wide(
    field_results: Sequence[AtlasScaleObservation],
    field_populations: Sequence[CertifiedFieldPopulation],
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
) -> tuple[CertifiedPhysicsAggregation, ...]:
    """Aggregate certified field-normalized results without volume weighting."""
    return _aggregate_certified_fields(
        field_results, field_populations, thresholds, branch_only=False
    )


def aggregate_ontology_branch(
    field_results: Sequence[AtlasScaleObservation],
    field_populations: Sequence[CertifiedFieldPopulation],
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
) -> tuple[CertifiedOntologyBranchAggregation, ...]:
    """Aggregate only fixed branch catalogs; never claim broad Physics coverage."""
    return tuple(
        cast(CertifiedOntologyBranchAggregation, item)
        for item in _aggregate_certified_fields(
            field_results, field_populations, thresholds, branch_only=True
        )
    )


def _aggregate_certified_fields(
    field_results: Sequence[AtlasScaleObservation],
    field_populations: Sequence[CertifiedFieldPopulation],
    thresholds: MetricValidationThresholds,
    *,
    branch_only: bool,
) -> tuple[CertifiedPhysicsAggregation, ...]:

    if any(
        not isinstance(item, CertifiedFieldPopulation) for item in field_populations
    ):
        raise CertificationError(
            "Physics aggregation requires certified field-population proofs"
        )
    if any(
        isinstance(item.evidence, OntologyBranchPopulationEvidence) != branch_only
        for item in field_populations
    ):
        raise CertificationError(
            "Physics and ontology-branch population contracts cannot mix"
        )
    populations = {
        (
            item.evidence.entity_id,
            item.evidence.metric_id,
            item.evidence.period,
            item.evidence.dataset_version,
            item.evidence.acquisition_scope,
        ): item
        for item in field_populations
    }
    if len(populations) != len(field_populations):
        raise CertificationError("Physics field-population proofs are duplicated")
    if any(not isinstance(item, AtlasScaleObservation) for item in field_results):
        raise CertificationError(
            "raw field results cannot reach Physics aggregation; "
            "apply Atlas Scale first"
        )
    if any(item.thresholds != thresholds for item in field_results):
        raise CertificationError(
            "Physics aggregation thresholds must match every field result"
        )
    grouped: dict[tuple[str, str, str, str], list[AtlasScaleObservation]] = defaultdict(
        list
    )
    for certified in field_results:
        result = certified.calculation
        grouped[
            (result.entity_type, result.entity_id, result.metric_id, result.period)
        ].append(certified)

    aggregated: list[CertifiedPhysicsAggregation] = []
    for group in grouped.values():
        field_observations = tuple(
            sorted(group, key=lambda item: item.calculation.field_id)
        )
        from .presentation import CertifiedMetricCalculation

        if any(
            not isinstance(item.certification_proof, CertifiedMetricCalculation)
            for item in field_observations
        ):
            raise CertificationError(
                "Physics aggregation requires field-level calculation proofs"
            )
        paper_mass: dict[str, float] = defaultdict(float)
        for observation in field_observations:
            proof = observation.certification_proof
            assert isinstance(proof, CertifiedMetricCalculation)
            for paper in proof.partition.partition.papers:
                paper_mass[paper.paper_id] += paper.attribution_weight
        if any(
            mass > 1 and not math.isclose(mass, 1.0, rel_tol=0.0, abs_tol=1e-12)
            for mass in paper_mass.values()
        ):
            raise CertificationError(
                "Physics aggregation violates cross-field attribution conservation"
            )
        baseline = field_observations[0].calculation
        population_key = (
            baseline.entity_id,
            baseline.metric_id,
            baseline.period,
            baseline.dataset_version,
            baseline.acquisition_scope,
        )
        population = populations.get(population_key)
        if population is None:
            raise CertificationError(
                "Physics aggregation lacks the reviewed field universe"
            )
        evidence = population.evidence
        field_evidence_weights = {
            (evidence.entity_id, field_id): weight
            for field_id, weight in evidence.field_weights
        }
        _validate_weights(field_evidence_weights)
        calculation = (
            _aggregate_branch_group(
                tuple(item.calculation for item in field_observations),
                evidence,
                thresholds,
            )
            if isinstance(evidence, OntologyBranchPopulationEvidence)
            else _aggregate_group(
                tuple(item.calculation for item in field_observations),
                field_evidence_weights,
                thresholds,
            )
        )
        proof_digest = canonical_digest(
            (
                tuple(
                    item.calculation.certification_manifest_digest
                    for item in field_observations
                ),
                population,
                thresholds,
                calculation,
            )
        )
        aggregation_type = (
            CertifiedOntologyBranchAggregation
            if branch_only
            else CertifiedPhysicsAggregation
        )
        aggregated.append(
            aggregation_type(
                calculation=calculation,
                field_observations=field_observations,
                field_population_proof=population,
                thresholds=thresholds,
                proof_digest=proof_digest,
            )
        )
    return tuple(aggregated)
