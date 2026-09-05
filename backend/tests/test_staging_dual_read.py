"""Small fixture-only orchestration tests; no retained corpus or provider calls."""

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from test_paired_trial_certification import _fixture_bundle

from physics_atlas_api.certification.contracts import CertificationError
from physics_atlas_api.metrics import calculate_activity_raw
from physics_atlas_api.paired_capture import verify_paired_capture_manifest
from physics_atlas_api.paired_trial_certification import (
    _canonicalize,
    _load_occurrences,
    certify_paired_trial,
)
from physics_atlas_api.storage import FilesystemArtifactStore
from physics_atlas_api.storage.dual_read import (
    PayloadAccessError,
    new_inline_state,
    prepare_reference,
    rollback_to_inline,
)
from physics_atlas_api.storage.payloads import PayloadMetadata


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    return importlib.import_module("verify_staging_dual_read")


def _rows(runner: Any, raw: Path, enrichment: Path) -> list[dict[str, Any]]:
    rows = []
    for tree, root in (("raw", raw), ("enrichment", enrichment)):
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            state = new_inline_state(
                path.read_bytes(),
                PayloadMetadata(
                    provider="offline-fixture",
                    provider_record_id=path.relative_to(root).as_posix(),
                    acquisition_id="fixture-acquisition",
                    snapshot_id=path.stem,
                    acquisition_scope="offline-test-only",
                    dataset_version="unchanged-fixture-v1",
                    acquired_at="2026-09-04T12:00:00+00:00",
                    status="fixture-not-live",
                    media_type="application/octet-stream",
                ),
            )
            inline, packed = runner.pack_state(state)
            row = {
                "tree": tree,
                "path": path.relative_to(root).as_posix(),
                "inline_payload": inline,
                # Exercise the actual JSONB semantic round trip, not shared objects.
                "state": json.loads(json.dumps(packed)),
            }
            assert runner.unpack_state(row) == state
            rows.append(row)
    return rows


def test_inline_reference_and_rollback_share_parser_and_certifier(
    tmp_path: Path, runner: Any
) -> None:
    raw, raw_manifest, enrichment, enrichment_manifest, baseline, manifest = (
        _fixture_bundle(tmp_path)
    )
    rows = _rows(runner, raw, enrichment)
    store = FilesystemArtifactStore(tmp_path / "cold")
    original = _load_occurrences(
        raw, verify_paired_capture_manifest(raw_manifest, output=raw)
    )
    for mode in ("inline", "reference", "rollback"):
        if mode != "inline":
            for row in rows:
                state = runner.unpack_state(row)
                changed = (
                    prepare_reference(state, store)
                    if mode == "reference"
                    else rollback_to_inline(state)
                )
                inline, packed = runner.pack_state(changed)
                assert inline == row["inline_payload"]
                row["state"] = json.loads(json.dumps(packed))
                assert runner.unpack_state(row) == changed
                with pytest.raises(CertificationError, match="certify evidence first"):
                    calculate_activity_raw(changed)  # type: ignore[arg-type]
        restored = tmp_path / mode
        selected_store = (
            runner.UnavailableStore(tmp_path / "cold") if mode == "rollback" else store
        )
        assert runner.restore_files(rows, selected_store, restored) == len(rows)
        restored_raw_manifest = restored / "raw" / raw_manifest.relative_to(raw)
        recovered = _load_occurrences(
            restored / "raw",
            verify_paired_capture_manifest(
                restored_raw_manifest, output=restored / "raw"
            ),
        )
        assert original == recovered
        assert _canonicalize(original) == _canonicalize(recovered)
        result, path = certify_paired_trial(
            raw_root=restored / "raw",
            raw_manifest_path=restored_raw_manifest,
            enrichment_root=restored / "enrichment",
            enrichment_manifest_path=restored
            / "enrichment"
            / enrichment_manifest.relative_to(enrichment),
            output=restored / "certification",
        )
        assert path.read_bytes() == manifest.read_bytes()
        assert len(result["artifacts"]) == 10
        for artifact in result["artifacts"]:
            assert (restored / "certification" / artifact["path"]).read_bytes() == (
                baseline / artifact["path"]
            ).read_bytes()
        assert result["metric_observations_created"] == 0
        assert result["certified_complete_year_count"] == 0
        assert result["certified_metric_window_count"] == 0


def test_late_archive_failure_creates_no_parser_or_certification_input(
    tmp_path: Path, runner: Any
) -> None:
    raw, _raw_manifest, enrichment, _enrichment_manifest, _baseline, _manifest = (
        _fixture_bundle(tmp_path)
    )
    rows = _rows(runner, raw, enrichment)
    store = FilesystemArtifactStore(tmp_path / "cold")
    for row in rows:
        state = prepare_reference(runner.unpack_state(row), store)
        row["inline_payload"], row["state"] = runner.pack_state(state)
    state = runner.unpack_state(rows[-1])
    assert state.reference is not None
    # Remove only a disposable fixture archive. Retained inline bytes still exist,
    # but reference mode must not use them as a silent scientific fallback.
    store.local_path(state.reference.artifact).unlink()
    destination = tmp_path / "blocked"
    with pytest.raises(PayloadAccessError):
        runner.restore_files(rows, store, destination)
    assert not destination.exists()


def test_restore_rejects_path_escape_before_writing(
    tmp_path: Path, runner: Any
) -> None:
    row = {"tree": "raw", "path": "../outside"}
    with pytest.raises(ValueError, match="inside its staging tree"):
        runner.restore_files([row], None, tmp_path / "destination")
    assert not (tmp_path / "destination").exists()


def test_failure_rehearsal_does_not_disguise_an_unexpected_runtime_bug(
    runner: Any,
) -> None:
    class Batch:
        def fingerprint(self) -> str:
            return "unchanged"

    def unexpected_bug() -> None:
        raise RuntimeError("unexpected implementation bug")

    with pytest.raises(RuntimeError, match="unexpected implementation bug"):
        runner.blocked_attempt(Batch(), "missing_artifact", unexpected_bug)


def test_optimized_python_cannot_disable_scientific_proof_checks(
    tmp_path: Path,
) -> None:
    tool = Path(__file__).resolve().parents[1] / "tools" / "verify_staging_dual_read.py"
    result = subprocess.run(  # noqa: S603 -- fixed local interpreter/script and test paths
        [
            sys.executable,
            "-O",
            str(tool),
            "--evidence",
            str(tmp_path / "unread-input"),
            "--output",
            str(tmp_path / "uncreated-output"),
            "--socket",
            str(tmp_path / "unopened-socket"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "optimized Python is forbidden" in result.stderr
    assert not (tmp_path / "uncreated-output").exists()
