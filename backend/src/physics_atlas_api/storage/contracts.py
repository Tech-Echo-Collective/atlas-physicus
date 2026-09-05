"""Provider-independent contracts for immutable evidence artifact storage."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import BinaryIO, Protocol, runtime_checkable

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_URI_PATTERN = re.compile(
    r"^physics-atlas-artifact://(?P<tier>warm|cold)/"
    r"(?P<prefix>[0-9a-f]{2})/(?P<digest>[0-9a-f]{64})$"
)


class StorageTier(StrEnum):
    """Durability tier; PostgreSQL is hot and artifact stores are warm/cold."""

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class ArtifactStoreError(RuntimeError):
    """Base error for immutable artifact storage."""


class ArtifactNotFoundError(ArtifactStoreError):
    """The referenced immutable artifact is unavailable."""


class ArtifactIntegrityError(ArtifactStoreError):
    """Stored bytes do not match their content-addressed reference."""


@dataclass(frozen=True)
class ArtifactRef:
    """Portable reference to one immutable, content-addressed artifact."""

    uri: str
    sha256: str
    size_bytes: int
    media_type: str
    content_encoding: str
    tier: StorageTier

    def __post_init__(self) -> None:
        match = _ARTIFACT_URI_PATTERN.fullmatch(self.uri)
        if match is None:
            raise ValueError("artifact URI must be a canonical content-addressed URI")
        if not _SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("artifact sha256 must be 64 lowercase hexadecimal digits")
        if match.group("digest") != self.sha256:
            raise ValueError("artifact URI digest must match sha256")
        if match.group("prefix") != self.sha256[:2]:
            raise ValueError("artifact URI prefix must match sha256")
        if match.group("tier") != self.tier.value or self.tier is StorageTier.HOT:
            raise ValueError("artifact references must use the warm or cold tier")
        if (
            not isinstance(self.size_bytes, int)
            or isinstance(self.size_bytes, bool)
            or self.size_bytes < 0
        ):
            raise ValueError("artifact size_bytes must be a nonnegative integer")
        if not self.media_type.strip():
            raise ValueError("artifact media_type must be non-empty")
        if self.content_encoding not in {"identity", "gzip", "zstd"}:
            raise ValueError("unsupported artifact content encoding")


@dataclass(frozen=True)
class ArtifactStat:
    reference: ArtifactRef
    stored_size_bytes: int


@runtime_checkable
class ArtifactStore(Protocol):
    """Minimal immutable store used outside the PostgreSQL hot state."""

    def put_bytes(
        self,
        payload: bytes,
        *,
        tier: StorageTier,
        media_type: str,
        content_encoding: str = "identity",
    ) -> ArtifactRef: ...

    def open(self, reference: ArtifactRef) -> BinaryIO: ...

    def stat(self, reference: ArtifactRef) -> ArtifactStat: ...

    def verify(self, reference: ArtifactRef) -> bool: ...
