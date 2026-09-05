"""Offline certification summary for checksum-verified historical replay bundles."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, cast

from .contracts import (
    CERTIFICATION_POLICY_VERSION,
    CertificationError,
    CertificationState,
    EvidenceCertificationDecision,
    EvidenceKind,
    EvidenceReference,
    canonical_digest,
)
from .rules import evidence_rule_version
from .validation_artifacts import (
    MAX_VALIDATION_DECISIONS,
    MAX_VALIDATION_PAPERS,
    check_validation_size,
    require_validation_runtime,
    validation_paper_limit,
)

REPLAY_CERTIFICATION_VERSION = "historical-replay-evidence-certification-v1"
_IN_MEMORY_DECISION_LIMIT = MAX_VALIDATION_DECISIONS
_JSONL_ROLES = frozenset(
    {
        "source-occurrences",
        "paper-components",
        "citation-observations",
        "field-ledgers",
        "researcher-appearances",
        "paper-time-affiliation-shares",
        "institution-authority-anchors",
        "fractional-attribution-ledgers",
    }
)
_REQUIRED_ROLES = frozenset(
    {
        "paper-components",
        "citation-observations",
        "field-ledgers",
        "researcher-appearances",
        "paper-time-affiliation-shares",
        "institution-authority-anchors",
    }
)
_CERTIFICATION_STATES: tuple[CertificationState, ...] = (
    "certified",
    "needs_review",
    "withheld",
    "conflicted",
    "insufficient_evidence",
)


@dataclass(frozen=True)
class CertificationArtifact:
    role: str
    relative_path: str
    checksum: str
    byte_count: int
    row_count: int | None
    content: bytes


@dataclass(frozen=True)
class ReplayCertificationResult:
    source_bundle_manifest_checksum: str
    decisions: tuple[EvidenceCertificationDecision, ...]
    report: dict[str, object]
    artifacts: tuple[CertificationArtifact, ...]
    certification_manifest: dict[str, object]


@dataclass(frozen=True)
class ReplayCertificationSummary:
    """Bounded-memory report over a deterministic certification decision stream."""

    source_bundle_manifest_checksum: str
    decision_stream_checksum: str
    decision_count: int
    report: dict[str, object]
    certification_manifest: dict[str, object]
    output_manifest_path: Path | None


@dataclass(frozen=True)
class _ArtifactEntry:
    role: str
    path: Path
    relative_path: str
    checksum: str
    byte_count: int
    row_count: int | None


def _canonical_json(value: object, *, pretty: bool = False) -> bytes:
    if pretty:
        return (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode()
            + b"\n"
        )
    return (
        json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
    )


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CertificationError(f"replay certification requires {label}")
    return value


def _load_manifest(root: Path, manifest_path: Path) -> dict[str, object]:
    resolved_root = root.expanduser().resolve()
    resolved_manifest = manifest_path.expanduser().resolve()
    if not _inside(resolved_manifest, resolved_root / "manifests"):
        raise CertificationError("replay manifest must belong to the bundle root")
    try:
        payload = json.loads(resolved_manifest.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise CertificationError("replay bundle manifest is unreadable") from error
    if not isinstance(payload, dict):
        raise CertificationError("replay bundle manifest must be an object")
    document = cast(dict[str, object], payload)
    checksum = _required_text(
        document.get("bundle_manifest_checksum"), "bundle manifest checksum"
    )
    unsigned = {
        key: value
        for key, value in document.items()
        if key != "bundle_manifest_checksum"
    }
    if canonical_digest(unsigned) != checksum:
        raise CertificationError("replay bundle manifest checksum failed")
    if (
        document.get("database_access") is not False
        or document.get("source_cursor_access") is not False
        or document.get("network_access") is not False
        or document.get("metric_observations_created") != 0
    ):
        raise CertificationError("replay bundle is not a staging-only input")
    return document


def _artifact_entries(
    root: Path, manifest: dict[str, object]
) -> tuple[_ArtifactEntry, ...]:
    raw_entries = manifest.get("artifacts")
    if not isinstance(raw_entries, list):
        raise CertificationError("replay bundle manifest lacks artifacts")
    resolved_root = root.expanduser().resolve()
    entries: list[_ArtifactEntry] = []
    roles: set[str] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise CertificationError("replay artifact entry is malformed")
        role = _required_text(raw.get("role"), "artifact role")
        relative = _required_text(raw.get("path"), "artifact path")
        checksum = _required_text(raw.get("checksum"), "artifact checksum")
        byte_count = raw.get("byte_count")
        row_count = raw.get("row_count")
        if role in roles:
            raise CertificationError("replay bundle contains a duplicate artifact role")
        if not isinstance(byte_count, int) or byte_count < 0:
            raise CertificationError("replay artifact byte count is invalid")
        if row_count is not None and (not isinstance(row_count, int) or row_count < 0):
            raise CertificationError("replay artifact row count is invalid")
        if role in _JSONL_ROLES and row_count is None:
            raise CertificationError("replay JSONL artifact lacks a row count")
        path = (resolved_root / relative).resolve()
        if Path(relative).is_absolute() or not _inside(path, resolved_root):
            raise CertificationError("replay artifact path leaves the bundle root")
        entries.append(
            _ArtifactEntry(
                role=role,
                path=path,
                relative_path=relative,
                checksum=checksum,
                byte_count=byte_count,
                row_count=row_count,
            )
        )
        roles.add(role)
    missing = _REQUIRED_ROLES - roles
    if missing:
        raise CertificationError(
            f"replay bundle lacks required evidence artifacts: {sorted(missing)}"
        )
    return tuple(entries)


def _verify_artifact(entry: _ArtifactEntry) -> None:
    digest = hashlib.sha256()
    byte_count = 0
    row_count = 0
    try:
        with entry.path.open("rb") as stream:
            if entry.row_count is None:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
                    byte_count += len(chunk)
            else:
                for raw_line in stream:
                    digest.update(raw_line)
                    byte_count += len(raw_line)
                    if raw_line.strip():
                        row_count += 1
    except OSError as error:
        raise CertificationError(
            f"replay artifact cannot be read: {entry.relative_path}"
        ) from error
    if byte_count != entry.byte_count or digest.hexdigest() != entry.checksum:
        raise CertificationError(
            f"replay artifact checksum failed: {entry.relative_path}"
        )
    if entry.row_count is not None and row_count != entry.row_count:
        raise CertificationError(
            f"replay artifact row count failed: {entry.relative_path}"
        )


def _rows(entry: _ArtifactEntry) -> Iterator[dict[str, object]]:
    count = 0
    try:
        with entry.path.open("rb") as stream:
            for raw_line in stream:
                if not raw_line.strip():
                    continue
                try:
                    row = json.loads(raw_line)
                except json.JSONDecodeError as error:
                    raise CertificationError(
                        f"replay JSONL is malformed: {entry.relative_path}"
                    ) from error
                if not isinstance(row, dict):
                    raise CertificationError("replay JSONL rows must be objects")
                count += 1
                yield cast(dict[str, object], row)
    except OSError as error:
        raise CertificationError(
            f"replay artifact cannot be read: {entry.relative_path}"
        ) from error
    if entry.row_count is not None and count != entry.row_count:
        raise CertificationError(
            f"replay artifact row count failed: {entry.relative_path}"
        )


def _references(
    row: dict[str, object],
    manifest_checksum: str,
    artifact: _ArtifactEntry,
) -> tuple[EvidenceReference, ...]:
    lineage = row.get("source_lineage")
    raw_items = lineage if isinstance(lineage, list) else [row]
    references: list[EvidenceReference] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        checksum = raw.get("source_record_checksum") or raw.get("page_checksum")
        if not isinstance(checksum, str) or len(checksum) != 64:
            continue
        provider = raw.get("provider")
        source_record = (
            raw.get("source_record_id")
            or raw.get("source_occurrence_id")
            or raw.get("occurrence_id")
            or row.get("observation_id")
            or row.get("candidate_id")
        )
        if not isinstance(provider, str) or not provider.strip():
            provider = "replay-lineage"
        if not isinstance(source_record, str) or not source_record.strip():
            continue
        references.append(
            EvidenceReference(
                provider=provider,
                source_record_id=source_record,
                checksum=checksum,
                source_snapshot_id=manifest_checksum,
                storage_reference=(
                    str(raw["page_path"])
                    if isinstance(raw.get("page_path"), str)
                    else None
                ),
            )
        )
    subject_reference = next(
        (
            value
            for value in (
                row.get("canonical_id"),
                row.get("candidate_id"),
                row.get("observation_id"),
                row.get("authorship_appearance_id"),
                row.get("paper_time_affiliation_share_id"),
            )
            if isinstance(value, str) and value.strip()
        ),
        artifact.checksum,
    )
    references.append(
        EvidenceReference(
            provider="historical-replay",
            source_record_id=f"{artifact.role}:{subject_reference}",
            checksum=artifact.checksum,
            source_snapshot_id=manifest_checksum,
            storage_reference=artifact.relative_path,
        )
    )
    return tuple(dict.fromkeys(references))


def _decision(
    *,
    subject_type: str,
    subject_id: str,
    kind: EvidenceKind,
    state: CertificationState,
    dataset_version: str,
    acquisition_scope: str,
    evidence: tuple[EvidenceReference, ...],
    reason: str | None = None,
) -> EvidenceCertificationDecision:
    if state == "certified" and not evidence:
        state = "insufficient_evidence"
        reason = "immutable source lineage is incomplete"
    return EvidenceCertificationDecision(
        subject_type=subject_type,
        subject_id=subject_id,
        evidence_kind=kind,
        state=state,
        rule_version=evidence_rule_version(kind),
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        evidence=evidence,
        reasons=(reason or "evidence is not certification-eligible",)
        if state != "certified"
        else (),
    )


def _paper_decisions(
    row: dict[str, object],
    dataset: str,
    scope: str,
    manifest_checksum: str,
    artifact: _ArtifactEntry,
) -> tuple[EvidenceCertificationDecision, ...]:
    paper_id = _required_text(
        row.get("canonical_id") or row.get("candidate_id"), "canonical paper id"
    )
    references = _references(row, manifest_checksum, artifact)
    has_source_lineage = any(
        item.provider != "historical-replay" for item in references
    )
    identity_state: CertificationState = (
        "certified"
        if row.get("status") == "matched"
        and row.get("merge_policy_version") == "canonical-paper-merge-policy-v1"
        and has_source_lineage
        else "needs_review"
    )
    has_date_evidence = bool(row.get("dates") or row.get("date_evidence"))
    date_state: CertificationState = (
        "certified"
        if row.get("canonical_date_selected") is True
        else "needs_review"
        if has_date_evidence
        else "insufficient_evidence"
    )
    return (
        _decision(
            subject_type="paper",
            subject_id=paper_id,
            kind="canonical-paper-identity",
            state=identity_state,
            dataset_version=dataset,
            acquisition_scope=scope,
            evidence=references,
            reason="canonical merge component requires identity review",
        ),
        _decision(
            subject_type="paper",
            subject_id=paper_id,
            kind="publication-metric-date",
            state=date_state,
            dataset_version=dataset,
            acquisition_scope=scope,
            evidence=references,
            reason=(
                "provider date facts exist but no canonical metric date was reviewed"
                if has_date_evidence
                else "no valid publication date evidence exists"
            ),
        ),
        _decision(
            subject_type="paper",
            subject_id=paper_id,
            kind="provenance-completeness",
            state="certified" if has_source_lineage else "insufficient_evidence",
            dataset_version=dataset,
            acquisition_scope=scope,
            evidence=references,
            reason="canonical paper lineage is incomplete",
        ),
    )


def _field_decisions(
    row: dict[str, object],
    dataset: str,
    scope: str,
    manifest_checksum: str,
    artifact: _ArtifactEntry,
) -> tuple[EvidenceCertificationDecision, ...]:
    paper_id = _required_text(
        row.get("canonical_id") or row.get("candidate_id"), "field paper id"
    )
    references = _references(row, manifest_checksum, artifact)
    ledger = (
        cast(dict[str, object], row["ledger"])
        if isinstance(row.get("ledger"), dict)
        else {}
    )
    reviewed_at = row.get("reviewed_at")
    try:
        parsed_reviewed_at = (
            datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            if isinstance(reviewed_at, str)
            else None
        )
    except ValueError:
        parsed_reviewed_at = None
    reviewed = (
        row.get("review_status") == "reviewed-approved"
        and isinstance(row.get("reviewed_by"), str)
        and bool(cast(str, row.get("reviewed_by")).strip())
        and parsed_reviewed_at is not None
        and parsed_reviewed_at.tzinfo is not None
        and parsed_reviewed_at.utcoffset() is not None
        and ledger.get("ontology_version") == "physics-field-ontology-v1"
        and ledger.get("mapping_version") == "provider-field-mapping-v1"
        and ledger.get("weighting_policy_version")
        == "provider-evidence-conservation-v2"
    )
    conserved = (
        row.get("conservation_passed") is True
        and ledger.get("weighting_policy_version")
        == "provider-evidence-conservation-v2"
        and ledger.get("ontology_version") == "physics-field-ontology-v1"
    )
    return (
        _decision(
            subject_type="paper",
            subject_id=paper_id,
            kind="field-classification",
            state="certified" if reviewed else "needs_review",
            dataset_version=dataset,
            acquisition_scope=scope,
            evidence=references,
            reason="provider field ledger is present but remains unreviewed",
        ),
        _decision(
            subject_type="paper",
            subject_id=paper_id,
            kind="field-weight-conservation",
            state="certified" if conserved else "conflicted",
            dataset_version=dataset,
            acquisition_scope=scope,
            evidence=references,
            reason="mapped and explicit unmapped field mass do not total one",
        ),
    )


def _citation_decisions(
    row: dict[str, object],
    dataset: str,
    scope: str,
    manifest_checksum: str,
    artifact: _ArtifactEntry,
) -> tuple[EvidenceCertificationDecision, ...]:
    paper_id = _required_text(
        row.get("canonical_id") or row.get("candidate_id"), "citation paper id"
    )
    references = _references(row, manifest_checksum, artifact)
    raw_count = row.get("raw_citation_count")
    non_self_count = row.get("non_self_citation_count")
    page_timestamp = row.get("page_capture_timestamp")
    cutoff_timestamp = row.get("cutoff_timestamp")
    reasons: list[str] = []
    state: CertificationState = "certified"
    raw_value = (
        raw_count
        if isinstance(raw_count, int) and not isinstance(raw_count, bool)
        else None
    )
    non_self_value = (
        non_self_count
        if isinstance(non_self_count, int) and not isinstance(non_self_count, bool)
        else None
    )
    if raw_value is None or raw_value < 0:
        state = "insufficient_evidence"
        reasons.append("citation observation lacks a valid raw count")
    if non_self_value is None or non_self_value < 0:
        state = "insufficient_evidence"
        reasons.append("citation observation lacks a valid non-self count")
    if (
        raw_value is not None
        and non_self_value is not None
        and non_self_value > raw_value
    ):
        state = "conflicted"
        reasons.append("non-self citation count exceeds the raw citation count")

    parsed_page: datetime | None = None
    parsed_cutoff: datetime | None = None
    try:
        if isinstance(page_timestamp, str):
            parsed_page = datetime.fromisoformat(page_timestamp.replace("Z", "+00:00"))
        if isinstance(cutoff_timestamp, str):
            parsed_cutoff = datetime.fromisoformat(
                cutoff_timestamp.replace("Z", "+00:00")
            )
    except ValueError:
        state = "conflicted"
        reasons.append("citation timestamps are malformed")
    if parsed_page is None:
        if state == "certified":
            state = "withheld"
        reasons.append("per-page citation capture time is absent")
    elif parsed_page.tzinfo is None or parsed_page.utcoffset() is None:
        state = "conflicted"
        reasons.append("citation page timestamp lacks a timezone")
    if parsed_cutoff is None:
        if state == "certified":
            state = "withheld"
        reasons.append("common citation cutoff is absent")
    elif parsed_cutoff.tzinfo is None or parsed_cutoff.utcoffset() is None:
        state = "conflicted"
        reasons.append("citation cutoff timestamp lacks a timezone")
    if (
        parsed_page is not None
        and parsed_cutoff is not None
        and parsed_page != parsed_cutoff
    ):
        state = "conflicted"
        reasons.append("citation page timestamp differs from the selected cutoff")
    if (
        row.get("simultaneous_observation_claimed") is not True
        or row.get("common_cutoff_comparable") is not True
    ):
        if state == "certified":
            state = "withheld"
        reasons.append("replay does not prove a simultaneous common-cutoff observation")
    reason = "; ".join(dict.fromkeys(reasons))
    return (
        _decision(
            subject_type="paper",
            subject_id=paper_id,
            kind="citation-observation",
            state=state,
            dataset_version=dataset,
            acquisition_scope=scope,
            evidence=references,
            reason=reason,
        ),
        _decision(
            subject_type="paper",
            subject_id=paper_id,
            kind="citation-cutoff-compatibility",
            state=state,
            dataset_version=dataset,
            acquisition_scope=scope,
            evidence=references,
            reason=reason,
        ),
    )


def _researcher_decision(
    row: dict[str, object],
    dataset: str,
    scope: str,
    manifest_checksum: str,
    artifact: _ArtifactEntry,
) -> EvidenceCertificationDecision:
    subject_id = _required_text(
        row.get("authorship_appearance_id"), "researcher appearance id"
    )
    references = _references(row, manifest_checksum, artifact)
    canonical = row.get("canonical_researcher_id")
    proof = row.get("researcher_certification_id")
    state: CertificationState = (
        "certified"
        if isinstance(canonical, str)
        and canonical.strip()
        and isinstance(proof, str)
        and proof.startswith("cert-")
        else "needs_review"
        if row.get("authority_identifiers")
        else "insufficient_evidence"
    )
    return _decision(
        subject_type="researcher-appearance",
        subject_id=subject_id,
        kind="researcher-identity",
        state=state,
        dataset_version=dataset,
        acquisition_scope=scope,
        evidence=references,
        reason="researcher authority evidence has no reviewed canonical identity",
    )


def _affiliation_decisions(
    row: dict[str, object],
    dataset: str,
    scope: str,
    manifest_checksum: str,
    artifact: _ArtifactEntry,
) -> tuple[EvidenceCertificationDecision, ...]:
    subject_id = _required_text(
        row.get("paper_time_affiliation_share_id"), "paper-time affiliation share id"
    )
    references = _references(row, manifest_checksum, artifact)
    has_paper_time_evidence = bool(row.get("raw_affiliations"))
    canonical = row.get("canonical_institution_id")
    certification_id = row.get("institution_certification_id")
    canonical_resolved = (
        isinstance(canonical, str)
        and bool(canonical.strip())
        and isinstance(certification_id, str)
        and certification_id.startswith("cert-")
        and row.get("eligible_for_public_metrics") is True
    )
    return (
        _decision(
            subject_type="paper-affiliation",
            subject_id=subject_id,
            kind="paper-time-affiliation",
            state=(
                "needs_review" if has_paper_time_evidence else "insufficient_evidence"
            ),
            dataset_version=dataset,
            acquisition_scope=scope,
            evidence=references,
            reason=(
                "paper-time affiliation evidence requires strict certification"
                if has_paper_time_evidence
                else "paper-time affiliation assertion is missing"
            ),
        ),
        _decision(
            subject_type="paper-affiliation",
            subject_id=subject_id,
            kind="canonical-institution",
            state="certified" if canonical_resolved else "needs_review",
            dataset_version=dataset,
            acquisition_scope=scope,
            evidence=references,
            reason="paper-time affiliation has no reviewed ROR-backed institution",
        ),
    )


def _institution_anchor_decision(
    row: dict[str, object],
    dataset: str,
    scope: str,
    manifest_checksum: str,
    artifact: _ArtifactEntry,
) -> EvidenceCertificationDecision:
    subject_id = _required_text(
        row.get("institution_authority_anchor_id"), "institution authority anchor id"
    )
    references = _references(row, manifest_checksum, artifact)
    authority_version = row.get("required_authority_bundle_version")
    correct_scope = isinstance(authority_version, str) and authority_version.startswith(
        f"{scope}-"
    )
    canonical = row.get("canonical_institution_id")
    certification_id = row.get("institution_certification_id")
    canonical_resolved = (
        isinstance(canonical, str)
        and bool(canonical.strip())
        and isinstance(certification_id, str)
        and certification_id.startswith("cert-")
        and row.get("eligible_for_public_metrics") is True
    )
    eligible = row.get("eligible_for_public_metrics") is True
    reasons: list[str] = []
    state: CertificationState = "certified"
    if not correct_scope:
        state = "conflicted"
        reasons.append("institution authority bundle belongs to another scope")
    if not canonical_resolved or not eligible:
        if state == "certified":
            state = "needs_review"
        reasons.append(
            "institution authority metadata remains unresolved or ineligible"
        )
    return _decision(
        subject_type="institution-authority-anchor",
        subject_id=subject_id,
        kind="canonical-institution",
        state=state,
        dataset_version=dataset,
        acquisition_scope=scope,
        evidence=references,
        reason="; ".join(reasons),
    )


def _decision_row(item: EvidenceCertificationDecision) -> dict[str, object]:
    return {
        "decision_id": item.decision_id,
        "subject_type": item.subject_type,
        "subject_id": item.subject_id,
        "evidence_kind": item.evidence_kind,
        "state": item.state,
        "rule_version": item.rule_version,
        "dataset_version": item.dataset_version,
        "acquisition_scope": item.acquisition_scope,
        "evidence": [
            {
                "provider": ref.provider,
                "source_record_id": ref.source_record_id,
                "source_snapshot_id": ref.source_snapshot_id,
                "checksum": ref.checksum,
                "storage_reference": ref.storage_reference,
            }
            for ref in item.evidence
        ],
        "reasons": list(item.reasons),
    }


def _iter_decisions(
    by_role: dict[str, _ArtifactEntry],
    *,
    dataset_version: str,
    acquisition_scope: str,
    source_checksum: str,
) -> Iterator[EvidenceCertificationDecision]:
    for row in _rows(by_role["paper-components"]):
        yield from _paper_decisions(
            row,
            dataset_version,
            acquisition_scope,
            source_checksum,
            by_role["paper-components"],
        )
    for row in _rows(by_role["field-ledgers"]):
        yield from _field_decisions(
            row,
            dataset_version,
            acquisition_scope,
            source_checksum,
            by_role["field-ledgers"],
        )
    for row in _rows(by_role["citation-observations"]):
        yield from _citation_decisions(
            row,
            dataset_version,
            acquisition_scope,
            source_checksum,
            by_role["citation-observations"],
        )
    for row in _rows(by_role["researcher-appearances"]):
        yield _researcher_decision(
            row,
            dataset_version,
            acquisition_scope,
            source_checksum,
            by_role["researcher-appearances"],
        )
    for row in _rows(by_role["institution-authority-anchors"]):
        yield _institution_anchor_decision(
            row,
            dataset_version,
            acquisition_scope,
            source_checksum,
            by_role["institution-authority-anchors"],
        )
    for row in _rows(by_role["paper-time-affiliation-shares"]):
        yield from _affiliation_decisions(
            row,
            dataset_version,
            acquisition_scope,
            source_checksum,
            by_role["paper-time-affiliation-shares"],
        )


def _report(
    *,
    manifest: dict[str, object],
    entries: tuple[_ArtifactEntry, ...],
    source_checksum: str,
    dataset_version: str,
    acquisition_scope: str,
    state_counts: Counter[tuple[EvidenceKind, CertificationState]],
    kind_totals: Counter[EvidenceKind],
    certified_counts: Counter[EvidenceKind],
    reason_counts: Counter[str],
    decision_count: int,
    decision_stream_checksum: str,
    decision_stream_byte_count: int,
    decision_artifact_available: bool,
) -> dict[str, object]:
    return {
        "certification_version": REPLAY_CERTIFICATION_VERSION,
        "certification_policy_version": CERTIFICATION_POLICY_VERSION,
        "source_bundle_manifest_checksum": source_checksum,
        "source_bundle_version": manifest.get("bundle_version"),
        "dataset_version": dataset_version,
        "acquisition_scope": acquisition_scope,
        "verified_artifact_count": len(entries),
        "verified_artifacts": [
            {
                "role": item.role,
                "path": item.relative_path,
                "checksum": item.checksum,
                "byte_count": item.byte_count,
                "row_count": item.row_count,
            }
            for item in entries
        ],
        "decision_count": decision_count,
        "decision_stream": {
            "checksum": decision_stream_checksum,
            "byte_count": decision_stream_byte_count,
            "row_count": decision_count,
            "deterministic_order": (
                "paper, field, citation, researcher, institution-authority, "
                "affiliation artifact row order"
            ),
            "artifact_available": decision_artifact_available,
        },
        "state_counts": {
            kind: {
                state: state_counts[(kind, state)]
                for state in _CERTIFICATION_STATES
                if state_counts[(kind, state)]
            }
            for kind in sorted(kind_totals)
        },
        "record_certification_coverage": {
            kind: certified_counts[kind] / total
            for kind, total in sorted(kind_totals.items())
            if total
        },
        "withheld_reason_counts": dict(sorted(reason_counts.items())),
        "certified_complete_years": [],
        "metric_window_certifications": 0,
        "metric_observations_created": 0,
        "full_year_certification_withheld_reason": (
            "Replay evidence has no reviewed canonical metric dates, reviewed field "
            "ledgers, or per-page common citation cutoff proof; downloaded partitions "
            "are not certified years."
        ),
        "database_access": False,
        "source_cursor_access": False,
        "network_access": False,
    }


def _certification_manifest(
    *,
    source_checksum: str,
    dataset_version: str,
    acquisition_scope: str,
    artifacts: tuple[CertificationArtifact, ...],
    decision_stream_checksum: str,
    decision_stream_byte_count: int,
    decision_count: int,
    summary_only: bool,
    retained_decision: dict[str, object] | None = None,
) -> dict[str, object]:
    unsigned: dict[str, object] = {
        "certification_version": REPLAY_CERTIFICATION_VERSION,
        "source_bundle_manifest_checksum": source_checksum,
        "dataset_version": dataset_version,
        "acquisition_scope": acquisition_scope,
        "decision_stream": {
            "checksum": decision_stream_checksum,
            "byte_count": decision_stream_byte_count,
            "row_count": decision_count,
            "artifact_available": not summary_only,
        },
        "summary_only": summary_only,
        "artifacts": [
            {
                "role": item.role,
                "path": item.relative_path,
                "checksum": item.checksum,
                "byte_count": item.byte_count,
                "row_count": item.row_count,
            }
            for item in artifacts
        ],
        "database_access": False,
        "source_cursor_access": False,
        "network_access": False,
        "metric_observations_created": 0,
    }
    if retained_decision is not None:
        artifact_rows = cast(list[dict[str, object]], unsigned["artifacts"])
        artifact_rows.insert(0, retained_decision)
    return {
        **unsigned,
        "certification_manifest_checksum": canonical_digest(unsigned),
    }


def _verified_context(
    bundle_root: Path,
    bundle_manifest: Path,
    *,
    in_memory_decision_limit: int | None = None,
    validation_max_papers: int | None = None,
) -> tuple[
    dict[str, object],
    tuple[_ArtifactEntry, ...],
    dict[str, _ArtifactEntry],
    str,
    str,
    str,
]:
    manifest = _load_manifest(bundle_root, bundle_manifest)
    entries = _artifact_entries(bundle_root, manifest)
    if in_memory_decision_limit is not None or validation_max_papers is not None:
        row_counts = {item.role: item.row_count or 0 for item in entries}
        estimated_decisions = (
            3 * row_counts["paper-components"]
            + 2 * row_counts["field-ledgers"]
            + 2 * row_counts["citation-observations"]
            + row_counts["researcher-appearances"]
            + row_counts["institution-authority-anchors"]
            + 2 * row_counts["paper-time-affiliation-shares"]
        )
        if (
            in_memory_decision_limit is not None
            and estimated_decisions > in_memory_decision_limit
        ):
            raise CertificationError(
                "replay is too large for in-memory decisions; use "
                "summary-only summarize_replay_bundle (no retained decisions)"
            )
        check_validation_size(
            paper_count=row_counts["paper-components"],
            paper_limit=validation_max_papers or MAX_VALIDATION_PAPERS,
            decision_count=estimated_decisions,
        )
    for entry in entries:
        _verify_artifact(entry)
    by_role = {entry.role: entry for entry in entries}
    source_checksum = _required_text(
        manifest.get("bundle_manifest_checksum"), "bundle manifest checksum"
    )
    dataset_version = _required_text(manifest.get("replay_digest"), "replay digest")
    acquisition_scope = _required_text(
        manifest.get("acquisition_scope"), "acquisition scope"
    )
    return (
        manifest,
        entries,
        by_role,
        source_checksum,
        dataset_version,
        acquisition_scope,
    )


def certify_replay_bundle(
    *,
    bundle_root: Path,
    bundle_manifest: Path,
) -> ReplayCertificationResult:
    """Build a bounded validation trace, never production certification state."""

    require_validation_runtime()
    (
        manifest,
        entries,
        by_role,
        source_checksum,
        dataset_version,
        acquisition_scope,
    ) = _verified_context(
        bundle_root,
        bundle_manifest,
        in_memory_decision_limit=_IN_MEMORY_DECISION_LIMIT,
    )

    ordered = tuple(
        _iter_decisions(
            by_role,
            dataset_version=dataset_version,
            acquisition_scope=acquisition_scope,
            source_checksum=source_checksum,
        )
    )
    state_counts = Counter((item.evidence_kind, item.state) for item in ordered)
    kind_totals = Counter(item.evidence_kind for item in ordered)
    certified_counts = Counter(
        item.evidence_kind for item in ordered if item.state == "certified"
    )
    reason_counts = Counter(reason for item in ordered for reason in item.reasons)
    decision_parts: list[bytes] = []
    decision_bytes = 0
    for item in ordered:
        content = _canonical_json(_decision_row(item))
        decision_bytes += len(content)
        check_validation_size(
            decision_count=len(decision_parts) + 1, decision_bytes=decision_bytes
        )
        decision_parts.append(content)
    decision_content = b"".join(decision_parts)
    decision_checksum = hashlib.sha256(decision_content).hexdigest()
    report = _report(
        manifest=manifest,
        entries=entries,
        source_checksum=source_checksum,
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        state_counts=state_counts,
        kind_totals=kind_totals,
        certified_counts=certified_counts,
        reason_counts=reason_counts,
        decision_count=len(ordered),
        decision_stream_checksum=decision_checksum,
        decision_stream_byte_count=len(decision_content),
        decision_artifact_available=True,
    )
    report_content = _canonical_json(report, pretty=True)
    artifacts = (
        CertificationArtifact(
            role="evidence-certification-decisions",
            relative_path=(f"certification/decisions/{decision_checksum}.jsonl"),
            checksum=decision_checksum,
            byte_count=len(decision_content),
            row_count=len(ordered),
            content=decision_content,
        ),
        CertificationArtifact(
            role="evidence-certification-report",
            relative_path=(
                f"certification/reports/{hashlib.sha256(report_content).hexdigest()}"
                ".json"
            ),
            checksum=hashlib.sha256(report_content).hexdigest(),
            byte_count=len(report_content),
            row_count=None,
            content=report_content,
        ),
    )
    certification_manifest = _certification_manifest(
        source_checksum=source_checksum,
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        artifacts=artifacts,
        decision_stream_checksum=decision_checksum,
        decision_stream_byte_count=len(decision_content),
        decision_count=len(ordered),
        summary_only=False,
    )
    return ReplayCertificationResult(
        source_bundle_manifest_checksum=source_checksum,
        decisions=ordered,
        report=report,
        artifacts=artifacts,
        certification_manifest=certification_manifest,
    )


def summarize_replay_bundle(
    *,
    bundle_root: Path,
    bundle_manifest: Path,
    output_root: Path | None = None,
    retain_decisions: bool = False,
    validation_max_papers: int | None = None,
) -> ReplayCertificationSummary:
    """Certify a large replay with bounded memory and optional decision retention.

    The deterministic decision stream is fully hashed and counted, but intentionally
    not retained by default. Retention requires an explicit bounded sample; it
    must never be used for duplicated full-corpus production certification.
    No implicit sampling/truncation changes the input population or decisions.
    """

    require_validation_runtime()
    if retain_decisions and output_root is None:
        raise CertificationError("retaining decisions requires an output root")
    if retain_decisions:
        validation_max_papers = validation_paper_limit(validation_max_papers)
    elif validation_max_papers is not None:
        raise CertificationError("validation_max_papers requires retained decisions")
    (
        manifest,
        entries,
        by_role,
        source_checksum,
        dataset_version,
        acquisition_scope,
    ) = _verified_context(
        bundle_root, bundle_manifest, validation_max_papers=validation_max_papers
    )
    digest = hashlib.sha256()
    decision_count = 0
    decision_byte_count = 0
    state_counts: Counter[tuple[EvidenceKind, CertificationState]] = Counter()
    kind_totals: Counter[EvidenceKind] = Counter()
    certified_counts: Counter[EvidenceKind] = Counter()
    reason_counts: Counter[str] = Counter()
    retained_decision: dict[str, object] | None = None
    with _decision_output(output_root, retain_decisions) as stream:
        for item in _iter_decisions(
            by_role,
            dataset_version=dataset_version,
            acquisition_scope=acquisition_scope,
            source_checksum=source_checksum,
        ):
            content = _canonical_json(_decision_row(item))
            digest.update(content)
            if stream is not None:
                check_validation_size(
                    decision_count=decision_count + 1,
                    decision_bytes=decision_byte_count + len(content),
                )
                stream.write(content)
            decision_count += 1
            decision_byte_count += len(content)
            state_counts[(item.evidence_kind, item.state)] += 1
            kind_totals[item.evidence_kind] += 1
            if item.state == "certified":
                certified_counts[item.evidence_kind] += 1
            reason_counts.update(item.reasons)
        if stream is not None:
            assert output_root is not None
            retained_decision = _retain_decision_stream(
                stream,
                output_root,
                digest.hexdigest(),
                decision_byte_count,
                decision_count,
            )

    decision_checksum = digest.hexdigest()
    report = _report(
        manifest=manifest,
        entries=entries,
        source_checksum=source_checksum,
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        state_counts=state_counts,
        kind_totals=kind_totals,
        certified_counts=certified_counts,
        reason_counts=reason_counts,
        decision_count=decision_count,
        decision_stream_checksum=decision_checksum,
        decision_stream_byte_count=decision_byte_count,
        decision_artifact_available=retain_decisions,
    )
    report_content = _canonical_json(report, pretty=True)
    report_checksum = hashlib.sha256(report_content).hexdigest()
    artifacts = (
        CertificationArtifact(
            role="evidence-certification-report",
            relative_path=f"certification/reports/{report_checksum}.json",
            checksum=report_checksum,
            byte_count=len(report_content),
            row_count=None,
            content=report_content,
        ),
    )
    certification_manifest = _certification_manifest(
        source_checksum=source_checksum,
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        artifacts=artifacts,
        decision_stream_checksum=decision_checksum,
        decision_stream_byte_count=decision_byte_count,
        decision_count=decision_count,
        summary_only=not retain_decisions,
        retained_decision=retained_decision,
    )
    output_manifest_path = (
        _write_certification_artifacts(output_root, artifacts, certification_manifest)
        if output_root is not None
        else None
    )
    return ReplayCertificationSummary(
        source_bundle_manifest_checksum=source_checksum,
        decision_stream_checksum=decision_checksum,
        decision_count=decision_count,
        report=report,
        certification_manifest=certification_manifest,
        output_manifest_path=output_manifest_path,
    )


@contextmanager
def _decision_output(
    output_root: Path | None,
    retain: bool,
) -> Iterator[BinaryIO | None]:
    if not retain:
        yield None
        return
    assert output_root is not None
    resolved = output_root.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w+b",
        prefix=".certification-decisions-",
        dir=resolved,
    ) as stream:
        yield cast(BinaryIO, stream)


def _retain_decision_stream(
    stream: BinaryIO,
    output_root: Path,
    checksum: str,
    byte_count: int,
    row_count: int,
) -> dict[str, object]:
    resolved = output_root.expanduser().resolve()
    relative_path = f"certification/decisions/{checksum}.jsonl"
    destination = (resolved / relative_path).resolve()
    if not _inside(destination, resolved):
        raise CertificationError("decision artifact path leaves output root")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stream.flush()
    os.fsync(stream.fileno())
    try:
        # Same-filesystem hard link publishes only the complete stream and never
        # overwrites an existing content address. Temporary-file cleanup follows.
        os.link(stream.name, destination)
    except FileExistsError:
        with destination.open("rb") as existing:
            actual_checksum = hashlib.file_digest(existing, "sha256").hexdigest()
        if destination.stat().st_size != byte_count or actual_checksum != checksum:
            raise CertificationError(
                "existing decision artifact differs from content address"
            ) from None
    return {
        "role": "evidence-certification-decisions",
        "path": relative_path,
        "checksum": checksum,
        "byte_count": byte_count,
        "row_count": row_count,
    }


def _write_certification_artifacts(
    output_root: Path,
    artifacts: tuple[CertificationArtifact, ...],
    certification_manifest: dict[str, object],
) -> Path:
    resolved = output_root.expanduser().resolve()
    for artifact in artifacts:
        destination = (resolved / artifact.relative_path).resolve()
        if not _inside(destination, resolved):
            raise CertificationError("certification artifact path leaves output root")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != artifact.content:
                raise CertificationError(
                    "existing certification artifact differs from content address"
                )
        else:
            destination.write_bytes(artifact.content)
    content = _canonical_json(certification_manifest, pretty=True)
    checksum = _required_text(
        certification_manifest.get("certification_manifest_checksum"),
        "certification manifest checksum",
    )
    destination = resolved / "certification" / "manifests" / f"{checksum}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != content:
            raise CertificationError(
                "existing certification manifest differs from content address"
            )
    else:
        destination.write_bytes(content)
    return destination


def write_replay_certification_bundle(
    output_root: Path,
    result: ReplayCertificationResult,
) -> Path:
    """Write bounded validation files only; identical reruns are idempotent."""

    require_validation_runtime()
    # Recheck the public writer too: a caller may retain/construct a result object.
    check_validation_size(
        paper_count=len(
            {
                item.subject_id
                for item in result.decisions
                if item.evidence_kind == "canonical-paper-identity"
            }
        ),
        decision_count=len(result.decisions),
    )
    decision_artifacts = [
        artifact
        for artifact in result.artifacts
        if artifact.role == "evidence-certification-decisions"
    ]
    if len(decision_artifacts) != 1:
        raise CertificationError(
            "validation bundle requires exactly one decision trace"
        )
    artifact = decision_artifacts[0]
    check_validation_size(
        decision_count=artifact.row_count or 0,
        decision_bytes=max(artifact.byte_count, len(artifact.content)),
    )
    return _write_certification_artifacts(
        output_root,
        result.artifacts,
        result.certification_manifest,
    )
