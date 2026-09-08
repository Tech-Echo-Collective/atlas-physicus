"""Bounded source-derived exclusion proofs; no weakened numerical thresholds."""

from dataclasses import replace

import pytest
from test_launch_attribution import _ROR_A, _ROR_B
from test_launch_calculations import _window, _year

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification import launch_calculations as bridge
from physics_atlas_api.certification.build_cache import bounded_build_verification_cache
from physics_atlas_api.certification.years import (
    EnumeratedLaunchSourceYearEvidence,
    certify_source_year,
    qualify_observed_release_source_year,
    source_quality_certification,
)
from physics_atlas_api.metrics.automatic_normalization import (
    ConditionalNormalizationPopulationEvidence,
    conditional_normalization_disclosure,
    derive_normalization_population,
)
from physics_atlas_api.metrics.thresholds import METRIC_VALIDATION_THRESHOLDS_V1


@pytest.fixture(scope="module")
def conditional_window():  # type: ignore[no-untyped-def]
    with bounded_build_verification_cache():
        years = []
        for year in (2021, 2022, 2023):
            source = _year(year, uncertain_peer=True)
            enumerated = certify_source_year(
                EnumeratedLaunchSourceYearEvidence(**vars(source.evidence)),
                source.coverage,
            )
            qualified = qualify_observed_release_source_year(enumerated)
            assert (
                source_quality_certification(qualified).state == "insufficient_evidence"
            )
            years.append(qualified)
        yield _window(tuple(years), "collaboration")


def test_exact_failed_peer_is_disclosed_not_silently_dropped(
    conditional_window,
) -> None:  # type: ignore[no-untyped-def]
    observations = bridge.calculate_launch_metric_cohort(
        conditional_window, field_id="nucl-th"
    )
    assert len(observations) == 1
    observation = observations[0]
    assert observation.calculation.entity_id == f"institution-ror-{_ROR_A}"
    assert observation.value is None  # existing sample-size guard still applies
    proof = observation.normalization_population_proof
    assert proof is not None
    evidence = proof.evidence
    assert isinstance(evidence, ConditionalNormalizationPopulationEvidence)
    assert len(evidence.source_entity_ids) == 2 and len(evidence.entity_ids) == 1
    excluded = evidence.ineligible_peers[0]
    assert excluded.entity_id == f"institution-ror-{_ROR_B}"
    assert excluded.failures[0].evidence_kind == "collaboration-relationship"
    assert excluded.failures[0].minimum == 0.9
    assert excluded.failures[0].numerator < excluded.failures[0].denominator * 0.9
    disclosure = conditional_normalization_disclosure(proof)
    assert disclosure is not None
    assert disclosure["sourcePeerCount"] == 2
    assert disclosure["eligiblePeerCount"] == disclosure["excludedPeerCount"] == 1
    assert METRIC_VALIDATION_THRESHOLDS_V1.activity.minimum_normalization_cohort == 30
    assert METRIC_VALIDATION_THRESHOLDS_V1.impact.minimum_normalization_cohort == 30
    assert METRIC_VALIDATION_THRESHOLDS_V1.momentum.minimum_normalization_cohort == 30


def test_omitted_duplicate_forged_or_eligible_exclusion_is_rejected(
    conditional_window,
) -> None:  # type: ignore[no-untyped-def]
    observation = bridge.calculate_launch_metric_cohort(
        conditional_window, field_id="nucl-th"
    )[0]
    proof = observation.normalization_population_proof
    assert proof is not None
    evidence = proof.evidence
    assert isinstance(evidence, ConditionalNormalizationPopulationEvidence)
    excluded = evidence.ineligible_peers[0]
    with pytest.raises(CertificationError, match="every source-window peer"):
        derive_normalization_population(conditional_window, evidence.calculations)
    with pytest.raises(CertificationError, match="every source-window peer"):
        derive_normalization_population(
            conditional_window,
            evidence.calculations,
            ineligible_peers=(excluded, excluded),
        )
    with pytest.raises(CertificationError, match="reconstruct scientific failures"):
        replace(excluded, partition_digest="0" * 64)
    with pytest.raises(CertificationError, match="reconstruct scientific failures"):
        replace(excluded, failures=())
    with pytest.raises(CertificationError, match="reconstruct scientific failures"):
        replace(excluded, entity_id=f"institution-ror-{_ROR_A}")
    with pytest.raises(CertificationError, match="another scope"):
        derive_normalization_population(
            conditional_window,
            evidence.calculations,
            ineligible_peers=(
                bridge._ineligible_launch_peer(
                    bridge._launch_partition_inputs(
                        conditional_window,
                        entity_id=excluded.entity_id,
                        field_id="nucl-ex",
                    )
                ),
            ),
        )


def test_implementation_errors_are_not_scientific_exclusions(
    conditional_window,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    def broken(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("unrelated parser defect")

    monkeypatch.setattr(bridge, "_launch_partition_inputs", broken)
    with pytest.raises(RuntimeError, match="unrelated parser defect"):
        bridge.calculate_launch_metric_cohort(conditional_window, field_id="nucl-th")
