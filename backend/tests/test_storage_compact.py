import json
from dataclasses import asdict, replace
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import pytest
from certification_helpers import certify_partition
from test_metric_system_v1 import paper, partition

from physics_atlas_api.certification import (
    CertificationError,
    EvidenceCertificationDecision,
    EvidenceReference,
)
from physics_atlas_api.metrics import calculate_activity_raw
from physics_atlas_api.storage import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FilesystemArtifactStore,
)
from physics_atlas_api.storage.compact import compact_decisions, recover_decisions


def decision(
    state: str = "needs_review", *, identity: str = "cert-a"
) -> dict[str, object]:
    return {
        "decision_id": identity,
        "canonical_paper_id": "paper-a",
        "subject_type": "paper",
        "subject_id": "paper-a",
        "evidence_kind": "field-weight-conservation",
        "state": state,
        "rule_version": "field-rule-v1",
        "dataset_version": "fixture-storage-v1",
        "acquisition_scope": "fixture-bounded-scope",
        "reasons": ["exact field assignment awaits review"],
        "evidence": [
            {
                "provider": "fixture",
                "source_record_id": "source-a",
                "source_snapshot_id": "snapshot-a",
                "storage_reference": "fixture://snapshot-a#paper-a",
                "checksum": "a" * 64,
            }
        ],
        "mass": {"exact": "1", "numerator": 1, "denominator": 1, "decimal": 1.0},
        "reviewed_at": None,
        "reviewed_by": None,
        "scope_ids": ["fixture-bounded-scope"],
    }


@pytest.mark.parametrize(
    "state",
    ["certified", "needs_review", "withheld", "conflicted", "insufficient_evidence"],
)
def test_roundtrip_preserves_every_state_reason_and_provenance(
    state: str, tmp_path: Path
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    original = decision(state)
    batch = compact_decisions([original], store)
    assert batch.rows[0].state == state
    assert batch.reasons[batch.rows[0].reason_code] == tuple(original["reasons"])
    assert recover_decisions(batch, store) == (original,)
    # Even "certified" rows are storage projections, not calculation credentials.
    with pytest.raises(CertificationError, match="certify evidence first"):
        calculate_activity_raw(batch.rows[0])  # type: ignore[arg-type]
    with pytest.raises(CertificationError, match="certify evidence first"):
        calculate_activity_raw(recover_decisions(batch, store)[0])  # type: ignore[arg-type]


def test_batch_is_deterministic_deduplicates_reasons_and_detaches_input(
    tmp_path: Path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    originals = [decision(identity="cert-b"), decision(identity="cert-a")]
    first = compact_decisions(originals, store)
    second = compact_decisions(list(reversed(originals)), store)
    assert first == second
    assert first.artifact == second.artifact
    assert len(first.reasons) == 1
    assert [row.audit_ordinal for row in first.rows] == [0, 1]
    originals[0]["state"] = "certified"
    assert recover_decisions(first, store)[1]["state"] == "needs_review"


def test_unknown_json_fields_missing_zero_and_conserved_mass_are_lossless(
    tmp_path: Path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    original = decision()
    original["future_evidence"] = {
        "missing": None,
        "measured_zero": 0,
        "not_reviewed": False,
        "field_weights": ["1/3", "1/3"],
        "explicit_unmapped": "1/3",
        "attribution_weights": ["1/4", "1/2"],
        "unresolved_attribution": "1/4",
        "unicode_name": "Instituto de Física",
    }
    restored = recover_decisions(compact_decisions([original], store), store)[0]
    assert restored == original
    values = restored["future_evidence"]
    assert isinstance(values, dict)
    assert "absent" not in values
    assert values["missing"] is None
    assert values["measured_zero"] == 0 and values["not_reviewed"] is False
    assert (
        sum(Fraction(weight) for weight in values["field_weights"])
        + Fraction(values["explicit_unmapped"])
        == 1
    )
    assert (
        sum(Fraction(weight) for weight in values["attribution_weights"])
        + Fraction(values["unresolved_attribution"])
        == 1
    )


def test_reconstructed_typed_evidence_keeps_calculation_and_proof_identical(
    tmp_path: Path,
) -> None:
    original = certify_partition(
        partition("institution-a", tuple(paper(index, 2025) for index in range(10))),
        "research_activity_score",
    )
    source = original.certification.evidence_decisions
    payloads = []
    for evidence in source:
        # The storage boundary consumes serialized JSON, not Python proof objects.
        payload = json.loads(json.dumps(asdict(evidence), default=str))
        payload["decision_id"] = evidence.decision_id
        payloads.append(payload)
    store = FilesystemArtifactStore(tmp_path)
    batch = compact_decisions(payloads, store)
    reconstructed = {}
    for payload in recover_decisions(batch, store):
        values = dict(payload)
        identity = values.pop("decision_id")
        values["evidence"] = tuple(
            EvidenceReference(**item) for item in values["evidence"]
        )
        values["reasons"] = tuple(values["reasons"])
        if values["reviewed_at"] is not None:
            values["reviewed_at"] = datetime.fromisoformat(values["reviewed_at"])
        restored = EvidenceCertificationDecision(**values)
        assert restored.decision_id == identity
        reconstructed[identity] = restored
    recovered_decisions = tuple(reconstructed[item.decision_id] for item in source)
    assert recovered_decisions == source
    # Reconstruct via the unchanged exact-typed proof validation, not the hot rows.
    recovered = replace(
        original,
        certification=replace(
            original.certification, evidence_decisions=recovered_decisions
        ),
    )
    assert recovered.certification.certification_digest == (
        original.certification.certification_digest
    )
    assert calculate_activity_raw(recovered) == calculate_activity_raw(original)


def test_missing_cold_archive_fails_closed(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path / "available")
    batch = compact_decisions([decision()], store)
    missing_store = FilesystemArtifactStore(tmp_path / "missing")
    with pytest.raises(ArtifactNotFoundError):
        recover_decisions(batch, missing_store)


def test_corrupted_cold_archive_fails_closed(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    batch = compact_decisions([decision()], store)
    store.local_path(batch.artifact).write_bytes(b"broken archive")
    with pytest.raises(ArtifactIntegrityError):
        recover_decisions(batch, store)


@pytest.mark.parametrize(
    "changed",
    [
        {"state": "certified"},
        {"decision_sha256": "0" * 64},
        {"rule_version": "unreviewed-v2"},
        {"canonical_paper_id": "another-paper"},
        {"reason_code": 100},
        {"audit_ordinal": 1},
    ],
)
def test_modified_hot_projection_cannot_recover(
    changed: dict[str, object], tmp_path: Path
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    batch = compact_decisions([decision()], store)
    tampered = replace(batch, rows=(replace(batch.rows[0], **changed),))
    with pytest.raises(ArtifactIntegrityError, match="projection differs"):
        recover_decisions(tampered, store)


def test_changed_scope_reason_or_batch_version_cannot_recover(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    batch = compact_decisions([decision()], store)
    for changed in (
        replace(batch, acquisition_scope="different"),
        replace(batch, reasons=(("invented explanation",),)),
        replace(batch, version="unreviewed-format-v2"),
        replace(batch, rows=()),
    ):
        with pytest.raises(ArtifactIntegrityError):
            recover_decisions(changed, store)


def test_duplicate_scope_mixing_non_json_and_oversize_inputs_fail(
    tmp_path: Path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    with pytest.raises(ValueError, match="duplicate"):
        compact_decisions([decision(), decision()], store)
    different = decision(identity="cert-b")
    different["dataset_version"] = "other-dataset"
    with pytest.raises(ValueError, match="cannot mix"):
        compact_decisions([decision(), different], store)
    invalid = decision()
    invalid["future_field"] = float("nan")
    with pytest.raises(ValueError):
        compact_decisions([invalid], store)
    invalid["future_field"] = {"tuple": (1, 2)}
    with pytest.raises(ValueError, match="JSON values"):
        compact_decisions([invalid], store)
    with pytest.raises(ValueError, match="between 1 and 10,000"):
        compact_decisions([decision()] * 10_001, store)
