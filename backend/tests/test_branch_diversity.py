"""Synthetic bounded proofs for an existing ontology branch, never live evidence."""

import math
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from certification_helpers import certify_partition
from test_metric_system_v1 import paper, partition

from physics_atlas_api.certification import (
    CertificationError,
    CoveragePopulationEvidence,
    build_certified_metric_partition,
    canonical_digest,
    certify_metric_window,
    certify_source_year,
    paper_evidence_value_digest,
    source_record_inventory_digest,
)
from physics_atlas_api.certification.automation import (
    AutomaticEvidenceContext,
    AutomaticFieldEvidence,
)
from physics_atlas_api.certification.coverage import certify_coverage
from physics_atlas_api.certification.fields import (
    AutomaticFieldBinding,
    automatic_field_decision,
    automatic_field_ledger,
    branch_diversity_field_projection,
    ontology_branch_category_ids,
)
from physics_atlas_api.certification.populations import (
    AUTOMATIC_BRANCH_DIVERSITY_POPULATION_VERSION,
    AutomaticMetricPopulationEvidence,
    derive_metric_population,
    metric_population_coverage_ledger,
    wrap_certified_metric_population,
)
from physics_atlas_api.certification.rules import evidence_decision_is_current
from physics_atlas_api.fields.mapping import (
    ProviderCategoryEvidence,
    ProviderFieldProjection,
)
from physics_atlas_api.metrics.calculators import calculate_diversity

_NOW = datetime(2026, 9, 5, tzinfo=UTC)
_CATEGORIES = ("nucl-ex", "nucl-th")


def _fixture():  # type: ignore[no-untyped-def]
    """Rebind small existing fixture proofs to exact automatic provider fields.

    Thirty included papers have entity share .9, nuclear mass 2/3 and outside
    HEP mass 1/3. Three additional papers belong only to HEP and must be excluded.
    Every source/reference here is synthetic test data.
    """
    original = replace(
        partition(
            "institution-a",
            tuple(
                paper(
                    index, 2023 + index % 3, weight=0.9, categories=(("nucl-th", 1.0),)
                )
                for index in range(33)
            ),
            categories=_CATEGORIES,
        ),
        field_id="nucl-th",
    )
    legacy = certify_partition(original, "research_diversity")
    outside_ids = {item.paper_id for item in original.papers[30:]}
    field_evidence: dict[str, AutomaticFieldEvidence] = {}
    source_years = []
    for year in legacy.window_proof.source_years:
        projections = []
        for source in year.evidence.paper_projections:
            reference = replace(source.occurrence_references[0], provider="arxiv")
            categories = (
                ("hep-th",)
                if source.paper_id in outside_ids
                else ("nucl-th", "nucl-ex", "hep-th")
            )
            evidence = AutomaticFieldEvidence(
                AutomaticEvidenceContext(
                    source.paper_id,
                    original.dataset_version,
                    original.acquisition_scope,
                ),
                (
                    ProviderFieldProjection(
                        "arxiv",
                        reference.source_record_id,
                        tuple(ProviderCategoryEvidence(value) for value in categories),
                        reference.source_snapshot_id,
                    ),
                ),
                (reference,),
            )
            field_evidence[source.paper_id] = evidence
            ledger = automatic_field_ledger(evidence)
            projections.append(
                replace(
                    source,
                    occurrence_references=(reference,),
                    field_weights=tuple(
                        (item.field_id, item.weight) for item in ledger.assignments
                    ),
                )
            )
        by_id = {item.paper_id: item for item in projections}
        source_digest = canonical_digest(
            tuple(sorted(projections, key=lambda item: item.paper_id))
        )
        structural = tuple(
            automatic_field_decision(
                field_evidence[item.subject_id],
                binding=AutomaticFieldBinding("source-year-ledger"),
                evidence_kind="field-weight-conservation",
            )
            if item.evidence_kind == "field-weight-conservation"
            else replace(
                item,
                evidence=by_id[item.subject_id].occurrence_references,
                certified_value_digest=by_id[item.subject_id].decision_value_digest(
                    item.evidence_kind
                ),
            )
            for item in year.evidence.structural_decisions
        )
        coverage_decisions = tuple(
            replace(item, evidence=by_id[item.subject_id].occurrence_references)
            for item in year.evidence.coverage_decisions
        )
        coverage = tuple(
            certify_coverage(
                item.evidence_kind,
                tuple(
                    decision
                    for decision in coverage_decisions
                    if decision.evidence_kind == item.evidence_kind
                ),
                replace(item.population, source_manifest_digest=source_digest),
            )
            for item in year.coverage
        )
        plan = year.evidence.acquisition_plan
        partitions = tuple((key, "arxiv") for key, _ in plan.partitions)
        plan_digest = canonical_digest(
            (
                plan.calendar_year,
                plan.cutoff,
                plan.dataset_version,
                plan.acquisition_scope,
                partitions,
            )
        )
        source_years.append(
            certify_source_year(
                replace(
                    year.evidence,
                    acquisition_plan=replace(
                        plan, partitions=partitions, source_manifest_digest=plan_digest
                    ),
                    paper_projections=tuple(projections),
                    structural_decisions=structural,
                    coverage_decisions=coverage_decisions,
                    partitions=tuple(
                        replace(
                            item,
                            provider="arxiv",
                            record_inventory_digest=source_record_inventory_digest(
                                tuple(
                                    ref
                                    for source in projections
                                    for ref in source.occurrence_references
                                )
                            ),
                        )
                        for item in year.evidence.partitions
                    ),
                ),
                coverage,
            )
        )
    window = certify_metric_window(
        metric_id="research_diversity",
        entity_type=original.entity_type,
        terminal_year=original.terminal_year,
        source_years=tuple(source_years),
        threshold_version="metric-validation-thresholds-v1",
    )
    population = derive_metric_population(
        window,
        entity_id=original.entity_id,
        field_id="nuclear",
        assessed_at=_NOW,
    )
    values = []
    for item in original.papers:
        ledger = automatic_field_ledger(field_evidence[item.paper_id])
        weight, categories = branch_diversity_field_projection(
            "nuclear",
            tuple((entry.field_id, entry.weight) for entry in ledger.assignments),
        )
        if weight > 0:
            values.append(
                replace(
                    item,
                    attribution_weight=item.attribution_weight * weight,
                    category_weights=categories,
                )
            )
    value = replace(original, field_id="nuclear", papers=tuple(values))
    by_id = {item.paper_id: item for item in values}
    decisions = []
    for decision in legacy.certification.evidence_decisions:
        if decision.subject_type != "paper" or decision.subject_id not in by_id:
            continue
        evidence = field_evidence[decision.subject_id]
        if decision.evidence_kind in {
            "field-classification",
            "field-weight-conservation",
        }:
            decisions.append(
                automatic_field_decision(
                    evidence,
                    binding=AutomaticFieldBinding(
                        "branch-diversity-paper-v1",
                        field_id="nuclear",
                        entity_attribution_weight=0.9,
                        include_category_weights=True,
                    ),
                    evidence_kind=decision.evidence_kind,
                )
            )
        else:
            decisions.append(
                replace(
                    decision,
                    evidence=evidence.references,
                    certified_value_digest=paper_evidence_value_digest(
                        value, by_id[decision.subject_id], decision.evidence_kind
                    ),
                )
            )
    coverage = []
    units = metric_population_coverage_ledger(population.certification.evidence)
    for prior in legacy.certification.coverage:
        template = next(
            item
            for item in legacy.certification.evidence_decisions
            if item.subject_type == "coverage-unit"
            and item.evidence_kind == prior.evidence_kind
        )
        kind_decisions = tuple(
            replace(
                template,
                subject_id=unit.unit_id,
                evidence=field_evidence[unit.paper_id].references,
            )
            for unit in units
        )
        decisions.extend(kind_decisions)
        coverage.append(
            certify_coverage(
                prior.evidence_kind,
                kind_decisions,
                CoveragePopulationEvidence(
                    evidence_kind=prior.evidence_kind,
                    units=tuple((unit.unit_id, unit.mass) for unit in units),
                    formula_inputs=tuple(
                        sorted(
                            (item.paper_id, item.attribution_weight) for item in values
                        )
                    ),
                    source_manifest_digest=population.certification.projection_digest,
                ),
            )
        )
    return value, tuple(decisions), tuple(coverage), window, population


def test_branch_shares_preserve_original_leaf_contribution_and_outside_mass() -> None:
    source = (("nucl-th", 0.3), ("nucl-ex", 0.2), ("hep-th", 0.4))
    weight, categories = branch_diversity_field_projection("nuclear", source)
    assert weight == 0.5
    assert dict(categories) == {"nucl-ex": 0.4, "nucl-th": 0.6}
    assert math.fsum(share for _, share in categories) == 1
    assert {key: 0.7 * weight * share for key, share in categories} == pytest.approx(
        {"nucl-th": 0.7 * 0.3, "nucl-ex": 0.7 * 0.2}
    )
    # Neither the .4 outside-branch mass nor the .1 explicitly unmapped mass
    # is reassigned. The source tuple remains byte/hash identical.
    assert source == (("nucl-th", 0.3), ("nucl-ex", 0.2), ("hep-th", 0.4))
    assert branch_diversity_field_projection("nuclear", (("hep-th", 1.0),)) == (0.0, ())
    assert ontology_branch_category_ids("nuclear") == _CATEGORIES


@pytest.mark.parametrize("field_id", ["nucl-th", "unknown", "physics"])
def test_branch_binding_cannot_invent_leaf_or_global_universe(field_id: str) -> None:
    with pytest.raises(CertificationError, match="ontology|cannot be invented"):
        branch_diversity_field_projection(field_id, (("nucl-th", 1.0),))


def test_branch_population_and_calculator_preserve_shannon_policy() -> None:
    value, decisions, coverage, window, population = _fixture()
    evidence = population.certification.evidence
    assert isinstance(evidence, AutomaticMetricPopulationEvidence)
    assert evidence.assessment_version == AUTOMATIC_BRANCH_DIVERSITY_POPULATION_VERSION
    assert (
        population.certification.rule_version
        == AUTOMATIC_BRANCH_DIVERSITY_POPULATION_VERSION
    )
    assert evidence.category_universe is not None
    assert evidence.category_universe.evidence.category_ids == _CATEGORIES
    assert len(evidence.projections) == 33
    assert sum(item.status == "included" for item in evidence.projections) == 30
    assert sum(item.status == "excluded" for item in evidence.projections) == 3
    assert math.fsum(
        item.attribution_weight for item in evidence.projections
    ) == pytest.approx(18)
    assert all(evidence_decision_is_current(item) for item in decisions)
    certified = build_certified_metric_partition(
        value,
        metric_id="research_diversity",
        decisions=decisions,
        coverage=coverage,
        window=window,
        population=population,
    )
    result = calculate_diversity(certified)
    assert result.raw_value == pytest.approx(1)
    assert result.normalized_value == pytest.approx(100)
    assert result.threshold_version == "metric-validation-thresholds-v1"
    assert wrap_certified_metric_population(evidence, window) == population


def test_branch_consumed_categories_cannot_be_reweighted_after_certification() -> None:
    value, decisions, coverage, window, population = _fixture()
    first, *rest = value.papers
    wrong = replace(
        value, papers=(replace(first, category_weights=(("nucl-th", 1.0),)), *rest)
    )
    with pytest.raises(CertificationError, match="formula input"):
        build_certified_metric_partition(
            wrong,
            metric_id="research_diversity",
            decisions=decisions,
            coverage=coverage,
            window=window,
            population=population,
        )
    with pytest.raises(CertificationError, match="exact typed evidence"):
        changed = replace(
            population.certification.evidence,
            assessment_version="source-window-metric-population-v1",
        )
        wrap_certified_metric_population(changed, window)
