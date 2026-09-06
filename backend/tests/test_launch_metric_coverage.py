"""Synthetic bounded source coverage; no provider access, writes or activation."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from unittest.mock import Mock

import pytest
from test_launch_attribution import (
    _ROR_A,
    _ROR_B,
    _author,
    _institution,
    _link,
    _lookup,
    _ror,
)

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.contracts import CoveragePopulationEvidence
from physics_atlas_api.certification.coverage import certify_coverage
from physics_atlas_api.certification.launch_attribution import attribute_launch_record
from physics_atlas_api.certification.launch_capture import (
    FetchedLaunchPage,
    collect_launch_year,
)
from physics_atlas_api.certification.launch_inputs import (
    canonicalize_launch_inputs,
    capture_launch_occurrence,
)
from physics_atlas_api.certification.launch_metric_coverage import (
    SourceAttributionMassPopulation,
    certify_launch_source_coverage,
    certify_source_attribution_mass,
    launch_relationship_status,
)
from physics_atlas_api.certification.launch_scope import bounded_launch_source_plan
from physics_atlas_api.certification.launch_years import (
    LaunchStructuralDecision,
    build_launch_source_year,
)
from physics_atlas_api.certification.years import certify_source_year
from physics_atlas_api.connectors.inspire import InspireConnector

NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)


def _build(author_lists):  # type: ignore[no-untyped-def]
    connector = InspireConnector(Mock(), "https://inspirehep.net/api")
    plan = bounded_launch_source_plan(
        calendar_year=2020, cutoff=NOW, dataset_version="test-only-launch-coverage"
    )
    payload = json.dumps(
        {
            "hits": {
                "total": len(author_lists),
                "hits": [
                    {
                        "id": str(index),
                        "metadata": {
                            "control_number": index,
                            "titles": [
                                {"title": "Explicit synthetic coverage fixture"}
                            ],
                            "preprint_date": "2020-01-09",
                            "document_type": ["article"],
                            "authors": authors,
                            "inspire_categories": [{"term": "Theory-Nucl"}],
                        },
                    }
                    for index, authors in enumerate(author_lists, start=1)
                ],
            }
        }
    ).encode()
    attributions = []
    institutions = _lookup((_institution("200", _ROR_A), _institution("201", _ROR_B)))
    rors = _lookup((_ror(_ROR_A), _ror(_ROR_B)))

    def process(record, reference):  # type: ignore[no-untyped-def]
        occurrence = capture_launch_occurrence(
            record,
            reference=reference,
            connector=connector,
            dataset_version=plan.dataset_version,
        )
        attributions.append(
            attribute_launch_record(
                record,
                reference=reference,
                source_facts=occurrence.source_facts,
                institution_lookup=institutions,
                ror_lookup=rors,
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
    return build_launch_source_year(
        captured,
        canonicalize_launch_inputs(captured.occurrences),
        tuple(attributions),
        entity_type="institution",
        evidence_cutoff=NOW + timedelta(seconds=2),
    )


def _proofs(build):  # type: ignore[no-untyped-def]
    assert build.source_year is not None
    return tuple(
        item
        for item in build.source_year.evidence.structural_decisions
        if isinstance(item, LaunchStructuralDecision)
        and item.evidence_kind == "provenance-completeness"
    )


def test_partial_affiliation_and_canonical_mass_keep_full_paper_denominator() -> None:
    original = _build(
        [
            [_author(1, [_link("200")]), _author(2)],
            [_author(3, [{"value": "Unresolved synthetic paper-native affiliation"}])],
        ]
    )
    result = certify_launch_source_coverage(original)
    measurements = {
        kind: (numerator, denominator, ratio)
        for kind, numerator, denominator, ratio in result.measured_coverage
    }
    assert measurements["paper-time-affiliation"] == (1.5, 2, 0.75)
    assert measurements["canonical-institution"] == (0.5, 2, 0.25)
    assert measurements["collaboration-relationship"] == (0, 2, 0)
    assert result.source_year.state == "insufficient_evidence"
    assert original.source_year is not None
    assert (
        result.source_year.evidence.paper_projections
        == original.source_year.evidence.paper_projections
    )
    assert (
        result.source_year.evidence.partitions
        == original.source_year.evidence.partitions
    )
    for certificate in result.source_year.coverage:
        if isinstance(certificate.population, SourceAttributionMassPopulation):
            assert sum(mass for _, mass in certificate.population.units) == 2
            assert certificate.minimum == (
                0.95 if certificate.evidence_kind == "canonical-institution" else 0.9
            )
    assert all(
        item.reviewed_by is None and item.reviewed_at is None
        for item in result.source_year.evidence.coverage_decisions
    )


def test_complete_single_institution_is_known_negative_not_missing() -> None:
    original = _build([[_author(1, [_link("200")]), _author(2, [_link("200")])]])
    proof = _proofs(original)[0]
    assert launch_relationship_status(proof, "institution") is False
    assert launch_relationship_status(proof, "country") is False
    assert launch_relationship_status(proof, "researcher") is True
    result = certify_launch_source_coverage(original)
    assert result.source_year.state == "certified"
    assert all(ratio == 1 for _, _, _, ratio in result.measured_coverage)


def test_supported_positive_is_not_changed_by_an_unknown_affiliation() -> None:
    original = _build(
        [[_author(1, [_link("200")]), _author(2, [_link("201")]), _author(3)]]
    )
    proof = _proofs(original)[0]
    assert launch_relationship_status(proof, "institution") is True
    assert launch_relationship_status(proof, "country") is None
    result = certify_launch_source_coverage(original)
    measurements = {kind: ratio for kind, _, _, ratio in result.measured_coverage}
    assert measurements["collaboration-relationship"] == 1
    assert measurements["canonical-institution"] == pytest.approx(2 / 3)
    assert result.source_year.state != "certified"


def test_mass_and_proof_tampering_or_generic_population_relabel_fail_closed() -> None:
    original = _build([[_author(1, [_link("200")]), _author(2)]])
    proof = _proofs(original)[0]
    certificate, decisions = certify_source_attribution_mass(
        (proof,), entity_type="institution", evidence_kind="canonical-institution"
    )
    with pytest.raises(CertificationError, match="units or full denominator"):
        replace(certificate.population, units=certificate.population.units[:-1])
    with pytest.raises(CertificationError, match="exact typed population"):
        certify_coverage(
            "canonical-institution",
            decisions,
            CoveragePopulationEvidence(
                certificate.population.evidence_kind,
                certificate.population.units,
                certificate.population.formula_inputs,
                certificate.population.source_manifest_digest,
            ),
        )
    with pytest.raises(CertificationError, match="fractions do not reconstruct"):
        replace(
            proof,
            attribution_results=(
                replace(
                    proof.attribution_results[0],
                    paper_time_affiliation_weight=Fraction(1),
                ),
            ),
        )
    with pytest.raises(CertificationError, match="cannot precede"):
        certify_launch_source_coverage(original, evaluation_cutoff=NOW)


def test_subset_population_cannot_certify_the_full_frozen_source_year() -> None:
    original = _build(
        [
            [_author(1, [_link("200")])],
            [_author(2)],
        ]
    )
    result = certify_launch_source_coverage(
        original, required_kinds=("canonical-institution",)
    )
    proof = next(
        item
        for item in _proofs(original)
        if item.attribution_results[0].fractional.allocated_weight == 1
    )
    partial, decisions = certify_source_attribution_mass(
        (proof,), entity_type="institution", evidence_kind="canonical-institution"
    )
    evidence = result.source_year.evidence
    altered = certify_source_year(
        replace(
            evidence,
            coverage_decisions=tuple(
                item
                for item in evidence.coverage_decisions
                if item.evidence_kind != "canonical-institution"
            )
            + decisions,
        ),
        tuple(
            item
            for item in result.source_year.coverage
            if item.evidence_kind != "canonical-institution"
        )
        + (partial,),
    )
    assert altered.state == "conflicted"
    assert (
        "source-year attribution mass does not bind its full canonical universe"
        in altered.certification.reasons
    )


def test_coverage_evaluation_preserves_original_times_and_membership() -> None:
    original = _build([[_author(1, [_link("200")])]])
    result = certify_launch_source_coverage(
        original, evaluation_cutoff=NOW + timedelta(minutes=5)
    )
    assert original.source_year is not None
    assert result.source_year.cutoff == NOW + timedelta(minutes=5)
    assert (
        result.source_year.evidence.partitions
        == original.source_year.evidence.partitions
    )
    assert (
        result.source_year.certification.canonical_paper_population_digest
        == original.source_year.certification.canonical_paper_population_digest
    )
    assert (
        result.source_year.evidence.structural_decisions
        == original.source_year.evidence.structural_decisions
    )
