"""Lossless local decision-JSONL archive pilot; no acquisition or recertification.

One manifest-bound existing file, at most 4 GiB / 3 million rows. Original bytes
and line order are untouched. Files are create-exclusive; failures leave their
unpublished/partial outputs for review, never remove originals or retry in place.
An archive manifest proves integrity, not permission to retire historical data.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import time
import zlib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

VERSION = "lossless-historical-jsonl-archive-v1"
MAX_BYTES = 4 * 1024**3
MAX_ARCHIVE_BYTES = MAX_BYTES + 8 * 1024**2
MAX_MANIFEST_BYTES = 1024**2
MAX_ROWS = 3_000_000
MAX_LINE = 16 * 1024**2
CHUNK = 1024**2
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PROJECTIONS = {
    "identity": ("decision_id", "subject_id", "subject_type"),
    "status_reason_version": (
        "state",
        "reasons",
        "rule_version",
        "evidence_kind",
        "acquisition_scope",
        "dataset_version",
    ),
    "provenance": ("evidence",),
}


class ArchiveError(ValueError):
    """Integrity/bounds failure; no successful restore or retirement implied."""


def encoded(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def digest_file(path):
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while body := stream.read(CHUNK):
            digest.update(body)
            size += len(body)
    return digest.hexdigest(), size


def file_size(path):
    stat = path.stat()
    return {"logical_bytes": stat.st_size, "allocated_bytes": stat.st_blocks * 512}


def stable_identity(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def read_manifest(path):
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_MANIFEST_BYTES:
        raise ArchiveError("manifest must be a bounded nonempty regular file")
    with path.open("rb") as stream:
        body = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(body) > MAX_MANIFEST_BYTES:
        raise ArchiveError("manifest size limit exceeded")
    return body


class LedgerSummary:
    """Ordered summaries only; never re-evaluate a scientific decision."""

    def __init__(self):
        self.rows = self.bytes = self.evidence_references = self.reason_entries = 0
        self.digest = hashlib.sha256()
        self.projections = {name: hashlib.sha256() for name in PROJECTIONS}
        self.counts = {
            name: Counter() for name in ("state", "evidence_kind", "rule_version")
        }

    def add(self, line):
        self.rows += 1
        self.bytes += len(line)
        if self.rows > MAX_ROWS or self.bytes > MAX_BYTES or len(line) > MAX_LINE:
            raise ArchiveError("bounded historical-artifact limit exceeded")
        try:
            row = json.loads(line)
        except (ValueError, UnicodeError) as error:
            raise ArchiveError("invalid decision JSONL") from error
        if not isinstance(row, dict) or not isinstance(row.get("decision_id"), str):
            raise ArchiveError("decision JSONL requires object rows with decision IDs")
        for name, counter in self.counts.items():
            value = row.get(name)
            if not isinstance(value, str):
                raise ArchiveError(f"decision {name} must be text")
            counter[value] += 1
            if len(counter) > 512:
                raise ArchiveError("bounded summary vocabulary exceeded")
        if not isinstance(row.get("evidence"), list) or not isinstance(
            row.get("reasons"), list
        ):
            raise ArchiveError(
                "decision evidence/reasons must retain their original lists"
            )
        self.evidence_references += len(row["evidence"])
        self.reason_entries += len(row["reasons"])
        self.digest.update(line)
        for name, keys in PROJECTIONS.items():
            self.projections[name].update(
                encoded({key: row[key] for key in keys if key in row}) + b"\n"
            )

    def result(self):
        return {
            "rows": self.rows,
            "bytes": self.bytes,
            "sha256": self.digest.hexdigest(),
            "counts": {name: dict(counter) for name, counter in self.counts.items()},
            "ordered_projection_sha256": {
                name: value.hexdigest() for name, value in self.projections.items()
            },
            "evidence_reference_occurrences": self.evidence_references,
            "reason_entries": self.reason_entries,
        }


def copy_summarized(source, destination, *, compare=None, byte_limit=MAX_BYTES):
    summary = LedgerSummary()
    while line := source.readline(MAX_LINE + 1):
        if summary.bytes + len(line) > byte_limit:
            raise ArchiveError("decoded payload exceeds declared size")
        summary.add(line)
        if compare is not None and compare.read(len(line)) != line:
            raise ArchiveError("restored bytes differ from retained original")
        destination.write(line)
    if compare is not None and compare.read(1):
        raise ArchiveError("retained original has trailing bytes")
    return summary.result()


def _publish_json(path, value):
    body = encoded(value) + b"\n"
    with path.open("xb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o400)
    return hashlib.sha256(body).hexdigest()


def create_archive(
    source, validation_manifest, output, *, expected_source_sha, expected_manifest_sha
):
    source, validation_manifest, output = (
        source.resolve(strict=True),
        validation_manifest.resolve(strict=True),
        output.resolve(),
    )
    if not SHA256.fullmatch(expected_source_sha) or not SHA256.fullmatch(
        expected_manifest_sha
    ):
        raise ArchiveError("explicit SHA-256 bindings are required")
    if source.is_relative_to(output) or validation_manifest.is_relative_to(output):
        raise ArchiveError("output cannot overlap input evidence")
    original_stat = stable_identity(source)
    if not source.is_file() or not 0 < original_stat[2] <= MAX_BYTES:
        raise ArchiveError("only one nonempty existing artifact up to 4 GiB is allowed")
    linked_bytes = read_manifest(validation_manifest)
    if hashlib.sha256(linked_bytes).hexdigest() != expected_manifest_sha:
        raise ArchiveError("linked validation manifest checksum mismatch")
    linked = json.loads(linked_bytes)
    manifest_id = linked.get("certification_manifest_checksum")
    if (
        hashlib.sha256(
            encoded(
                {
                    key: value
                    for key, value in linked.items()
                    if key != "certification_manifest_checksum"
                }
            )
        ).hexdigest()
        != manifest_id
    ):
        raise ArchiveError("linked validation manifest self-checksum differs")
    records = [
        row
        for row in linked["artifacts"]
        if row["role"] == "evidence-certification-decisions"
        and row["checksum"] == expected_source_sha
    ]
    if len(records) != 1:
        raise ArchiveError(
            "exact decision artifact is not bound by linked validation manifest"
        )
    entry = records[0]
    if (
        entry["byte_count"] != original_stat[2]
        or not 0 < entry["row_count"] <= MAX_ROWS
        or validation_manifest.parents[2] / entry["path"] != source
    ):
        raise ArchiveError("source path/size/row count differs from linked manifest")
    # Fresh directory is the operation boundary. Nothing is overwritten or removed.
    output.mkdir(parents=True, exist_ok=False)
    archive = output / (expected_source_sha + ".jsonl.gz")
    started = time.monotonic()
    with source.open("rb") as original, archive.open("xb") as compressed:
        with gzip.GzipFile(
            fileobj=compressed, mode="wb", filename="", mtime=0, compresslevel=6
        ) as target:
            summary = copy_summarized(original, target, byte_limit=entry["byte_count"])
        compressed.flush()
        os.fsync(compressed.fileno())
    if (
        summary["sha256"] != expected_source_sha
        or summary["bytes"] != entry["byte_count"]
        or summary["rows"] != entry["row_count"]
        or stable_identity(source) != original_stat
    ):
        raise ArchiveError("original artifact changed or fails its manifest binding")
    archive_sha, archive_bytes = digest_file(archive)
    archive.chmod(0o400)
    manifest = {
        "version": VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "original": {
            "path": str(source),
            "sha256": expected_source_sha,
            "bytes": entry["byte_count"],
            "rows": entry["row_count"],
            "format": "utf-8-jsonl",
            "line_order_preserved": True,
        },
        "linked_validation_manifest": {
            "path": str(validation_manifest),
            "file_sha256": expected_manifest_sha,
            "manifest_id": linked["certification_manifest_checksum"],
            "source_bundle_manifest_checksum": linked[
                "source_bundle_manifest_checksum"
            ],
            "dataset_version": linked["dataset_version"],
            "acquisition_scope": linked["acquisition_scope"],
        },
        "archive": {
            "path": archive.name,
            "sha256": archive_sha,
            "bytes": archive_bytes,
            "encoding": "gzip",
            "level": 6,
            "mtime": 0,
            "filename_header": "",
            "zlib_version": zlib.ZLIB_RUNTIME_VERSION,
        },
        "scientific_summary": summary,
        "retention": (
            "original retained; archive integrity alone does not authorize retirement"
        ),
        "restore": (
            "Use this tool restore with manifest SHA-256 and a new output path; "
            "verify archive and decoded hashes before accepting output. "
            "No provider access or scientific recalculation is required."
        ),
    }
    manifest_path = output / "archive-manifest.json"
    manifest_sha = _publish_json(manifest_path, manifest)
    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "compression_seconds": time.monotonic() - started,
        "original": file_size(source),
        "archive": file_size(archive),
        "manifest": file_size(manifest_path),
        "scientific_summary": summary,
    }


def restore_archive(
    manifest_path, destination, *, expected_manifest_sha, compare_source=None
):
    manifest_path, destination = (
        manifest_path.resolve(strict=True),
        destination.resolve(),
    )
    if destination.exists():
        raise ArchiveError("restore destination already exists")
    body = read_manifest(manifest_path)
    if (
        not SHA256.fullmatch(expected_manifest_sha)
        or hashlib.sha256(body).hexdigest() != expected_manifest_sha
    ):
        raise ArchiveError("archive manifest checksum mismatch")
    manifest = json.loads(body)
    archived, original = manifest["archive"], manifest["original"]
    if (
        manifest["version"] != VERSION
        or archived["encoding"] != "gzip"
        or Path(archived["path"]).name != archived["path"]
        or not 0 < original["bytes"] <= MAX_BYTES
        or not 0 < original["rows"] <= MAX_ROWS
    ):
        raise ArchiveError("unsupported or unbounded archive manifest")
    archive = manifest_path.parent / archived["path"]
    archive_identity = stable_identity(archive)
    if (
        not archive.is_file()
        or not 0 < archived["bytes"] <= MAX_ARCHIVE_BYTES
        or archive_identity[2] != archived["bytes"]
    ):
        raise ArchiveError("compressed artifact must be a bounded regular file")
    if digest_file(archive) != (archived["sha256"], archived["bytes"]):
        raise ArchiveError("compressed artifact checksum/size mismatch")
    if stable_identity(archive) != archive_identity:
        raise ArchiveError("compressed artifact changed during integrity verification")
    compare = compare_source.open("rb") if compare_source is not None else None
    comparison_stat = (
        stable_identity(compare_source) if compare_source is not None else None
    )
    started = time.monotonic()
    try:
        with archive.open("rb") as compressed, destination.open("xb") as restored:
            with gzip.GzipFile(fileobj=compressed, mode="rb") as decoded:
                summary = copy_summarized(
                    decoded, restored, compare=compare, byte_limit=original["bytes"]
                )
            restored.flush()
            os.fsync(restored.fileno())
    except (OSError, EOFError) as error:
        raise ArchiveError(
            "archive restore failed; partial output is not verified"
        ) from error
    finally:
        if compare is not None:
            compare.close()
    if stable_identity(archive) != archive_identity:
        raise ArchiveError("compressed artifact changed during restoration")
    if summary != manifest["scientific_summary"] or (
        compare_source is not None
        and stable_identity(compare_source) != comparison_stat
    ):
        raise ArchiveError("restored scientific summary or original identity differs")
    if (
        summary["sha256"] != original["sha256"]
        or summary["bytes"] != original["bytes"]
        or summary["rows"] != original["rows"]
    ):
        raise ArchiveError("restored hash/size/rows differ from original manifest")
    return {
        "restored_path": str(destination),
        "restored": file_size(destination),
        "restore_seconds": time.monotonic() - started,
        "byte_for_byte_compared": compare_source is not None,
        "scientific_summary": summary,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    compact = commands.add_parser("pilot")
    compact.add_argument("--source", type=Path, required=True)
    compact.add_argument("--validation-manifest", type=Path, required=True)
    compact.add_argument("--source-sha256", required=True)
    compact.add_argument("--validation-manifest-sha256", required=True)
    compact.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--manifest", type=Path, required=True)
    restore.add_argument("--manifest-sha256", required=True)
    restore.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "restore":
        result = restore_archive(
            args.manifest, args.output, expected_manifest_sha=args.manifest_sha256
        )
    else:
        created = create_archive(
            args.source,
            args.validation_manifest,
            args.output,
            expected_source_sha=args.source_sha256,
            expected_manifest_sha=args.validation_manifest_sha256,
        )
        print(
            json.dumps(
                {
                    "stage": "archive_complete",
                    "manifest_sha256": created["manifest_sha256"],
                    "archive": created["archive"],
                    "compression_seconds": created["compression_seconds"],
                }
            ),
            flush=True,
        )
        restored = restore_archive(
            Path(created["manifest_path"]),
            args.output / "verified-restored-original.jsonl",
            expected_manifest_sha=created["manifest_sha256"],
            compare_source=args.source,
        )
        result = {
            "version": VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "compression": created,
            "recovery": restored,
            "original_retained": True,
            "scientific_recalculation": False,
            "network_access": False,
            "production_access": False,
        }
        _publish_json(args.output / "pilot-result.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    sys.exit(main())
