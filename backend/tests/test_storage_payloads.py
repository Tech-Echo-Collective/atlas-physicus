from __future__ import annotations

import gzip
import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO

import pytest

from physics_atlas_api.storage.contracts import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactRef,
)
from physics_atlas_api.storage.filesystem import FilesystemArtifactStore
from physics_atlas_api.storage.payloads import (
    MAX_PAYLOAD_BYTES,
    PayloadMetadata,
    archive_payload,
    recover_payload,
)


@pytest.fixture
def metadata() -> PayloadMetadata:
    return PayloadMetadata(
        provider="inspire",
        provider_record_id="page-0",
        acquisition_id="existing-week-manifest-sha",
        snapshot_id="existing-week-hep-th-page-0",
        acquisition_scope="hep-th-v1",
        dataset_version="retained-paired-week-v2",
        acquired_at="2026-09-04T16:05:51.942606Z",
        status="200",
        media_type="application/json",
    )


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b' { "count": 0, "missing": null } \r\n',
        b"\x00\xff\nraw bytes\r\n",
        '<?xml version="1.0"?><entry>\u03c6\u00e9</entry>\n'.encode(),
    ],
)
def test_payload_round_trip_preserves_exact_bytes(
    tmp_path: Path, metadata: PayloadMetadata, payload: bytes
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    reference = archive_payload(payload, metadata, store)
    assert recover_payload(reference, store) == payload
    assert reference.metadata == metadata
    assert reference.payload_sha256 == hashlib.sha256(payload).hexdigest()
    assert reference.payload_size_bytes == len(payload)
    assert reference.artifact.sha256 != reference.payload_sha256


def test_payload_json_missing_zero_and_null_are_not_reinterpreted(
    tmp_path: Path, metadata: PayloadMetadata
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    payload = b'{"zero":0,"null":null,"weights":["1/3","2/3"]}\n'
    reference = archive_payload(payload, metadata, store)
    restored = json.loads(recover_payload(reference, store))
    assert restored["zero"] == 0
    assert restored["null"] is None
    assert "absent" not in restored
    assert restored["weights"] == ["1/3", "2/3"]


def test_archive_is_deterministic_across_stores_and_input_is_unchanged(
    tmp_path: Path, metadata: PayloadMetadata
) -> None:
    payload = b"original raw provider page"
    one = archive_payload(payload, metadata, FilesystemArtifactStore(tmp_path / "one"))
    two = archive_payload(payload, metadata, FilesystemArtifactStore(tmp_path / "two"))
    assert one == two
    assert payload == b"original raw provider page"


@pytest.mark.parametrize(
    "field",
    [
        "provider",
        "provider_record_id",
        "acquisition_id",
        "snapshot_id",
        "acquisition_scope",
        "dataset_version",
        "status",
        "media_type",
        "acquired_at",
    ],
)
def test_every_hot_metadata_field_is_bound_to_cold_payload(
    tmp_path: Path, metadata: PayloadMetadata, field: str
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    reference = archive_payload(b"raw", metadata, store)
    value = "2026-09-04T16:05:52Z" if field == "acquired_at" else "altered"
    changed = replace(reference, metadata=replace(metadata, **{field: value}))
    with pytest.raises(ArtifactIntegrityError, match="metadata binding"):
        recover_payload(changed, store)


def test_wrong_original_digest_and_size_fail_closed(
    tmp_path: Path, metadata: PayloadMetadata
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    reference = archive_payload(b"raw", metadata, store)
    for changed in (
        replace(reference, payload_sha256="0" * 64),
        replace(reference, payload_size_bytes=4),
        replace(reference, version="unreviewed-version"),
        replace(reference, artifact=replace(reference.artifact, media_type="other")),
    ):
        with pytest.raises(ArtifactIntegrityError):
            recover_payload(changed, store)


def test_missing_corrupt_and_substituted_artifact_fail_closed(
    tmp_path: Path, metadata: PayloadMetadata
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    reference = archive_payload(b"raw", metadata, store)
    other = archive_payload(b"different", metadata, store)
    with pytest.raises(ArtifactIntegrityError):
        recover_payload(replace(reference, artifact=other.artifact), store)
    store.local_path(reference.artifact).write_bytes(b"corrupt")
    with pytest.raises(ArtifactIntegrityError):
        recover_payload(reference, store)
    store.local_path(reference.artifact).unlink()
    with pytest.raises(ArtifactNotFoundError):
        recover_payload(reference, store)


def test_invalid_gzip_with_valid_stored_digest_fails_closed(
    tmp_path: Path, metadata: PayloadMetadata
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    reference = archive_payload(b"raw", metadata, store)
    invalid = store.put_bytes(
        b"not gzip",
        tier=reference.artifact.tier,
        media_type=reference.artifact.media_type,
        content_encoding="gzip",
    )
    with pytest.raises(ArtifactIntegrityError, match="payload recovery failed"):
        recover_payload(replace(reference, artifact=invalid), store)


def test_gzip_expansion_is_bounded(tmp_path: Path, metadata: PayloadMetadata) -> None:
    store = FilesystemArtifactStore(tmp_path)
    reference = archive_payload(b"raw", metadata, store)
    bomb = store.put_bytes(
        gzip.compress(b"x" * (MAX_PAYLOAD_BYTES + 128 * 1024)),
        tier=reference.artifact.tier,
        media_type=reference.artifact.media_type,
        content_encoding="gzip",
    )
    with pytest.raises(ArtifactIntegrityError, match="payload recovery failed"):
        recover_payload(replace(reference, artifact=bomb), store)


def test_unverified_store_cannot_return_changed_bytes(
    tmp_path: Path, metadata: PayloadMetadata
) -> None:
    class ChangedStreamStore(FilesystemArtifactStore):
        def open(self, reference: ArtifactRef) -> BinaryIO:
            return io.BytesIO(b"wrong")

    store = FilesystemArtifactStore(tmp_path)
    reference = archive_payload(b"raw", metadata, store)
    with pytest.raises(ArtifactIntegrityError, match="archive checksum or size"):
        recover_payload(reference, ChangedStreamStore(tmp_path))
    with pytest.raises(ArtifactIntegrityError, match="archive checksum or size"):
        archive_payload(b"raw", metadata, ChangedStreamStore(tmp_path))


def test_compressed_read_is_bounded_and_oversize_reference_never_opens(
    tmp_path: Path, metadata: PayloadMetadata
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    reference = archive_payload(b"raw", metadata, store)
    read_sizes: list[int] = []

    class TrackedStream(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            assert size is not None
            read_sizes.append(size)
            return super().read(size)

    class TrackedStore(FilesystemArtifactStore):
        def open(self, reference: ArtifactRef) -> BinaryIO:
            return TrackedStream(self.local_path(reference).read_bytes())

    assert recover_payload(reference, TrackedStore(tmp_path)) == b"raw"
    assert len(read_sizes) == 1
    assert 0 < read_sizes[0] <= MAX_PAYLOAD_BYTES + 128 * 1024 + 2
    oversized = replace(
        reference,
        artifact=replace(reference.artifact, size_bytes=MAX_PAYLOAD_BYTES * 2),
    )
    with pytest.raises(ArtifactIntegrityError, match="unbounded"):
        recover_payload(oversized, TrackedStore(tmp_path))
    assert len(read_sizes) == 1


def test_bounded_input_and_timestamp_requirements(
    tmp_path: Path, metadata: PayloadMetadata
) -> None:
    with pytest.raises(ValueError, match="16 MiB"):
        archive_payload(
            b"x" * (MAX_PAYLOAD_BYTES + 1), metadata, FilesystemArtifactStore(tmp_path)
        )
    for acquired_at in ("2026-09-04", "2026-09-04T16:05:51", "invalid"):
        with pytest.raises(ValueError, match="acquired_at"):
            replace(metadata, acquired_at=acquired_at)
    with pytest.raises(ValueError, match="bounded non-empty"):
        replace(metadata, provider="")
