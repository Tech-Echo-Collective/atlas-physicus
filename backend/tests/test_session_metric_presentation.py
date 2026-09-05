"""Session metadata and normalization isolation; not scientific proof fixtures."""

from dataclasses import replace

import pytest

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.citations import CITATION_POLICY_VERSION
from physics_atlas_api.certification.measurement_windows import (
    SESSION_CITATION_POLICY_VERSION,
)
from physics_atlas_api.metrics.aggregation import _aggregate_group
from physics_atlas_api.metrics.calculators import (
    MetricCalculationResult,
    MetricMetadataValue,
    citation_session_normalization_key,
    normalize_impact_results,
)
from physics_atlas_api.metrics.contracts import get_metric_contract
from physics_atlas_api.metrics.presentation import (
    _comparison_cohort,
    _normalization_cohort_key,
    _presentation_cutoff,
)
from physics_atlas_api.metrics.thresholds import METRIC_VALIDATION_THRESHOLDS_V1

_START = "2026-09-05T12:00:00+00:00"
_END = "2026-09-05T12:00:05+00:00"
_HORIZON = "2026-09-05T13:00:00+00:00"


def _result(
    index: int = 0, session_id: str | None = "test-only-session-a"
) -> MetricCalculationResult:
    contract = get_metric_contract("research_impact")
    assert contract is not None
    components: dict[str, MetricMetadataValue] = {"citation_cutoff": _HORIZON}
    if session_id is not None:
        components = {
            "citation_cutoff": None,
            "citation_session_id": session_id,
            "citation_measurement_started_at": _START,
            "citation_measurement_ended_at": _END,
            "citation_measurement_semantics": "retrospective-measurement-window",
        }
    return MetricCalculationResult(
        metric_id="research_impact",
        metric_definition_version=contract.version,
        algorithm_version=contract.algorithm_version,
        normalization_version=contract.normalization_version,
        entity_type="institution",
        entity_id=f"test-only-institution-{index}",
        field_id="hep-th",
        period="2022",
        raw_value=float(index + 1),
        raw_unit=contract.raw_unit,
        normalized_value=None,
        components=components,
        normalization_parameters={},
        input_count=10,
        input_manifest_digest="test-only-not-admission-proof",
        certification_manifest_digest="test-only-not-admission-proof",
        threshold_version=METRIC_VALIDATION_THRESHOLDS_V1.version,
        dataset_version="test-only-session-dataset-v1",
        acquisition_scope="hep-th-v1",
        evidence_cutoff=_HORIZON,
        attribution_policy_version="test-only-attribution",
        ontology_version="test-only-ontology",
        mapping_policy_version="test-only-mapping",
        citation_policy_version=(
            SESSION_CITATION_POLICY_VERSION
            if session_id is not None
            else CITATION_POLICY_VERSION
        ),
    )


def test_session_metadata_is_retrospective_and_preserves_legacy_cohort_key() -> None:
    legacy, session = _result(session_id=None), _result()
    assert citation_session_normalization_key(legacy) == ()
    assert len(_normalization_cohort_key(legacy)) == 15
    assert _normalization_cohort_key(session)[-3:] == (
        "test-only-session-a",
        _START,
        _END,
    )
    assert len(_normalization_cohort_key(session)) == 18
    metadata = _comparison_cohort(session)
    assert metadata["citation_measurement_started_at"] == _START
    assert metadata["citation_measurement_ended_at"] == _END
    assert (
        metadata["citation_measurement_semantics"] == "retrospective-measurement-window"
    )
    assert "citation_cutoff" not in metadata
    assert "citation_session_id" not in _comparison_cohort(legacy)
    assert _presentation_cutoff(legacy) == _HORIZON
    assert _presentation_cutoff(session) is None
    assert session.evidence_cutoff == _HORIZON


@pytest.mark.parametrize(
    "changes",
    [
        {"citation_session_id": None},
        {"citation_measurement_started_at": ""},
        {"citation_measurement_started_at": "2026-09-05T12:00:00"},
        {"citation_measurement_ended_at": "not-a-timestamp"},
        {"citation_measurement_ended_at": "2026-09-05T11:00:00+00:00"},
        {"citation_measurement_ended_at": "2026-09-05T14:00:00+00:00"},
        {"citation_measurement_semantics": "atomic-cutoff"},
        {"citation_cutoff": _END},
    ],
)
def test_session_normalization_rejects_missing_or_falsified_interval(
    changes: dict[str, MetricMetadataValue],
) -> None:
    result = _result()
    result = replace(result, components={**result.components, **changes})
    with pytest.raises(CertificationError):
        normalize_impact_results((result,))
    with pytest.raises(CertificationError):
        _normalization_cohort_key(result)


def test_same_session_uses_unchanged_normalization_math() -> None:
    legacy = tuple(_result(index, None) for index in range(30))
    session = tuple(_result(index) for index in range(30))
    legacy_output = normalize_impact_results(legacy)
    session_output = normalize_impact_results(session)
    assert [item.normalized_value for item in session_output] == [
        item.normalized_value for item in legacy_output
    ]
    assert all(item.normalized_value is not None for item in session_output)
    assert all(not item.missing_reasons for item in session_output)


def test_distinct_sessions_cannot_pool_peers_to_pass_minimum_30() -> None:
    inputs = tuple(
        _result(index, "test-only-session-a" if index < 15 else "test-only-session-b")
        for index in range(30)
    )
    output = normalize_impact_results(inputs)
    assert all(item.normalized_value is None for item in output)
    assert all(item.missing_reasons for item in output)
    assert all(item.normalization_parameters["cohort_size"] == 15 for item in output)


def test_equal_horizon_does_not_make_distinct_sessions_comparable() -> None:
    first, second = _result(0, "test-only-session-a"), _result(1, "test-only-session-b")
    assert first.evidence_cutoff == second.evidence_cutoff
    assert _normalization_cohort_key(first) != _normalization_cohort_key(second)


def test_physics_aggregation_preserves_session_interval_and_unchanged_math() -> None:
    first = replace(_result(), normalized_value=20.0)
    second = replace(first, field_id="gr-qc", normalized_value=60.0)
    weights = {(first.entity_id, field): 1.0 for field in ("hep-th", "gr-qc")}
    combined = _aggregate_group(
        (first, second), weights, METRIC_VALIDATION_THRESHOLDS_V1
    )
    assert combined.raw_value == combined.normalized_value == 40.0
    assert combined.field_id == "physics"
    assert citation_session_normalization_key(
        combined
    ) == citation_session_normalization_key(first)
    assert combined.components["citation_cutoff"] is None
    assert _presentation_cutoff(combined) is None
    assert combined.evidence_cutoff == _HORIZON
    legacy = replace(_result(session_id=None), normalized_value=20.0)
    legacy_combined = _aggregate_group(
        (legacy, replace(legacy, field_id="gr-qc", normalized_value=60.0)),
        weights,
        METRIC_VALIDATION_THRESHOLDS_V1,
    )
    assert legacy_combined.normalized_value == combined.normalized_value
    assert "citation_session_id" not in legacy_combined.components
    assert _presentation_cutoff(legacy_combined) == _HORIZON


def test_physics_aggregation_rejects_different_sessions_even_with_equal_horizon() -> (
    None
):
    first = replace(_result(), normalized_value=20.0)
    second = replace(
        _result(session_id="test-only-session-b"),
        field_id="gr-qc",
        normalized_value=60.0,
    )
    weights = {(first.entity_id, field): 1.0 for field in ("hep-th", "gr-qc")}
    with pytest.raises(ValueError, match="identical versions"):
        _aggregate_group((first, second), weights, METRIC_VALIDATION_THRESHOLDS_V1)
