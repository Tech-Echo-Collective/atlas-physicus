"""Pure source-bound bridge into the existing certified Metric System v1.

The caller supplies certified source windows, not approval flags or fabricated
metric inputs. Nothing is acquired, persisted, activated or silently excluded.
An unsupported positive paper remains a certification blocker; small cohorts
remain explicit missing calculator results.
"""

import math
from collections import Counter
from dataclasses import dataclass, fields, replace
from datetime import date, datetime
from typing import Literal, cast

from ..attribution import FRACTIONAL_ATTRIBUTION_V1
from ..fields import PHYSICS_FIELD_ONTOLOGY_VERSION, PROVIDER_FIELD_MAPPING_VERSION
from ..metrics.automatic_normalization import derive_normalization_population
from ..metrics.calculators import (
    AttributedPaperEvidence,
    MetricCoverageEvidence,
    MetricEntityType,
    MetricPartitionInput,
    calculate_activity_raw,
    calculate_connectivity,
    calculate_diversity,
    calculate_impact_raw,
    calculate_momentum_raw,
)
from ..metrics.presentation import (
    AtlasScaleObservation,
    CertifiedMetricCalculation,
    apply_atlas_scale,
    bind_metric_calculation,
    certify_normalization_population,
)
from .automation import (
    automatic_known_researcher_decision,
    automatic_paper_identity_decision,
)
from .citations import (
    CITATION_POLICY_VERSION,
    CitationObservationCertification,
    impact_comparable_paper_ids,
)
from .contracts import (
    CertificationError,
    CertificationState,
    CertifiedMetricPartition,
    CoverageCertification,
    CoveragePopulationEvidence,
    EvidenceCertificationDecision,
    EvidenceKind,
    canonical_digest,
)
from .coverage import certify_coverage
from .fields import (
    BRANCH_DIVERSITY_FIELD_BINDING,
    AutomaticFieldBinding,
    automatic_field_decision,
    branch_diversity_field_projection,
)
from .launch_metric_coverage import launch_relationship_status
from .launch_years import LaunchStructuralDecision
from .materialization import (
    _explicit_missing_is_usable,
    build_certified_metric_partition,
)
from .measurement_windows import (
    SESSION_CITATION_POLICY_VERSION,
    CertifiedSessionCitationCohort,
    session_comparison_key,
)
from .populations import (
    OBSERVED_ATTRIBUTION_COVERAGE_VERSION,
    CertifiedMetricPopulation,
    derive_metric_population,
    metric_population_coverage_ledger,
)
from .projections import paper_evidence_value_digest
from .rules import (
    evidence_rule_version,
    required_coverage_evidence,
    required_paper_evidence,
)
from .years import (
    CertifiedMetricWindow,
    CertifiedSourceYear,
    ConditionalObservedSourceYearEvidence,
    SourceYearPaperProjection,
    certify_source_year,
)

LAUNCH_CALCULATION_BRIDGE_VERSION = "source-bound-launch-calculations-v1"
CONDITIONAL_LAUNCH_PEER_VERSION = "conditional-source-peer-eligibility-v1"


@dataclass(frozen=True)
class LaunchPaperBinding:
    entity_type: MetricEntityType
    entity_id: str
    field_id: str
    branch_diversity: bool = False
    citation_observation: CitationObservationCertification | None = None


def _paper(
    proof: LaunchStructuralDecision, binding: LaunchPaperBinding
) -> AttributedPaperEvidence:
    if not isinstance(proof, LaunchStructuralDecision):
        raise CertificationError("launch calculation requires typed source evidence")
    proof.__post_init__()
    if proof.evidence_kind != "provenance-completeness" or proof.state != "certified":
        raise CertificationError(
            "launch calculation source provenance is not certified"
        )
    source = proof.source_projection
    if (
        proof.source_paper.component.status != "matched"
        or len(proof.source_paper.occurrences) != 1
    ):
        raise CertificationError(
            "launch calculation cannot choose unresolved identities"
        )
    occurrence = proof.source_paper.occurrences[0]
    facts = occurrence.source_facts
    document_type = occurrence.identity.document_type
    if document_type != "article":
        raise CertificationError(
            "launch calculation requires source-verified article type"
        )
    entity_weight = math.fsum(
        mass
        for kind, entity_id, mass in source.entity_shares
        if kind == binding.entity_type and entity_id == binding.entity_id
    )
    field_weight, categories = (
        branch_diversity_field_projection(binding.field_id, source.field_weights)
        if binding.branch_diversity
        else (dict(source.field_weights).get(binding.field_id, 0.0), ())
    )
    if entity_weight * field_weight <= 0:
        raise CertificationError(
            "launch calculation requires actual positive known mass"
        )
    count: float | None = None
    observed_at: date | None = None
    observation = binding.citation_observation
    if observation is not None:
        observation.__post_init__()
        if (
            observation.evidence.dataset_version != proof.dataset_version
            or observation.evidence.acquisition_scope != proof.acquisition_scope
            or observation.cohort_key
            != (binding.field_id, source.publication_date.year, document_type)
            or observation.paper_id != source.paper_id
            or observation.evidence.publication_date != source.publication_date
            or observation.state != "certified"
        ):
            raise CertificationError(
                "launch citation cohort differs from source membership"
            )
        count = observation.non_self_citation_count
        if observation.evidence.observed_at is not None:
            observed_at = observation.evidence.observed_at.date()
    partners = tuple(
        sorted(
            identifier
            for kind, identifier, mass in source.entity_shares
            if kind == binding.entity_type
            and identifier != binding.entity_id
            and mass > 0
        )
    )
    return AttributedPaperEvidence(
        paper_id=source.paper_id,
        publication_date=source.publication_date,
        document_type=document_type,
        attribution_weight=entity_weight * field_weight,
        researcher_ids=facts.researcher_ids,
        citation_count=count,
        citation_observed_at=observed_at,
        collaborative=launch_relationship_status(proof, "researcher"),
        cross_institution=launch_relationship_status(proof, "institution"),
        international=launch_relationship_status(proof, "country"),
        partner_entity_ids=partners,
        category_weights=categories,
    )


def _decision_view(
    proof: LaunchStructuralDecision, binding: LaunchPaperBinding, kind: EvidenceKind
) -> EvidenceCertificationDecision:
    paper = _paper(proof, binding)
    if kind not in {
        "canonical-paper-identity",
        "paper-time-affiliation",
        "canonical-institution",
        "collaboration-relationship",
        "provenance-completeness",
        "citation-observation",
        "citation-cutoff-compatibility",
    }:
        raise CertificationError("unsupported launch paper decision kind")
    missing = (
        kind == "citation-observation"
        and paper.citation_count is None
        or kind == "citation-cutoff-compatibility"
        and paper.citation_observed_at is None
        or kind == "collaboration-relationship"
        and getattr(
            paper,
            {
                "researcher": "collaborative",
                "institution": "cross_institution",
                "country": "international",
            }[binding.entity_type],
        )
        is None
    )
    refs = set(proof.evidence)
    if binding.citation_observation is not None:
        ref = binding.citation_observation.evidence.source_reference
        if ref is not None:
            refs.add(ref)
    return EvidenceCertificationDecision(
        subject_type="paper",
        subject_id=paper.paper_id,
        evidence_kind=kind,
        state="insufficient_evidence" if missing else "certified",
        rule_version=evidence_rule_version(kind),
        dataset_version=proof.dataset_version,
        acquisition_scope=proof.acquisition_scope,
        evidence=tuple(sorted(refs, key=canonical_digest)),
        certified_value_digest=paper_evidence_value_digest(binding, paper, kind),
        reasons=("source-bound formula input remains explicitly missing",)
        if missing
        else (),
    )


@dataclass(frozen=True, kw_only=True)
class LaunchPaperDecision(EvidenceCertificationDecision):
    source_proof: LaunchStructuralDecision
    binding: LaunchPaperBinding
    producer_version: str = LAUNCH_CALCULATION_BRIDGE_VERSION

    def __post_init__(self) -> None:
        EvidenceCertificationDecision.__post_init__(self)
        expected = _decision_view(self.source_proof, self.binding, self.evidence_kind)
        if self.producer_version != LAUNCH_CALCULATION_BRIDGE_VERSION or any(
            getattr(self, item.name) != getattr(expected, item.name)
            for item in fields(EvidenceCertificationDecision)
        ):
            raise CertificationError(
                "launch paper decision differs from source evidence"
            )


def _source_citation_decision(
    source: SourceYearPaperProjection,
    observations: tuple[CitationObservationCertification, ...],
    *,
    dataset_version: str,
    acquisition_scope: str,
) -> EvidenceCertificationDecision:
    by_field = {item.evidence.field_id: item for item in observations}
    if len(by_field) != len(observations):
        raise CertificationError("source citation proof repeats a field observation")
    expected_fields = {key for key, weight in source.field_weights if weight > 0}
    for item in observations:
        item.__post_init__()
        if (
            item.paper_id != source.paper_id
            or item.evidence.publication_date != source.publication_date
            or item.evidence.dataset_version != dataset_version
            or item.evidence.acquisition_scope != acquisition_scope
            or item.evidence.document_type != "article"
            or item.evidence.field_id not in expected_fields
        ):
            raise CertificationError("source citation proof changes paper membership")
    supported = (
        bool(expected_fields)
        and set(by_field) == expected_fields
        and all(item.state == "certified" for item in observations)
    )
    refs = set(source.occurrence_references)
    refs.update(
        item.evidence.source_reference
        for item in observations
        if item.evidence.source_reference is not None
    )
    return EvidenceCertificationDecision(
        subject_type="coverage-unit",
        subject_id=source.paper_id,
        evidence_kind="citation-observation",
        state="certified" if supported else "insufficient_evidence",
        rule_version=evidence_rule_version("citation-observation"),
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        evidence=tuple(sorted(refs, key=canonical_digest)),
        certified_value_digest=canonical_digest((source, observations)),
        reasons=()
        if supported
        else ("source paper lacks comparable measured citations in its known fields",),
    )


@dataclass(frozen=True, kw_only=True)
class LaunchSourceCitationDecision(EvidenceCertificationDecision):
    source_projection: SourceYearPaperProjection
    observations: tuple[CitationObservationCertification, ...]
    producer_version: str = LAUNCH_CALCULATION_BRIDGE_VERSION

    def __post_init__(self) -> None:
        EvidenceCertificationDecision.__post_init__(self)
        expected = _source_citation_decision(
            self.source_projection,
            self.observations,
            dataset_version=self.dataset_version,
            acquisition_scope=self.acquisition_scope,
        )
        if self.producer_version != LAUNCH_CALCULATION_BRIDGE_VERSION or any(
            getattr(self, item.name) != getattr(expected, item.name)
            for item in fields(EvidenceCertificationDecision)
        ):
            raise CertificationError("source citation decision cannot reconstruct")


def certify_launch_citation_coverage(
    source_year: CertifiedSourceYear,
    citation_cohorts: tuple[CertifiedSessionCitationCohort, ...],
    *,
    evaluation_cutoff: datetime,
) -> CertifiedSourceYear:
    """Add actual measured citation coverage without replacing frozen membership.

    One source paper remains one denominator unit. A paper with a missing
    comparable known-field citation stays missing; no field or paper is dropped.
    """
    if not isinstance(source_year, CertifiedSourceYear):
        raise CertificationError(
            "citation coverage requires certified source membership"
        )
    source_year.__post_init__()
    if (
        source_year.state != "certified"
        or "citation-observation" in source_year.required_coverage_kinds
    ):
        raise CertificationError(
            "citation coverage requires original certified source authority"
        )
    session_comparison_key(citation_cohorts)
    if (
        evaluation_cutoff.tzinfo is None
        or evaluation_cutoff.utcoffset() is None
        or evaluation_cutoff < source_year.cutoff
        or any(item.ended_at > evaluation_cutoff for item in citation_cohorts)
        or any(
            source_year not in item.population.source_years for item in citation_cohorts
        )
    ):
        raise CertificationError(
            "citation coverage differs from frozen source or measurement horizon"
        )
    source_ids = {item.paper_id for item in source_year.evidence.paper_projections}
    by_paper: dict[str, list[CitationObservationCertification]] = {}
    for cohort in citation_cohorts:
        for observation in cohort.observations:
            if observation.paper_id in source_ids:
                by_paper.setdefault(observation.paper_id, []).append(observation)
    decisions = []
    for source in sorted(
        source_year.evidence.paper_projections, key=lambda item: item.paper_id
    ):
        observations = tuple(
            sorted(
                by_paper.get(source.paper_id, ()),
                key=lambda item: item.evidence.field_id,
            )
        )
        base = _source_citation_decision(
            source,
            observations,
            dataset_version=source_year.dataset_version,
            acquisition_scope=source_year.acquisition_scope,
        )
        decisions.append(
            LaunchSourceCitationDecision(
                **vars(base), source_projection=source, observations=observations
            )
        )
    coverage = certify_coverage(
        "citation-observation",
        tuple(decisions),
        CoveragePopulationEvidence(
            evidence_kind="citation-observation",
            units=tuple((item.subject_id, 1.0) for item in decisions),
            formula_inputs=tuple(
                (item.subject_id, 1.0)
                for item in decisions
                if item.state == "certified"
            ),
            source_manifest_digest=source_year.certification.canonical_paper_population_digest,
        ),
    )
    return certify_source_year(
        replace(
            source_year.evidence,
            cutoff=evaluation_cutoff,
            acquisition_plan=replace(
                source_year.evidence.acquisition_plan, cutoff=evaluation_cutoff
            ),
            required_coverage_kinds=(
                *source_year.required_coverage_kinds,
                "citation-observation",
            ),
            coverage_decisions=(*source_year.evidence.coverage_decisions, *decisions),
        ),
        (*source_year.coverage, coverage),
    )


def validate_launch_citation_window(window: CertifiedMetricWindow) -> None:
    """Bind compact source citation decisions to this window's actual session.

    Called after the window reconstructs. Do not recursively validate the window
    here, and do not expand a whole citation cohort inside each paper decision.
    Legacy source-coverage producers are unaffected.
    """
    decisions = tuple(
        item
        for year in window.source_years
        for item in year.evidence.coverage_decisions
        if isinstance(item, LaunchSourceCitationDecision)
    )
    if not decisions:
        return
    if window.certification.metric_id != "research_impact" or not all(
        isinstance(item, CertifiedSessionCitationCohort)
        for item in window.citation_cohorts
    ):
        raise CertificationError("launch citation coverage requires its actual session")
    cohorts = cast(tuple[CertifiedSessionCitationCohort, ...], window.citation_cohorts)
    session_comparison_key(cohorts)
    observed: dict[str, list[CitationObservationCertification]] = {}
    for cohort in cohorts:
        for item in cohort.observations:
            observed.setdefault(item.paper_id, []).append(item)
    expected_sources = {
        item.paper_id: item
        for year in window.source_years
        for item in year.evidence.paper_projections
    }
    if len(decisions) != len(expected_sources) or {
        item.subject_id for item in decisions
    } != set(expected_sources):
        raise CertificationError("launch citation coverage omits source-window papers")
    for decision in decisions:
        expected = tuple(
            sorted(
                observed.get(decision.subject_id, ()),
                key=lambda item: item.evidence.field_id,
            )
        )
        if (
            decision.source_projection != expected_sources[decision.subject_id]
            or decision.observations != expected
        ):
            raise CertificationError(
                "source citation coverage differs from measured session evidence"
            )


def build_launch_metric_partition(
    window: CertifiedMetricWindow, *, entity_id: str, field_id: str
) -> CertifiedMetricPartition[MetricPartitionInput]:
    """Consume all supported known papers; never select favorable formula inputs."""
    return _materialize_launch_partition(
        _launch_partition_inputs(window, entity_id=entity_id, field_id=field_id)
    )


@dataclass(frozen=True)
class _LaunchPartitionInputs:
    partition: MetricPartitionInput
    decisions: tuple[EvidenceCertificationDecision, ...]
    coverage: tuple[CoverageCertification, ...]
    window: CertifiedMetricWindow
    population: CertifiedMetricPopulation


def _materialize_launch_partition(
    inputs: _LaunchPartitionInputs,
) -> CertifiedMetricPartition[MetricPartitionInput]:
    return build_certified_metric_partition(
        inputs.partition,
        metric_id=inputs.window.certification.metric_id,
        decisions=inputs.decisions,
        coverage=inputs.coverage,
        window=inputs.window,
        population=inputs.population,
    )


def _launch_partition_inputs(
    window: CertifiedMetricWindow, *, entity_id: str, field_id: str
) -> _LaunchPartitionInputs:
    if not isinstance(window, CertifiedMetricWindow):
        raise CertificationError(
            "launch calculation requires a certified metric window"
        )
    window.__post_init__()
    context = window.certification
    population = derive_metric_population(
        window,
        entity_id=entity_id,
        field_id=field_id,
        assessed_at=window.cutoff,
        coverage_policy=OBSERVED_ATTRIBUTION_COVERAGE_VERSION,
    )
    cohort_by_key = {}
    for cohort in window.citation_cohorts:
        if not isinstance(cohort, CertifiedSessionCitationCohort):
            raise CertificationError(
                "launch bridge requires actual citation measurement sessions"
            )
        if cohort.cohort_key in cohort_by_key:
            raise CertificationError("launch bridge repeats a citation cohort")
        cohort_by_key[cohort.cohort_key] = {
            item.paper_id: item for item in cohort.observations
        }
    proofs = {
        item.subject_id: item
        for year in window.source_years
        for item in year.evidence.structural_decisions
        if isinstance(item, LaunchStructuralDecision)
        and item.evidence_kind == "provenance-completeness"
    }
    source_projections = {
        item.paper_id: item
        for year in window.source_years
        for item in year.evidence.paper_projections
    }
    if set(proofs) != set(source_projections) or any(
        proof.source_projection != source_projections[key]
        for key, proof in proofs.items()
    ):
        raise CertificationError("launch bridge lacks exact complete source provenance")
    papers: list[AttributedPaperEvidence] = []
    decisions: list[EvidenceCertificationDecision] = []
    for projection in population.certification.evidence.projections:
        if projection.status != "included":
            continue
        proof = proofs[projection.paper_id]
        binding = LaunchPaperBinding(
            cast(MetricEntityType, context.entity_type),
            entity_id,
            field_id,
            branch_diversity=context.metric_id == "research_diversity",
            citation_observation=cohort_by_key.get(
                (field_id, projection.publication_date.year, "article"), {}
            ).get(projection.paper_id),
        )
        paper = _paper(proof, binding)
        papers.append(paper)
        facts = proof.source_paper.occurrences[0].source_facts
        for kind in required_paper_evidence(context.metric_id, context.entity_type):
            if kind == "researcher-identity" and context.entity_type in {
                "institution",
                "country",
            }:
                decisions.append(
                    automatic_known_researcher_decision(
                        facts,
                        entity_type=cast(
                            Literal["institution", "country"], context.entity_type
                        ),
                    )
                )
            elif kind in {"publication-metric-date", "researcher-identity"}:
                decisions.append(
                    automatic_paper_identity_decision(facts, evidence_kind=kind)
                )
            elif kind in {"field-classification", "field-weight-conservation"}:
                decisions.append(
                    automatic_field_decision(
                        proof.source_paper.field_evidence,
                        binding=AutomaticFieldBinding(
                            BRANCH_DIVERSITY_FIELD_BINDING
                            if binding.branch_diversity
                            else "metric-paper",
                            field_id=field_id,
                            entity_attribution_weight=projection.entity_attribution_weight,
                            include_category_weights=binding.branch_diversity,
                        ),
                        evidence_kind=kind,
                    )
                )
            else:
                base = _decision_view(proof, binding, kind)
                decisions.append(
                    LaunchPaperDecision(
                        **vars(base), source_proof=proof, binding=binding
                    )
                )
    partition = MetricPartitionInput(
        entity_type=cast(MetricEntityType, context.entity_type),
        entity_id=entity_id,
        field_id=field_id,
        terminal_year=context.terminal_year,
        as_of_date=window.cutoff.date(),
        dataset_version=context.dataset_version,
        acquisition_scope=context.acquisition_scope,
        attribution_policy_version=FRACTIONAL_ATTRIBUTION_V1.version,
        ontology_version=PHYSICS_FIELD_ONTOLOGY_VERSION,
        mapping_policy_version=PROVIDER_FIELD_MAPPING_VERSION,
        citation_policy_version=SESSION_CITATION_POLICY_VERSION
        if cohort_by_key
        else CITATION_POLICY_VERSION,
        coverage=MetricCoverageEvidence(None, None, None, None),
        complete_source_years=context.required_years,
        papers=tuple(papers),
        eligible_category_ids=(
            population.certification.evidence.category_universe.evidence.category_ids
            if population.certification.evidence.category_universe
            else ()
        ),
    )
    coverage, coverage_decisions = _coverage(partition, population, window, proofs)
    by_kind = {item.evidence_kind: item.ratio for item in coverage}
    partition = replace(
        partition,
        coverage=MetricCoverageEvidence(
            by_kind.get("paper-time-affiliation"),
            by_kind.get("canonical-institution"),
            by_kind.get("citation-observation"),
            by_kind.get("field-classification"),
            by_kind.get("collaboration-relationship"),
        ),
    )
    return _LaunchPartitionInputs(
        partition=partition,
        decisions=tuple(decisions) + coverage_decisions,
        coverage=coverage,
        window=window,
        population=population,
    )


def _coverage(
    partition: MetricPartitionInput,
    population: CertifiedMetricPopulation,
    window: CertifiedMetricWindow,
    proofs: dict[str, LaunchStructuralDecision],
) -> tuple[
    tuple[CoverageCertification, ...], tuple[EvidenceCertificationDecision, ...]
]:
    ledger = metric_population_coverage_ledger(population.certification.evidence)
    comparable = (
        set(impact_comparable_paper_ids(partition, window.citation_cohorts))
        if window.certification.metric_id == "research_impact"
        else set()
    )
    papers = {item.paper_id: item for item in partition.papers}
    certificates, all_decisions = [], []
    for kind in required_coverage_evidence(
        window.certification.metric_id, partition.entity_type
    ):
        inputs, decisions = [], []
        for unit in ledger:
            paper = papers.get(unit.paper_id)
            supported = unit.status == "known" and paper is not None
            if kind == "citation-observation":
                supported = supported and unit.paper_id in comparable
            if kind == "collaboration-relationship" and paper is not None:
                supported = (
                    supported
                    and getattr(
                        paper,
                        {
                            "researcher": "collaborative",
                            "institution": "cross_institution",
                            "country": "international",
                        }[partition.entity_type],
                    )
                    is not None
                )
            if supported:
                inputs.append((unit.paper_id, unit.mass))
            decisions.append(
                EvidenceCertificationDecision(
                    subject_type="coverage-unit",
                    subject_id=unit.unit_id,
                    evidence_kind=kind,
                    state="certified" if supported else "insufficient_evidence",
                    rule_version=evidence_rule_version(kind),
                    dataset_version=partition.dataset_version,
                    acquisition_scope=partition.acquisition_scope,
                    evidence=proofs[unit.paper_id].evidence,
                    certified_value_digest=canonical_digest((unit, kind, supported)),
                    reasons=()
                    if supported
                    else ("source-bound formula input is missing",),
                )
            )
        evidence = CoveragePopulationEvidence(
            evidence_kind=kind,
            units=tuple((item.unit_id, item.mass) for item in ledger),
            formula_inputs=tuple(sorted(inputs)),
            source_manifest_digest=population.certification.projection_digest,
        )
        certificates.append(certify_coverage(kind, tuple(decisions), evidence))
        all_decisions.extend(decisions)
    return tuple(certificates), tuple(all_decisions)


@dataclass(frozen=True)
class LaunchPeerFailure:
    """Compact deterministic summary, not a duplicated per-paper decision ledger."""

    evidence_kind: EvidenceKind
    subject_type: Literal["paper", "coverage"]
    state: CertificationState
    reasons: tuple[str, ...]
    affected_count: int
    numerator: float | None = None
    denominator: float | None = None
    minimum: float | None = None


def _launch_peer_failures(
    inputs: _LaunchPartitionInputs,
) -> tuple[LaunchPeerFailure, ...]:
    """Only existing scientific verdicts can exclude a peer; never exceptions."""
    papers = {item.paper_id: item for item in inputs.partition.papers}
    counts: Counter[tuple[EvidenceKind, CertificationState, tuple[str, ...]]] = (
        Counter()
    )
    for decision in inputs.decisions:
        if decision.subject_type != "paper" or decision.state == "certified":
            continue
        if decision.state == "insufficient_evidence" and _explicit_missing_is_usable(
            papers[decision.subject_id],
            inputs.window.certification.metric_id,
            inputs.partition.entity_type,
            decision.evidence_kind,
        ):
            continue
        counts[(decision.evidence_kind, decision.state, decision.reasons)] += 1
    failures = [
        LaunchPeerFailure(kind, "paper", state, reasons, count)
        for (kind, state, reasons), count in sorted(counts.items())
    ]
    failures.extend(
        LaunchPeerFailure(
            item.evidence_kind,
            "coverage",
            item.state,
            item.reasons,
            1,
            item.numerator,
            item.denominator,
            item.minimum,
        )
        for item in inputs.coverage
        if item.state != "certified"
    )
    return tuple(failures)


@dataclass(frozen=True)
class LaunchPeerIneligibility:
    """Source-reconstructed exclusion; shared window retained once in memory.

    No failed implementation call is converted into scientific missingness.
    The original rules must explicitly withhold paper evidence or coverage.
    """

    source_window: CertifiedMetricWindow
    entity_id: str
    field_id: str
    partition_digest: str
    population_certification_id: str
    failures: tuple[LaunchPeerFailure, ...]
    version: str = CONDITIONAL_LAUNCH_PEER_VERSION

    def __post_init__(self) -> None:
        if (
            self.version != CONDITIONAL_LAUNCH_PEER_VERSION
            or not isinstance(self.source_window, CertifiedMetricWindow)
            or not self.source_window.source_years
            or not all(
                isinstance(year.evidence, ConditionalObservedSourceYearEvidence)
                for year in self.source_window.source_years
            )
        ):
            raise CertificationError(
                "ineligible peer proof requires conditional source scope"
            )
        inputs = _launch_partition_inputs(
            self.source_window, entity_id=self.entity_id, field_id=self.field_id
        )
        if (
            not self.failures
            or self.failures != _launch_peer_failures(inputs)
            or self.partition_digest != canonical_digest(inputs.partition)
            or self.population_certification_id
            != inputs.population.certification.certification_id
        ):
            raise CertificationError(
                "ineligible peer does not reconstruct scientific failures"
            )


def _ineligible_launch_peer(inputs: _LaunchPartitionInputs) -> LaunchPeerIneligibility:
    return LaunchPeerIneligibility(
        source_window=inputs.window,
        entity_id=inputs.partition.entity_id,
        field_id=inputs.partition.field_id,
        partition_digest=canonical_digest(inputs.partition),
        population_certification_id=inputs.population.certification.certification_id,
        failures=_launch_peer_failures(inputs),
    )


class NoEligibleLaunchPeers(CertificationError):
    def __init__(self, peers: tuple[LaunchPeerIneligibility, ...]) -> None:
        self.ineligible_peers = peers
        super().__init__(
            "no source peer has a certification-eligible partition "
            f"({len(peers)} excluded)"
        )


def calculate_launch_metric_cohort(
    window: CertifiedMetricWindow, *, field_id: str
) -> tuple[AtlasScaleObservation, ...]:
    """Use all represented peers and preserve every existing raw/scale threshold."""
    entity_ids = {
        identifier
        for year in window.source_years
        for source in year.evidence.paper_projections
        if (
            branch_diversity_field_projection(field_id, source.field_weights)[0]
            if window.certification.metric_id == "research_diversity"
            else dict(source.field_weights).get(field_id, 0)
        )
        > 0
        for kind, identifier, mass in source.entity_shares
        if kind == window.certification.entity_type and mass > 0
    }
    calculations: list[CertifiedMetricCalculation] = []
    ineligible_peers: list[LaunchPeerIneligibility] = []
    conditional = bool(window.source_years) and all(
        isinstance(year.evidence, ConditionalObservedSourceYearEvidence)
        for year in window.source_years
    )
    for entity_id in sorted(entity_ids):
        inputs = _launch_partition_inputs(
            window, entity_id=entity_id, field_id=field_id
        )
        if conditional and _launch_peer_failures(inputs):
            ineligible_peers.append(_ineligible_launch_peer(inputs))
            continue
        partition = _materialize_launch_partition(inputs)
        metric_id = window.certification.metric_id
        if metric_id == "research_impact":
            cohorts = tuple(
                item
                for item in window.citation_cohorts
                if isinstance(item, CertifiedSessionCitationCohort)
            )
            result = calculate_impact_raw(partition, cohorts)
            calculations.append(
                bind_metric_calculation(result, partition, citation_cohorts=cohorts)
            )
        else:
            calculator = {
                "research_activity_score": calculate_activity_raw,
                "collaboration": calculate_connectivity,
                "research_diversity": calculate_diversity,
                "momentum": calculate_momentum_raw,
            }[metric_id]
            calculations.append(
                bind_metric_calculation(calculator(partition), partition)
            )
    peers = tuple(calculations)
    if not peers:
        raise NoEligibleLaunchPeers(tuple(ineligible_peers))
    normalization = certify_normalization_population(
        derive_normalization_population(
            window, peers, ineligible_peers=tuple(ineligible_peers)
        )
    )
    return apply_atlas_scale(peers, normalization_populations=(normalization,))
