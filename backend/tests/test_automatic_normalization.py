from dataclasses import replace

import pytest
from certification_helpers import certify_normalization_populations, certify_partition
from test_metric_system_v1 import paper, partition

from physics_atlas_api.certification import CertificationError, CertifiedMetricWindow
from physics_atlas_api.metrics.automatic_normalization import (
    derive_normalization_population,
)
from physics_atlas_api.metrics.calculators import calculate_activity_raw
from physics_atlas_api.metrics.presentation import (
    CertifiedMetricCalculation,
    apply_atlas_scale,
    bind_metric_calculation,
    certify_normalization_population,
)


def calculation(weight: float = 1.0) -> CertifiedMetricCalculation:
    value = partition(
        "institution-a",
        tuple(
            paper(index, year, weight=weight)
            for year in (2023, 2024, 2025)
            for index in range(5)
        ),
    )
    certified = certify_partition(value, "research_activity_score")
    return bind_metric_calculation(calculate_activity_raw(certified), certified)


def test_machine_population_matches_legacy_normalization_without_faking_review() -> (
    None
):
    source = calculation()
    window = source.partition.window_proof
    assert isinstance(window, CertifiedMetricWindow)
    evidence = derive_normalization_population(window, (source,))
    assert evidence.entity_ids == ("institution-a",)
    assert evidence.reviewed_by is evidence.reviewed_at is None
    machine = certify_normalization_population(evidence)
    automatic = apply_atlas_scale((source,), normalization_populations=(machine,))
    legacy = apply_atlas_scale(
        (source,),
        normalization_populations=certify_normalization_populations((source,)),
    )
    assert automatic[0].calculation == legacy[0].calculation
    assert automatic[0].calculation.raw_value == 15
    # The unchanged 30-peer threshold still withholds this one-peer fixture.
    assert automatic[0].value is None
    assert automatic[0].uncertainty_reasons == legacy[0].uncertainty_reasons


def test_machine_population_rejects_omitted_peer() -> None:
    source = calculation(0.5)
    window = source.partition.window_proof
    assert isinstance(window, CertifiedMetricWindow)
    with pytest.raises(CertificationError, match="every source-window peer"):
        derive_normalization_population(window, (source,))


@pytest.mark.parametrize(
    "changes",
    [
        {"entity_ids": ("another",)},
        {"automatic_rule_version": "arbitrary-approved-v1"},
        {"reviewed_by": "fabricated-reviewer"},
        {"source_manifest_digest": "0" * 64},
        {"calculations": ()},
    ],
)
def test_machine_population_rechecks_retained_evidence(
    changes: dict[str, object],
) -> None:
    source = calculation()
    window = source.partition.window_proof
    assert isinstance(window, CertifiedMetricWindow)
    evidence = derive_normalization_population(window, (source,))
    with pytest.raises(CertificationError):
        certify_normalization_population(replace(evidence, **changes))


def test_machine_population_rejects_duplicate_calculations() -> None:
    source = calculation()
    window = source.partition.window_proof
    assert isinstance(window, CertifiedMetricWindow)
    with pytest.raises(CertificationError, match="every source-window peer"):
        derive_normalization_population(window, (source, source))
