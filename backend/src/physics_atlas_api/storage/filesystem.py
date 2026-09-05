"""Local content-addressed artifact store for staging and deterministic tests."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import BinaryIO

from .contracts import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactRef,
    ArtifactStat,
    StorageTier,
)


class FilesystemArtifactStore:
    """Immutable local store; it is not an object-storage deployment."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self._root = root.resolve()

    def put_bytes(
        self,
        payload: bytes,
        *,
        tier: StorageTier,
        media_type: str,
        content_encoding: str = "identity",
    ) -> ArtifactRef:
        if tier is StorageTier.HOT:
            raise ValueError("hot state belongs in PostgreSQL, not an artifact store")
        digest = hashlib.sha256(payload).hexdigest()
        reference = ArtifactRef(
            uri=self._uri(tier, digest),
            sha256=digest,
            size_bytes=len(payload),
            media_type=media_type,
            content_encoding=content_encoding,
            tier=tier,
        )
        destination = self.local_path(reference)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if not self.verify(reference):
                raise ArtifactIntegrityError(
                    "existing content-addressed artifact failed verification"
                )
            return reference

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=".artifact-tmp-",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, destination)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        if not self.verify(reference):
            raise ArtifactIntegrityError("new artifact failed verification")
        return reference

    def open(self, reference: ArtifactRef) -> BinaryIO:
        path = self.local_path(reference)
        if not path.is_file():
            raise ArtifactNotFoundError(f"artifact is unavailable: {reference.uri}")
        if not self.verify(reference):
            raise ArtifactIntegrityError(
                f"artifact failed verification: {reference.uri}"
            )
        return path.open("rb")

    def read_bytes(self, reference: ArtifactRef) -> bytes:
        with self.open(reference) as stream:
            return stream.read()

    def stat(self, reference: ArtifactRef) -> ArtifactStat:
        path = self.local_path(reference)
        if not path.is_file():
            raise ArtifactNotFoundError(f"artifact is unavailable: {reference.uri}")
        return ArtifactStat(reference=reference, stored_size_bytes=path.stat().st_size)

    def verify(self, reference: ArtifactRef) -> bool:
        path = self.local_path(reference)
        if not path.is_file() or path.stat().st_size != reference.size_bytes:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == reference.sha256

    def local_path(self, reference: ArtifactRef) -> Path:
        expected_uri = self._uri(reference.tier, reference.sha256)
        if reference.uri != expected_uri:
            raise ValueError("artifact URI is not canonical for this store")
        path = (
            self._root / reference.tier.value / reference.sha256[:2] / reference.sha256
        )
        resolved = path.resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError("artifact path escapes the configured store root")
        return resolved

    @staticmethod
    def _uri(tier: StorageTier, digest: str) -> str:
        return f"physics-atlas-artifact://{tier.value}/{digest[:2]}/{digest}"
