from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from ..certification import (
    CertificationError,
    CertifiedCitationCohort,
    CertifiedMetricPartition,
    canonical_digest,
)
from .calculators import (
    CitationReferenceCohort,
    MetricCalculationResult,
    MetricMetadataValue,
    MetricPartitionInput,
    calculate_activity_raw,
    calculate_connectivity,
    calculate_diversity,
    calculate_impact_raw,
    calculate_momentum_raw,
    citation_session_normalization_key,
    normalize_activity_results,
    normalize_impact_results,
    normalize_momentum_results,
)
from .thresholds import (
    METRIC_VALIDATION_THRESHOLDS_V1,
    MetricValidationThresholds,
)

if TYPE_CHECKING:
    from ..certification.measurement_windows import CertifiedSessionCitationCohort

ATLAS_SCALE_VERSION = "normalized-atlas-scale-v1"
type AtlasMetadata = dict[str, MetricMetadataValue]


@dataclass(frozen=True)
class NormalizationPopulationEvidence:
    """Reviewed exact entity universe for one field normalization cohort."""

    cohort_key: tuple[str, ...]
    entity_ids: tuple[str, ...]
    calculation_certification_digests: tuple[tuple[str, str], ...]
    source_manifest_digest: str
    review_state: str
    reviewed_by: str | None
    reviewed_at: datetime | None

    @property
    def content_digest(self) -> str:
        return _normalization_population_content_digest(
            self.cohort_key,
            self.entity_ids,
            self.calculation_certification_digests,
        )


@dataclass(frozen=True)
class CertifiedNormalizationPopulation:
    evidence: NormalizationPopulationEvidence
    certification_digest: str

    def __post_init__(self) -> None:
        _validate_normalization_population(self.evidence)
        if self.certification_digest != canonical_digest(self.evidence):
            raise CertificationError(
                "normalization population proof does not reconstruct"
            )


def _normalization_population_content_digest(
    cohort_key: tuple[str, ...],
    entity_ids: tuple[str, ...],
    calculation_certification_digests: tuple[tuple[str, str], ...],
) -> str:
    return canonical_digest(
        (
            cohort_key,
            tuple(sorted(entity_ids)),
            tuple(sorted(calculation_certification_digests)),
        )
    )


def _validate_normalization_population(
    evidence: NormalizationPopulationEvidence,
) -> None:
    from .automatic_normalization import (
        AutomaticNormalizationPopulationEvidence,
        validate_automatic_normalization_population,
    )

    if isinstance(evidence, AutomaticNormalizationPopulationEvidence):
        validate_automatic_normalization_population(evidence)
        return
    if len(evidence.cohort_key) != 15 or any(
        not item.strip() for item in evidence.cohort_key
    ):
        raise CertificationError("normalization population cohort key is invalid")
    if not evidence.entity_ids or len(set(evidence.entity_ids)) != len(
        evidence.entity_ids
    ):
        raise CertificationError(
            "normalization population entity ids must be non-empty and unique"
        )
    if any(not item.strip() for item in evidence.entity_ids):
        raise CertificationError("normalization population entity id is empty")
    calculation_digests = dict(evidence.calculation_certification_digests)
    if (
        len(calculation_digests) != len(evidence.calculation_certification_digests)
        or set(calculation_digests) != set(evidence.entity_ids)
        or any(
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            for digest in calculation_digests.values()
        )
    ):
        raise CertificationError(
            "normalization population must bind one calculation proof per entity"
        )
    if (
        evidence.review_state != "reviewed-approved"
        or not evidence.reviewed_by
        or not evidence.reviewed_by.strip()
        or evidence.reviewed_at is None
        or evidence.reviewed_at.tzinfo is None
        or evidence.reviewed_at.utcoffset() is None
    ):
        raise CertificationError(
            "normalization population requires dated reviewed approval"
        )
    if evidence.source_manifest_digest != evidence.content_digest:
        raise CertificationError(
            "normalization source manifest does not match reviewed population"
        )


def certify_normalization_population(
    evidence: NormalizationPopulationEvidence,
) -> CertifiedNormalizationPopulation:
    _validate_normalization_population(evidence)
    return CertifiedNormalizationPopulation(evidence, canonical_digest(evidence))


@dataclass(frozen=True)
class CertifiedMetricCalculation:
    """Presentation boundary binding a result to its evidence certification."""

    calculation: MetricCalculationResult
    partition: CertifiedMetricPartition[MetricPartitionInput]
    thresholds: MetricValidationThresholds
    citation_cohorts: tuple[
        CertifiedCitationCohort[CitationReferenceCohort]
        | CertifiedSessionCitationCohort,
        ...,
    ] = ()

    def __post_init__(self) -> None:
        from ..certification.measurement_windows import CertifiedSessionCitationCohort

        if not isinstance(self.calculation, MetricCalculationResult):
            raise CertificationError(
                "metric calculation proof requires an exact calculation result"
            )
        if not isinstance(self.partition, CertifiedMetricPartition):
            raise CertificationError(
                "metric calculation proof requires a certified partition"
            )
        if not isinstance(self.thresholds, MetricValidationThresholds):
            raise CertificationError(
                "metric calculation proof requires exact validation thresholds"
            )
        if any(
            not isinstance(
                item, (CertifiedCitationCohort, CertifiedSessionCitationCohort)
            )
            for item in self.citation_cohorts
        ):
            raise CertificationError(
                "metric calculation proof requires certified citation cohorts"
            )
        item = self.calculation
        if (
            item.threshold_version != self.thresholds.version
            or self.partition.certification.threshold_version != self.thresholds.version
        ):
            raise CertificationError(
                "metric result, partition, and threshold contract do not match"
            )
        calculators = {
            "research_activity_score": lambda: calculate_activity_raw(
                self.partition, self.thresholds
            ),
            "research_impact": lambda: calculate_impact_raw(
                self.partition, self.citation_cohorts, self.thresholds
            ),
            "collaboration": lambda: calculate_connectivity(
                self.partition, self.thresholds
            ),
            "research_diversity": lambda: calculate_diversity(
                self.partition, self.thresholds
            ),
            "momentum": lambda: calculate_momentum_raw(self.partition, self.thresholds),
        }
        calculator = calculators.get(item.metric_id)
        if calculator is None or calculator() != item:
            raise CertificationError(
                "metric result does not reconstruct from its certified partition"
            )


def bind_metric_calculation(
    calculation: MetricCalculationResult,
    partition: CertifiedMetricPartition[MetricPartitionInput],
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
    citation_cohorts: tuple[
        CertifiedCitationCohort[CitationReferenceCohort]
        | CertifiedSessionCitationCohort,
        ...,
    ] = (),
) -> CertifiedMetricCalculation:
    return CertifiedMetricCalculation(
        calculation, partition, thresholds, citation_cohorts
    )


@dataclass(frozen=True)
class AtlasScaleObservation:
    """Presentation-only view over a reconstructable scientific raw result."""

    calculation: MetricCalculationResult
    value: float | None
    scale_version: str
    metric_normalization_version: str
    certification_manifest_digest: str
    comparison_cohort: AtlasMetadata
    cutoff: str | None
    coverage: AtlasMetadata
    uncertainty_reasons: tuple[str, ...]
    certification_proof: object
    normalization_proofs: tuple[CertifiedMetricCalculation, ...]
    normalization_population_proof: CertifiedNormalizationPopulation | None
    thresholds: MetricValidationThresholds

    def __post_init__(self) -> None:
        if not isinstance(self.calculation, MetricCalculationResult):
            raise CertificationError(
                "Atlas observation requires an exact metric calculation"
            )
        if not isinstance(self.thresholds, MetricValidationThresholds):
            raise CertificationError(
                "Atlas observation requires exact validation thresholds"
            )
        if self.value is not None and (
            not math.isfinite(self.value) or not 0 <= self.value <= 100
        ):
            raise ValueError("Atlas presentation values must be finite within [0,100]")
        if self.value is not None and self.calculation.raw_value is None:
            raise ValueError(
                "an Atlas value cannot exist without its scientific raw value"
            )
        if self.value is None and not self.uncertainty_reasons:
            raise ValueError("a missing Atlas value must retain an explicit reason")
        if (
            self.scale_version != ATLAS_SCALE_VERSION
            or self.metric_normalization_version
            != self.calculation.normalization_version
            or self.comparison_cohort != _comparison_cohort(self.calculation)
            or self.coverage != _coverage_projection(self.calculation)
            or self.uncertainty_reasons != _uncertainty_projection(self.calculation)
        ):
            raise CertificationError(
                "Atlas presentation metadata does not reconstruct from calculation"
            )
        from .aggregation import CertifiedPhysicsAggregation

        if isinstance(self.certification_proof, CertifiedMetricCalculation):
            if not self.normalization_proofs:
                raise CertificationError(
                    "field Atlas observations require normalization cohort proofs"
                )
            if any(
                not isinstance(item, CertifiedMetricCalculation)
                for item in self.normalization_proofs
            ):
                raise CertificationError(
                    "Atlas normalization cohort requires certified calculations"
                )
            if any(
                item.thresholds != self.thresholds for item in self.normalization_proofs
            ):
                raise CertificationError(
                    "Atlas normalization proof uses incompatible thresholds"
                )
            if any(
                _normalization_cohort_key(item.calculation)
                != _normalization_cohort_key(self.certification_proof.calculation)
                for item in self.normalization_proofs
            ):
                raise CertificationError(
                    "Atlas normalization proof mixes comparison cohorts"
                )
            population = self.normalization_population_proof
            if not isinstance(population, CertifiedNormalizationPopulation) or (
                population.evidence.cohort_key
                != _normalization_cohort_key(self.certification_proof.calculation)
                or set(population.evidence.entity_ids)
                != {item.calculation.entity_id for item in self.normalization_proofs}
                or dict(population.evidence.calculation_certification_digests)
                != {
                    item.calculation.entity_id: (
                        item.calculation.certification_manifest_digest
                    )
                    for item in self.normalization_proofs
                }
            ):
                raise CertificationError(
                    "Atlas normalization cohort differs from its population proof"
                )
            normalized = _normalize_results(
                tuple(item.calculation for item in self.normalization_proofs),
                self.thresholds,
            )
            proof_key = _calculation_key(self.certification_proof.calculation)
            matching = tuple(
                item for item in normalized if _calculation_key(item) == proof_key
            )
            if len(matching) != 1 or matching[0] != self.calculation:
                raise CertificationError(
                    "Atlas value does not reconstruct from its certified cohort"
                )
        elif isinstance(self.certification_proof, CertifiedPhysicsAggregation):
            if self.normalization_proofs or self.normalization_population_proof:
                raise CertificationError(
                    "Physics aggregation must retain its own field proof"
                )
            if self.certification_proof.calculation != self.calculation:
                raise CertificationError(
                    "Atlas Physics value differs from its aggregation proof"
                )
        else:
            raise CertificationError("Atlas observation lacks certification proof")
        if (
            self.value != self.calculation.normalized_value
            or self.certification_manifest_digest
            != self.calculation.certification_manifest_digest
            or self.cutoff != _presentation_cutoff(self.calculation)
        ):
            raise CertificationError(
                "Atlas presentation fields differ from the certified calculation"
            )


def _presentation_cutoff(result: MetricCalculationResult) -> str | None:
    # A measurement session has an interval, not an atomic citation cutoff.
    # Its calculation still retains the separate dataset evaluation horizon.
    return (
        None if citation_session_normalization_key(result) else result.evidence_cutoff
    )


def _calculation_key(result: MetricCalculationResult) -> tuple[str, ...]:
    return (
        result.metric_id,
        result.entity_type,
        result.entity_id,
        result.field_id,
        result.period,
        result.certification_manifest_digest,
    )


def _normalization_cohort_key(result: MetricCalculationResult) -> tuple[str, ...]:
    return (
        result.metric_id,
        result.entity_type,
        result.field_id,
        result.period,
        result.metric_definition_version,
        result.algorithm_version,
        result.normalization_version,
        result.dataset_version,
        result.acquisition_scope,
        result.evidence_cutoff,
        result.attribution_policy_version,
        result.ontology_version,
        result.mapping_policy_version,
        result.citation_policy_version,
        result.threshold_version,
    ) + citation_session_normalization_key(result)


def _comparison_cohort(result: MetricCalculationResult) -> AtlasMetadata:
    metadata: AtlasMetadata = {
        "entity_type": result.entity_type,
        "field_id": result.field_id,
        "period": result.period,
        "dataset_version": result.dataset_version,
        "acquisition_scope": result.acquisition_scope,
        "threshold_version": result.threshold_version,
        "cohort_size": result.normalization_parameters.get("cohort_size"),
    }
    session_key = citation_session_normalization_key(result)
    if session_key:
        metadata.update(
            {
                "citation_session_id": session_key[0],
                "citation_measurement_started_at": session_key[1],
                "citation_measurement_ended_at": session_key[2],
                "citation_measurement_semantics": "retrospective-measurement-window",
            }
        )
    return metadata


def _coverage_projection(result: MetricCalculationResult) -> AtlasMetadata:
    return {
        key: value
        for key, value in result.components.items()
        if key.endswith("_coverage")
    }


def _uncertainty_projection(result: MetricCalculationResult) -> tuple[str, ...]:
    if result.missing_reasons:
        return result.missing_reasons
    if result.normalized_value is None:
        return ("metric-specific Atlas normalization is unavailable",)
    return ()


def _normalize_results(
    results: tuple[MetricCalculationResult, ...],
    thresholds: MetricValidationThresholds,
) -> tuple[MetricCalculationResult, ...]:
    output = list(results)
    normalizers = {
        "research_activity_score": normalize_activity_results,
        "research_impact": normalize_impact_results,
        "momentum": normalize_momentum_results,
    }
    supported = {
        "research_activity_score",
        "research_impact",
        "collaboration",
        "research_diversity",
        "momentum",
    }
    unknown = {item.metric_id for item in results} - supported
    if unknown:
        raise ValueError(f"Atlas scale received unsupported metrics: {sorted(unknown)}")
    for metric_id, normalizer in normalizers.items():
        indices = [
            index for index, item in enumerate(results) if item.metric_id == metric_id
        ]
        normalized = normalizer(tuple(results[index] for index in indices), thresholds)
        for index, item in zip(indices, normalized, strict=True):
            output[index] = item
    return tuple(output)


def apply_atlas_scale(
    results: tuple[object, ...],
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
    *,
    normalization_populations: tuple[CertifiedNormalizationPopulation, ...] = (),
) -> tuple[AtlasScaleObservation, ...]:
    """Apply v1 metric transforms without changing or discarding raw values."""

    from .aggregation import CertifiedPhysicsAggregation

    if any(
        not isinstance(item, (CertifiedMetricCalculation, CertifiedPhysicsAggregation))
        for item in results
    ):
        raise CertificationError(
            "raw metric results cannot reach Atlas Scale; bind certification first"
        )
    certified_results = tuple(
        item
        for item in results
        if isinstance(item, (CertifiedMetricCalculation, CertifiedPhysicsAggregation))
    )
    if any(item.thresholds != thresholds for item in certified_results):
        raise CertificationError(
            "Atlas Scale thresholds must match every certified calculation"
        )
    population_by_key = {
        item.evidence.cohort_key: item for item in normalization_populations
    }
    if len(population_by_key) != len(normalization_populations):
        raise CertificationError("normalization population proofs are duplicated")
    field_indices = tuple(
        index
        for index, item in enumerate(certified_results)
        if isinstance(item, CertifiedMetricCalculation)
    )
    normalized_fields = _normalize_results(
        tuple(certified_results[index].calculation for index in field_indices),
        thresholds,
    )
    normalized_by_index = dict(zip(field_indices, normalized_fields, strict=True))
    normalized = tuple(
        normalized_by_index.get(index, item.calculation)
        for index, item in enumerate(certified_results)
    )
    output: list[AtlasScaleObservation] = []
    for index, item in enumerate(normalized):
        cohort = _comparison_cohort(item)
        coverage = _coverage_projection(item)
        reasons = _uncertainty_projection(item)
        proof_item = certified_results[index]
        proof_cohort = (
            tuple(
                candidate
                for candidate in certified_results
                if isinstance(candidate, CertifiedMetricCalculation)
                and _normalization_cohort_key(candidate.calculation)
                == _normalization_cohort_key(proof_item.calculation)
            )
            if isinstance(proof_item, CertifiedMetricCalculation)
            else ()
        )
        population_proof = (
            population_by_key.get(_normalization_cohort_key(proof_item.calculation))
            if isinstance(proof_item, CertifiedMetricCalculation)
            else None
        )
        if isinstance(proof_item, CertifiedMetricCalculation) and (
            population_proof is None
            or set(population_proof.evidence.entity_ids)
            != {candidate.calculation.entity_id for candidate in proof_cohort}
            or dict(population_proof.evidence.calculation_certification_digests)
            != {
                candidate.calculation.entity_id: (
                    candidate.calculation.certification_manifest_digest
                )
                for candidate in proof_cohort
            }
        ):
            raise CertificationError(
                "Atlas Scale requires the exact reviewed normalization population"
            )
        output.append(
            AtlasScaleObservation(
                calculation=item,
                value=item.normalized_value,
                scale_version=ATLAS_SCALE_VERSION,
                metric_normalization_version=item.normalization_version,
                certification_manifest_digest=item.certification_manifest_digest,
                comparison_cohort=cohort,
                cutoff=_presentation_cutoff(item),
                coverage=coverage,
                uncertainty_reasons=reasons,
                certification_proof=proof_item,
                normalization_proofs=proof_cohort,
                normalization_population_proof=population_proof,
                thresholds=thresholds,
            )
        )
    return tuple(output)
