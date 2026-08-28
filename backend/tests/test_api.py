from collections.abc import Generator
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from physics_atlas_api import models, schemas
from physics_atlas_api.database import get_session
from physics_atlas_api.main import create_app


def test_read_api_exposes_repository_contract(seeded_session: Session) -> None:
    application = create_app()

    def session_override() -> Generator[Session]:
        yield seeded_session

    application.dependency_overrides[get_session] = session_override
    with TestClient(application) as client:
        health = client.get("/api/health")
        domains = client.get("/api/domains")
        institutions = client.get("/api/institutions", params={"limit": 3})
        authorships = client.get("/api/authorships", params={"limit": 2})
        search = client.get("/api/search", params={"q": "MIT"})
        paper_search = client.get(
            "/api/search", params={"q": "10.0000/physics-atlas.demo.001"}
        )
        paper = client.get("/api/papers/paper-boundary-symmetries")
        paper_authorships = client.get(
            "/api/authorships",
            params={"paper_id": "paper-boundary-symmetries", "limit": 20},
        )
        profile = client.get("/api/profiles/institutions/institution-mit")
        map_nodes = client.get(
            "/api/map/institutions",
            params={
                "country_id": "country-us",
                "science_domain_id": "physics",
                "metric_id": "research_activity_score",
                "period": "2026",
                "limit": 5,
            },
        )
        update_status = client.get("/api/updates/status")
        invalid_period = client.get(
            "/api/metric-observations", params={"period": "not-a-year"}
        )

    assert health.status_code == 200
    assert health.json()["database"] == "ok"
    assert domains.json()[0]["id"] == "physics"
    assert institutions.status_code == 200
    assert institutions.json()["limit"] == 3
    assert institutions.json()["total"] >= 3
    assert authorships.status_code == 200
    assert authorships.json()["items"]
    assert search.status_code == 200
    assert search.json()[0]["entityId"] == "institution-mit"
    assert paper_search.status_code == 200
    assert paper_search.json()[0]["entityId"] == "paper-boundary-symmetries"
    assert paper_search.json()[0]["matchedOn"] == "external-identifier"
    assert paper.status_code == 200
    assert paper.json()["doi"] == "10.0000/physics-atlas.demo.001"
    assert paper_authorships.status_code == 200
    assert paper_authorships.json()["items"]
    assert profile.status_code == 200
    assert profile.json()["institution"]["id"] == "institution-mit"
    assert map_nodes.status_code == 200
    assert 0 < len(map_nodes.json()) <= 5
    assert all(
        node["institution"]["countryId"] == "country-us" for node in map_nodes.json()
    )
    assert update_status.status_code == 200
    assert update_status.json()["metricRecalculationStatus"] == "idle"
    assert invalid_period.status_code == 422
    assert invalid_period.json()["error"]["code"] == "validation_error"


def test_api_returns_structured_not_found(seeded_session: Session) -> None:
    application = create_app()

    def session_override() -> Generator[Session]:
        yield seeded_session

    application.dependency_overrides[get_session] = session_override
    with TestClient(application) as client:
        response = client.get("/api/researchers/missing-researcher")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "entity_not_found"


def test_api_omits_missing_metric_rows(seeded_session: Session) -> None:
    provenance = {
        "source": "missing-value test fixture",
        "sourceType": "synthetic-demo",
        "version": "test-v1",
        "status": "synthetic",
    }
    seeded_session.add_all(
        [
            models.MetricObservation(
                id="observation-missing-country",
                entity_type="country",
                entity_id="country-us",
                science_domain_id="physics",
                field_id=None,
                metric_id="research_activity_score",
                period="1800",
                value=None,
                source="fixture",
                algorithm_version="test-v1",
                calculation_version="test-v1",
                provenance_json=provenance,
            ),
            models.MetricObservation(
                id="observation-missing-institution",
                entity_type="institution",
                entity_id="institution-mit",
                science_domain_id="physics",
                field_id=None,
                metric_id="research_activity_score",
                period="1800",
                value=None,
                source="fixture",
                algorithm_version="test-v1",
                calculation_version="test-v1",
                provenance_json=provenance,
            ),
        ]
    )
    seeded_session.commit()
    application = create_app()

    def session_override() -> Generator[Session]:
        yield seeded_session

    application.dependency_overrides[get_session] = session_override
    with TestClient(application) as client:
        observations = client.get(
            "/api/metric-observations",
            params={"metric_id": "research_activity_score", "limit": 200},
        )
        profile = client.get("/api/profiles/institutions/institution-mit")

    assert observations.status_code == 200
    assert "observation-missing-country" not in {
        item["id"] for item in observations.json()["items"]
    }
    assert profile.status_code == 200
    assert "observation-missing-institution" not in {
        item["id"] for item in profile.json()["metrics"]
    }


def test_identity_contract_accepts_quarantined_missing_metadata() -> None:
    resolution = schemas.IdentityResolutionOut.model_validate(
        {
            "id": "resolution-missing-year",
            "rawEntityRecordId": "raw-missing-year",
            "entityType": "paper",
            "status": "unresolved",
            "canonicalEntityId": None,
            "method": "insufficient-metadata",
            "confidence": 0,
            "evidence": [
                {
                    "method": "required-metadata",
                    "inputValue": "publication_year",
                    "score": 0,
                }
            ],
            "resolverVersion": "test-v1",
            "resolvedAt": "2026-08-28T00:00:00Z",
            "provenance": {
                "source": "test fixture",
                "sourceType": "synthetic-demo",
                "version": "test-v1",
                "status": "synthetic",
            },
        }
    )

    assert resolution.method == "insufficient-metadata"
    assert resolution.evidence[0].method == "required-metadata"


def test_metadata_and_evidence_routes_have_validated_response_contracts(
    seeded_session: Session,
) -> None:
    captured_at = datetime(2026, 8, 28, tzinfo=UTC)
    provenance = {
        "source": "typed contract fixture",
        "sourceType": "synthetic-demo",
        "version": "test-v1",
        "status": "synthetic",
    }
    snapshot = models.SourceSnapshot(
        id="snapshot-typed-contract",
        source="inspire",
        source_version="fixture-v1",
        captured_at=captured_at,
        update_mode="incremental",
        record_count=1,
        content_checksum="typed-contract-checksum",
        storage_reference="database://source_snapshots/snapshot-typed-contract",
        raw_payload=[],
        provenance_json=provenance,
    )
    raw_record = models.RawEntityRecord(
        id="raw-typed-contract",
        entity_type="paper",
        source="inspire",
        source_record_id="typed-contract-record",
        source_snapshot_id=snapshot.id,
        raw_name="Typed contract paper",
        external_ids=[{"scheme": "inspire", "value": "987654"}],
        attributes_json={"publication_year": 2026, "categories": ["Theory-HEP"]},
        raw_payload={"control_number": 987654},
        ingested_at=captured_at,
        provenance_json=provenance,
    )
    resolution = models.IdentityResolution(
        id="resolution-typed-contract",
        raw_entity_record_id=raw_record.id,
        entity_type="paper",
        status="matched",
        canonical_entity_id="paper-boundary-symmetries",
        method="external-identifier",
        confidence=1.0,
        evidence=[
            {
                "method": "external-identifier",
                "inputValue": "inspire:987654",
                "candidateEntityId": "paper-boundary-symmetries",
                "score": 1.0,
            }
        ],
        resolver_version="test-resolver-v1",
        resolved_at=captured_at,
        provenance_json=provenance,
    )
    update = models.DatasetUpdate(
        id="dataset-update-typed-contract",
        applied_at=captured_at,
        update_mode="incremental",
        source_snapshot_ids=[snapshot.id],
        previous_dataset_version="test-v0",
        dataset_version="test-v1",
        resolver_version="test-resolver-v1",
        metric_calculation_version="test-metric-v1",
        changes={
            "created": 1,
            "updated": 0,
            "unchanged": 0,
            "unresolved": 0,
            "failed": 0,
        },
        affected_entities=[],
        provenance_json=provenance,
    )
    seeded_session.add_all([snapshot, raw_record, resolution, update])
    seeded_session.commit()

    application = create_app()

    def session_override() -> Generator[Session]:
        yield seeded_session

    application.dependency_overrides[get_session] = session_override
    with TestClient(application) as client:
        dataset = client.get("/api/dataset")
        snapshots = client.get("/api/source-snapshots")
        updates = client.get("/api/dataset-updates")
        raw_records = client.get("/api/raw-entity-records")
        resolutions = client.get("/api/identity-resolutions")

    assert dataset.status_code == 200
    assert dataset.json()["datasetKind"] == "synthetic-demo"
    assert snapshots.status_code == 200
    assert snapshots.json()["items"][0]["id"] == snapshot.id
    assert updates.status_code == 200
    assert updates.json()["items"][0]["changes"]["failed"] == 0
    assert updates.json()["items"][0]["affectedEntities"] == []
    assert raw_records.status_code == 200
    assert raw_records.json()["items"][0]["attributes"]["publication_year"] == 2026
    assert resolutions.status_code == 200
    assert resolutions.json()["items"][0]["canonicalEntityId"] == (
        "paper-boundary-symmetries"
    )

    openapi_paths = application.openapi()["paths"]
    for path in (
        "/api/dataset",
        "/api/source-snapshots",
        "/api/dataset-updates",
        "/api/raw-entity-records",
        "/api/identity-resolutions",
        "/api/knowledge-graph",
    ):
        response_schema = openapi_paths[path]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema


def test_knowledge_graph_balances_nodes_and_bounds_edges(
    seeded_session: Session,
) -> None:
    provenance = {
        "source": "bounded graph fixture",
        "sourceType": "synthetic-demo",
        "version": "test-v1",
        "status": "synthetic",
    }
    graph_institutions = [
        models.Institution(
            id=f"institution-000-graph-{index}",
            canonical_name=f"Graph Institution {index}",
            aliases=[],
            historical_names=[],
            external_ids=[],
            country_id="country-us",
            city="Test City",
            field_ids=[],
            provenance_json=provenance,
        )
        for index in range(8)
    ]
    graph_researchers = [
        models.Researcher(
            id=f"researcher-000-graph-{index}",
            canonical_name=f"Graph Researcher {index}",
            aliases=[],
            historical_names=[],
            external_ids=[],
            field_ids=[],
            provenance_json=provenance,
        )
        for index in range(2)
    ]
    graph_affiliations = [
        models.Affiliation(
            id=f"affiliation-000-graph-{index}",
            researcher_id=graph_researchers[index].id,
            institution_id=graph_institutions[0].id,
            provenance_json=provenance,
        )
        for index in range(2)
    ]
    seeded_session.add_all(
        [*graph_institutions, *graph_researchers, *graph_affiliations]
    )
    seeded_session.commit()

    application = create_app()

    def session_override() -> Generator[Session]:
        yield seeded_session

    application.dependency_overrides[get_session] = session_override
    with TestClient(application) as client:
        response = client.get(
            "/api/knowledge-graph", params={"node_limit": 6, "edge_limit": 1}
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["nodeCount"] == 6
    assert payload["edgeCount"] == len(payload["edges"]) == 1
    assert payload["nodeLimit"] == 6
    assert payload["edgeLimit"] == 1
    assert payload["truncated"] is True
    assert {node["entityType"] for node in payload["nodes"]} == {
        "institution",
        "researcher",
    }
    assert payload["edges"][0]["sourceId"].startswith("researcher-000-graph-")
    assert payload["edges"][0]["targetId"] == graph_institutions[0].id
