from datetime import UTC, datetime

from sqlalchemy.orm import Session

from physics_atlas_api import models
from physics_atlas_api.fields import (
    CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION,
    FIELD_WEIGHTING_POLICY_VERSION,
)
from physics_atlas_api.metrics import METRIC_CONTRACTS
from physics_atlas_api.metrics.activation import DIVERSITY_BREADTH_REVIEW_VERSION
from physics_atlas_api.repository import AtlasDatabaseRepository

REVIEWED_BROAD_SCOPE = "reviewed-broad-physics-v1"


def test_live_public_reads_require_the_complete_joint_release_manifest(
    session: Session,
) -> None:
    contract = METRIC_CONTRACTS["research_activity_score"]
    session.add(
        models.DatasetState(
            id="current",
            schema_version="metric-system-v1",
            dataset_kind="live-api",
            period="2025",
            generated_at=datetime(2026, 8, 30, tzinfo=UTC),
            latest_update_at=datetime(2026, 8, 30, tzinfo=UTC),
            source_snapshot_ids=["snapshot-v1"],
            update_sequence=1,
            disclaimer="fixture",
            provenance_json={
                "source": "fixture",
                "version": "dataset-v1",
                "acquisitionScope": REVIEWED_BROAD_SCOPE,
            },
        )
    )
    definitions = {
        metric_id: models.MetricDefinition(
            id=metric_id,
            name=metric_contract.name,
            category=metric_contract.name,
            description=metric_contract.formula,
            interpretation=metric_contract.interpretation,
            unit=metric_contract.raw_unit,
            version=metric_contract.version,
            required_data=metric_contract.required_data_metadata(),
            implementation_status="experimental-candidate",
            provenance_json={"source": "fixture"},
        )
        for metric_id, metric_contract in METRIC_CONTRACTS.items()
    }
    session.add_all(definitions.values())
    session.add(
        models.MetricObservation(
            id="metric-live-candidate",
            entity_type="institution",
            entity_id="institution-a",
            science_domain_id="physics",
            field_id="hep-th",
            metric_id=contract.metric_id,
            period="2025",
            value=50,
            source="fixture",
            metric_definition_version=contract.version,
            algorithm_version=contract.algorithm_version,
            calculation_version="calculation-v1",
            data_source_version="dataset-v1",
            acquisition_scope=REVIEWED_BROAD_SCOPE,
            raw_value=10,
            raw_unit=contract.raw_unit,
            normalization_method=contract.normalization_version,
            normalization_parameters={"fitted": True},
            input_count=10,
            quality_flags=["experimental-candidate"],
            calculated_at=datetime(2026, 8, 30, tzinfo=UTC),
            provenance_json={"source": "fixture"},
        )
    )
    session.flush()
    repository = AtlasDatabaseRepository(session)

    hidden, total = repository.metric_observations(limit=10, offset=0)
    assert hidden == []
    assert total == 0

    release = models.MetricSystemRelease(
        id="metric-system-v1",
        status="active",
        metric_ids=list(METRIC_CONTRACTS)[:-1],
        algorithm_versions={
            metric_id: item.algorithm_version
            for metric_id, item in list(METRIC_CONTRACTS.items())[:-1]
        },
        attribution_policy_version="fractional-attribution-v1",
        ontology_version="physics-field-ontology-v1",
        mapping_policy_version="provider-field-mapping-v1",
        threshold_version="metric-validation-thresholds-v1",
        validation_evidence={"jointGatePassed": True},
        activated_at=datetime(2026, 8, 30, tzinfo=UTC),
        provenance_json={"source": "fixture"},
    )
    session.add(release)
    session.flush()
    partial, partial_total = repository.metric_observations(limit=10, offset=0)
    assert partial == []
    assert partial_total == 0

    release.metric_ids = list(METRIC_CONTRACTS)
    release.algorithm_versions = {
        metric_id: item.algorithm_version
        for metric_id, item in METRIC_CONTRACTS.items()
    }
    for metric_id, definition in definitions.items():
        if metric_id != "momentum":
            definition.implementation_status = "live-calculated"
    release.mapping_policy_version = "stale-provider-mapping"
    session.flush()
    incompatible, incompatible_total = repository.metric_observations(
        limit=10, offset=0
    )
    assert incompatible == []
    assert incompatible_total == 0

    release.mapping_policy_version = "provider-field-mapping-v1"
    session.flush()
    incomplete_definitions, incomplete_definitions_total = (
        repository.metric_observations(limit=10, offset=0)
    )
    assert incomplete_definitions == []
    assert incomplete_definitions_total == 0

    definitions["momentum"].implementation_status = "live-calculated"
    session.flush()
    missing_field_proof, missing_field_proof_total = repository.metric_observations(
        limit=10, offset=0
    )
    assert missing_field_proof == []
    assert missing_field_proof_total == 0

    release.validation_evidence = {
        "jointGatePassed": True,
        "fieldWeightingPolicyVersion": FIELD_WEIGHTING_POLICY_VERSION,
        "fieldReconciliationVersion": CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION,
        "fieldWeightConservationPassed": True,
        "acquisitionScope": REVIEWED_BROAD_SCOPE,
        "acquisitionBoundaryKind": "broad-physics",
        "dataSourceVersion": "dataset-v1",
        "diversityBreadthReviewVersion": DIVERSITY_BREADTH_REVIEW_VERSION,
        "diversityBreadthReviewPassed": True,
    }
    session.flush()
    visible, visible_total = repository.metric_observations(limit=10, offset=0)
    assert [item["id"] for item in visible] == ["metric-live-candidate"]
    assert visible_total == 1

    release.validation_evidence = {
        **release.validation_evidence,
        "dataSourceVersion": "stale-dataset",
    }
    session.flush()
    stale_dataset, stale_dataset_total = repository.metric_observations(
        limit=10, offset=0
    )
    assert stale_dataset == []
    assert stale_dataset_total == 0

    release.validation_evidence = {
        **release.validation_evidence,
        "dataSourceVersion": "dataset-v1",
        "acquisitionScope": "hep-th-v1",
    }
    session.flush()
    conditioned_scope, conditioned_scope_total = repository.metric_observations(
        limit=10, offset=0
    )
    assert conditioned_scope == []
    assert conditioned_scope_total == 0

    release.validation_evidence = {
        **release.validation_evidence,
        "acquisitionScope": "cond-mat-validation-v1",
    }
    session.flush()
    mislabeled_cond_mat, mislabeled_cond_mat_total = repository.metric_observations(
        limit=10, offset=0
    )
    assert mislabeled_cond_mat == []
    assert mislabeled_cond_mat_total == 0

    release.validation_evidence = {
        **release.validation_evidence,
        "acquisitionScope": REVIEWED_BROAD_SCOPE,
        "acquisitionBoundaryKind": "field-conditioned",
    }
    session.flush()
    conditioned_boundary, conditioned_boundary_total = repository.metric_observations(
        limit=10, offset=0
    )
    assert conditioned_boundary == []
    assert conditioned_boundary_total == 0

    release.validation_evidence = {
        **release.validation_evidence,
        "acquisitionBoundaryKind": "broad-physics",
        "diversityBreadthReviewVersion": "stale-breadth-review",
    }
    session.flush()
    stale_breadth_review, stale_breadth_review_total = repository.metric_observations(
        limit=10, offset=0
    )
    assert stale_breadth_review == []
    assert stale_breadth_review_total == 0

    release.validation_evidence = {
        **release.validation_evidence,
        "diversityBreadthReviewVersion": DIVERSITY_BREADTH_REVIEW_VERSION,
        "fieldWeightingPolicyVersion": "stale-field-weighting",
    }
    session.flush()
    stale_field_policy, stale_field_policy_total = repository.metric_observations(
        limit=10, offset=0
    )
    assert stale_field_policy == []
    assert stale_field_policy_total == 0
