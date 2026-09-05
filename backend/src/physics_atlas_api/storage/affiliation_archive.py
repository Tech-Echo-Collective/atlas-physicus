"""Lossless affiliation codec for the existing historical artifact resolver.

This is not an authority resolver, importer, certification engine or deletion
tool. One already-existing artifact may be streamed under historical-file bounds;
the smaller per-trace validation-generation limits are deliberately unchanged.
Historical paths are metadata only during recovery. No scientific row is edited.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import zlib
from collections import Counter, defaultdict
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, cast

VERSION = "lossless-affiliation-jsonl-archive-v1"
MAX_BYTES = 4 * 1024**3
MAX_ROWS = 1_000_000
MAX_MANIFEST_BYTES = 1024**2
MAX_LINE = 16 * 1024**2
MAX_ARCHIVE_BYTES = 192 * 1024**2
CHUNK = 1024**2
ROLES = frozenset({"affiliation-shares", "paper-time-affiliation-shares"})
_SHA = re.compile(r"[0-9a-f]{64}")
_FRACTION = re.compile(r"-?[0-9]+(?:/[0-9]+)?")
_STATES = (
    "resolution_status",
    "paper_time_affiliation_state",
    "institution_state",
    "eligible_for_metrics",
    "eligible_for_public_metrics",
    "same_source_ror_conflict",
)
_LINKS = (
    "institution",
    "source",
    "page",
    "provenance",
    "ror",
    "version",
    "policy",
    "precedence",
)


class ArchiveError(ValueError):
    """Integrity/bounds failure; no authority or retirement is implied."""


def encoded(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ArchiveError("expected lowercase SHA-256")
    return value


def _integer(value: object, maximum: int) -> int:
    if type(value) is not int or not 0 < value <= maximum:
        raise ArchiveError("invalid or unbounded artifact dimensions")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ArchiveError("expected exact nonempty text")
    return value


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArchiveError("duplicate JSON property")
        result[key] = value
    return result


def _json(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body, object_pairs_hook=_object)
        if not isinstance(value, dict):
            raise ArchiveError("JSON object required")
        encoded(value)  # Reject NaN/Infinity; preserves missing/null/zero distinctions.
        return cast(dict[str, Any], value)
    except (ValueError, UnicodeError) as error:
        raise ArchiveError("invalid affiliation JSON") from error


def _role(role: str) -> None:
    if role not in ROLES:
        raise ArchiveError("unsupported affiliation role")


def _locator(row: dict[str, Any], role: str) -> tuple[str, bool]:
    canonical = row.get("canonical_paper_id")
    if isinstance(canonical, str) and canonical.strip():
        return canonical, True
    candidate = row.get("candidate_id")
    if (
        role == "paper-time-affiliation-shares"
        and "canonical_paper_id" in row
        and canonical is None
        and isinstance(candidate, str)
        and candidate.strip()
    ):
        return candidate, False
    raise ArchiveError("affiliation row lacks an exact supported paper locator")


def _fraction(value: object) -> Fraction:
    if not isinstance(value, dict):
        raise ArchiveError("exact affiliation fraction required")
    exact = value.get("exact")
    if (
        not isinstance(exact, str)
        or len(exact) > 256
        or _FRACTION.fullmatch(exact) is None
    ):
        raise ArchiveError("invalid exact affiliation fraction")
    try:
        result = Fraction(exact)
    except (ValueError, ZeroDivisionError) as error:
        raise ArchiveError("invalid exact affiliation fraction") from error
    if not 0 <= result <= 1:
        raise ArchiveError("affiliation fraction is outside unit bounds")
    if "numerator" in value or "denominator" in value:
        numerator, denominator = value.get("numerator"), value.get("denominator")
        if (
            type(numerator) is not int
            or type(denominator) is not int
            or denominator <= 0
            or Fraction(numerator, denominator) != result
        ):
            raise ArchiveError("stored fraction representations disagree")
    return result


def copy_summarized(
    source: BinaryIO,
    destination: BinaryIO,
    *,
    byte_limit: int,
    role: str,
    compare: BinaryIO | None = None,
) -> dict[str, Any]:
    """Stream exact bytes plus aggregate fingerprints, never a new row trace.

    Stored per-paper totals and products are measured, not adjusted. Non-unit
    totals remain explicit; the caller's retirement review decides eligibility.
    """
    _role(role)
    _integer(byte_limit, MAX_BYTES)
    digest, semantic, linkage, statuses = (hashlib.sha256() for _ in range(4))
    totals: dict[str, Fraction] = defaultdict(Fraction)
    kinds: dict[str, bool] = {}
    states: Counter[str] = Counter()
    rows = size = products = product_mismatches = product_absent = 0
    while line := source.readline(min(MAX_LINE, byte_limit - size) + 1):
        if len(line) > MAX_LINE or size + len(line) > byte_limit or rows >= MAX_ROWS:
            raise ArchiveError("affiliation stream exceeds pinned byte/row bounds")
        row = _json(line)
        paper, canonical = _locator(row, role)
        if paper in kinds and kinds[paper] != canonical:
            raise ArchiveError("ambiguous canonical/candidate affiliation locator")
        kinds[paper] = canonical
        weight = _fraction(row.get("attribution_weight", row.get("mass")))
        totals[paper] += weight
        if "author_weight" in row or "affiliation_weight" in row:
            author = _fraction(row.get("author_weight"))
            affiliation = _fraction(row.get("affiliation_weight"))
            products += 1
            product_mismatches += author * affiliation != weight
        else:
            product_absent += 1
        for field in _STATES:
            stored = encoded(row[field]).decode() if field in row else "<absent>"
            states[f"{field}:{stored}"] += 1
        linked = {
            key: value
            for key, value in row.items()
            if any(marker in key for marker in _LINKS)
        }
        state_row = {
            key: value
            for key, value in row.items()
            if any(
                marker in key
                for marker in (
                    "state",
                    "status",
                    "reason",
                    "version",
                    "policy",
                    "eligible",
                )
            )
        }
        digest.update(line)
        semantic.update(encoded(row) + b"\n")
        linkage.update(encoded(linked) + b"\n")
        statuses.update(encoded(state_row) + b"\n")
        if compare is not None and compare.read(len(line)) != line:
            raise ArchiveError("restored bytes differ from retained original")
        if destination.write(line) != len(line):
            raise ArchiveError("partial affiliation output write")
        rows += 1
        size += len(line)
    if not rows or (compare is not None and compare.read(1)):
        raise ArchiveError("empty affiliation stream or unmatched original tail")
    return {
        "summary_version": "affiliation-byte-summary-v1",
        "sha256": digest.hexdigest(),
        "bytes": size,
        "rows": rows,
        "papers": len(totals),
        "total_exact_mass": str(sum(totals.values(), Fraction())),
        "unit_mass_papers": sum(total == 1 for total in totals.values()),
        "non_unit_mass_papers": sum(total != 1 for total in totals.values()),
        "paper_mass_sha256": hashlib.sha256(
            encoded({key: str(value) for key, value in sorted(totals.items())})
        ).hexdigest(),
        "states": dict(sorted(states.items())),
        "institution_provenance_sha256": linkage.hexdigest(),
        "complete_semantic_sha256": semantic.hexdigest(),
        "status_reason_version_sha256": statuses.hexdigest(),
        "author_affiliation_product_rows": products,
        "author_affiliation_product_mismatches": product_mismatches,
        "author_affiliation_product_absent_rows": product_absent,
        "canonical_null_components": sum(not kind for kind in kinds.values()),
    }


def _identity(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def digest_file(path: Path, maximum: int = MAX_BYTES) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise ArchiveError("artifact must be a regular nonsymlink file")
    before = _identity(path)
    if not 0 < before[2] <= maximum:
        raise ArchiveError("artifact size exceeds bounded limit")
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while body := stream.read(min(CHUNK, maximum - size) + 1):
            size += len(body)
            if size > maximum:
                raise ArchiveError("artifact grew beyond bounded limit")
            digest.update(body)
    if _identity(path) != before or size != before[2]:
        raise ArchiveError("artifact changed during checksum verification")
    return digest.hexdigest(), size


def _keys(value: object, expected: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ArchiveError("unsupported or missing archive fields")
    return cast(dict[str, Any], value)


def _bindings(bindings: object, original: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(bindings, list) or not 1 <= len(bindings) <= 64:
        raise ArchiveError("bounded historical bindings are required")
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in bindings:
        binding = _keys(
            item,
            {
                "manifest_sha256",
                "manifest_id",
                "manifest_version",
                "historical_manifest_path",
                "original_path",
                "entry",
            },
        )
        _sha(binding["manifest_sha256"])
        _sha(binding["manifest_id"])
        _text(binding["manifest_version"])
        historical = PurePosixPath(_text(binding["historical_manifest_path"]))
        old_path = PurePosixPath(_text(binding["original_path"]))
        entry_keys = {"role", "path", "checksum", "byte_count", "row_count"}
        if original["type"] == "affiliation-shares":
            entry_keys.add("media_type")
        entry = _keys(binding["entry"], entry_keys)
        if (
            original["type"] == "affiliation-shares"
            and entry["media_type"] != "application/x-ndjson"
        ):
            raise ArchiveError("paired affiliation media type differs")
        _integer(entry["byte_count"], MAX_BYTES)
        _integer(entry["row_count"], MAX_ROWS)
        relative = _text(entry["path"])
        if (
            PurePosixPath(relative).is_absolute()
            or any(part in ("", ".", "..") for part in relative.split("/"))
            or "\\" in relative
            or ":" in relative
        ):
            raise ArchiveError("historical entry must be a contained relative path")
        if (
            not historical.is_absolute()
            or not old_path.is_absolute()
            or ".." in historical.parts
            or ".." in old_path.parts
            or historical.parent.parent / relative != old_path
        ):
            raise ArchiveError("historical original/path binding differs")
        if any(
            entry[key] != original[target]
            for key, target in (
                ("role", "type"),
                ("checksum", "sha256"),
                ("byte_count", "bytes"),
                ("row_count", "rows"),
            )
        ):
            raise ArchiveError("historical content binding differs")
        identity = (binding["manifest_sha256"], str(historical))
        if identity in seen:
            raise ArchiveError("duplicate historical binding")
        seen.add(identity)
        result.append(binding)
    return result


def _original(
    *,
    expected_source_sha: str,
    expected_bytes: int,
    expected_rows: int,
    role: str,
    schema_version: str,
) -> dict[str, Any]:
    _role(role)
    return {
        "sha256": _sha(expected_source_sha),
        "bytes": _integer(expected_bytes, MAX_BYTES),
        "rows": _integer(expected_rows, MAX_ROWS),
        "type": role,
        "schema_version": _text(schema_version),
        "format": "utf-8-jsonl",
        "line_order_preserved": True,
    }


def _check_summary(summary: dict[str, Any], original: dict[str, Any]) -> None:
    if any(summary[key] != original[key] for key in ("sha256", "bytes", "rows")):
        raise ArchiveError("decoded affiliation identity differs")


def read_manifest(path: Path, expected_sha: str, role: str) -> dict[str, Any]:
    _role(role)
    if digest_file(path, MAX_MANIFEST_BYTES)[0] != _sha(expected_sha):
        raise ArchiveError("archive manifest checksum mismatch")
    before = _identity(path)
    with path.open("rb") as stream:
        body = stream.read(MAX_MANIFEST_BYTES + 1)
    if (
        len(body) > MAX_MANIFEST_BYTES
        or hashlib.sha256(body).hexdigest() != expected_sha
        or _identity(path) != before
    ):
        raise ArchiveError("archive manifest changed during read")
    manifest = _keys(
        _json(body),
        {"version", "original", "archive", "scientific_summary", "historical_bindings"},
    )
    if manifest["version"] != VERSION:
        raise ArchiveError("unsupported affiliation archive version")
    original = _keys(
        manifest["original"],
        {
            "sha256",
            "bytes",
            "rows",
            "type",
            "schema_version",
            "format",
            "line_order_preserved",
        },
    )
    expected = _original(
        expected_source_sha=original["sha256"],
        expected_bytes=original["bytes"],
        expected_rows=original["rows"],
        role=role,
        schema_version=original["schema_version"],
    )
    if original != expected or original["line_order_preserved"] is not True:
        raise ArchiveError("original affiliation role/format differs")
    archive = _keys(manifest["archive"], {"path", "sha256", "bytes", "encoding"})
    filename = _text(archive["path"])
    if (
        filename in (".", "..")
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
        or ":" in filename
    ):
        raise ArchiveError("archive payload must be beside its manifest")
    _sha(archive["sha256"])
    _integer(archive["bytes"], MAX_ARCHIVE_BYTES)
    if archive["encoding"] != "gzip" or not isinstance(
        manifest["scientific_summary"], dict
    ):
        raise ArchiveError("invalid affiliation archive encoding/summary")
    _bindings(manifest["historical_bindings"], original)
    return manifest


def restore_archive(
    manifest_path: Path, destination: Path, *, expected_manifest_sha: str, role: str
) -> dict[str, Any]:
    """Verify selected bytes; caller owns cleanup of only its temporary output."""
    if destination.exists() or destination.is_symlink():
        raise ArchiveError("restore destination already exists")
    manifest = read_manifest(manifest_path, expected_manifest_sha, role)
    archive = manifest_path.parent / manifest["archive"]["path"]
    expected = manifest["archive"]
    if digest_file(archive, MAX_ARCHIVE_BYTES) != (
        expected["sha256"],
        expected["bytes"],
    ):
        raise ArchiveError("compressed affiliation checksum/size mismatch")
    before = _identity(archive)
    try:
        with archive.open("rb") as compressed, destination.open("xb") as restored:
            with gzip.GzipFile(fileobj=compressed, mode="rb") as decoded:
                summary = copy_summarized(
                    cast(BinaryIO, decoded),
                    restored,
                    byte_limit=manifest["original"]["bytes"],
                    role=role,
                )
            restored.flush()
            os.fsync(restored.fileno())
    except (OSError, EOFError, zlib.error) as error:
        raise ArchiveError(
            "affiliation restore failed; partial output is not verified"
        ) from error
    if _identity(archive) != before:
        raise ArchiveError("archive changed during restoration")
    _check_summary(summary, manifest["original"])
    if encoded(summary) != encoded(manifest["scientific_summary"]):
        raise ArchiveError("restored affiliation scientific summary differs")
    return {"scientific_summary": summary, "restored_path": str(destination)}


class _LimitedWriter:
    def __init__(self, stream: BinaryIO) -> None:
        self.stream, self.size = stream, 0

    def write(self, body: bytes) -> int:
        if self.size + len(body) > MAX_ARCHIVE_BYTES:
            raise ArchiveError("compressed affiliation output exceeds 192 MiB")
        count = self.stream.write(body)
        if count != len(body):
            raise ArchiveError("partial compressed affiliation write")
        self.size += count
        return count

    def flush(self) -> None:
        self.stream.flush()


class _Discard:
    def write(self, body: bytes) -> int:
        return len(body)


def _new_output(output: Path, source: Path) -> None:
    if output.absolute() != output.resolve() or source.is_relative_to(output.resolve()):
        raise ArchiveError("archive output is unsafe or overlaps input")
    output.mkdir(parents=True, exist_ok=False)


def _publish(
    output: Path,
    original: dict[str, Any],
    summary: dict[str, Any],
    bindings: list[dict[str, Any]],
    archive: Path,
) -> dict[str, Any]:
    archive_sha, archive_bytes = digest_file(archive, MAX_ARCHIVE_BYTES)
    manifest = {
        "version": VERSION,
        "original": original,
        "archive": {
            "path": archive.name,
            "sha256": archive_sha,
            "bytes": archive_bytes,
            "encoding": "gzip",
        },
        "scientific_summary": summary,
        "historical_bindings": bindings,
    }
    body = encoded(manifest) + b"\n"
    if len(body) > MAX_MANIFEST_BYTES:
        raise ArchiveError("archive manifest exceeds 1 MiB")
    path = output / "archive-manifest.json"
    with path.open("xb") as stream:
        if stream.write(body) != len(body):
            raise ArchiveError("partial archive manifest write")
        stream.flush()
        os.fsync(stream.fileno())
    archive.chmod(0o400)
    path.chmod(0o400)
    return {
        "manifest_path": str(path),
        "manifest_sha256": hashlib.sha256(body).hexdigest(),
        "scientific_summary": summary,
        "archive": manifest["archive"],
    }


def create_archive(
    source: Path,
    output: Path,
    *,
    expected_source_sha: str,
    expected_bytes: int,
    expected_rows: int,
    role: str,
    schema_version: str,
    historical_bindings: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Compress exactly one existing pinned affiliation stream, without replay."""
    from ..certification.validation_artifacts import require_validation_runtime

    require_validation_runtime()
    original = _original(
        expected_source_sha=expected_source_sha,
        expected_bytes=expected_bytes,
        expected_rows=expected_rows,
        role=role,
        schema_version=schema_version,
    )
    bindings = _bindings(list(historical_bindings), original)
    if (
        source.is_symlink()
        or not source.is_file()
        or _identity(source)[2] != expected_bytes
    ):
        raise ArchiveError("original affiliation size/path differs")
    before = _identity(source)
    _new_output(output, source.resolve())
    archive = output / (expected_source_sha + ".jsonl.gz")
    with source.open("rb") as incoming, archive.open("xb") as stored:
        limited = cast(BinaryIO, _LimitedWriter(stored))
        with gzip.GzipFile(
            fileobj=limited, mode="wb", filename="", mtime=0, compresslevel=6
        ) as compressed:
            summary = copy_summarized(
                incoming,
                cast(BinaryIO, compressed),
                byte_limit=expected_bytes,
                role=role,
            )
        stored.flush()
        os.fsync(stored.fileno())
    if _identity(source) != before:
        raise ArchiveError("original affiliation changed during archival")
    _check_summary(summary, original)
    return _publish(output, original, summary, bindings, archive)


def adopt_archive(
    archive_path: Path,
    output: Path,
    *,
    expected_archive_sha: str,
    expected_archive_bytes: int,
    expected_source_sha: str,
    expected_bytes: int,
    expected_rows: int,
    role: str,
    schema_version: str,
    historical_bindings: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Verify/copy existing complete gzip bytes; never recompress or read original."""
    from ..certification.validation_artifacts import require_validation_runtime

    require_validation_runtime()
    original = _original(
        expected_source_sha=expected_source_sha,
        expected_bytes=expected_bytes,
        expected_rows=expected_rows,
        role=role,
        schema_version=schema_version,
    )
    bindings = _bindings(list(historical_bindings), original)
    _integer(expected_archive_bytes, MAX_ARCHIVE_BYTES)
    if digest_file(archive_path, MAX_ARCHIVE_BYTES) != (
        _sha(expected_archive_sha),
        expected_archive_bytes,
    ):
        raise ArchiveError("adopted archive checksum/size mismatch")
    before = _identity(archive_path)
    try:
        with archive_path.open("rb") as compressed:
            with gzip.GzipFile(fileobj=compressed, mode="rb") as decoded:
                summary = copy_summarized(
                    cast(BinaryIO, decoded),
                    cast(BinaryIO, _Discard()),
                    byte_limit=expected_bytes,
                    role=role,
                )
    except (OSError, EOFError, zlib.error) as error:
        raise ArchiveError("adopted gzip is corrupt or truncated") from error
    _check_summary(summary, original)
    if _identity(archive_path) != before:
        raise ArchiveError("adopted archive changed during verification")
    _new_output(output, archive_path.resolve())
    archive = output / (expected_source_sha + ".jsonl.gz")
    with archive_path.open("rb") as source, archive.open("xb") as target:
        limited = _LimitedWriter(target)
        while chunk := source.read(CHUNK):
            limited.write(chunk)
        target.flush()
        os.fsync(target.fileno())
    if _identity(archive_path) != before or digest_file(archive, MAX_ARCHIVE_BYTES) != (
        expected_archive_sha,
        expected_archive_bytes,
    ):
        raise ArchiveError("adopted compressed copy differs")
    return _publish(output, original, summary, bindings, archive)
