"""Synthetic source-proof fixtures, never scientific launch evidence."""

from dataclasses import replace

import pytest
from test_bounded_launch_source_plan import launch_source_year
from test_metric_activation import complete_evidence

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.metrics.activation import assess_joint_metric_activation
from physics_atlas_api.metrics.scoped_activation import (
    SCOPED_DATASET_ACTIVATION_VERSION,
    CertifiedDatasetScope,
    certify_dataset_scope,
)


@pytest.fixture
def scope() -> CertifiedDatasetScope:
    return certify_dataset_scope(
        tuple(launch_source_year(year) for year in range(2018, 2024))
    )


def scoped_evidence(scope: CertifiedDatasetScope):  # type: ignore[no-untyped-def]
    return replace(
        complete_evidence(),
        acquisition_scope=scope.acquisition_scope,
        acquisition_boundary_kind="ontology-branch",
        data_source_version=scope.dataset_version,
        diversity_breadth_review_version=SCOPED_DATASET_ACTIVATION_VERSION,
    )


def test_scope_is_exact_source_proof_not_a_broad_physics_label(
    scope: CertifiedDatasetScope,
) -> None:
    assert scope.root_field_id == "nuclear"
    assert set(scope.leaf_field_ids) == {"nucl-th", "nucl-ex"}
    evidence = scoped_evidence(scope)
    assert not assess_joint_metric_activation(evidence).may_activate
    assert assess_joint_metric_activation(evidence, dataset_scope=scope).may_activate
    metadata = scope.release_metadata()
    assert metadata["boundaryKind"] == "ontology-branch"
    assert len(metadata["sourceYearProofs"]) == 6  # type: ignore[arg-type]
    assert "paper_projections" not in repr(metadata)


@pytest.mark.parametrize("fraction", [0.0, 0.949999])
def test_scoped_release_preserves_canonical_institution_gate(
    scope: CertifiedDatasetScope, fraction: float
) -> None:
    evidence = scoped_evidence(scope)
    evidence = replace(
        evidence, coverage=replace(evidence.coverage, canonical_institution=fraction)
    )
    result = assess_joint_metric_activation(evidence, dataset_scope=scope)
    assert not result.may_activate
    assert any("canonical institution" in reason for reason in result.reasons)


@pytest.mark.parametrize(
    "changes",
    [
        {"acquisition_scope": "hep-th-v1"},
        {"acquisition_boundary_kind": "broad-physics"},
        {"data_source_version": "another-release"},
        {"normalization_validated": False},
        {"citation_maturity_validated": False},
        {"historical_coverage_validated": False},
    ],
)
def test_scope_does_not_bypass_lineage_or_scientific_gates(
    scope: CertifiedDatasetScope, changes: dict[str, object]
) -> None:
    result = assess_joint_metric_activation(
        replace(scoped_evidence(scope), **changes), dataset_scope=scope
    )
    assert not result.may_activate


def test_scope_requires_complete_unique_exact_years(
    scope: CertifiedDatasetScope,
) -> None:
    for years in (
        (),
        scope.source_years[:-1],
        (*scope.source_years, scope.source_years[0]),
    ):
        with pytest.raises(CertificationError):
            certify_dataset_scope(years)
    with pytest.raises(CertificationError, match="does not reconstruct"):
        replace(scope, certification_digest="a" * 64)
    with pytest.raises(CertificationError, match="unsupported"):
        replace(scope, version="unbounded")


def test_boolean_or_metadata_alone_cannot_enable_scoped_activation(
    scope: CertifiedDatasetScope,
) -> None:
    with pytest.raises(ValueError, match="certified source years"):
        assess_joint_metric_activation(scoped_evidence(scope), dataset_scope=True)  # type: ignore[arg-type]
