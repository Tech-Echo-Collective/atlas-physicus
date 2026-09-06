"""Source-bound, conserved coverage for a bounded launch population.

Each paper contributes exactly one denominator unit, split into certified and
unknown mass. Affiliation presence and canonical allocation use the existing
fractional attribution result, not an all-or-nothing whole-paper approximation.
Relationship evidence is a paper property: a supported positive is sufficient;
a negative requires a complete relevant inventory. Unknown is never false.

This module neither computes metrics nor admits a population to public release.
"""

from dataclasses import dataclass, fields, replace
from datetime import datetime
from fractions import Fraction
from typing import Literal, cast

from .contracts import (
    CertificationError,
    CoverageCertification,
    CoveragePopulationEvidence,
    EvidenceCertificationDecision,
    EvidenceKind,
    canonical_digest,
)
from .launch_years import LaunchSourceYearBuild, LaunchStructuralDecision
from .rules import evidence_rule_version
from .years import (
    CertifiedSourceYear,
    SourceEntityType,
    SourceYearPaperProjection,
    certify_source_year,
)

SOURCE_ATTRIBUTION_MASS_VERSION = "source-attribution-mass-coverage-v1"
type AttributionCoverageKind = Literal[
    "paper-time-affiliation", "canonical-institution", "collaboration-relationship"
]
type MassKind = Literal["known", "unknown"]
_KINDS = frozenset(
    {"paper-time-affiliation", "canonical-institution", "collaboration-relationship"}
)


def _checked_proof(proof: LaunchStructuralDecision) -> None:
    if not isinstance(proof, LaunchStructuralDecision) or (
        proof.evidence_kind != "provenance-completeness" or proof.state != "certified"
    ):
        raise CertificationError(
            "launch coverage requires exact typed provenance proof"
        )
    proof.__post_init__()


def launch_relationship_status(
    proof: LaunchStructuralDecision, entity_type: SourceEntityType
) -> bool | None:
    """Derive only source-supported coauthorship/cross-institution/country facts."""
    _checked_proof(proof)
    if entity_type not in {"researcher", "institution", "country"}:
        raise CertificationError("unsupported source coverage entity type")
    if len(proof.attribution_results) != 1 or (
        proof.source_paper.component.status != "matched"
    ):
        return None
    result = proof.attribution_results[0]
    if entity_type == "researcher":
        facts = proof.source_paper.occurrences[0].source_facts
        identifiers = set(facts.researcher_ids)
        # Conflicted paper identities cannot establish a distinct-person count.
        if result.researcher_state == "conflicted":
            return None
        complete = result.researcher_state == "certified"
    else:
        identifiers = {
            identifier
            for kind, identifier, mass in proof.source_projection.entity_shares
            if kind == entity_type and mass > 0
        }
        complete = (
            dict(proof.source_projection.unresolved_entity_mass)[entity_type] == 0
        )
    if len(identifiers) >= 2:
        return True
    if identifiers and complete:
        return False
    return None


def _parts(
    proof: LaunchStructuralDecision,
    kind: EvidenceKind,
    entity_type: SourceEntityType,
) -> tuple[float, float]:
    _checked_proof(proof)
    if kind not in _KINDS or entity_type not in {
        "researcher",
        "institution",
        "country",
    }:
        raise CertificationError("unsupported source attribution coverage dimension")
    result = (
        proof.attribution_results[0]
        if len(proof.attribution_results) == 1
        and proof.source_paper.component.status == "matched"
        else None
    )
    known = Fraction(0)
    if kind == "paper-time-affiliation" and result is not None:
        known = result.paper_time_affiliation_weight or Fraction(0)
    elif kind == "canonical-institution" and result is not None and result.fractional:
        known = sum(result.fractional.institution_weights().values(), start=Fraction(0))
    elif kind == "collaboration-relationship":
        known = Fraction(
            int(launch_relationship_status(proof, entity_type) is not None)
        )
    if not 0 <= known <= 1:
        raise CertificationError(
            "source attribution coverage does not conserve one paper"
        )
    return float(known), float(1 - known)


def _unit_id(paper_id: str, kind: EvidenceKind, mass_kind: MassKind) -> str:
    return f"attribution-mass:{canonical_digest((paper_id, kind, mass_kind))}"


def _decision(
    proof: LaunchStructuralDecision,
    kind: EvidenceKind,
    entity_type: SourceEntityType,
    mass_kind: MassKind,
) -> EvidenceCertificationDecision:
    known, unknown = _parts(proof, kind, entity_type)
    if (
        mass_kind not in {"known", "unknown"}
        or (known if mass_kind == "known" else unknown) <= 0
    ):
        raise CertificationError(
            "coverage decision requires a positive existing mass unit"
        )
    return EvidenceCertificationDecision(
        subject_type="coverage-unit",
        subject_id=_unit_id(proof.subject_id, kind, mass_kind),
        evidence_kind=kind,
        state="certified" if mass_kind == "known" else "insufficient_evidence",
        rule_version=evidence_rule_version(kind),
        dataset_version=proof.dataset_version,
        acquisition_scope=proof.acquisition_scope,
        evidence=proof.evidence,
        certified_value_digest=canonical_digest(
            (
                SOURCE_ATTRIBUTION_MASS_VERSION,
                proof.source_projection,
                kind,
                entity_type,
                mass_kind,
                known,
                unknown,
            )
        ),
        reasons=()
        if mass_kind == "known"
        else ("explicit unsupported source mass remains withheld",),
    )


@dataclass(frozen=True, kw_only=True)
class SourceAttributionMassDecision(EvidenceCertificationDecision):
    source_proof: LaunchStructuralDecision
    entity_type: SourceEntityType
    mass_kind: MassKind
    producer_version: str = SOURCE_ATTRIBUTION_MASS_VERSION

    def __post_init__(self) -> None:
        EvidenceCertificationDecision.__post_init__(self)
        expected = _decision(
            self.source_proof, self.evidence_kind, self.entity_type, self.mass_kind
        )
        if self.producer_version != SOURCE_ATTRIBUTION_MASS_VERSION or any(
            getattr(self, item.name) != getattr(expected, item.name)
            for item in fields(EvidenceCertificationDecision)
        ):
            raise CertificationError(
                "attribution mass decision does not reconstruct source facts"
            )


@dataclass(frozen=True, kw_only=True)
class SourceAttributionMassPopulation(CoveragePopulationEvidence):
    source_proofs: tuple[LaunchStructuralDecision, ...]
    entity_type: SourceEntityType
    version: str = SOURCE_ATTRIBUTION_MASS_VERSION

    @property
    def source_projections(self) -> tuple[SourceYearPaperProjection, ...]:
        return tuple(item.source_projection for item in self.source_proofs)

    def __post_init__(self) -> None:
        CoveragePopulationEvidence.__post_init__(self)
        if self.version != SOURCE_ATTRIBUTION_MASS_VERSION or not self.source_proofs:
            raise CertificationError(
                "source attribution mass requires versioned source proofs"
            )
        if (
            len({item.subject_id for item in self.source_proofs})
            != len(self.source_proofs)
            or len(
                {
                    (item.dataset_version, item.acquisition_scope)
                    for item in self.source_proofs
                }
            )
            != 1
        ):
            raise CertificationError(
                "source attribution mass requires one exact paper universe"
            )
        units, inputs = [], []
        for proof in sorted(self.source_proofs, key=lambda item: item.subject_id):
            known, unknown = _parts(proof, self.evidence_kind, self.entity_type)
            if known > 0:
                inputs.append((proof.subject_id, known))
                units.append(
                    (_unit_id(proof.subject_id, self.evidence_kind, "known"), known)
                )
            if unknown > 0:
                units.append(
                    (_unit_id(proof.subject_id, self.evidence_kind, "unknown"), unknown)
                )
        if (
            self.units != tuple(sorted(units))
            or self.formula_inputs != tuple(inputs)
            or (
                self.source_manifest_digest
                != canonical_digest(
                    tuple(
                        sorted(self.source_projections, key=lambda item: item.paper_id)
                    )
                )
            )
        ):
            raise CertificationError(
                "source attribution units or full denominator were altered"
            )

    @property
    def population_digest(self) -> str:
        return canonical_digest(
            (
                super().population_digest,
                self.version,
                self.entity_type,
                tuple(item.decision_id for item in self.source_proofs),
            )
        )


def validate_source_attribution_mass_decisions(
    population: SourceAttributionMassPopulation,
    decisions: tuple[EvidenceCertificationDecision, ...],
) -> None:
    population.__post_init__()
    expected = {}
    for proof in population.source_proofs:
        known, unknown = _parts(proof, population.evidence_kind, population.entity_type)
        for mass_kind, mass in (("known", known), ("unknown", unknown)):
            if mass > 0:
                typed_kind: MassKind = "known" if mass_kind == "known" else "unknown"
                expected[
                    _unit_id(proof.subject_id, population.evidence_kind, typed_kind)
                ] = (proof, typed_kind)
    if (
        len(decisions) != len(expected)
        or {item.subject_id for item in decisions} != set(expected)
        or any(
            not isinstance(item, SourceAttributionMassDecision)
            or item.entity_type != population.entity_type
            or (item.source_proof, item.mass_kind) != expected[item.subject_id]
            for item in decisions
        )
    ):
        raise CertificationError(
            "attribution decisions omit or alter source population mass"
        )
    for item in decisions:
        item.__post_init__()


def certify_source_attribution_mass(
    source_proofs: tuple[LaunchStructuralDecision, ...],
    *,
    entity_type: SourceEntityType,
    evidence_kind: AttributionCoverageKind,
) -> tuple[CoverageCertification, tuple[EvidenceCertificationDecision, ...]]:
    from .coverage import certify_coverage

    units, inputs, decisions = [], [], []
    for proof in sorted(source_proofs, key=lambda item: item.subject_id):
        known, unknown = _parts(proof, evidence_kind, entity_type)
        if known > 0:
            inputs.append((proof.subject_id, known))
        for mass_kind, mass in (("known", known), ("unknown", unknown)):
            if mass <= 0:
                continue
            typed_kind: MassKind = "known" if mass_kind == "known" else "unknown"
            base = _decision(proof, evidence_kind, entity_type, typed_kind)
            decisions.append(
                SourceAttributionMassDecision(
                    **vars(base),
                    source_proof=proof,
                    entity_type=entity_type,
                    mass_kind=typed_kind,
                )
            )
            units.append((base.subject_id, mass))
    population = SourceAttributionMassPopulation(
        evidence_kind=evidence_kind,
        units=tuple(sorted(units)),
        formula_inputs=tuple(inputs),
        source_manifest_digest=canonical_digest(
            tuple(
                sorted(
                    (item.source_projection for item in source_proofs),
                    key=lambda item: item.paper_id,
                )
            )
        ),
        source_proofs=source_proofs,
        entity_type=entity_type,
    )
    return certify_coverage(evidence_kind, tuple(decisions), population), tuple(
        decisions
    )


@dataclass(frozen=True)
class LaunchMetricCoverageBuild:
    source_year: CertifiedSourceYear
    measured_coverage: tuple[tuple[EvidenceKind, float, float, float | None], ...]
    version: str = SOURCE_ATTRIBUTION_MASS_VERSION


def certify_launch_source_coverage(
    source_build: LaunchSourceYearBuild,
    *,
    required_kinds: tuple[AttributionCoverageKind, ...] = (
        "paper-time-affiliation",
        "canonical-institution",
        "collaboration-relationship",
    ),
    evaluation_cutoff: datetime | None = None,
) -> LaunchMetricCoverageBuild:
    """Add measured purposes without changing source membership or source times."""
    if not isinstance(source_build, LaunchSourceYearBuild):
        raise CertificationError("source coverage requires a typed launch source build")
    original = source_build.source_year
    if not isinstance(original, CertifiedSourceYear):
        raise CertificationError(
            "source coverage requires a complete captured membership proof"
        )
    original.__post_init__()
    if (
        not required_kinds
        or len(set(required_kinds)) != len(required_kinds)
        or not set(required_kinds) <= _KINDS
    ):
        raise CertificationError(
            "source coverage purposes are unsupported or duplicated"
        )
    evidence = original.evidence
    if evidence.entity_type not in {"researcher", "institution", "country"}:
        raise CertificationError("unsupported source coverage entity type")
    entity_type = cast(SourceEntityType, evidence.entity_type)
    if evidence.required_coverage_kinds != ("field-classification",):
        raise CertificationError(
            "source coverage must start from the exact membership-only proof"
        )
    cutoff = evaluation_cutoff or evidence.cutoff
    if cutoff.tzinfo is None or cutoff.utcoffset() is None or cutoff < evidence.cutoff:
        raise CertificationError(
            "source evaluation cutoff cannot precede its frozen evidence"
        )
    proofs = tuple(
        item
        for item in evidence.structural_decisions
        if isinstance(item, LaunchStructuralDecision)
        and item.evidence_kind == "provenance-completeness"
    )
    if len(proofs) != len(evidence.paper_projections) or {
        item.subject_id for item in proofs
    } != {item.paper_id for item in evidence.paper_projections}:
        raise CertificationError(
            "source coverage lacks the full exact typed paper inventory"
        )
    coverage = list(original.coverage)
    decisions = list(evidence.coverage_decisions)
    for kind in required_kinds:
        certificate, extra = certify_source_attribution_mass(
            proofs, entity_type=entity_type, evidence_kind=kind
        )
        coverage.append(certificate)
        decisions.extend(extra)
    rebuilt = certify_source_year(
        replace(
            evidence,
            cutoff=cutoff,
            acquisition_plan=replace(evidence.acquisition_plan, cutoff=cutoff),
            required_coverage_kinds=("field-classification", *required_kinds),
            coverage_decisions=tuple(decisions),
        ),
        tuple(coverage),
    )
    if (
        rebuilt.certification.canonical_paper_population_digest
        != original.certification.canonical_paper_population_digest
    ):
        raise CertificationError(
            "coverage evaluation changed frozen scientific membership"
        )
    return LaunchMetricCoverageBuild(
        rebuilt,
        tuple(
            (item.evidence_kind, item.numerator, item.denominator, item.ratio)
            for item in coverage
        ),
    )
