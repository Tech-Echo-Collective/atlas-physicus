import json
import math
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from physics_atlas_api import models
from physics_atlas_api.metrics.contracts import (
    CANDIDATE_METRIC_IDS,
    METRIC_CONTRACTS,
)
from physics_atlas_api.metrics.normalization import (
    log_midrank_percentiles,
    normalized_shannon_evenness,
    robust_log_winsorized_cohort,
    symmetric_window_change,
)
from physics_atlas_api.metrics.validation import (
    REQUIRED_SANITY_CHECKS,
    MetricPartitionReadiness,
    MetricSanityCheck,
    MetricValidationSummary,
    assess_metric_activation,
    build_metric_validation_report,
)
from physics_atlas_api.seed import ensure_reference_data, seed_reference_data

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DATA = REPOSITORY_ROOT / "src" / "data" / "demo" / "atlas.json"
NOW = datetime(2026, 8, 29, tzinfo=UTC)
PROVENANCE = {
    "source": "deterministic metric-science test",
    "sourceType": "derived",
    "version": "live-test-v1",
    "status": "unverified",
    "acquisitionScope": "hep-th-v1",
}


def test_all_five_candidate_contracts_are_explicit_and_versioned() -> None:
    assert CANDIDATE_METRIC_IDS == (
        "research_activity_score",
        "research_impact",
        "collaboration",
        "research_diversity",
        "momentum",
    )
    for metric_id, contract in METRIC_CONTRACTS.items():
        assert contract.metric_id == metric_id
        assert contract.implementation_status == "experimental-candidate"
        assert contract.provenance.source_scope == "hep-th-v1"
        assert contract.version.endswith("-v1")
        assert contract.algorithm_version.endswith("-v1")
        assert contract.normalization_version.endswith("-v1")
        assert contract.raw_unit
        assert contract.normalized_range == (0.0, 100.0)
        assert contract.interpretation
        assert contract.formula
        assert contract.input_observations
        assert contract.aggregation_levels
        assert contract.aggregation_rule
        assert contract.time_window
        assert contract.field_normalization
        assert contract.entity_normalization
        assert contract.missing_data_behavior
        assert contract.minimum_data_requirements
        assert contract.high_score_meaning
        assert contract.low_score_meaning
        assert contract.does_not_mean
        assert contract.known_limitations
        metadata = contract.required_data_metadata()
        assert f"contract-version:{contract.version}" in metadata
        assert f"algorithm-version:{contract.algorithm_version}" in metadata
        assert f"normalization-version:{contract.normalization_version}" in metadata
        assert "source-scope:hep-th-v1" in metadata

    activity_contract = METRIC_CONTRACTS["research_activity_score"]
    assert "a cohort percentile" in activity_contract.does_not_mean
    for contract in METRIC_CONTRACTS.values():
        assert "than most" not in contract.high_score_meaning
        assert "than most" not in contract.low_score_meaning
    assert METRIC_CONTRACTS["momentum"].name == "Research Momentum"


def test_robust_log_normalization_is_bounded_and_preserves_measured_zero() -> None:
    values = {f"entity-{index:02}": float(index) for index in range(30)}
    values["entity-29"] = 1_000_000.0

    result = robust_log_winsorized_cohort(values)

    assert result.eligible is True
    assert result.reason is None
    assert set(result.scores) == set(values)
    assert result.scores["entity-00"] == 0.0
    assert result.scores["entity-29"] == 100.0
    assert all(0 <= score <= 100 for score in result.scores.values())
    assert result.parameters["fitted_upper"] != pytest.approx(math.log1p(1_000_000.0))

    insufficient = robust_log_winsorized_cohort(
        {"measured-zero": 0.0}, minimum_cohort=2
    )
    assert insufficient.eligible is False
    assert insufficient.scores == {}
    assert insufficient.reason == "insufficient normalization cohort"


def test_impact_midranks_are_tie_aware_and_missing_is_not_inserted() -> None:
    result = log_midrank_percentiles(
        {"zero-a": 0.0, "zero-b": 0.0, "one": 1.0, "ten": 10.0},
        minimum_cohort=4,
    )

    assert result.eligible is True
    assert result.scores["zero-a"] == pytest.approx(result.scores["zero-b"])
    assert result.scores["zero-a"] == pytest.approx(100 / 6)
    assert result.scores["ten"] == 100.0
    assert "missing-paper" not in result.scores

    all_tied = log_midrank_percentiles({"a": 0.0, "b": 0.0, "c": 0.0}, minimum_cohort=3)
    assert set(all_tied.scores.values()) == {50.0}


def test_metric_specific_bounded_transforms_handle_sparse_evidence() -> None:
    even = normalized_shannon_evenness({"hep-th": 5.0, "gr-qc": 5.0})
    concentrated = normalized_shannon_evenness({"hep-th": 10.0, "gr-qc": 0.0})
    missing = normalized_shannon_evenness({"hep-th": 0.0, "gr-qc": 0.0})

    assert even.eligible is True
    assert even.score == pytest.approx(100.0)
    assert concentrated.eligible is True
    assert concentrated.score == pytest.approx(0.0)
    assert missing.eligible is False
    assert missing.score is None

    growth = symmetric_window_change(15.0, 5.0)
    no_evidence = symmetric_window_change(0.0, 0.0)
    assert growth.eligible is True
    assert growth.raw_value == pytest.approx(0.5)
    assert growth.score == pytest.approx(75.0)
    assert no_evidence.eligible is False
    assert no_evidence.raw_value is None
    assert no_evidence.score is None


def test_reference_seed_registers_candidates_without_observations(
    session: Session,
) -> None:
    payload = json.loads(REFERENCE_DATA.read_text(encoding="utf-8"))
    seed_reference_data(session, payload)

    for metric_id, contract in METRIC_CONTRACTS.items():
        definition = session.get_one(models.MetricDefinition, metric_id)
        assert definition.implementation_status == "experimental-candidate"
        assert definition.version == contract.version
        assert definition.required_data == contract.required_data_metadata()
        assert definition.provenance_json["algorithmVersion"] == (
            contract.algorithm_version
        )
        assert definition.provenance_json["normalizationVersion"] == (
            contract.normalization_version
        )
    for metric_id in ("talent_ecosystem", "concentration_vulnerability"):
        definition = session.get_one(models.MetricDefinition, metric_id)
        assert definition.implementation_status == "taxonomy-only"
        assert definition.version == "metric-definition-v1"
    assert (
        session.scalar(select(func.count()).select_from(models.MetricObservation)) == 0
    )

    stale = session.get_one(models.MetricDefinition, "research_activity_score")
    stale.version = "metric-definition-v1"
    stale.implementation_status = "taxonomy-only"
    stale.required_data = ["stale"]
    session.commit()

    ensure_reference_data(session)

    repaired = session.get_one(models.MetricDefinition, "research_activity_score")
    assert repaired.version == METRIC_CONTRACTS["research_activity_score"].version
    assert repaired.implementation_status == "experimental-candidate"
    assert (
        session.scalar(select(func.count()).select_from(models.MetricObservation)) == 0
    )


def test_database_validation_reports_insufficient_live_coverage_without_writes(
    session: Session,
) -> None:
    payload = json.loads(REFERENCE_DATA.read_text(encoding="utf-8"))
    seed_reference_data(session, payload)
    session.add_all(
        [
            models.SourceSnapshot(
                id="snapshot-test",
                source="inspire",
                source_version="test-v1",
                captured_at=NOW,
                update_mode="incremental",
                record_count=1,
                previous_snapshot_id=None,
                content_checksum="metric-test-checksum",
                storage_reference=None,
                raw_payload=[],
                provenance_json=PROVENANCE,
            ),
            models.DatasetState(
                id="current",
                schema_version="3.0.5-alpha",
                dataset_kind="live-api",
                period="2026",
                generated_at=NOW,
                latest_update_at=NOW,
                source_snapshot_ids=["snapshot-test"],
                update_sequence=1,
                disclaimer="Test evidence is incomplete and is not a ranking.",
                provenance_json=PROVENANCE,
            ),
            models.Paper(
                id="paper-live-test",
                title="A bounded paper",
                summary="",
                publication_year=2026,
                doi=None,
                arxiv_id="2608.00001",
                external_ids=[{"scheme": "arxiv", "value": "2608.00001"}],
                provenance_json=PROVENANCE,
            ),
            models.Researcher(
                id="researcher-live-test",
                canonical_name="Ada Example",
                aliases=[],
                historical_names=[],
                external_ids=[{"scheme": "inspire", "value": "author-1"}],
                identity_confidence=1.0,
                field_ids=["hep-th"],
                provenance_json=PROVENANCE,
            ),
            models.RawEntityRecord(
                id="raw-paper-live-test",
                entity_type="paper",
                source="inspire",
                source_record_id="paper-1",
                source_snapshot_id="snapshot-test",
                raw_name="A bounded paper",
                external_ids=[{"scheme": "inspire", "value": "paper-1"}],
                attributes_json={
                    "citation_count": 0,
                    "authors": [
                        {
                            "full_name": "Example, Ada",
                            "affiliations": [{"value": "Example University"}],
                        }
                    ],
                },
                raw_payload={"id": "paper-1"},
                ingested_at=NOW,
                provenance_json=PROVENANCE,
            ),
        ]
    )
    session.flush()
    session.add_all(
        [
            models.PaperField(
                paper_id="paper-live-test",
                field_id="hep-th",
                classification_method="provider-category-rules-v1",
                confidence=0.95,
                provenance_json=PROVENANCE,
            ),
            models.Authorship(
                id="authorship-live-test",
                paper_id="paper-live-test",
                researcher_id="researcher-live-test",
                author_position=1,
                provenance_json=PROVENANCE,
            ),
            models.IdentityResolution(
                id="resolution-paper-live-test",
                raw_entity_record_id="raw-paper-live-test",
                entity_type="paper",
                status="matched",
                canonical_entity_id="paper-live-test",
                method="external-id",
                confidence=1.0,
                evidence=[{"scheme": "inspire", "value": "paper-1"}],
                resolver_version="test-v1",
                resolved_at=NOW,
                provenance_json=PROVENANCE,
            ),
        ]
    )
    session.commit()
    observations_before = session.scalar(
        select(func.count()).select_from(models.MetricObservation)
    )

    report = build_metric_validation_report(session, terminal_year=2026)

    assert report.report_version == "metric-validation-report-v1"
    assert report.summary.dataset_version == "live-test-v1"
    assert report.summary.acquisition_scope == "hep-th-v1"
    assert report.summary.publication_years == (2026,)
    assert report.summary.complete_source_years == ()
    assert report.summary.canonical_paper_count == 1
    assert report.summary.canonical_institution_count == 0
    assert report.summary.affiliation_count == 0
    assert report.summary.paper_time_affiliation_count == 0
    assert report.summary.paper_time_affiliation_coverage == 0
    assert report.summary.collaboration_relationship_coverage is None
    assert report.summary.paper_time_affiliation_attribution_certified is False
    assert report.summary.citation_edge_count == 0
    assert report.summary.citation_age_control_certified is False
    assert report.summary.common_citation_cutoff_certified is False
    assert report.summary.non_self_citation_rule_certified is False
    assert report.summary.reviewed_taxonomy_version is None
    assert report.summary.citation_observation_coverage == 1.0
    assert report.summary.raw_affiliation_assertion_count == 1
    assert {decision.metric_id for decision in report.decisions} == set(
        CANDIDATE_METRIC_IDS
    )
    assert all(decision.status == "withheld" for decision in report.decisions)
    assert all(decision.reasons for decision in report.decisions)

    session.add(
        models.RawEntityRecord(
            id="raw-paper-live-test-2",
            entity_type="paper",
            source="inspire",
            source_record_id="paper-2",
            source_snapshot_id="snapshot-test",
            raw_name="A second evidence record",
            external_ids=[{"scheme": "inspire", "value": "paper-2"}],
            # A second provider row for the same canonical paper has no
            # comparable citation observation. Coverage is canonical-paper
            # presence, so this must not dilute or inflate the denominator.
            attributes_json={"authors": []},
            raw_payload={"id": "paper-2"},
            ingested_at=NOW,
            provenance_json=PROVENANCE,
        )
    )
    session.flush()
    session.add(
        models.IdentityResolution(
            id="resolution-paper-live-test-2",
            raw_entity_record_id="raw-paper-live-test-2",
            entity_type="paper",
            status="matched",
            canonical_entity_id="paper-live-test",
            method="external-id",
            confidence=1.0,
            evidence=[{"scheme": "inspire", "value": "paper-2"}],
            resolver_version="test-v1",
            resolved_at=NOW,
            provenance_json=PROVENANCE,
        )
    )
    session.commit()

    bounded_report = build_metric_validation_report(
        session, terminal_year=2026, max_evidence_records=1
    )
    assert bounded_report.summary.evidence_truncated is True
    assert bounded_report.summary.matched_paper_evidence_examined == 1
    assert bounded_report.summary.matched_papers_with_citation_observation is None
    assert bounded_report.summary.raw_affiliation_assertion_count is None
    assert bounded_report.summary.citation_observation_coverage is None
    assert (
        session.scalar(select(func.count()).select_from(models.MetricObservation))
        == observations_before
        == 0
    )

    deduplicated_report = build_metric_validation_report(
        session, terminal_year=2026, max_evidence_records=10
    )
    assert deduplicated_report.summary.matched_paper_evidence_examined == 1
    assert deduplicated_report.summary.matched_papers_with_citation_observation == 1
    assert deduplicated_report.summary.citation_observation_coverage == 1.0

    session.add_all(
        [
            models.Country(
                id="country-validation-test",
                iso_alpha3="TST",
                iso_alpha2="TS",
                iso_numeric="999",
                name="Test Country",
                region="Test",
                provenance_json=PROVENANCE,
            ),
            models.Institution(
                id="institution-validation-test",
                canonical_name="Test Institution",
                aliases=[],
                historical_names=[],
                external_ids=[],
                identity_confidence=1.0,
                country_id="country-validation-test",
                city="Test City",
                longitude=0,
                latitude=0,
                field_ids=["hep-th"],
                provenance_json=PROVENANCE,
            ),
        ]
    )
    session.flush()
    session.add(
        models.Affiliation(
            id="profile-affiliation-validation-test",
            researcher_id="researcher-live-test",
            institution_id="institution-validation-test",
            research_group_id=None,
            start_date=None,
            end_date=None,
            provenance_json=PROVENANCE,
        )
    )
    session.commit()

    profile_only_report = build_metric_validation_report(session, terminal_year=2026)
    assert profile_only_report.summary.affiliation_count == 1
    assert profile_only_report.summary.paper_time_affiliation_count == 0
    assert profile_only_report.summary.paper_time_affiliation_coverage == 0

    session.add(
        models.Paper(
            id="paper-live-unmaterialized",
            title="An unmaterialized paper",
            summary="",
            publication_year=2026,
            document_type="article",
            external_ids=[],
            provenance_json=PROVENANCE,
        )
    )

    common_values = {
        "paper_id": "paper-live-test",
        "authorship_id": "authorship-live-test",
        "researcher_id": "researcher-live-test",
        "source_snapshot_id": "snapshot-test",
        "dataset_version": "live-test-v1",
        "provider": "inspire",
        "source_record_id": "paper-1",
        "author_position": 1,
        "raw_author_name": "Example, Ada",
        "provider_affiliation_id": None,
        "subunit_label": None,
        "author_resolution_status": "resolved",
        "author_weight": Decimal("1"),
        "author_weight_numerator": 1,
        "author_weight_denominator": 1,
        "effective_affiliation_count": 2,
        "attribution_policy_version": "fractional-attribution-v1",
        "materialization_version": "paper-time-affiliation-materialization-v1",
        "contribution_evidence": [],
        "resolution_evidence": [],
        "is_current": True,
        "provenance_json": PROVENANCE,
    }
    session.add_all(
        [
            models.PaperAffiliation(
                id="paper-affiliation-validation-resolved",
                institution_id="institution-validation-test",
                country_id="country-validation-test",
                raw_affiliation="Test Institution",
                affiliation_resolution_status="resolved",
                affiliation_weight=Decimal("0.5"),
                attribution_weight=Decimal("0.5"),
                attribution_weight_numerator=1,
                attribution_weight_denominator=2,
                **common_values,
            ),
            models.PaperAffiliation(
                id="paper-affiliation-validation-unresolved",
                institution_id=None,
                country_id=None,
                raw_affiliation="Unknown Institute",
                affiliation_resolution_status="unresolved",
                affiliation_weight=Decimal("0.5"),
                attribution_weight=Decimal("0.5"),
                attribution_weight_numerator=1,
                attribution_weight_denominator=2,
                **common_values,
            ),
        ]
    )
    session.commit()

    materialized_report = build_metric_validation_report(session, terminal_year=2026)
    assert materialized_report.summary.affiliation_count == 1
    assert materialized_report.summary.paper_time_affiliation_count == 2
    assert materialized_report.summary.paper_time_affiliation_coverage == pytest.approx(
        0.25
    )
    assert (
        materialized_report.summary.paper_time_affiliation_attribution_certified
        is False
    )
    assert materialized_report.summary.collaboration_relationship_coverage is None


def _sufficient_activity_summary() -> MetricValidationSummary:
    return MetricValidationSummary(
        dataset_version="live-sufficient-test-v1",
        dataset_kind="live-api",
        acquisition_scope="hep-th-v1",
        terminal_year=2026,
        update_sequence=1,
        source_snapshot_count=6,
        source_snapshot_sources=("arxiv", "inspire"),
        complete_source_years=(2021, 2022, 2023, 2024, 2025, 2026),
        raw_record_count=1_000,
        raw_paper_record_count=700,
        raw_researcher_record_count=300,
        canonical_paper_count=500,
        canonical_researcher_count=200,
        canonical_institution_count=50,
        publication_years=(2021, 2022, 2023, 2024, 2025, 2026),
        mature_paper_count=300,
        paper_field_link_count=500,
        classified_paper_count=500,
        reviewed_classified_paper_count=500,
        minimum_field_age_cohort_size=50,
        authorship_count=1_000,
        authored_paper_count=500,
        affiliation_count=900,
        paper_time_affiliation_count=900,
        paper_time_affiliation_coverage=1.0,
        collaboration_relationship_coverage=1.0,
        countries_with_institutions=30,
        paper_time_affiliation_attribution_certified=True,
        citation_edge_count=5_000,
        citation_age_control_certified=True,
        common_citation_cutoff_certified=True,
        non_self_citation_rule_certified=True,
        reviewed_taxonomy_version="reviewed-taxonomy-test-v1",
        identity_resolution_count=1_000,
        matched_resolution_count=1_000,
        unresolved_resolution_count=0,
        ambiguous_resolution_count=0,
        needs_review_count=0,
        matched_paper_evidence_examined=500,
        matched_papers_with_citation_observation=500,
        raw_affiliation_assertion_count=900,
        evidence_truncated=False,
        metric_observation_count=0,
    )


def test_activation_requires_validated_contract_and_every_sanity_check() -> None:
    contract = METRIC_CONTRACTS["research_activity_score"]
    summary = _sufficient_activity_summary()
    checks = tuple(
        MetricSanityCheck(check_id, True, "deterministic test passed")
        for check_id in REQUIRED_SANITY_CHECKS[contract.metric_id]
    )

    candidate_decision = assess_metric_activation(contract, summary, checks)
    assert candidate_decision.status == "withheld"
    assert "scientific contract remains experimental-candidate" in (
        candidate_decision.reasons
    )

    validated_contract = replace(
        contract,
        provenance=replace(contract.provenance, status="validated"),
    )
    corpus_only_decision = assess_metric_activation(validated_contract, summary, checks)
    assert corpus_only_decision.status == "withheld"
    assert corpus_only_decision.reasons == (
        "exact partition and input-lineage readiness are not certified",
    )

    readiness = MetricPartitionReadiness(
        metric_id=contract.metric_id,
        metric_version=contract.version,
        entity_type="institution",
        scope_kind="research-field",
        scope_id="hep-th",
        period="2024-2026",
        dataset_version="live-sufficient-test-v1",
        acquisition_scope="hep-th-v1",
        update_sequence=1,
        input_lineage_complete=True,
        per_entity_minimums_passed=True,
        cohort_requirements_passed=True,
        missing_data_checks_passed=True,
    )
    eligible_decision = assess_metric_activation(
        validated_contract, summary, checks, readiness
    )
    assert eligible_decision.status == "eligible-for-reviewed-activation"
    assert eligible_decision.reasons == ()
    assert eligible_decision.may_activate is True

    failed_check = replace(checks[0], passed=False)
    rejected = assess_metric_activation(
        validated_contract,
        summary,
        (failed_check, *checks[1:]),
        readiness,
    )
    assert rejected.status == "withheld"
    assert rejected.reasons == (f"sanity check failed: {failed_check.check_id}",)

    stale_lineage = replace(readiness, update_sequence=0)
    rejected_lineage = assess_metric_activation(
        validated_contract,
        summary,
        checks,
        stale_lineage,
    )
    assert rejected_lineage.status == "withheld"
    assert rejected_lineage.reasons == (
        "partition input update sequence does not match the summary",
    )
