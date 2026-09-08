"""Derive exact normalization membership from an already certified window.

No new scientific approval is inferred here: every raw result and its complete
source window must already pass their existing contracts. Include insufficient
and missing peers rather than selecting only convenient successful results.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..certification import CertificationError, CertifiedMetricWindow, canonical_digest
from ..certification.fields import branch_diversity_field_projection
from ..certification.years import ConditionalObservedSourceYearEvidence
from ..fields import PHYSICS_FIELD_ONTOLOGY_V1
from .presentation import (
    CertifiedMetricCalculation,
    CertifiedNormalizationPopulation,
    NormalizationPopulationEvidence,
    _calculation_population_coverage_policy,
    _normalization_cohort_key,
    _normalization_population_content_digest,
)

if TYPE_CHECKING:
    from ..certification.launch_calculations import LaunchPeerIneligibility

AUTOMATIC_NORMALIZATION_POPULATION_VERSION = (
    "certified-window-normalization-population-v1"
)
CONDITIONAL_NORMALIZATION_POPULATION_VERSION = (
    "conditional-source-peer-normalization-v1"
)


@dataclass(frozen=True)
class AutomaticNormalizationPopulationEvidence(NormalizationPopulationEvidence):
    source_window: CertifiedMetricWindow
    calculations: tuple[CertifiedMetricCalculation, ...]
    automatic_rule_version: str = AUTOMATIC_NORMALIZATION_POPULATION_VERSION


@dataclass(frozen=True, kw_only=True)
class ConditionalNormalizationPopulationEvidence(
    AutomaticNormalizationPopulationEvidence
):
    source_entity_ids: tuple[str, ...]
    ineligible_peers: tuple[LaunchPeerIneligibility, ...]
    automatic_rule_version: str = CONDITIONAL_NORMALIZATION_POPULATION_VERSION


def derive_normalization_population(
    source_window: CertifiedMetricWindow,
    calculations: tuple[CertifiedMetricCalculation, ...],
    *,
    ineligible_peers: tuple[LaunchPeerIneligibility, ...] = (),
) -> AutomaticNormalizationPopulationEvidence:
    """Require every represented peer, not a caller-selected approval flag."""
    from ..certification.launch_calculations import LaunchPeerIneligibility

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
    if (
        len({_calculation_population_coverage_policy(item) for item in calculations})
        != 1
    ):
        raise CertificationError(
            "automatic normalization mixes population coverage policies"
        )
    if any(item.thresholds != calculations[0].thresholds for item in calculations):
        raise CertificationError(
            "automatic normalization mixes threshold configurations"
        )
    metric_id, entity_type, field_id, *_ = key
    branch_diversity = (
        metric_id == "research_diversity"
        and PHYSICS_FIELD_ONTOLOGY_V1.contains(field_id)
        and PHYSICS_FIELD_ONTOLOGY_V1.get(field_id).node_kind == "branch"
    )
    expected_ids = {
        entity_id
        for year in source_window.source_years
        for paper in year.evidence.paper_projections
        if (
            branch_diversity_field_projection(field_id, paper.field_weights)[0]
            if branch_diversity
            else dict(paper.field_weights).get(field_id, 0)
        )
        > 0
        for kind, entity_id, share in paper.entity_shares
        if kind == entity_type and share > 0
    }
    actual_ids = tuple(item.calculation.entity_id for item in calculations)
    conditional = all(
        isinstance(year.evidence, ConditionalObservedSourceYearEvidence)
        for year in source_window.source_years
    )
    if ineligible_peers and not conditional:
        raise CertificationError(
            "only conditional source scope permits ineligible peer proofs"
        )
    for peer in ineligible_peers:
        if not isinstance(peer, LaunchPeerIneligibility):
            raise CertificationError(
                "normalization exclusions need exact scientific proofs"
            )
        peer.__post_init__()
        if peer.source_window != source_window or peer.field_id != field_id:
            raise CertificationError(
                "normalization excluded peer belongs to another scope"
            )
    excluded_ids = tuple(item.entity_id for item in ineligible_peers)
    if (
        not expected_ids
        or len(set(actual_ids)) != len(actual_ids)
        or len(set(excluded_ids)) != len(excluded_ids)
        or set(actual_ids) & set(excluded_ids)
        or set(actual_ids) | set(excluded_ids) != expected_ids
    ):
        raise CertificationError(
            "normalization calculations must cover every source-window peer, "
            "including missing results"
        )
    ids = tuple(sorted(actual_ids))
    digests = tuple(
        sorted(
            (item.calculation.entity_id, item.calculation.certification_manifest_digest)
            for item in calculations
        )
    )
    evidence = AutomaticNormalizationPopulationEvidence(
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
    if conditional:
        return ConditionalNormalizationPopulationEvidence(
            **{
                key: value
                for key, value in vars(evidence).items()
                if key != "automatic_rule_version"
            },
            source_entity_ids=tuple(sorted(expected_ids)),
            ineligible_peers=tuple(
                sorted(ineligible_peers, key=lambda item: item.entity_id)
            ),
        )
    return evidence


def validate_automatic_normalization_population(
    evidence: AutomaticNormalizationPopulationEvidence,
) -> None:
    expected = derive_normalization_population(
        evidence.source_window,
        evidence.calculations,
        ineligible_peers=(
            evidence.ineligible_peers
            if isinstance(evidence, ConditionalNormalizationPopulationEvidence)
            else ()
        ),
    )
    if evidence != expected or canonical_digest(evidence) != canonical_digest(expected):
        raise CertificationError(
            "automatic normalization population does not reconstruct"
        )


def conditional_normalization_disclosure(
    population: CertifiedNormalizationPopulation,
) -> dict[str, object] | None:
    """Compact per-cohort disclosure, without repeating full peer traces in JSON."""
    evidence = population.evidence
    if not isinstance(evidence, ConditionalNormalizationPopulationEvidence):
        return None
    population.__post_init__()
    reasons: Counter[str] = Counter()
    for peer in evidence.ineligible_peers:
        for failure in peer.failures:
            reasons[
                f"{failure.subject_type}:{failure.evidence_kind}:{failure.state}"
            ] += 1
    return {
        "policyVersion": CONDITIONAL_NORMALIZATION_POPULATION_VERSION,
        "sourcePeerCount": len(evidence.source_entity_ids),
        "eligiblePeerCount": len(evidence.entity_ids),
        "numericRawPeerCount": sum(
            item.calculation.raw_value is not None for item in evidence.calculations
        ),
        "excludedPeerCount": len(evidence.ineligible_peers),
        "excludedReasonCounts": dict(sorted(reasons.items())),
        "peerInventoryDigest": canonical_digest(
            (
                evidence.source_entity_ids,
                evidence.entity_ids,
                tuple(
                    (item.entity_id, item.partition_digest, item.failures)
                    for item in evidence.ineligible_peers
                ),
            )
        ),
        "interpretation": (
            "conditional on certification-eligible observed peers; "
            "not full-source completeness"
        ),
    }
