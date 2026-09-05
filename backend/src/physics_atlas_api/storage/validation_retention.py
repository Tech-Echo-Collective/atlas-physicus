"""Cumulative admission for bounded validation evidence, not a disk quota.

All physical representations count, including archives, duplicates, old versions
and REVIEW files. Classification never implies deletion or free bytes. The
inventory is an operator-reviewed scope assertion; hashes authenticate that
assertion, not its completeness outside the explicitly managed root. Callers
must serialize proof jobs, inventory all retained outputs before another run,
and enforce their reservation while writing. This module does not run scientific
processing or change existing per-trace limits or certification policy.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from ..certification.validation_artifacts import (
    require_validation_runtime,
    validation_paper_limit,
)

VALIDATION_RETENTION_VERSION = "validation-retention-budget-v1"
VALIDATION_INVENTORY_VERSION = "validation-retention-inventory-v1"
MAX_PERSISTENT_VALIDATION_BYTES = 1_073_741_824  # 1 GiB within PA-048, not extra.
_SHA256 = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")


class ValidationRetentionError(ValueError):
    """Missing, inconsistent or over-budget operational evidence fails closed."""


class RetentionClass(StrEnum):
    KEEP = "KEEP"
    COMPRESS_ARCHIVE = "COMPRESS/ARCHIVE"
    REGENERABLE = "REGENERABLE"
    RETIRE_CANDIDATE = "RETIRE_CANDIDATE"
    REVIEW = "REVIEW"


def _integer(name: str, value: int, *, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValidationRetentionError(f"{name} must be an integer >= {minimum}")


def _digest(name: str, value: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValidationRetentionError(f"{name} must be a lowercase SHA-256")


def _identifier(name: str, value: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValidationRetentionError(f"{name} must be a safe nonempty identifier")


def _absolute_path(value: str) -> Path:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValidationRetentionError("storage reference must be an absolute path")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ValidationRetentionError("storage reference must be a canonical path")
    return path


@dataclass(frozen=True)
class RetainedValidationFile:
    """One actual file occurrence, never a deduplicated logical-artifact count."""

    storage_reference: str
    size_bytes: int
    sha256: str
    classification: RetentionClass
    pipeline_version: str
    sample_id: str

    def __post_init__(self) -> None:
        _absolute_path(self.storage_reference)
        _integer("size_bytes", self.size_bytes)
        _digest("file sha256", self.sha256)
        if not isinstance(self.classification, RetentionClass):
            raise ValidationRetentionError("unknown retention classification")
        _identifier("pipeline_version", self.pipeline_version)
        _identifier("sample_id", self.sample_id)


@dataclass(frozen=True)
class ValidationRetentionInventory:
    """Pinned, complete inventory of retained validation across all versions.

    managed_root is the dedicated location for future version-level proof jobs.
    Legacy scattered files must be explicitly included in files. Measured
    metadata_bytes counts the inventory and its proof metadata, avoiding a
    self-hashing manifest. These bytes are not an unmeasured savings allowance.
    """

    scope_id: str
    measured_at: str
    managed_root: str
    files: tuple[RetainedValidationFile, ...]
    metadata_bytes: int
    total_bytes: int
    complete: bool
    version: str = VALIDATION_INVENTORY_VERSION

    def __post_init__(self) -> None:
        if self.version != VALIDATION_INVENTORY_VERSION:
            raise ValidationRetentionError("unsupported inventory version")
        _identifier("scope_id", self.scope_id)
        _absolute_path(self.managed_root)
        try:
            measured = datetime.fromisoformat(self.measured_at)
            if measured.tzinfo is None or measured.utcoffset() is None:
                raise ValueError("timezone required")
        except (TypeError, ValueError):
            raise ValidationRetentionError(
                "invalid inventory measurement time"
            ) from None
        if type(self.files) is not tuple or any(
            not isinstance(item, RetainedValidationFile) for item in self.files
        ):
            raise ValidationRetentionError("inventory requires immutable file entries")
        paths = [item.storage_reference for item in self.files]
        if len(set(paths)) != len(paths):
            raise ValidationRetentionError("duplicate physical path in inventory")
        _integer("metadata_bytes", self.metadata_bytes)
        _integer("total_bytes", self.total_bytes)
        if self.total_bytes != self.metadata_bytes + sum(
            item.size_bytes for item in self.files
        ):
            raise ValidationRetentionError("inventory total does not match all bytes")
        if self.complete is not True:
            raise ValidationRetentionError("inventory completeness is not established")

    def canonical_payload(self) -> bytes:
        document = asdict(self)
        document["files"] = sorted(
            document["files"], key=lambda item: item["storage_reference"]
        )
        return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_payload()).hexdigest()


@dataclass(frozen=True)
class ValidationRetentionReservation:
    """Admission result only: not authenticated capacity or an OS write quota."""

    policy_version: str
    sample_id: str
    sample_manifest_sha256: str
    paper_count: int
    pipeline_version: str
    proof_manifest_sha256: str
    inventory_sha256: str
    output_reference: str
    retained_bytes: int
    reserved_new_bytes: int
    projected_bytes: int
    limit_bytes: int


def require_validation_retention_budget(
    inventory: ValidationRetentionInventory | None,
    *,
    expected_inventory_sha256: str,
    sample_id: str,
    expected_sample_id: str,
    sample_manifest_sha256: str,
    expected_sample_manifest_sha256: str,
    paper_count: int,
    pipeline_version: str,
    proof_manifest_sha256: str,
    reserved_new_bytes: int,
    limit_bytes: int = MAX_PERSISTENT_VALIDATION_BYTES,
) -> ValidationRetentionReservation:
    """Refuse unless measured retained bytes plus the new reservation fit v1.

    The reservation must include every planned persistent file, metadata,
    archive and extra copy. The default cap can be tightened, never raised.
    Sample content is validated by its existing sample verifier before this call;
    exact expected bindings prevent accidental sample/version substitution here.
    """

    require_validation_runtime()
    if not isinstance(inventory, ValidationRetentionInventory):
        raise ValidationRetentionError("complete retention inventory is required")
    _digest("expected inventory sha256", expected_inventory_sha256)
    if inventory.sha256 != expected_inventory_sha256:
        raise ValidationRetentionError("inventory checksum mismatch")
    _identifier("sample_id", sample_id)
    _identifier("expected_sample_id", expected_sample_id)
    _digest("sample manifest sha256", sample_manifest_sha256)
    _digest("expected sample manifest sha256", expected_sample_manifest_sha256)
    if (
        sample_id != expected_sample_id
        or sample_manifest_sha256 != expected_sample_manifest_sha256
    ):
        raise ValidationRetentionError("sample identity or manifest checksum mismatch")
    validation_paper_limit(paper_count)
    _identifier("pipeline_version", pipeline_version)
    _digest("proof manifest sha256", proof_manifest_sha256)
    _integer("reserved_new_bytes", reserved_new_bytes, minimum=1)
    _integer("limit_bytes", limit_bytes, minimum=1)
    if limit_bytes > MAX_PERSISTENT_VALIDATION_BYTES:
        raise ValidationRetentionError("the v1 retention cap cannot be raised")
    projected = inventory.total_bytes + reserved_new_bytes
    if projected > limit_bytes:
        raise ValidationRetentionError(
            "cumulative validation retention budget exceeded: "
            f"{inventory.total_bytes} + {reserved_new_bytes} > {limit_bytes}"
        )
    output = (
        Path(inventory.managed_root)
        / sample_id
        / pipeline_version
        / proof_manifest_sha256
    )
    return ValidationRetentionReservation(
        policy_version=VALIDATION_RETENTION_VERSION,
        sample_id=sample_id,
        sample_manifest_sha256=sample_manifest_sha256,
        paper_count=paper_count,
        pipeline_version=pipeline_version,
        proof_manifest_sha256=proof_manifest_sha256,
        inventory_sha256=inventory.sha256,
        output_reference=str(output),
        retained_bytes=inventory.total_bytes,
        reserved_new_bytes=reserved_new_bytes,
        projected_bytes=projected,
        limit_bytes=limit_bytes,
    )


def verify_validation_retention_files(
    inventory: ValidationRetentionInventory, *, verify_hashes: bool = False
) -> None:
    """Read-only freshness check; never treats a missing file as reclaimed space.

    Unlisted managed files fail closed. Legacy inventory completeness and counted
    metadata remain operator-reviewed outside this dedicated root. Default size
    accounting does not open payloads. Optional integrity checks hash one file at
    a time in bounded memory; they never parse archives or scientific records.
    """

    require_validation_runtime()
    listed = {Path(item.storage_reference) for item in inventory.files}
    root = _absolute_path(inventory.managed_root)
    try:
        if root.is_symlink() or root.resolve() != root:
            raise ValidationRetentionError("invalid managed validation root")
        if root.exists():
            if not root.is_dir():
                raise ValidationRetentionError("invalid managed validation root")
            for path in root.rglob("*"):
                if path.is_symlink() or (not path.is_dir() and path not in listed):
                    raise ValidationRetentionError("unlisted managed validation file")
        for item in inventory.files:
            path = Path(item.storage_reference)
            if path.is_symlink() or not path.is_file() or path.resolve() != path:
                raise ValidationRetentionError("missing or unsafe retained file")
            before = path.stat()
            if before.st_size != item.size_bytes:
                raise ValidationRetentionError("retained file size mismatch")
            digest = hashlib.sha256()
            if verify_hashes:
                with path.open("rb") as stream:
                    while block := stream.read(1024 * 1024):
                        digest.update(block)
            after = path.stat()
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ) or (verify_hashes and digest.hexdigest() != item.sha256):
                raise ValidationRetentionError(
                    "retained file checksum or identity changed"
                )
    except OSError:
        raise ValidationRetentionError(
            "retained validation storage unavailable"
        ) from None


def check_validation_reservation_output(
    reservation: ValidationRetentionReservation, *, bytes_to_retain: int
) -> None:
    """Writer check before persistence; all files/metadata share one reservation.

    This deliberately does not publish, delete, truncate or mutate scientific
    artifacts. Callers must use create-exclusive publication and a single writer.
    """

    _integer("bytes_to_retain", bytes_to_retain)
    if bytes_to_retain > reservation.reserved_new_bytes:
        raise ValidationRetentionError("new validation output exceeds its reservation")
    path = Path(reservation.output_reference)
    if path.exists() or path.is_symlink():
        raise ValidationRetentionError("immutable version-level proof already exists")


def preflight_validation_retention(
    inventory: ValidationRetentionInventory,
    reservation: ValidationRetentionReservation,
    *,
    verify_hashes: bool = False,
) -> None:
    """Recheck one pinned admission before an exclusively published proof job.

    A fresh reviewed inventory and serialized jobs are required. This is a
    metadata/accounting admission boundary, not an OS quota or archive-integrity
    proof; callers separately verify the inputs used by their bounded pilots.
    """

    require_validation_runtime()
    if inventory.sha256 != reservation.inventory_sha256:
        raise ValidationRetentionError("reservation inventory checksum mismatch")
    expected = require_validation_retention_budget(
        inventory,
        expected_inventory_sha256=reservation.inventory_sha256,
        sample_id=reservation.sample_id,
        expected_sample_id=reservation.sample_id,
        sample_manifest_sha256=reservation.sample_manifest_sha256,
        expected_sample_manifest_sha256=reservation.sample_manifest_sha256,
        paper_count=reservation.paper_count,
        pipeline_version=reservation.pipeline_version,
        proof_manifest_sha256=reservation.proof_manifest_sha256,
        reserved_new_bytes=reservation.reserved_new_bytes,
        limit_bytes=reservation.limit_bytes,
    )
    if expected != reservation:
        raise ValidationRetentionError("inconsistent validation reservation")
    verify_validation_retention_files(inventory, verify_hashes=verify_hashes)
    check_validation_reservation_output(reservation, bytes_to_retain=0)
