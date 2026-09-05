"""Bounded affiliation-only archive experiment; originals never become optional.

Uses the existing ArtifactRef/FilesystemArtifactStore, not a new authority
resolver. An archive proves recovery of a selected exact JSONL stream, not
permission to retire a source file or promote scientific eligibility.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import zlib
from collections import Counter, defaultdict
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path

from physics_atlas_api.certification.validation_artifacts import (
    check_validation_size,
    require_validation_runtime,
)
from physics_atlas_api.storage import ArtifactRef, FilesystemArtifactStore, StorageTier
from physics_atlas_api.storage.validation_retention import (
    check_validation_reservation_output,
    preflight_validation_retention,
)

VERSION = "bounded-affiliation-archive-pilot-v1"
MAX_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BYTES = 1200 * 1024 * 1024
ROLES = {"affiliation-shares", "paper-time-affiliation-shares"}


def encoded(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def read_pinned(path, expected, maximum=MAX_BYTES):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized pilot input")
    body = path.read_bytes()
    if sha256(body) != expected:
        raise ValueError("pilot input checksum mismatch")
    return body


def paper_locator(row, source_role):
    """Locate historical components without inventing a canonical identity.

    A null canonical ID is preserved. Only the historical replay affiliation
    schema has a retained candidate-component locator; paired shares still
    require their canonical ID. No source row or eligibility flag is rewritten.
    """
    if source_role not in ROLES or not isinstance(row, dict):
        raise ValueError("invalid affiliation role or row")
    canonical = row.get("canonical_paper_id")
    if isinstance(canonical, str) and canonical.strip():
        return canonical
    candidate = row.get("candidate_id")
    if (
        source_role == "paper-time-affiliation-shares"
        and "canonical_paper_id" in row
        and canonical is None
        and isinstance(candidate, str)
        and candidate.strip()
    ):
        return candidate
    raise ValueError("affiliation row lacks an exact supported paper locator")


def summarize(body, source_role="affiliation-shares"):
    """Describe stored shares exactly; do not re-resolve or recertify evidence."""
    if not body or len(body) > MAX_BYTES:
        raise ValueError("affiliation pilot requires 1 byte through 16 MiB")
    totals = defaultdict(Fraction)
    locator_kinds = {}
    states = Counter()
    linkage = hashlib.sha256()
    semantic = hashlib.sha256()
    rows = 0
    for line in body.splitlines():
        row = json.loads(line)
        paper = paper_locator(row, source_role)
        canonical = row["canonical_paper_id"] is not None
        if paper in locator_kinds and locator_kinds[paper] != canonical:
            raise ValueError("ambiguous canonical/candidate affiliation locator")
        locator_kinds[paper] = canonical
        weight = row.get("attribution_weight", row.get("mass"))
        if not isinstance(weight, dict) or not isinstance(weight.get("exact"), str):
            raise ValueError("affiliation row lacks exact stored mass")
        value = Fraction(weight["exact"])
        if value < 0 or value > 1:
            raise ValueError("invalid stored affiliation mass")
        totals[paper] += value
        for key in (
            "resolution_status",
            "paper_time_affiliation_state",
            "institution_state",
            "eligible_for_metrics",
            "eligible_for_public_metrics",
            "same_source_ror_conflict",
        ):
            states[
                f"{key}:{encoded(row[key]).decode() if key in row else '<absent>'}"
            ] += 1
        linked = {
            key: val
            for key, val in row.items()
            if any(
                marker in key
                for marker in (
                    "institution",
                    "source",
                    "page",
                    "provenance",
                    "ror",
                    "version",
                    "policy",
                    "precedence",
                )
            )
        }
        linkage.update(encoded(linked) + b"\n")
        semantic.update(encoded(row) + b"\n")
        rows += 1
        check_validation_size(paper_count=len(totals), decision_count=rows)
    return {
        "rows": rows,
        "papers": len(totals),
        "total_exact_mass": str(sum(totals.values(), Fraction())),
        "unit_mass_papers": sum(value == 1 for value in totals.values()),
        "non_unit_mass_papers": sum(value != 1 for value in totals.values()),
        "paper_mass_sha256": sha256(
            encoded({key: str(value) for key, value in sorted(totals.items())})
        ),
        "states": dict(sorted(states.items())),
        "institution_provenance_sha256": linkage.hexdigest(),
        "complete_semantic_sha256": semantic.hexdigest(),
    }


def select_source(source, source_manifest, manifest_sha256, paper_ids=None):
    manifest = json.loads(read_pinned(source_manifest, manifest_sha256))
    entries = [entry for entry in manifest["artifacts"] if entry.get("role") in ROLES]
    if len(entries) != 1:
        raise ValueError("manifest must bind exactly one affiliation artifact")
    entry = entries[0]
    root = source_manifest.resolve().parent.parent
    if source.is_symlink() or (root / entry["path"]).resolve() != source.resolve():
        raise ValueError("affiliation source differs from the exact manifest path")
    if not source.resolve().is_relative_to(root):
        raise ValueError("affiliation source escapes manifest root")
    if (
        source.stat().st_size != entry["byte_count"]
        or source.stat().st_size > MAX_SOURCE_BYTES
    ):
        raise ValueError("affiliation source size mismatch or source limit exceeded")
    if paper_ids is not None:
        check_validation_size(paper_count=len(paper_ids))
        if not paper_ids:
            raise ValueError("empty selected paper set")
    before = source.stat()
    digest = hashlib.sha256()
    parts = []
    selected_bytes = 0
    seen = set()
    row_count = 0
    locators = []
    offset = 0
    with source.open("rb") as stream:
        while line := stream.readline(MAX_BYTES + 1):
            if len(line) > MAX_BYTES:
                raise ValueError("oversized affiliation line")
            # A changing/appended input must not extend this bounded scan. Refuse
            # before parsing beyond the immutable manifest's byte/row limits.
            if (
                offset + len(line) > entry["byte_count"]
                or row_count >= entry["row_count"]
            ):
                raise ValueError("affiliation source exceeds pinned byte/row bounds")
            digest.update(line)
            row_count += 1
            row = json.loads(line)
            paper = paper_locator(row, entry["role"])
            if paper_ids is None or paper in paper_ids:
                selected_bytes += len(line)
                if selected_bytes > MAX_BYTES:
                    raise ValueError("selected affiliation stream exceeds 16 MiB")
                check_validation_size(
                    paper_count=len(seen | {paper}), decision_count=len(parts) + 1
                )
                parts.append(line)
                seen.add(paper)
                locators.append(
                    {
                        "row": row_count,
                        "offset": offset,
                        "bytes": len(line),
                        "sha256": sha256(line),
                    }
                )
            offset += len(line)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    ):
        raise ValueError("affiliation source changed during selection")
    if digest.hexdigest() != entry["checksum"] or row_count != entry["row_count"]:
        raise ValueError("affiliation source hash/row count differs")
    if paper_ids is not None and seen != paper_ids:
        raise ValueError("selected papers are absent from affiliation source")
    return b"".join(parts), entry, locators


def create_pilot(
    source,
    source_manifest,
    manifest_sha256,
    output,
    paper_ids=None,
    *,
    inventory,
    reservation,
):
    require_validation_runtime()
    if output != Path(reservation.output_reference):
        raise ValueError("pilot output must match its immutable retention reservation")
    preflight_validation_retention(inventory, reservation)
    body, entry, locators = select_source(
        source, source_manifest, manifest_sha256, paper_ids
    )
    summary = summarize(body, entry["role"])
    if summary["papers"] > reservation.paper_count:
        raise ValueError("selected affiliation papers exceed the retention reservation")
    if summary["non_unit_mass_papers"]:
        raise ValueError(
            "selected complete-paper affiliation masses do not conserve one"
        )
    source_root = source_manifest.resolve().parent.parent
    if output.resolve().is_relative_to(source_root) or source_root.is_relative_to(
        output.resolve()
    ):
        raise ValueError("pilot output must not overlap original source tree")
    buffer = io.BytesIO()
    with gzip.GzipFile(
        fileobj=buffer, mode="wb", filename="", mtime=0, compresslevel=6
    ) as stream:
        stream.write(body)
    # Reserve the entire stream, archive and bounded manifest BEFORE publishing.
    # Unused metadata allowance is capacity, not reported persistent bytes.
    check_validation_reservation_output(
        reservation,
        bytes_to_retain=len(body) + len(buffer.getvalue()) + MAX_BYTES,
    )
    output.mkdir(parents=True, exist_ok=False)
    store = FilesystemArtifactStore(output / "store")
    reference = store.put_bytes(
        buffer.getvalue(),
        tier=StorageTier.COLD,
        media_type="application/x-ndjson",
        content_encoding="gzip",
    )
    identity = {
        "version": VERSION,
        "source_artifact_sha256": entry["checksum"],
        "source_manifest_sha256": manifest_sha256,
        "selected_original_sha256": sha256(body),
    }
    manifest = {
        **identity,
        "pilot_id": sha256(encoded(identity)),
        "source_path": str(source.resolve()),
        "historical_manifest_path": str(source_manifest.resolve()),
        "source_role": entry["role"],
        "source_bytes": entry["byte_count"],
        "source_rows": entry["row_count"],
        "original_bytes": len(body),
        "archive": asdict(reference),
        "summary": summary,
        "selection": locators,
        "entire_source_selected": len(body) == entry["byte_count"],
        "original_retained": True,
        "archive_authority_promoted": False,
        "metric_observations_created": 0,
        "retention_inventory_sha256": inventory.sha256,
        "sample_id": reservation.sample_id,
        "sample_manifest_sha256": reservation.sample_manifest_sha256,
        "pipeline_version": reservation.pipeline_version,
    }
    if len(encoded(manifest)) + 1 > MAX_BYTES:
        raise ValueError("pilot manifest exceeds reserved metadata bound")
    for name, payload in (
        ("selected-original.jsonl", body),
        ("manifest.json", encoded(manifest) + b"\n"),
    ):
        with (output / name).open("xb") as stream:
            stream.write(payload)
        (output / name).chmod(0o444)
    store.local_path(reference).chmod(0o444)
    return manifest


def restore_pilot(manifest_path, manifest_sha256, store_root, output):
    require_validation_runtime()
    manifest = json.loads(read_pinned(manifest_path, manifest_sha256))
    if (
        manifest.get("version") != VERSION
        or type(manifest.get("original_bytes")) is not int
        or not 0 < manifest["original_bytes"] <= MAX_BYTES
    ):
        raise ValueError("invalid or unbounded affiliation pilot descriptor")
    identity = {
        key: manifest[key]
        for key in (
            "version",
            "source_artifact_sha256",
            "source_manifest_sha256",
            "selected_original_sha256",
        )
    }
    if manifest.get("pilot_id") != sha256(encoded(identity)):
        raise ValueError("affiliation pilot identity mismatch")
    record = dict(manifest["archive"])
    record["tier"] = StorageTier(record["tier"])
    reference = ArtifactRef(**record)
    if reference.content_encoding != "gzip" or reference.size_bytes > MAX_BYTES + 65536:
        raise ValueError("invalid archive encoding/size")
    store = FilesystemArtifactStore(store_root)
    with store.open(reference) as compressed:
        try:
            with gzip.GzipFile(fileobj=compressed, mode="rb") as stream:
                body = stream.read(MAX_BYTES + 1)
        except (OSError, EOFError, zlib.error) as error:
            raise ValueError("affiliation archive is corrupt or truncated") from error
    if (
        len(body) != manifest["original_bytes"]
        or sha256(body) != manifest["selected_original_sha256"]
    ):
        raise ValueError("recovered affiliation bytes do not match")
    if summarize(body, manifest["source_role"]) != manifest["summary"]:
        raise ValueError("recovered affiliation scientific summary differs")
    # Original path is historical metadata only: never read it during recovery.
    with output.open("xb") as stream:
        stream.write(body)
    return {
        "pilot_id": manifest["pilot_id"],
        "exact_restore": True,
        "sha256": sha256(body),
        "bytes": len(body),
        "summary": manifest["summary"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            restore_pilot(args.manifest, args.manifest_sha256, args.store, args.output),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
