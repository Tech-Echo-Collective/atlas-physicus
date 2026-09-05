"""Tiny historical affiliation fixtures, never retained scientific evidence."""

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.contracts import require_certified_partition
from physics_atlas_api.storage import affiliation_archive as codec
from physics_atlas_api.storage import historical_authority as resolver
from physics_atlas_api.storage import historical_decision_archive

SCHEMAS = (
    ("affiliation-shares", "physics-paired-trial-certification-manifest-v1"),
    ("affiliation-shares", "physics-paired-trial-certification-manifest-v2"),
    (
        "paper-time-affiliation-shares",
        "cond-mat-validation-v1-historical-replay-bundle-v2",
    ),
)


def write_json(path: Path, document: Any) -> str:
    body = codec.encoded(document) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.chmod(0o600)  # Only mutable test-fixture metadata.
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def fraction(value: str) -> dict[str, str]:
    return {"exact": value}


def build_fixture(tmp_path: Path, role: str, schema: str) -> dict[str, Any]:
    root = tmp_path.resolve() / "storage"
    root.mkdir()
    rows = []
    for index, (paper, weight, state) in enumerate(
        (
            ("p1", "1/2", "certified"),
            ("p1", "1/2", "needs_review"),
            ("p2", "1/2", "conflicted"),
            ("p2", "1/2", "insufficient_evidence"),
            ("p3", "1", "withheld"),
        )
    ):
        row = {
            "canonical_paper_id": paper,
            "institution_id": "ror:fixture" if index == 0 else None,
            "paper_time_affiliation_state": state,
            "institution_state": state,
            "eligible_for_metrics": False,
            "reasons": [] if index == 0 else ["unchanged reason φ"],
            "attribution_policy_version": "unchanged-fixture-v1",
            "source_provenance": {"checksum": "a" * 64, "source": "fixture"},
            "future_field": {"missing_is_absent": True, "null": None, "zero": 0},
        }
        if role == "paper-time-affiliation-shares":
            row.update(
                attribution_weight=fraction(weight),
                author_weight=fraction(weight),
                affiliation_weight=fraction("1"),
                candidate_id=paper,
                canonical_paper_id=None if paper == "p3" else paper,
                resolution_status="withheld-unresolved-affiliation",
                eligible_for_public_metrics=False,
            )
        else:
            row["mass"] = fraction(weight)
        rows.append(row)
    body = b"\r\n".join(json.dumps(row, ensure_ascii=False).encode() for row in rows)
    content_sha = hashlib.sha256(body).hexdigest()
    artifact = {
        "type": role,
        "schema_version": schema,
        "sha256": content_sha,
        "bytes": len(body),
        "rows": len(rows),
        "logical_id": resolver.logical_artifact_id(role, schema, content_sha),
    }
    entry = {
        "role": role,
        "path": (
            "artifacts/affiliation-shares/"
            if role == "affiliation-shares"
            else "relationships/affiliations/"
        )
        + content_sha
        + ".jsonl",
        "checksum": content_sha,
        "byte_count": len(body),
        "row_count": len(rows),
    }
    checksum_key, version_key = (
        ("manifest_checksum", "manifest_version")
        if role == "affiliation-shares"
        else ("bundle_manifest_checksum", "bundle_version")
    )
    if role == "affiliation-shares":
        entry["media_type"] = "application/x-ndjson"
    manifests, originals, bindings, hashes = [], [], [], []
    for name in ("historical", "corrected"):
        bundle_root = root / name
        source = bundle_root / entry["path"]
        source.parent.mkdir(parents=True)
        source.write_bytes(body)
        document = {
            version_key: schema,
            "dataset_version": name + "-fixture-only",
            "artifacts": [entry],
        }
        document[checksum_key] = hashlib.sha256(codec.encoded(document)).hexdigest()
        manifest = bundle_root / "manifests/source.json"
        digest = write_json(manifest, document)
        manifests.append(manifest)
        originals.append(source)
        hashes.append(digest)
        bindings.append(resolver.affiliation_binding_record(manifest, digest, artifact))
    created = codec.create_archive(
        originals[0],
        root / "archive",
        expected_source_sha=content_sha,
        expected_bytes=len(body),
        expected_rows=len(rows),
        role=role,
        schema_version=schema,
        historical_bindings=bindings,
    )
    descriptor = {
        "version": resolver.DESCRIPTOR_VERSION,
        "artifact": artifact,
        "authoritative_representation": "archive-v1",
        "representations": [
            {
                "id": "archive-v1",
                "type": "archive",
                "storage_reference": "archive/archive-manifest.json",
                "archive_manifest_sha256": created["manifest_sha256"],
                "restore_method": codec.VERSION,
            },
            {
                "id": "original-v1",
                "type": "original",
                "storage_reference": originals[0].relative_to(root).as_posix(),
                "restore_method": resolver.ORIGINAL_METHOD,
            },
        ],
    }
    descriptor_path = root / "descriptor.json"
    descriptor_sha = write_json(descriptor_path, descriptor)
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    return dict(
        root=root,
        originals=originals,
        manifests=manifests,
        manifest_hashes=hashes,
        body=body,
        rows=rows,
        descriptor=descriptor,
        descriptor_path=descriptor_path,
        descriptor_sha=descriptor_sha,
        archive_manifest=Path(created["manifest_path"]),
        archive=root / "archive" / (content_sha + ".jsonl.gz"),
        temporary=temporary,
        bindings=bindings,
        checksum_key=checksum_key,
    )


@pytest.fixture(params=SCHEMAS, ids=["paired-v1", "paired-v2", "replay-v2"])
def bundle(request: pytest.FixtureRequest, tmp_path: Path) -> dict[str, Any]:
    return build_fixture(tmp_path, *request.param)


def resolve(bundle: dict[str, Any], index: int = 0, **kwargs: Any) -> Any:
    return resolver.resolve_historical_artifact(
        bundle["descriptor_path"],
        expected_descriptor_sha256=bundle["descriptor_sha"],
        storage_root=bundle["root"],
        certification_manifest=bundle["manifests"][index],
        expected_certification_manifest_sha256=bundle["manifest_hashes"][index],
        temp_parent=bundle["temporary"],
        **kwargs,
    )


def repin(bundle: dict[str, Any]) -> None:
    bundle["descriptor_sha"] = write_json(
        bundle["descriptor_path"], bundle["descriptor"]
    )


def repin_archive(bundle: dict[str, Any], document: Any) -> None:
    changed = write_json(bundle["archive_manifest"], document)
    bundle["descriptor"]["representations"][0]["archive_manifest_sha256"] = changed
    repin(bundle)


def test_inline_and_archive_same_exact_rows_and_scientific_summary(bundle):
    historical = [path.read_bytes() for path in bundle["manifests"]]
    with resolve(bundle) as archived:
        assert archived.path.read_bytes() == bundle["body"]
        summary = archived.scientific_summary
        assert summary["unit_mass_papers"] == 3
        assert summary["non_unit_mass_papers"] == 0
        assert summary["total_exact_mass"] == "3"
        assert summary["author_affiliation_product_mismatches"] == 0
        assert summary["states"]["eligible_for_metrics:false"] == 5
    bundle["descriptor"]["authoritative_representation"] = "original-v1"
    repin(bundle)
    with resolve(bundle) as inline:
        assert inline.path.read_bytes() == bundle["body"]
        assert inline.scientific_summary == summary
        assert inline.logical_artifact_id == archived.logical_artifact_id
    assert historical == [path.read_bytes() for path in bundle["manifests"]]
    assert not archived.path.exists() and not inline.path.exists()
    assert not list(bundle["temporary"].iterdir())


def test_original_absent_twins_keep_both_bindings_without_probing_originals(
    bundle, monkeypatch
):
    original_paths = set(bundle["originals"])
    for path in original_paths:
        path.unlink()  # Disposable tiny fixtures only.
    original_open, original_stat = Path.open, Path.stat

    def guarded_open(path, *args, **kwargs):
        assert path not in original_paths, "archive resolver must not open originals"
        return original_open(path, *args, **kwargs)

    def guarded_stat(path, *args, **kwargs):
        assert path not in original_paths, "archive resolver must not stat originals"
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(Path, "stat", guarded_stat)
    outcomes = []
    for index in range(2):
        with resolve(bundle, index) as result:
            assert result.path.read_bytes() == bundle["body"]
            outcomes.append((result.logical_artifact_id, result.scientific_summary))
    assert outcomes[0] == outcomes[1]
    assert bundle["manifest_hashes"][0] != bundle["manifest_hashes"][1]
    assert not list(bundle["temporary"].iterdir())


def test_moved_archive_kit_preserves_recorded_historical_path(bundle, tmp_path):
    moved = tmp_path / "isolated-kit"
    moved.mkdir()
    old = bundle["manifests"][1]
    shutil.copytree(bundle["root"] / "archive", moved / "archive")
    shutil.copyfile(bundle["descriptor_path"], moved / "descriptor.json")
    shutil.copyfile(old, moved / "historical-manifest.json")
    bundle.update(
        root=moved,
        descriptor_path=moved / "descriptor.json",
        manifests=[moved / "historical-manifest.json"],
        manifest_hashes=[bundle["manifest_hashes"][1]],
    )
    with resolve(bundle, historical_recorded_path=old) as recovered:
        assert recovered.path.read_bytes() == bundle["body"]
    with pytest.raises(resolver.ResolutionError, match="historical affiliation"):
        with resolve(bundle):
            pytest.fail("moved path must not guess its historical alias")


@pytest.mark.parametrize("damage", ["missing", "corrupt", "truncated"])
def test_archive_damage_never_falls_back_to_intact_original(bundle, damage):
    path = bundle["archive"]
    path.chmod(0o600)
    if damage == "missing":
        path.unlink()
    elif damage == "corrupt":
        path.write_bytes(b"x" * path.stat().st_size)
    else:
        path.write_bytes(path.read_bytes()[:-4])
    with pytest.raises(resolver.ResolutionError):
        with resolve(bundle):
            pytest.fail("invalid archive admitted")
    assert all(path.read_bytes() == bundle["body"] for path in bundle["originals"])
    assert not list(bundle["temporary"].iterdir())


@pytest.mark.parametrize(
    "damage", ["identity", "schema", "authority", "duplicate", "reference", "pin"]
)
def test_invalid_descriptor_fails_closed(bundle, damage):
    descriptor = bundle["descriptor"]
    if damage == "identity":
        descriptor["artifact"]["logical_id"] = "0" * 64
    elif damage == "schema":
        descriptor["artifact"]["schema_version"] = "unreviewed-schema-v9"
    elif damage == "authority":
        descriptor["authoritative_representation"] = "no-such-authority"
    elif damage == "duplicate":
        descriptor["representations"].append(
            copy.deepcopy(descriptor["representations"][0])
        )
    elif damage == "reference":
        descriptor["representations"][0]["storage_reference"] = "../archive.json"
    else:
        descriptor["representations"][0]["archive_manifest_sha256"] = "0" * 64
    repin(bundle)
    with pytest.raises(resolver.ResolutionError):
        with resolve(bundle):
            pytest.fail("invalid descriptor admitted")
    assert not list(bundle["temporary"].iterdir())


@pytest.mark.parametrize("damage", ["duplicate-alias", "wrong-alias", "wrong-summary"])
def test_rehashed_archive_cannot_change_alias_or_scientific_summary(bundle, damage):
    document = json.loads(bundle["archive_manifest"].read_bytes())
    if damage == "duplicate-alias":
        document["historical_bindings"].append(
            copy.deepcopy(document["historical_bindings"][0])
        )
    elif damage == "wrong-alias":
        document["historical_bindings"][0]["manifest_id"] = "0" * 64
    else:
        document["scientific_summary"]["total_exact_mass"] = "0"
    repin_archive(bundle, document)
    with pytest.raises(resolver.ResolutionError):
        with resolve(bundle):
            pytest.fail("altered archive evidence admitted")
    assert not list(bundle["temporary"].iterdir())


@pytest.mark.parametrize("damage", ["self-hash", "duplicate-role", "path"])
def test_historical_manifest_requires_exact_role_path_and_self_hash(bundle, damage):
    path = bundle["manifests"][0]
    document = json.loads(path.read_bytes())
    key = bundle["checksum_key"]
    if damage == "self-hash":
        document[key] = "0" * 64
    else:
        if damage == "duplicate-role":
            document["artifacts"].append(copy.deepcopy(document["artifacts"][0]))
        else:
            document["artifacts"][0]["path"] = "other/path.jsonl"
        document.pop(key)
        document[key] = hashlib.sha256(codec.encoded(document)).hexdigest()
    bundle["manifest_hashes"][0] = write_json(path, document)
    with pytest.raises(resolver.ResolutionError):
        with resolve(bundle):
            pytest.fail("invalid historical reference admitted")


def test_original_authority_does_not_fallback_when_original_is_absent(bundle):
    bundle["descriptor"]["authoritative_representation"] = "original-v1"
    repin(bundle)
    bundle["originals"][0].unlink()
    with pytest.raises(resolver.ResolutionError):
        with resolve(bundle):
            pytest.fail("must not silently select an alternative archive")
    assert bundle["archive"].exists()


def test_recovered_affiliation_rows_are_not_a_certified_metric_partition(bundle):
    with resolve(bundle) as recovered:
        rows = [json.loads(line) for line in recovered.path.read_bytes().splitlines()]
    assert rows == bundle["rows"]
    for row in rows:
        assert row["future_field"]["null"] is None
        assert row["future_field"]["zero"] == 0
        assert "absent" not in row["future_field"]
        with pytest.raises(CertificationError, match="certify evidence first"):
            require_certified_partition(
                row,
                metric_id="research_activity_score",
                threshold_version="metric-validation-thresholds-v1",
            )


def test_existing_decision_codec_selection_is_unchanged():
    decision = {
        "type": resolver.ARTIFACT_TYPE,
        "schema_version": resolver.ARTIFACT_SCHEMA_VERSION,
    }
    assert resolver._codec(decision) is historical_decision_archive
    for role, schema in SCHEMAS:
        assert resolver._codec({"type": role, "schema_version": schema}) is codec
