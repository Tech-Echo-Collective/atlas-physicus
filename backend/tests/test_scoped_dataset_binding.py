"""Explicit synthetic source proofs; these tests do not establish launch evidence."""

from dataclasses import replace
from datetime import timedelta

import pytest
from test_bounded_launch_source_plan import launch_source_year

from physics_atlas_api.certification import (
    CertificationError,
    CoveragePopulationEvidence,
    SourceAcquisitionPlanEvidence,
    canonical_digest,
    certify_coverage,
    certify_metric_window,
    certify_source_year,
)
from physics_atlas_api.metrics.scoped_activation import (
    CertifiedDatasetScope,
    certify_dataset_scope,
)


@pytest.fixture
def release_scope() -> CertifiedDatasetScope:
    return certify_dataset_scope(
        tuple(launch_source_year(year) for year in range(2018, 2024))
    )


def test_scope_binds_exact_source_years_and_metric_window(
    release_scope: CertifiedDatasetScope,
) -> None:
    for source in release_scope.source_years:
        assert release_scope.require_source_inventory(source) is source
    window = certify_metric_window(
        metric_id="research_activity_score",
        entity_type="researcher",
        terminal_year=2023,
        source_years=release_scope.source_years[-3:],
        threshold_version="metric-validation-thresholds-v1",
    )
    assert window.state == "certified"
    release_scope.require_metric_window(window)


def test_same_version_labels_cannot_substitute_canonical_population(
    release_scope: CertifiedDatasetScope,
) -> None:
    original = release_scope.source_years[0]
    projection = replace(
        original.evidence.paper_projections[0],
        entity_shares=(("researcher", "different-fixture-entity", 1.0),),
    )
    structural = tuple(
        replace(
            item,
            certified_value_digest=projection.decision_value_digest(item.evidence_kind),
        )
        for item in original.evidence.structural_decisions
    )
    coverage = tuple(
        certify_coverage(
            item.evidence_kind,
            tuple(
                decision
                for decision in original.evidence.coverage_decisions
                if decision.evidence_kind == item.evidence_kind
            ),
            CoveragePopulationEvidence(
                item.evidence_kind,
                item.population.units,
                item.population.formula_inputs,
                canonical_digest((projection,)),
            ),
        )
        for item in original.coverage
    )
    changed = certify_source_year(
        replace(
            original.evidence,
            paper_projections=(projection,),
            structural_decisions=structural,
        ),
        coverage,
    )
    assert (
        changed.state == "certified"
    )  # Independently valid fixture, not this scope's authority.
    assert changed.dataset_version == release_scope.dataset_version
    with pytest.raises(
        CertificationError, match="inventory, pages or acquisition recipe"
    ):
        release_scope.require_source_inventory(changed)


def test_equal_projection_digest_does_not_hide_different_pages(
    release_scope: CertifiedDatasetScope,
) -> None:
    original = release_scope.source_years[0]
    partition = original.evidence.partitions[0]
    page = partition.pages[0]  # type: ignore[attr-defined]
    # Deliberately altered compact transport fixture, not a source-origin claim.
    changed_page = replace(
        page,
        page_checksum="a" * 64,
        membership_digest=canonical_digest(
            (
                page.provider,
                page.partition_id,
                "a" * 64,
                page.response_bytes,
                page.record_checksums,
                page.version,
            )
        ),
    )
    changed_partition = replace(
        partition, pages=(changed_page,), page_checksums=(changed_page.page_checksum,)
    )
    changed = certify_source_year(
        replace(original.evidence, partitions=(changed_partition,)), original.coverage
    )
    assert changed.state == "certified"
    assert (
        changed.certification.canonical_paper_population_digest
        == original.certification.canonical_paper_population_digest
    )
    with pytest.raises(
        CertificationError, match="inventory, pages or acquisition recipe"
    ):
        release_scope.require_source_inventory(changed)


def test_equal_inventory_cannot_replace_exact_launch_query(
    release_scope: CertifiedDatasetScope,
) -> None:
    original = release_scope.source_years[0]
    plan = original.evidence.acquisition_plan
    # Explicit legacy fixture proof, not a reviewer in the production path.
    legacy = SourceAcquisitionPlanEvidence(
        plan.calendar_year,
        plan.cutoff,
        plan.dataset_version,
        plan.acquisition_scope,
        plan.partitions,
        canonical_digest(
            (
                plan.calendar_year,
                plan.cutoff,
                plan.dataset_version,
                plan.acquisition_scope,
                tuple(sorted(plan.partitions)),
            )
        ),
        "reviewed-approved",
        "explicit-test-fixture-not-a-person",
        plan.cutoff,
    )
    changed = certify_source_year(
        replace(original.evidence, acquisition_plan=legacy), original.coverage
    )
    assert changed.state == "certified"
    with pytest.raises(
        CertificationError, match="inventory, pages or acquisition recipe"
    ):
        release_scope.require_source_inventory(changed)


def test_later_horizon_cannot_relabel_non_citation_years(
    release_scope: CertifiedDatasetScope,
) -> None:
    later = tuple(
        certify_source_year(
            replace(
                source.evidence,
                cutoff=source.cutoff + timedelta(days=1),
                acquisition_plan=replace(
                    source.evidence.acquisition_plan,
                    cutoff=source.cutoff + timedelta(days=1),
                ),
            ),
            source.coverage,
        )
        for source in release_scope.source_years[-3:]
    )
    window = certify_metric_window(
        metric_id="research_activity_score",
        entity_type="researcher",
        terminal_year=2023,
        source_years=later,
        threshold_version="metric-validation-thresholds-v1",
    )
    assert window.state == "certified"
    with pytest.raises(CertificationError, match="frozen measurement bridge"):
        release_scope.require_metric_window(window)
