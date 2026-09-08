"""PA-063 normalization boundaries use typed, source-derived fixture decisions."""

from copy import copy
from dataclasses import replace

import pytest
from certification_helpers import certify_normalization_populations
from test_launch_attribution import _ROR_A, _ROR_B
from test_launch_calculations import _window, _year

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.automation import (
    AutomaticUnambiguousResearcherDecision,
    automatic_known_researcher_decision,
)
from physics_atlas_api.certification.build_cache import bounded_build_verification_cache
from physics_atlas_api.certification.launch_calculations import (
    build_launch_metric_partition,
)
from physics_atlas_api.certification.materialization import (
    build_certified_metric_partition,
)
from physics_atlas_api.certification.years import (
    EnumeratedLaunchSourceYearEvidence,
    certify_source_year,
    qualify_observed_release_source_year,
)
from physics_atlas_api.fields import PHYSICS_FIELD_ONTOLOGY_V1
from physics_atlas_api.metrics.aggregation import (
    aggregate_ontology_branch,
    certify_field_population,
    derive_ontology_branch_population,
)
from physics_atlas_api.metrics.automatic_normalization import (
    derive_normalization_population,
)
from physics_atlas_api.metrics.calculators import calculate_activity_raw
from physics_atlas_api.metrics.presentation import (
    _calculation_researcher_identity_policy,
    apply_atlas_scale,
    bind_metric_calculation,
    certify_normalization_population,
)


@pytest.fixture(scope="module")
def peers():  # type: ignore[no-untyped-def]
    with bounded_build_verification_cache():
        years = tuple(_year(year) for year in (2021, 2022, 2023))
        qualified = tuple(
            qualify_observed_release_source_year(
                certify_source_year(
                    EnumeratedLaunchSourceYearEvidence(**vars(year.evidence)),
                    year.coverage,
                )
            )
            for year in years
        )
        window = _window(qualified, "research_activity_score")
        current, legacy = [], []
        for identifier in (_ROR_A, _ROR_B):
            partition = build_launch_metric_partition(
                window, entity_id=f"institution-ror-{identifier}", field_id="nucl-th"
            )
            current.append(
                bind_metric_calculation(calculate_activity_raw(partition), partition)
            )
            decisions = tuple(
                automatic_known_researcher_decision(
                    item.source_facts, entity_type="institution"
                )
                if isinstance(item, AutomaticUnambiguousResearcherDecision)
                else item
                for item in partition.certification.evidence_decisions
            )
            old = build_certified_metric_partition(
                partition.partition,
                metric_id="research_activity_score",
                decisions=decisions,
                coverage=partition.certification.coverage,
                window=window,
                population=partition.population_proof,
            )
            legacy.append(bind_metric_calculation(calculate_activity_raw(old), old))
        yield window, tuple(current), tuple(legacy)


@pytest.mark.parametrize("index", [1, 2])
def test_homogeneous_identity_policies_keep_existing_values_and_thresholds(
    peers, index
):  # type: ignore[no-untyped-def]
    window = peers[0]
    calculations = peers[index]
    with bounded_build_verification_cache():
        population = certify_normalization_population(
            derive_normalization_population(window, calculations)
        )
        observations = apply_atlas_scale(
            calculations, normalization_populations=(population,)
        )
        assert len(observations) == 2 and all(
            item.value is None for item in observations
        )
        for new, legacy in zip(peers[1], peers[2], strict=True):
            assert new.calculation.raw_value == legacy.calculation.raw_value
            assert new.calculation.components == legacy.calculation.components
            assert new.calculation.missing_reasons == legacy.calculation.missing_reasons
            assert (
                new.calculation.algorithm_version
                == legacy.calculation.algorithm_version
            )


def test_automatic_population_certification_rejects_mixed_consumed_identity_policies(
    peers,
):  # type: ignore[no-untyped-def]
    window, current, legacy = peers
    with bounded_build_verification_cache():
        evidence = derive_normalization_population(window, (current[0], legacy[1]))
        with pytest.raises(
            CertificationError, match="mixes researcher identity producer"
        ):
            certify_normalization_population(evidence)


def test_observation_guard_rejects_mixed_policies_even_with_reviewed_population(peers):  # type: ignore[no-untyped-def]
    _, current, legacy = peers
    mixed = (current[0], legacy[1])
    with bounded_build_verification_cache():
        reviewed = certify_normalization_populations(mixed)
        with pytest.raises(
            CertificationError, match="mixes researcher identity producer"
        ):
            apply_atlas_scale(mixed, normalization_populations=reviewed)
        original = apply_atlas_scale(
            current,
            normalization_populations=certify_normalization_populations(current),
        )[0]
        with pytest.raises(
            CertificationError, match="mixes researcher identity producer"
        ):
            replace(
                original,
                normalization_proofs=mixed,
                normalization_population_proof=reviewed[0],
            )


def test_identity_policy_guard_checks_exact_producer_rule_not_just_type(peers):  # type: ignore[no-untyped-def]
    # Deliberately corrupt a copied frozen proof; never mutate the shared fixture.
    original = peers[1][0]
    partition, certificate = (
        copy(original.partition),
        copy(original.partition.certification),
    )
    decisions = list(certificate.evidence_decisions)
    for index, decision in enumerate(decisions):
        if isinstance(decision, AutomaticUnambiguousResearcherDecision):
            changed = copy(decision)
            object.__setattr__(changed, "rule_version", "stale-subset-producer")
            decisions[index] = changed
            break
    object.__setattr__(certificate, "evidence_decisions", tuple(decisions))
    object.__setattr__(partition, "certification", certificate)
    forged = copy(original)
    object.__setattr__(forged, "partition", partition)
    with pytest.raises(CertificationError, match="researcher identity producer"):
        _calculation_researcher_identity_policy(forged)


def test_branch_and_presentation_reject_mixed_identity_producers_between_fields(peers):  # type: ignore[no-untyped-def]
    window, current, legacy = peers
    with bounded_build_verification_cache():
        second = tuple(
            build_launch_metric_partition(
                window, entity_id=f"institution-ror-{identifier}", field_id="nucl-ex"
            )
            for identifier in (_ROR_A, _ROR_B)
        )
        second_calculations = tuple(
            bind_metric_calculation(calculate_activity_raw(item), item)
            for item in second
        )
        second_observations = apply_atlas_scale(
            second_calculations,
            normalization_populations=(
                certify_normalization_population(
                    derive_normalization_population(window, second_calculations)
                ),
            ),
        )
        first_observations = apply_atlas_scale(
            current,
            normalization_populations=certify_normalization_populations(current),
        )
        old_observations = apply_atlas_scale(
            legacy, normalization_populations=certify_normalization_populations(legacy)
        )
        branch = PHYSICS_FIELD_ONTOLOGY_V1.get("nuclear")
        homogeneous = (first_observations[0], second_observations[0])
        population = certify_field_population(
            derive_ontology_branch_population(branch, homogeneous)
        )
        aggregate = aggregate_ontology_branch(homogeneous, (population,))[0]
        original = apply_atlas_scale((aggregate,))[0]
        mixed = (old_observations[0], second_observations[0])
        mixed_population = certify_field_population(
            derive_ontology_branch_population(branch, mixed)
        )
        with pytest.raises(
            CertificationError, match="mixes researcher identity producer"
        ):
            aggregate_ontology_branch(mixed, (mixed_population,))
        with pytest.raises(
            CertificationError, match="mixes researcher identity producer"
        ):
            replace(
                aggregate,
                field_observations=mixed,
                field_population_proof=mixed_population,
            )
        # A forged frozen aggregation cannot bypass the independent Atlas view
        # guard merely by retaining its old numeric calculation/digest fields.
        forged = copy(aggregate)
        object.__setattr__(forged, "field_observations", mixed)
        with pytest.raises(
            CertificationError, match="mixes researcher identity producer"
        ):
            replace(original, certification_proof=forged)
