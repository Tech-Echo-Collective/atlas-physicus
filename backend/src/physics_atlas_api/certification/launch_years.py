"""Pure, bounded source-membership certification; not public metric activation.

Provider-origin authentication remains at the trusted transport/parser boundary.
This adapter reconstructs captured identities, conserved fields and attribution,
retaining every source occurrence and explicit unknown mass. It writes nothing.
"""

import math
from dataclasses import dataclass, fields, replace
from datetime import datetime
from fractions import Fraction

from ..attribution import (
    FRACTIONAL_ATTRIBUTION_V1,
    AuthorAttributionInput,
    PaperTimeAffiliationAssertion,
    calculate_fractional_attribution,
)
from .automation import ResolvedResearcherIdentifiers, automatic_paper_identity_decision
from .contracts import (
    CERTIFICATION_POLICY_VERSION,
    CertificationError,
    CertificationState,
    EvidenceCertificationDecision,
    EvidenceKind,
    canonical_digest,
)
from .fields import (
    AutomaticFieldBinding,
    automatic_field_decision,
    automatic_field_ledger,
)
from .launch_attribution import LAUNCH_ATTRIBUTION_VERSION, LaunchAttributionResult
from .launch_capture import LAUNCH_CAPTURE_VERSION, CapturedLaunchYear
from .launch_inputs import (
    LaunchCanonicalInputs,
    LaunchCanonicalPaper,
    LaunchSourceOccurrence,
    canonicalize_launch_inputs,
)
from .years import (
    CertifiedSourceYear,
    SourceEntityType,
    SourceYearEvidence,
    SourceYearPaperProjection,
    certify_source_year,
)

LAUNCH_SOURCE_YEAR_VERSION = "bounded-launch-source-year-v1"


@dataclass(frozen=True)
class LaunchSourceYearBuild:
    source_year: CertifiedSourceYear | None
    measured_counts: dict[str, int | float | None]
    blockers: tuple[tuple[str, str], ...]
    version: str = LAUNCH_SOURCE_YEAR_VERSION


def _validate_attribution(
    occurrence: LaunchSourceOccurrence,
    result: LaunchAttributionResult,
) -> None:
    """Reconstruct exact per-author fractions from captured slots and decisions."""
    facts, reference = occurrence.source_facts, occurrence.reference
    if (
        not isinstance(result, LaunchAttributionResult)
        or result.version != LAUNCH_ATTRIBUTION_VERSION
        or result.paper_reference != reference
        or result.researcher_state
        != automatic_paper_identity_decision(
            facts, evidence_kind="researcher-identity"
        ).state
    ):
        raise CertificationError(
            "launch attribution does not bind its exact paper occurrence"
        )
    if not facts.author_count:
        if (
            result.fractional is not None
            or result.affiliations
            or result.paper_time_affiliation_weight is not None
        ):
            raise CertificationError(
                "missing author inventory cannot invent attribution"
            )
        return
    fractional = result.fractional
    if fractional is None or fractional.paper_id not in {
        facts.context.paper_id,
        f"source-occurrence:{canonical_digest(reference)}",
    }:
        raise CertificationError(
            "launch attribution has no matching fractional paper identity"
        )
    resolutions = {
        (item.author_position, item.affiliation_position): item
        for item in result.affiliations
    }
    if len(resolutions) != len(result.affiliations):
        raise CertificationError("launch attribution repeats an affiliation position")
    used = set()
    inputs = []
    present = set()
    assessments = facts.researcher_assessments
    for author in occurrence.authors:
        source_key = "affiliations" if author.structured else "raw_affiliations"
        native = author.structured if author.structured else author.raw
        assertions = []
        for fact in native:
            key = author.author_position, fact.position
            resolution = resolutions.get(key)
            source_field = f"authors[{key[0] - 1}].{source_key}[{key[1] - 1}]"
            assertion_id = f"affiliation:{canonical_digest((reference, source_field))}"
            if (
                resolution is None
                or resolution.source_field != source_field
                or resolution.assertion_id != assertion_id
                or resolution.raw_name != fact.text
                or reference not in resolution.evidence
            ):
                raise CertificationError(
                    "launch attribution differs from captured affiliation slots"
                )
            used.add(key)
            certified = resolution.state == "certified"
            institution = resolution.institution
            if certified and (
                institution is None
                or institution.state != "certified"
                or institution.canonical_institution_id is None
                or resolution.country_code is None
                or {item.country_code for item in resolution.locations}
                != {resolution.country_code}
            ):
                raise CertificationError(
                    "certified launch affiliation lacks exact institution/geography"
                )
            if not certified and not resolution.reasons:
                raise CertificationError(
                    "unresolved launch affiliation lacks its reason"
                )
            if fact.text or fact.provider_reference or fact.identifiers:
                present.add(assertion_id)
            assertions.append(
                PaperTimeAffiliationAssertion(
                    assertion_id=assertion_id,
                    resolution_status="resolved"
                    if certified
                    else "ambiguous"
                    if resolution.state == "conflicted"
                    else "unresolved",
                    source="inspire",
                    source_record_id=reference.source_record_id,
                    evidence_version=LAUNCH_ATTRIBUTION_VERSION,
                    institution_id=institution.canonical_institution_id
                    if certified and institution
                    else None,
                    country_id=f"country-{resolution.country_code.casefold()}"
                    if certified and resolution.country_code
                    else None,
                )
            )
        assessment = assessments[author.author_position - 1]
        value = assessment.value
        if not isinstance(value, ResolvedResearcherIdentifiers):
            raise CertificationError(
                "launch author assessment has no exact identity projection"
            )
        identifiers = (
            dict(value.identifiers) if assessment.decision.state == "certified" else {}
        )
        researcher = identifiers.get("inspire-author")
        inputs.append(
            AuthorAttributionInput(
                author_slot_id=(
                    "author-slot:"
                    f"{canonical_digest((reference, author.author_position - 1))}"
                ),
                author_position=author.author_position,
                researcher_id=f"inspire-author:{researcher}"
                if researcher is not None
                else None,
                affiliations=tuple(assertions),
            )
        )
    if used != set(resolutions):
        raise CertificationError(
            "launch attribution includes uncaptured affiliation slots"
        )
    rebuilt = calculate_fractional_attribution(fractional.paper_id, inputs)
    presence = sum(
        (
            item.weight
            for item in rebuilt.shares
            if set(item.affiliation_assertion_ids) & present
        ),
        start=Fraction(0),
    )
    if rebuilt != fractional or presence != result.paper_time_affiliation_weight:
        raise CertificationError(
            "launch attribution fractions do not reconstruct from source assertions"
        )


def _projection(
    paper: LaunchCanonicalPaper,
    attributions: tuple[LaunchAttributionResult, ...],
) -> SourceYearPaperProjection:
    # Recompute the existing strong-ID component; never accept a caller's matched flag.
    if canonicalize_launch_inputs(paper.occurrences).papers != (paper,):
        raise CertificationError("launch canonical identity does not reconstruct")
    dates = {item.source_facts.exact_date for item in paper.occurrences}
    if None in dates or len(dates) != 1:
        raise CertificationError(
            "source paper lacks one exact consistent declared date"
        )
    results = {item.paper_reference: item for item in attributions}
    if len(results) != len(attributions) or set(results) != {
        item.reference for item in paper.occurrences
    }:
        raise CertificationError(
            "launch attribution must retain every source occurrence"
        )
    for occurrence in paper.occurrences:
        _validate_attribution(occurrence, results[occurrence.reference])
    ledger = automatic_field_ledger(paper.field_evidence)
    shares: list[tuple[SourceEntityType, str, float]] = []
    unresolved: list[tuple[SourceEntityType, float]] = []
    # Multiple same-provider identity candidates cannot choose a favorable author
    # projection. Preserve their scientific identity blocker and unknown mass.
    result = (
        attributions[0]
        if len(attributions) == 1 and paper.component.status == "matched"
        else None
    )
    fractional = result.fractional if result else None
    entity_types: tuple[SourceEntityType, ...] = (
        "researcher",
        "institution",
        "country",
    )
    for entity_type in entity_types:
        weights = (
            {}
            if fractional is None
            else (
                fractional.researcher_weights()
                if entity_type == "researcher"
                else fractional.institution_weights()
                if entity_type == "institution"
                else fractional.country_weights()
            )
        )
        if (
            entity_type == "researcher"
            and result
            and result.researcher_state != "certified"
        ):
            weights = {}
        allocated = sum(weights.values(), start=Fraction(0))
        shares.extend(
            (entity_type, identifier, float(weight))
            for identifier, weight in sorted(weights.items())
        )
        unresolved.append((entity_type, float(1 - allocated)))
    return SourceYearPaperProjection(
        paper_id=paper.paper_id,
        publication_date=next(iter(dates)),  # type: ignore[arg-type]
        occurrence_references=tuple(sorted(results, key=canonical_digest)),
        field_weights=tuple(
            sorted((item.field_id, item.weight) for item in ledger.assignments)
        ),
        unmapped_field_mass=ledger.unmapped_mass,
        field_weight_total=ledger.conservation_total,
        field_weighting_policy_version=ledger.weighting_policy_version,
        entity_shares=tuple(shares),
        unresolved_entity_mass=tuple(unresolved),
        attribution_policy_version=FRACTIONAL_ATTRIBUTION_V1.version,
    )


def _structural_values(
    paper: LaunchCanonicalPaper,
    projection: SourceYearPaperProjection,
    attributions: tuple[LaunchAttributionResult, ...],
    kind: EvidenceKind,
) -> EvidenceCertificationDecision:
    """Prepare unchanged decision fields; typed admission verifies the inputs."""
    if kind not in {"canonical-paper-identity", "provenance-completeness"}:
        raise CertificationError("unsupported launch structural projection kind")
    matched = (
        paper.component.status == "matched"
        and paper.component.canonical_id == paper.paper_id
    )
    state: CertificationState = (
        "needs_review"
        if kind == "canonical-paper-identity" and not matched
        else "certified"
    )
    context = paper.occurrences[0].source_facts.context
    references = set(projection.occurrence_references)
    if kind == "provenance-completeness":
        references.update(
            ref
            for result in attributions
            for resolution in result.affiliations
            for ref in resolution.evidence
        )
    return EvidenceCertificationDecision(
        subject_type="paper",
        subject_id=paper.paper_id,
        evidence_kind=kind,
        state=state,
        rule_version=CERTIFICATION_POLICY_VERSION,
        dataset_version=context.dataset_version,
        acquisition_scope=context.acquisition_scope,
        evidence=tuple(sorted(references, key=canonical_digest)),
        certified_value_digest=projection.decision_value_digest(kind),
        reasons=()
        if state == "certified"
        else ("canonical strong-identifier component remains unresolved",),
    )


def _structural_view(
    paper: LaunchCanonicalPaper,
    projection: SourceYearPaperProjection,
    attributions: tuple[LaunchAttributionResult, ...],
    kind: EvidenceKind,
) -> EvidenceCertificationDecision:
    if _projection(paper, attributions) != projection:
        raise CertificationError(
            "launch structural evidence differs from scientific projection"
        )
    return _structural_values(paper, projection, attributions, kind)


@dataclass(frozen=True, kw_only=True)
class LaunchStructuralDecision(EvidenceCertificationDecision):
    source_paper: LaunchCanonicalPaper
    source_projection: SourceYearPaperProjection
    attribution_results: tuple[LaunchAttributionResult, ...]
    producer_version: str = LAUNCH_SOURCE_YEAR_VERSION

    def __post_init__(self) -> None:
        EvidenceCertificationDecision.__post_init__(self)
        expected = _structural_view(
            self.source_paper,
            self.source_projection,
            self.attribution_results,
            self.evidence_kind,
        )
        if self.producer_version != LAUNCH_SOURCE_YEAR_VERSION or any(
            getattr(self, item.name) != getattr(expected, item.name)
            for item in fields(EvidenceCertificationDecision)
        ):
            raise CertificationError(
                "launch structural decision does not reconstruct its source facts"
            )


def _structural_decision(
    paper: LaunchCanonicalPaper,
    projection: SourceYearPaperProjection,
    attributions: tuple[LaunchAttributionResult, ...],
    kind: EvidenceKind,
) -> LaunchStructuralDecision:
    # The constructor independently reconstructs the projection. Preparing its
    # fields need not perform that identical reconstruction immediately before it.
    expected = _structural_values(paper, projection, attributions, kind)
    return LaunchStructuralDecision(
        **{
            item.name: getattr(expected, item.name)
            for item in fields(EvidenceCertificationDecision)
        },
        source_paper=paper,
        source_projection=projection,
        attribution_results=attributions,
    )


def build_launch_source_year(
    captured: CapturedLaunchYear,
    canonical_inputs: LaunchCanonicalInputs,
    attribution_results: tuple[LaunchAttributionResult, ...],
    *,
    entity_type: SourceEntityType,
    evidence_cutoff: datetime,
) -> LaunchSourceYearBuild:
    """Freeze exact membership, not affiliation/citation metric readiness.

    Later metric evaluation must certify its additional required coverage over
    these same projections. Unknown dates cannot be guessed into a source-year
    projection: report the retained blocker and do not issue a partial proof.
    """
    from .field_mass import certify_source_field_mass

    if not isinstance(captured, CapturedLaunchYear) or not isinstance(
        canonical_inputs, LaunchCanonicalInputs
    ):
        raise CertificationError(
            "launch year requires captured and canonical typed inputs"
        )
    captured.plan.__post_init__()
    captured.partition.__post_init__()
    if (
        entity_type not in {"country", "institution", "researcher"}
        or evidence_cutoff.tzinfo is None
        or evidence_cutoff.utcoffset() is None
        or not captured.requests
        or any(item.received_at > evidence_cutoff for item in captured.requests)
        or captured.manifest_digest
        != canonical_digest(
            (
                LAUNCH_CAPTURE_VERSION,
                captured.plan,
                captured.partition,
                captured.requests,
            )
        )
        or not captured.partition.reconciles
        or captured.partition.partition_id != captured.plan.partitions[0][0]
    ):
        raise CertificationError(
            "launch source-year capture, cutoff or partition authority is invalid"
        )
    local = canonicalize_launch_inputs(captured.occurrences)
    references = {item.reference for item in captured.occurrences}
    selected = tuple(
        item
        for item in canonical_inputs.papers
        if any(occurrence.reference in references for occurrence in item.occurrences)
    )
    if {item.paper_id: item for item in selected} != {
        item.paper_id: item for item in local.papers
    }:
        raise CertificationError(
            "canonical launch input omits, changes or crosses "
            "captured source-year membership"
        )
    results = {item.paper_reference: item for item in attribution_results}
    if len(results) != len(attribution_results) or not references.issubset(results):
        raise CertificationError(
            "launch source year is missing exact attribution results"
        )
    projections = []
    structural: list[EvidenceCertificationDecision] = []
    field_evidence = []
    blockers = []
    for paper in selected:
        attributed = tuple(results[item.reference] for item in paper.occurrences)
        dates = {item.source_facts.exact_date for item in paper.occurrences}
        if None in dates or len(dates) != 1:
            blockers.append(
                (
                    paper.paper_id,
                    "missing or conflicting exact source date; "
                    "no partial source-year proof",
                )
            )
            continue
        projection = _projection(paper, attributed)
        projections.append(projection)
        field_evidence.append(paper.field_evidence)
        structural.extend(
            (
                _structural_decision(
                    paper, projection, attributed, "canonical-paper-identity"
                ),
                automatic_paper_identity_decision(
                    paper.occurrences[0].source_facts,
                    evidence_kind="publication-metric-date",
                ),
                automatic_field_decision(
                    paper.field_evidence,
                    binding=AutomaticFieldBinding("source-year-ledger"),
                    evidence_kind="field-weight-conservation",
                ),
                _structural_decision(
                    paper, projection, attributed, "provenance-completeness"
                ),
            )
        )
    ordered = tuple(sorted(projections, key=lambda item: item.paper_id))
    counts: dict[str, int | float | None] = {
        "provider_occurrences": len(captured.occurrences),
        "canonical_papers": len(selected),
        "projected_papers": len(ordered),
        "canonical_identity_matched_papers": sum(
            item.component.status == "matched" for item in selected
        ),
        "exact_date_blockers": len(blockers),
        "known_field_mass": math.fsum(
            math.fsum(weight for _, weight in item.field_weights) for item in ordered
        ),
        "unmapped_field_mass": math.fsum(item.unmapped_field_mass for item in ordered),
        "unresolved_institution_mass": math.fsum(
            dict(item.unresolved_entity_mass)["institution"] for item in ordered
        ),
        "unresolved_country_mass": math.fsum(
            dict(item.unresolved_entity_mass)["country"] for item in ordered
        ),
        "unresolved_researcher_mass": math.fsum(
            dict(item.unresolved_entity_mass)["researcher"] for item in ordered
        ),
    }
    if blockers:
        return LaunchSourceYearBuild(None, counts, tuple(blockers))
    coverage, coverage_decisions = certify_source_field_mass(
        tuple(field_evidence), ordered
    )
    counts["certified_field_mass"] = coverage.numerator
    counts["field_coverage_denominator"] = coverage.denominator
    counts["field_coverage"] = (
        coverage.numerator / coverage.denominator if coverage.denominator else None
    )
    evidence = SourceYearEvidence(
        calendar_year=captured.plan.calendar_year,
        entity_type=entity_type,
        cutoff=evidence_cutoff,
        dataset_version=captured.plan.dataset_version,
        acquisition_scope=captured.plan.acquisition_scope,
        acquisition_plan=replace(captured.plan, cutoff=evidence_cutoff),
        required_partition_ids=(captured.partition.partition_id,),
        required_coverage_kinds=("field-classification",),
        paper_projections=ordered,
        partitions=(captured.partition,),
        structural_decisions=tuple(structural),
        coverage_decisions=coverage_decisions,
    )
    certified = certify_source_year(evidence, (coverage,))
    return LaunchSourceYearBuild(certified, counts, ())
