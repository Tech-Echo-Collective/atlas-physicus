"""Bounded synthetic policy regressions; no acquisition or public activation."""

import math
from dataclasses import asdict, replace
from datetime import UTC, datetime

import pytest
from certification_helpers import certify_normalization_populations, certify_partition
from test_branch_diversity import _fixture as branch_fixture
from test_launch_metric_coverage import _author, _build, _link
from test_metric_system_v1 import complete_coverage, paper, partition

from physics_atlas_api.certification import (
    CertificationError,
    build_certified_metric_partition,
    canonical_digest,
    certify_coverage,
)
from physics_atlas_api.certification.launch_metric_coverage import (
    certify_launch_source_coverage,
)
from physics_atlas_api.certification.populations import (
    AUTOMATIC_OBSERVED_BRANCH_DIVERSITY_POPULATION_VERSION,
    OBSERVED_ATTRIBUTION_COVERAGE_VERSION,
    POSSIBLE_ATTRIBUTION_COVERAGE_VERSION,
    derive_metric_population,
    metric_population_attribution_bounds,
    metric_population_coverage_ledger,
    metric_population_coverage_policy,
    wrap_certified_metric_population,
)
from physics_atlas_api.certification.rules import evidence_rule_version
from physics_atlas_api.metrics.calculators import calculate_activity_raw
from physics_atlas_api.metrics.dataset import _observation_payload
from physics_atlas_api.metrics.presentation import (
    apply_atlas_scale,
    bind_metric_calculation,
)

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def _legacy():  # type: ignore[no-untyped-def]
    return certify_partition(
        partition(
            "institution-a",
            tuple(paper(index, 2025, weight=0.96) for index in range(12)),
            coverage=complete_coverage(
                paper_time_affiliation=0.96,
                canonical_institution=0.96,
                field_attribution=0.96,
            ),
        ),
        "research_activity_score",
        unresolved_entity_remainder=True,
    )


def _observed(legacy, entity_id="institution-a"):  # type: ignore[no-untyped-def]
    return derive_metric_population(
        legacy.window_proof,
        entity_id=entity_id,
        field_id=legacy.partition.field_id,
        assessed_at=NOW,
        coverage_policy=OBSERVED_ATTRIBUTION_COVERAGE_VERSION,
    )


def _rebind(legacy, population):  # type: ignore[no-untyped-def]
    units = metric_population_coverage_ledger(population.certification.evidence)
    unit_ids = {item.unit_id for item in units}
    decisions = tuple(
        item
        for item in legacy.certification.evidence_decisions
        if item.subject_type != "coverage-unit" or item.subject_id in unit_ids
    )
    coverage = tuple(
        certify_coverage(
            item.evidence_kind,
            tuple(
                decision
                for decision in decisions
                if decision.decision_id in item.decision_ids
            ),
            replace(
                item.population,
                units=tuple((unit.unit_id, unit.mass) for unit in units),
                source_manifest_digest=population.certification.projection_digest,
            ),
        )
        for item in legacy.certification.coverage
    )
    return build_certified_metric_partition(
        replace(legacy.partition, coverage=complete_coverage()),
        metric_id="research_activity_score",
        decisions=decisions,
        coverage=coverage,
        window=legacy.window_proof,
        population=population,
    )


def test_opt_in_changes_denominator_not_source_unknown_mass_or_raw_calculation() -> (
    None
):
    legacy = _legacy()
    digest = canonical_digest(legacy.population_proof.certification)
    population = _observed(legacy)
    automatic_v1 = derive_metric_population(
        legacy.window_proof,
        entity_id="institution-a",
        field_id="hep-th",
        assessed_at=NOW,
    )
    assert (
        population.certification.evidence.projections
        == automatic_v1.certification.evidence.projections
    )
    assert (
        population.certification.evidence.decisions
        == automatic_v1.certification.evidence.decisions
    )
    assert (
        population.certification.certification_id
        != automatic_v1.certification.certification_id
    )
    assert (
        metric_population_coverage_policy(automatic_v1.certification.evidence)
        == POSSIBLE_ATTRIBUTION_COVERAGE_VERSION
    )
    assert (
        math.fsum(
            item.mass
            for item in metric_population_coverage_ledger(
                automatic_v1.certification.evidence
            )
        )
        == 12
    )
    assert math.fsum(
        item.mass
        for item in metric_population_coverage_ledger(population.certification.evidence)
    ) == pytest.approx(11.52)
    bounds = metric_population_attribution_bounds(population)
    assert bounds.observed_mass == pytest.approx(11.52)
    assert bounds.unresolved_possible_mass == pytest.approx(0.48)
    assert bounds.possible_mass == 12
    assert bounds.observed_paper_count == 12
    assert bounds.projection_digest == population.certification.projection_digest
    assert (
        bounds.population_certification_id == population.certification.certification_id
    )
    certified = _rebind(legacy, population)
    certified.__post_init__()  # Independent typed boundary, not just the factory.
    assert all(item.ratio == 1 for item in certified.certification.coverage)
    assert (
        calculate_activity_raw(certified).raw_value
        == calculate_activity_raw(legacy).raw_value
    )
    assert canonical_digest(legacy.population_proof.certification) == digest
    assert "coverage_policy" not in asdict(automatic_v1.certification.evidence)
    with pytest.raises(CertificationError, match="population proof does not match"):
        replace(certified, population_proof=automatic_v1)


def test_absent_entity_is_unresolved_not_zero_or_complete() -> None:
    population = _observed(_legacy(), "no-supported-institution")
    assert metric_population_coverage_ledger(population.certification.evidence) == ()
    bounds = metric_population_attribution_bounds(population)
    assert bounds.observed_mass == bounds.observed_paper_count == 0
    assert bounds.unresolved_possible_mass == pytest.approx(0.48)
    decisions = population.certification.evidence.decisions
    assert sum(item.state == "insufficient_evidence" for item in decisions) == 12
    with pytest.raises(ValueError, match="non-empty"):
        _rebind(_legacy(), population)


@pytest.mark.parametrize("kind", ["citation-observation", "collaboration-relationship"])
def test_missing_evidence_inside_observed_mass_still_fails(kind: str) -> None:
    legacy = _legacy()
    population = _observed(legacy)
    certified = _rebind(legacy, population)
    template = certified.certification.coverage[0]
    decisions = tuple(
        replace(
            item,
            evidence_kind=kind,
            state="insufficient_evidence",
            reasons=("explicit missing fixture evidence",),
            rule_version=evidence_rule_version(kind),
        )
        for item in certified.certification.evidence_decisions
        if item.decision_id in template.decision_ids
    )
    measured = certify_coverage(
        kind,
        decisions,
        replace(template.population, evidence_kind=kind, formula_inputs=()),
    )
    assert measured.denominator == pytest.approx(11.52)
    assert measured.numerator == measured.ratio == 0
    assert measured.state == "insufficient_evidence"


def test_policy_and_bound_tampering_or_source_subset_fail_closed() -> None:
    legacy = _legacy()
    population = _observed(legacy)
    evidence = population.certification.evidence
    with pytest.raises(CertificationError, match="typed evidence"):
        replace(evidence, assessment_version="unapproved-coverage")
    with pytest.raises(CertificationError, match="unsupported.*coverage policy"):
        derive_metric_population(
            legacy.window_proof,
            entity_id="institution-a",
            field_id="hep-th",
            assessed_at=NOW,
            coverage_policy="unapproved",
        )
    projections = tuple(
        replace(item, coverage_weight=item.attribution_weight)
        for item in evidence.projections
    )
    with pytest.raises(CertificationError, match="conserved source field/entity"):
        wrap_certified_metric_population(
            replace(
                evidence,
                projections=projections,
                source_manifest_digest=canonical_digest(projections),
            ),
            legacy.window_proof,
        )
    subset = evidence.projections[:-1]
    with pytest.raises(CertificationError, match="every source-window paper"):
        wrap_certified_metric_population(
            replace(
                evidence,
                projections=subset,
                source_manifest_digest=canonical_digest(subset),
            ),
            legacy.window_proof,
        )


@pytest.mark.parametrize("known", [94, 95])
def test_source_wide_canonical_95_percent_gate_is_not_replaced(known: int) -> None:
    # One bounded 100-author synthetic paper; unresolved author mass stays explicit.
    build = _build(
        [
            [
                _author(index, [_link("200")] if index < known else None)
                for index in range(100)
            ]
        ]
    )
    result = certify_launch_source_coverage(build)
    certificate = next(
        item
        for item in result.source_year.coverage
        if item.evidence_kind == "canonical-institution"
    )
    assert certificate.denominator == 1
    assert certificate.ratio == pytest.approx(known / 100)
    assert certificate.minimum == 0.95
    assert certificate.state == (
        "certified" if known == 95 else "insufficient_evidence"
    )


def test_branch_diversity_preserves_exact_field_projection_under_opt_in() -> None:
    value, decisions, coverage, window, legacy = branch_fixture()
    population = derive_metric_population(
        window,
        entity_id=value.entity_id,
        field_id="nuclear",
        assessed_at=NOW,
        coverage_policy=OBSERVED_ATTRIBUTION_COVERAGE_VERSION,
    )
    assert (
        population.certification.rule_version
        == AUTOMATIC_OBSERVED_BRANCH_DIVERSITY_POPULATION_VERSION
    )
    assert (
        population.certification.evidence.projections
        == legacy.certification.evidence.projections
    )
    assert (
        population.certification.evidence.category_universe.evidence.category_ids
        == ("nucl-ex", "nucl-th")
    )
    build_certified_metric_partition(
        value,
        metric_id="research_diversity",
        decisions=decisions,
        coverage=coverage,
        window=window,
        population=population,
    ).__post_init__()


def test_export_discloses_observed_denominator_and_unknown_bounds_not_zero() -> None:
    legacy = _legacy()
    certified = _rebind(legacy, _observed(legacy))
    proof = bind_metric_calculation(calculate_activity_raw(certified), certified)
    atlas = apply_atlas_scale(
        (proof,), normalization_populations=certify_normalization_populations((proof,))
    )[0]
    row = _observation_payload(atlas, NOW)
    disclosure = row["normalizationParameters"]["attributionCoverage"]
    assert disclosure["policyVersion"] == OBSERVED_ATTRIBUTION_COVERAGE_VERSION
    assert "not completeness" in disclosure["interpretation"]
    assert disclosure["populations"][0]["unresolved_possible_mass"] == pytest.approx(
        0.48
    )
    assert (
        row["value"] is None
    )  # Still fewer than the unchanged 30 normalization peers.
    assert row["qualityFlags"]
