"""Deterministic identity-resolution validation support.

The helpers in this module do not alter canonical entities or resolution records.
They expose aggregate operational evidence and make manually labelled validation
sets reproducible without treating resolver output as ground truth.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models

EntityType = Literal["institution", "researcher", "paper"]
ResolutionStatus = Literal["matched", "unresolved", "ambiguous"]
ResolutionMethod = Literal[
    "external-identifier",
    "canonical-name",
    "alias",
    "historical-name",
    "fuzzy-name",
    "source-record-identifier",
    "manual-review",
    "insufficient-metadata",
]
SummaryResolutionMethod = ResolutionMethod | Literal["unmatched"]
SummaryResolutionReason = Literal[
    "missing-or-invalid",
    "authority-identifier-required",
    "unclassified",
]

ENTITY_TYPES: tuple[EntityType, ...] = ("institution", "researcher", "paper")
RESOLUTION_STATUSES: tuple[ResolutionStatus, ...] = (
    "matched",
    "unresolved",
    "ambiguous",
)
RESOLUTION_METHODS: tuple[SummaryResolutionMethod, ...] = (
    "external-identifier",
    "canonical-name",
    "alias",
    "historical-name",
    "fuzzy-name",
    "source-record-identifier",
    "manual-review",
    "insufficient-metadata",
    "unmatched",
)
SUMMARY_REASONS: tuple[SummaryResolutionReason, ...] = (
    "missing-or-invalid",
    "authority-identifier-required",
    "unclassified",
)
AUTHORITY_SCHEMES: dict[EntityType, frozenset[str]] = {
    "institution": frozenset(("ror",)),
    "researcher": frozenset(("orcid", "inspire-author")),
    "paper": frozenset(("doi", "arxiv", "inspire")),
}


def _typed_status(value: str) -> ResolutionStatus:
    if value not in RESOLUTION_STATUSES:
        raise ValueError(f"Unsupported identity resolution status: {value!r}")
    return value


def _typed_entity_type(value: str) -> EntityType:
    if value not in ENTITY_TYPES:
        raise ValueError(f"Unsupported identity entity type: {value!r}")
    return value


def _summary_method(value: str | None) -> SummaryResolutionMethod:
    if value in RESOLUTION_METHODS and value != "unmatched":
        return cast(SummaryResolutionMethod, value)
    return "unmatched"


def classify_resolution_reason(
    *,
    entity_type: EntityType,
    status: ResolutionStatus,
    evidence: list[dict[str, Any]],
    external_ids: list[dict[str, str]],
    attributes: dict[str, Any],
) -> SummaryResolutionReason | None:
    """Classify a non-match without exposing names or raw source payloads."""

    if status == "matched":
        return None
    evidence_reasons = {
        item.get("reason") for item in evidence if isinstance(item.get("reason"), str)
    }
    if "missing-or-invalid" in evidence_reasons:
        return "missing-or-invalid"
    has_authority_identifier = any(
        item.get("scheme", "").casefold() in AUTHORITY_SCHEMES[entity_type]
        and bool(item.get("value"))
        for item in external_ids
    )
    if attributes.get("requires_authority") is True and not has_authority_identifier:
        return "authority-identifier-required"
    return "unclassified"


def build_identity_resolution_summary(session: Session) -> dict[str, Any]:
    """Return compact aggregate counts for the public operations view.

    Resolution status and manual-review workflow status are counted independently.
    The query deliberately excludes raw names and source payloads.
    """

    rows = session.execute(
        select(
            models.IdentityResolution.id,
            models.IdentityResolution.entity_type,
            models.IdentityResolution.status,
            models.IdentityResolution.method,
            models.IdentityResolution.resolver_version,
            models.IdentityResolution.evidence,
            models.RawEntityRecord.external_ids,
            models.RawEntityRecord.attributes_json,
        ).join(
            models.RawEntityRecord,
            models.RawEntityRecord.id == models.IdentityResolution.raw_entity_record_id,
        )
    ).all()
    needs_review_ids = set(
        session.scalars(
            select(models.IdentityReview.resolution_id).where(
                models.IdentityReview.status == "needs_review"
            )
        )
    )

    status_counts: Counter[ResolutionStatus] = Counter()
    method_counts: Counter[SummaryResolutionMethod] = Counter()
    reason_counts: Counter[SummaryResolutionReason] = Counter()
    resolver_version_counts: Counter[str] = Counter()
    entity_counts: dict[EntityType, Counter[str]] = {
        entity_type: Counter() for entity_type in ENTITY_TYPES
    }

    for (
        resolution_id,
        raw_entity_type,
        raw_status,
        raw_method,
        resolver_version,
        evidence,
        external_ids,
        attributes,
    ) in rows:
        status = _typed_status(raw_status)
        entity_type = _typed_entity_type(raw_entity_type)
        method = _summary_method(raw_method)
        status_counts[status] += 1
        method_counts[method] += 1
        resolver_version_counts[resolver_version or "unversioned"] += 1
        entity_counts[entity_type]["total"] += 1
        entity_counts[entity_type][status] += 1
        if resolution_id in needs_review_ids:
            entity_counts[entity_type]["needs_review"] += 1
        reason = classify_resolution_reason(
            entity_type=entity_type,
            status=status,
            evidence=evidence,
            external_ids=external_ids,
            attributes=attributes,
        )
        if reason is not None:
            reason_counts[reason] += 1

    return {
        "total": len(rows),
        "statusCounts": {
            status: status_counts[status] for status in RESOLUTION_STATUSES
        },
        "workflowCounts": {"needsReview": len(needs_review_ids)},
        "methodCounts": [
            {"method": method, "count": method_counts[method]}
            for method in RESOLUTION_METHODS
            if method_counts[method]
        ],
        "entityTypeCounts": [
            {
                "entityType": entity_type,
                "total": entity_counts[entity_type]["total"],
                "matched": entity_counts[entity_type]["matched"],
                "unresolved": entity_counts[entity_type]["unresolved"],
                "ambiguous": entity_counts[entity_type]["ambiguous"],
                "needsReview": entity_counts[entity_type]["needs_review"],
            }
            for entity_type in ENTITY_TYPES
        ],
        "reasonCounts": [
            {"reason": reason, "count": reason_counts[reason]}
            for reason in SUMMARY_REASONS
            if reason_counts[reason]
        ],
        "resolverVersionCounts": [
            {"resolverVersion": version, "count": count}
            for version, count in sorted(resolver_version_counts.items())
        ],
    }


@dataclass(frozen=True)
class ManualReviewCandidate:
    """Internal resolution evidence eligible for deterministic manual review."""

    resolution_id: str
    raw_entity_record_id: str
    source: str
    source_record_id: str
    source_snapshot_id: str
    raw_name: str
    entity_type: EntityType
    observed_status: ResolutionStatus
    observed_method: SummaryResolutionMethod
    reason: SummaryResolutionReason | None
    confidence: float
    resolver_version: str
    workflow_status: str | None = None
    external_ids: tuple[tuple[str, str], ...] = ()
    candidate_entity_ids: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ManualReviewManifestItem:
    """One reproducibly selected case for an independent human label."""

    sample_id: str
    sample_version: str
    stratum: str
    selection_hash: str
    candidate: ManualReviewCandidate


def _candidate_stratum(candidate: ManualReviewCandidate) -> str:
    reason = candidate.reason or "not-applicable"
    return "|".join(
        (
            candidate.source,
            candidate.entity_type,
            candidate.observed_status,
            candidate.observed_method,
            reason,
        )
    )


def select_stratified_manual_review_manifest(
    candidates: list[ManualReviewCandidate],
    *,
    sample_version: str,
    per_stratum: int,
    maximum_cases: int = 100,
) -> list[ManualReviewManifestItem]:
    """Select a stable, capped sample independent of database row order."""

    if not sample_version.strip():
        raise ValueError("sample_version must be non-empty")
    if per_stratum < 1:
        raise ValueError("per_stratum must be at least one")
    if maximum_cases < 1:
        raise ValueError("maximum_cases must be at least one")
    by_stratum: dict[str, list[tuple[str, ManualReviewCandidate]]] = defaultdict(list)
    seen_resolution_ids: set[str] = set()
    for candidate in candidates:
        if candidate.resolution_id in seen_resolution_ids:
            raise ValueError(
                f"Duplicate resolution in validation sample: {candidate.resolution_id}"
            )
        seen_resolution_ids.add(candidate.resolution_id)
        digest = sha256(
            f"{sample_version}:{candidate.resolution_id}".encode()
        ).hexdigest()
        by_stratum[_candidate_stratum(candidate)].append((digest, candidate))

    selected_by_stratum: dict[str, list[tuple[str, ManualReviewCandidate]]] = {}
    for stratum in sorted(by_stratum):
        selected_by_stratum[stratum] = sorted(
            by_stratum[stratum], key=lambda item: (item[0], item[1].resolution_id)
        )[:per_stratum]
    manifest: list[ManualReviewManifestItem] = []
    for rank in range(per_stratum):
        for stratum in sorted(selected_by_stratum):
            selected = selected_by_stratum[stratum]
            if rank >= len(selected):
                continue
            selection_hash, candidate = selected[rank]
            manifest.append(
                ManualReviewManifestItem(
                    sample_id=f"{sample_version}:{selection_hash[:16]}",
                    sample_version=sample_version,
                    stratum=stratum,
                    selection_hash=selection_hash,
                    candidate=candidate,
                )
            )
            if len(manifest) == maximum_cases:
                return manifest
    return manifest


def _external_id_pairs(
    external_ids: list[dict[str, str]],
) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (item["scheme"], item["value"])
            for item in external_ids
            if item.get("scheme") and item.get("value")
        )
    )


def _candidate_ids(
    evidence: list[dict[str, Any]], review: models.IdentityReview | None
) -> tuple[str, ...]:
    identifiers = {
        str(item["candidateEntityId"])
        for item in evidence
        if item.get("candidateEntityId")
    }
    if review is not None:
        identifiers.update(review.candidate_entity_ids)
    return tuple(sorted(identifiers))


def build_manual_review_manifest(
    session: Session,
    *,
    sample_version: str,
    per_stratum: int,
    maximum_cases: int = 100,
) -> list[ManualReviewManifestItem]:
    """Build a deterministic internal review manifest from persisted evidence."""

    rows = session.execute(
        select(
            models.IdentityResolution,
            models.RawEntityRecord,
            models.IdentityReview,
        )
        .join(
            models.RawEntityRecord,
            models.RawEntityRecord.id == models.IdentityResolution.raw_entity_record_id,
        )
        .outerjoin(
            models.IdentityReview,
            models.IdentityReview.resolution_id == models.IdentityResolution.id,
        )
    ).all()
    candidates: list[ManualReviewCandidate] = []
    for resolution, raw_record, review in rows:
        status = _typed_status(resolution.status)
        entity_type = _typed_entity_type(resolution.entity_type)
        reason = classify_resolution_reason(
            entity_type=entity_type,
            status=status,
            evidence=resolution.evidence,
            external_ids=raw_record.external_ids,
            attributes=raw_record.attributes_json,
        )
        candidates.append(
            ManualReviewCandidate(
                resolution_id=resolution.id,
                raw_entity_record_id=raw_record.id,
                source=raw_record.source,
                source_record_id=raw_record.source_record_id,
                source_snapshot_id=raw_record.source_snapshot_id,
                raw_name=raw_record.raw_name,
                entity_type=entity_type,
                observed_status=status,
                observed_method=_summary_method(resolution.method),
                reason=reason,
                confidence=resolution.confidence,
                resolver_version=resolution.resolver_version,
                workflow_status=review.status if review is not None else None,
                external_ids=_external_id_pairs(raw_record.external_ids),
                candidate_entity_ids=_candidate_ids(resolution.evidence, review),
                evidence=tuple(dict(item) for item in resolution.evidence),
            )
        )
    return select_stratified_manual_review_manifest(
        candidates,
        sample_version=sample_version,
        per_stratum=per_stratum,
        maximum_cases=maximum_cases,
    )


@dataclass(frozen=True)
class IdentityValidationPrediction:
    case_id: str
    status: ResolutionStatus
    canonical_entity_id: str | None
    confidence: float

    def __post_init__(self) -> None:
        _validate_decision(self.status, self.canonical_entity_id)
        if not 0 <= self.confidence <= 1:
            raise ValueError("Prediction confidence must be between zero and one")


@dataclass(frozen=True)
class IdentityValidationLabel:
    case_id: str
    status: ResolutionStatus
    canonical_entity_id: str | None = None

    def __post_init__(self) -> None:
        _validate_decision(self.status, self.canonical_entity_id)


@dataclass(frozen=True)
class CalibrationBin:
    lower_bound: float
    upper_bound: float
    count: int
    mean_confidence: float
    accuracy: float


@dataclass(frozen=True)
class ConfidenceCalibration:
    sample_size: int
    brier_score: float
    expected_calibration_error: float
    bins: tuple[CalibrationBin, ...]


@dataclass(frozen=True)
class IdentityValidationReport:
    sample_size: int
    predicted_matched_count: int
    expected_matched_count: int
    correct_match_count: int
    minimum_metric_cases: int
    minimum_calibration_cases: int
    precision: float | None
    recall: float | None
    unresolved_rate: float | None
    ambiguous_rate: float | None
    decision_accuracy: float | None
    calibration: ConfidenceCalibration | None


def _validate_decision(
    status: ResolutionStatus, canonical_entity_id: str | None
) -> None:
    if status == "matched" and not canonical_entity_id:
        raise ValueError("A matched decision requires a canonical entity identifier")
    if status != "matched" and canonical_entity_id is not None:
        raise ValueError("A non-matched decision cannot name a canonical entity")


def _decisions_match(
    prediction: IdentityValidationPrediction, label: IdentityValidationLabel
) -> bool:
    return prediction.status == label.status and (
        prediction.status != "matched"
        or prediction.canonical_entity_id == label.canonical_entity_id
    )


def _calibration_report(
    decisions: list[tuple[float, bool]], *, bin_count: int
) -> ConfidenceCalibration:
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(bin_count)]
    for confidence, correct in decisions:
        bin_index = min(int(confidence * bin_count), bin_count - 1)
        bins[bin_index].append((confidence, correct))

    populated_bins: list[CalibrationBin] = []
    expected_calibration_error = 0.0
    sample_size = len(decisions)
    for index, values in enumerate(bins):
        if not values:
            continue
        mean_confidence = sum(value[0] for value in values) / len(values)
        accuracy = sum(1.0 for _, correct in values if correct) / len(values)
        expected_calibration_error += (
            len(values) / sample_size * abs(accuracy - mean_confidence)
        )
        populated_bins.append(
            CalibrationBin(
                lower_bound=index / bin_count,
                upper_bound=(index + 1) / bin_count,
                count=len(values),
                mean_confidence=mean_confidence,
                accuracy=accuracy,
            )
        )
    brier_score = (
        sum((confidence - float(correct)) ** 2 for confidence, correct in decisions)
        / sample_size
    )
    return ConfidenceCalibration(
        sample_size=sample_size,
        brier_score=brier_score,
        expected_calibration_error=expected_calibration_error,
        bins=tuple(populated_bins),
    )


def calculate_identity_validation_report(
    predictions: list[IdentityValidationPrediction],
    labels: list[IdentityValidationLabel],
    *,
    minimum_metric_cases: int = 30,
    minimum_calibration_cases: int = 30,
    calibration_bin_count: int = 5,
) -> IdentityValidationReport:
    """Calculate evidence only from independent labels with explicit sufficiency."""

    if minimum_metric_cases < 1:
        raise ValueError("minimum_metric_cases must be at least one")
    if minimum_calibration_cases < 1:
        raise ValueError("minimum_calibration_cases must be at least one")
    if calibration_bin_count < 1:
        raise ValueError("calibration_bin_count must be at least one")

    predictions_by_id: dict[str, IdentityValidationPrediction] = {}
    for prediction in predictions:
        if prediction.case_id in predictions_by_id:
            raise ValueError(f"Duplicate prediction case: {prediction.case_id}")
        predictions_by_id[prediction.case_id] = prediction
    labels_by_id: dict[str, IdentityValidationLabel] = {}
    for label in labels:
        if label.case_id in labels_by_id:
            raise ValueError(f"Duplicate label case: {label.case_id}")
        labels_by_id[label.case_id] = label
    if predictions_by_id.keys() != labels_by_id.keys():
        raise ValueError("Predictions and labels must cover the same case identifiers")

    sample_size = len(labels_by_id)
    predicted_matched = [
        prediction for prediction in predictions if prediction.status == "matched"
    ]
    expected_matched_count = sum(1 for label in labels if label.status == "matched")
    correct_match_count = sum(
        1
        for prediction in predicted_matched
        if prediction.canonical_entity_id
        == labels_by_id[prediction.case_id].canonical_entity_id
        and labels_by_id[prediction.case_id].status == "matched"
    )
    precision = (
        correct_match_count / len(predicted_matched)
        if len(predicted_matched) >= minimum_metric_cases
        else None
    )
    recall = (
        correct_match_count / expected_matched_count
        if expected_matched_count >= minimum_metric_cases
        else None
    )
    if sample_size >= minimum_metric_cases:
        unresolved_rate = (
            sum(1 for item in predictions if item.status == "unresolved") / sample_size
        )
        ambiguous_rate = (
            sum(1 for item in predictions if item.status == "ambiguous") / sample_size
        )
        decision_accuracy = (
            sum(
                1
                for item in predictions
                if _decisions_match(item, labels_by_id[item.case_id])
            )
            / sample_size
        )
    else:
        unresolved_rate = None
        ambiguous_rate = None
        decision_accuracy = None

    calibration_decisions = [
        (
            prediction.confidence,
            prediction.canonical_entity_id
            == labels_by_id[prediction.case_id].canonical_entity_id
            and labels_by_id[prediction.case_id].status == "matched",
        )
        for prediction in predicted_matched
    ]
    calibration = (
        _calibration_report(calibration_decisions, bin_count=calibration_bin_count)
        if len(calibration_decisions) >= minimum_calibration_cases
        else None
    )
    return IdentityValidationReport(
        sample_size=sample_size,
        predicted_matched_count=len(predicted_matched),
        expected_matched_count=expected_matched_count,
        correct_match_count=correct_match_count,
        minimum_metric_cases=minimum_metric_cases,
        minimum_calibration_cases=minimum_calibration_cases,
        precision=precision,
        recall=recall,
        unresolved_rate=unresolved_rate,
        ambiguous_rate=ambiguous_rate,
        decision_accuracy=decision_accuracy,
        calibration=calibration,
    )
