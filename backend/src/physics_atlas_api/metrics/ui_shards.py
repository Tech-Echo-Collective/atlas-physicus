"""Bounded immutable transport of existing UI relationships, not new evidence.

Only compressed final assets and exact lookup indexes accumulate. The source
projection streams one paper's already validated relationships at a time; no
expanded full-corpus relationship document or duplicated profile is produced.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

from .. import schemas
from ..certification import CertificationError

if TYPE_CHECKING:
    from .dataset import AtlasDatasetEntities

UI_SHARDS_VERSION = "atlas-ui-shards-v1"
MAX_UI_SHARD_BYTES = 4 * 1024 * 1024
MAX_UI_INDEX_BYTES = 8 * 1024 * 1024
MAX_UI_SHARDS = 512
UIKind = Literal["authorships", "affiliations", "externalResources"]
UIRecord = schemas.AuthorshipOut | schemas.AffiliationOut | schemas.ExternalResourceOut
KINDS: tuple[UIKind, ...] = ("authorships", "affiliations", "externalResources")
MODELS: dict[str, type[schemas.ApiModel]] = {
    "authorships": schemas.AuthorshipOut,
    "affiliations": schemas.AffiliationOut,
    "externalResources": schemas.ExternalResourceOut,
}


def _encode(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _compressed(path: str, decoded: bytes) -> tuple[dict[str, Any], bytes]:
    content = gzip.compress(decoded, compresslevel=6, mtime=0)
    return {
        "path": path,
        "encoding": "gzip",
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "decodedSha256": hashlib.sha256(decoded).hexdigest(),
        "decodedBytes": len(decoded),
    }, content


class UIRelationshipSink(Protocol):
    def add(self, kind: UIKind, record: UIRecord) -> None: ...

    @property
    def record_counts(self) -> dict[str, int]: ...


class _Index:
    def __init__(self) -> None:
        self.ids: dict[str, set[str]] = {kind: set() for kind in KINDS}
        self.maps: dict[str, dict[str, set[str]]] = {
            name: defaultdict(set)
            for name in (
                "paperAuthorshipShards",
                "researcherPaperIds",
                "researcherAffiliationShards",
                "institutionAffiliationShards",
                "entityResourceShards",
            )
        }
        self.author_counts: Counter[str] = Counter()
        self.authorship_keys: set[tuple[str, str]] = set()
        self.affiliation_keys: set[tuple[str, str]] = set()
        self.referenced: dict[str, set[str]] = defaultdict(set)

    def add(self, kind: UIKind, row: dict[str, Any], shard_id: str) -> None:
        identity = row["id"]
        if identity in self.ids[kind]:
            raise CertificationError("duplicate UI relationship identity")
        self.ids[kind].add(identity)
        if kind == "authorships":
            paper, researcher = row["paperId"], row["researcherId"]
            pair = paper, researcher
            if pair in self.authorship_keys:
                raise CertificationError("duplicate UI paper/researcher relationship")
            self.authorship_keys.add(pair)
            self.maps["paperAuthorshipShards"][paper].add(shard_id)
            self.maps["researcherPaperIds"][researcher].add(paper)
            self.author_counts[paper] += 1
            self.referenced["paper"].add(paper)
            self.referenced["researcher"].add(researcher)
        elif kind == "affiliations":
            researcher, institution = row["researcherId"], row["institutionId"]
            self.maps["researcherAffiliationShards"][researcher].add(shard_id)
            self.maps["institutionAffiliationShards"][institution].add(shard_id)
            self.referenced["researcher"].add(researcher)
            self.referenced["institution"].add(institution)
            if row.get("paperId"):
                self.affiliation_keys.add((row["paperId"], researcher))
                self.referenced["paper"].add(row["paperId"])
            if row.get("researchGroupId"):
                self.referenced["research-group"].add(row["researchGroupId"])
        else:
            entity_type, entity_id = row["entityType"], row["entityId"]
            self.maps["entityResourceShards"][f"{entity_type}:{entity_id}"].add(
                shard_id
            )
            self.referenced[entity_type].add(entity_id)

    def document(
        self, core: AtlasDatasetEntities, dataset_version: str, shard_ids: list[str]
    ) -> dict[str, Any]:
        catalogs = {
            "paper": {row.id for row in core.papers},
            "researcher": {row.id for row in core.researchers},
            "institution": {row.id for row in core.institutions},
            "research-group": {row.id for row in core.research_groups},
        }
        if (
            any(
                not identities <= catalogs.get(kind, set())
                for kind, identities in self.referenced.items()
            )
            or not self.affiliation_keys <= self.authorship_keys
        ):
            raise CertificationError(
                "UI shard relationship has no exact core/author link"
            )
        paper_ids = sorted(catalogs["paper"])
        paper_offsets = {key: index for index, key in enumerate(paper_ids)}
        shard_offsets = {key: index for index, key in enumerate(shard_ids)}
        return {
            "version": UI_SHARDS_VERSION,
            "datasetVersion": dataset_version,
            "paperIds": paper_ids,
            "shardIds": shard_ids,
            **{
                name: {
                    key: [
                        (
                            paper_offsets
                            if name == "researcherPaperIds"
                            else shard_offsets
                        )[item]
                        for item in sorted(value)
                    ]
                    for key, value in sorted(mapping.items())
                }
                for name, mapping in self.maps.items()
            },
            # This is the exact displayed known-authorship count, not a claim
            # that a paper with zero supported identities has no source authors.
            "paperAuthorCounts": {
                key: self.author_counts[key] for key in sorted(catalogs["paper"])
            },
        }


@dataclass(frozen=True)
class UIShardExport:
    metadata: dict[str, Any]
    assets: tuple[tuple[str, str, bytes], ...]
    dataset_version: str

    def validate(self, core: AtlasDatasetEntities) -> None:
        """Verify complete index/record closure one bounded shard at a time."""
        if core.authorships or core.affiliations or core.external_resources:
            raise CertificationError(
                "UI relationships cannot be both inline and sharded"
            )
        if self.metadata.get("version") != UI_SHARDS_VERSION:
            raise CertificationError("unsupported UI shard version")
        descriptors = self.metadata["shards"]
        if len(descriptors) > MAX_UI_SHARDS:
            raise CertificationError("too many UI shard assets")
        assets = {path: content for _, path, content in self.assets}
        expected_paths = {item["path"] for item in descriptors}
        expected_paths.add(self.metadata["index"]["path"])
        if len(assets) != len(self.assets) or set(assets) != expected_paths:
            raise CertificationError("UI shard asset inventory is not exact")
        index = _Index()
        ids: set[str] = set()
        for descriptor in descriptors:
            kind, identity = descriptor["kind"], descriptor["id"]
            if kind not in KINDS or identity in ids:
                raise CertificationError("UI shard identity/kind is invalid")
            ids.add(identity)
            document = _read_asset(descriptor, assets, MAX_UI_SHARD_BYTES)
            if (
                document.get("version") != UI_SHARDS_VERSION
                or document.get("datasetVersion") != self.dataset_version
                or document.get("kind") != kind
                or descriptor["recordCount"] <= 0
                or len(document["records"]) != descriptor["recordCount"]
            ):
                raise CertificationError("UI shard source/count differs")
            for row in document["records"]:
                _validate_row(kind, row)
                index.add(kind, row, identity)
        expected = index.document(core, self.dataset_version, sorted(ids))
        if _read_asset(self.metadata["index"], assets, MAX_UI_INDEX_BYTES) != expected:
            raise CertificationError(
                "UI shard lookup index omits or substitutes records"
            )
        if self.metadata["recordCounts"] != {
            kind: len(index.ids[kind]) for kind in KINDS
        }:
            raise CertificationError("UI shard total counts differ")


def _read_asset(
    descriptor: dict[str, Any], assets: dict[str, bytes], maximum: int
) -> Any:
    path = descriptor["path"]
    if (
        not path.startswith("ui-")
        or not path.endswith(".json.gz")
        or "/" in path
        or "\\" in path
        or descriptor["encoding"] != "gzip"
        or not 0 < descriptor["decodedBytes"] <= maximum
        or not 0 < descriptor["bytes"] <= maximum
    ):
        raise CertificationError("invalid bounded UI asset descriptor")
    content = assets[path]
    if (
        len(content) != descriptor["bytes"]
        or hashlib.sha256(content).hexdigest() != descriptor["sha256"]
    ):
        raise CertificationError("UI shard compressed checksum/size differs")
    # A bounded read prevents a corrupt/bomb artifact from expanding unchecked.
    import io

    try:
        with gzip.GzipFile(fileobj=io.BytesIO(content)) as archive:
            decoded = archive.read(maximum + 1)
        if (
            len(decoded) != descriptor["decodedBytes"]
            or hashlib.sha256(decoded).hexdigest() != descriptor["decodedSha256"]
        ):
            raise CertificationError("UI shard decoded checksum/size differs")
        return json.loads(decoded)
    except (OSError, EOFError, ValueError) as error:
        raise CertificationError("UI shard recovery failed") from error


def _validate_row(kind: str, row: dict[str, Any]) -> None:
    MODELS[kind].model_validate(row)
    provenance = row["provenance"]
    if (
        provenance["status"] == "synthetic"
        or provenance["sourceType"] == "synthetic-demo"
    ):
        raise CertificationError("UI shard provenance/source differs")


class UIShardBuilder:
    """Deterministic producer order; at most three small decoded buffers in RAM."""

    def __init__(self, dataset_version: str) -> None:
        if not dataset_version.strip():
            raise CertificationError("UI shard dataset version is required")
        self.dataset_version = dataset_version
        self.index = _Index()
        self.buffers: dict[str, list[bytes]] = {kind: [] for kind in KINDS}
        self.sizes: Counter[str] = Counter()
        self.sequences: Counter[str] = Counter()
        self.descriptors: list[dict[str, Any]] = []
        self.assets: list[tuple[str, str, bytes]] = []
        self.finished = False

    @property
    def record_counts(self) -> dict[str, int]:
        return {kind: len(self.index.ids[kind]) for kind in KINDS}

    def _id(self, kind: str) -> str:
        return f"ui-{kind.lower()}-{self.sequences[kind]:04d}"

    def _prefix(self, kind: str) -> bytes:
        # Same canonical JSON as _encode with records inserted without decoding.
        return (
            b'{"datasetVersion":'
            + _encode(self.dataset_version)
            + b',"kind":'
            + _encode(kind)
            + b',"records":['
        )

    def _suffix(self) -> bytes:
        return b'],"version":' + _encode(UI_SHARDS_VERSION) + b"}"

    def add(self, kind: UIKind, record: UIRecord) -> None:
        if self.finished or kind not in KINDS or not isinstance(record, MODELS[kind]):
            raise CertificationError("invalid or finalized UI relationship sink")
        row = record.model_dump(mode="json", by_alias=True, exclude_none=True)
        _validate_row(kind, row)
        encoded = _encode(row)
        overhead = len(self._prefix(kind)) + len(self._suffix())
        if overhead + len(encoded) > MAX_UI_SHARD_BYTES:
            raise CertificationError(
                "single UI record exceeds bounded shard; not truncated"
            )
        if self.buffers[kind] and (
            overhead + self.sizes[kind] + 1 + len(encoded) > MAX_UI_SHARD_BYTES
        ):
            self._flush(kind)
        self.index.add(kind, row, self._id(kind))
        self.sizes[kind] += len(encoded) + bool(self.buffers[kind])
        self.buffers[kind].append(encoded)

    def _flush(self, kind: str) -> None:
        rows = self.buffers[kind]
        if not rows:
            return
        if len(self.descriptors) >= MAX_UI_SHARDS:
            raise CertificationError(
                "UI export exceeds 512 shards; no records truncated"
            )
        identity = self._id(kind)
        descriptor, content = _compressed(
            f"{identity}.json.gz", self._prefix(kind) + b",".join(rows) + self._suffix()
        )
        if descriptor["bytes"] > MAX_UI_SHARD_BYTES:
            raise CertificationError("compressed UI shard exceeds transport limit")
        descriptor.update(id=identity, kind=kind, recordCount=len(rows))
        self.descriptors.append(descriptor)
        self.assets.append(("ui-shard", descriptor["path"], content))
        self.sequences[kind] += 1
        self.buffers[kind] = []
        self.sizes[kind] = 0

    def finish(self, core: AtlasDatasetEntities) -> UIShardExport:
        if self.finished:
            raise CertificationError("UI shard builder is already finalized")
        for kind in KINDS:
            self._flush(kind)
        content = _encode(
            self.index.document(
                core,
                self.dataset_version,
                sorted(row["id"] for row in self.descriptors),
            )
        )
        if len(content) > MAX_UI_INDEX_BYTES:
            raise CertificationError(
                "UI index exceeds bounded 8 MiB; no index truncated"
            )
        descriptor, compressed = _compressed("ui-index.json.gz", content)
        if len(compressed) > MAX_UI_INDEX_BYTES:
            raise CertificationError("compressed UI index exceeds transport limit")
        result = UIShardExport(
            {
                "version": UI_SHARDS_VERSION,
                "index": descriptor,
                "shards": self.descriptors,
                "recordCounts": self.record_counts,
            },
            tuple(self.assets) + (("ui-index", descriptor["path"], compressed),),
            self.dataset_version,
        )
        self.finished = True
        return result
