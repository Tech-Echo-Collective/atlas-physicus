import math

from .contracts import (
    CertificationError,
    CertificationState,
    CoverageCertification,
    CoverageDecisionMass,
    CoveragePopulationEvidence,
    EvidenceCertificationDecision,
    EvidenceKind,
)
from .rules import coverage_minimum, evidence_decision_is_current

COVERAGE_SUBJECT_TYPE = "coverage-unit"


def certify_coverage(
    evidence_kind: EvidenceKind,
    decisions: tuple[EvidenceCertificationDecision, ...],
    population: CoveragePopulationEvidence,
) -> CoverageCertification:
    """Derive a v1 coverage gate from the exact, immutable evidence decisions.

    Each decision is binary, while its denominator mass may be fractional. This
    supports authorship-share denominators without allowing one proof to claim a
    partially certified mass.
    """

    from .field_mass import (
        SourceFieldMassDecision,
        SourceFieldMassPopulation,
        validate_source_field_mass_decisions,
    )
    from .launch_metric_coverage import (
        SourceAttributionMassDecision,
        SourceAttributionMassPopulation,
        validate_source_attribution_mass_decisions,
    )

    if isinstance(population, SourceFieldMassPopulation):
        validate_source_field_mass_decisions(population, decisions)
    elif isinstance(population, SourceAttributionMassPopulation):
        validate_source_attribution_mass_decisions(population, decisions)
    elif any(isinstance(item, SourceFieldMassDecision) for item in decisions):
        raise CertificationError(
            "source field mass decisions require their exact typed population"
        )
    elif any(isinstance(item, SourceAttributionMassDecision) for item in decisions):
        raise CertificationError(
            "source attribution mass decisions require their exact typed population"
        )
    minimum = coverage_minimum(evidence_kind)
    ids = [item.decision_id for item in decisions]
    if not ids or len(set(ids)) != len(ids):
        raise CertificationError("coverage decisions must be non-empty and unique")
    if population.evidence_kind != evidence_kind:
        raise CertificationError("coverage population evidence kind differs")
    decisions_by_subject = {item.subject_id: item for item in decisions}
    population_by_subject = dict(population.units)
    if len(decisions_by_subject) != len(decisions) or set(decisions_by_subject) != set(
        population_by_subject
    ):
        raise CertificationError(
            "coverage population must bind every supplied decision subject exactly"
        )
    if any(item.evidence_kind != evidence_kind for item in decisions):
        raise CertificationError("coverage decisions must share one evidence kind")
    if any(not evidence_decision_is_current(item) for item in decisions):
        raise CertificationError("coverage contains a stale evidence rule")

    measurements = tuple(
        sorted(
            (
                CoverageDecisionMass(
                    decision_id=decision.decision_id,
                    certified_mass=(mass if decision.state == "certified" else 0.0),
                    denominator_mass=mass,
                )
                for subject_id, mass in population_by_subject.items()
                for decision in (decisions_by_subject[subject_id],)
            ),
            key=lambda item: item.decision_id,
        )
    )
    numerator = math.fsum(item.certified_mass for item in measurements)
    denominator = math.fsum(item.denominator_mass for item in measurements)
    ratio = numerator / denominator if denominator else None
    state: CertificationState = (
        "certified"
        if ratio is not None and ratio >= minimum
        else "insufficient_evidence"
    )
    return CoverageCertification(
        evidence_kind=evidence_kind,
        numerator=numerator,
        denominator=denominator,
        minimum=minimum,
        state=state,
        population=population,
        decision_ids=tuple(item.decision_id for item in measurements),
        decision_masses=measurements,
        reasons=()
        if state == "certified"
        else ("certified evidence mass is below the v1 coverage minimum",),
    )


def validate_coverage_certification(
    certification: CoverageCertification,
    decisions: tuple[EvidenceCertificationDecision, ...],
) -> None:
    """Fail closed unless a coverage certificate reconstructs from exact decisions."""

    try:
        rebuilt = certify_coverage(
            certification.evidence_kind,
            decisions,
            certification.population,
        )
    except (ValueError, CertificationError) as error:
        raise CertificationError(
            "coverage certification does not match its current evidence decisions"
        ) from error
    if rebuilt != certification:
        raise CertificationError(
            "coverage certification does not match its current evidence decisions"
        )
