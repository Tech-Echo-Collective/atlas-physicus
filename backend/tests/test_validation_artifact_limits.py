"""Tiny fixtures only: no retained scientific corpus or provider/DB access."""

import importlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from test_historical_replay_materialization import _staged_acquisition
from test_paired_trial_certification import _fixture_bundle

from physics_atlas_api.certification import (
    CertificationError,
    canonical_digest,
    certify_replay_bundle,
    staging,
    summarize_replay_bundle,
    write_replay_certification_bundle,
)
from physics_atlas_api.certification import validation_artifacts as limits
from physics_atlas_api.historical_replay_materialization import (
    materialize_historical_replay,
)
from physics_atlas_api.paired_trial_certification import (
    _jsonl,
    certify_paired_trial,
    verify_paired_trial_certification_manifest,
)
from physics_atlas_api.replay_certification import run


@pytest.fixture
def replay(tmp_path: Path) -> tuple[Path, Path]:
    raw, source = _staged_acquisition(tmp_path)
    root = tmp_path / "fixture-replay"
    bundle = materialize_historical_replay(
        staging_root=raw, source_manifest=source, output=root, execute=True
    )
    assert bundle.output_manifest_path is not None
    return root, bundle.output_manifest_path


@pytest.mark.parametrize("maximum", [None, 0, -1, True, 2_501, 100_000, 1.5])
def test_unbounded_retention_rejects_before_read_or_output(
    maximum: Any, tmp_path: Path
) -> None:
    with pytest.raises(CertificationError, match="explicit validation_max_papers"):
        summarize_replay_bundle(
            bundle_root=tmp_path / "absent",
            bundle_manifest=tmp_path / "absent.json",
            output_root=tmp_path / "output",
            retain_decisions=True,
            validation_max_papers=maximum,
        )
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    "role,count",
    [
        ("paper-components", 2_501),
        ("researcher-appearances", 100_001),
    ],
)
def test_oversize_manifest_rejected_before_evidence_read(
    role: str,
    count: int,
    replay: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, manifest = replay
    value = json.loads(manifest.read_bytes())
    next(row for row in value["artifacts"] if row["role"] == role)["row_count"] = count
    value.pop("bundle_manifest_checksum")
    value["bundle_manifest_checksum"] = canonical_digest(value)
    changed = root / "manifests" / "oversize.json"
    changed.write_text(json.dumps(value))

    def no_evidence_read(*_: object) -> None:
        pytest.fail("oversize sample must reject before reading evidence")

    monkeypatch.setattr(staging, "_verify_artifact", no_evidence_read)
    with pytest.raises(CertificationError, match="(paper|decision) count exceeds"):
        summarize_replay_bundle(
            bundle_root=root,
            bundle_manifest=changed,
            output_root=tmp_path / "out",
            retain_decisions=True,
            validation_max_papers=2_500,
        )
    with pytest.raises(CertificationError, match="(paper count|too large)"):
        certify_replay_bundle(bundle_root=root, bundle_manifest=changed)
    assert not (tmp_path / "out").exists()


def test_runtime_byte_cap_cleans_partial_stream_and_preserves_science(
    replay: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, manifest = replay
    before = certify_replay_bundle(bundle_root=root, bundle_manifest=manifest)
    first_line = before.artifacts[0].content.splitlines(keepends=True)[0]
    output = tmp_path / "output"
    with monkeypatch.context() as patch:
        patch.setattr(limits, "MAX_VALIDATION_DECISION_BYTES", len(first_line))
        with pytest.raises(CertificationError, match="decision bytes exceed"):
            summarize_replay_bundle(
                bundle_root=root,
                bundle_manifest=manifest,
                output_root=output,
                retain_decisions=True,
                validation_max_papers=10,
            )
        assert not [path for path in output.rglob("*") if path.is_file()]
        # Summary-only hashes every same decision without retaining the trace.
        summary = summarize_replay_bundle(bundle_root=root, bundle_manifest=manifest)
        assert summary.decision_stream_checksum == before.artifacts[0].checksum
        assert summary.report["state_counts"] == before.report["state_counts"]
        assert (
            summary.report["withheld_reason_counts"]
            == before.report["withheld_reason_counts"]
        )
    after = certify_replay_bundle(bundle_root=root, bundle_manifest=manifest)
    assert after == before  # every scientific byte, provenance, state and version


def test_public_writer_cannot_bypass_output_cap(
    replay: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    root, manifest = replay
    result = certify_replay_bundle(bundle_root=root, bundle_manifest=manifest)
    exaggerated = replace(result.artifacts[0], row_count=100_001)
    with pytest.raises(CertificationError, match="decision count exceeds"):
        write_replay_certification_bundle(
            tmp_path / "out", replace(result, artifacts=(exaggerated,))
        )
    assert not (tmp_path / "out").exists()


def test_paired_bytes_remain_identical_and_limits_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {"state": "needs_review", "value": None},
        {"state": "certified", "value": 0},
    ]
    assert _jsonl(rows, validation_decisions=True) == _jsonl(rows)
    monkeypatch.setattr(limits, "MAX_VALIDATION_DECISIONS", 1)
    with pytest.raises(CertificationError, match="decision count exceeds"):
        _jsonl(rows, validation_decisions=True)


def test_public_writer_refuses_duplicate_traces(
    replay: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    root, manifest = replay
    result = certify_replay_bundle(bundle_root=root, bundle_manifest=manifest)
    with pytest.raises(CertificationError, match="exactly one decision trace"):
        write_replay_certification_bundle(
            tmp_path / "out", replace(result, artifacts=result.artifacts * 2)
        )
    assert not (tmp_path / "out").exists()


def test_paired_refuses_oversize_trace_before_any_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, raw_manifest, enrichment, enrichment_manifest, _, _ = _fixture_bundle(tmp_path)
    monkeypatch.setattr(limits, "MAX_VALIDATION_DECISION_BYTES", 1)
    with pytest.raises(CertificationError, match="decision bytes exceed"):
        certify_paired_trial(
            raw_root=raw,
            raw_manifest_path=raw_manifest,
            enrichment_root=enrichment,
            enrichment_manifest_path=enrichment_manifest,
            output=tmp_path / "refused",
        )
    assert not (tmp_path / "refused").exists()


@pytest.mark.parametrize(
    "operation",
    ["paired", "paired-verify", "replay", "summary", "writer", "recovery", "dual-read"],
)
def test_production_refuses_validation_before_io(
    operation: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHYSICS_ATLAS_ENVIRONMENT", "production")
    monkeypatch.setenv("PHYSICS_ATLAS_FIXTURE_MODE", "false")
    missing = tmp_path / "no-inputs"
    output = tmp_path / "output"
    with pytest.raises(CertificationError, match="forbidden in production"):
        if operation == "paired":
            certify_paired_trial(
                raw_root=missing,
                raw_manifest_path=missing,
                enrichment_root=missing,
                enrichment_manifest_path=missing,
                output=output,
            )
        elif operation == "paired-verify":
            verify_paired_trial_certification_manifest(
                missing,
                raw_root=missing,
                raw_manifest_path=missing,
                enrichment_root=missing,
                enrichment_manifest_path=missing,
                output=output,
            )
        elif operation == "replay":
            certify_replay_bundle(bundle_root=missing, bundle_manifest=missing)
        elif operation == "summary":
            summarize_replay_bundle(bundle_root=missing, bundle_manifest=missing)
        elif operation == "writer":
            write_replay_certification_bundle(output, None)  # type: ignore[arg-type]
        else:
            monkeypatch.syspath_prepend(
                str(Path(__file__).resolve().parents[1] / "tools")
            )
            if operation == "recovery":
                importlib.import_module("verify_payload_recovery").run_pilot(
                    missing, output
                )
            else:
                importlib.import_module("verify_staging_dual_read").run(
                    missing, output, missing
                )
    assert not output.exists()


def test_dotenv_production_cannot_bypass_runtime_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PHYSICS_ATLAS_ENVIRONMENT", raising=False)
    monkeypatch.delenv("PHYSICS_ATLAS_FIXTURE_MODE", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "PHYSICS_ATLAS_ENVIRONMENT=production\nPHYSICS_ATLAS_FIXTURE_MODE=false\n"
    )
    with pytest.raises(CertificationError, match="forbidden in production"):
        limits.require_validation_runtime()


def test_cli_retention_without_sample_fails_before_manifest_read(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        run(
            (
                "--bundle-root",
                str(tmp_path),
                "--bundle-manifest",
                "absent",
                "--output",
                str(tmp_path / "out"),
                "--retain-decisions",
            )
        )
    assert error.value.code == 2
    assert "explicit validation_max_papers" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
