"""Offline authority/restore fixtures; no corpus, provider or production access."""

import copy
import hashlib
import importlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.contracts import require_certified_partition


@pytest.fixture
def resolver(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    return importlib.import_module("resolve_historical_artifact")


def write_json(path: Path, value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


@pytest.fixture
def bundle(tmp_path: Path, resolver: Any) -> dict[str, Any]:
    helper = resolver.archive_helper
    root = tmp_path / "storage"
    root.mkdir()
    rows = [
        {
            "decision_id": f"fixture-{index}",
            "subject_id": f"paper-{index}",
            "subject_type": "paper",
            "state": state,
            "evidence_kind": "fixture-kind",
            "rule_version": "unchanged-fixture-v1",
            "acquisition_scope": "fixture-only",
            "dataset_version": "fixture-v1",
            "evidence": [{"checksum": "a" * 64, "storage_reference": "fixture#1"}],
            "reasons": ["unchanged reason φ"] if index else [],
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
    sha = hashlib.sha256(body).hexdigest()
    source = root / "original/certification/decisions" / f"{sha}.jsonl"
    source.parent.mkdir(parents=True)
    source.write_bytes(body)
    historical = {
        "certification_version": resolver.ARTIFACT_SCHEMA_VERSION,
        "source_bundle_manifest_checksum": "b" * 64,
        "dataset_version": "fixture-v1",
        "acquisition_scope": "fixture-only",
        "decision_stream": {
            "checksum": sha,
            "byte_count": len(body),
            "row_count": len(rows),
            "artifact_available": True,
        },
        "summary_only": False,
        "artifacts": [
            {
                "role": resolver.ARTIFACT_TYPE,
                "path": f"certification/decisions/{sha}.jsonl",
                "checksum": sha,
                "byte_count": len(body),
                "row_count": len(rows),
            }
        ],
    }
    historical["certification_manifest_checksum"] = hashlib.sha256(
        helper.encoded(historical)
    ).hexdigest()
    manifest = root / "original/certification/manifests/fixture.json"
    manifest.parent.mkdir()
    historical_sha = write_json(manifest, historical)
    created = helper.create_archive(
        source,
        manifest,
        root / "archive",
        expected_source_sha=sha,
        expected_manifest_sha=historical_sha,
    )
    descriptor = {
        "version": resolver.DESCRIPTOR_VERSION,
        "artifact": {
            "type": resolver.ARTIFACT_TYPE,
            "schema_version": resolver.ARTIFACT_SCHEMA_VERSION,
            "sha256": sha,
            "bytes": len(body),
            "rows": len(rows),
            "logical_id": resolver.logical_artifact_id(
                resolver.ARTIFACT_TYPE, resolver.ARTIFACT_SCHEMA_VERSION, sha
            ),
        },
        "authoritative_representation": "archive-v1",
        "representations": [
            {
                "id": "archive-v1",
                "type": "archive",
                "storage_reference": "archive/archive-manifest.json",
                "restore_method": helper.VERSION,
                "archive_manifest_sha256": created["manifest_sha256"],
            },
            {
                "id": "original-v1",
                "type": "original",
                "storage_reference": source.relative_to(root).as_posix(),
                "restore_method": resolver.ORIGINAL_METHOD,
            },
        ],
    }
    descriptor_path = root / "descriptor.json"
    descriptor_sha = write_json(descriptor_path, descriptor)
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    return {
        "root": root,
        "source": source,
        "body": body,
        "rows": rows,
        "manifest": manifest,
        "manifest_sha": historical_sha,
        "descriptor": descriptor,
        "descriptor_path": descriptor_path,
        "descriptor_sha": descriptor_sha,
        "temporary": temporary,
        "archive_manifest": Path(created["manifest_path"]),
        "archive": root / "archive" / f"{sha}.jsonl.gz",
    }


def resolve(resolver: Any, bundle: dict[str, Any]) -> Any:
    return resolver.resolve_historical_artifact(
        bundle["descriptor_path"],
        expected_descriptor_sha256=bundle["descriptor_sha"],
        storage_root=bundle["root"],
        certification_manifest=bundle["manifest"],
        expected_certification_manifest_sha256=bundle["manifest_sha"],
        temp_parent=bundle["temporary"],
    )


def repin(bundle: dict[str, Any]) -> None:
    bundle["descriptor_sha"] = write_json(
        bundle["descriptor_path"], bundle["descriptor"]
    )


def test_original_and_archive_authority_same_exact_bytes_and_summary(
    resolver: Any, bundle: dict[str, Any]
) -> None:
    before = bundle["manifest"].read_bytes()
    with resolve(resolver, bundle) as archived:
        assert archived.path.read_bytes() == bundle["body"]
        assert archived.representation_type == "archive"
        summary = archived.scientific_summary
        row = json.loads(archived.path.read_bytes().splitlines()[0])
        assert row["unknown_future_field"] == {
            "zero": 0,
            "null": None,
            "fraction": "1/3",
        }
        assert "absent" not in row["unknown_future_field"]
        assert summary["counts"]["state"] == {row["state"]: 1 for row in bundle["rows"]}
    assert not archived.path.exists()
    bundle["descriptor"]["authoritative_representation"] = "original-v1"
    repin(bundle)
    with resolve(resolver, bundle) as original:
        assert original.path.read_bytes() == bundle["body"]
        assert original.scientific_summary == summary
        assert original.logical_artifact_id == archived.logical_artifact_id
    assert bundle["manifest"].read_bytes() == before
    assert bundle["source"].read_bytes() == bundle["body"]
    assert not list(bundle["temporary"].iterdir())


def test_archive_resolution_never_opens_or_stats_original(
    resolver: Any, bundle: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    source = bundle["source"]
    original_open, original_stat = Path.open, Path.stat

    def guarded_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == source:
            raise AssertionError("original must never be opened")
        return original_open(path, *args, **kwargs)

    def guarded_stat(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == source:
            raise AssertionError("original must never be probed")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(Path, "stat", guarded_stat)
    with resolve(resolver, bundle) as result:
        assert result.path.read_bytes() == bundle["body"]


def test_identity_and_archive_resolution_are_location_independent(
    resolver: Any, bundle: dict[str, Any], tmp_path: Path
) -> None:
    moved = tmp_path / "moved"
    moved.mkdir()
    shutil.copytree(bundle["root"] / "archive", moved / "archive")
    shutil.copyfile(bundle["descriptor_path"], moved / "descriptor.json")
    shutil.copyfile(bundle["manifest"], moved / "certification.json")
    bundle.update(
        root=moved,
        descriptor_path=moved / "descriptor.json",
        manifest=moved / "certification.json",
    )
    with resolve(resolver, bundle) as result:
        assert (
            result.logical_artifact_id == bundle["descriptor"]["artifact"]["logical_id"]
        )
        assert result.path.read_bytes() == bundle["body"]
    assert not (moved / "original").exists()


@pytest.mark.parametrize("failure", ["missing", "corrupt", "truncated"])
def test_bad_authority_never_falls_back_to_intact_original(
    resolver: Any, bundle: dict[str, Any], failure: str
) -> None:
    archive = bundle["archive"]
    archive.chmod(0o600)
    if failure == "missing":
        archive.unlink()
    elif failure == "corrupt":
        archive.write_bytes(b"not a valid archive")
    else:
        archive.write_bytes(archive.read_bytes()[:-4])
    with pytest.raises(resolver.ResolutionError):
        with resolve(resolver, bundle):
            pytest.fail("invalid authority admitted")
    assert bundle["source"].read_bytes() == bundle["body"]
    assert not list(bundle["temporary"].iterdir())


@pytest.mark.parametrize(
    "mutation",
    [
        "identity",
        "schema",
        "bytes",
        "rows",
        "no-authority",
        "duplicate-id",
        "traversal",
        "absolute",
        "wrong-method",
        "archive-pin",
        "unknown-field",
    ],
)
def test_invalid_descriptor_is_rejected(
    resolver: Any, bundle: dict[str, Any], mutation: str
) -> None:
    descriptor = bundle["descriptor"]
    artifact = descriptor["artifact"]
    rep = descriptor["representations"][0]
    if mutation == "identity":
        artifact["logical_id"] = "0" * 64
    elif mutation == "schema":
        artifact["schema_version"] = "unknown-v2"
    elif mutation in ("bytes", "rows"):
        artifact[mutation] += 1
    elif mutation == "no-authority":
        descriptor["authoritative_representation"] = "absent"
    elif mutation == "duplicate-id":
        descriptor["representations"].append(copy.deepcopy(rep))
    elif mutation == "traversal":
        rep["storage_reference"] = "../archive/archive-manifest.json"
    elif mutation == "absolute":
        rep["storage_reference"] = str(bundle["archive_manifest"])
    elif mutation == "wrong-method":
        rep["restore_method"] = "guess-v1"
    elif mutation == "archive-pin":
        rep["archive_manifest_sha256"] = "0" * 64
    else:
        descriptor["unknown_field"] = True
    repin(bundle)
    with pytest.raises(resolver.ResolutionError):
        with resolve(resolver, bundle):
            pytest.fail("invalid descriptor admitted")
    assert not list(bundle["temporary"].iterdir())


def test_changed_descriptor_and_historical_manifest_fail_pinned_checks(
    resolver: Any, bundle: dict[str, Any]
) -> None:
    bundle["descriptor_path"].write_bytes(bundle["descriptor_path"].read_bytes() + b" ")
    with pytest.raises(resolver.ResolutionError, match="integrity"):
        with resolve(resolver, bundle):
            pytest.fail("changed descriptor admitted")
    repin(bundle)
    bundle["manifest"].write_bytes(bundle["manifest"].read_bytes() + b" ")
    with pytest.raises(resolver.ResolutionError, match="integrity"):
        with resolve(resolver, bundle):
            pytest.fail("changed historical manifest admitted")


@pytest.mark.parametrize("mutation", ["self-checksum", "path", "schema", "available"])
def test_historical_compatibility_adapter_rejects_wrong_binding(
    resolver: Any, bundle: dict[str, Any], mutation: str
) -> None:
    manifest = json.loads(bundle["manifest"].read_bytes())
    if mutation == "self-checksum":
        manifest["certification_manifest_checksum"] = "0" * 64
    else:
        if mutation == "path":
            manifest["artifacts"][0]["path"] = "other.jsonl"
        elif mutation == "schema":
            manifest["certification_version"] = "other-v1"
        else:
            manifest["decision_stream"]["artifact_available"] = False
        manifest.pop("certification_manifest_checksum")
        manifest["certification_manifest_checksum"] = hashlib.sha256(
            resolver.archive_helper.encoded(manifest)
        ).hexdigest()
    bundle["manifest_sha"] = write_json(bundle["manifest"], manifest)
    with pytest.raises(resolver.ResolutionError, match="historical"):
        with resolve(resolver, bundle):
            pytest.fail("wrong historical binding admitted")


@pytest.mark.parametrize("target", ["reference", "gzip"])
def test_symlink_representation_is_rejected(
    resolver: Any, bundle: dict[str, Any], tmp_path: Path, target: str
) -> None:
    path = bundle["archive_manifest"] if target == "reference" else bundle["archive"]
    external = tmp_path / "external"
    shutil.copyfile(path, external)
    path.unlink()
    path.symlink_to(external)
    with pytest.raises(resolver.ResolutionError, match="symlink"):
        with resolve(resolver, bundle):
            pytest.fail("symlink authority admitted")


def test_failed_restore_removes_only_its_own_partial_output(
    resolver: Any, bundle: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = bundle["temporary"] / "keep.txt"
    sentinel.write_bytes(b"untouched")

    def fail(_manifest: Path, output: Path, **_kwargs: Any) -> Any:
        output.write_bytes(b"partial")
        raise OSError("injected interrupted restore")

    monkeypatch.setattr(resolver.archive_helper, "restore_archive", fail)
    with pytest.raises(resolver.ResolutionError, match="interrupted"):
        with resolve(resolver, bundle):
            pytest.fail("partial artifact admitted")
    assert list(bundle["temporary"].iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"untouched"
    assert bundle["source"].read_bytes() == bundle["body"]


def test_caller_failure_cleans_temporary_path_without_reclassifying_error(
    resolver: Any, bundle: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match="caller failure") as caught:
        with resolve(resolver, bundle) as result:
            assert result.path.exists()
            raise ValueError("caller failure")
    assert type(caught.value) is ValueError
    assert not list(bundle["temporary"].iterdir())
    assert bundle["source"].exists()


@pytest.mark.parametrize(
    "mutation", ["original-hash", "original-path", "linked-manifest"]
)
def test_archive_must_bind_the_exact_historical_artifact(
    resolver: Any, bundle: dict[str, Any], mutation: str
) -> None:
    archived = json.loads(bundle["archive_manifest"].read_bytes())
    if mutation == "original-hash":
        archived["original"]["sha256"] = "0" * 64
    elif mutation == "original-path":
        archived["original"]["path"] = "/different/decisions/other.jsonl"
    else:
        archived["linked_validation_manifest"]["manifest_id"] = "0" * 64
    bundle["archive_manifest"].chmod(0o600)
    changed_sha = write_json(bundle["archive_manifest"], archived)
    bundle["descriptor"]["representations"][0]["archive_manifest_sha256"] = changed_sha
    repin(bundle)
    with pytest.raises(resolver.ResolutionError, match="archive"):
        with resolve(resolver, bundle):
            pytest.fail("different archived artifact admitted")
    assert not list(bundle["temporary"].iterdir())


@pytest.mark.parametrize("mutation", ["missing", "same-size-corruption"])
def test_original_authority_never_falls_back_to_valid_archive(
    resolver: Any, bundle: dict[str, Any], mutation: str
) -> None:
    bundle["descriptor"]["authoritative_representation"] = "original-v1"
    repin(bundle)
    if mutation == "missing":
        bundle["source"].unlink()
    else:
        bundle["source"].write_bytes(
            bundle["body"].replace(b"fixture-0", b"fixture-X", 1)
        )
    with pytest.raises(resolver.ResolutionError):
        with resolve(resolver, bundle):
            pytest.fail("invalid original admitted")
    assert bundle["archive"].exists()
    assert not list(bundle["temporary"].iterdir())


def test_duplicate_descriptor_property_cannot_override_authority(
    resolver: Any, bundle: dict[str, Any]
) -> None:
    body = bundle["descriptor_path"].read_bytes().rstrip()[:-1]
    body += b',"authoritative_representation":"original-v1"}'
    bundle["descriptor_path"].write_bytes(body)
    bundle["descriptor_sha"] = hashlib.sha256(body).hexdigest()
    with pytest.raises(resolver.ResolutionError, match="duplicate"):
        with resolve(resolver, bundle):
            pytest.fail("ambiguous authority admitted")


def test_recovered_audit_rows_do_not_become_calculation_eligible(
    resolver: Any, bundle: dict[str, Any]
) -> None:
    # A byte-integrity proof does not construct CertifiedMetricPartition or certify
    # an audit overlay. Even a row whose historical state says certified is not a
    # typed calculator admission proof; all five states retain the same rejection.
    with resolve(resolver, bundle) as resolved:
        recovered = [
            json.loads(line) for line in resolved.path.read_bytes().splitlines()
        ]
    assert recovered == bundle["rows"]
    for rows in (bundle["rows"], recovered):
        for row in rows:
            with pytest.raises(CertificationError, match="certify evidence first"):
                require_certified_partition(
                    row,
                    metric_id="research_activity_score",
                    threshold_version="metric-validation-thresholds-v1",
                )
    assert {row["state"] for row in recovered} == {
        "certified",
        "needs_review",
        "withheld",
        "conflicted",
        "insufficient_evidence",
    }
