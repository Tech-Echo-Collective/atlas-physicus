"""Exact source-year field coverage with known and unmapped binary mass units.

PA-033 permits a known contribution without reallocating its unknown remainder.
Every paper still supplies exactly one denominator unit. No caller-supplied
coverage percentage or partial approval is accepted by this adapter.
"""

import math
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Literal

from ..fields import PHYSICS_FIELD_ONTOLOGY_V1
from .automation import AutomaticCertification, AutomaticFieldEvidence
from .contracts import (
    CertificationError,
    CoverageCertification,
    CoveragePopulationEvidence,
    EvidenceCertificationDecision,
    canonical_digest,
)
from .fields import automatic_field_ledger

if TYPE_CHECKING:
    from .years import SourceYearPaperProjection

SOURCE_FIELD_MASS_COVERAGE_VERSION = "source-field-mass-coverage-v1"
FieldMassKind = Literal["known", "unmapped"]


def field_mass_unit_id(paper_id: str, kind: FieldMassKind) -> str:
    return f"field-mass:{canonical_digest((paper_id, kind))}"


def _parts(evidence: AutomaticFieldEvidence) -> tuple[float, float]:
    ledger = automatic_field_ledger(evidence)
    if any(
        PHYSICS_FIELD_ONTOLOGY_V1.get(item.field_id).node_kind != "field"
        for item in ledger.assignments
    ) or not math.isclose(ledger.conservation_total, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise CertificationError(
            "field mass requires a conserved canonical-leaf/unmapped ledger"
        )
    return math.fsum(item.weight for item in ledger.assignments), ledger.unmapped_mass


def _decision(
    evidence: AutomaticFieldEvidence, kind: FieldMassKind
) -> EvidenceCertificationDecision:
    known, unmapped = _parts(evidence)
    if (
        kind not in {"known", "unmapped"}
        or (known if kind == "known" else unmapped) <= 0
    ):
        raise CertificationError(
            "field mass decision requires a positive existing unit"
        )
    assessment = AutomaticCertification(evidence)
    return EvidenceCertificationDecision(
        subject_type="coverage-unit",
        subject_id=field_mass_unit_id(evidence.context.paper_id, kind),
        evidence_kind="field-classification",
        state="certified" if kind == "known" else "insufficient_evidence",
        rule_version=SOURCE_FIELD_MASS_COVERAGE_VERSION,
        dataset_version=evidence.context.dataset_version,
        acquisition_scope=evidence.context.acquisition_scope,
        evidence=assessment.decision.evidence,
        certified_value_digest=canonical_digest((evidence, kind, known, unmapped)),
        reasons=()
        if kind == "known"
        else ("explicit unmapped field mass remains withheld",),
    )


@dataclass(frozen=True, kw_only=True)
class SourceFieldMassDecision(EvidenceCertificationDecision):
    source_field_evidence: AutomaticFieldEvidence
    mass_kind: FieldMassKind

    def __post_init__(self) -> None:
        EvidenceCertificationDecision.__post_init__(self)
        expected = _decision(self.source_field_evidence, self.mass_kind)
        if any(
            getattr(self, item.name) != getattr(expected, item.name)
            for item in fields(EvidenceCertificationDecision)
        ):
            raise CertificationError(
                "field mass decision does not reconstruct from exact provider evidence"
            )


@dataclass(frozen=True, kw_only=True)
class SourceFieldMassPopulation(CoveragePopulationEvidence):
    source_field_evidence: tuple[AutomaticFieldEvidence, ...]
    source_projections: tuple["SourceYearPaperProjection", ...]
    version: str = SOURCE_FIELD_MASS_COVERAGE_VERSION

    def __post_init__(self) -> None:
        from .years import SourceYearPaperProjection

        CoveragePopulationEvidence.__post_init__(self)
        if (
            self.version != SOURCE_FIELD_MASS_COVERAGE_VERSION
            or self.evidence_kind != "field-classification"
            or any(
                not isinstance(item, SourceYearPaperProjection)
                for item in self.source_projections
            )
            or any(
                not isinstance(item, AutomaticFieldEvidence)
                for item in self.source_field_evidence
            )
        ):
            raise CertificationError(
                "source field mass population uses invalid typed evidence"
            )
        projections = {item.paper_id: item for item in self.source_projections}
        evidence = {item.context.paper_id: item for item in self.source_field_evidence}
        if (
            len(projections) != len(self.source_projections)
            or len(evidence) != len(self.source_field_evidence)
            or set(projections) != set(evidence)
            or len(
                {
                    (item.context.dataset_version, item.context.acquisition_scope)
                    for item in evidence.values()
                }
            )
            != 1
        ):
            raise CertificationError(
                "source field mass population must cover one exact paper universe"
            )
        units = []
        inputs = []
        for paper_id, item in sorted(evidence.items()):
            projection = projections[paper_id]
            projection.__post_init__()
            ledger = automatic_field_ledger(item)
            known, unmapped = _parts(item)
            if (
                set(item.references) != set(projection.occurrence_references)
                or tuple(
                    sorted(
                        (value.field_id, value.weight) for value in ledger.assignments
                    )
                )
                != tuple(sorted(projection.field_weights))
                or ledger.unmapped_mass != projection.unmapped_field_mass
                or ledger.conservation_total != projection.field_weight_total
                or ledger.weighting_policy_version
                != projection.field_weighting_policy_version
            ):
                raise CertificationError(
                    "source field mass does not reconstruct exact paper projections"
                )
            if known > 0:
                units.append((field_mass_unit_id(paper_id, "known"), known))
                inputs.append((paper_id, known))
            if unmapped > 0:
                units.append((field_mass_unit_id(paper_id, "unmapped"), unmapped))
        if (
            self.units != tuple(sorted(units))
            or self.formula_inputs != tuple(inputs)
            or self.source_manifest_digest
            != canonical_digest(
                tuple(sorted(self.source_projections, key=lambda item: item.paper_id))
            )
        ):
            raise CertificationError(
                "source field mass units or denominator were altered"
            )

    @property
    def population_digest(self) -> str:
        return canonical_digest(
            (super().population_digest, self.version, self.source_field_evidence)
        )


def certify_source_field_mass(
    field_evidence: tuple[AutomaticFieldEvidence, ...],
    source_projections: tuple["SourceYearPaperProjection", ...],
) -> tuple[CoverageCertification, tuple[EvidenceCertificationDecision, ...]]:
    """Return exact binary-unit decisions and unchanged-threshold coverage proof."""
    from .coverage import certify_coverage

    units = []
    inputs = []
    decisions: list[EvidenceCertificationDecision] = []
    for item in sorted(field_evidence, key=lambda value: value.context.paper_id):
        known, unmapped = _parts(item)
        if known > 0:
            inputs.append((item.context.paper_id, known))
        for kind, mass in (("known", known), ("unmapped", unmapped)):
            if mass <= 0:
                continue
            typed_kind: FieldMassKind = "known" if kind == "known" else "unmapped"
            base = _decision(item, typed_kind)
            decisions.append(
                SourceFieldMassDecision(
                    **vars(base),
                    source_field_evidence=item,
                    mass_kind=typed_kind,
                )
            )
            units.append((base.subject_id, mass))
    population = SourceFieldMassPopulation(
        evidence_kind="field-classification",
        units=tuple(sorted(units)),
        formula_inputs=tuple(inputs),
        source_manifest_digest=canonical_digest(
            tuple(sorted(source_projections, key=lambda item: item.paper_id))
        ),
        source_field_evidence=field_evidence,
        source_projections=source_projections,
    )
    return certify_coverage(
        "field-classification", tuple(decisions), population
    ), tuple(decisions)


def validate_source_field_mass_decisions(
    population: SourceFieldMassPopulation,
    decisions: tuple[EvidenceCertificationDecision, ...],
) -> None:
    population.__post_init__()
    by_paper = {
        item.context.paper_id: item for item in population.source_field_evidence
    }
    expected = {}
    for paper_id, evidence in by_paper.items():
        known, unmapped = _parts(evidence)
        if known > 0:
            expected[field_mass_unit_id(paper_id, "known")] = (evidence, "known")
        if unmapped > 0:
            expected[field_mass_unit_id(paper_id, "unmapped")] = (evidence, "unmapped")
    if (
        len(decisions) != len(expected)
        or {item.subject_id for item in decisions} != set(expected)
        or any(
            not isinstance(item, SourceFieldMassDecision)
            or (item.source_field_evidence, item.mass_kind) != expected[item.subject_id]
            for item in decisions
        )
    ):
        raise CertificationError(
            "field mass coverage decisions do not bind the exact source universe"
        )
    for item in decisions:
        item.__post_init__()
