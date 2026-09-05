"""Bounded, lossless hot/cold certification storage prototype, not a migration.

Hot rows are query projections, never certification proofs or calculator inputs.
The entire original JSON decision, including unknown future fields, remains in
one immutable cold artifact. Recovery verifies both the archive and each exact
decision before returning ordinary JSON for the existing certification boundary.
No rule is rerun, outcome promoted, provenance removed, or metric calculated.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import get_args

from ..certification.contracts import CertificationState, EvidenceKind
from .contracts import ArtifactIntegrityError, ArtifactRef, ArtifactStore, StorageTier

COMPACT_DECISION_VERSION = "compact-certification-audit-prototype-v1"
MAX_PROTOTYPE_DECISIONS = 10_000


@dataclass(frozen=True)
class CompactDecisionRow:
    """Candidate hot columns; reason text and archive reference are batch joins."""

    decision_id: str
    decision_sha256: str
    canonical_paper_id: str | None
    subject_type: str
    subject_id: str
    evidence_kind: str
    state: str
    rule_version: str
    reason_code: int
    audit_ordinal: int


@dataclass(frozen=True)
class CompactDecisionBatch:
    """One bounded immutable scope/version, with a deduplicated reason catalog.

    PostgreSQL measurements must include the batch and reason tables and their
    indexes, not just the per-decision rows. ``reason_code`` indexes ``reasons``.
    ``audit_ordinal`` locates the full decision in the verified JSONL archive.
    """

    version: str
    dataset_version: str
    acquisition_scope: str
    artifact: ArtifactRef
    reasons: tuple[tuple[str, ...], ...]
    rows: tuple[CompactDecisionRow, ...]


def _json_value(value: object) -> None:
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("decision JSON object keys must be strings")
        for item in value.values():
            _json_value(item)
    elif isinstance(value, list):
        for item in value:
            _json_value(item)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError("decision payload must contain JSON values only")


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    value = dict(payload)
    _json_value(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _required_text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"decision {field} must be a non-empty string")
    return value


def _reasons(payload: Mapping[str, object]) -> tuple[str, ...]:
    values = payload.get("reasons")
    if not isinstance(values, list) or any(
        not isinstance(value, str) for value in values
    ):
        raise ValueError("decision reasons must be a JSON string array")
    return tuple(str(value) for value in values)


def _project(
    payload: Mapping[str, object], *, reason_code: int, audit_ordinal: int
) -> CompactDecisionRow:
    state = _required_text(payload, "state")
    kind = _required_text(payload, "evidence_kind")
    if state not in get_args(CertificationState) or kind not in get_args(EvidenceKind):
        raise ValueError("unknown certification state or evidence kind")
    paper_id = payload.get("canonical_paper_id")
    if paper_id is not None and (not isinstance(paper_id, str) or not paper_id):
        raise ValueError("canonical paper id must be absent, null, or a string")
    return CompactDecisionRow(
        decision_id=_required_text(payload, "decision_id"),
        decision_sha256=hashlib.sha256(_canonical_json(payload)).hexdigest(),
        canonical_paper_id=paper_id,
        subject_type=_required_text(payload, "subject_type"),
        subject_id=_required_text(payload, "subject_id"),
        evidence_kind=kind,
        state=state,
        rule_version=_required_text(payload, "rule_version"),
        reason_code=reason_code,
        audit_ordinal=audit_ordinal,
    )


def compact_decisions(
    payloads: Sequence[Mapping[str, object]], store: ArtifactStore
) -> CompactDecisionBatch:
    """Write/verify cold bytes before exposing hot references; scope is <=10k.

    Sorting by decision ID makes input iteration order irrelevant. The checksum
    binds canonical JSON values, not the whitespace of an upstream JSONL file.
    Callers must retain upstream manifests/source references separately.
    """
    if not 0 < len(payloads) <= MAX_PROTOTYPE_DECISIONS:
        raise ValueError("compact prototype requires between 1 and 10,000 decisions")
    # Detach caller-owned mutable dictionaries before constructing the projection.
    records: list[dict[str, object]] = [
        json.loads(_canonical_json(payload)) for payload in payloads
    ]
    records.sort(key=lambda payload: _required_text(payload, "decision_id"))
    dataset_version = _required_text(records[0], "dataset_version")
    acquisition_scope = _required_text(records[0], "acquisition_scope")
    identities = [_required_text(record, "decision_id") for record in records]
    if len(set(identities)) != len(identities):
        raise ValueError("a compact batch cannot contain duplicate decision IDs")
    if any(
        _required_text(record, "dataset_version") != dataset_version
        or _required_text(record, "acquisition_scope") != acquisition_scope
        for record in records
    ):
        raise ValueError("a compact batch cannot mix dataset versions or scopes")
    reasons = tuple(sorted({_reasons(record) for record in records}))
    reason_codes = {reason: index for index, reason in enumerate(reasons)}
    rows = tuple(
        _project(
            record, reason_code=reason_codes[_reasons(record)], audit_ordinal=index
        )
        for index, record in enumerate(records)
    )
    archive = b"".join(_canonical_json(record) + b"\n" for record in records)
    output = io.BytesIO()
    # Explicit empty filename/mtime gives a stable gzip header across supported Python.
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as stream:
        stream.write(archive)
    artifact = store.put_bytes(
        output.getvalue(),
        tier=StorageTier.COLD,
        media_type="application/x-ndjson",
        content_encoding="gzip",
    )
    if not store.verify(artifact):
        raise ArtifactIntegrityError("cold decision archive failed write verification")
    return CompactDecisionBatch(
        version=COMPACT_DECISION_VERSION,
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        artifact=artifact,
        reasons=reasons,
        rows=rows,
    )


def recover_decisions(
    batch: CompactDecisionBatch, store: ArtifactStore
) -> tuple[dict[str, object], ...]:
    """Recover exact JSON only after checking all hot/cold correspondences.

    These ordinary JSON objects still need the existing typed certification and
    exact-population verification to become eligible metric inputs. A successful
    storage round trip is not scientific certification or activation.
    """
    if not isinstance(batch, CompactDecisionBatch) or (
        batch.version != COMPACT_DECISION_VERSION
        or not 0 < len(batch.rows) <= MAX_PROTOTYPE_DECISIONS
        or batch.artifact.tier is not StorageTier.COLD
        or batch.artifact.content_encoding != "gzip"
        or batch.artifact.media_type != "application/x-ndjson"
    ):
        raise ArtifactIntegrityError("unsupported compact decision batch")
    with store.open(batch.artifact) as stream:
        compressed = stream.read()
    if (
        len(compressed) != batch.artifact.size_bytes
        or hashlib.sha256(compressed).hexdigest() != batch.artifact.sha256
    ):
        raise ArtifactIntegrityError("cold decision archive failed read verification")
    try:
        archive = gzip.decompress(compressed)
        lines = archive.splitlines()
        if len(lines) != len(batch.rows):
            raise ValueError("archive/row count differs")
        records: list[dict[str, object]] = []
        for index, line in enumerate(lines):
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("archive entry is not an object")
            if (
                _required_text(record, "dataset_version") != batch.dataset_version
                or _required_text(record, "acquisition_scope")
                != batch.acquisition_scope
            ):
                raise ValueError("archive/row dataset boundary differs")
            reason = _reasons(record)
            if reason not in batch.reasons:
                raise ValueError("archive reason is absent from hot reason catalog")
            expected = _project(
                record, reason_code=batch.reasons.index(reason), audit_ordinal=index
            )
            if expected != batch.rows[index]:
                raise ValueError("archive decision digest or hot projection differs")
            if line != _canonical_json(record):
                raise ValueError("archive decision encoding is not canonical")
            records.append(record)
        if tuple(sorted({_reasons(record) for record in records})) != batch.reasons:
            raise ValueError("reason catalog has extra or non-canonical entries")
        ids = [_required_text(record, "decision_id") for record in records]
        if ids != sorted(set(ids)) or archive != b"".join(
            line + b"\n" for line in lines
        ):
            raise ValueError("archive entries are duplicated or non-canonical")
    except (ValueError, OSError, EOFError, TypeError) as error:
        raise ArtifactIntegrityError(
            f"compact decision recovery failed: {error}"
        ) from error
    return tuple(records)
