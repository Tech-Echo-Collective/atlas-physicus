"""Affiliation-only compatibility for immutable historical manifest paths.

The sidecar is an explicit local authority selection, not scientific evidence.
Without one, readers retain their legacy inline behavior. With one, an invalid
or unavailable selected representation is an error, never an inline fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO

from .historical_authority import resolve_historical_artifact

INDEX_VERSION = "local-artifact-authority-index-v1"
AFFILIATION_ROLES = frozenset({"affiliation-shares", "paper-time-affiliation-shares"})
_MAX_INDEX_BYTES = 256 * 1024
_MAX_ENTRIES = 64
_SHA = re.compile(r"[0-9a-f]{64}")
_ENTRY_KEYS = frozenset(
    {
        "relative_path",
        "role",
        "checksum",
        "byte_count",
        "row_count",
        "descriptor_path",
        "descriptor_sha256",
        "storage_root",
        "historical_manifest_path",
        "historical_manifest_sha256",
        "historical_recorded_path",
    }
)


class HistoricalReadError(ValueError):
    """A selected historical artifact could not be admitted for reading."""


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise HistoricalReadError("duplicate authority property")
        value[key] = item
    return value


def _lexical(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _no_symlinks(path: Path) -> None:
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise HistoricalReadError("authority path contains a symlink")


def _document(path: Path, limit: int) -> tuple[dict[str, Any], bytes]:
    _no_symlinks(path)
    try:
        before = path.stat()
        if not path.is_file() or not 0 < before.st_size <= limit:
            raise HistoricalReadError("authority metadata must be bounded regular file")
        with path.open("rb") as stream:
            body = stream.read(limit + 1)
        after = path.stat()
        if len(body) != before.st_size or (
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise HistoricalReadError("authority metadata changed while reading")
        value = json.loads(body, object_pairs_hook=_unique_pairs)
    except (OSError, json.JSONDecodeError) as error:
        raise HistoricalReadError("authority metadata is unreadable") from error
    if not isinstance(value, dict):
        raise HistoricalReadError("authority metadata must be an object")
    return value, body


def _reference(root: Path, value: object) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or Path(value).is_absolute()
        or "\\" in value
        or ":" in value
    ):
        raise HistoricalReadError("authority reference must be explicit relative path")
    path = _lexical(root / value)
    _no_symlinks(root / value)
    return path


def _entry(root: Path, relative: str) -> dict[str, Any] | None:
    index_path = root / "artifact-authority.json"
    if not os.path.lexists(index_path):
        return None
    index, _ = _document(index_path, _MAX_INDEX_BYTES)
    entries = index.get("entries")
    if (
        set(index) != {"version", "entries"}
        or index.get("version") != INDEX_VERSION
        or not isinstance(entries, list)
        or not 1 <= len(entries) <= _MAX_ENTRIES
    ):
        raise HistoricalReadError("invalid authority index")
    seen: set[str] = set()
    selected = None
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != _ENTRY_KEYS:
            raise HistoricalReadError("invalid authority entry")
        recorded = entry["relative_path"]
        if (
            not isinstance(recorded, str)
            or not recorded
            or Path(recorded).is_absolute()
            or any(part in ("", ".", "..") for part in recorded.split("/"))
            or "\\" in recorded
            or recorded in seen
            or not isinstance(entry["historical_recorded_path"], str)
            or not Path(entry["historical_recorded_path"]).is_absolute()
            or str(_lexical(Path(entry["historical_recorded_path"])))
            != entry["historical_recorded_path"]
            or not isinstance(entry["role"], str)
            or entry["role"] not in AFFILIATION_ROLES
            or any(
                not isinstance(entry[key], str) or _SHA.fullmatch(entry[key]) is None
                for key in (
                    "checksum",
                    "descriptor_sha256",
                    "historical_manifest_sha256",
                )
            )
            or any(
                type(entry[key]) is not int or entry[key] <= 0
                for key in ("byte_count", "row_count")
            )
        ):
            raise HistoricalReadError("invalid or ambiguous authority binding")
        for key in ("descriptor_path", "storage_root", "historical_manifest_path"):
            _reference(root, entry[key])
        seen.add(recorded)
        if recorded == relative:
            selected = entry
    if selected is None:
        raise HistoricalReadError("authority index does not bind requested artifact")
    return selected


@contextmanager
def open_artifact(
    path: Path,
    *,
    role: str,
    checksum: str,
    byte_count: int | None,
    row_count: int | None,
    bundle_root: Path,
) -> Iterator[BinaryIO]:
    """Open an unchanged inline input or a fully verified archive-owned temp file.

    Only affiliation roles consult the explicit per-bundle index. Scientific parsers
    and provenance continue using the caller's original manifest entry and path.
    """
    if role not in AFFILIATION_ROLES:
        with path.open("rb") as stream:
            yield stream
        return
    root, original = _lexical(bundle_root), _lexical(path)
    try:
        relative = original.relative_to(root).as_posix()
    except ValueError as error:
        raise HistoricalReadError("historical path leaves bundle root") from error
    _no_symlinks(root)
    entry = _entry(root, relative)
    if entry is None:
        _no_symlinks(path)
        with path.open("rb") as stream:
            yield stream
        return
    if type(byte_count) is not int or type(row_count) is not int:
        raise HistoricalReadError(
            "historical request requires exact integer dimensions"
        )
    if any(
        entry[key] != expected
        for key, expected in (
            ("role", role),
            ("checksum", checksum),
            ("byte_count", byte_count),
            ("row_count", row_count),
        )
    ):
        raise HistoricalReadError("request differs from exact authority binding")
    historical_recorded_path = Path(entry["historical_recorded_path"])
    descriptor_path = _reference(root, entry["descriptor_path"])
    descriptor, body = _document(descriptor_path, 64 * 1024)
    artifact = descriptor.get("artifact")
    if (
        hashlib.sha256(body).hexdigest() != entry["descriptor_sha256"]
        or not isinstance(artifact, dict)
        or artifact.get("type") != role
        or any(
            artifact.get(key) != expected
            for key, expected in (
                ("sha256", checksum),
                ("bytes", byte_count),
                ("rows", row_count),
            )
        )
    ):
        raise HistoricalReadError("descriptor differs from historical request")
    with resolve_historical_artifact(
        descriptor_path,
        expected_descriptor_sha256=entry["descriptor_sha256"],
        storage_root=_reference(root, entry["storage_root"]),
        certification_manifest=_reference(root, entry["historical_manifest_path"]),
        expected_certification_manifest_sha256=entry["historical_manifest_sha256"],
        historical_recorded_path=historical_recorded_path,
    ) as resolved:
        with resolved.path.open("rb") as stream:
            yield stream


def read_artifact(root: Path, entry: dict[str, Any]) -> bytes:
    """Small existing comparison callers; no new parsing or scientific logic."""
    with open_artifact(
        root / entry["path"],
        role=entry["role"],
        checksum=entry["checksum"],
        byte_count=entry["byte_count"],
        row_count=entry["row_count"],
        bundle_root=root,
    ) as stream:
        return stream.read()
