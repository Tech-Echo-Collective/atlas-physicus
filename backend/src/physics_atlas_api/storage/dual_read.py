"""Explicit, staging-only payload selection before the existing scientific path.

This module neither connects to a database nor parses/certifies evidence. The
caller persists a verified candidate and checkpoint in one transaction. Retained
inline bytes are deliberately kept for rollback, never used as an implicit
fallback when a reference read fails. Errors block processing, not convert lost
storage into missing scientific evidence or a certification decision.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from enum import StrEnum

from .contracts import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactStore,
    ArtifactStoreError,
)
from .payloads import (
    MAX_PAYLOAD_BYTES,
    PAYLOAD_REFERENCE_VERSION,
    PayloadMetadata,
    PayloadReference,
    archive_payload,
    recover_payload,
)

STAGING_DUAL_READ_VERSION = "staging-payload-dual-read-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PayloadMode(StrEnum):
    INLINE = "inline"
    REFERENCE = "reference"


class PayloadFailureCode(StrEnum):
    INVALID_STATE = "invalid_state"
    INVALID_REFERENCE = "invalid_reference"
    MISSING_ARTIFACT = "missing_artifact"
    INTEGRITY_FAILURE = "integrity_failure"
    ARCHIVE_UNAVAILABLE = "archive_unavailable"
    INTERRUPTED_WRITE = "interrupted_write"


class PayloadAccessError(ArtifactStoreError):
    """Operational failure before parsing; never a scientific evidence state."""

    status = "blocked"

    def __init__(self, code: PayloadFailureCode, operation: str, detail: str) -> None:
        self.code = code
        self.operation = operation
        super().__init__(f"{operation} blocked ({code.value}): {detail}")


@dataclass(frozen=True)
class StagingPayloadState:
    """Hot selection and acquisition binding, with rollback bytes retained.

    ``source_digest`` binds version, metadata and original payload digest/size;
    it is integrity evidence, not a signature of provider or reviewer authority.
    The original acquisition manifest must still be independently verified.
    """

    version: str
    mode: PayloadMode
    metadata: PayloadMetadata
    payload_sha256: str
    payload_size_bytes: int
    source_digest: str
    inline_payload: bytes | None
    reference: PayloadReference | None = None


def _source_digest(
    metadata: PayloadMetadata, payload_sha256: str, payload_size_bytes: int
) -> str:
    binding = {
        "version": STAGING_DUAL_READ_VERSION,
        "metadata": asdict(metadata),
        "payload_sha256": payload_sha256,
        "payload_size_bytes": payload_size_bytes,
    }
    return hashlib.sha256(
        json.dumps(
            binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def _validate_state(state: StagingPayloadState, operation: str) -> None:
    if not isinstance(state, StagingPayloadState) or (
        state.version != STAGING_DUAL_READ_VERSION
        or not isinstance(state.mode, PayloadMode)
        or not isinstance(state.metadata, PayloadMetadata)
        or not isinstance(state.payload_sha256, str)
        or not _SHA256.fullmatch(state.payload_sha256)
        or not isinstance(state.payload_size_bytes, int)
        or isinstance(state.payload_size_bytes, bool)
        or not 0 <= state.payload_size_bytes <= MAX_PAYLOAD_BYTES
        or not isinstance(state.source_digest, str)
        or not _SHA256.fullmatch(state.source_digest)
    ):
        raise PayloadAccessError(
            PayloadFailureCode.INVALID_STATE, operation, "invalid staging selection"
        )
    if state.source_digest != _source_digest(
        state.metadata, state.payload_sha256, state.payload_size_bytes
    ):
        raise PayloadAccessError(
            PayloadFailureCode.INTEGRITY_FAILURE,
            operation,
            "acquisition/payload binding differs",
        )


def _inline_bytes(state: StagingPayloadState, operation: str) -> bytes:
    _validate_state(state, operation)
    payload = state.inline_payload
    if (
        not isinstance(payload, bytes)
        or len(payload) != state.payload_size_bytes
        or hashlib.sha256(payload).hexdigest() != state.payload_sha256
    ):
        raise PayloadAccessError(
            PayloadFailureCode.INTEGRITY_FAILURE,
            operation,
            "retained inline payload is missing or differs",
        )
    return payload


def _storage_failure(error: Exception, operation: str) -> PayloadAccessError:
    if isinstance(error, ArtifactNotFoundError):
        code = PayloadFailureCode.MISSING_ARTIFACT
    elif isinstance(error, ArtifactIntegrityError):
        code = PayloadFailureCode.INTEGRITY_FAILURE
    elif isinstance(error, ValueError):
        code = PayloadFailureCode.INVALID_REFERENCE
    elif isinstance(error, InterruptedError) and operation == "prepare":
        code = PayloadFailureCode.INTERRUPTED_WRITE
    else:
        code = PayloadFailureCode.ARCHIVE_UNAVAILABLE
    return PayloadAccessError(code, operation, str(error))


def new_inline_state(payload: bytes, metadata: PayloadMetadata) -> StagingPayloadState:
    """Bind existing bytes without acquisition, parsing or external writes."""
    if not isinstance(metadata, PayloadMetadata) or (
        not isinstance(payload, bytes) or len(payload) > MAX_PAYLOAD_BYTES
    ):
        raise PayloadAccessError(
            PayloadFailureCode.INVALID_STATE,
            "prepare",
            "typed metadata and at most 16 MiB of bytes required",
        )
    digest = hashlib.sha256(payload).hexdigest()
    return StagingPayloadState(
        version=STAGING_DUAL_READ_VERSION,
        mode=PayloadMode.INLINE,
        metadata=metadata,
        payload_sha256=digest,
        payload_size_bytes=len(payload),
        source_digest=_source_digest(metadata, digest, len(payload)),
        inline_payload=payload,
    )


def read_payload(
    state: StagingPayloadState, store: ArtifactStore | None = None
) -> bytes:
    """Return verified bytes for one explicitly selected path, with no fallback."""
    _validate_state(state, "read")
    if state.mode is PayloadMode.INLINE:
        return _inline_bytes(state, "read")
    reference = state.reference
    if not isinstance(reference, PayloadReference) or (
        reference.version != PAYLOAD_REFERENCE_VERSION
    ):
        raise PayloadAccessError(
            PayloadFailureCode.INVALID_REFERENCE, "read", "reference is invalid"
        )
    if (
        reference.metadata != state.metadata
        or reference.payload_sha256 != state.payload_sha256
        or reference.payload_size_bytes != state.payload_size_bytes
    ):
        raise PayloadAccessError(
            PayloadFailureCode.INTEGRITY_FAILURE,
            "read",
            "reference belongs to different source metadata or bytes",
        )
    if store is None:
        raise PayloadAccessError(
            PayloadFailureCode.ARCHIVE_UNAVAILABLE,
            "read",
            "reference mode requires an archive",
        )
    try:
        return recover_payload(reference, store)
    except (ArtifactStoreError, OSError, ValueError) as error:
        raise _storage_failure(error, "read") from error


def prepare_reference(
    state: StagingPayloadState, store: ArtifactStore
) -> StagingPayloadState:
    """Return a new selection only after complete write and exact read-back.

    No input state or checkpoint is mutated. An interrupted write may leave an
    unreferenced archive, but cannot return a candidate that advances source
    state. Database atomicity and checkpoint ownership remain the caller's job.
    """
    payload = _inline_bytes(state, "prepare")
    if state.mode is not PayloadMode.INLINE:
        raise PayloadAccessError(
            PayloadFailureCode.INVALID_STATE,
            "prepare",
            "explicit inline selection required before promotion",
        )
    try:
        reference = archive_payload(payload, state.metadata, store)
    except (ArtifactStoreError, OSError, ValueError) as error:
        raise _storage_failure(error, "prepare") from error
    return replace(state, mode=PayloadMode.REFERENCE, reference=reference)


def rollback_to_inline(state: StagingPayloadState) -> StagingPayloadState:
    """Deliberately reselect verified inline bytes, without archive/provider I/O."""
    _inline_bytes(state, "rollback")
    return replace(state, mode=PayloadMode.INLINE)
