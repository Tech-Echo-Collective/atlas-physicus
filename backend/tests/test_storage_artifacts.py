import hashlib
import os
from pathlib import Path

import pytest

from physics_atlas_api.storage import (
    ArtifactIntegrityError,
    ArtifactRef,
    FilesystemArtifactStore,
    StorageTier,
)


def test_filesystem_store_is_content_addressed_and_reproducible(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path / "artifacts")
    payload = b'{"provider":"inspire","records":[]}'

    first = store.put_bytes(
        payload,
        tier=StorageTier.COLD,
        media_type="application/json",
    )
    second = store.put_bytes(
        payload,
        tier=StorageTier.COLD,
        media_type="application/json",
    )

    assert first == second
    assert first.sha256 == hashlib.sha256(payload).hexdigest()
    assert first.size_bytes == len(payload)
    assert store.read_bytes(first) == payload
    assert store.stat(first).stored_size_bytes == len(payload)
    assert store.verify(first) is True
    assert len(list((tmp_path / "artifacts").rglob(first.sha256))) == 1


def test_filesystem_store_detects_corruption(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path / "artifacts")
    reference = store.put_bytes(
        b"certification evidence",
        tier=StorageTier.WARM,
        media_type="application/octet-stream",
    )
    store.local_path(reference).write_bytes(b"corrupt")

    assert store.verify(reference) is False
    with pytest.raises(ArtifactIntegrityError):
        store.read_bytes(reference)


def test_artifact_reference_rejects_traversal_and_mismatched_digest() -> None:
    digest = "a" * 64
    with pytest.raises(ValueError, match="canonical content-addressed URI"):
        ArtifactRef(
            uri=f"physics-atlas-artifact://cold/../{digest}",
            sha256=digest,
            size_bytes=1,
            media_type="application/json",
            content_encoding="identity",
            tier=StorageTier.COLD,
        )
    with pytest.raises(ValueError, match="must match sha256"):
        ArtifactRef(
            uri=f"physics-atlas-artifact://cold/aa/{'b' * 64}",
            sha256=digest,
            size_bytes=1,
            media_type="application/json",
            content_encoding="identity",
            tier=StorageTier.COLD,
        )


def test_filesystem_store_cleans_temporary_file_after_atomic_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FilesystemArtifactStore(tmp_path / "artifacts")

    def fail_replace(source: os.PathLike[str], destination: os.PathLike[str]) -> None:
        del source, destination
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        store.put_bytes(
            b"payload",
            tier=StorageTier.COLD,
            media_type="application/octet-stream",
        )

    assert not list((tmp_path / "artifacts").rglob(".artifact-tmp-*"))


def test_artifact_store_refuses_hot_postgresql_state(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path / "artifacts")

    with pytest.raises(ValueError, match="PostgreSQL"):
        store.put_bytes(
            b"canonical entity",
            tier=StorageTier.HOT,
            media_type="application/octet-stream",
        )
