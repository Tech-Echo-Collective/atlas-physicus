"""Explicit, pinned local artifact resolution; no production or scientific logic.

The descriptor chooses exactly one authority. Alternative representations are
never fallback candidates. Immutable historical manifests remain unchanged; their
logical path is verified as metadata, not opened when archive authority is chosen.
Only a resolver-owned temporary copy is returned, and only that copy is cleaned up.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import compact_historical_artifact as archive_helper

DESCRIPTOR_VERSION = "historical-artifact-descriptor-v1"
ARTIFACT_TYPE = "evidence-certification-decisions"
ARTIFACT_SCHEMA_VERSION = "historical-replay-evidence-certification-v1"
ORIGINAL_METHOD = "verified-copy-v1"
MAX_DESCRIPTOR_BYTES = 64 * 1024
MAX_REPRESENTATIONS = 8
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ResolutionError(ValueError):
    """Authority, identity or recovery failed; no usable artifact was admitted."""


@dataclass(frozen=True)
class ResolvedArtifact:
    path: Path
    logical_artifact_id: str
    representation_id: str
    representation_type: str
    scientific_summary: dict


def logical_artifact_id(artifact_type, schema_version, sha256):
    """Location-independent identity; the content hash alone is not the type."""
    return hashlib.sha256(
        archive_helper.encoded(
            {"type": artifact_type, "schema_version": schema_version, "sha256": sha256}
        )
    ).hexdigest()


def _exact_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ResolutionError(f"{label} has unsupported or missing fields")


def _text(value, label):
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ResolutionError(f"{label} must be nonempty text")
    return value


def _sha(value, label):
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ResolutionError(f"{label} must be a lowercase SHA-256")
    return value


def _relative(value):
    value = _text(value, "storage reference")
    parts = value.split("/")
    if (
        "\\" in value
        or ":" in value
        or any(part in ("", ".", "..") for part in parts)
        or PurePosixPath(value).is_absolute()
    ):
        raise ResolutionError("storage reference must be contained relative components")
    return value


def _root(path):
    absolute = Path(path).absolute()
    resolved = absolute.resolve(strict=True)
    if resolved != absolute or not resolved.is_dir():
        raise ResolutionError("storage root must be a real nonsymlink directory")
    return resolved


def _contained_file(root, reference):
    candidate = root / _relative(reference)
    current = root
    for part in PurePosixPath(reference).parts:
        current /= part
        if current.is_symlink():
            raise ResolutionError("storage reference contains a symlink")
    if candidate.resolve(strict=True) != candidate or not candidate.is_file():
        raise ResolutionError("storage reference is not a contained regular file")
    return candidate


def _read_pinned(path, expected_sha, limit):
    _sha(expected_sha, "pinned manifest hash")
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ResolutionError("manifest must be a bounded regular file")
    before = archive_helper.stable_identity(path)
    with path.open("rb") as stream:
        body = stream.read(limit + 1)
    if (
        len(body) > limit
        or hashlib.sha256(body).hexdigest() != expected_sha
        or archive_helper.stable_identity(path) != before
    ):
        raise ResolutionError("pinned manifest integrity failed")

    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ResolutionError("duplicate manifest property")
            value[key] = item
        return value

    value = json.loads(body, object_pairs_hook=unique_pairs)
    if not isinstance(value, dict):
        raise ResolutionError("manifest must be a JSON object")
    return value


def _descriptor(path, expected_sha):
    descriptor = _read_pinned(path, expected_sha, MAX_DESCRIPTOR_BYTES)
    _exact_keys(
        descriptor,
        ("version", "artifact", "authoritative_representation", "representations"),
        "descriptor",
    )
    if descriptor["version"] != DESCRIPTOR_VERSION:
        raise ResolutionError("unsupported descriptor version")
    artifact = descriptor["artifact"]
    _exact_keys(
        artifact,
        ("type", "schema_version", "sha256", "bytes", "rows", "logical_id"),
        "logical artifact",
    )
    if (
        artifact["type"] != ARTIFACT_TYPE
        or artifact["schema_version"] != ARTIFACT_SCHEMA_VERSION
    ):
        raise ResolutionError("unsupported artifact type/schema version")
    _sha(artifact["sha256"], "artifact hash")
    if (
        type(artifact["bytes"]) is not int
        or not 0 < artifact["bytes"] <= archive_helper.MAX_BYTES
        or type(artifact["rows"]) is not int
        or not 0 < artifact["rows"] <= archive_helper.MAX_ROWS
        or artifact["logical_id"]
        != logical_artifact_id(
            artifact["type"], artifact["schema_version"], artifact["sha256"]
        )
    ):
        raise ResolutionError("logical artifact identity or bounds failed")
    authority = _text(descriptor["authoritative_representation"], "authority id")
    representations = descriptor["representations"]
    if (
        not isinstance(representations, list)
        or not 1 <= len(representations) <= MAX_REPRESENTATIONS
    ):
        raise ResolutionError("descriptor requires bounded representations")
    by_id = {}
    for item in representations:
        if not isinstance(item, dict):
            raise ResolutionError("representation must be an object")
        keys = {"id", "type", "storage_reference", "restore_method"}
        if item.get("type") == "archive":
            keys.add("archive_manifest_sha256")
            _sha(item.get("archive_manifest_sha256"), "archive manifest hash")
            method = archive_helper.VERSION
        elif item.get("type") == "original":
            method = ORIGINAL_METHOD
        else:
            raise ResolutionError("unsupported representation type")
        _exact_keys(item, keys, "representation")
        identifier = _text(item["id"], "representation id")
        if identifier in by_id or item["restore_method"] != method:
            raise ResolutionError("conflicting representation id or restore method")
        _relative(item["storage_reference"])
        by_id[identifier] = item
    if authority not in by_id:
        raise ResolutionError("authoritative representation is absent")
    return artifact, by_id[authority]


def _historical_binding(path, expected_sha, artifact):
    manifest = _read_pinned(path, expected_sha, archive_helper.MAX_MANIFEST_BYTES)
    manifest_id = _sha(manifest.get("certification_manifest_checksum"), "historical id")
    unsigned = {
        key: value
        for key, value in manifest.items()
        if key != "certification_manifest_checksum"
    }
    if hashlib.sha256(archive_helper.encoded(unsigned)).hexdigest() != manifest_id:
        raise ResolutionError("historical manifest self-checksum failed")
    if manifest.get("certification_version") != artifact["schema_version"]:
        raise ResolutionError("historical artifact schema version differs")
    stream = manifest.get("decision_stream")
    expected_stream = {
        "artifact_available": True,
        "byte_count": artifact["bytes"],
        "checksum": artifact["sha256"],
        "row_count": artifact["rows"],
    }
    if stream != expected_stream or manifest.get("summary_only") is not False:
        raise ResolutionError(
            "historical manifest does not retain exact decision stream"
        )
    entries = manifest.get("artifacts")
    if not isinstance(entries, list) or len(entries) > 32:
        raise ResolutionError("historical artifacts must be a bounded list")
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("role") == artifact["type"]
    ]
    expected_entry = {
        "role": artifact["type"],
        "path": f"certification/decisions/{artifact['sha256']}.jsonl",
        "checksum": artifact["sha256"],
        "byte_count": artifact["bytes"],
        "row_count": artifact["rows"],
    }
    if matches != [expected_entry]:
        raise ResolutionError("historical role/path/hash/size/rows binding differs")
    return manifest, expected_entry


def _archive_binding(
    path, representation, artifact, manifest, manifest_sha, entry, root
):
    stored = _read_pinned(
        path,
        representation["archive_manifest_sha256"],
        archive_helper.MAX_MANIFEST_BYTES,
    )
    original, linked = stored.get("original"), stored.get("linked_validation_manifest")
    if not isinstance(original, dict) or not isinstance(linked, dict):
        raise ResolutionError("archive lacks original/historical linkage")
    if any(original.get(key) != artifact[key] for key in ("sha256", "bytes", "rows")):
        raise ResolutionError("archive original identity differs")
    if (
        original.get("format") != "utf-8-jsonl"
        or original.get("line_order_preserved") is not True
    ):
        raise ResolutionError("archive original format/order differs")
    expected = {
        "file_sha256": manifest_sha,
        "manifest_id": manifest["certification_manifest_checksum"],
        "source_bundle_manifest_checksum": manifest.get(
            "source_bundle_manifest_checksum"
        ),
        "dataset_version": manifest.get("dataset_version"),
        "acquisition_scope": manifest.get("acquisition_scope"),
    }
    if any(linked.get(key) != value for key, value in expected.items()):
        raise ResolutionError("archive linked historical manifest differs")
    # Historical absolute locations are checked lexically only: never stat/open.
    old_manifest = PurePosixPath(_text(linked.get("path"), "historical manifest path"))
    old_original = PurePosixPath(
        _text(original.get("path"), "historical original path")
    )
    if (
        not old_manifest.is_absolute()
        or not old_original.is_absolute()
        or ".." in old_manifest.parts
        or ".." in old_original.parts
        or len(old_manifest.parents) < 3
        or old_manifest.parent.parent.parent / entry["path"] != old_original
    ):
        raise ResolutionError("archive historical location binding differs")
    archived = stored.get("archive")
    if not isinstance(archived, dict):
        raise ResolutionError("archive representation metadata is missing")
    filename = _relative(archived.get("path"))
    if "/" in filename:
        raise ResolutionError("archive payload must be beside its manifest")
    archive_path = path.parent / filename
    _contained_file(root, archive_path.relative_to(root).as_posix())
    return stored


@contextmanager
def resolve_historical_artifact(
    descriptor_path,
    *,
    expected_descriptor_sha256,
    storage_root,
    certification_manifest,
    expected_certification_manifest_sha256,
    temp_parent=None,
):
    """Yield only fully verified local bytes; never fall back or retire originals.

    Returned paths live only inside this context. Any temporary partial output is
    deleted on failure, and context exit removes the unique resolver-owned copy.
    No original/alternative path is read for an archive-authoritative descriptor.
    """
    admitted = False
    try:
        root = _root(storage_root)
        artifact, authority = _descriptor(descriptor_path, expected_descriptor_sha256)
        historical, entry = _historical_binding(
            certification_manifest, expected_certification_manifest_sha256, artifact
        )
        source = _contained_file(root, authority["storage_reference"])
        if authority["type"] == "archive":
            _archive_binding(
                source,
                authority,
                artifact,
                historical,
                expected_certification_manifest_sha256,
                entry,
                root,
            )
        with tempfile.TemporaryDirectory(
            prefix="atlas-artifact-resolve-", dir=temp_parent
        ) as directory:
            restored = Path(directory) / "verified.jsonl"
            if authority["type"] == "archive":
                summary = archive_helper.restore_archive(
                    source,
                    restored,
                    expected_manifest_sha=authority["archive_manifest_sha256"],
                )["scientific_summary"]
            else:
                before = archive_helper.stable_identity(source)
                if before[2] != artifact["bytes"]:
                    raise ResolutionError("original representation size differs")
                with source.open("rb") as original, restored.open("xb") as target:
                    summary = archive_helper.copy_summarized(
                        original, target, byte_limit=artifact["bytes"]
                    )
                    target.flush()
                    os.fsync(target.fileno())
                if archive_helper.stable_identity(source) != before:
                    raise ResolutionError("original representation changed during read")
            if any(
                summary[key] != artifact[key] for key in ("sha256", "bytes", "rows")
            ):
                raise ResolutionError("resolved logical artifact integrity differs")
            restored.chmod(0o400)
            result = ResolvedArtifact(
                restored,
                artifact["logical_id"],
                authority["id"],
                authority["type"],
                summary,
            )
            # Caller exceptions must propagate unchanged; cleanup is still guaranteed.
            admitted = True
            yield result
    except ResolutionError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        if admitted:
            raise
        raise ResolutionError(f"artifact resolution failed: {error}") from error
