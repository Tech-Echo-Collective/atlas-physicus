import math
from collections.abc import Mapping
from dataclasses import dataclass

NormalizationParameter = float | int | str


@dataclass(frozen=True)
class CohortNormalizationResult:
    """A fitted cohort transform whose parameters can be persisted as provenance."""

    eligible: bool
    scores: dict[str, float]
    method_version: str
    parameters: dict[str, NormalizationParameter]
    reason: str | None = None


@dataclass(frozen=True)
class ScalarNormalizationResult:
    """A bounded scalar transform that distinguishes missing from measured zero."""

    eligible: bool
    raw_value: float | None
    score: float | None
    method_version: str
    parameters: dict[str, NormalizationParameter]
    reason: str | None = None


def _validated_values(raw_values: Mapping[str, float]) -> dict[str, float]:
    values: dict[str, float] = {}
    for entity_id, raw_value in raw_values.items():
        value = float(raw_value)
        if not math.isfinite(value) or value < 0:
            raise ValueError("metric inputs must be finite and nonnegative")
        values[entity_id] = value
    return values


def _linear_quantile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        raise ValueError("a quantile requires at least one value")
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between zero and one")
    position = (len(sorted_values) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    return lower + (upper - lower) * (position - lower_index)


def robust_log_winsorized_cohort(
    raw_values: Mapping[str, float],
    *,
    minimum_cohort: int = 30,
    lower_quantile: float = 0.05,
    upper_quantile: float = 0.95,
) -> CohortNormalizationResult:
    """Fit the Activity/Connectivity v1 transform to one exact cohort.

    This is a winsorized linear display transform after ``log1p``. It is not a
    rank or percentile transform, so callers must not interpret a score as the
    percentage of cohort entities below an observation.
    """
    if minimum_cohort < 2:
        raise ValueError("minimum_cohort must be at least two")
    if not 0 <= lower_quantile < upper_quantile <= 1:
        raise ValueError("quantile bounds must satisfy 0 <= lower < upper <= 1")

    values = _validated_values(raw_values)
    method_version = "robust-log-winsorized-cohort-v1"
    base_parameters: dict[str, NormalizationParameter] = {
        "cohort_size": len(values),
        "minimum_cohort": minimum_cohort,
        "lower_quantile": lower_quantile,
        "upper_quantile": upper_quantile,
        "input_transform": "log1p",
        "output_min": 0.0,
        "output_max": 100.0,
    }
    if len(values) < minimum_cohort:
        return CohortNormalizationResult(
            eligible=False,
            scores={},
            method_version=method_version,
            parameters=base_parameters,
            reason="insufficient normalization cohort",
        )

    transformed = {entity_id: math.log1p(value) for entity_id, value in values.items()}
    ordered = sorted(transformed.values())
    lower = _linear_quantile(ordered, lower_quantile)
    upper = _linear_quantile(ordered, upper_quantile)
    parameters = {
        **base_parameters,
        "fitted_lower": lower,
        "fitted_upper": upper,
    }
    if math.isclose(lower, upper, rel_tol=0.0, abs_tol=1e-12):
        return CohortNormalizationResult(
            eligible=False,
            scores={},
            method_version=method_version,
            parameters=parameters,
            reason="degenerate normalization cohort",
        )

    scale = upper - lower
    scores = {
        entity_id: 100.0 * min(1.0, max(0.0, (value - lower) / scale))
        for entity_id, value in transformed.items()
    }
    return CohortNormalizationResult(
        eligible=True,
        scores=scores,
        method_version=method_version,
        parameters=parameters,
    )


def robust_mncs_cohort(
    raw_values: Mapping[str, float],
    *,
    minimum_cohort: int = 30,
    lower_quantile: float = 0.05,
    upper_quantile: float = 0.95,
) -> CohortNormalizationResult:
    """Map nonnegative entity MNCS values to a reproducible display range.

    MNCS is already field/year/document-type normalized at paper level. This
    second transform is presentation-only and preserves MNCS as the raw value.
    """
    result = robust_log_winsorized_cohort(
        raw_values,
        minimum_cohort=minimum_cohort,
        lower_quantile=lower_quantile,
        upper_quantile=upper_quantile,
    )
    return CohortNormalizationResult(
        eligible=result.eligible,
        scores=result.scores,
        method_version="field-year-document-mncs-robust-v1",
        parameters={
            **result.parameters,
            "input_metric": "fractional-mncs",
            "field_normalization": "same-field-year-document-type-mean",
        },
        reason=result.reason,
    )


def log_midrank_percentiles(
    raw_values: Mapping[str, float],
    *,
    minimum_cohort: int = 50,
) -> CohortNormalizationResult:
    """Return tie-aware Impact v1 paper percentiles for one field-age cohort."""
    if minimum_cohort < 2:
        raise ValueError("minimum_cohort must be at least two")
    values = _validated_values(raw_values)
    method_version = "field-age-log-midrank-v1"
    parameters: dict[str, NormalizationParameter] = {
        "cohort_size": len(values),
        "minimum_cohort": minimum_cohort,
        "input_transform": "log1p",
        "rank_method": "midrank",
        "output_min": 0.0,
        "output_max": 100.0,
    }
    if len(values) < minimum_cohort:
        return CohortNormalizationResult(
            eligible=False,
            scores={},
            method_version=method_version,
            parameters=parameters,
            reason="insufficient field-age cohort",
        )

    transformed = {entity_id: math.log1p(value) for entity_id, value in values.items()}
    ordered = sorted(transformed.items(), key=lambda item: (item[1], item[0]))
    if math.isclose(ordered[0][1], ordered[-1][1], rel_tol=0.0, abs_tol=1e-12):
        return CohortNormalizationResult(
            eligible=True,
            scores={entity_id: 50.0 for entity_id in transformed},
            method_version=method_version,
            parameters={**parameters, "all_values_tied": "true"},
        )

    scores: dict[str, float] = {}
    start = 0
    denominator = len(ordered) - 1
    while start < len(ordered):
        end = start
        while end + 1 < len(ordered) and math.isclose(
            ordered[end + 1][1], ordered[start][1], rel_tol=0.0, abs_tol=1e-12
        ):
            end += 1
        percentile = 100.0 * ((start + end) / 2) / denominator
        for index in range(start, end + 1):
            scores[ordered[index][0]] = percentile
        start = end + 1

    return CohortNormalizationResult(
        eligible=True,
        scores=scores,
        method_version=method_version,
        parameters=parameters,
    )


def normalized_shannon_evenness(
    category_weights: Mapping[str, float],
) -> ScalarNormalizationResult:
    """Calculate Diversity v1 over an explicit, versioned category universe."""
    weights = _validated_values(category_weights)
    method_version = "normalized-shannon-evenness-v1"
    parameters: dict[str, NormalizationParameter] = {
        "eligible_category_count": len(weights),
        "output_min": 0.0,
        "output_max": 100.0,
    }
    if len(weights) < 2:
        return ScalarNormalizationResult(
            eligible=False,
            raw_value=None,
            score=None,
            method_version=method_version,
            parameters=parameters,
            reason="at least two eligible categories are required",
        )
    total = sum(weights.values())
    if total <= 0:
        return ScalarNormalizationResult(
            eligible=False,
            raw_value=None,
            score=None,
            method_version=method_version,
            parameters={**parameters, "total_weight": total},
            reason="category evidence is missing",
        )

    entropy = -sum(
        proportion * math.log(proportion)
        for weight in weights.values()
        if (proportion := weight / total) > 0
    )
    evenness = entropy / math.log(len(weights))
    score = 100.0 * min(1.0, max(0.0, evenness))
    return ScalarNormalizationResult(
        eligible=True,
        raw_value=evenness,
        score=score,
        method_version=method_version,
        parameters={**parameters, "total_weight": total},
    )


def symmetric_window_change(
    recent: float,
    baseline: float,
    *,
    minimum_total: float = 10,
) -> ScalarNormalizationResult:
    """Calculate Momentum v1 without treating two absent windows as neutral."""
    values = _validated_values({"recent": recent, "baseline": baseline})
    recent_value = values["recent"]
    baseline_value = values["baseline"]
    total = recent_value + baseline_value
    method_version = "bounded-symmetric-change-v1"
    parameters: dict[str, NormalizationParameter] = {
        "recent": recent_value,
        "baseline": baseline_value,
        "minimum_total": minimum_total,
        "output_min": 0.0,
        "output_max": 100.0,
    }
    if minimum_total <= 0:
        raise ValueError("minimum_total must be positive")
    if total < minimum_total:
        return ScalarNormalizationResult(
            eligible=False,
            raw_value=None,
            score=None,
            method_version=method_version,
            parameters={**parameters, "total": total},
            reason="insufficient evidence across the two windows",
        )

    raw_change = (recent_value - baseline_value) / total
    return ScalarNormalizationResult(
        eligible=True,
        raw_value=raw_change,
        score=50.0 * (raw_change + 1.0),
        method_version=method_version,
        parameters={**parameters, "total": total},
    )


def robust_centered_change_cohort(
    raw_log_changes: Mapping[str, float],
    *,
    minimum_cohort: int = 30,
    z_clip: float = 3.0,
) -> CohortNormalizationResult:
    """Normalize Momentum after subtracting the exact field-cohort median.

    A median/MAD scale is used first. IQR supplies a deterministic fallback
    when the median absolute deviation is zero but the cohort still varies.
    A fully tied cohort maps to the neutral field-relative value 50.
    """
    if minimum_cohort < 2:
        raise ValueError("minimum_cohort must be at least two")
    if z_clip <= 0:
        raise ValueError("z_clip must be positive")
    values: dict[str, float] = {}
    for entity_id, raw_value in raw_log_changes.items():
        value = float(raw_value)
        if not math.isfinite(value):
            raise ValueError("momentum inputs must be finite")
        values[entity_id] = value

    method_version = "field-relative-robust-log-change-v1"
    base_parameters: dict[str, NormalizationParameter] = {
        "cohort_size": len(values),
        "minimum_cohort": minimum_cohort,
        "center": "median",
        "primary_scale": "1.4826*median-absolute-deviation",
        "fallback_scale": "interquartile-range/1.349",
        "z_clip": z_clip,
        "output_min": 0.0,
        "output_midpoint": 50.0,
        "output_max": 100.0,
    }
    if len(values) < minimum_cohort:
        return CohortNormalizationResult(
            eligible=False,
            scores={},
            method_version=method_version,
            parameters=base_parameters,
            reason="insufficient field momentum cohort",
        )

    ordered = sorted(values.values())
    median = _linear_quantile(ordered, 0.5)
    deviations = sorted(abs(value - median) for value in ordered)
    mad = _linear_quantile(deviations, 0.5)
    q1 = _linear_quantile(ordered, 0.25)
    q3 = _linear_quantile(ordered, 0.75)
    mad_scale = 1.4826 * mad
    iqr_scale = (q3 - q1) / 1.349
    scale = mad_scale if mad_scale > 1e-12 else iqr_scale
    parameters = {
        **base_parameters,
        "fitted_median": median,
        "fitted_mad": mad,
        "fitted_q1": q1,
        "fitted_q3": q3,
        "fitted_scale": scale,
    }

    if scale <= 1e-12:
        if math.isclose(ordered[0], ordered[-1], rel_tol=0.0, abs_tol=1e-12):
            return CohortNormalizationResult(
                eligible=True,
                scores={entity_id: 50.0 for entity_id in values},
                method_version=method_version,
                parameters={**parameters, "all_values_tied": "true"},
            )
        return CohortNormalizationResult(
            eligible=False,
            scores={},
            method_version=method_version,
            parameters=parameters,
            reason="degenerate robust momentum scale",
        )

    scores = {
        entity_id: 50.0
        + (50.0 / z_clip) * min(z_clip, max(-z_clip, (value - median) / scale))
        for entity_id, value in values.items()
    }
    return CohortNormalizationResult(
        eligible=True,
        scores=scores,
        method_version=method_version,
        parameters=parameters,
    )
