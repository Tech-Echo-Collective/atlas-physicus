"""Affiliation codec fixtures only; no retained corpus, replay or provider access."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

from physics_atlas_api.storage import affiliation_archive as codec


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def write_json(path: Path, value: object) -> str:
    body = codec.encoded(value) + b"\n"
    path.write_bytes(body)
    return digest(body)


def fraction(exact: str) -> dict[str, object]:
    from fractions import Fraction

    value = Fraction(exact)
    return {
        "exact": exact,
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": float(value),
    }


@pytest.fixture(params=["affiliation-shares", "paper-time-affiliation-shares"])
def source(tmp_path: Path, request: pytest.FixtureRequest) -> dict[str, Any]:
    role = request.param
    rows = []
    for index, (paper, mass, author, affiliation, state) in enumerate(
        [
            ("p1", "1/3", "1/3", "1", "certified"),
            ("p2", "1/2", "1", "1/2", "conflicted"),
            ("p1", "2/3", "2/3", "1", "needs_review"),
            ("p2", "1/2", "1", "1/2", "insufficient_evidence"),
            ("p3", "1", "1", "1", "withheld"),
        ]
    ):
        row = {
            "canonical_paper_id": None
            if role == "paper-time-affiliation-shares" and paper == "p2"
            else paper,
            "candidate_id": paper,
            "share_id": f"share-{index}",
            "paper_time_affiliation_state": state,
            "institution_state": state,
            "canonical_institution_id": "ror-retained" if index == 0 else None,
            "institution_reasons": ["preserved reason φ"],
            "source_snapshot_id": "f" * 64,
            "provenance": {"reference": "original-fixture.json#1"},
            "policy_version": "unchanged-fixture-v1",
            "eligible_for_metrics": False,
            "same_source_ror_conflict": state == "conflicted",
            "unknown_future_field": {"null": None, "zero": 0, "empty": ""},
        }
        if role == "paper-time-affiliation-shares":
            row.update(
                attribution_weight=fraction(mass),
                author_weight=fraction(author),
                affiliation_weight=fraction(affiliation),
            )
        else:
            row["mass"] = fraction(mass)
        rows.append(row)
    # Preserve non-canonical whitespace, Unicode, CRLF and absent terminal newline.
    body = b"\r\n".join(json.dumps(row, ensure_ascii=False).encode() for row in rows)
    sha = digest(body)
    root = tmp_path / "original"
    source_path = root / "affiliations" / (sha + ".jsonl")
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(body)
    manifest = root / "manifests/fixture.json"
    manifest.parent.mkdir()
    manifest.write_bytes(b"retained immutable historical metadata")
    binding = {
        "manifest_sha256": digest(manifest.read_bytes()),
        "manifest_id": "a" * 64,
        "manifest_version": "fixture-affiliation-manifest-v1",
        "historical_manifest_path": str(manifest),
        "original_path": str(source_path),
        "entry": {
            "role": role,
            "path": source_path.relative_to(root).as_posix(),
            "checksum": sha,
            "byte_count": len(body),
            "row_count": len(rows),
        },
    }
    if role == "affiliation-shares":
        binding["entry"]["media_type"] = "application/x-ndjson"
    arguments = {
        "expected_source_sha": sha,
        "expected_bytes": len(body),
        "expected_rows": len(rows),
        "role": role,
        "schema_version": "fixture-affiliation-v1",
        "historical_bindings": [binding],
    }
    return {
        "path": source_path,
        "body": body,
        "rows": rows,
        "role": role,
        "arguments": arguments,
        "manifest": manifest,
    }


def create(source: dict[str, Any], output: Path) -> dict[str, Any]:
    return codec.create_archive(source["path"], output, **source["arguments"])


def restore(created: dict[str, Any], output: Path, role: str) -> dict[str, Any]:
    return codec.restore_archive(
        Path(created["manifest_path"]),
        output,
        expected_manifest_sha=created["manifest_sha256"],
        role=role,
    )


def test_deterministic_archive_exact_scientific_summary_and_original_bytes(
    source: dict[str, Any], tmp_path: Path
) -> None:
    first = create(source, tmp_path / "first")
    second = create(source, tmp_path / "second")
    assert first["archive"] == second["archive"]
    assert first["scientific_summary"] == second["scientific_summary"]
    result = restore(first, tmp_path / "restored", source["role"])
    assert (tmp_path / "restored").read_bytes() == source["body"]
    assert source["path"].read_bytes() == source["body"]
    summary = result["scientific_summary"]
    assert summary["sha256"] == digest(source["body"])
    assert summary["rows"] == 5
    assert summary["papers"] == 3
    assert summary["total_exact_mass"] == "3"
    assert summary["unit_mass_papers"] == 3
    assert summary["non_unit_mass_papers"] == 0
    assert summary["author_affiliation_product_mismatches"] == 0
    assert summary["author_affiliation_product_rows"] == (
        5 if source["role"] == "paper-time-affiliation-shares" else 0
    )
    assert summary["canonical_null_components"] == (
        1 if source["role"] == "paper-time-affiliation-shares" else 0
    )
    assert summary["states"]['institution_state:"conflicted"'] == 1
    assert summary["states"]["eligible_for_metrics:false"] == 5


@pytest.mark.parametrize("operation", ["create", "adopt"])
def test_generators_refuse_production_before_evidence_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    from physics_atlas_api.certification.contracts import CertificationError

    monkeypatch.setenv("PHYSICS_ATLAS_ENVIRONMENT", "production")
    monkeypatch.setenv("PHYSICS_ATLAS_FIXTURE_MODE", "false")
    source, output = tmp_path / "must-not-read", tmp_path / "must-not-create"
    arguments = {
        "expected_source_sha": "a" * 64,
        "expected_bytes": 1,
        "expected_rows": 1,
        "role": "affiliation-shares",
        "schema_version": "fixture-affiliation-v1",
        "historical_bindings": [],
    }
    # Empty bindings would fail metadata validation if the runtime guard were late.
    with pytest.raises(CertificationError, match="forbidden in production"):
        if operation == "create":
            codec.create_archive(source, output, **arguments)
        else:
            codec.adopt_archive(
                source,
                output,
                expected_archive_sha="b" * 64,
                expected_archive_bytes=1,
                **arguments,
            )
    assert not output.exists()


def test_adoption_keeps_existing_compressed_bytes_and_reads_no_original(
    source: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = tmp_path / "existing.gz"
    compressed = gzip.compress(source["body"], mtime=123)
    existing.write_bytes(compressed)
    old_open, old_stat = Path.open, Path.stat

    def guarded_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path.is_relative_to(source["path"].parents[1]):
            pytest.fail("historical original/manifest must not be opened")
        return old_open(path, *args, **kwargs)

    def guarded_stat(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == source["path"] or path == source["manifest"]:
            pytest.fail("historical original/manifest must not be probed")
        return old_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(Path, "stat", guarded_stat)
    adopted = codec.adopt_archive(
        existing,
        tmp_path / "adopted",
        expected_archive_sha=digest(compressed),
        expected_archive_bytes=len(compressed),
        **source["arguments"],
    )
    archive = Path(adopted["manifest_path"]).parent / adopted["archive"]["path"]
    assert archive.read_bytes() == compressed  # Not recompressed with another header.
    restore(adopted, tmp_path / "restored", source["role"])
    assert (tmp_path / "restored").read_bytes() == source["body"]


def test_replay_twins_keep_distinct_exact_historical_bindings(
    source: dict[str, Any], tmp_path: Path
) -> None:
    original = source["arguments"]["historical_bindings"][0]
    twin_root = tmp_path / "twin"
    twin = {
        **original,
        "manifest_sha256": "b" * 64,
        "manifest_id": "c" * 64,
        "historical_manifest_path": str(twin_root / "manifests/twin.json"),
        "original_path": str(twin_root / original["entry"]["path"]),
    }
    args = {**source["arguments"], "historical_bindings": [original, twin]}
    created = codec.create_archive(source["path"], tmp_path / "archive", **args)
    manifest = codec.read_manifest(
        Path(created["manifest_path"]), created["manifest_sha256"], source["role"]
    )
    assert manifest["historical_bindings"] == [original, twin]
    assert manifest["original"]["sha256"] == source["arguments"]["expected_source_sha"]
    restore(created, tmp_path / "restored", source["role"])
    assert (tmp_path / "restored").read_bytes() == source["body"]


@pytest.mark.parametrize("kind", ["source_hash", "source_rows", "binding", "role"])
def test_mismatched_identity_or_binding_never_publishes_manifest(
    source: dict[str, Any], tmp_path: Path, kind: str
) -> None:
    args = dict(source["arguments"])
    if kind == "source_hash":
        args["expected_source_sha"] = "0" * 64
    elif kind == "source_rows":
        args["expected_rows"] += 1
    elif kind == "binding":
        args["historical_bindings"] = [
            {
                **args["historical_bindings"][0],
                "original_path": "/wrong/historical/file.jsonl",
            }
        ]
    else:
        args["role"] = "provider-captures"
    with pytest.raises(codec.ArchiveError):
        codec.create_archive(source["path"], tmp_path / "bad", **args)
    assert not (tmp_path / "bad/archive-manifest.json").exists()
    assert source["path"].read_bytes() == source["body"]


def test_missing_corrupt_archive_and_bad_pin_fail_before_output(
    source: dict[str, Any], tmp_path: Path
) -> None:
    created = create(source, tmp_path / "archive")
    with pytest.raises(codec.ArchiveError, match="checksum"):
        restore(
            {**created, "manifest_sha256": "0" * 64},
            tmp_path / "restored",
            source["role"],
        )
    archive = Path(created["manifest_path"]).parent / created["archive"]["path"]
    archive.chmod(0o600)
    archive.write_bytes(b"X" * archive.stat().st_size)
    with pytest.raises(codec.ArchiveError, match="checksum"):
        restore(created, tmp_path / "restored", source["role"])
    assert not (tmp_path / "restored").exists()
    archive.unlink()  # This test owns a tiny generated fixture, not retained evidence.
    with pytest.raises(codec.ArchiveError, match="regular"):
        restore(created, tmp_path / "restored", source["role"])


@pytest.mark.parametrize("damage", ["truncate", "deflate"])
def test_rehashed_broken_gzip_never_becomes_verified_output(
    source: dict[str, Any], tmp_path: Path, damage: str
) -> None:
    created = create(source, tmp_path / "archive")
    path = Path(created["manifest_path"])
    manifest = json.loads(path.read_bytes())
    archive = path.parent / manifest["archive"]["path"]
    body = bytearray(archive.read_bytes())
    if damage == "truncate":
        body = body[:-5]
    else:
        body[10] = (body[10] & ~6) | 6
    archive.chmod(0o600)
    archive.write_bytes(body)
    manifest["archive"].update(sha256=digest(body), bytes=len(body))
    path.chmod(0o600)
    created["manifest_sha256"] = write_json(path, manifest)
    with pytest.raises(codec.ArchiveError, match="restore failed"):
        restore(created, tmp_path / "partial-owned-by-caller", source["role"])
    with pytest.raises(codec.ArchiveError, match="corrupt or truncated"):
        codec.adopt_archive(
            archive,
            tmp_path / "adopt",
            expected_archive_sha=digest(body),
            expected_archive_bytes=len(body),
            **source["arguments"],
        )
    assert not (tmp_path / "adopt").exists()


def test_summary_tamper_and_partial_source_archive_rejected(
    source: dict[str, Any], tmp_path: Path
) -> None:
    created = create(source, tmp_path / "archive")
    path = Path(created["manifest_path"])
    manifest = json.loads(path.read_bytes())
    manifest["scientific_summary"]["institution_provenance_sha256"] = "0" * 64
    path.chmod(0o600)
    created["manifest_sha256"] = write_json(path, manifest)
    with pytest.raises(codec.ArchiveError, match="summary differs"):
        restore(created, tmp_path / "unverified", source["role"])
    short = gzip.compress(source["body"].splitlines(keepends=True)[0], mtime=0)
    compressed = tmp_path / "partial.gz"
    compressed.write_bytes(short)
    with pytest.raises(codec.ArchiveError, match="identity differs"):
        codec.adopt_archive(
            compressed,
            tmp_path / "partial-adopt",
            expected_archive_sha=digest(short),
            expected_archive_bytes=len(short),
            **source["arguments"],
        )
    assert not (tmp_path / "partial-adopt").exists()


def test_caps_cover_stream_source_and_compressed_output(
    source: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(codec.ArchiveError, match="byte/row"):
        codec.copy_summarized(
            io.BytesIO(source["body"] + b"x"),
            io.BytesIO(),
            byte_limit=len(source["body"]),
            role=source["role"],
        )
    monkeypatch.setattr(codec, "MAX_ROWS", 1)
    with pytest.raises(codec.ArchiveError, match="byte/row"):
        codec.copy_summarized(
            io.BytesIO(source["body"]),
            io.BytesIO(),
            byte_limit=len(source["body"]),
            role=source["role"],
        )
    monkeypatch.setattr(codec, "MAX_ROWS", 1_000_000)
    monkeypatch.setattr(codec, "MAX_ARCHIVE_BYTES", 20)
    with pytest.raises(codec.ArchiveError, match="192 MiB"):
        create(source, tmp_path / "capped")
    assert not (tmp_path / "capped/archive-manifest.json").exists()


def test_existing_outputs_and_ambiguous_locator_refuse(
    source: dict[str, Any], tmp_path: Path
) -> None:
    created = create(source, tmp_path / "archive")
    with pytest.raises(FileExistsError):
        create(source, tmp_path / "archive")
    out = tmp_path / "existing"
    out.write_bytes(b"never overwrite")
    with pytest.raises(codec.ArchiveError, match="already exists"):
        restore(created, out, source["role"])
    assert out.read_bytes() == b"never overwrite"
    rows = [
        {"canonical_paper_id": "same", "mass": fraction("1/2")},
        {"canonical_paper_id": None, "candidate_id": "same", "mass": fraction("1/2")},
    ]
    body = b"\n".join(codec.encoded(row) for row in rows)
    with pytest.raises(codec.ArchiveError, match="ambiguous"):
        codec.copy_summarized(
            io.BytesIO(body),
            io.BytesIO(),
            byte_limit=len(body),
            role="paper-time-affiliation-shares",
        )


def test_nonunit_product_mismatch_are_reported_not_repaired() -> None:
    row = {
        "canonical_paper_id": "paper",
        "attribution_weight": fraction("1/3"),
        "author_weight": fraction("1/2"),
        "affiliation_weight": fraction("1"),
    }
    body = codec.encoded(row)
    out = io.BytesIO()
    summary = codec.copy_summarized(
        io.BytesIO(body),
        out,
        byte_limit=len(body),
        role="paper-time-affiliation-shares",
    )
    assert out.getvalue() == body
    assert summary["non_unit_mass_papers"] == 1
    assert summary["total_exact_mass"] == "1/3"
    assert summary["author_affiliation_product_mismatches"] == 1


@pytest.mark.parametrize(
    "body",
    [
        b'{"canonical_paper_id":"a","canonical_paper_id":"b"}',
        b'{"canonical_paper_id":"p","mass":{"exact":"NaN"}}',
        b'{"canonical_paper_id":null,"candidate_id":"p","mass":{"exact":"1"}}',
        b'{"canonical_paper_id":"p","mass":{"exact":"1","numerator":0,"denominator":1}}',
    ],
)
def test_invalid_json_fraction_or_paired_candidate_fails_closed(body: bytes) -> None:
    with pytest.raises(codec.ArchiveError):
        codec.copy_summarized(
            io.BytesIO(body),
            io.BytesIO(),
            byte_limit=len(body),
            role="affiliation-shares",
        )


def test_null_missing_zero_provenance_and_unknown_fields_have_distinct_fingerprints(
    source: dict[str, Any],
) -> None:
    rows = source["rows"]
    original = codec.copy_summarized(
        io.BytesIO(source["body"]),
        io.BytesIO(),
        byte_limit=len(source["body"]),
        role=source["role"],
    )
    rows[0]["unknown_future_field"]["null"] = 0
    altered = b"\n".join(codec.encoded(row) for row in rows)
    changed = codec.copy_summarized(
        io.BytesIO(altered), io.BytesIO(), byte_limit=len(altered), role=source["role"]
    )
    assert changed["complete_semantic_sha256"] != original["complete_semantic_sha256"]
    assert changed["total_exact_mass"] == original["total_exact_mass"]
    assert (
        changed["institution_provenance_sha256"]
        == original["institution_provenance_sha256"]
    )


@pytest.mark.parametrize("change", ["line_order", "binding_rows", "summary_count"])
def test_bool_is_not_equivalent_to_count_metadata(
    source: dict[str, Any], tmp_path: Path, change: str
) -> None:
    created = create(source, tmp_path / "archive")
    path = Path(created["manifest_path"])
    value = json.loads(path.read_bytes())
    if change == "line_order":
        value["original"]["line_order_preserved"] = 1
    elif change == "binding_rows":
        value["historical_bindings"][0]["entry"]["row_count"] = True
    else:
        value["scientific_summary"]["author_affiliation_product_mismatches"] = False
    path.chmod(0o600)
    created["manifest_sha256"] = write_json(path, value)
    with pytest.raises(codec.ArchiveError):
        restore(created, tmp_path / "not-verified", source["role"])


def test_optional_byte_comparison_and_incomplete_writes_fail_closed(
    source: dict[str, Any],
) -> None:
    body = source["body"]
    with pytest.raises(codec.ArchiveError, match="differ"):
        codec.copy_summarized(
            io.BytesIO(body),
            io.BytesIO(),
            byte_limit=len(body),
            role=source["role"],
            compare=io.BytesIO(b"wrong"),
        )
    with pytest.raises(codec.ArchiveError, match="tail"):
        codec.copy_summarized(
            io.BytesIO(body),
            io.BytesIO(),
            byte_limit=len(body),
            role=source["role"],
            compare=io.BytesIO(body + b"x"),
        )

    class Partial(io.BytesIO):
        def write(self, value: Any) -> int:
            return len(value) - 1

    with pytest.raises(codec.ArchiveError, match="partial"):
        codec.copy_summarized(
            io.BytesIO(body), Partial(), byte_limit=len(body), role=source["role"]
        )


@pytest.mark.parametrize("mutation", ["remove", "wrong", "unexpected"])
def test_role_specific_historical_entry_fields_are_strict(
    source: dict[str, Any], tmp_path: Path, mutation: str
) -> None:
    args = source["arguments"]
    entry = args["historical_bindings"][0]["entry"]
    if mutation == "remove":
        entry.pop("media_type" if source["role"] == "affiliation-shares" else "role")
    elif mutation == "wrong":
        entry["media_type"] = "application/json"
    else:
        entry["unexpected_field"] = "must not be silently discarded"
    with pytest.raises(codec.ArchiveError):
        codec.create_archive(source["path"], tmp_path / "bad", **args)
    assert not (tmp_path / "bad").exists()
