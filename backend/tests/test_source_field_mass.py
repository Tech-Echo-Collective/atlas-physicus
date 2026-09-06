"""Conserved partial-field fixtures, never claims about acquired scientific data."""

from dataclasses import fields, replace

import pytest
from test_evidence_certification import _year_evidence

from physics_atlas_api.certification.automation import (
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
from physics_atlas_api.certification.field_mass import (
    SourceFieldMassPopulation,
    certify_source_field_mass,
)
from physics_atlas_api.certification.fields import (
    AUTOMATIC_FIELD_PROJECTION_RULE_VERSION,
    AutomaticFieldBinding,
    automatic_field_decision,
    automatic_field_ledger,
)
from physics_atlas_api.certification.rules import evidence_decision_is_current
from physics_atlas_api.certification.years import (
    certify_source_year,
    source_record_inventory_digest,
)
from physics_atlas_api.fields import ProviderCategoryEvidence, ProviderFieldProjection

_KNOWN = (
    "Theory-HEP",
    "Phenomenology-HEP",
    "Experiment-HEP",
    "Lattice",
    "Gravitation and Cosmology",
    "Astrophysics",
    "Theory-Nucl",
    "Experiment-Nucl",
    "Mathematical Physics",
)


def _pair(index: int = 0, known: int = 1, unknown: int = 1):  # type: ignore[no-untyped-def]
    original = _year_evidence(2022)
    paper_id = f"partial-field-paper-{index:04d}"
    reference = EvidenceReference(
        "inspire", f"record-{index}", "a" * 64, "inspire-2022"
    )
    evidence = AutomaticFieldEvidence(
        AutomaticEvidenceContext(
            paper_id, original.dataset_version, original.acquisition_scope
        ),
        (
            ProviderFieldProjection(
                "inspire",
                reference.source_record_id,
                tuple(
                    ProviderCategoryEvidence(item)
                    for item in (
                        *_KNOWN[:known],
                        *(f"Unknown category {value}" for value in range(unknown)),
                    )
                ),
                reference.source_snapshot_id,
            ),
        ),
        (reference,),
    )
    ledger = automatic_field_ledger(evidence)
    projection = replace(
        original.paper_projections[0],
        paper_id=paper_id,
        occurrence_references=(reference,),
        field_weights=tuple(
            (item.field_id, item.weight) for item in ledger.assignments
        ),
        unmapped_field_mass=ledger.unmapped_mass,
        field_weight_total=ledger.conservation_total,
    )
    return evidence, projection


def test_half_known_field_can_conserve_and_bind_only_its_actual_share() -> None:
    evidence, projection = _pair()
    structural = automatic_field_decision(
        evidence,
        binding=AutomaticFieldBinding("source-year-ledger"),
        evidence_kind="field-weight-conservation",
    )
    assert structural.state == "certified"
    assert structural.rule_version == AUTOMATIC_FIELD_PROJECTION_RULE_VERSION
    assert structural.certified_value_digest == projection.decision_value_digest(
        "field-weight-conservation"
    )
    assert (
        projection.field_weights == (("hep-th", 0.5),)
        and projection.unmapped_field_mass == 0.5
    )
    for kind in ("field-classification", "field-weight-conservation"):
        projected = automatic_field_decision(
            evidence,
            binding=AutomaticFieldBinding(
                "metric-paper", field_id="hep-th", entity_attribution_weight=0.4
            ),
            evidence_kind=kind,
        )
        assert projected.state == "certified" and evidence_decision_is_current(
            projected
        )
        assert projected.certified_value_digest == canonical_digest(
            {
                "paper_id": projection.paper_id,
                "field_id": "hep-th",
                "attribution_weight": 0.2,
                "category_weights": (),
            }
        )
    whole_paper = automatic_field_decision(
        evidence,
        binding=AutomaticFieldBinding("coverage"),
        evidence_kind="field-classification",
    )
    assert whole_paper.state == "insufficient_evidence"


def test_all_unknown_mass_conserves_but_never_becomes_metric_eligible() -> None:
    evidence, projection = _pair(known=0)
    structural = automatic_field_decision(
        evidence,
        binding=AutomaticFieldBinding("source-year-ledger"),
        evidence_kind="field-weight-conservation",
    )
    assert structural.state == "certified" and projection.unmapped_field_mass == 1
    with pytest.raises(CertificationError):
        automatic_field_decision(
            evidence,
            binding=AutomaticFieldBinding(
                "metric-paper", field_id="hep-th", entity_attribution_weight=1
            ),
            evidence_kind="field-classification",
        )
    coverage, decisions = certify_source_field_mass((evidence,), (projection,))
    assert coverage.numerator == 0 and coverage.denominator == 1
    assert coverage.state == "insufficient_evidence" and len(decisions) == 1


def test_unknown_half_stays_in_denominator_as_a_separate_withheld_binary_unit() -> None:
    evidence, projection = _pair()
    coverage, decisions = certify_source_field_mass((evidence,), (projection,))
    assert coverage.numerator == 0.5 and coverage.denominator == 1
    assert coverage.minimum == 0.9 and coverage.state == "insufficient_evidence"
    assert sorted(
        (item.certified_mass, item.denominator_mass)
        for item in coverage.decision_masses
    ) == [(0, 0.5), (0.5, 0.5)]
    assert {item.state for item in decisions} == {"certified", "insufficient_evidence"}
    assert isinstance(coverage.population, SourceFieldMassPopulation)


def test_250_paper_scenario_preserves_229_point_4_known_mass_not_206_whole_papers() -> (
    None
):
    # Synthetic arithmetic matching the observed diagnostic totals, not a replay
    # of the diagnostic's paper records:206 full +40 half +2 four-fifths +2 nine-tenths.
    pairs = (
        *(_pair(index, 1, 0) for index in range(206)),
        *(_pair(index, 1, 1) for index in range(206, 246)),
        *(_pair(index, 4, 1) for index in range(246, 248)),
        *(_pair(index, 9, 1) for index in range(248, 250)),
    )
    coverage, _ = certify_source_field_mass(
        tuple(item for item, _ in pairs), tuple(item for _, item in pairs)
    )
    assert coverage.numerator == pytest.approx(229.4)
    assert coverage.denominator == 250
    assert coverage.numerator / coverage.denominator == pytest.approx(0.9176)
    assert coverage.minimum == 0.9 and coverage.state == "certified"


def test_partial_field_mass_source_year_keeps_completeness_checks() -> None:
    original = _year_evidence(2022)
    pairs = tuple(_pair(index, 1, int(index == 9)) for index in range(10))
    projections = tuple(item for _, item in pairs)
    coverage, coverage_decisions = certify_source_field_mass(
        tuple(item for item, _ in pairs), projections
    )
    assert coverage.numerator == 9.5 and coverage.denominator == 10
    structural = tuple(
        automatic_field_decision(
            evidence,
            binding=AutomaticFieldBinding("source-year-ledger"),
            evidence_kind="field-weight-conservation",
        )
        if old.evidence_kind == "field-weight-conservation"
        else replace(
            old,
            subject_id=projection.paper_id,
            evidence=projection.occurrence_references,
            certified_value_digest=projection.decision_value_digest(old.evidence_kind),
        )
        for evidence, projection in pairs
        for old in original.structural_decisions
    )
    partition = replace(
        original.partitions[0],
        expected_unique_records=10,
        observed_records=10,
        observed_unique_records=10,
        record_inventory_digest=source_record_inventory_digest(
            tuple(ref for item in projections for ref in item.occurrence_references)
        ),
    )
    evidence = replace(
        original,
        paper_projections=projections,
        structural_decisions=structural,
        coverage_decisions=coverage_decisions,
        partitions=(partition,),
    )
    certified = certify_source_year(evidence, (coverage,))
    assert certified.state == "certified", certified.certification.reasons
    incomplete = replace(evidence, partitions=(replace(partition, complete=False),))
    assert certify_source_year(incomplete, (coverage,)).state != "certified"


def test_unknown_unit_cannot_be_dropped_or_promoted_to_certified() -> None:
    evidence, projection = _pair()
    coverage, decisions = certify_source_field_mass((evidence,), (projection,))
    with pytest.raises(CertificationError):
        replace(coverage.population, units=coverage.population.units[:1])
    with pytest.raises(CertificationError):
        certify_coverage("field-classification", decisions[:1], coverage.population)
    unknown = next(item for item in decisions if item.state != "certified")
    with pytest.raises(CertificationError):
        replace(unknown, state="certified", reasons=())


def test_typed_proof_cannot_be_stripped_or_rebound_to_another_source_field() -> None:
    evidence, projection = _pair()
    coverage, decisions = certify_source_field_mass((evidence,), (projection,))
    bare_population = CoveragePopulationEvidence(
        **{
            item.name: getattr(coverage.population, item.name)
            for item in fields(CoveragePopulationEvidence)
        }
    )
    with pytest.raises(CertificationError):
        certify_coverage("field-classification", decisions, bare_population)
    base = EvidenceCertificationDecision(
        **{
            item.name: getattr(decisions[0], item.name)
            for item in fields(EvidenceCertificationDecision)
        }
    )
    assert not evidence_decision_is_current(base)
    altered = replace(projection, field_weights=(("gr-qc", 0.5),))
    with pytest.raises(CertificationError):
        certify_source_field_mass((evidence,), (altered,))


def test_source_universe_and_ratio_cannot_be_cherry_picked() -> None:
    first, first_projection = _pair(0)
    second, second_projection = _pair(1)
    with pytest.raises(CertificationError):
        certify_source_field_mass((first,), (first_projection, second_projection))
    coverage, _ = certify_source_field_mass(
        (first, second), (first_projection, second_projection)
    )
    with pytest.raises(CertificationError):
        replace(coverage.population, formula_inputs=((first_projection.paper_id, 1.0),))
