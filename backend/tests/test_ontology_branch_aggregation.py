"""Scoped aggregation fixtures do not establish any real-data activation."""

from dataclasses import replace

import pytest
from certification_helpers import certify_normalization_populations
from test_automatic_field_population import field_observations  # noqa: F401
from test_session_metric_presentation import _result

from physics_atlas_api.certification import (
    CertificationError,
    CertifiedMetricWindow,
    build_certified_metric_partition,
    certify_coverage,
)
from physics_atlas_api.certification.populations import (
    OBSERVED_ATTRIBUTION_COVERAGE_VERSION,
    derive_metric_population,
)
from physics_atlas_api.fields import PHYSICS_FIELD_ONTOLOGY_V1
from physics_atlas_api.metrics.aggregation import (
    ONTOLOGY_BRANCH_AGGREGATION_VERSION,
    CertifiedOntologyBranchAggregation,
    _aggregate_branch_group,
    aggregate_ontology_branch,
    aggregate_physics_wide,
    certify_field_population,
    derive_ontology_branch_population,
)
from physics_atlas_api.metrics.calculators import calculate_connectivity
from physics_atlas_api.metrics.presentation import (
    AtlasScaleObservation,
    CertifiedMetricCalculation,
    apply_atlas_scale,
    bind_metric_calculation,
)
from physics_atlas_api.metrics.thresholds import METRIC_VALIDATION_THRESHOLDS_V1


def nuclear_fields(
    observations: tuple[AtlasScaleObservation, ...],
) -> tuple[AtlasScaleObservation, ...]:
    return tuple(
        item
        for item in observations
        if item.calculation.field_id in {"nucl-th", "nucl-ex"}
    )


def test_branch_proof_is_typed_and_output_stays_nuclear_not_physics(
    field_observations: tuple[AtlasScaleObservation, ...],  # noqa: F811
) -> None:
    selected = nuclear_fields(field_observations)
    evidence = derive_ontology_branch_population(
        PHYSICS_FIELD_ONTOLOGY_V1.get("nuclear"), selected
    )
    assert evidence.field_weights == (("nucl-ex", 1.0), ("nucl-th", 1.0))
    assert evidence.reviewed_by is evidence.reviewed_at is None
    proof = certify_field_population(evidence)
    aggregated = aggregate_ontology_branch(selected, (proof,))
    assert isinstance(aggregated[0], CertifiedOntologyBranchAggregation)
    result = aggregated[0].calculation
    assert result.field_id == "nuclear"
    assert result.components["expected_field_count"] == 2
    assert result.components["field_evidence_coverage"] == 1.0
    assert (
        result.normalization_parameters["ontology_branch_aggregation_version"]
        == ONTOLOGY_BRANCH_AGGREGATION_VERSION
    )
    assert "physics_aggregation_version" not in result.normalization_parameters
    assert (
        result.normalized_value
        == sum(item.value for item in selected if item.value is not None) / 2
    )
    atlas = apply_atlas_scale(aggregated)
    assert atlas[0].calculation.field_id == "nuclear"
    assert atlas[0].value == result.normalized_value
    with pytest.raises(CertificationError, match="cannot mix"):
        aggregate_physics_wide(selected, (proof,))


def test_one_missing_leaf_keeps_two_leaf_denominator_and_withholds(
    field_observations: tuple[AtlasScaleObservation, ...],  # noqa: F811
) -> None:
    selected = nuclear_fields(field_observations)[:1]
    evidence = derive_ontology_branch_population(
        PHYSICS_FIELD_ONTOLOGY_V1.get("nuclear"), selected
    )
    result = aggregate_ontology_branch(selected, (certify_field_population(evidence),))[
        0
    ].calculation
    assert result.components["expected_field_count"] == 2
    assert result.components["field_evidence_coverage"] == 0.5
    assert result.normalized_value is None
    assert result.missing_reasons == (
        "Ontology-branch field evidence coverage is below the v1 threshold",
    )


def test_catalog_target_and_bound_leaf_inputs_cannot_be_redefined(
    field_observations: tuple[AtlasScaleObservation, ...],  # noqa: F811
) -> None:
    selected = nuclear_fields(field_observations)
    branch = PHYSICS_FIELD_ONTOLOGY_V1.get("nuclear")
    evidence = derive_ontology_branch_population(branch, selected)
    for changed in (
        replace(evidence, branch_id="physics"),
        replace(evidence, branch_id="hep"),
        replace(evidence, field_weights=evidence.field_weights[:1]),
        replace(evidence, field_weights=(("nucl-th", 2.0), ("nucl-ex", 1.0))),
        replace(evidence, observations=(field_observations[0],)),
    ):
        with pytest.raises(CertificationError):
            certify_field_population(changed)
    with pytest.raises(CertificationError, match="frozen ontology"):
        derive_ontology_branch_population(
            replace(branch, description="caller-defined branch"), selected
        )
    with pytest.raises(CertificationError, match="ontology branch"):
        derive_ontology_branch_population(
            PHYSICS_FIELD_ONTOLOGY_V1.get("nucl-th"), selected
        )
    with pytest.raises(CertificationError, match="automatic population inputs"):
        aggregate_ontology_branch(selected[:1], (certify_field_population(evidence),))


def test_branch_arithmetic_preserves_leaf_impact_session_and_rejects_mixing(
    field_observations: tuple[AtlasScaleObservation, ...],  # noqa: F811
) -> None:
    # Pure arithmetic/session fixtures below are deliberately NOT certified
    # Impact inputs. The public typed path still requires their actual proofs.
    evidence = derive_ontology_branch_population(
        PHYSICS_FIELD_ONTOLOGY_V1.get("nuclear"), nuclear_fields(field_observations)
    )
    first = replace(
        _result(),
        entity_id=evidence.entity_id,
        field_id="nucl-th",
        normalized_value=40.0,
    )
    second = replace(
        _result(),
        entity_id=evidence.entity_id,
        field_id="nucl-ex",
        normalized_value=60.0,
    )
    result = _aggregate_branch_group(
        (first, second), evidence, METRIC_VALIDATION_THRESHOLDS_V1
    )
    assert result.field_id == "nuclear"
    assert result.normalized_value == 50
    assert (
        result.components["citation_session_id"]
        == first.components["citation_session_id"]
    )
    assert result.components["citation_cutoff"] is None
    assert (
        result.components["citation_measurement_semantics"]
        == "retrospective-measurement-window"
    )
    changed = replace(
        second,
        components={**second.components, "citation_session_id": "different-session"},
    )
    with pytest.raises(ValueError, match="identical versions"):
        _aggregate_branch_group(
            (first, changed), evidence, METRIC_VALIDATION_THRESHOLDS_V1
        )


def _observed_field(observation: AtlasScaleObservation) -> AtlasScaleObservation:
    proof = observation.certification_proof
    assert isinstance(proof, CertifiedMetricCalculation)
    original = proof.partition
    window = original.window_proof
    assert isinstance(window, CertifiedMetricWindow)
    population = derive_metric_population(
        window,
        entity_id=observation.calculation.entity_id,
        field_id=observation.calculation.field_id,
        assessed_at=window.cutoff,
        coverage_policy=OBSERVED_ATTRIBUTION_COVERAGE_VERSION,
    )
    decisions = original.certification.evidence_decisions
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
        original.partition,
        metric_id="collaboration",
        decisions=decisions,
        coverage=coverage,
        window=window,
        population=population,
    )
    calculated = bind_metric_calculation(calculate_connectivity(certified), certified)
    return apply_atlas_scale(
        (calculated,),
        normalization_populations=certify_normalization_populations((calculated,)),
    )[0]


def test_branch_aggregation_rejects_mixed_coverage_policies_between_fields(
    field_observations: tuple[AtlasScaleObservation, ...],  # noqa: F811
) -> None:
    selected = nuclear_fields(field_observations)
    branch = PHYSICS_FIELD_ONTOLOGY_V1.get("nuclear")
    legacy = aggregate_ontology_branch(
        selected,
        (
            certify_field_population(
                derive_ontology_branch_population(branch, selected)
            ),
        ),
    )[0]
    observed = tuple(_observed_field(item) for item in selected)
    homogeneous = aggregate_ontology_branch(
        observed,
        (
            certify_field_population(
                derive_ontology_branch_population(branch, observed)
            ),
        ),
    )[0]
    assert homogeneous.calculation.raw_value == legacy.calculation.raw_value
    assert (
        homogeneous.calculation.normalized_value == legacy.calculation.normalized_value
    )

    mixed = (selected[0], observed[1])
    mixed_population = certify_field_population(
        derive_ontology_branch_population(branch, mixed)
    )
    with pytest.raises(CertificationError, match="mixes population coverage policies"):
        aggregate_ontology_branch(mixed, (mixed_population,))
    with pytest.raises(CertificationError, match="mixes population coverage policies"):
        replace(
            legacy,
            field_observations=mixed,
            field_population_proof=mixed_population,
        )
