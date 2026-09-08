"""PA-062 synthetic frozen source→observed reference tests, without acquisition."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlencode

import pytest

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.build_cache import bounded_build_verification_cache
from physics_atlas_api.certification.citation_sessions import (
    CitationMeasurementSession,
    capture_citation_session_page,
    explicit_citation_id_query,
)
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
from physics_atlas_api.certification.launch_years import build_launch_source_year
from physics_atlas_api.certification.measurement_windows import (
    OBSERVED_POSITIVE_FIELD_CITATION_MEMBERSHIP_VERSION,
    CertifiedObservedSessionCitationCohort,
    CertifiedSessionCitationCohort,
    FrozenScientificCitationPopulation,
    citation_reference_membership_version,
    citation_reference_result_metadata,
    session_comparison_key,
)
from physics_atlas_api.certification.years import (
    ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
    qualify_observed_release_source_year,
)
from physics_atlas_api.connectors.acquisition import AcquisitionScope
from physics_atlas_api.connectors.inspire import InspireConnector
from physics_atlas_api.metrics.calculators import citation_session_normalization_key

NOW = datetime(2026, 9, 8, tzinfo=UTC)
KEY = ("nucl-th", 2020, "article")


@pytest.fixture(autouse=True)
def bounded_cache():  # type: ignore[no-untyped-def]
    with bounded_build_verification_cache():
        yield


def _case(*, unknown_other=True, qualify=True, count=50):  # type: ignore[no-untyped-def]
    plan = bounded_launch_source_plan(
        calendar_year=2020,
        cutoff=NOW,
        dataset_version="test-only-observed-reference-v1",
    )
    connector = InspireConnector(
        Mock(),
        "https://inspirehep.net/api",
        acquisition_scope=AcquisitionScope(
            plan.acquisition_scope, "subject:Theory-Nucl or subject:Experiment-Nucl", ""
        ),
    )
    hits = [
        {
            "id": str(index),
            "metadata": {
                "control_number": index,
                "titles": [{"title": "Synthetic observed reference fixture"}],
                "preprint_date": "2020-01-09",
                "document_type": ["article"],
                "authors": [{"recid": str(index)}],
                "inspire_categories": [{"term": "Theory-Nucl"}],
                "citation_count": index + 2,
                "citation_count_without_self_citations": index,
            },
        }
        for index in range(1, count + 2)
    ]
    if unknown_other:
        hits[-1]["metadata"]["inspire_categories"] = [
            {"term": "Experiment-Nucl"},
            {"term": "unknown-test-category"},
        ]
        hits[-1]["metadata"].pop("citation_count_without_self_citations")
    payload = json.dumps(
        {"hits": {"total": len(hits), "hits": hits}, "links": {}}
    ).encode()
    attributions = []

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
    built = build_launch_source_year(
        captured,
        canonicalize_launch_inputs(captured.occurrences),
        tuple(attributions),
        entity_type="institution",
        evidence_cutoff=NOW + timedelta(seconds=2),
        identity_completeness_policy=ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
    )
    assert built.source_year is not None
    year = (
        qualify_observed_release_source_year(built.source_year)
        if qualify
        else built.source_year
    )
    population = FrozenScientificCitationPopulation(
        (year,), NOW + timedelta(seconds=3), "inspire-preprint-date"
    )
    pairs = population.measurement_population.provider_to_canonical
    ids = tuple(item[0] for item in pairs)
    page = capture_citation_session_page(
        payload,
        connector=connector,
        request_url="https://inspirehep.net/api/literature?"
        + urlencode(
            {"q": explicit_citation_id_query(ids), "page": 1, "size": len(ids)}
        ),
        requested_at=NOW + timedelta(seconds=4),
        received_at=NOW + timedelta(seconds=5),
        dataset_version=plan.dataset_version,
        calendar_year=2020,
        declared_date_basis="inspire-preprint-date",
        source_snapshot_id="test-only-observed-reference-citations",
        canonical_paper_ids=dict(pairs),
        expected_source_ids=ids,
    )
    session = CitationMeasurementSession((page,), population.measurement_population)
    return population, session


def test_observed_reference_preserves_unknown_source_and_exact_known_members() -> None:
    population, session = _case()
    with pytest.raises(CertificationError, match="unresolved source records"):
        CertifiedSessionCitationCohort(population, session, KEY)
    cohort = CertifiedObservedSessionCitationCohort(population, session, KEY)
    assert len(cohort.observations) == 50
    assert all(item.state == "certified" for item in cohort.observations)
    assert len(population.paper_projections) == len(session.pages[0].records) == 51
    metadata = cohort.reference_population_metadata
    assert metadata["sourceYearPaperCount"] == 51
    assert metadata["knownReferencePaperCount"] == 50
    assert metadata["unknownTargetMembershipPaperCount"] == 1
    assert metadata["sourceYearUnmappedFieldMass"] == 0.5
    assert metadata["completeFieldUniverse"] is False
    unknown = next(
        item for item in session.pages[0].records if item.source_record_id == "51"
    )
    assert unknown.non_self_citation_count is None and unknown.unresolved_membership
    assert (
        citation_reference_membership_version(cohort)
        == OBSERVED_POSITIVE_FIELD_CITATION_MEMBERSHIP_VERSION
    )


def test_missing_any_known_reference_member_count_still_withholds_cohort() -> None:
    population, session = _case()
    page = session.pages[0]
    changed = replace(
        page,
        records=tuple(
            replace(row, non_self_citation_count=None)
            if row.source_record_id == "1"
            else row
            for row in page.records
        ),
    )
    missing = replace(session, pages=(changed,))
    with pytest.raises(CertificationError, match="missing or immature"):
        CertifiedObservedSessionCitationCohort(population, missing, KEY)


def test_observed_reference_minimum_fifty_is_unchanged() -> None:
    population, session = _case(count=49)
    with pytest.raises(CertificationError, match="50-paper minimum"):
        CertifiedObservedSessionCitationCohort(population, session, KEY)


def test_observed_reference_cannot_be_used_with_legacy_source_authority() -> None:
    population, session = _case(qualify=False)
    with pytest.raises(CertificationError, match="conditional qualified"):
        CertifiedObservedSessionCitationCohort(population, session, KEY)


def test_changed_document_type_cannot_change_frozen_observed_membership() -> None:
    population, session = _case()
    page = session.pages[0]
    changed = replace(
        page,
        records=(replace(page.records[0], document_type="book"), *page.records[1:]),
    )
    drift = replace(session, pages=(changed,))
    with pytest.raises(CertificationError, match="document type differs"):
        CertifiedObservedSessionCitationCohort(population, drift, KEY)


def test_legacy_and_observed_reference_meanings_cannot_mix_in_comparison() -> None:
    population, session = _case(unknown_other=False)
    observed = CertifiedObservedSessionCitationCohort(population, session, KEY)
    legacy = CertifiedSessionCitationCohort(population, session, KEY)
    assert len(observed.counts) == len(legacy.counts) == 51
    with pytest.raises(CertificationError, match="mixes sessions"):
        session_comparison_key((observed, legacy))
    assert session_comparison_key((observed,))[0] == session.session_id
    with pytest.raises(CertificationError, match="conditional qualified"):
        replace(observed, reference_membership_version="unversioned")


def test_observed_metadata_and_normalization_keys_cannot_hide_universe_change() -> None:
    population, session = _case(unknown_other=False)
    observed = CertifiedObservedSessionCitationCohort(population, session, KEY)
    legacy = CertifiedSessionCitationCohort(population, session, KEY)
    metadata = citation_reference_result_metadata((observed,))
    assert metadata["citation_reference_complete_field_universe"] is False
    assert citation_reference_result_metadata((legacy,)) == {}
    with pytest.raises(CertificationError, match="meanings cannot mix"):
        citation_reference_result_metadata((observed, legacy))
    components = {
        "citation_session_id": session.session_id,
        "citation_measurement_started_at": observed.started_at.isoformat(),
        "citation_measurement_ended_at": observed.ended_at.isoformat(),
        "citation_measurement_semantics": "retrospective-measurement-window",
        "citation_cutoff": None,
    }
    result = SimpleNamespace(
        metric_id="research_impact",
        citation_policy_version=observed.policy_version,
        evidence_cutoff=(NOW + timedelta(seconds=6)).isoformat(),
        components=components,
    )
    old_key = citation_session_normalization_key(result)
    result.components = {**components, **metadata}
    new_key = citation_session_normalization_key(result)
    assert old_key == new_key[:3] and len(new_key) == 4
    result.components["citation_reference_complete_field_universe"] = True
    with pytest.raises(CertificationError, match="semantics are invalid"):
        citation_session_normalization_key(result)
    result.components = {**components, **metadata}
    result.components.pop("citation_reference_membership_version")
    with pytest.raises(CertificationError, match="version is missing"):
        citation_session_normalization_key(result)
