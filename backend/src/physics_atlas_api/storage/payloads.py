"""Isolated, bounded payload-reference pilot; not a production storage migration.

Only full provider bytes move into the local artifact abstraction. Queryable
normalized attributes, external identifiers, provenance links and scientific
state remain the caller's hot responsibility. A page reference can be shared by
many provider occurrences; each occurrence still retains its own source ID and
page locator. Recovering bytes is not scientific certification or activation.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime

from .contracts import ArtifactIntegrityError, ArtifactRef, ArtifactStore, StorageTier

PAYLOAD_REFERENCE_VERSION = "payload-reference-prototype-v1"
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
_MAX_HEADER_BYTES = 64 * 1024
_MAX_ENVELOPE_BYTES = MAX_PAYLOAD_BYTES + _MAX_HEADER_BYTES + 1
_MAX_ARCHIVE_BYTES = _MAX_ENVELOPE_BYTES + 64 * 1024
_ARTIFACT_MEDIA_TYPE = "application/vnd.physics-atlas.payload-envelope-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PayloadMetadata:
    """Original acquisition identity; not a newly fetched or certified record.

    For page payloads, ``provider_record_id`` is the source page identity; hot
    occurrence rows retain their original per-record identifiers separately.
    Preserve the original timestamp string rather than normalizing its spelling.
    """

    provider: str
    provider_record_id: str
    acquisition_id: str
    snapshot_id: str
    acquisition_scope: str
    dataset_version: str
    acquired_at: str
    status: str
    media_type: str

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, str) or not value.strip() or len(value) > 4096:
                raise ValueError(f"payload {name} must be bounded non-empty text")
        try:
            instant = datetime.fromisoformat(self.acquired_at)
        except ValueError as error:
            raise ValueError("payload acquired_at must be an ISO timestamp") from error
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("payload acquired_at must have an explicit UTC offset")


@dataclass(frozen=True)
class PayloadReference:
    """Candidate hot metadata with distinct original-payload and archive hashes."""

    version: str
    metadata: PayloadMetadata
    payload_sha256: str
    payload_size_bytes: int
    artifact: ArtifactRef


def _header(reference: PayloadReference) -> bytes:
    return json.dumps(
        {
            "version": reference.version,
            "metadata": asdict(reference.metadata),
            "payload_sha256": reference.payload_sha256,
            "payload_size_bytes": reference.payload_size_bytes,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _compress(envelope: bytes) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as stream:
        stream.write(envelope)
    return output.getvalue()


def archive_payload(
    payload: bytes, metadata: PayloadMetadata, store: ArtifactStore
) -> PayloadReference:
    """Archive exact bytes and verify recovery before exposing a hot reference.

    No parsing, whitespace normalization, field removal or acquisition occurs.
    This one-payload operation is capped at 16 MiB and changes no database rows.
    A caller must independently retain/verify the original acquisition manifest.
    """
    if not isinstance(payload, bytes) or len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("payload must be bytes no larger than 16 MiB")
    if not isinstance(metadata, PayloadMetadata):
        raise ValueError("payload requires typed acquisition metadata")
    header = json.dumps(
        {
            "version": PAYLOAD_REFERENCE_VERSION,
            "metadata": asdict(metadata),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "payload_size_bytes": len(payload),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if len(header) > _MAX_HEADER_BYTES:
        raise ValueError("payload metadata exceeds the bounded header size")
    artifact = store.put_bytes(
        _compress(header + b"\n" + payload),
        tier=StorageTier.COLD,
        media_type=_ARTIFACT_MEDIA_TYPE,
        content_encoding="gzip",
    )
    reference = PayloadReference(
        version=PAYLOAD_REFERENCE_VERSION,
        metadata=metadata,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        payload_size_bytes=len(payload),
        artifact=artifact,
    )
    # Read-after-write includes envelope/metadata checks, not just object existence.
    if recover_payload(reference, store) != payload:
        raise ArtifactIntegrityError("new payload artifact failed exact recovery")
    return reference


def recover_payload(reference: PayloadReference, store: ArtifactStore) -> bytes:
    """Fail closed on missing/corrupt bytes or a mismatched hot metadata binding.

    Both compressed and expanded reads are bounded. The envelope binds original
    payload bytes to the retained acquisition identity, but its hash is not an
    attestation of source authority or scientific correctness.
    """
    if not isinstance(reference, PayloadReference) or (
        reference.version != PAYLOAD_REFERENCE_VERSION
        or not isinstance(reference.metadata, PayloadMetadata)
        or not isinstance(reference.payload_size_bytes, int)
        or isinstance(reference.payload_size_bytes, bool)
        or not 0 <= reference.payload_size_bytes <= MAX_PAYLOAD_BYTES
        or not isinstance(reference.payload_sha256, str)
        or not _SHA256.fullmatch(reference.payload_sha256)
        or not isinstance(reference.artifact, ArtifactRef)
        or reference.artifact.tier is not StorageTier.COLD
        or reference.artifact.content_encoding != "gzip"
        or reference.artifact.media_type != _ARTIFACT_MEDIA_TYPE
        or reference.artifact.size_bytes > _MAX_ARCHIVE_BYTES
    ):
        raise ArtifactIntegrityError("unsupported or unbounded payload reference")
    expected_header = _header(reference)
    if len(expected_header) > _MAX_HEADER_BYTES:
        raise ArtifactIntegrityError("payload metadata exceeds bounded header size")
    with store.open(reference.artifact) as stream:
        compressed = stream.read(_MAX_ARCHIVE_BYTES + 1)
    if (
        len(compressed) != reference.artifact.size_bytes
        or hashlib.sha256(compressed).hexdigest() != reference.artifact.sha256
    ):
        raise ArtifactIntegrityError("payload archive checksum or size differs")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
            envelope = stream.read(_MAX_ENVELOPE_BYTES + 1)
        header, separator, payload = envelope.partition(b"\n")
        if (
            len(envelope) > _MAX_ENVELOPE_BYTES
            or not separator
            or header != expected_header
            or len(payload) != reference.payload_size_bytes
            or hashlib.sha256(payload).hexdigest() != reference.payload_sha256
        ):
            raise ValueError("payload bytes or acquisition metadata binding differs")
    except (OSError, EOFError, ValueError) as error:
        raise ArtifactIntegrityError(f"payload recovery failed: {error}") from error
    return payload
