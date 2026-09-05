"""Small affiliation-only fixtures; no acquisition, replay, DB or corpus reads."""

import gzip
import hashlib
import importlib.util
import io
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.storage import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactRef,
    FilesystemArtifactStore,
    StorageTier,
)
from physics_atlas_api.storage.validation_retention import (
    ValidationRetentionError,
    ValidationRetentionInventory,
    require_validation_retention_budget,
)

SPEC = importlib.util.spec_from_file_location(
    "affiliation_pilot",
    Path(__file__).resolve().parents[1] / "tools/pilot_affiliation_compaction.py",
)
assert SPEC is not None and SPEC.loader is not None
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


def hashed(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_bytes(pilot.encoded(value) + b"\n")
    return hashed(path)


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setenv("PHYSICS_ATLAS_ENVIRONMENT", "test")
    root = tmp_path / "source"
    root.mkdir()
    # Deliberately interleave two complete paper groups, including stored zero,
    # null and absent values; no source scientific decision may be recalculated.
    rows = [
        {
            "canonical_paper_id": paper,
            "share_id": f"share-{index}",
            "mass": {"exact": mass},
            "paper_time_affiliation_state": affiliation,
            "institution_state": institution,
            "canonical_institution_id": "ror-fixture" if index == 0 else None,
            "provenance": {"source": "retained-fixture", "version": "fixture-v1"},
            "source_snapshot_id": f"fixture-snapshot-{index}",
            "eligible_for_metrics": False,
            "same_source_ror_conflict": institution == "conflicted",
            "nullable_value": None if index % 2 else 0,
            **({"optional_value": 0} if index == 0 else {}),
        }
        for index, (paper, mass, affiliation, institution) in enumerate(
            [
                ("paper-1", "1/3", "certified", "certified"),
                ("paper-2", "1/2", "insufficient_evidence", "needs_review"),
                ("paper-1", "2/3", "certified", "conflicted"),
                ("paper-2", "1/2", "withheld", "insufficient_evidence"),
            ]
        )
    ]
    body = b"".join(pilot.encoded(row) + b"\n" for row in rows)
    data = root / "affiliations.jsonl"
    data.write_bytes(body)
    manifest = root / "manifests/source.json"
    manifest.parent.mkdir()
    sha = write_json(
        manifest,
        {
            "artifacts": [
                {
                    "role": "paper-time-affiliation-shares",
                    "path": "affiliations.jsonl",
                    "checksum": hashed(data),
                    "byte_count": len(body),
                    "row_count": len(rows),
                }
            ]
        },
    )
    return data, manifest, sha, body


def admission(output):
    inventory = ValidationRetentionInventory(
        scope_id="fixture-validation-v1",
        measured_at="2026-09-05T00:00:00+00:00",
        managed_root=str(output.resolve()),
        files=(),
        metadata_bytes=0,
        total_bytes=0,
        complete=True,
    )
    reservation = require_validation_retention_budget(
        inventory,
        expected_inventory_sha256=inventory.sha256,
        sample_id="fixture-sample",
        expected_sample_id="fixture-sample",
        sample_manifest_sha256="a" * 64,
        expected_sample_manifest_sha256="a" * 64,
        paper_count=2,
        pipeline_version="fixture-pilot-v1",
        proof_manifest_sha256="b" * 64,
        reserved_new_bytes=48 * 1024**2,
    )
    return inventory, reservation


def create(source, output, paper_ids=None):
    data, manifest, sha, _ = source
    inventory, reservation = admission(output)
    actual = Path(reservation.output_reference)
    value = pilot.create_pilot(
        data,
        manifest,
        sha,
        actual,
        paper_ids,
        inventory=inventory,
        reservation=reservation,
    )
    path = actual / "manifest.json"
    return value, path, hashed(path)


def reference(value):
    return ArtifactRef(**{**value["archive"], "tier": StorageTier.COLD})


def replacement_archive(tmp_path, output, value, payload):
    store = FilesystemArtifactStore(output / "store")
    new = store.put_bytes(
        payload,
        tier=StorageTier.COLD,
        media_type="application/x-ndjson",
        content_encoding="gzip",
    )
    changed = {**value, "archive": asdict(new)}
    path = tmp_path / "changed-manifest.json"
    return path, write_json(path, changed)


def test_exact_deterministic_complete_paper_selection_and_states(source, tmp_path):
    first, path, sha = create(source, tmp_path / "first", {"paper-1"})
    second, _, _ = create(source, tmp_path / "second", {"paper-1"})
    assert first["archive"] == second["archive"]
    assert first["pilot_id"] == second["pilot_id"]
    assert first["summary"] == second["summary"]
    assert [entry["row"] for entry in first["selection"]] == [1, 3]
    assert first["summary"]["papers"] == 1
    assert first["summary"]["total_exact_mass"] == "1"
    assert first["summary"]["non_unit_mass_papers"] == 0
    assert first["summary"]["states"]['institution_state:"conflicted"'] == 1
    assert first["summary"]["states"]["eligible_for_metrics:false"] == 2
    output = tmp_path / "restored.jsonl"
    result = pilot.restore_pilot(path, sha, path.parent / "store", output)
    expected = b"".join(source[3].splitlines(keepends=True)[::2])
    assert output.read_bytes() == expected
    assert result["summary"] == pilot.summarize(expected)
    assert source[0].read_bytes() == source[3]
    assert first["original_retained"] is True
    assert first["archive_authority_promoted"] is False
    assert first["metric_observations_created"] == 0


def test_original_absent_restore_never_reads_scientific_source(
    source, tmp_path, monkeypatch
):
    value, path, sha = create(source, tmp_path / "pilot")
    original_open = Path.open
    blocked_root = source[0].parent

    # Source tree is inaccessible, and even the selected expanded pilot copy
    # is denied: only manifest and archive may participate in recovery.
    def guarded(file, *args, **kwargs):
        assert not file.is_relative_to(blocked_root)
        assert file.name != "selected-original.jsonl"
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    output = tmp_path / "restore.jsonl"
    result = pilot.restore_pilot(path, sha, path.parent / "store", output)
    assert output.read_bytes() == source[3]
    assert result["summary"] == value["summary"]
    assert result["exact_restore"] is True


@pytest.mark.parametrize("damage", ["missing", "checksum"])
def test_missing_or_changed_archive_fails_closed(source, tmp_path, damage):
    value, path, sha = create(source, tmp_path / "pilot")
    archive = FilesystemArtifactStore(path.parent / "store").local_path(
        reference(value)
    )
    if damage == "missing":
        archive.unlink()
        error = ArtifactNotFoundError
    else:
        archive.chmod(0o644)
        archive.write_bytes(b"X" * archive.stat().st_size)
        error = ArtifactIntegrityError
    output = tmp_path / "restore.jsonl"
    with pytest.raises(error):
        pilot.restore_pilot(path, sha, path.parent / "store", output)
    assert not output.exists()
    assert source[0].read_bytes() == source[3]


def test_truncated_gzip_with_valid_outer_checksum_is_rejected(source, tmp_path):
    value, path, _ = create(source, tmp_path / "pilot")
    archive = FilesystemArtifactStore(path.parent / "store").local_path(
        reference(value)
    )
    changed, sha = replacement_archive(
        tmp_path, path.parent, value, archive.read_bytes()[:-5]
    )
    output = tmp_path / "restore.jsonl"
    with pytest.raises(ValueError, match="corrupt or truncated"):
        pilot.restore_pilot(changed, sha, path.parent / "store", output)
    assert not output.exists()


def test_corrupt_deflate_with_valid_outer_checksum_is_rejected(source, tmp_path):
    value, path, _ = create(source, tmp_path / "pilot")
    archive = FilesystemArtifactStore(path.parent / "store").local_path(
        reference(value)
    )
    body = bytearray(archive.read_bytes())
    # Header has no filename/comment; invalid DEFLATE block type reaches zlib.
    body[10] = (body[10] & ~6) | 6
    changed, sha = replacement_archive(tmp_path, path.parent, value, bytes(body))
    output = tmp_path / "restore.jsonl"
    with pytest.raises(ValueError, match="corrupt or truncated"):
        pilot.restore_pilot(changed, sha, path.parent / "store", output)
    assert not output.exists()


def test_rehashed_invalid_pilot_identity_is_rejected(source, tmp_path):
    value, path, _ = create(source, tmp_path / "pilot")
    changed = tmp_path / "changed.json"
    sha = write_json(changed, {**value, "pilot_id": "0" * 64})
    with pytest.raises(ValueError, match="identity mismatch"):
        pilot.restore_pilot(changed, sha, path.parent / "store", tmp_path / "restore")
    assert not (tmp_path / "restore").exists()


def test_bounded_decompression_refuses_false_expanded_size(source, tmp_path):
    value, path, _ = create(source, tmp_path / "pilot")
    changed, _ = replacement_archive(
        tmp_path, path.parent, value, gzip.compress(source[3] + b"\n", mtime=0)
    )
    output = tmp_path / "restore.jsonl"
    with pytest.raises(ValueError, match="bytes do not match"):
        pilot.restore_pilot(changed, hashed(changed), path.parent / "store", output)
    assert not output.exists()


@pytest.mark.parametrize(
    "change",
    [
        {"version": "unknown"},
        {"original_bytes": 0},
        {"original_bytes": True},
        {"original_bytes": 16 * 1024**2 + 1},
    ],
)
def test_invalid_or_oversize_descriptor(source, tmp_path, change):
    value, path, _ = create(source, tmp_path / "pilot")
    changed = tmp_path / "changed.json"
    sha = write_json(changed, {**value, **change})
    with pytest.raises(ValueError, match="invalid or unbounded"):
        pilot.restore_pilot(changed, sha, path.parent / "store", tmp_path / "restore")
    assert not (tmp_path / "restore").exists()


def test_bad_manifest_pin_and_uri_fail_before_restore(source, tmp_path):
    value, path, _ = create(source, tmp_path / "pilot")
    with pytest.raises(ValueError, match="checksum mismatch"):
        pilot.restore_pilot(path, "0" * 64, path.parent / "store", tmp_path / "restore")
    value["archive"]["uri"] = "file:///outside"
    changed = tmp_path / "changed.json"
    sha = write_json(changed, value)
    with pytest.raises(ValueError, match="canonical content-addressed"):
        pilot.restore_pilot(changed, sha, path.parent / "store", tmp_path / "restore")
    assert not (tmp_path / "restore").exists()


def test_summary_tampering_rejected_and_missing_zero_remain_distinct(source, tmp_path):
    value, path, _ = create(source, tmp_path / "pilot")
    value["summary"]["institution_provenance_sha256"] = "0" * 64
    changed = tmp_path / "changed.json"
    sha = write_json(changed, value)
    with pytest.raises(ValueError, match="scientific summary differs"):
        pilot.restore_pilot(changed, sha, path.parent / "store", tmp_path / "restore")
    original = pilot.summarize(source[3])
    changed_rows = [json.loads(line) for line in source[3].splitlines()]
    changed_rows[1]["nullable_value"] = 0
    altered = b"".join(pilot.encoded(row) + b"\n" for row in changed_rows)
    assert (
        pilot.summarize(altered)["complete_semantic_sha256"]
        != original["complete_semantic_sha256"]
    )


def test_incomplete_group_refused_before_output(source, tmp_path):
    data, manifest, _, _ = source
    lines = data.read_bytes().splitlines(keepends=True)
    data.write_bytes(lines[0] + lines[1] + lines[3])
    value = json.loads(manifest.read_bytes())
    value["artifacts"][0].update(
        checksum=hashed(data), byte_count=data.stat().st_size, row_count=3
    )
    sha = write_json(manifest, value)
    with pytest.raises(ValueError, match="do not conserve one"):
        create((data, manifest, sha, source[3]), tmp_path / "pilot")
    assert not (tmp_path / "pilot").exists()


def test_unknown_empty_or_excessive_selection_refused(source, tmp_path):
    for papers in (set(), {"absent"}, {f"paper-{index}" for index in range(2501)}):
        with pytest.raises((ValueError, CertificationError)):
            create(source, tmp_path / "pilot", papers)
        assert not (tmp_path / "pilot").exists()


def test_source_size_and_selected_size_caps(source, tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "MAX_SOURCE_BYTES", 1)
    with pytest.raises(ValueError, match="source limit exceeded"):
        create(source, tmp_path / "pilot")
    monkeypatch.setattr(pilot, "MAX_SOURCE_BYTES", 1200 * 1024**2)
    monkeypatch.setattr(pilot, "MAX_BYTES", 1500)
    with pytest.raises(ValueError, match="selected affiliation stream exceeds"):
        create(source, tmp_path / "pilot")
    assert not (tmp_path / "pilot").exists()


@pytest.mark.parametrize("bound", ["bytes", "rows"])
def test_source_scan_stops_at_pinned_bounds_before_parsing_extra_data(
    source, tmp_path, monkeypatch, bound
):
    data, manifest, manifest_sha, body = source
    expected_rows = len(body.splitlines())
    if bound == "rows":
        value = json.loads(manifest.read_bytes())
        expected_rows -= 1
        value["artifacts"][0]["row_count"] = expected_rows
        manifest_sha = write_json(manifest, value)
    opened = Path.open
    reads = []

    class GrowingSource(io.BytesIO):
        def readline(self, size=-1):
            reads.append(1)
            if len(reads) > expected_rows + 1:
                pytest.fail("source scan continued past its pinned bounds")
            return super().readline(size)

    def growing_open(path, *args, **kwargs):
        if path == data:
            # Initial filesystem metadata stays pinned. Model data appended after
            # that stat, and prove the extra malformed row is never parsed.
            return GrowingSource(body + b"not-json-must-not-be-parsed\n")
        return opened(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", growing_open)
    with pytest.raises(ValueError, match="exceeds pinned byte/row bounds"):
        create((data, manifest, manifest_sha, body), tmp_path / "pilot")
    assert len(reads) == expected_rows + 1
    assert not (tmp_path / "pilot").exists()


def test_production_refuses_before_any_io(source, tmp_path, monkeypatch):
    inventory, reservation = admission(tmp_path / "pilot")
    monkeypatch.setenv("PHYSICS_ATLAS_ENVIRONMENT", "production")

    def no_io(*args, **kwargs):
        pytest.fail("production must refuse before scientific/filesystem IO")

    monkeypatch.setattr(pilot, "select_source", no_io)
    monkeypatch.setattr(pilot, "read_pinned", no_io)
    with pytest.raises(CertificationError):
        pilot.create_pilot(
            *source[:3],
            Path(reservation.output_reference),
            inventory=inventory,
            reservation=reservation,
        )
    with pytest.raises(CertificationError):
        pilot.restore_pilot(
            tmp_path / "absent", "x", tmp_path / "store", tmp_path / "out"
        )
    assert not (tmp_path / "pilot").exists()
    assert not (tmp_path / "store").exists()


def test_existing_outputs_never_overwritten(source, tmp_path):
    _, path, sha = create(source, tmp_path / "pilot")
    with pytest.raises(ValidationRetentionError):
        create(source, tmp_path / "pilot")
    out = tmp_path / "existing"
    out.write_bytes(b"preserve existing evidence")
    with pytest.raises(FileExistsError):
        pilot.restore_pilot(path, sha, path.parent / "store", out)
    assert out.read_bytes() == b"preserve existing evidence"
    assert source[0].read_bytes() == source[3]


def test_reservation_output_identity_and_bytes_enforced(source, tmp_path):
    from dataclasses import replace

    inventory, reservation = admission(tmp_path / "pilot")
    with pytest.raises(ValueError, match="immutable retention reservation"):
        pilot.create_pilot(
            *source[:3],
            tmp_path / "outside",
            inventory=inventory,
            reservation=reservation,
        )
    # A self-consistent small reservation passes admission but cannot publish
    # body + archive + metadata beyond its declared cumulative allowance.
    small = replace(reservation, reserved_new_bytes=1, projected_bytes=1)
    with pytest.raises(ValidationRetentionError, match="exceeds its reservation"):
        pilot.create_pilot(
            *source[:3],
            Path(small.output_reference),
            inventory=inventory,
            reservation=small,
        )
    assert not Path(small.output_reference).exists()
    assert source[0].read_bytes() == source[3]


def test_reservation_paper_bound_cannot_be_bypassed(source, tmp_path):
    from dataclasses import replace

    inventory, reservation = admission(tmp_path / "pilot")
    single = replace(reservation, paper_count=1)
    with pytest.raises(ValueError, match="paper"):
        pilot.create_pilot(
            *source[:3],
            Path(single.output_reference),
            inventory=inventory,
            reservation=single,
        )
    assert not Path(single.output_reference).exists()
    assert source[0].read_bytes() == source[3]


def test_historical_null_canonical_candidate_recovers_without_promotion(
    source, tmp_path
):
    data, source_manifest, _, _ = source
    rows = [json.loads(line) for line in source[3].splitlines()]
    for row in rows:
        if row["canonical_paper_id"] == "paper-1":
            row.update(
                canonical_paper_id=None,
                candidate_id="candidate-conflict",
                resolution_status="conflicted",
                eligible_for_metrics=False,
            )
    body = b"".join(pilot.encoded(row) + b"\n" for row in rows)
    data.write_bytes(body)
    manifest = json.loads(source_manifest.read_bytes())
    manifest["artifacts"][0].update(checksum=hashed(data), byte_count=len(body))
    sha = write_json(source_manifest, manifest)
    value, path, pin = create(
        (data, source_manifest, sha, body), tmp_path / "pilot", {"candidate-conflict"}
    )
    assert value["summary"]["papers"] == 1
    assert value["summary"]["total_exact_mass"] == "1"
    assert value["summary"]["states"]['resolution_status:"conflicted"'] == 2
    assert value["summary"]["states"]["eligible_for_metrics:false"] == 2
    restored = tmp_path / "restore.jsonl"
    pilot.restore_pilot(path, pin, path.parent / "store", restored)
    expected = b"".join(body.splitlines(keepends=True)[::2])
    assert restored.read_bytes() == expected
    assert all(
        json.loads(line)["canonical_paper_id"] is None
        for line in restored.read_bytes().splitlines()
    )
    assert data.read_bytes() == body


@pytest.mark.parametrize(
    "row",
    [
        {"canonical_paper_id": None},
        {"canonical_paper_id": None, "candidate_id": ""},
        {"candidate_id": "missing-explicit-null"},
        {"canonical_paper_id": "", "candidate_id": "must-not-replace-empty"},
        {"canonical_paper_id": False, "candidate_id": "must-not-replace-invalid"},
    ],
)
def test_historical_missing_or_invalid_locators_fail_closed(row):
    body = pilot.encoded({**row, "mass": {"exact": "1"}}) + b"\n"
    with pytest.raises(ValueError, match="supported paper locator"):
        pilot.summarize(body, "paper-time-affiliation-shares")


def test_paired_schema_cannot_use_candidate_fallback():
    body = (
        pilot.encoded(
            {
                "canonical_paper_id": None,
                "candidate_id": "candidate",
                "mass": {"exact": "1"},
            }
        )
        + b"\n"
    )
    with pytest.raises(ValueError, match="supported paper locator"):
        pilot.summarize(body, "affiliation-shares")


def test_candidate_and_canonical_same_text_never_silently_merge():
    rows = [
        {"canonical_paper_id": "same", "mass": {"exact": "1/2"}},
        {"canonical_paper_id": None, "candidate_id": "same", "mass": {"exact": "1/2"}},
    ]
    body = b"".join(pilot.encoded(row) + b"\n" for row in rows)
    with pytest.raises(ValueError, match="ambiguous canonical/candidate"):
        pilot.summarize(body, "paper-time-affiliation-shares")
