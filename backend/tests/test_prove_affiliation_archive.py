"""Fixture-only isolated proof runner; real OS isolation is an external control."""

from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path
from typing import Any

import pytest

from physics_atlas_api.storage import affiliation_archive as codec
from physics_atlas_api.storage import historical_authority as authority
from physics_atlas_api.storage import historical_read as reader


def write_json(path: Path, value: object) -> str:
    body = codec.encoded(value) + b"\n"
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


@pytest.fixture
def proof(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    runner = importlib.import_module("prove_affiliation_archive")
    kit = tmp_path / "kit"
    kit.mkdir()
    old = tmp_path / "old"
    old.mkdir()
    role = "affiliation-shares"
    schema = "physics-paired-trial-certification-manifest-v2"
    body = b"\n".join(
        codec.encoded(
            {
                "canonical_paper_id": "p1",
                "paper_time_affiliation_share_id": "share-" + state,
                "mass": {"exact": "1/2"},
                "raw_affiliations": ["dated fixture affiliation"]
                if state == "certified"
                else [],
                "canonical_institution_id": "ror:fixture"
                if state == "certified"
                else None,
                "institution_certification_id": "cert-fixture"
                if state == "certified"
                else None,
                "institution_state": state,
                "institution_reasons": ["unchanged-fixture-reason"],
                "policy_version": "unchanged-fixture-v1",
                "provenance": {"reference": "fixture#1"},
                "eligible_for_public_metrics": state == "certified",
                "source_lineage": [
                    {
                        "provider": "fixture",
                        "source_record_id": "fixture-paper-1",
                        "source_record_checksum": "a" * 64,
                        "page_path": "fixture-provider-not-read.json",
                    }
                ],
                "unknown_field": {"missing": None, "zero": 0},
            }
        )
        for state in ("certified", "needs_review")
    )
    sha = hashlib.sha256(body).hexdigest()
    artifact = {
        "type": role,
        "schema_version": schema,
        "sha256": sha,
        "bytes": len(body),
        "rows": 2,
        "logical_id": authority.logical_artifact_id(role, schema, sha),
    }
    entry = authority._affiliation_entry(artifact)
    original = old / entry["path"]
    original.parent.mkdir(parents=True)
    original.write_bytes(body)
    manifest = {"manifest_version": schema, "artifacts": [entry]}
    manifest["manifest_checksum"] = hashlib.sha256(codec.encoded(manifest)).hexdigest()
    (kit / "manifests").mkdir()
    copied_manifest = kit / "manifests/00.json"
    manifest_sha = write_json(copied_manifest, manifest)
    historical_path = old / "manifests/old.json"
    binding = authority.affiliation_binding_record(
        copied_manifest,
        manifest_sha,
        artifact,
        historical_recorded_path=historical_path,
    )
    created = codec.create_archive(
        original,
        kit / "archive",
        expected_source_sha=sha,
        expected_bytes=len(body),
        expected_rows=2,
        role=role,
        schema_version=schema,
        historical_bindings=[binding],
    )
    descriptor = {
        "version": authority.DESCRIPTOR_VERSION,
        "artifact": artifact,
        "authoritative_representation": "archive",
        "representations": [
            {
                "id": "archive",
                "type": "archive",
                "storage_reference": "archive/archive-manifest.json",
                "restore_method": codec.VERSION,
                "archive_manifest_sha256": created["manifest_sha256"],
            }
        ],
    }
    descriptor_sha = write_json(kit / "descriptor.json", descriptor)
    bundle = kit / "bindings/00"
    bundle.mkdir(parents=True)
    index = {
        "version": reader.INDEX_VERSION,
        "entries": [
            {
                "relative_path": entry["path"],
                "role": role,
                "checksum": sha,
                "byte_count": len(body),
                "row_count": 2,
                "descriptor_path": "../../descriptor.json",
                "descriptor_sha256": descriptor_sha,
                "storage_root": "../..",
                "historical_manifest_path": "../../manifests/00.json",
                "historical_manifest_sha256": manifest_sha,
                "historical_recorded_path": str(historical_path),
            }
        ],
    }
    write_json(bundle / "artifact-authority.json", index)
    plan = {
        "version": runner.VERSION,
        "descriptor_path": "descriptor.json",
        "descriptor_sha256": descriptor_sha,
        "storage_root": ".",
        "bindings": [
            {
                "bundle_root": "bindings/00",
                "manifest_path": "manifests/00.json",
                "manifest_sha256": manifest_sha,
                "historical_recorded_path": str(historical_path),
                "original_path": str(original),
                "entry": entry,
            }
        ],
        "expected_scientific_summary": created["scientific_summary"],
        "denied_paths": {"original_root": str(old)},
    }
    plan_path = kit / "plan.json"
    plan_sha = write_json(plan_path, plan)
    arguments = {
        "plan_path": plan_path,
        "plan_sha256": plan_sha,
        "kit": kit,
        "output": tmp_path / "receipt.json",
    }
    saved_open = os.open

    def deny_originals(path: Any, *args: Any, **kwargs: Any) -> int:
        if Path(path) in (old, original):
            raise PermissionError("fixture OS denial")
        return saved_open(path, *args, **kwargs)

    class DeniedSocket:
        def __enter__(self) -> DeniedSocket:
            return self

        def __exit__(self, *_args: Any) -> None:
            pass

        def connect(self, _address: Any) -> None:
            raise PermissionError("fixture network denial")

    saved_path_open = Path.open

    def guard_real_original(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path.is_relative_to(old):
            pytest.fail("recovery must not read historical original")
        return saved_path_open(path, *args, **kwargs)

    monkeypatch.setattr(runner.os, "open", deny_originals)
    monkeypatch.setattr(runner.socket, "socket", DeniedSocket)
    monkeypatch.setattr(Path, "open", guard_real_original)
    return {
        "runner": runner,
        "plan": plan,
        "arguments": arguments,
        "original": original,
        "body": body,
    }


def test_fixture_bridge_proof_is_exact_and_cleans_expanded_file(
    proof: dict[str, Any],
) -> None:
    receipt = proof["runner"].run(**proof["arguments"])
    assert receipt["result"] == "PASS"
    assert receipt["scientific_summary"] == proof["plan"]["expected_scientific_summary"]
    assert receipt["bindings"][0]["temporary_expanded_file_removed"] is True
    assert receipt["controls"]["original_00"] == "OS_permission_denied"
    assert receipt["controls"]["network_connect"] == "OS_permission_denied"
    assert receipt["certification_decisions_regenerated"] is False
    assert receipt["metric_observations_created"] == 0
    assert proof["original"].exists()


@pytest.mark.parametrize("change", ["summary", "binding", "plan-pin", "outside-kit"])
def test_proof_refuses_inconsistent_pins_without_receipt(
    proof: dict[str, Any], change: str
) -> None:
    plan, arguments = proof["plan"], proof["arguments"]
    if change == "summary":
        plan["expected_scientific_summary"]["total_exact_mass"] = "99"
    elif change == "binding":
        plan["bindings"][0]["original_path"] += ".wrong"
    elif change == "outside-kit":
        plan["descriptor_path"] = "../elsewhere.json"
    arguments["plan_sha256"] = write_json(arguments["plan_path"], plan)
    if change == "plan-pin":
        arguments["plan_sha256"] = "a" * 64
    with pytest.raises(ValueError):
        proof["runner"].run(**arguments)
    assert not arguments["output"].exists()


def test_guard_failure_and_existing_receipt_never_read_original(
    proof: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, arguments = proof["runner"], proof["arguments"]
    closed = []
    monkeypatch.setattr(runner.os, "open", lambda *_args, **_kwargs: 42)
    monkeypatch.setattr(runner.os, "close", closed.append)
    with pytest.raises(RuntimeError, match="read denial did not hold"):
        runner.denied_controls({"original": str(proof["original"])})
    assert closed == [42]
    arguments["output"].write_bytes(b"retained receipt")
    with pytest.raises(ValueError, match="must be new"):
        runner.run(**arguments)
    assert arguments["output"].read_bytes() == b"retained receipt"


def test_existing_parser_and_certification_decisions_equal_for_inline_and_archive(
    proof: dict[str, Any],
) -> None:
    from physics_atlas_api.certification import staging
    from physics_atlas_api.certification.contracts import (
        CertificationError,
        require_certified_partition,
    )

    kit = proof["arguments"]["kit"]
    binding = proof["plan"]["bindings"][0]
    entry = binding["entry"]
    inline_root = kit / "fixture-inline"
    inline_path = inline_root / entry["path"]
    inline_path.parent.mkdir(parents=True)
    inline_path.write_bytes(proof["body"])  # Independent fixture input, not original.
    outputs = []
    for root in (inline_root, kit / binding["bundle_root"]):
        artifact = staging._ArtifactEntry(
            role=entry["role"],
            path=root / entry["path"],
            relative_path=entry["path"],
            checksum=entry["checksum"],
            byte_count=entry["byte_count"],
            row_count=entry["row_count"],
            bundle_root=root,
        )
        rows = list(staging._rows(artifact))
        decisions = tuple(
            decision
            for row in rows
            for decision in staging._affiliation_decisions(
                row,
                "fixture-dataset-v1",
                "fixture-scope",
                binding["manifest_sha256"],
                artifact,
            )
        )
        outputs.append((rows, decisions))
        for row in rows:
            assert row["unknown_field"] == {"missing": None, "zero": 0}
            with pytest.raises(CertificationError, match="certify evidence first"):
                require_certified_partition(
                    row,
                    metric_id="research_activity_score",
                    threshold_version="metric-validation-thresholds-v1",
                )
    # Exact dataclass equality includes decision IDs, states, reasons, versions,
    # dataset/scope identity, and unchanged historical and provider references.
    assert outputs[0] == outputs[1]
    assert {item.state for item in outputs[0][1]} == {
        "certified",
        "needs_review",
        "insufficient_evidence",
    }
    assert all(item.evidence for item in outputs[0][1])
    assert any(item.reasons for item in outputs[0][1])
