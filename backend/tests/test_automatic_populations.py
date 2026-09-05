"""Bounded fixture proofs for evidence-derived membership, not live approval."""

from dataclasses import asdict, fields, replace
from datetime import UTC, datetime, timedelta

import pytest
from certification_helpers import certify_partition
from test_metric_system_v1 import complete_coverage, paper, partition

from physics_atlas_api.certification import (
    CertificationError,
    build_certified_metric_partition,
    canonical_digest,
)
from physics_atlas_api.certification.coverage import certify_coverage
from physics_atlas_api.certification.populations import (
    AUTOMATIC_METRIC_POPULATION_VERSION,
    METRIC_POPULATION_CERTIFICATION_VERSION,
    AutomaticCategoryUniverseEvidence,
    AutomaticMetricPopulationEvidence,
    CategoryUniverseEvidence,
    MetricPopulationEvidence,
    certify_category_universe,
    derive_category_universe,
    derive_metric_population,
    metric_population_coverage_ledger,
    wrap_certified_metric_population,
)
from physics_atlas_api.fields import PHYSICS_FIELD_ONTOLOGY_V1
from physics_atlas_api.metrics import calculate_activity_raw

_ASSESSED_AT = datetime(2026, 9, 5, tzinfo=UTC)


def _category(field_id: str):  # type: ignore[no-untyped-def]
    return derive_category_universe(
        field_id=field_id,
        dataset_version="dataset-test-v1",
        acquisition_scope="hep-th-v1",
        assessed_at=_ASSESSED_AT,
    )


def test_automatic_category_universe_binds_full_frozen_catalog() -> None:
    physics = _category("physics")
    assert physics.evidence.category_ids == tuple(
        sorted(
            item.id
            for item in PHYSICS_FIELD_ONTOLOGY_V1.fields
            if item.node_kind == "field"
        )
    )
    assert len(physics.evidence.category_ids) == 16
    assert _category("hep").evidence.category_ids == (
        "hep-ex",
        "hep-lat",
        "hep-ph",
        "hep-th",
    )
    assert _category("nuclear").evidence.category_ids == ("nucl-ex", "nucl-th")
    assert "reviewed_by" not in asdict(physics.evidence)
    assert "review_state" not in asdict(physics.evidence)
    assert certify_category_universe(physics.evidence) == physics


@pytest.mark.parametrize("field_id", ["hep-th", "cond-mat", "not-a-field"])
def test_unknown_or_leaf_category_universe_cannot_invent_subfields(
    field_id: str,
) -> None:
    with pytest.raises(CertificationError, match="ontology root|cannot be invented"):
        _category(field_id)


def test_automatic_category_universe_rejects_favorable_subset_and_stale_policy() -> (
    None
):
    evidence = _category("physics").evidence
    assert isinstance(evidence, AutomaticCategoryUniverseEvidence)
    subset = replace(evidence, category_ids=("hep-th", "hep-ph"))
    with pytest.raises(CertificationError, match="does not reconstruct"):
        certify_category_universe(
            replace(subset, source_manifest_digest=subset.content_digest)
        )
    for changed in (
        replace(evidence, assessment_version="unapproved-v2"),
        replace(evidence, category_universe_version="unapproved-ontology"),
        replace(evidence, source_manifest_digest="0" * 64),
        replace(evidence, assessed_at=_ASSESSED_AT.replace(tzinfo=None)),
    ):
        with pytest.raises(CertificationError, match="does not reconstruct"):
            certify_category_universe(changed)


@pytest.mark.parametrize(
    "metric_id", ["research_activity_score", "collaboration", "momentum"]
)
def test_automatic_population_preserves_all_source_years_and_exclusions(
    metric_id: str,
) -> None:
    legacy = certify_partition(
        partition("institution-a", (paper(1, 2025, weight=0.5),)), metric_id
    )
    window = legacy.window_proof
    automatic = derive_metric_population(
        window, entity_id="institution-a", field_id="hep-th", assessed_at=_ASSESSED_AT
    )
    evidence = automatic.certification.evidence
    assert isinstance(evidence, AutomaticMetricPopulationEvidence)
    assert automatic.certification.rule_version == AUTOMATIC_METRIC_POPULATION_VERSION
    assert (
        evidence.source_year_certification_ids
        == window.certification.source_year_certification_ids
    )
    assert len(evidence.projections) == len(window.source_years)
    assert sum(item.status == "included" for item in evidence.projections) == 1
    assert (
        sum(item.status == "excluded" for item in evidence.projections)
        == len(window.source_years) - 1
    )
    assert metric_population_coverage_ledger(
        evidence
    ) == metric_population_coverage_ledger(
        legacy.population_proof.certification.evidence
    )
    source_references = {
        item.paper_id: item.occurrence_references
        for year in window.source_years
        for item in year.evidence.paper_projections
    }
    assert all(
        item.evidence == source_references[item.subject_id]
        for item in evidence.decisions
    )
    assert all(
        item.reviewed_by is None and item.reviewed_at is None
        for item in evidence.decisions
    )
    assert "review_state" not in asdict(evidence)
    assert "reviewed_by" not in asdict(evidence)
    assert "reviewed_at" not in asdict(evidence)
    assert wrap_certified_metric_population(evidence, window) == automatic


def test_automatic_population_preserves_unresolved_mass_not_zero() -> None:
    legacy = certify_partition(
        partition(
            "institution-a",
            (paper(1, 2025, weight=0.99),),
            coverage=complete_coverage(
                paper_time_affiliation=0.99,
                canonical_institution=0.99,
                field_attribution=0.99,
            ),
        ),
        "research_activity_score",
        unresolved_entity_remainder=True,
    )
    known = derive_metric_population(
        legacy.window_proof,
        entity_id="institution-a",
        field_id="hep-th",
        assessed_at=_ASSESSED_AT,
    )
    assert metric_population_coverage_ledger(known.certification.evidence) == (
        metric_population_coverage_ledger(
            legacy.population_proof.certification.evidence
        )
    )
    absent = derive_metric_population(
        legacy.window_proof,
        entity_id="not-resolved-in-source",
        field_id="hep-th",
        assessed_at=_ASSESSED_AT,
    )
    unresolved = [
        item
        for item in absent.certification.evidence.projections
        if item.status == "unresolved"
    ]
    assert len(unresolved) == 1
    assert unresolved[0].attribution_weight == 0
    assert unresolved[0].coverage_weight == pytest.approx(0.01)
    assert len(metric_population_coverage_ledger(absent.certification.evidence)) == 1
    decision = next(
        item
        for item in absent.certification.evidence.decisions
        if item.subject_id == unresolved[0].paper_id
    )
    assert decision.state == "insufficient_evidence"
    assert decision.reasons


def test_automatic_population_rechecks_window_source_and_exact_membership() -> None:
    legacy = certify_partition(
        partition("institution-a", (paper(1, 2025),)), "research_activity_score"
    )
    window = legacy.window_proof
    auto = derive_metric_population(
        window, entity_id="institution-a", field_id="hep-th", assessed_at=_ASSESSED_AT
    )
    evidence = auto.certification.evidence
    assert isinstance(evidence, AutomaticMetricPopulationEvidence)
    omitted = evidence.projections[:-1]
    with pytest.raises(CertificationError, match="every source-window paper"):
        wrap_certified_metric_population(
            replace(
                evidence,
                projections=omitted,
                source_manifest_digest=canonical_digest(omitted),
            ),
            window,
        )
    with pytest.raises(CertificationError, match="another window or cutoff"):
        wrap_certified_metric_population(
            replace(evidence, source_window_certification_id="another-window"), window
        )
    with pytest.raises(CertificationError, match="lineage differs"):
        wrap_certified_metric_population(
            replace(
                evidence,
                source_year_certification_ids=evidence.source_year_certification_ids[
                    :-1
                ],
            ),
            window,
        )
    with pytest.raises(CertificationError, match="another window or cutoff"):
        wrap_certified_metric_population(
            replace(evidence, assessed_at=window.cutoff - timedelta(seconds=1)), window
        )
    for field_id in ("hep", "unknown-field"):
        with pytest.raises(CertificationError, match="canonical"):
            wrap_certified_metric_population(
                replace(evidence, field_id=field_id), window
            )
    # Bypass dataclass construction deliberately to prove that a typed but stale
    # source proof is re-evaluated, not trusted merely for its 'certified' label.
    bad_year = object.__new__(type(window.source_years[0]))
    original_year = window.source_years[0]
    for item in fields(original_year):
        object.__setattr__(bad_year, item.name, getattr(original_year, item.name))
    object.__setattr__(bad_year, "coverage", ())
    bad_window = replace(window, source_years=(bad_year, *window.source_years[1:]))
    with pytest.raises(CertificationError, match="does not reconstruct"):
        wrap_certified_metric_population(evidence, bad_window)


def test_automatic_population_rejects_changed_weights_reasons_and_provenance() -> None:
    legacy = certify_partition(
        partition("institution-a", (paper(1, 2025),)), "research_activity_score"
    )
    window = legacy.window_proof
    auto = derive_metric_population(
        window, entity_id="institution-a", field_id="hep-th", assessed_at=_ASSESSED_AT
    )
    evidence = auto.certification.evidence
    assert isinstance(evidence, AutomaticMetricPopulationEvidence)
    selected = next(item for item in evidence.projections if item.status == "included")
    changed = replace(selected, entity_attribution_weight=0.5, attribution_weight=0.5)
    projections = tuple(
        changed if item == selected else item for item in evidence.projections
    )
    with pytest.raises(CertificationError, match="conserved source field/entity"):
        wrap_certified_metric_population(
            replace(
                evidence,
                projections=projections,
                source_manifest_digest=canonical_digest(projections),
            ),
            window,
        )
    excluded = next(item for item in evidence.projections if item.status == "excluded")
    projections = tuple(
        replace(item, reason="a guessed reason") if item == excluded else item
        for item in evidence.projections
    )
    with pytest.raises(CertificationError, match="reason does not derive"):
        wrap_certified_metric_population(
            replace(
                evidence,
                projections=projections,
                source_manifest_digest=canonical_digest(projections),
            ),
            window,
        )
    first, second, *rest = evidence.decisions
    with pytest.raises(CertificationError, match="loses source provenance"):
        wrap_certified_metric_population(
            replace(
                evidence,
                decisions=(replace(first, evidence=second.evidence), second, *rest),
            ),
            window,
        )


def test_automatic_population_cannot_invent_leaf_diversity_catalog() -> None:
    legacy = certify_partition(
        partition(
            "institution-a",
            (paper(1, 2025, categories=(("theory", 1.0),)),),
            categories=("theory", "experiment"),
        ),
        "research_diversity",
    )
    with pytest.raises(CertificationError, match="cannot be invented"):
        derive_metric_population(
            legacy.window_proof,
            entity_id="institution-a",
            field_id="hep-th",
            assessed_at=_ASSESSED_AT,
        )
    with pytest.raises(CertificationError, match="certified source window"):
        derive_metric_population(
            None, entity_id="institution-a", field_id="hep-th", assessed_at=_ASSESSED_AT
        )  # type: ignore[arg-type]


def test_automatic_population_keeps_calculator_result_and_legacy_hash_contract() -> (
    None
):
    raw = partition("institution-a", tuple(paper(index, 2025) for index in range(10)))
    legacy = certify_partition(raw, "research_activity_score")
    legacy_evidence = legacy.population_proof.certification.evidence
    assert isinstance(legacy_evidence, MetricPopulationEvidence)
    legacy_digest = canonical_digest(legacy.population_proof.certification)
    auto = derive_metric_population(
        legacy.window_proof,
        entity_id="institution-a",
        field_id="hep-th",
        assessed_at=_ASSESSED_AT,
    )
    decisions = legacy.certification.evidence_decisions
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
                source_manifest_digest=auto.certification.projection_digest,
            ),
        )
        for item in legacy.certification.coverage
    )
    automatic_partition = build_certified_metric_partition(
        raw,
        metric_id="research_activity_score",
        decisions=decisions,
        coverage=coverage,
        window=legacy.window_proof,
        population=auto,
    )
    before, after = (
        calculate_activity_raw(legacy),
        calculate_activity_raw(automatic_partition),
    )
    assert before.raw_value == after.raw_value == 10
    assert (
        replace(
            before, certification_manifest_digest=after.certification_manifest_digest
        )
        == after
    )
    assert canonical_digest(legacy.population_proof.certification) == legacy_digest
    assert (
        legacy.population_proof.certification.rule_version
        == METRIC_POPULATION_CERTIFICATION_VERSION
    )
    assert (
        wrap_certified_metric_population(legacy_evidence, legacy.window_proof)
        == legacy.population_proof
    )
    assert "assessment_version" not in {
        item.name for item in fields(MetricPopulationEvidence)
    }
    assert "assessment_version" not in {
        item.name for item in fields(CategoryUniverseEvidence)
    }
