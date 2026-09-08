from dataclasses import replace

import pytest
from certification_helpers import certify_normalization_populations, certify_partition
from test_metric_system_v1 import paper, partition

from physics_atlas_api.certification import (
    CertificationError,
    CertifiedMetricWindow,
    build_certified_metric_partition,
    certify_coverage,
    paper_evidence_value_digest,
)
from physics_atlas_api.certification.populations import (
    OBSERVED_ATTRIBUTION_COVERAGE_VERSION,
    POSSIBLE_ATTRIBUTION_COVERAGE_VERSION,
    derive_metric_population,
)
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


def _same_window_calculation(
    source: CertifiedMetricCalculation, entity_id: str, coverage_policy: str
) -> CertifiedMetricCalculation:
    """Rebind one of the two exact fixture peers, without changing its source."""
    original = source.partition
    window = original.window_proof
    assert isinstance(window, CertifiedMetricWindow)
    value = replace(original.partition, entity_id=entity_id)
    population = derive_metric_population(
        window,
        entity_id=entity_id,
        field_id=value.field_id,
        assessed_at=window.cutoff,
        coverage_policy=coverage_policy,
    )
    papers = {item.paper_id: item for item in value.papers}
    decisions = tuple(
        replace(
            item,
            certified_value_digest=paper_evidence_value_digest(
                value, papers[item.subject_id], item.evidence_kind
            ),
        )
        if item.subject_type == "paper"
        else item
        for item in original.certification.evidence_decisions
    )
    coverage = tuple(
        certify_coverage(
            item.evidence_kind,
            tuple(
                decision
                for decision in decisions
                if decision.subject_type == "coverage-unit"
                and decision.evidence_kind == item.evidence_kind
            ),
            replace(
                item.population,
                source_manifest_digest=population.certification.projection_digest,
            ),
        )
        for item in original.certification.coverage
    )
    certified = build_certified_metric_partition(
        value,
        metric_id="research_activity_score",
        decisions=decisions,
        coverage=coverage,
        window=window,
        population=population,
    )
    return bind_metric_calculation(calculate_activity_raw(certified), certified)


@pytest.mark.parametrize(
    "coverage_policy",
    [POSSIBLE_ATTRIBUTION_COVERAGE_VERSION, OBSERVED_ATTRIBUTION_COVERAGE_VERSION],
)
def test_homogeneous_population_coverage_policy_preserves_normalization(
    coverage_policy: str,
) -> None:
    source = calculation(0.5)
    window = source.partition.window_proof
    assert isinstance(window, CertifiedMetricWindow)
    peers = tuple(
        _same_window_calculation(source, entity_id, coverage_policy)
        for entity_id in ("institution-a", "fixture-other-institution")
    )
    population = certify_normalization_population(
        derive_normalization_population(window, peers)
    )
    observations = apply_atlas_scale(peers, normalization_populations=(population,))
    assert len(observations) == 2
    assert all(
        item.calculation.components["fractional_papers"] == 7.5 for item in observations
    )
    # Neither coverage policy relaxes the raw Activity minimum or the 30-peer
    # normalization minimum for this deliberately small fixture.
    assert all(item.calculation.raw_value is None for item in observations)
    assert all(item.value is None for item in observations)
    assert all(item.uncertainty_reasons for item in observations)


def test_normalization_rejects_mixed_population_coverage_policies() -> None:
    source = calculation(0.5)
    window = source.partition.window_proof
    assert isinstance(window, CertifiedMetricWindow)
    observed_peer = _same_window_calculation(
        source, "fixture-other-institution", OBSERVED_ATTRIBUTION_COVERAGE_VERSION
    )
    mixed = (source, observed_peer)
    with pytest.raises(CertificationError, match="mixes population coverage policies"):
        derive_normalization_population(window, mixed)

    # Even an explicit reviewed population cannot bypass the independent Atlas
    # presentation boundary and mix conditional with worst-case admission.
    mixed_populations = certify_normalization_populations(mixed)
    with pytest.raises(CertificationError, match="mixes population coverage policies"):
        apply_atlas_scale(mixed, normalization_populations=mixed_populations)

    possible_peer = _same_window_calculation(
        source, "fixture-other-institution", POSSIBLE_ATTRIBUTION_COVERAGE_VERSION
    )
    legacy = (source, possible_peer)
    original = apply_atlas_scale(
        legacy,
        normalization_populations=certify_normalization_populations(legacy),
    )[0]
    with pytest.raises(CertificationError, match="mixes population coverage policies"):
        replace(
            original,
            normalization_proofs=mixed,
            normalization_population_proof=mixed_populations[0],
        )
