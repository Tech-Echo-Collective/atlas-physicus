import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from physics_atlas_api import models
from physics_atlas_api.attribution import FRACTIONAL_ATTRIBUTION_V1
from physics_atlas_api.fields import PHYSICS_FIELD_ONTOLOGY_VERSION
from physics_atlas_api.fields.mapping import PROVIDER_FIELD_MAPPING_VERSION
from physics_atlas_api.metrics.contracts import METRIC_CONTRACTS
from physics_atlas_api.metrics.thresholds import METRIC_VALIDATION_THRESHOLDS_V1
from physics_atlas_api.seed import (
    ensure_reference_data,
    seed_dataset,
    seed_reference_data,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DATA = REPOSITORY_ROOT / "src" / "data" / "demo" / "atlas.json"


def test_ensure_reference_data_repairs_a_partial_seed(session: Session) -> None:
    payload = json.loads(REFERENCE_DATA.read_text(encoding="utf-8"))
    seed_reference_data(session, payload)
    session.delete(session.get_one(models.ResearchField, "hep-th"))
    session.delete(session.get_one(models.Country, "country-us"))
    session.delete(session.get_one(models.MetricDefinition, "research_activity_score"))
    session.delete(session.get_one(models.MetricSystemRelease, "metric-system-v1"))
    session.commit()

    ensure_reference_data(session)

    assert session.get(models.ScienceDomain, "physics") is not None
    assert session.get(models.ResearchField, "hep-th") is not None
    assert session.get(models.Country, "country-us") is not None
    assert session.get(models.MetricDefinition, "research_activity_score") is not None
    assert session.get(models.MetricSystemRelease, "metric-system-v1") is not None


def test_ensure_reference_data_is_idempotent(session: Session) -> None:
    ensure_reference_data(session)
    domain = session.get_one(models.ScienceDomain, "physics")
    original_created_at = domain.created_at

    ensure_reference_data(session)

    assert (
        session.get_one(models.ScienceDomain, "physics").created_at
        == original_created_at
    )


def test_reference_seed_materializes_versioned_scientific_foundation(
    session: Session,
) -> None:
    ensure_reference_data(session)

    hep_branch = session.get_one(models.ResearchField, "hep")
    hep_theory = session.get_one(models.ResearchField, "hep-th")
    assert hep_branch.node_kind == "branch"
    assert hep_branch.is_explorable is False
    assert hep_theory.parent_field_id == "hep"
    assert hep_theory.node_kind == "field"
    assert hep_theory.is_explorable is True
    assert hep_theory.ontology_version == PHYSICS_FIELD_ONTOLOGY_VERSION
    assert hep_theory.aliases

    release = session.get_one(models.MetricSystemRelease, "metric-system-v1")
    assert release.status == "experimental-withheld"
    assert release.metric_ids == list(METRIC_CONTRACTS)
    assert release.algorithm_versions == {
        metric_id: contract.algorithm_version
        for metric_id, contract in METRIC_CONTRACTS.items()
    }
    assert release.attribution_policy_version == FRACTIONAL_ATTRIBUTION_V1.version
    assert release.ontology_version == PHYSICS_FIELD_ONTOLOGY_VERSION
    assert release.mapping_policy_version == PROVIDER_FIELD_MAPPING_VERSION
    assert release.threshold_version == METRIC_VALIDATION_THRESHOLDS_V1.version
    assert release.validation_evidence["jointGatePassed"] is False
    assert release.activated_at is None


def test_ensure_reference_data_repairs_stale_ontology_metadata(
    session: Session,
) -> None:
    ensure_reference_data(session)
    field = session.get_one(models.ResearchField, "hep-th")
    field.aliases = ["stale alias"]
    field.ontology_version = "stale-ontology"
    session.commit()

    ensure_reference_data(session)

    repaired = session.get_one(models.ResearchField, "hep-th")
    assert repaired.ontology_version == PHYSICS_FIELD_ONTOLOGY_VERSION
    assert "stale alias" not in repaired.aliases

    branch = session.get_one(models.ResearchField, "hep")
    branch.is_explorable = True
    session.commit()

    ensure_reference_data(session)

    assert session.get_one(models.ResearchField, "hep").is_explorable is False


def test_demo_seed_includes_required_ontology_ancestors_with_foreign_keys(
    session: Session,
) -> None:
    session.execute(text("PRAGMA foreign_keys = ON"))
    payload = json.loads(REFERENCE_DATA.read_text(encoding="utf-8"))

    seed_dataset(session, payload)

    hep_branch = session.get_one(models.ResearchField, "hep")
    hep_theory = session.get_one(models.ResearchField, "hep-th")
    assert hep_branch.node_kind == "branch"
    assert hep_branch.is_explorable is False
    assert hep_theory.parent_field_id == hep_branch.id


@pytest.mark.parametrize("release_status", ["eligible", "active"])
def test_reference_seed_preserves_reviewed_metric_system_metadata(
    session: Session,
    release_status: str,
) -> None:
    payload = json.loads(REFERENCE_DATA.read_text(encoding="utf-8"))
    ensure_reference_data(session)
    reviewed_metadata: dict[str, tuple[str, list[str], dict[str, str]]] = {}
    for metric_id, contract in METRIC_CONTRACTS.items():
        definition = session.get_one(models.MetricDefinition, metric_id)
        description = f"Reviewed live definition for {metric_id}"
        required_data = [f"reviewed-evidence:{metric_id}"]
        provenance = {
            "source": "reviewed activation fixture",
            "version": contract.version,
            "reviewId": f"review-{metric_id}",
        }
        definition.description = description
        definition.required_data = required_data
        definition.implementation_status = "live-calculated"
        definition.provenance_json = provenance
        reviewed_metadata[metric_id] = (description, required_data, provenance)

    release = session.get_one(models.MetricSystemRelease, "metric-system-v1")
    release.status = release_status
    release.metric_ids = list(METRIC_CONTRACTS)
    release.algorithm_versions = {
        metric_id: contract.algorithm_version
        for metric_id, contract in METRIC_CONTRACTS.items()
    }
    release.attribution_policy_version = FRACTIONAL_ATTRIBUTION_V1.version
    release.ontology_version = PHYSICS_FIELD_ONTOLOGY_VERSION
    release.mapping_policy_version = PROVIDER_FIELD_MAPPING_VERSION
    release.threshold_version = METRIC_VALIDATION_THRESHOLDS_V1.version
    release.validation_evidence = {
        "jointGatePassed": True,
        "reviewId": "reviewed-joint-gate-v1",
    }
    release.activated_at = (
        datetime(2026, 8, 30, tzinfo=UTC) if release_status == "active" else None
    )
    release.provenance_json = {
        "source": "reviewed activation fixture",
        "reviewId": "reviewed-joint-gate-v1",
    }
    session.commit()

    ensure_reference_data(session)
    seed_reference_data(session, payload)

    preserved_release = session.get_one(models.MetricSystemRelease, "metric-system-v1")
    assert preserved_release.status == release_status
    assert preserved_release.validation_evidence == {
        "jointGatePassed": True,
        "reviewId": "reviewed-joint-gate-v1",
    }
    assert preserved_release.provenance_json == {
        "source": "reviewed activation fixture",
        "reviewId": "reviewed-joint-gate-v1",
    }
    assert (preserved_release.activated_at is not None) == (release_status == "active")
    for metric_id, expected_metadata in reviewed_metadata.items():
        definition = session.get_one(models.MetricDefinition, metric_id)
        assert definition.version == METRIC_CONTRACTS[metric_id].version
        assert definition.implementation_status == "live-calculated"
        assert (
            definition.description,
            definition.required_data,
            definition.provenance_json,
        ) == expected_metadata


def test_reference_seed_repairs_stray_live_candidate_without_activation(
    session: Session,
) -> None:
    ensure_reference_data(session)
    definition = session.get_one(models.MetricDefinition, "research_activity_score")
    definition.implementation_status = "live-calculated"
    definition.description = "Unreviewed stray live marker"
    release = session.get_one(models.MetricSystemRelease, "metric-system-v1")
    release.metric_ids = list(METRIC_CONTRACTS)[:-1]
    release.algorithm_versions = {
        metric_id: contract.algorithm_version
        for metric_id, contract in list(METRIC_CONTRACTS.items())[:-1]
    }
    release.validation_evidence = {"jointGatePassed": True}
    session.commit()

    ensure_reference_data(session)

    repaired_definition = session.get_one(
        models.MetricDefinition, "research_activity_score"
    )
    repaired_release = session.get_one(models.MetricSystemRelease, "metric-system-v1")
    assert repaired_definition.implementation_status == "experimental-candidate"
    assert repaired_definition.description != "Unreviewed stray live marker"
    assert repaired_release.status == "experimental-withheld"
    assert repaired_release.metric_ids == list(METRIC_CONTRACTS)
    assert repaired_release.validation_evidence["jointGatePassed"] is False
    assert repaired_release.activated_at is None
