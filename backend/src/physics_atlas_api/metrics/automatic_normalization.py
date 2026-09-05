"""Derive exact normalization membership from an already certified window.

No new scientific approval is inferred here: every raw result and its complete
source window must already pass their existing contracts. Include insufficient
and missing peers rather than selecting only convenient successful results.
"""

from dataclasses import dataclass

from ..certification import CertificationError, CertifiedMetricWindow, canonical_digest
from .presentation import (
    CertifiedMetricCalculation,
    NormalizationPopulationEvidence,
    _normalization_cohort_key,
    _normalization_population_content_digest,
)

AUTOMATIC_NORMALIZATION_POPULATION_VERSION = (
    "certified-window-normalization-population-v1"
)


@dataclass(frozen=True)
class AutomaticNormalizationPopulationEvidence(NormalizationPopulationEvidence):
    source_window: CertifiedMetricWindow
    calculations: tuple[CertifiedMetricCalculation, ...]
    automatic_rule_version: str = AUTOMATIC_NORMALIZATION_POPULATION_VERSION


def derive_normalization_population(
    source_window: CertifiedMetricWindow,
    calculations: tuple[CertifiedMetricCalculation, ...],
) -> AutomaticNormalizationPopulationEvidence:
    """Require every represented peer, not a caller-selected approval flag."""
    if not isinstance(source_window, CertifiedMetricWindow):
        raise CertificationError("automatic normalization requires a certified window")
    source_window.__post_init__()
    if source_window.certification.state != "certified":
        raise CertificationError(
            "automatic normalization source window is not certified"
        )
    if not calculations or any(
        not isinstance(item, CertifiedMetricCalculation) for item in calculations
    ):
        raise CertificationError(
            "automatic normalization requires certified calculations"
        )
    for item in calculations:
        item.__post_init__()
        if item.partition.window_proof != source_window:
            raise CertificationError(
                "normalization peers do not share the exact source window"
            )
    key = _normalization_cohort_key(calculations[0].calculation)
    if any(_normalization_cohort_key(item.calculation) != key for item in calculations):
        raise CertificationError("automatic normalization mixes comparison cohorts")
    if any(item.thresholds != calculations[0].thresholds for item in calculations):
        raise CertificationError(
            "automatic normalization mixes threshold configurations"
        )
    _, entity_type, field_id, *_ = key
    expected_ids = {
        entity_id
        for year in source_window.source_years
        for paper in year.evidence.paper_projections
        if dict(paper.field_weights).get(field_id, 0) > 0
        for kind, entity_id, share in paper.entity_shares
        if kind == entity_type and share > 0
    }
    actual_ids = tuple(item.calculation.entity_id for item in calculations)
    if (
        not expected_ids
        or len(set(actual_ids)) != len(actual_ids)
        or set(actual_ids) != expected_ids
    ):
        raise CertificationError(
            "normalization calculations must cover every source-window peer, "
            "including missing results"
        )
    ids = tuple(sorted(expected_ids))
    digests = tuple(
        sorted(
            (item.calculation.entity_id, item.calculation.certification_manifest_digest)
            for item in calculations
        )
    )
    return AutomaticNormalizationPopulationEvidence(
        cohort_key=key,
        entity_ids=ids,
        calculation_certification_digests=digests,
        source_manifest_digest=_normalization_population_content_digest(
            key, ids, digests
        ),
        review_state="automatic-evidence-derived",
        reviewed_by=None,
        reviewed_at=None,
        source_window=source_window,
        calculations=tuple(
            sorted(calculations, key=lambda item: item.calculation.entity_id)
        ),
    )


def validate_automatic_normalization_population(
    evidence: AutomaticNormalizationPopulationEvidence,
) -> None:
    expected = derive_normalization_population(
        evidence.source_window, evidence.calculations
    )
    if evidence != expected or canonical_digest(evidence) != canonical_digest(expected):
        raise CertificationError(
            "automatic normalization population does not reconstruct"
        )
