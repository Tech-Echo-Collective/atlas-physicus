"""Bounded synthetic source-adapter tests; no acquisition or release activation."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock
from urllib.parse import urlencode

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

from physics_atlas_api.certification import (
    CertificationError,
    CertifiedMetricWindow,
    certify_metric_window,
)
from physics_atlas_api.certification.automation import verify_automatic_source_binding
from physics_atlas_api.certification.citation_sessions import (
    CitationMeasurementSession,
    capture_citation_session_page,
    explicit_citation_id_query,
)
from physics_atlas_api.certification.launch_attribution import attribute_launch_record
from physics_atlas_api.certification.launch_calculations import (
    LaunchPaperBinding,
    LaunchPaperDecision,
    _paper,
    build_launch_metric_partition,
    calculate_launch_metric_cohort,
    certify_launch_citation_coverage,
    validate_launch_citation_window,
)
from physics_atlas_api.certification.launch_capture import (
    FetchedLaunchPage,
    collect_launch_year,
)
from physics_atlas_api.certification.launch_inputs import (
    canonicalize_launch_inputs,
    capture_launch_occurrence,
)
from physics_atlas_api.certification.launch_metric_coverage import (
    certify_launch_source_coverage,
)
from physics_atlas_api.certification.launch_scope import bounded_launch_source_plan
from physics_atlas_api.certification.launch_years import build_launch_source_year
from physics_atlas_api.certification.measurement_windows import (
    CertifiedSessionCitationCohort,
    FrozenScientificCitationPopulation,
)
from physics_atlas_api.certification.populations import (
    OBSERVED_ATTRIBUTION_COVERAGE_VERSION,
    metric_population_coverage_policy,
)
from physics_atlas_api.certification.rules import evidence_decision_is_current
from physics_atlas_api.connectors.acquisition import AcquisitionScope
from physics_atlas_api.connectors.inspire import InspireConnector
from physics_atlas_api.metrics.calculators import calculate_activity_raw

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def _year(  # type: ignore[no-untyped-def]
    year: int,
    *,
    missing_researcher: bool = False,
    paper_count: int = 2,
    uncertain_peer: bool = False,
):
    connector = InspireConnector(Mock(), "https://inspirehep.net/api")
    plan = bounded_launch_source_plan(
        calendar_year=year, cutoff=NOW, dataset_version="test-only-launch-calculations"
    )
    authors = [
        _author(index, [_link("200" if index < 4 else "201")]) for index in range(1, 6)
    ]
    if missing_researcher:
        authors[0].pop("recid")
    payload = json.dumps(
        {
            "hits": {
                "total": paper_count,
                "hits": [
                    {
                        "id": str(year * 100 + index),
                        "metadata": {
                            "control_number": year * 100 + index,
                            "titles": [{"title": "Synthetic adapter test"}],
                            "preprint_date": f"{year}-01-09",
                            "document_type": ["article"],
                            "authors": authors
                            if not uncertain_peer or index % 2
                            else [
                                _author(position, [_link("201")])
                                if position < 10
                                else _author(position)
                                for position in range(6, 11)
                            ],
                            "inspire_categories": [
                                {"term": "Theory-Nucl"},
                                {"term": "Experiment-Nucl"},
                            ],
                        },
                    }
                    for index in range(1, paper_count + 1)
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
    built = build_launch_source_year(
        captured,
        canonicalize_launch_inputs(captured.occurrences),
        tuple(attributions),
        entity_type="institution",
        evidence_cutoff=NOW + timedelta(seconds=2),
    )
    return certify_launch_source_coverage(built).source_year


@pytest.fixture(scope="module")
def source_years():  # type: ignore[no-untyped-def]
    return tuple(_year(year) for year in range(2018, 2024))


def _window(years, metric):  # type: ignore[no-untyped-def]
    return certify_metric_window(
        metric_id=metric,
        entity_type="institution",
        terminal_year=2023,
        source_years=years if metric == "momentum" else years[-3:],
        threshold_version="metric-validation-thresholds-v1",
    )


def test_source_bound_activity_keeps_fractional_mass_and_raw_thresholds(
    source_years,
) -> None:  # type: ignore[no-untyped-def]
    partition = build_launch_metric_partition(
        _window(source_years, "research_activity_score"),
        entity_id=f"institution-ror-{_ROR_A}",
        field_id="nucl-th",
    )
    assert len(partition.partition.papers) == 6
    assert sum(
        item.attribution_weight for item in partition.partition.papers
    ) == pytest.approx(1.8)
    assert (
        metric_population_coverage_policy(
            partition.population_proof.certification.evidence
        )
        == OBSERVED_ATTRIBUTION_COVERAGE_VERSION
    )
    assert partition.partition.coverage.canonical_institution == 1
    result = calculate_activity_raw(partition)
    assert result.raw_value is None
    assert result.missing_reasons
    assert all(
        item.reviewed_by is None for item in partition.certification.evidence_decisions
    )


@pytest.mark.parametrize(
    "metric,field",
    [
        ("research_activity_score", "nucl-th"),
        ("collaboration", "nucl-th"),
        ("research_diversity", "nuclear"),
        ("momentum", "nucl-th"),
    ],
)
def test_complete_peers_reach_existing_scale_without_fabricating_observations(
    source_years, metric: str, field: str
) -> None:  # type: ignore[no-untyped-def]
    values = calculate_launch_metric_cohort(
        _window(source_years, metric), field_id=field
    )
    assert {item.calculation.entity_id for item in values} == {
        f"institution-ror-{_ROR_A}",
        f"institution-ror-{_ROR_B}",
    }
    assert all(item.value is None and item.uncertainty_reasons for item in values)


def test_changed_source_bound_decision_fails_closed(source_years) -> None:  # type: ignore[no-untyped-def]
    partition = build_launch_metric_partition(
        _window(source_years, "research_activity_score"),
        entity_id=f"institution-ror-{_ROR_A}",
        field_id="nucl-th",
    )
    decision = next(
        item
        for item in partition.certification.evidence_decisions
        if isinstance(item, LaunchPaperDecision)
    )
    assert evidence_decision_is_current(decision)
    verify_automatic_source_binding(decision, decision.source_proof.source_projection)
    with pytest.raises(CertificationError, match="exact source projection"):
        verify_automatic_source_binding(
            decision,
            replace(
                decision.source_proof.source_projection, publication_date=NOW.date()
            ),
        )
    with pytest.raises(CertificationError, match="differs from source"):
        replace(decision, certified_value_digest="0" * 64)
    with pytest.raises(CertificationError):
        replace(
            decision, binding=replace(decision.binding, entity_id="invented-entity")
        )


def test_unknown_researcher_is_not_invented_and_known_tuple_remains_usable(
    source_years,
) -> None:  # type: ignore[no-untyped-def]
    years = (*source_years[:-1], _year(2023, missing_researcher=True))
    partition = build_launch_metric_partition(
        _window(years, "research_activity_score"),
        entity_id=f"institution-ror-{_ROR_A}",
        field_id="nucl-th",
    )
    papers = [
        item
        for item in partition.partition.papers
        if item.publication_date.year == 2023
    ]
    assert all(len(item.researcher_ids) == 4 for item in papers)
    assert all("inspire-author:1" not in item.researcher_ids for item in papers)
    decisions = [
        item
        for item in partition.certification.evidence_decisions
        if item.evidence_kind == "researcher-identity"
        and item.subject_id in {paper.paper_id for paper in papers}
    ]
    assert all(item.omitted_author_positions == (1,) for item in decisions)
    assert calculate_activity_raw(partition).raw_value is None


def test_missing_citation_sessions_cannot_activate_impact(source_years) -> None:  # type: ignore[no-untyped-def]
    window = _window(source_years, "research_impact")
    assert window.state != "certified"
    with pytest.raises(CertificationError, match="certified source window"):
        build_launch_metric_partition(
            window, entity_id=f"institution-ror-{_ROR_A}", field_id="nucl-th"
        )


def test_measured_source_citation_coverage_preserves_zero_and_missing_fields() -> None:
    year = _year(2020, paper_count=50)
    population = FrozenScientificCitationPopulation(
        (year,), NOW + timedelta(seconds=3), "inspire-preprint-date"
    )
    pairs = population.measurement_population.provider_to_canonical
    ids = tuple(key for key, _ in pairs)
    payload = json.dumps(
        {
            "hits": {
                "total": 50,
                "hits": [
                    {
                        "id": identifier,
                        "metadata": {
                            "titles": [{"title": "Synthetic citation bridge fixture"}],
                            "preprint_date": "2020-01-09",
                            "document_type": ["article"],
                            "inspire_categories": [
                                {"term": "Theory-Nucl"},
                                {"term": "Experiment-Nucl"},
                            ],
                            "citation_count": position + 2,
                            "citation_count_without_self_citations": position,
                        },
                    }
                    for position, identifier in enumerate(ids)
                ],
            },
            "links": {},
        }
    ).encode()
    page = capture_citation_session_page(
        payload,
        connector=InspireConnector(
            Mock(),
            "https://inspirehep.net/api",
            acquisition_scope=AcquisitionScope(
                year.acquisition_scope,
                "subject:Theory-Nucl or subject:Experiment-Nucl",
                "",
            ),
        ),
        request_url="https://inspirehep.net/api/literature?"
        + urlencode({"q": explicit_citation_id_query(ids), "page": 1, "size": 50}),
        requested_at=NOW + timedelta(seconds=4),
        received_at=NOW + timedelta(seconds=5),
        dataset_version=year.dataset_version,
        calendar_year=2020,
        end_calendar_year=2020,
        declared_date_basis="inspire-preprint-date",
        source_snapshot_id="synthetic-citation-bridge-page",
        canonical_paper_ids=dict(pairs),
        expected_source_ids=ids,
    )
    session = CitationMeasurementSession((page,), population.measurement_population)
    for changed in (
        replace(page, calendar_year=2024),
        replace(page, expected_source_ids=None),
        replace(page, declared_date_basis="arxiv-initial-submission"),
    ):
        with pytest.raises(CertificationError, match="bounded frozen IDs"):
            changed.validate()
    cohorts = tuple(
        CertifiedSessionCitationCohort(population, session, (field_id, 2020, "article"))
        for field_id in ("nucl-th", "nucl-ex")
    )
    result = certify_launch_citation_coverage(
        year, cohorts, evaluation_cutoff=NOW + timedelta(seconds=6)
    )
    coverage = next(
        item for item in result.coverage if item.evidence_kind == "citation-observation"
    )
    assert result.state == "certified"
    assert coverage.numerator == coverage.denominator == 50
    assert result.evidence.paper_projections == year.evidence.paper_projections
    # Exercise the post-reconstruction linkage hook without constructing another
    # full metric window: this does not manufacture an admissible certificate.
    linkage = SimpleNamespace(
        source_years=(result,),
        citation_cohorts=cohorts,
        certification=SimpleNamespace(metric_id="research_impact"),
    )
    validate_launch_citation_window(cast(CertifiedMetricWindow, linkage))
    linkage.citation_cohorts = cohorts[:1]
    with pytest.raises(CertificationError, match="differs from measured session"):
        validate_launch_citation_window(cast(CertifiedMetricWindow, linkage))
    assert min(item.non_self_citation_count for item in cohorts[0].observations) == 0
    observed_zero = next(
        item for item in cohorts[0].observations if item.non_self_citation_count == 0
    )
    source_proof = next(
        item
        for item in year.evidence.structural_decisions
        if item.subject_id == observed_zero.paper_id
        and item.evidence_kind == "provenance-completeness"
    )
    paper = _paper(
        source_proof,
        LaunchPaperBinding(
            "institution",
            f"institution-ror-{_ROR_A}",
            "nucl-th",
            citation_observation=observed_zero,
        ),
    )
    assert paper.citation_count == 0
    assert paper.citation_observed_at == page.received_at.date()
    missing = certify_launch_citation_coverage(
        year, cohorts[:1], evaluation_cutoff=NOW + timedelta(seconds=6)
    )
    assert missing.state == "insufficient_evidence"
    missing_coverage = next(
        item
        for item in missing.coverage
        if item.evidence_kind == "citation-observation"
    )
    assert missing_coverage.numerator == 0 and missing_coverage.denominator == 50
    with pytest.raises(CertificationError, match="measurement horizon"):
        certify_launch_citation_coverage(
            year, cohorts, evaluation_cutoff=NOW + timedelta(seconds=4)
        )
