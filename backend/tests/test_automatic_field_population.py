"""Deterministic fixture validation; not a real-data activation assessment."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from certification_helpers import certify_normalization_populations, certify_partition
from test_metric_system_v1 import paper, partition

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.fields import PHYSICS_FIELD_ONTOLOGY_V1
from physics_atlas_api.metrics.aggregation import (
    FieldPopulationEvidence,
    aggregate_physics_wide,
    certify_field_population,
    derive_automatic_field_population,
)
from physics_atlas_api.metrics.calculators import calculate_connectivity
from physics_atlas_api.metrics.presentation import (
    AtlasScaleObservation,
    apply_atlas_scale,
    bind_metric_calculation,
)


@pytest.fixture(scope="module")
def field_observations() -> tuple[AtlasScaleObservation, ...]:
    proofs = []
    for index, field in enumerate(PHYSICS_FIELD_ONTOLOGY_V1.fields):
        if field.node_kind != "field":
            continue
        source = partition(
            "institution-a",
            tuple(paper(index * 100 + offset, 2025) for offset in range(10)),
            field_id=field.id,
        )
        certified = certify_partition(source, "collaboration")
        proofs.append(
            bind_metric_calculation(calculate_connectivity(certified), certified)
        )
    return apply_atlas_scale(
        tuple(proofs),
        normalization_populations=certify_normalization_populations(tuple(proofs)),
    )


def test_exact_catalog_is_derived_without_a_fictitious_reviewer(
    field_observations: tuple[AtlasScaleObservation, ...],
) -> None:
    evidence = derive_automatic_field_population(field_observations)
    assert evidence.reviewed_by is evidence.reviewed_at is None
    assert evidence.review_state == "automatic-evidence-derived"
    assert len(evidence.field_weights) == 16
    assert {weight for _, weight in evidence.field_weights} == {1.0}
    assert evidence.source_manifest_digest == evidence.content_digest
    automatic = aggregate_physics_wide(
        field_observations, (certify_field_population(evidence),)
    )
    assert automatic[0].calculation.eligible_for_observation
    assert automatic[0].calculation.components["field_evidence_coverage"] == 1.0

    legacy = FieldPopulationEvidence(
        entity_id=evidence.entity_id,
        metric_id=evidence.metric_id,
        period=evidence.period,
        dataset_version=evidence.dataset_version,
        acquisition_scope=evidence.acquisition_scope,
        ontology_version=evidence.ontology_version,
        field_weights=evidence.field_weights,
        source_manifest_digest="0" * 64,
        review_state="reviewed-approved",
        reviewed_by="explicit-test-fixture-reviewer",
        reviewed_at=datetime(2026, 9, 5, tzinfo=UTC),
    )
    legacy = replace(legacy, source_manifest_digest=legacy.content_digest)
    reviewed = aggregate_physics_wide(
        field_observations, (certify_field_population(legacy),)
    )
    assert automatic[0].calculation == reviewed[0].calculation


@pytest.mark.parametrize("count,ready", [(1, False), (14, False), (15, True)])
def test_missing_fields_keep_full_denominator_and_unchanged_ninety_percent_gate(
    field_observations: tuple[AtlasScaleObservation, ...], count: int, ready: bool
) -> None:
    selected = field_observations[:count]
    proof = certify_field_population(derive_automatic_field_population(selected))
    result = aggregate_physics_wide(selected, (proof,))[0].calculation
    assert result.components["expected_field_count"] == 16
    assert result.components["field_evidence_coverage"] == count / 16
    assert result.eligible_for_observation is ready
    if not ready:
        assert result.normalized_value is None
        assert result.missing_reasons


def test_automatic_population_rejects_mutated_authority_and_catalog(
    field_observations: tuple[AtlasScaleObservation, ...],
) -> None:
    evidence = derive_automatic_field_population(field_observations)
    for changes in (
        {"reviewed_by": "invented-reviewer"},
        {"reviewed_at": datetime(2026, 9, 5, tzinfo=UTC)},
        {"automatic_rule_version": "arbitrary-approval-v1"},
        {"dataset_version": "different-dataset"},
        {"field_weights": evidence.field_weights[:-1]},
        {"observations": ()},
        {"source_manifest_digest": "0" * 64},
    ):
        with pytest.raises(CertificationError):
            certify_field_population(replace(evidence, **changes))  # type: ignore[arg-type]


def test_automatic_population_cannot_be_reused_for_another_input_set(
    field_observations: tuple[AtlasScaleObservation, ...],
) -> None:
    proof = certify_field_population(
        derive_automatic_field_population(field_observations)
    )
    with pytest.raises(CertificationError, match="automatic population inputs"):
        aggregate_physics_wide(field_observations[:-1], (proof,))
    with pytest.raises(CertificationError, match="duplicate fields"):
        derive_automatic_field_population(
            (field_observations[0], field_observations[0])
        )
    with pytest.raises(CertificationError, match="certified Atlas observations"):
        derive_automatic_field_population((object(),))  # type: ignore[arg-type]
