import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_metric_activation import complete_evidence as complete_metric_evidence

from physics_atlas_api.metrics import assess_joint_metric_activation
from physics_atlas_api.storage import (
    STORAGE_BUDGET_POLICY_V1,
    STORAGE_PROJECTION_METHOD_V1,
    ArtifactRef,
    FilesystemArtifactStore,
    ScientificGateEvidence,
    ScientificGateReview,
    StorageBudgetEvidence,
    StorageGateEvidence,
    StorageTier,
    assess_full_physics_load,
    assess_storage_budget,
    backup_restore_evidence_payload,
    estimate_linear_storage,
    measured_storage_audit_payload,
    scientific_gate_evidence_digest,
    scientific_gate_evidence_payload,
    storage_budget_evidence_digest,
    storage_projection_payload,
    target_population_evidence_payload,
    verify_scientific_gate_evidence,
    verify_storage_gate_evidence,
)


def _reference(payload: bytes) -> ArtifactRef:
    digest = hashlib.sha256(payload).hexdigest()
    return ArtifactRef(
        uri=f"physics-atlas-artifact://warm/{digest[:2]}/{digest}",
        sha256=digest,
        size_bytes=len(payload),
        media_type="application/json",
        content_encoding="identity",
        tier=StorageTier.WARM,
    )


def complete_evidence() -> StorageBudgetEvidence:
    draft = StorageBudgetEvidence(
        capacity_bytes=5_000_000_000,
        current_used_bytes=500_000_000,
        measured_sample_papers=10_000,
        measured_sample_bytes=200_000_000,
        measured_fixed_bytes=100_000_000,
        measurement_environment_id="representative-staging-v1",
        measured_at=datetime(2026, 9, 4, tzinfo=UTC),
        target_papers=50_000,
        target_population_id="physics-full-reviewed-2026-09-04",
        target_population_policy_version="full-physics-population-v1",
        target_population_cutoff=datetime(2026, 9, 4, tzinfo=UTC),
        target_population_paper_ids_digest="1" * 64,
        projection_method_version=STORAGE_PROJECTION_METHOD_V1,
        projected_steady_state_bytes=2_000_000_000,
        projected_peak_bytes=2_800_000_000,
        representative_final_schema=True,
        database_statistics_refreshed=True,
        peak_working_set_included=True,
        certification_storage_included=True,
        citation_storage_included=True,
        cold_payloads_externalized=True,
        artifact_integrity_verified=True,
        backup_restore_verified=True,
        backup_id="backup-staging-2026-09-04",
        backup_digest="2" * 64,
        restore_target_id="restore-check-2026-09-04",
        restore_environment_id="isolated-restore-staging-v1",
        restore_checks_digest="3" * 64,
        restore_completed_at=datetime(2026, 9, 4, 12, tzinfo=UTC),
        restore_reviewer_id="test-storage-reviewer",
    )
    audit = _reference(measured_storage_audit_payload(draft))
    projection = _reference(storage_projection_payload(draft))
    backup = _reference(backup_restore_evidence_payload(draft))
    target = _reference(target_population_evidence_payload(draft))
    return replace(
        draft,
        measured_audit_digest=audit.sha256,
        measured_audit_reference=audit.uri,
        projection_evidence_digest=projection.sha256,
        projection_evidence_reference=projection.uri,
        backup_restore_evidence_digest=backup.sha256,
        backup_restore_evidence_reference=backup.uri,
        target_population_evidence_digest=target.sha256,
        target_population_evidence_reference=target.uri,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def scientific_gate(passed: bool, tmp_path: Path) -> ScientificGateEvidence:
    evidence = complete_metric_evidence()
    if not passed:
        evidence = replace(evidence, provenance_complete=False)
    decision = assess_joint_metric_activation(evidence)
    review = ScientificGateReview(
        reviewer_id="test-reviewer",
        reviewed_at=datetime(2026, 9, 4, tzinfo=UTC),
        evidence_digest=scientific_gate_evidence_digest(evidence),
        decision_digest=_digest(asdict(decision)),
        approved_for_full_load=decision.may_activate,
    )
    store = FilesystemArtifactStore(tmp_path / f"scientific-{passed}")
    artifact = store.put_bytes(
        scientific_gate_evidence_payload(evidence, decision, review),
        tier=StorageTier.WARM,
        media_type="application/json",
    )
    return verify_scientific_gate_evidence(
        evidence,
        artifact_store=store,
        evidence_artifact=artifact,
        review=review,
    )


def storage_gate(
    evidence: StorageBudgetEvidence, tmp_path: Path
) -> StorageGateEvidence:
    evidence = replace(
        evidence,
        measured_audit_digest=None,
        measured_audit_reference=None,
        projection_evidence_digest=None,
        projection_evidence_reference=None,
        backup_restore_evidence_digest=None,
        backup_restore_evidence_reference=None,
        target_population_evidence_digest=None,
        target_population_evidence_reference=None,
    )
    store = FilesystemArtifactStore(tmp_path / "storage-evidence")
    audit = store.put_bytes(
        measured_storage_audit_payload(evidence),
        tier=StorageTier.WARM,
        media_type="application/json",
    )
    projection = store.put_bytes(
        storage_projection_payload(evidence),
        tier=StorageTier.WARM,
        media_type="application/json",
    )
    backup = store.put_bytes(
        backup_restore_evidence_payload(evidence),
        tier=StorageTier.WARM,
        media_type="application/json",
    )
    target = store.put_bytes(
        target_population_evidence_payload(evidence),
        tier=StorageTier.WARM,
        media_type="application/json",
    )
    evidence = replace(
        evidence,
        measured_audit_digest=audit.sha256,
        measured_audit_reference=audit.uri,
        projection_evidence_digest=projection.sha256,
        projection_evidence_reference=projection.uri,
        backup_restore_evidence_digest=backup.sha256,
        backup_restore_evidence_reference=backup.uri,
        target_population_evidence_digest=target.sha256,
        target_population_evidence_reference=target.uri,
    )
    return verify_storage_gate_evidence(
        evidence,
        artifact_store=store,
        measured_audit_artifact=audit,
        projection_evidence_artifact=projection,
        backup_restore_evidence_artifact=backup,
        target_population_evidence_artifact=target,
        evidence_reference="artifact://storage-gate/v1",
    )


def test_storage_budget_gate_passes_only_with_conservative_headroom() -> None:
    decision = assess_storage_budget(complete_evidence())

    assert STORAGE_BUDGET_POLICY_V1.version == "storage-budget-gate-v1"
    assert decision.status == "pass"
    assert decision.may_start_full_load is True
    assert decision.steady_state_limit_bytes == 3_000_000_000
    assert decision.peak_limit_bytes == 4_000_000_000
    assert decision.conservative_steady_state_bytes == 2_500_000_000
    assert decision.conservative_peak_bytes == 3_500_000_000
    assert decision.input_evidence_digest == storage_budget_evidence_digest(
        complete_evidence()
    )
    assert len(decision.decision_digest) == 64
    assert decision.reasons == ()


def test_storage_budget_gate_enforces_steady_and_peak_limits() -> None:
    decision = assess_storage_budget(
        replace(
            complete_evidence(),
            projected_steady_state_bytes=2_500_000_001,
            projected_peak_bytes=3_200_000_001,
        )
    )

    assert decision.status == "withheld"
    assert "steady-state projection exceeds 60%" in " ".join(decision.reasons)
    assert "peak projection exceeds 80%" in " ".join(decision.reasons)


def test_storage_budget_gate_fails_closed_for_incomplete_evidence() -> None:
    decision = assess_storage_budget(
        StorageBudgetEvidence(
            capacity_bytes=None,
            current_used_bytes=None,
            measured_sample_papers=823,
            measured_sample_bytes=None,
            measured_fixed_bytes=None,
            measurement_environment_id=None,
            measured_at=None,
            target_papers=None,
            target_population_id=None,
            target_population_policy_version=None,
            target_population_cutoff=None,
            target_population_paper_ids_digest=None,
            projection_method_version=None,
            projected_steady_state_bytes=None,
            projected_peak_bytes=None,
            representative_final_schema=False,
            database_statistics_refreshed=False,
            peak_working_set_included=False,
            certification_storage_included=False,
            citation_storage_included=False,
            cold_payloads_externalized=False,
            artifact_integrity_verified=False,
            backup_restore_verified=False,
        )
    )

    reasons = " ".join(decision.reasons)
    assert decision.status == "withheld"
    assert "physical volume capacity is missing" in reasons
    assert "fewer than 10000 representative papers" in reasons
    assert "database statistics have not been refreshed" in reasons
    assert "peak WAL and migration/index working storage" in reasons
    assert "certification storage is absent" in reasons
    assert "citation storage is absent" in reasons
    assert "cold provider payloads" in reasons
    assert "backup and isolated restore" in reasons
    assert "measured storage audit evidence is missing" in reasons
    assert "storage projection evidence is missing" in reasons


def test_storage_budget_gate_rejects_internally_inconsistent_projection() -> None:
    decision = assess_storage_budget(
        replace(
            complete_evidence(),
            projected_steady_state_bytes=600_000_000,
            projected_peak_bytes=550_000_000,
        )
    )

    assert decision.status == "withheld"
    assert "projected peak storage is below projected steady state" in decision.reasons

    smaller_target = assess_storage_budget(
        replace(complete_evidence(), target_papers=9_999)
    )
    assert "target paper count is smaller" in " ".join(smaller_target.reasons)

    below_floor = assess_storage_budget(
        replace(
            complete_evidence(),
            measured_sample_bytes=500_000_000,
            measured_fixed_bytes=100_000_000,
            projected_steady_state_bytes=1_000_000_000,
        )
    )
    assert "below the deterministic v1 estimate" in " ".join(below_floor.reasons)

    nonisolated = assess_storage_budget(
        replace(
            complete_evidence(),
            restore_environment_id="representative-staging-v1",
        )
    )
    assert "did not use an isolated environment" in " ".join(nonisolated.reasons)


def test_storage_budget_gate_requires_checksum_bound_audit_and_projection() -> None:
    missing_audit = assess_storage_budget(
        replace(
            complete_evidence(),
            measured_audit_digest=None,
            measured_audit_reference=None,
        )
    )
    assert missing_audit.status == "withheld"
    assert "measured storage audit evidence is missing" in " ".join(
        missing_audit.reasons
    )

    with pytest.raises(ValueError, match="provided together"):
        replace(complete_evidence(), projection_evidence_reference=None)
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        replace(complete_evidence(), measured_audit_digest="not-a-digest")
    with pytest.raises(ValueError, match="boolean evidence"):
        replace(complete_evidence(), backup_restore_verified=1)  # type: ignore[arg-type]


def test_storage_decision_digest_binds_every_projection_input() -> None:
    first = assess_storage_budget(complete_evidence())
    changed = assess_storage_budget(
        replace(complete_evidence(), projected_peak_bytes=2_800_000_001)
    )

    assert first.input_evidence_digest != changed.input_evidence_digest
    assert first.decision_digest != changed.decision_digest


def test_linear_estimate_preserves_fixed_storage_and_rounds_up() -> None:
    assert (
        estimate_linear_storage(
            measured_bytes=1_001,
            measured_papers=10,
            target_papers=21,
            fixed_bytes=101,
        )
        == 1_991
    )
    with pytest.raises(ValueError, match="measured_papers must be positive"):
        estimate_linear_storage(
            measured_bytes=1,
            measured_papers=0,
            target_papers=1,
        )


@pytest.mark.parametrize(
    ("scientific_passed", "storage_passed", "authorized"),
    (
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ),
)
def test_full_physics_load_requires_both_independent_gates(
    scientific_passed: bool,
    storage_passed: bool,
    authorized: bool,
    tmp_path: Path,
) -> None:
    storage = storage_gate(
        complete_evidence()
        if storage_passed
        else replace(complete_evidence(), backup_restore_verified=False),
        tmp_path,
    )
    decision = assess_full_physics_load(
        scientific_gate=scientific_gate(scientific_passed, tmp_path),
        storage_gate=storage,
    )

    assert decision.may_start_full_load is authorized
    assert (decision.status == "authorized") is authorized
    assert len(decision.scientific_gate_evidence_digest) == 64
    assert len(decision.scientific_gate_decision_digest) == 64
    assert len(decision.scientific_gate_artifact_digest) == 64
    assert decision.storage_budget_decision_digest == storage.decision_digest
    assert decision.storage_gate_evidence_digest == storage.evidence_digest


def test_scientific_gate_requires_verified_review_artifact(tmp_path: Path) -> None:
    bound = scientific_gate(True, tmp_path)
    with pytest.raises(ValueError, match="must be built by"):
        ScientificGateEvidence(
            evidence=bound.evidence,
            decision=bound.decision,
            evidence_digest=bound.evidence_digest,
            evidence_reference=bound.evidence_reference,
            review=bound.review,
            evidence_artifact=bound.evidence_artifact,
        )

    changed = replace(bound.evidence, provenance_complete=False)
    with pytest.raises(ValueError, match="review evidence digest does not match"):
        verify_scientific_gate_evidence(
            changed,
            artifact_store=FilesystemArtifactStore(tmp_path / "scientific-True"),
            evidence_artifact=bound.evidence_artifact,
            review=bound.review,
        )


def test_full_load_rejects_deserialized_gate_lookalikes(tmp_path: Path) -> None:
    scientific = scientific_gate(True, tmp_path)
    storage = storage_gate(complete_evidence(), tmp_path)
    scientific_payload = SimpleNamespace(
        **vars(scientific), decision_digest=scientific.decision_digest
    )
    storage_payload = SimpleNamespace(**vars(storage))

    with pytest.raises(ValueError, match="verified scientific gate evidence"):
        assess_full_physics_load(
            scientific_gate=scientific_payload,
            storage_gate=storage,
        )
    with pytest.raises(ValueError, match="verified storage gate evidence"):
        assess_full_physics_load(
            scientific_gate=scientific,
            storage_gate=storage_payload,
        )


def test_storage_gate_requires_verified_typed_artifacts(tmp_path: Path) -> None:
    evidence = complete_evidence()
    bound = storage_gate(evidence, tmp_path)
    assert bound.decision.may_start_full_load is True

    with pytest.raises(ValueError, match="must be built by"):
        StorageGateEvidence(
            evidence=evidence,
            decision=assess_storage_budget(evidence),
            evidence_digest=storage_budget_evidence_digest(evidence),
            evidence_reference="artifact://storage-gate/forged",
            measured_audit_artifact=bound.measured_audit_artifact,
            projection_evidence_artifact=bound.projection_evidence_artifact,
            backup_restore_evidence_artifact=bound.backup_restore_evidence_artifact,
            target_population_evidence_artifact=(
                bound.target_population_evidence_artifact
            ),
        )

    mismatched = replace(evidence, current_used_bytes=600_000_000)
    with pytest.raises(ValueError, match="content does not match"):
        verify_storage_gate_evidence(
            mismatched,
            artifact_store=FilesystemArtifactStore(tmp_path / "storage-evidence"),
            measured_audit_artifact=bound.measured_audit_artifact,
            projection_evidence_artifact=bound.projection_evidence_artifact,
            backup_restore_evidence_artifact=bound.backup_restore_evidence_artifact,
            target_population_evidence_artifact=(
                bound.target_population_evidence_artifact
            ),
            evidence_reference="artifact://storage-gate/tampered",
        )

    changed_population = replace(evidence, target_population_id="different-population")
    with pytest.raises(ValueError, match="content does not match"):
        verify_storage_gate_evidence(
            changed_population,
            artifact_store=FilesystemArtifactStore(tmp_path / "storage-evidence"),
            measured_audit_artifact=bound.measured_audit_artifact,
            projection_evidence_artifact=bound.projection_evidence_artifact,
            backup_restore_evidence_artifact=bound.backup_restore_evidence_artifact,
            target_population_evidence_artifact=(
                bound.target_population_evidence_artifact
            ),
            evidence_reference="artifact://storage-gate/tampered-population",
        )
