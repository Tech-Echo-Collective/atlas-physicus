"""Bounded synthetic producer fixtures; no files, acquisition or activation."""

import json
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from unittest.mock import Mock, patch

import pytest

from physics_atlas_api.certification import (
    CertificationError,
    EvidenceCertificationDecision,
    certify_metric_window,
)
from physics_atlas_api.certification import launch_years as launch_years_module
from physics_atlas_api.certification.launch_attribution import attribute_launch_record
from physics_atlas_api.certification.launch_capture import (
    FetchedLaunchPage,
    collect_launch_year,
)
from physics_atlas_api.certification.launch_inputs import (
    canonicalize_launch_inputs,
    capture_launch_occurrence,
)
from physics_atlas_api.certification.launch_scope import bounded_launch_source_plan
from physics_atlas_api.certification.launch_years import (
    LaunchStructuralDecision,
    build_launch_source_year,
)
from physics_atlas_api.certification.measurement_windows import (
    FrozenScientificCitationPopulation,
)
from physics_atlas_api.certification.years import (
    ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
    SOURCE_YEAR_CERTIFICATION_RULE_VERSION,
    EnumeratedLaunchSourceYearEvidence,
    SourceYearEvidence,
    certify_source_year,
)
from physics_atlas_api.connectors.inspire import InspireConnector

NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)


def captured_fixture(  # type: ignore[no-untyped-def]
    *,
    unknown_field: bool = False,
    missing_date: bool = False,
    duplicate_arxiv: bool = False,
    year: int = 2020,
    record_offset: int = 0,
):
    connector = InspireConnector(Mock(), "https://inspirehep.net/api")
    plan = bounded_launch_source_plan(
        calendar_year=year, cutoff=NOW, dataset_version="test-only-launch-year"
    )
    payload = json.dumps(
        {
            "hits": {
                "total": 2,
                "hits": [
                    {
                        "id": str(index + record_offset),
                        "metadata": {
                            "control_number": index + record_offset,
                            "titles": [{"title": "Explicit synthetic launch fixture"}],
                            "preprint_date": str(year)
                            if index == 2 and missing_date
                            else f"{year}-01-09",
                            "document_type": ["article"],
                            "authors": [{"recid": str(index)}],
                            **(
                                {
                                    "arxiv_eprints": [
                                        {"value": "1803.05701"},
                                        {"value": "1806.03050"},
                                    ]
                                }
                                if duplicate_arxiv and index == 1
                                else {}
                            ),
                            "inspire_categories": [{"term": "Theory-Nucl"}]
                            + (
                                [{"term": "unknown-test-category"}]
                                if index == 2 and unknown_field
                                else []
                            ),
                        },
                    }
                    for index in (1, 2)
                ],
            }
        }
    ).encode()
    attribution = []

    def process(record, reference):  # type: ignore[no-untyped-def]
        occurrence = capture_launch_occurrence(
            record,
            reference=reference,
            connector=connector,
            dataset_version=plan.dataset_version,
        )
        attribution.append(
            attribute_launch_record(
                record,
                reference=reference,
                source_facts=occurrence.source_facts,
                institution_lookup=lambda _: None,
                ror_lookup=lambda _: None,
            )
        )

    captured = collect_launch_year(
        plan,
        connector=connector,
        fetch=lambda uri: FetchedLaunchPage(
            uri, NOW, NOW + timedelta(seconds=1), payload
        ),
        process_record=process,
    )
    return (
        captured,
        canonicalize_launch_inputs(captured.occurrences),
        tuple(attribution),
    )


def test_exact_membership_does_not_claim_affiliation_or_metric_readiness() -> None:
    captured, canonical, attributions = captured_fixture()
    built = build_launch_source_year(
        captured,
        canonical,
        attributions,
        entity_type="institution",
        evidence_cutoff=NOW + timedelta(seconds=2),
    )
    assert built.source_year is not None and built.source_year.state == "certified"
    assert built.source_year.required_coverage_kinds == ("field-classification",)
    assert (
        built.measured_counts["provider_occurrences"]
        == built.measured_counts["canonical_papers"]
        == 2
    )
    assert built.measured_counts["unresolved_institution_mass"] == 2
    assert built.measured_counts["unresolved_country_mass"] == 2
    assert built.measured_counts["unresolved_researcher_mass"] == 0
    assert built.measured_counts["field_coverage"] == 1
    assert not built.blockers
    for paper in built.source_year.evidence.paper_projections:
        assert paper.field_weight_total == 1
        assert dict(paper.unresolved_entity_mass)["institution"] == 1
        assert paper.occurrence_references[0] in {
            item.reference for item in captured.occurrences
        }
    assert all(
        item.reviewed_by is item.reviewed_at is None
        for item in built.source_year.evidence.structural_decisions
    )
    assert any(
        isinstance(item, LaunchStructuralDecision)
        for item in built.source_year.evidence.structural_decisions
    )


def test_partial_known_fields_keep_conservation_and_unknown_denominator() -> None:
    captured, canonical, attributions = captured_fixture(unknown_field=True)
    built = build_launch_source_year(
        captured,
        canonical,
        attributions,
        entity_type="country",
        evidence_cutoff=NOW + timedelta(seconds=2),
    )
    assert built.source_year is not None and built.source_year.state != "certified"
    assert built.measured_counts["field_coverage_denominator"] == 2
    assert built.measured_counts["certified_field_mass"] == 1.5
    assert built.measured_counts["field_coverage"] == 0.75
    assert built.measured_counts["unmapped_field_mass"] == 0.5
    conservation = [
        item
        for item in built.source_year.evidence.structural_decisions
        if item.evidence_kind == "field-weight-conservation"
    ]
    assert all(item.state == "certified" for item in conservation)


@pytest.mark.parametrize(
    "identity_policy", (None, ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION)
)
def test_missing_exact_date_cannot_be_dropped_to_certify_a_smaller_year(
    identity_policy: str | None,
) -> None:
    captured, canonical, attributions = captured_fixture(missing_date=True)
    built = build_launch_source_year(
        captured,
        canonical,
        attributions,
        entity_type="institution",
        evidence_cutoff=NOW + timedelta(seconds=2),
        identity_completeness_policy=identity_policy,
    )
    assert built.source_year is None
    assert (
        built.measured_counts["provider_occurrences"]
        == built.measured_counts["canonical_papers"]
        == 2
    )
    assert (
        built.measured_counts["projected_papers"]
        == built.measured_counts["exact_date_blockers"]
        == 1
    )
    assert len(built.blockers) == 1 and "exact source date" in built.blockers[0][1]


def test_source_capture_subset_cutoff_and_fraction_tampering_fail_closed() -> None:
    captured, canonical, attributions = captured_fixture()
    cutoff = NOW + timedelta(seconds=2)
    with pytest.raises(CertificationError, match="capture, cutoff"):
        build_launch_source_year(
            replace(captured, manifest_digest="a" * 64),
            canonical,
            attributions,
            entity_type="institution",
            evidence_cutoff=cutoff,
        )
    with pytest.raises(CertificationError, match="capture, cutoff"):
        build_launch_source_year(
            captured,
            canonical,
            attributions,
            entity_type="institution",
            evidence_cutoff=NOW,
        )
    with pytest.raises(CertificationError, match="canonical launch input"):
        build_launch_source_year(
            captured,
            replace(canonical, papers=canonical.papers[:-1]),
            attributions,
            entity_type="institution",
            evidence_cutoff=cutoff,
        )
    with pytest.raises(CertificationError, match="missing exact attribution"):
        build_launch_source_year(
            captured,
            canonical,
            attributions[:-1],
            entity_type="institution",
            evidence_cutoff=cutoff,
        )
    first = attributions[0]
    assert first.fractional is not None
    changed = replace(
        first,
        fractional=replace(
            first.fractional,
            shares=(replace(first.fractional.shares[0], weight=Fraction(1, 2)),),
        ),
    )
    with pytest.raises(CertificationError, match="fractions do not reconstruct"):
        build_launch_source_year(
            captured,
            canonical,
            (changed, *attributions[1:]),
            entity_type="institution",
            evidence_cutoff=cutoff,
        )


@pytest.mark.parametrize(
    "kind", ("canonical-paper-identity", "provenance-completeness")
)
def test_structural_factory_reconstructs_once_without_changing_proof_or_digest(
    kind: str,
) -> None:
    captured, canonical, attributions = captured_fixture()
    build = build_launch_source_year(
        captured,
        canonical,
        attributions,
        entity_type="institution",
        evidence_cutoff=NOW + timedelta(seconds=2),
    )
    assert build.source_year is not None
    original = next(
        item
        for item in build.source_year.evidence.structural_decisions
        if isinstance(item, LaunchStructuralDecision) and item.evidence_kind == kind
    )
    # Recreate the previous factory route: reconstruct to obtain the fields, then
    # independently reconstruct in the typed constructor. Neither route is cached.
    base = launch_years_module._structural_view(
        original.source_paper,
        original.source_projection,
        original.attribution_results,
        original.evidence_kind,
    )
    previous = LaunchStructuralDecision(
        **vars(base),
        source_paper=original.source_paper,
        source_projection=original.source_projection,
        attribution_results=original.attribution_results,
    )
    with patch.object(
        launch_years_module, "_projection", wraps=launch_years_module._projection
    ) as reconstruct:
        current = launch_years_module._structural_decision(
            original.source_paper,
            original.source_projection,
            original.attribution_results,
            original.evidence_kind,
        )
        assert reconstruct.call_count == 1
    assert current == previous == original
    assert current.decision_id == previous.decision_id == original.decision_id

    changed = replace(
        original.source_projection,
        entity_shares=(),
        unresolved_entity_mass=(
            ("researcher", 1.0),
            ("institution", 1.0),
            ("country", 1.0),
        ),
    )
    with pytest.raises(CertificationError, match="differs from scientific projection"):
        launch_years_module._structural_decision(
            original.source_paper,
            changed,
            original.attribution_results,
            original.evidence_kind,
        )
    with pytest.raises(CertificationError, match="does not reconstruct"):
        replace(current, certified_value_digest="0" * 64)


def test_enumerated_launch_year_keeps_conflicting_identity_and_full_unknown_mass() -> (
    None
):
    captured, canonical, attributions = captured_fixture(duplicate_arxiv=True)
    arguments = dict(
        entity_type="researcher", evidence_cutoff=NOW + timedelta(seconds=2)
    )
    legacy = build_launch_source_year(captured, canonical, attributions, **arguments)
    current = build_launch_source_year(
        captured,
        canonical,
        attributions,
        **arguments,
        identity_completeness_policy=ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
    )
    assert legacy.source_year is not None and current.source_year is not None
    old, new = legacy.source_year, current.source_year
    assert old.state == "insufficient_evidence"
    assert new.state == "certified"
    assert old.rule_version == SOURCE_YEAR_CERTIFICATION_RULE_VERSION
    assert new.rule_version == ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION
    assert new.evidence.paper_projections == old.evidence.paper_projections
    assert new.evidence.structural_decisions == old.evidence.structural_decisions
    assert new.evidence.partitions == old.evidence.partitions
    assert new.coverage == old.coverage
    unresolved = next(
        item
        for item in new.evidence.structural_decisions
        if item.evidence_kind == "canonical-paper-identity"
        and item.state == "needs_review"
    )
    projection = next(
        item
        for item in new.evidence.paper_projections
        if item.paper_id == unresolved.subject_id
    )
    assert unresolved.reasons == (
        "canonical strong-identifier component remains unresolved",
    )
    assert projection.entity_shares == ()
    assert dict(projection.unresolved_entity_mass) == {
        "researcher": 1,
        "institution": 1,
        "country": 1,
    }
    assert projection.field_weight_total == 1
    assert new.certification.canonical_paper_count == 2
    assert new.certification.certification_id != old.certification.certification_id
    # Removing only the new opt-in metadata reconstructs the exact old proof.
    restored_legacy = SourceYearEvidence(
        **{
            item.name: getattr(new.evidence, item.name)
            for item in fields(SourceYearEvidence)
        }
    )
    assert certify_source_year(restored_legacy, new.coverage) == old

    frozen = FrozenScientificCitationPopulation(
        (new,), NOW + timedelta(seconds=3), "inspire-preprint-date"
    )
    assert frozen.paper_projections == new.evidence.paper_projections
    assert frozen.unmeasurable_paper_ids == (unresolved.subject_id,)
    assert len(frozen.measurement_population.provider_to_canonical) == 1
    assert (
        unresolved.subject_id
        not in dict(frozen.measurement_population.provider_to_canonical).values()
    )


def test_enumerated_identity_policy_cannot_approve_conflicts_or_assign_their_mass() -> (
    None
):
    captured, canonical, attributions = captured_fixture(duplicate_arxiv=True)
    built = build_launch_source_year(
        captured,
        canonical,
        attributions,
        entity_type="institution",
        evidence_cutoff=NOW + timedelta(seconds=2),
        identity_completeness_policy=ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
    )
    assert built.source_year is not None
    evidence = built.source_year.evidence
    assert isinstance(evidence, EnumeratedLaunchSourceYearEvidence)
    unresolved = next(
        item
        for item in evidence.structural_decisions
        if item.evidence_kind == "canonical-paper-identity"
        and item.state == "needs_review"
    )
    with pytest.raises(CertificationError, match="does not reconstruct"):
        replace(unresolved, state="certified", reasons=())
    generic = EvidenceCertificationDecision(
        **{
            item.name: getattr(unresolved, item.name)
            for item in fields(EvidenceCertificationDecision)
        }
    )
    with pytest.raises(CertificationError, match="reconstructed launch source proofs"):
        replace(
            evidence,
            structural_decisions=tuple(
                generic if item == unresolved else item
                for item in evidence.structural_decisions
            ),
        )
    projection = next(
        item
        for item in evidence.paper_projections
        if item.paper_id == unresolved.subject_id
    )
    changed = replace(
        projection,
        entity_shares=(("researcher", "invented", 1),),
        unresolved_entity_mass=(("researcher", 0), ("institution", 1), ("country", 1)),
    )
    with pytest.raises(CertificationError, match="full unknown entity mass"):
        replace(
            evidence,
            paper_projections=tuple(
                changed if item == projection else item
                for item in evidence.paper_projections
            ),
        )
    with pytest.raises(CertificationError, match="exact versioned capture plan"):
        replace(evidence, identity_completeness_policy="unversioned")


def test_enumerated_identity_policy_preserves_field_and_source_affiliation_gates() -> (
    None
):
    from physics_atlas_api.certification.launch_metric_coverage import (
        certify_launch_source_coverage,
    )

    captured, canonical, attributions = captured_fixture(
        duplicate_arxiv=True, unknown_field=True
    )
    built = build_launch_source_year(
        captured,
        canonical,
        attributions,
        entity_type="institution",
        evidence_cutoff=NOW + timedelta(seconds=2),
        identity_completeness_policy=ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
    )
    assert (
        built.source_year is not None
        and built.source_year.state == "insufficient_evidence"
    )
    assert built.measured_counts["field_coverage"] == 0.75
    assert built.source_year.coverage[0].minimum == 0.90
    # Additional metric purposes still retain the entire source denominator.
    coverage = certify_launch_source_coverage(built)
    assert coverage.source_year.state == "insufficient_evidence"
    canonical_gate = next(
        item
        for item in coverage.source_year.coverage
        if item.evidence_kind == "canonical-institution"
    )
    assert (
        canonical_gate.numerator,
        canonical_gate.denominator,
        canonical_gate.minimum,
    ) == (0, 2, 0.95)
    assert (
        coverage.source_year.evidence.paper_projections
        == built.source_year.evidence.paper_projections
    )


def test_homogeneous_enumerated_windows_work_and_mixed_versions_are_rejected() -> None:
    new_years = []
    legacy_years = []
    for year in (2020, 2021, 2022):
        captured, canonical, attributions = captured_fixture(
            year=year, record_offset=(year - 2020) * 10
        )
        arguments = dict(
            entity_type="researcher", evidence_cutoff=NOW + timedelta(seconds=2)
        )
        legacy = build_launch_source_year(
            captured, canonical, attributions, **arguments
        )
        new = build_launch_source_year(
            captured,
            canonical,
            attributions,
            **arguments,
            identity_completeness_policy=ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
        )
        assert legacy.source_year is not None and new.source_year is not None
        legacy_years.append(legacy.source_year)
        new_years.append(new.source_year)
    arguments = dict(
        metric_id="research_activity_score",
        entity_type="researcher",
        terminal_year=2022,
        threshold_version="metric-validation-thresholds-v1",
    )
    assert (
        certify_metric_window(source_years=tuple(new_years), **arguments).state
        == "certified"
    )
    assert (
        certify_metric_window(source_years=tuple(legacy_years), **arguments).state
        == "certified"
    )
    mixed = (legacy_years[0], *new_years[1:])
    assert certify_metric_window(source_years=mixed, **arguments).state == "conflicted"
    with pytest.raises(CertificationError, match="mixes lineage"):
        FrozenScientificCitationPopulation(
            mixed, NOW + timedelta(seconds=3), "inspire-preprint-date"
        )
