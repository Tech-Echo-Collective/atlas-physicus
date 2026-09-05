"""Synthetic, in-memory source→measurement→Impact integration fixtures only.

Numeric INSPIRE-shaped IDs exercise the real parser contract; no network or real
provider evidence is used and no scientific fixtures are persisted by these tests.
"""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock
from urllib.parse import urlencode

import pytest
from certification_helpers import certify_partition
from test_metric_system_v1 import paper, partition

from physics_atlas_api.certification import (
    CERTIFICATION_POLICY_VERSION,
    CITATION_CERTIFICATION_RULE_VERSION,
    FIELD_CERTIFICATION_RULE_VERSION,
    INSTITUTION_CERTIFICATION_RULE_VERSION,
    CertificationError,
    CoveragePopulationEvidence,
    EvidenceCertificationDecision,
    EvidenceKind,
    EvidenceReference,
    SourcePartitionEvidence,
    build_certified_metric_partition,
    canonical_digest,
    certify_coverage,
    certify_metric_window,
    certify_source_year,
    paper_evidence_value_digest,
    required_coverage_evidence,
    required_paper_evidence,
    source_record_inventory_digest,
)
from physics_atlas_api.certification.citation_sessions import (
    CitationMeasurementSession,
    capture_citation_session_page,
    explicit_citation_id_query,
)
from physics_atlas_api.certification.measurement_windows import (
    SESSION_CITATION_POLICY_VERSION,
    CertifiedSessionCitationCohort,
    FrozenScientificCitationPopulation,
    partition_citation_policy_is_current,
    require_session_cohort,
    session_comparison_key,
)
from physics_atlas_api.certification.populations import (
    derive_metric_population,
    metric_population_coverage_ledger,
)
from physics_atlas_api.certification.years import CertifiedSourceYear
from physics_atlas_api.connectors.inspire import InspireConnector
from physics_atlas_api.metrics import calculate_impact_raw

_YEARS = (2020, 2021, 2022)
_BEFORE = datetime(2026, 9, 4, 23, 50, tzinfo=UTC)
_FREEZE = datetime(2026, 9, 4, 23, 55, tzinfo=UTC)
_START = datetime(2026, 9, 4, 23, 59, 57, tzinfo=UTC)
_AFTER = datetime(2026, 9, 5, 0, 1, tzinfo=UTC)


def _rule(kind: EvidenceKind) -> str:
    return {
        "canonical-institution": INSTITUTION_CERTIFICATION_RULE_VERSION,
        "field-classification": FIELD_CERTIFICATION_RULE_VERSION,
        "field-weight-conservation": FIELD_CERTIFICATION_RULE_VERSION,
        "citation-observation": CITATION_CERTIFICATION_RULE_VERSION,
        "citation-cutoff-compatibility": CITATION_CERTIFICATION_RULE_VERSION,
    }.get(kind, CERTIFICATION_POLICY_VERSION)


def _recertify_year(
    original: CertifiedSourceYear,
    *,
    cutoff: datetime,
    metric_id: str,
    inspire_refs: bool = False,
    no_provider_last: bool = False,
    citation_refs: dict[str, EvidenceReference] | None = None,
) -> CertifiedSourceYear:
    old = original.evidence
    projections = old.paper_projections
    if inspire_refs:
        projections = tuple(
            replace(
                item,
                occurrence_references=(
                    replace(
                        item.occurrence_references[0],
                        provider=(
                            "arxiv"
                            if no_provider_last and index == len(projections) - 1
                            else "inspire"
                        ),
                        source_record_id=str(old.calendar_year * 1000 + index + 1),
                        source_snapshot_id=(
                            f"synthetic-source-{old.calendar_year}-arxiv"
                            if no_provider_last and index == len(projections) - 1
                            else f"synthetic-source-{old.calendar_year}-inspire"
                        ),
                    ),
                ),
            )
            for index, item in enumerate(projections)
        )
    by_paper = {item.paper_id: item for item in projections}
    groups: dict[tuple[str, str], list[EvidenceReference]] = {}
    for item in projections:
        for ref in item.occurrence_references:
            assert ref.source_snapshot_id is not None
            groups.setdefault((ref.source_snapshot_id, ref.provider), []).append(ref)
    planned = tuple(sorted(groups))
    plan = replace(
        old.acquisition_plan,
        cutoff=cutoff,
        partitions=planned,
        reviewed_at=cutoff,
        source_manifest_digest=canonical_digest(
            (
                old.calendar_year,
                cutoff,
                old.dataset_version,
                old.acquisition_scope,
                planned,
            )
        ),
    )
    partitions = tuple(
        SourcePartitionEvidence(
            partition_id=key[0],
            provider=key[1],
            expected_unique_records=len(refs),
            observed_records=len(refs),
            observed_unique_records=len(refs),
            duplicate_records=0,
            truncated=False,
            page_checksums=tuple(sorted({item.checksum for item in refs})),
            record_inventory_digest=source_record_inventory_digest(tuple(refs)),
            complete=True,
        )
        for key, refs in sorted(groups.items())
    )
    structural = tuple(
        replace(
            item,
            evidence=by_paper[item.subject_id].occurrence_references,
            certified_value_digest=by_paper[item.subject_id].decision_value_digest(
                item.evidence_kind
            ),
        )
        for item in old.structural_decisions
    )
    required = required_coverage_evidence(metric_id, "institution")
    decisions = tuple(
        EvidenceCertificationDecision(
            subject_type="coverage-unit",
            subject_id=item.paper_id,
            evidence_kind=kind,
            state="certified",
            rule_version=_rule(kind),
            dataset_version=old.dataset_version,
            acquisition_scope=old.acquisition_scope,
            evidence=(
                (citation_refs[item.paper_id],)
                if kind == "citation-observation" and citation_refs
                else item.occurrence_references
            ),
        )
        for kind in required
        for item in projections
    )
    digest = canonical_digest(
        tuple(sorted(projections, key=lambda item: item.paper_id))
    )
    units = tuple(
        (item.paper_id, 1.0)
        for item in sorted(projections, key=lambda item: item.paper_id)
    )
    coverage = tuple(
        certify_coverage(
            kind,
            tuple(item for item in decisions if item.evidence_kind == kind),
            CoveragePopulationEvidence(kind, units, units, digest),
        )
        for kind in required
    )
    certified = certify_source_year(
        replace(
            old,
            cutoff=cutoff,
            acquisition_plan=plan,
            required_partition_ids=tuple(key[0] for key in planned),
            required_coverage_kinds=required,
            paper_projections=projections,
            partitions=partitions,
            structural_decisions=structural,
            coverage_decisions=decisions,
        ),
        coverage,
    )
    assert certified.state == "certified", certified.certification.reasons
    return certified


def _population(
    count: int = 50, *, no_provider_last: bool = False
) -> FrozenScientificCitationPopulation:
    fixture = certify_partition(
        partition(
            "institution-a",
            tuple(paper(index, year) for year in _YEARS for index in range(count)),
            terminal_year=2022,
            as_of_date=_BEFORE.date(),
            complete_years=_YEARS,
        ),
        "research_activity_score",
    )
    years = tuple(
        _recertify_year(
            item,
            cutoff=_BEFORE,
            metric_id="research_activity_score",
            inspire_refs=True,
            no_provider_last=no_provider_last,
        )
        for item in fixture.window_proof.source_years
    )
    return FrozenScientificCitationPopulation(years, _FREEZE, "inspire-preprint-date")


def _session(
    population: FrozenScientificCitationPopulation,
) -> CitationMeasurementSession:
    inventory = population.measurement_population.provider_to_canonical
    sources = {item.paper_id: item for item in population.paper_projections}
    midpoint = (len(inventory) + 1) // 2
    batches = (inventory[:midpoint], inventory[midpoint:])
    transport = Mock()
    connector = InspireConnector(transport, "https://inspirehep.net/api")
    pages = []
    for batch_index, batch in enumerate(batches):
        ids = tuple(item[0] for item in batch)
        payload = {
            "hits": {
                "total": len(batch),
                "hits": [
                    {
                        "id": source_id,
                        "metadata": {
                            "titles": [
                                {"title": (f"Synthetic measurement fixture {paper_id}")}
                            ],
                            "preprint_date": sources[
                                paper_id
                            ].publication_date.isoformat(),
                            "document_type": ["article"],
                            "inspire_categories": [{"term": "Theory-HEP"}],
                            "citation_count": int(source_id) % 1000 + 2,
                            "citation_count_without_self_citations": int(source_id)
                            % 1000,
                        },
                    }
                    for source_id, paper_id in batch
                ],
            },
            "links": {},
        }
        url = "https://inspirehep.net/api/literature?" + urlencode(
            {"q": explicit_citation_id_query(ids), "page": 1, "size": midpoint}
        )
        pages.append(
            capture_citation_session_page(
                json.dumps(payload).encode(),
                connector=connector,
                request_url=url,
                requested_at=_START + timedelta(seconds=batch_index * 2),
                received_at=_START + timedelta(seconds=1 if batch_index == 0 else 4),
                dataset_version=population.source_years[0].dataset_version,
                calendar_year=2020,
                end_calendar_year=2022,
                declared_date_basis="inspire-preprint-date",
                source_snapshot_id=f"synthetic-measurement-page-{batch_index}",
                canonical_paper_ids=dict(batch),
                expected_source_ids=ids,
            )
        )
    transport.get_json.assert_not_called()
    return CitationMeasurementSession(tuple(pages), population.measurement_population)


@pytest.fixture(scope="module")
def measured():  # type: ignore[no-untyped-def]
    population = _population()
    session = _session(population)
    cohorts = tuple(
        CertifiedSessionCitationCohort(population, session, ("hep-th", year, "article"))
        for year in _YEARS
    )
    return population, session, cohorts


def _impact_window(population, cohorts, *, cutoff=_AFTER):  # type: ignore[no-untyped-def]
    citation_refs = {
        item.paper_id: item.evidence.source_reference
        for cohort in cohorts
        for item in cohort.observations
    }
    years = tuple(
        _recertify_year(
            item,
            cutoff=cutoff,
            metric_id="research_impact",
            citation_refs=citation_refs,
        )
        for item in population.source_years
    )
    window = certify_metric_window(
        metric_id="research_impact",
        entity_type="institution",
        terminal_year=2022,
        source_years=years,
        threshold_version="metric-validation-thresholds-v1",
        citation_cohorts=cohorts,
    )
    return window


def test_frozen_membership_binds_real_typed_source_proofs_and_actual_times(
    measured,
) -> None:  # type: ignore[no-untyped-def]
    population, session, cohorts = measured
    assert population.unmeasurable_paper_ids == ()
    assert len(population.measurement_population.provider_to_canonical) == 150
    assert all(len(item.observations) == 50 for item in cohorts)
    assert {
        item.evidence.observed_at for cohort in cohorts for item in cohort.observations
    } == {_START + timedelta(seconds=1), _START + timedelta(seconds=4)}
    assert {
        item.evidence.observed_at.date()
        for cohort in cohorts
        for item in cohort.observations
    } == {date(2026, 9, 4), date(2026, 9, 5)}
    assert session_comparison_key(cohorts) == (
        session.session_id,
        session.measurement_started_at.isoformat(),
        session.measurement_finished_at.isoformat(),
    )
    window = _impact_window(population, cohorts)
    assert window.state == "certified", window.reasons
    assert all(
        before.certification.canonical_paper_population_digest
        == after.certification.canonical_paper_population_digest
        for before, after in zip(
            population.source_years, window.source_years, strict=True
        )
    )
    assert (
        population.source_years[0].certification.certification_id
        != window.source_years[0].certification.certification_id
    )


def test_missing_provider_identity_is_not_invented_and_empty_universe_fails() -> None:
    population = _population(2, no_provider_last=True)
    assert len(population.unmeasurable_paper_ids) == 3
    assert len(population.paper_projections) == 6
    assert len(population.measurement_population.provider_to_canonical) == 3
    with pytest.raises(CertificationError, match="empty or ambiguous"):
        _population(1, no_provider_last=True)


def test_minimum_50_and_missing_counts_are_not_relaxed(measured) -> None:  # type: ignore[no-untyped-def]
    short = _population(49)
    with pytest.raises(CertificationError, match="50-paper minimum"):
        CertifiedSessionCitationCohort(
            short, _session(short), ("hep-th", 2020, "article")
        )
    population, session, _ = measured
    first = session.pages[0]
    changed = replace(
        first,
        records=(
            replace(first.records[0], non_self_citation_count=None),
            *first.records[1:],
        ),
    )
    missing = replace(session, pages=(changed, *session.pages[1:]))
    with pytest.raises(CertificationError, match="missing or immature"):
        CertifiedSessionCitationCohort(population, missing, ("hep-th", 2020, "article"))


@pytest.mark.parametrize(
    "mutation", ["date", "field", "foreign-population", "old-policy"]
)
def test_cohort_rejects_altered_scientific_evidence(measured, mutation: str) -> None:  # type: ignore[no-untyped-def]
    population, session, cohorts = measured
    with pytest.raises(CertificationError):
        if mutation in {"date", "field"}:
            first = session.pages[0]
            record = first.records[0]
            record = (
                replace(record, publication_date=date(2020, 1, 2))
                if mutation == "date"
                else replace(record, field_ids=("quant-ph",))
            )
            changed = replace(
                session,
                pages=(
                    replace(first, records=(record, *first.records[1:])),
                    *session.pages[1:],
                ),
            )
            CertifiedSessionCitationCohort(population, changed, cohorts[0].cohort_key)
        elif mutation == "foreign-population":
            changed = replace(population, frozen_at=_FREEZE + timedelta(seconds=1))
            CertifiedSessionCitationCohort(changed, session, cohorts[0].cohort_key)
        else:
            replace(cohorts[0], policy_version="non-self-citation-cutoff-v1")


def test_horizon_and_legacy_policy_cannot_hide_measurement_interval(measured) -> None:  # type: ignore[no-untyped-def]
    population, _, cohorts = measured
    stale = _impact_window(population, cohorts, cutoff=_START)
    assert stale.state != "certified"
    with pytest.raises(CertificationError, match="evaluation horizon"):
        require_session_cohort(
            cohorts[0],
            dataset_version=population.source_years[0].dataset_version,
            acquisition_scope="hep-th-v1",
            evaluation_horizon=_BEFORE.date(),
        )
    old = partition("institution-a", (), terminal_year=2022)
    assert not partition_citation_policy_is_current(old, "research_impact", cohorts)
    assert not partition_citation_policy_is_current(
        replace(old, citation_policy_version=SESSION_CITATION_POLICY_VERSION),
        "research_impact",
        (),
    )


def test_measurement_cohorts_reach_unchanged_impact_formula(measured) -> None:  # type: ignore[no-untyped-def]
    population, session, cohorts = measured
    window = _impact_window(population, cohorts)
    observations = {
        item.paper_id: item for cohort in cohorts for item in cohort.observations
    }
    papers = tuple(
        paper(
            index,
            year,
            citations=float(index + 1),
            citation_cutoff=observations[
                f"paper-{year}-{index}"
            ].evidence.observed_at.date(),
        )
        for year in _YEARS
        for index in range(50)
    )
    raw = replace(
        partition(
            "institution-a",
            papers,
            terminal_year=2022,
            as_of_date=_AFTER.date(),
            complete_years=_YEARS,
        ),
        citation_policy_version=SESSION_CITATION_POLICY_VERSION,
    )
    eligible = derive_metric_population(
        window, entity_id="institution-a", field_id="hep-th", assessed_at=_AFTER
    )
    source = {item.paper_id: item for item in population.paper_projections}
    decisions = [
        EvidenceCertificationDecision(
            subject_type="paper",
            subject_id=item.paper_id,
            evidence_kind=kind,
            state="certified",
            rule_version=_rule(kind),
            dataset_version=raw.dataset_version,
            acquisition_scope=raw.acquisition_scope,
            evidence=(
                (observations[item.paper_id].evidence.source_reference,)
                if kind.startswith("citation-")
                else source[item.paper_id].occurrence_references
            ),
            certified_value_digest=paper_evidence_value_digest(raw, item, kind),
        )
        for item in papers
        for kind in required_paper_evidence("research_impact", "institution")
    ]
    units = metric_population_coverage_ledger(eligible.certification.evidence)
    coverage = []
    for kind in required_coverage_evidence("research_impact", "institution"):
        chosen = tuple(
            EvidenceCertificationDecision(
                subject_type="coverage-unit",
                subject_id=unit.unit_id,
                evidence_kind=kind,
                state="certified",
                rule_version=_rule(kind),
                dataset_version=raw.dataset_version,
                acquisition_scope=raw.acquisition_scope,
                evidence=(
                    (observations[unit.paper_id].evidence.source_reference,)
                    if kind == "citation-observation"
                    else source[unit.paper_id].occurrence_references
                ),
            )
            for unit in units
        )
        decisions.extend(chosen)
        coverage.append(
            certify_coverage(
                kind,
                chosen,
                CoveragePopulationEvidence(
                    kind,
                    tuple((item.unit_id, item.mass) for item in units),
                    tuple(
                        sorted(
                            (item.paper_id, item.attribution_weight) for item in papers
                        )
                    ),
                    eligible.certification.projection_digest,
                ),
            )
        )
    certified = build_certified_metric_partition(
        raw,
        metric_id="research_impact",
        decisions=tuple(decisions),
        coverage=tuple(coverage),
        window=window,
        population=eligible,
    )
    result = calculate_impact_raw(certified, cohorts)
    assert result.raw_eligible
    assert result.raw_value == pytest.approx(1.0)
    assert result.components["mncs"] == pytest.approx(1.0)
    assert result.components["pp_top_10_share"] == pytest.approx(0.1)
    assert result.components["eligible_papers"] == 150
    assert (
        result.components["citation_measurement_semantics"]
        == "retrospective-measurement-window"
    )
    assert result.components["citation_session_id"] == session.session_id
    assert result.components["citation_cutoff"] is None
