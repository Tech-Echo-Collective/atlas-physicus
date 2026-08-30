import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace

from .calculators import MetricCalculationResult
from .thresholds import (
    METRIC_VALIDATION_THRESHOLDS_V1,
    MetricValidationThresholds,
)


def aggregate_physics_wide(
    field_results: Sequence[MetricCalculationResult],
    field_evidence_weights: Mapping[tuple[str, str], float],
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
) -> tuple[MetricCalculationResult, ...]:
    """Aggregate already normalized fields without publication-volume weighting.

    Evidence weights decide only whether enough of an entity's expected field
    evidence is represented. Every included field then receives equal weight,
    preventing a large field from dominating the Physics-domain value merely
    because it publishes more papers.
    """
    for key, value in field_evidence_weights.items():
        if not all(part.strip() for part in key):
            raise ValueError("field evidence keys must be non-empty")
        if not math.isfinite(value) or value < 0:
            raise ValueError("field evidence weights must be finite and nonnegative")

    grouped: dict[tuple[str, str, str, str], list[MetricCalculationResult]] = (
        defaultdict(list)
    )
    for result in field_results:
        grouped[
            (result.entity_type, result.entity_id, result.metric_id, result.period)
        ].append(result)

    aggregated: list[MetricCalculationResult] = []
    for (_, entity_id, _, _), results in sorted(grouped.items()):
        by_field = {result.field_id: result for result in results}
        if len(by_field) != len(results):
            raise ValueError("a Physics aggregation may contain one result per field")
        version_tuples = {
            (
                result.metric_definition_version,
                result.algorithm_version,
                result.normalization_version,
                result.threshold_version,
                result.dataset_version,
                result.acquisition_scope,
                result.attribution_policy_version,
                result.ontology_version,
                result.mapping_policy_version,
                result.citation_policy_version,
            )
            for result in results
        }
        if len(version_tuples) != 1:
            raise ValueError("Physics aggregation inputs must use identical versions")

        expected = {
            field_id: weight
            for (expected_entity_id, field_id), weight in field_evidence_weights.items()
            if expected_entity_id == entity_id and weight > 0
        }
        expected_weight = math.fsum(expected.values())
        available = {
            field_id: result
            for field_id, result in by_field.items()
            if field_id in expected and result.eligible_for_observation
        }
        available_weight = math.fsum(expected[field_id] for field_id in available)
        coverage = available_weight / expected_weight if expected_weight > 0 else None
        reasons: tuple[str, ...] = ()
        score: float | None = None
        if not expected:
            reasons = ("no expected canonical field evidence is available",)
        elif coverage is None or coverage < thresholds.coverage.field_attribution:
            reasons = (
                "Physics-wide field evidence coverage is below the v1 threshold",
            )
        elif not available:
            reasons = ("no eligible field-normalized observations are available",)
        else:
            score = math.fsum(
                result.normalized_value or 0.0 for result in available.values()
            ) / len(available)

        baseline = results[0]
        digest_payload = "|".join(
            sorted(result.input_manifest_digest for result in available.values())
        )
        digest = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()
        aggregated.append(
            replace(
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
                },
                normalization_parameters={
                    "physics_aggregation_version": (
                        "physics-field-balanced-coverage-aware-v1"
                    ),
                    "field_weighting": "equal-across-eligible-fields",
                    "coverage_threshold": thresholds.coverage.field_attribution,
                    "threshold_version": thresholds.version,
                },
                input_count=sum(result.input_count for result in available.values()),
                input_manifest_digest=digest,
                missing_reasons=reasons,
            )
        )
    return tuple(aggregated)
