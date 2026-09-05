from dataclasses import fields, replace
from datetime import UTC, datetime

import pytest
from certification_helpers import certify_partition
from test_evidence_certification import _coverage, _year_evidence
from test_metric_system_v1 import paper, partition

from physics_atlas_api.certification.automation import (
    AUTOMATIC_DATE_RULE_VERSION,
    AUTOMATIC_FIELD_RULE_VERSION,
    AutomaticEvidenceContext,
    AutomaticFieldEvidence,
)
from physics_atlas_api.certification.contracts import (
    CertificationError,
    CoveragePopulationEvidence,
    EvidenceCertificationDecision,
    EvidenceReference,
    canonical_digest,
)
from physics_atlas_api.certification.coverage import certify_coverage
from physics_atlas_api.certification.fields import (
    AutomaticFieldBinding,
    AutomaticFieldDecision,
    FieldWeight,
    automatic_field_decision,
    automatic_field_ledger,
    certify_field_ledger,
)
from physics_atlas_api.certification.materialization import (
    build_certified_metric_partition,
)
from physics_atlas_api.certification.rules import evidence_decision_is_current
from physics_atlas_api.certification.years import (
    automatic_source_acquisition_plan,
    certify_source_year,
)
from physics_atlas_api.fields.mapping import (
    ProviderCategoryEvidence,
    ProviderFieldProjection,
)
from physics_atlas_api.metrics.calculators import calculate_activity_raw


def evidence(
    paper_id: str = "paper-2022-1",
    *,
    category: str = "Theory-HEP",
    dataset: str = "paired-trial-v1",
    scope: str = "paired-field-trial-v1",
    source: EvidenceReference | None = None,
) -> AutomaticFieldEvidence:
    reference = source or EvidenceReference("inspire", paper_id, "a" * 64, "snapshot-1")
    return AutomaticFieldEvidence(
        AutomaticEvidenceContext(paper_id, dataset, scope),
        (
            ProviderFieldProjection(
                "inspire",
                reference.source_record_id,
                (ProviderCategoryEvidence(category),),
                reference.source_snapshot_id,
            ),
        ),
        (reference,),
    )


def test_opt_in_field_boundary_consumes_exact_automatic_ledger_without_reviewer() -> (
    None
):
    ledger = automatic_field_ledger(evidence())
    result = certify_field_ledger(ledger)
    assert result.state == "certified"
    assert result.rule_version == AUTOMATIC_FIELD_RULE_VERSION
    assert ledger.reviewed_by is None and ledger.reviewed_at is None
    assert ledger.review_state == "machine-assessed"
    with pytest.raises(CertificationError, match="differs from exact provider"):
        replace(ledger, assignments=(FieldWeight("gr-qc", 1.0),))


def test_unknown_field_mass_cannot_pass_existing_coverage_threshold() -> None:
    decision = automatic_field_decision(
        evidence(category="Unmapped category"),
        binding=AutomaticFieldBinding("coverage"),
        evidence_kind="field-classification",
    )
    result = certify_coverage(
        "field-classification",
        (decision,),
        CoveragePopulationEvidence(
            "field-classification", ((decision.subject_id, 1.0),), (), "a" * 64
        ),
    )
    assert result.state == "insufficient_evidence"
    assert result.numerator == 0 and result.denominator == 1
    assert result.minimum == 0.9


def test_rule_name_without_typed_reconstructed_proof_does_not_admit_evidence() -> None:
    automatic = automatic_field_decision(
        evidence(),
        binding=AutomaticFieldBinding("coverage"),
        evidence_kind="field-classification",
    )
    assert evidence_decision_is_current(automatic)
    bare = EvidenceCertificationDecision(
        **{
            item.name: getattr(automatic, item.name)
            for item in fields(EvidenceCertificationDecision)
        }
    )
    assert not evidence_decision_is_current(bare)
    assert not evidence_decision_is_current(
        replace(bare, rule_version=AUTOMATIC_DATE_RULE_VERSION)
    )
    with pytest.raises(CertificationError, match="does not reconstruct"):
        replace(automatic, certified_value_digest="b" * 64)


def test_exact_auto_field_proofs_feed_existing_source_year_and_coverage_checks() -> (
    None
):
    original = _year_evidence(2022)
    source = original.paper_projections[0].occurrence_references[0]
    source_evidence = evidence(source=source)
    structural = automatic_field_decision(
        source_evidence,
        binding=AutomaticFieldBinding("source-year-ledger"),
        evidence_kind="field-weight-conservation",
    )
    coverage_decision = automatic_field_decision(
        source_evidence,
        binding=AutomaticFieldBinding("coverage"),
        evidence_kind="field-classification",
    )
    assert structural.certified_value_digest == original.paper_projections[
        0
    ].decision_value_digest("field-weight-conservation")
    coverage = certify_coverage(
        "field-classification",
        (coverage_decision,),
        CoveragePopulationEvidence(
            "field-classification",
            ((structural.subject_id, 1.0),),
            ((structural.subject_id, 1.0),),
            canonical_digest(original.paper_projections),
        ),
    )
    changed = replace(
        original,
        structural_decisions=tuple(
            structural if item.evidence_kind == "field-weight-conservation" else item
            for item in original.structural_decisions
        ),
        coverage_decisions=(coverage_decision,),
    )
    assert certify_source_year(changed, (coverage,)).state == "certified"
    missing = replace(
        changed,
        partitions=tuple(replace(item, complete=False) for item in changed.partitions),
    )
    assert certify_source_year(missing, (coverage,)).state != "certified"


def test_activity_accepts_bound_auto_fields_without_formula_change() -> None:
    value = partition(
        "institution-a", tuple(paper(index, 2023 + index % 3) for index in range(30))
    )
    legacy = certify_partition(value, "research_activity_score")
    changed = []
    for decision in legacy.certification.evidence_decisions:
        if decision.subject_type == "paper" and decision.evidence_kind in {
            "field-classification",
            "field-weight-conservation",
        }:
            changed.append(
                automatic_field_decision(
                    evidence(
                        decision.subject_id,
                        dataset=value.dataset_version,
                        scope=value.acquisition_scope,
                    ),
                    binding=AutomaticFieldBinding(
                        "metric-paper", field_id="hep-th", entity_attribution_weight=1.0
                    ),
                    evidence_kind=decision.evidence_kind,
                )
            )
        else:
            changed.append(decision)
    result = build_certified_metric_partition(
        value,
        metric_id="research_activity_score",
        decisions=tuple(changed),
        coverage=legacy.certification.coverage,
        window=legacy.window_proof,
        population=legacy.population_proof,
    )
    assert (
        calculate_activity_raw(result).raw_value
        == calculate_activity_raw(legacy).raw_value
        == 30
    )
    auto = next(item for item in changed if isinstance(item, AutomaticFieldDecision))
    different_value = automatic_field_decision(
        auto.automatic_field_evidence,
        binding=AutomaticFieldBinding(
            "metric-paper", field_id="hep-th", entity_attribution_weight=0.5
        ),
        evidence_kind=auto.evidence_kind,
    )
    with pytest.raises(CertificationError, match="formula input"):
        build_certified_metric_partition(
            value,
            metric_id="research_activity_score",
            decisions=tuple(
                different_value if item is auto else item for item in changed
            ),
            coverage=legacy.certification.coverage,
            window=legacy.window_proof,
            population=legacy.population_proof,
        )


def test_source_plan_is_derived_not_reviewed_and_is_not_year_completeness() -> None:
    plan = automatic_source_acquisition_plan(
        calendar_year=2022,
        cutoff=datetime(2026, 9, 5, tzinfo=UTC),
        dataset_version="paired-trial-v1",
        acquisition_scope="hep-th-v1",
    )
    assert len(plan.partitions) == 2
    assert not hasattr(plan, "reviewed_by")
    assert "submission-year" in plan.query_partitions[1].query_version
    with pytest.raises(CertificationError, match="exact fixed query recipe"):
        replace(plan, query_partitions=plan.query_partitions[:1])
    altered = replace(plan.query_partitions[0], query="different query")
    with pytest.raises(CertificationError, match="exact fixed query recipe"):
        replace(plan, query_partitions=(altered, plan.query_partitions[1]))
    year = _year_evidence(2022)
    # Existing fixture source/partition IDs do not match this actual provider plan.
    changed = replace(
        year,
        acquisition_scope="hep-th-v1",
        cutoff=plan.cutoff,
        acquisition_plan=plan,
        structural_decisions=tuple(
            replace(item, acquisition_scope="hep-th-v1")
            for item in year.structural_decisions
        ),
        coverage_decisions=tuple(
            replace(item, acquisition_scope="hep-th-v1")
            for item in year.coverage_decisions
        ),
    )
    assert certify_source_year(changed, _coverage(2022)).state != "certified"


@pytest.mark.parametrize("year", [2019, 2026])
def test_automatic_plan_does_not_extend_approved_years(year: int) -> None:
    with pytest.raises(ValueError):
        automatic_source_acquisition_plan(
            calendar_year=year,
            cutoff=datetime(2026, 9, 5, tzinfo=UTC),
            dataset_version="fixture-v1",
            acquisition_scope="hep-th-v1",
        )
