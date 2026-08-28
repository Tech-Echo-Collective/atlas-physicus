import json
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from physics_atlas_api import models, schemas
from physics_atlas_api.connectors.base import (
    ConnectorBatch,
    NormalizedRecord,
    SourceConnector,
    SourceRecord,
)
from physics_atlas_api.connectors.http import FixtureTransport
from physics_atlas_api.database import get_session
from physics_atlas_api.identity.validation import (
    IdentityValidationLabel,
    IdentityValidationPrediction,
    ManualReviewCandidate,
    ResolutionStatus,
    build_manual_review_manifest,
    calculate_identity_validation_report,
    select_stratified_manual_review_manifest,
)
from physics_atlas_api.main import create_app
from physics_atlas_api.updates.engine import IncrementalUpdateEngine

PROVENANCE = {
    "source": "identity validation test fixture",
    "sourceType": "external-api",
    "version": "test-v1",
    "status": "unverified",
}


class MissingYearPaperConnector(SourceConnector):
    provider = "crossref"
    source_version = "identity-validation-test-v1"
    min_interval_seconds = 0

    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        del cursor, limit
        return ConnectorBatch(
            records=(
                SourceRecord(
                    provider="crossref",
                    source_record_id="missing-year-paper",
                    raw={"title": "Missing year validation paper"},
                ),
            ),
            next_cursor="identity-validation-complete",
        )

    def fetch_record(self, record_id: str) -> SourceRecord | None:
        del record_id
        return None

    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        return NormalizedRecord(
            provider="crossref",
            kind="paper",
            source_record_id=record.source_record_id,
            canonical_name="Missing year validation paper",
            external_ids=(("doi", "10.1234/identity-validation-missing-year"),),
            attributes={
                "title": "Missing year validation paper",
                "abstract": "A deterministic missing-metadata case.",
                "authors": [],
                "atlas_field_candidates": [],
            },
            raw=record.raw,
            provenance=PROVENANCE,
        )


def _client(session: Session) -> TestClient:
    application = create_app()

    def session_override() -> Generator[Session]:
        yield session

    application.dependency_overrides[get_session] = session_override
    return TestClient(application)


def _run_missing_year_case(
    session: Session, fixture_directory: Path
) -> models.SourceSnapshot:
    connector = MissingYearPaperConnector(
        FixtureTransport(fixture_directory),
        "https://crossref.test",
    )
    result = IncrementalUpdateEngine(session, connector).run()
    assert result.status == "succeeded"
    snapshot = session.scalar(select(models.SourceSnapshot))
    assert snapshot is not None
    return snapshot


def test_engine_missing_year_evidence_serializes_and_filter_is_typed(
    session: Session, fixture_directory: Path
) -> None:
    _run_missing_year_case(session, fixture_directory)

    with _client(session) as client:
        all_resolutions = client.get("/api/identity-resolutions")
        unresolved = client.get(
            "/api/identity-resolutions",
            params={"resolution_status": "unresolved"},
        )
        invalid = client.get(
            "/api/identity-resolutions",
            params={"resolution_status": "needs_review"},
        )

    assert all_resolutions.status_code == 200
    evidence = all_resolutions.json()["items"][0]["evidence"][0]
    assert evidence["method"] == "required-metadata"
    assert evidence["reason"] == "missing-or-invalid"
    assert unresolved.status_code == 200
    assert unresolved.json()["total"] == 1
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"

    first_manifest = build_manual_review_manifest(
        session,
        sample_version="missing-year-review-v1",
        per_stratum=1,
    )
    second_manifest = build_manual_review_manifest(
        session,
        sample_version="missing-year-review-v1",
        per_stratum=1,
    )
    assert first_manifest == second_manifest
    assert first_manifest[0].candidate.reason == "missing-or-invalid"
    assert first_manifest[0].candidate.raw_name == "Missing year validation paper"


def _add_summary_cases(session: Session, snapshot: models.SourceSnapshot) -> None:
    timestamp = datetime(2026, 8, 29, tzinfo=UTC)

    def raw_record(
        record_id: str,
        entity_type: str,
        *,
        external_ids: list[dict[str, str]] | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> models.RawEntityRecord:
        return models.RawEntityRecord(
            id=f"raw-{record_id}",
            entity_type=entity_type,
            source="crossref",
            source_record_id=record_id,
            source_snapshot_id=snapshot.id,
            raw_name=f"Private raw name {record_id}",
            external_ids=external_ids or [],
            attributes_json=attributes or {},
            raw_payload={"privateSourceValue": record_id},
            ingested_at=timestamp,
            provenance_json=PROVENANCE,
        )

    matched_raw = raw_record(
        "matched",
        "paper",
        external_ids=[{"scheme": "doi", "value": "10.1234/matched"}],
    )
    authority_raw = raw_record(
        "authority-required",
        "researcher",
        attributes={"requires_authority": True},
    )
    ambiguous_raw = raw_record("ambiguous", "institution")
    matched = models.IdentityResolution(
        id="resolution-summary-matched",
        raw_entity_record_id=matched_raw.id,
        entity_type="paper",
        status="matched",
        canonical_entity_id="paper-summary-matched",
        method="external-identifier",
        confidence=1,
        evidence=[
            {
                "method": "external-identifier",
                "inputValue": "doi:10.1234/matched",
                "candidateEntityId": "paper-summary-matched",
                "score": 1,
            }
        ],
        resolver_version="summary-resolver-v1",
        resolved_at=timestamp,
        provenance_json=PROVENANCE,
    )
    authority = models.IdentityResolution(
        id="resolution-summary-authority",
        raw_entity_record_id=authority_raw.id,
        entity_type="researcher",
        status="unresolved",
        canonical_entity_id=None,
        method=None,
        confidence=0,
        evidence=[],
        resolver_version="summary-resolver-v1",
        resolved_at=timestamp,
        provenance_json=PROVENANCE,
    )
    ambiguous = models.IdentityResolution(
        id="resolution-summary-ambiguous",
        raw_entity_record_id=ambiguous_raw.id,
        entity_type="institution",
        status="ambiguous",
        canonical_entity_id=None,
        method=None,
        confidence=0.5,
        evidence=[
            {
                "method": "external-identifier",
                "inputValue": "conflicting-id",
                "candidateEntityId": "institution-a",
                "score": 1,
            }
        ],
        resolver_version="summary-resolver-v1",
        resolved_at=timestamp,
        provenance_json=PROVENANCE,
    )
    session.add_all(
        [
            matched_raw,
            authority_raw,
            ambiguous_raw,
            matched,
            authority,
            ambiguous,
            models.IdentityReview(
                id="review-summary-authority",
                resolution_id=authority.id,
                status="needs_review",
                candidate_entity_ids=[],
            ),
            models.IdentityReview(
                id="review-summary-ambiguous",
                resolution_id=ambiguous.id,
                status="resolved",
                candidate_entity_ids=["institution-a"],
            ),
        ]
    )
    session.commit()


def test_identity_summary_separates_resolution_and_workflow_status(
    session: Session, fixture_directory: Path
) -> None:
    snapshot = _run_missing_year_case(session, fixture_directory)
    _add_summary_cases(session, snapshot)

    with _client(session) as client:
        response = client.get("/api/identity-resolutions/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert payload["statusCounts"] == {
        "matched": 1,
        "unresolved": 2,
        "ambiguous": 1,
    }
    assert payload["workflowCounts"] == {"needsReview": 2}
    assert {item["method"]: item["count"] for item in payload["methodCounts"]} == {
        "external-identifier": 1,
        "insufficient-metadata": 1,
        "unmatched": 2,
    }
    assert {item["reason"]: item["count"] for item in payload["reasonCounts"]} == {
        "missing-or-invalid": 1,
        "authority-identifier-required": 1,
        "unclassified": 1,
    }
    entity_counts = {item["entityType"]: item for item in payload["entityTypeCounts"]}
    assert entity_counts["paper"] == {
        "entityType": "paper",
        "total": 2,
        "matched": 1,
        "unresolved": 1,
        "ambiguous": 0,
        "needsReview": 1,
    }
    assert entity_counts["researcher"]["needsReview"] == 1
    assert entity_counts["institution"]["ambiguous"] == 1
    assert "Private raw name" not in response.text
    assert "privateSourceValue" not in response.text


def _candidate(resolution_id: str) -> ManualReviewCandidate:
    return ManualReviewCandidate(
        resolution_id=resolution_id,
        raw_entity_record_id=f"raw-{resolution_id}",
        source="inspire",
        source_record_id=f"source-{resolution_id}",
        source_snapshot_id="snapshot-1",
        raw_name=f"Review case {resolution_id}",
        entity_type="researcher",
        observed_status="unresolved",
        observed_method="unmatched",
        reason="authority-identifier-required",
        confidence=0,
        resolver_version="challenge-resolver-v1",
    )


def test_manual_review_selection_is_stable_and_stratum_capped() -> None:
    candidates = [_candidate("resolution-c"), _candidate("resolution-a")]
    candidates.append(_candidate("resolution-b"))

    first = select_stratified_manual_review_manifest(
        candidates,
        sample_version="challenge-v1",
        per_stratum=2,
    )
    second = select_stratified_manual_review_manifest(
        list(reversed(candidates)),
        sample_version="challenge-v1",
        per_stratum=2,
    )

    assert first == second
    assert len(first) == 2
    assert len({item.selection_hash for item in first}) == 2
    assert all(item.sample_version == "challenge-v1" for item in first)
    bounded = select_stratified_manual_review_manifest(
        candidates,
        sample_version="challenge-v1",
        per_stratum=3,
        maximum_cases=1,
    )
    assert len(bounded) == 1
    assert bounded[0] == first[0]


def test_labeled_report_is_reproducible_and_withholds_small_calibration() -> None:
    fixture_path = (
        Path(__file__).parent / "fixtures" / "identity_validation_challenge_v1.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    predictions = [
        IdentityValidationPrediction(
            case_id=item["case_id"],
            status=cast(ResolutionStatus, item["status"]),
            canonical_entity_id=item["canonical_entity_id"],
            confidence=item["confidence"],
        )
        for item in payload["predictions"]
    ]
    labels = [
        IdentityValidationLabel(
            case_id=item["case_id"],
            status=cast(ResolutionStatus, item["status"]),
            canonical_entity_id=item["canonical_entity_id"],
        )
        for item in payload["labels"]
    ]

    report = calculate_identity_validation_report(
        predictions,
        labels,
        # This deterministic challenge fixture tests arithmetic only. The
        # production default deliberately withholds results below 30 labels.
        minimum_metric_cases=1,
    )

    assert payload["sampleVersion"] == "identity-validation-challenge-v1"
    assert report.sample_size == 8
    assert report.precision == pytest.approx(0.5)
    assert report.recall == pytest.approx(0.5)
    assert report.unresolved_rate == pytest.approx(3 / 8)
    assert report.ambiguous_rate == pytest.approx(1 / 8)
    assert report.decision_accuracy == pytest.approx(5 / 8)
    assert report.calibration is None


def test_report_withholds_insufficient_metrics_and_computes_bounded_calibration() -> (
    None
):
    prediction = IdentityValidationPrediction("case-1", "matched", "entity-1", 0.8)
    label = IdentityValidationLabel("case-1", "matched", "entity-1")
    insufficient = calculate_identity_validation_report(
        [prediction],
        [label],
        minimum_metric_cases=2,
        minimum_calibration_cases=2,
    )
    calibrated = calculate_identity_validation_report(
        [prediction],
        [label],
        minimum_calibration_cases=1,
    )

    assert insufficient.precision is None
    assert insufficient.recall is None
    assert insufficient.decision_accuracy is None
    assert insufficient.calibration is None
    assert calibrated.calibration is not None
    assert calibrated.calibration.sample_size == 1
    assert calibrated.calibration.brier_score == pytest.approx(0.04)


def test_report_default_withholds_statistics_below_predeclared_label_minimum() -> None:
    predictions = [
        IdentityValidationPrediction(f"case-{index}", "matched", f"entity-{index}", 0.9)
        for index in range(29)
    ]
    labels = [
        IdentityValidationLabel(f"case-{index}", "matched", f"entity-{index}")
        for index in range(29)
    ]

    report = calculate_identity_validation_report(predictions, labels)

    assert report.minimum_metric_cases == 30
    assert report.precision is None
    assert report.recall is None
    assert report.unresolved_rate is None
    assert report.ambiguous_rate is None
    assert report.decision_accuracy is None


def test_metric_observation_additive_fields_have_legacy_safe_defaults() -> None:
    observation = schemas.MetricObservationOut.model_validate(
        {
            "id": "metric-observation-legacy",
            "entityType": "country",
            "entityId": "country-us",
            "metricId": "research_activity_score",
            "period": "2026",
            "value": 1,
            "source": "legacy fixture",
            "algorithmVersion": "legacy-v1",
            "calculationVersion": "legacy-v1",
            "calculatedAt": "2026-08-29T00:00:00Z",
            "provenance": {
                "source": "legacy fixture",
                "sourceType": "synthetic-demo",
                "version": "legacy-v1",
                "status": "synthetic",
            },
        }
    )

    assert observation.metric_definition_version == "legacy-v1"
    assert observation.normalization_parameters == {}
    assert observation.input_count is None
    assert observation.quality_flags == []


def test_current_candidate_observation_requires_complete_reconstruction_metadata() -> (
    None
):
    candidate_payload: dict[str, Any] = {
        "id": "metric-observation-candidate",
        "entityType": "country",
        "entityId": "country-us",
        "scienceDomainId": "physics",
        "fieldId": "hep-th",
        "metricId": "research_activity_score",
        "period": "2026",
        "value": 42,
        "source": "Physics Atlas candidate calculation",
        "algorithmVersion": "activity-distinct-paper-window-v1",
        "calculationVersion": "candidate-run-v1",
        "calculatedAt": "2026-08-29T00:00:00Z",
        "provenance": {
            "source": "Physics Atlas candidate calculation",
            "sourceType": "derived",
            "version": "candidate-run-v1",
            "status": "unverified",
            "acquisitionScope": "hep-th-v1",
        },
    }

    with pytest.raises(ValueError, match="reconstructable metadata"):
        schemas.MetricObservationOut.model_validate(candidate_payload)

    complete = schemas.MetricObservationOut.model_validate(
        {
            **candidate_payload,
            "metricDefinitionVersion": "activity-output-participation-v1",
            "dataSourceVersion": "live-dataset-v1",
            "acquisitionScope": "hep-th-v1",
            "rawValue": 12,
            "rawUnit": "distinct attributed canonical papers",
            "normalizationMethod": "robust-log-winsorized-cohort-v1",
            "normalizationParameters": {
                "cohort_size": 30,
                "fitted_lower": 0,
                "fitted_upper": 4.2,
            },
            "inputCount": 12,
            "qualityFlags": [],
        }
    )

    assert complete.metric_definition_version == "activity-output-participation-v1"
    assert complete.data_source_version == "live-dataset-v1"
    assert complete.input_count == 12


def test_metric_observation_lineage_versions_coexist_and_nonlegacy_rows_are_guarded(
    session: Session,
) -> None:
    session.add(
        models.MetricDefinition(
            id="lineage-test-metric",
            name="Lineage test metric",
            category="Test",
            description="Persistence-only reconstruction test.",
            interpretation="No scientific interpretation.",
            unit="test units",
            version="definition-v1",
            required_data=["test input"],
            implementation_status="experimental-candidate",
            provenance_json=PROVENANCE,
        )
    )
    session.commit()

    base = {
        "entity_type": "country",
        "entity_id": "country-test",
        "science_domain_id": "physics",
        "field_id": "hep-th",
        "metric_id": "lineage-test-metric",
        "period": "2026",
        "value": 42.0,
        "source": "lineage persistence test",
        "calculation_version": "calculation-run-v1",
        "acquisition_scope": "hep-th-v1",
        "raw_value": 12.0,
        "raw_unit": "test raw units",
        "normalization_method": "test-normalization-v1",
        "normalization_parameters": {"cohort_size": 30},
        "input_count": 12,
        "quality_flags": [],
        "calculated_at": datetime(2026, 8, 29, tzinfo=UTC),
        "provenance_json": PROVENANCE,
    }
    versions = (
        ("observation-lineage-base", "definition-v1", "algorithm-v1", "dataset-v1"),
        (
            "observation-lineage-definition",
            "definition-v2",
            "algorithm-v1",
            "dataset-v1",
        ),
        (
            "observation-lineage-algorithm",
            "definition-v1",
            "algorithm-v2",
            "dataset-v1",
        ),
        ("observation-lineage-dataset", "definition-v1", "algorithm-v1", "dataset-v2"),
    )
    session.add_all(
        [
            models.MetricObservation(
                id=observation_id,
                metric_definition_version=definition_version,
                algorithm_version=algorithm_version,
                data_source_version=dataset_version,
                **base,
            )
            for (
                observation_id,
                definition_version,
                algorithm_version,
                dataset_version,
            ) in versions
        ]
    )
    session.commit()

    persisted = list(
        session.scalars(
            select(models.MetricObservation)
            .where(models.MetricObservation.metric_id == "lineage-test-metric")
            .order_by(models.MetricObservation.id)
        )
    )
    assert len(persisted) == 4
    assert {
        (
            item.metric_definition_version,
            item.algorithm_version,
            item.data_source_version,
        )
        for item in persisted
    } == {
        ("definition-v1", "algorithm-v1", "dataset-v1"),
        ("definition-v2", "algorithm-v1", "dataset-v1"),
        ("definition-v1", "algorithm-v2", "dataset-v1"),
        ("definition-v1", "algorithm-v1", "dataset-v2"),
    }

    session.add(
        models.MetricObservation(
            id="observation-lineage-incomplete",
            entity_type="country",
            entity_id="country-test",
            science_domain_id="physics",
            field_id="hep-th",
            metric_id="lineage-test-metric",
            period="2027",
            value=1,
            source="lineage persistence test",
            metric_definition_version="definition-v2",
            algorithm_version="algorithm-v2",
            calculation_version="calculation-run-v2",
            data_source_version=None,
            acquisition_scope=None,
            raw_value=None,
            raw_unit=None,
            normalization_method=None,
            normalization_parameters={},
            input_count=None,
            quality_flags=[],
            calculated_at=datetime(2026, 8, 29, tzinfo=UTC),
            provenance_json=PROVENANCE,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


@pytest.mark.parametrize("input_count", [-1, -100])
def test_metric_observation_rejects_negative_input_count(input_count: int) -> None:
    with pytest.raises(ValueError):
        schemas.MetricObservationOut.model_validate(
            {
                "id": "metric-observation-invalid",
                "entityType": "country",
                "entityId": "country-us",
                "metricId": "research_activity_score",
                "period": "2026",
                "value": 1,
                "source": "test fixture",
                "algorithmVersion": "test-v1",
                "calculationVersion": "test-v1",
                "inputCount": input_count,
                "calculatedAt": "2026-08-29T00:00:00Z",
                "provenance": {
                    "source": "test fixture",
                    "sourceType": "synthetic-demo",
                    "version": "test-v1",
                    "status": "synthetic",
                },
            }
        )
