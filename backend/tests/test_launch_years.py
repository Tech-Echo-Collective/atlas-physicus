"""Bounded synthetic producer fixtures; no files, acquisition or activation."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from unittest.mock import Mock, patch

import pytest

from physics_atlas_api.certification import CertificationError
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
from physics_atlas_api.connectors.inspire import InspireConnector

NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)


def captured_fixture(*, unknown_field: bool = False, missing_date: bool = False):  # type: ignore[no-untyped-def]
    connector = InspireConnector(Mock(), "https://inspirehep.net/api")
    plan = bounded_launch_source_plan(
        calendar_year=2020, cutoff=NOW, dataset_version="test-only-launch-year"
    )
    payload = json.dumps(
        {
            "hits": {
                "total": 2,
                "hits": [
                    {
                        "id": str(index),
                        "metadata": {
                            "control_number": index,
                            "titles": [{"title": "Explicit synthetic launch fixture"}],
                            "preprint_date": "2020"
                            if index == 2 and missing_date
                            else "2020-01-09",
                            "document_type": ["article"],
                            "authors": [{"recid": str(index)}],
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


def test_missing_exact_date_cannot_be_dropped_to_certify_a_smaller_year() -> None:
    captured, canonical, attributions = captured_fixture(missing_date=True)
    built = build_launch_source_year(
        captured,
        canonical,
        attributions,
        entity_type="institution",
        evidence_cutoff=NOW + timedelta(seconds=2),
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
