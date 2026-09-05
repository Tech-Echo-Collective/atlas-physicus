"""Lossless local archival fixtures; no retained corpus, replay or network."""

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def helper(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    return importlib.import_module("compact_historical_artifact")


def source_fixture(root: Path, helper: Any) -> tuple[Path, Path, dict[str, str], bytes]:
    rows = [
        {
            "decision_id": f"fixture-{index}",
            "subject_id": f"paper-{index}",
            "subject_type": "paper",
            "state": state,
            "evidence_kind": "fixture-evidence",
            "rule_version": "unchanged-fixture-v1",
            "acquisition_scope": "offline-fixture",
            "dataset_version": "fixture-v1",
            "reasons": [] if index == 0 else ["retained reason φ"],
            "evidence": [{"checksum": "a" * 64, "storage_reference": "fixture#1"}],
            "unknown_future_field": {"zero": 0, "null": None, "fraction": "1/3"},
        }
        for index, state in enumerate(
            (
                "certified",
                "needs_review",
                "withheld",
                "conflicted",
                "insufficient_evidence",
            )
        )
    ]
    body = b"\r\n".join(json.dumps(row, ensure_ascii=False).encode() for row in rows)
    digest = hashlib.sha256(body).hexdigest()
    source = root / "certification" / "decisions" / f"{digest}.jsonl"
    source.parent.mkdir(parents=True)
    source.write_bytes(body)
    manifest = {
        "artifacts": [
            {
                "role": "evidence-certification-decisions",
                "checksum": digest,
                "path": str(source.relative_to(root)),
                "byte_count": len(body),
                "row_count": len(rows),
            }
        ],
        "source_bundle_manifest_checksum": "b" * 64,
        "dataset_version": "fixture-v1",
        "acquisition_scope": "offline-fixture",
    }
    manifest["certification_manifest_checksum"] = hashlib.sha256(
        helper.encoded(manifest)
    ).hexdigest()
    path = root / "certification" / "manifests" / "fixture.json"
    path.parent.mkdir()
    path.write_bytes(helper.encoded(manifest) + b"\n")
    return (
        source,
        path,
        {
            "expected_source_sha": digest,
            "expected_manifest_sha": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        body,
    )


def create_fixture(root: Path, helper: Any) -> tuple[Any, ...]:
    source, manifest, binding, body = source_fixture(root / "source", helper)
    result = helper.create_archive(source, manifest, root / "archive", **binding)
    return source, manifest, binding, body, result


def test_deterministic_archive_exact_order_and_scientific_projections(
    tmp_path: Path, helper: Any
) -> None:
    source, manifest, binding, body, result = create_fixture(tmp_path, helper)
    second = helper.create_archive(source, manifest, tmp_path / "second", **binding)
    archive_one = next((tmp_path / "archive").glob("*.gz"))
    archive_two = next((tmp_path / "second").glob("*.gz"))
    assert archive_one.stat().st_mode & 0o222 == 0
    assert Path(result["manifest_path"]).stat().st_mode & 0o222 == 0
    assert archive_one.read_bytes() == archive_two.read_bytes()
    restored = tmp_path / "restored.jsonl"
    recovered = helper.restore_archive(
        Path(result["manifest_path"]),
        restored,
        expected_manifest_sha=result["manifest_sha256"],
        compare_source=source,
    )
    assert restored.read_bytes() == source.read_bytes() == body
    preserved = json.loads(restored.read_bytes().splitlines()[0])[
        "unknown_future_field"
    ]
    assert preserved == {"zero": 0, "null": None, "fraction": "1/3"}
    assert "absent" not in preserved
    assert (
        result["scientific_summary"]
        == second["scientific_summary"]
        == recovered["scientific_summary"]
    )
    assert recovered["byte_for_byte_compared"]
    assert recovered["scientific_summary"]["counts"]["state"] == {
        "certified": 1,
        "needs_review": 1,
        "withheld": 1,
        "conflicted": 1,
        "insufficient_evidence": 1,
    }
    assert recovered["scientific_summary"]["evidence_reference_occurrences"] == 5
    assert recovered["scientific_summary"]["reason_entries"] == 4


def test_restore_requires_no_original_source_access(
    tmp_path: Path, helper: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _manifest, _binding, body, result = create_fixture(tmp_path, helper)
    original_open = Path.open

    def guarded_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == source:
            raise PermissionError("original unavailable")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    target = tmp_path / "independent.jsonl"
    recovered = helper.restore_archive(
        Path(result["manifest_path"]),
        target,
        expected_manifest_sha=result["manifest_sha256"],
    )
    assert target.read_bytes() == body
    assert not recovered["byte_for_byte_compared"]


@pytest.mark.parametrize(
    "binding_key", ["expected_source_sha", "expected_manifest_sha"]
)
def test_wrong_input_bindings_refuse_before_outputs(
    tmp_path: Path, helper: Any, binding_key: str
) -> None:
    source, manifest, binding, body = source_fixture(tmp_path / "source", helper)
    binding[binding_key] = "0" * 64
    with pytest.raises(helper.ArchiveError):
        helper.create_archive(source, manifest, tmp_path / "archive", **binding)
    assert not (tmp_path / "archive").exists()
    assert source.read_bytes() == body


def test_changed_source_leaves_no_published_manifest(
    tmp_path: Path, helper: Any
) -> None:
    source, manifest, binding, body = source_fixture(tmp_path / "source", helper)
    changed = body.replace(b"fixture-0", b"fixture-X", 1)
    source.write_bytes(changed)
    with pytest.raises(helper.ArchiveError, match="manifest binding"):
        helper.create_archive(source, manifest, tmp_path / "archive", **binding)
    assert not (tmp_path / "archive/archive-manifest.json").exists()
    assert source.read_bytes() == changed


def test_existing_output_and_restore_target_are_not_overwritten(
    tmp_path: Path, helper: Any
) -> None:
    source, manifest, binding, body, result = create_fixture(tmp_path, helper)
    with pytest.raises(FileExistsError):
        helper.create_archive(source, manifest, tmp_path / "archive", **binding)
    target = tmp_path / "restore.jsonl"
    target.write_bytes(b"preexisting")
    with pytest.raises(helper.ArchiveError, match="already exists"):
        helper.restore_archive(
            Path(result["manifest_path"]),
            target,
            expected_manifest_sha=result["manifest_sha256"],
        )
    assert target.read_bytes() == b"preexisting"
    assert source.read_bytes() == body


def test_interrupted_write_cannot_publish_archive_manifest(
    tmp_path: Path, helper: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, manifest, binding, body = source_fixture(tmp_path / "source", helper)
    original_write = helper.gzip.GzipFile.write
    calls = 0

    def interrupted_write(stream: Any, data: bytes) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected disk write interruption")
        return original_write(stream, data)

    monkeypatch.setattr(helper.gzip.GzipFile, "write", interrupted_write)
    with pytest.raises(OSError, match="injected"):
        helper.create_archive(source, manifest, tmp_path / "archive", **binding)
    assert not (tmp_path / "archive/archive-manifest.json").exists()
    assert source.read_bytes() == body
    assert len(list((tmp_path / "archive").glob("*.gz"))) == 1


@pytest.mark.parametrize("mutation", ["truncated", "corrupt"])
def test_bad_archive_is_rejected_before_restore_output(
    tmp_path: Path, helper: Any, mutation: str
) -> None:
    _source, _manifest, _binding, _body, result = create_fixture(tmp_path, helper)
    archive = next((tmp_path / "archive").glob("*.gz"))
    original = archive.read_bytes()
    archive.chmod(0o600)  # Explicit corruption of this disposable test fixture only.
    archive.write_bytes(
        original[:-4] if mutation == "truncated" else b"x" * len(original)
    )
    destination = tmp_path / "restore.jsonl"
    with pytest.raises(helper.ArchiveError, match="compressed artifact"):
        helper.restore_archive(
            Path(result["manifest_path"]),
            destination,
            expected_manifest_sha=result["manifest_sha256"],
        )
    assert not destination.exists()


def test_wrong_manifest_and_decoded_size_fail_closed(
    tmp_path: Path, helper: Any
) -> None:
    _source, _manifest, _binding, _body, result = create_fixture(tmp_path, helper)
    manifest_path = Path(result["manifest_path"])
    with pytest.raises(helper.ArchiveError, match="manifest checksum"):
        helper.restore_archive(
            manifest_path, tmp_path / "wrong.jsonl", expected_manifest_sha="0" * 64
        )
    manifest = json.loads(manifest_path.read_bytes())
    manifest["original"]["bytes"] -= 1
    changed = manifest_path.parent / "changed.json"
    changed.write_bytes(helper.encoded(manifest) + b"\n")
    with pytest.raises(helper.ArchiveError, match="declared size"):
        helper.restore_archive(
            changed,
            tmp_path / "bounded.jsonl",
            expected_manifest_sha=hashlib.sha256(changed.read_bytes()).hexdigest(),
        )


def test_compressed_size_and_manifest_bounds_precede_hashing(
    tmp_path: Path, helper: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source, _manifest, _binding, _body, result = create_fixture(tmp_path, helper)

    def forbidden_hash(_path: Path) -> None:
        raise AssertionError("oversized archive must not be hashed")

    monkeypatch.setattr(helper, "MAX_ARCHIVE_BYTES", 1)
    monkeypatch.setattr(helper, "digest_file", forbidden_hash)
    with pytest.raises(helper.ArchiveError, match="bounded regular file"):
        helper.restore_archive(
            Path(result["manifest_path"]),
            tmp_path / "oversize.jsonl",
            expected_manifest_sha=result["manifest_sha256"],
        )
    monkeypatch.setattr(helper, "MAX_MANIFEST_BYTES", 1)
    with pytest.raises(helper.ArchiveError, match="manifest must be"):
        helper.restore_archive(
            Path(result["manifest_path"]),
            tmp_path / "manifest.jsonl",
            expected_manifest_sha=result["manifest_sha256"],
        )


def test_archive_change_during_hashing_fails_before_restore(
    tmp_path: Path, helper: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source, _manifest, _binding, _body, result = create_fixture(tmp_path, helper)
    original_hash = helper.digest_file

    def changed_after_hash(path: Path) -> Any:
        result = original_hash(path)
        before = path.stat()
        helper.os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1))
        return result

    monkeypatch.setattr(helper, "digest_file", changed_after_hash)
    destination = tmp_path / "changed.jsonl"
    with pytest.raises(helper.ArchiveError, match="changed during integrity"):
        helper.restore_archive(
            Path(result["manifest_path"]),
            destination,
            expected_manifest_sha=result["manifest_sha256"],
        )
    assert not destination.exists()
