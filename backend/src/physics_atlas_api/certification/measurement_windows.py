"""Citation measurement over independently certified, frozen scientific membership.

This does not pretend mutable pagination is a snapshot. Missing INSPIRE identities
stay outside the measurable reference universe and inside source-year/metric
coverage denominators. Neither freezing IDs nor receiving pages certifies a year.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

from .citation_sessions import (
    CitationMeasurementSession,
    FrozenCitationPopulationEvidence,
    derive_observed_session_citation_observations,
    derive_session_citation_observations,
)
from .citations import CITATION_MATURITY_MONTHS_V1, IMPACT_REFERENCE_COHORT_MINIMUM_V1
from .contracts import CertificationError, EvidenceReference, canonical_digest

if TYPE_CHECKING:
    from .citations import CitationObservationCertification
    from .years import CertifiedSourceYear, SourceYearPaperProjection

SESSION_CITATION_POLICY_VERSION = "non-self-citation-measurement-window-v1"
COMPLETE_FIELD_REFERENCE_MEMBERSHIP_VERSION = "complete-field-reference-membership-v1"
OBSERVED_POSITIVE_FIELD_CITATION_MEMBERSHIP_VERSION = (
    "observed-positive-field-citation-membership-v1"
)


def partition_citation_policy_is_current(
    partition: object, metric_id: str, cohorts: tuple[object, ...]
) -> bool:
    from .citations import CITATION_POLICY_VERSION

    policy = getattr(partition, "citation_policy_version", None)
    if policy == CITATION_POLICY_VERSION:
        return not any(
            isinstance(item, CertifiedSessionCitationCohort) for item in cohorts
        )
    if (
        policy != SESSION_CITATION_POLICY_VERSION
        or metric_id != "research_impact"
        or not cohorts
    ):
        return False
    if not all(isinstance(item, CertifiedSessionCitationCohort) for item in cohorts):
        return False
    session_comparison_key(
        tuple(
            item for item in cohorts if isinstance(item, CertifiedSessionCitationCohort)
        )
    )
    return True


@dataclass(frozen=True)
class FrozenScientificCitationPopulation:
    source_years: tuple[CertifiedSourceYear, ...]
    frozen_at: datetime
    declared_date_basis: str

    def __post_init__(self) -> None:
        from .years import CertifiedSourceYear

        if (
            not self.source_years
            or any(
                not isinstance(item, CertifiedSourceYear) for item in self.source_years
            )
            or self.frozen_at.tzinfo is None
            or self.frozen_at.utcoffset() is None
            or not self.declared_date_basis.strip()
        ):
            raise CertificationError(
                "citation membership needs certified source years and freeze time"
            )
        for item in self.source_years:
            item.__post_init__()
            if item.state != "certified" or item.evidence.cutoff > self.frozen_at:
                raise CertificationError(
                    "citation population must be certified before its freeze"
                )
        if (
            len({item.evidence.calendar_year for item in self.source_years})
            != len(self.source_years)
            or len(
                {
                    (
                        item.evidence.dataset_version,
                        item.evidence.acquisition_scope,
                        item.evidence.entity_type,
                        item.rule_version,
                    )
                    for item in self.source_years
                }
            )
            != 1
            or len(self.paper_projections)
            != len({item.paper_id for item in self.paper_projections})
        ):
            raise CertificationError(
                "frozen citation population mixes lineage or repeats source papers"
            )
        self.measurement_population.validate()

    @property
    def paper_projections(self) -> tuple[SourceYearPaperProjection, ...]:
        return tuple(
            paper
            for year in self.source_years
            for paper in year.evidence.paper_projections
        )

    @property
    def unmeasurable_paper_ids(self) -> tuple[str, ...]:
        certified_identities = {
            decision.subject_id
            for year in self.source_years
            for decision in year.evidence.structural_decisions
            if decision.evidence_kind == "canonical-paper-identity"
            and decision.state == "certified"
        }
        return tuple(
            sorted(
                paper.paper_id
                for paper in self.paper_projections
                if paper.paper_id not in certified_identities
                or not any(
                    ref.provider == "inspire" for ref in paper.occurrence_references
                )
            )
        )

    @property
    def content_digest(self) -> str:
        return canonical_digest(self)

    @property
    def measurement_population(self) -> FrozenCitationPopulationEvidence:
        pairs: list[tuple[str, str]] = []
        unmeasurable = set(self.unmeasurable_paper_ids)
        for paper in self.paper_projections:
            if paper.paper_id in unmeasurable:
                continue
            identifiers = {
                ref.source_record_id
                for ref in paper.occurrence_references
                if ref.provider == "inspire"
            }
            if len(identifiers) > 1:
                raise CertificationError(
                    "one canonical citation paper has conflicting provider identities"
                )
            pairs.extend((identifier, paper.paper_id) for identifier in identifiers)
        inventory = tuple(sorted(pairs))
        if not inventory or len({key for key, _ in inventory}) != len(inventory):
            raise CertificationError("frozen citation inventory is empty or ambiguous")
        first = self.source_years[0].evidence
        return FrozenCitationPopulationEvidence(
            reference=EvidenceReference(
                provider="atlas-certified-population",
                source_record_id=canonical_digest(self.source_years),
                checksum=canonical_digest(inventory),
                source_snapshot_id=self.content_digest,
                storage_reference=f"certified-citation-population:{self.content_digest}",
            ),
            dataset_version=first.dataset_version,
            acquisition_scope=first.acquisition_scope,
            declared_date_basis=self.declared_date_basis,
            frozen_at=self.frozen_at,
            provider_to_canonical=inventory,
        )


@dataclass(frozen=True)
class CertifiedSessionCitationCohort:
    population: FrozenScientificCitationPopulation
    session: CitationMeasurementSession
    cohort_key: tuple[str, int, str]
    policy_version: str = SESSION_CITATION_POLICY_VERSION

    @property
    def state(self) -> str:
        return "certified"

    def __post_init__(self) -> None:
        if not isinstance(
            self.population, FrozenScientificCitationPopulation
        ) or not isinstance(self.session, CitationMeasurementSession):
            raise CertificationError(
                "session cohort needs typed source population and measurement"
            )
        self.population.__post_init__()
        self.session.__post_init__()
        if (
            self.policy_version != SESSION_CITATION_POLICY_VERSION
            or self.session.frozen_population != self.population.measurement_population
        ):
            raise CertificationError(
                "session cohort differs from independently certified membership"
            )
        projections = {
            paper.paper_id: paper for paper in self.population.paper_projections
        }
        for page in self.session.pages:
            for record in page.records:
                source = projections[record.paper_id]
                if record.publication_date != source.publication_date or set(
                    record.field_ids
                ) != {field for field, weight in source.field_weights if weight > 0}:
                    raise CertificationError(
                        "measurement date or field differs from frozen "
                        "scientific evidence"
                    )
        observations = self.observations
        if len(observations) < IMPACT_REFERENCE_COHORT_MINIMUM_V1:
            raise CertificationError(
                "session citation cohort is below the v1 50-paper minimum"
            )
        if any(
            item.state != "certified"
            or item.maturity_months != CITATION_MATURITY_MONTHS_V1
            for item in observations
        ):
            raise CertificationError(
                "session citation cohort contains missing or immature evidence"
            )

    @property
    def observations(self) -> tuple[CitationObservationCertification, ...]:
        return derive_session_citation_observations(self.session, self.cohort_key)

    @property
    def dataset_version(self) -> str:
        return self.session.frozen_population.dataset_version

    @property
    def acquisition_scope(self) -> str:
        return self.session.frozen_population.acquisition_scope

    @property
    def session_id(self) -> str:
        return self.session.session_id

    @property
    def source_year_certification_ids(self) -> tuple[str, ...]:
        return tuple(
            item.certification.certification_id for item in self.population.source_years
        )

    @property
    def source_year_population_digests(self) -> tuple[tuple[int, str], ...]:
        return tuple(
            sorted(
                (
                    item.evidence.calendar_year,
                    item.certification.canonical_paper_population_digest,
                )
                for item in self.population.source_years
            )
        )

    @property
    def started_at(self) -> datetime:
        return self.session.measurement_started_at

    @property
    def ended_at(self) -> datetime:
        return self.session.measurement_finished_at

    @property
    def counts(self) -> tuple[tuple[str, float], ...]:
        return tuple(
            (item.paper_id, float(item.non_self_citation_count))
            for item in self.observations
            if item.non_self_citation_count is not None
        )

    def actual_observed_at(self, paper_id: str) -> datetime:
        for item in self.observations:
            if item.paper_id == paper_id and item.evidence.observed_at is not None:
                return item.evidence.observed_at
        raise CertificationError("paper has no measured session observation")

    @property
    def certification_id(self) -> str:
        return f"citation-measurement-cohort-{canonical_digest(self)}"


@dataclass(frozen=True)
class CertifiedObservedSessionCitationCohort(CertifiedSessionCitationCohort):
    """PA-062 observed reference population, never a complete-field claim.

    Positive field/year/type membership is frozen independently of citation
    counts. Every known member still needs its exact mature non-self observation.
    Unknown source membership remains explicit, not recategorized as nonmembership.
    """

    reference_membership_version: str = (
        OBSERVED_POSITIVE_FIELD_CITATION_MEMBERSHIP_VERSION
    )

    def __post_init__(self) -> None:
        from .years import (
            CONDITIONAL_OBSERVED_SOURCE_YEAR_RULE_VERSION,
            ConditionalObservedSourceYearEvidence,
        )

        if (
            self.reference_membership_version
            != OBSERVED_POSITIVE_FIELD_CITATION_MEMBERSHIP_VERSION
            or not isinstance(self.population, FrozenScientificCitationPopulation)
            or not isinstance(self.session, CitationMeasurementSession)
            or any(
                not isinstance(year.evidence, ConditionalObservedSourceYearEvidence)
                or year.rule_version != CONDITIONAL_OBSERVED_SOURCE_YEAR_RULE_VERSION
                for year in self.population.source_years
            )
        ):
            raise CertificationError(
                "observed reference cohorts require conditional qualified source years"
            )
        _, _, document_types = self._frozen_membership()
        for page in self.session.pages:
            for row in page.records:
                if row.document_type != document_types[row.paper_id]:
                    raise CertificationError(
                        "measured document type differs from frozen source evidence"
                    )
        CertifiedSessionCitationCohort.__post_init__(self)

    def _frozen_membership(
        self,
    ) -> tuple[
        tuple[str, ...],
        dict[str, str | int | float | bool],
        dict[str, str | None],
    ]:
        from .launch_years import LaunchStructuralDecision

        document_types: dict[str, str | None] = {}
        for year in self.population.source_years:
            for decision in year.evidence.structural_decisions:
                if decision.evidence_kind != "canonical-paper-identity":
                    continue
                if not isinstance(decision, LaunchStructuralDecision):
                    raise CertificationError(
                        "observed reference membership lacks captured document types"
                    )
                values = {
                    item.identity.document_type
                    for item in decision.source_paper.occurrences
                }
                document_types[decision.subject_id] = (
                    next(iter(values)) if len(values) == 1 else None
                )
        projections = self.population.paper_projections
        if set(document_types) != {item.paper_id for item in projections}:
            raise CertificationError(
                "frozen observed document-type inventory is incomplete"
            )
        inventory = self.population.measurement_population.provider_to_canonical
        measurable = {paper_id for _, paper_id in inventory}
        field_id, target_year, document_type = self.cohort_key
        candidates = [
            item for item in projections if item.publication_date.year == target_year
        ]
        members: list[str] = []
        unknown_membership = unmeasurable_known = partial_members = known_other = 0
        for item in candidates:
            recorded_type = document_types[item.paper_id]
            if recorded_type is not None and recorded_type != document_type:
                known_other += 1
                continue
            known_weight = dict(item.field_weights).get(field_id, 0.0)
            if known_weight > 0 and recorded_type == document_type:
                if item.paper_id in measurable:
                    members.append(item.paper_id)
                    partial_members += item.unmapped_field_mass > 0
                else:
                    unmeasurable_known += 1
            elif known_weight > 0 or item.unmapped_field_mass > 0:
                unknown_membership += 1
            else:
                known_other += 1
        metadata: dict[str, str | int | float | bool] = {
            "referenceMembershipVersion": self.reference_membership_version,
            "referenceUniverse": (
                "recorded positive field/year/document-type membership"
            ),
            "completeFieldUniverse": False,
            "sourcePaperCount": len(projections),
            "sourceYearPaperCount": len(candidates),
            "frozenMeasurablePaperCount": len(measurable),
            "unmeasurableSourcePaperCount": len(projections) - len(measurable),
            "knownReferencePaperCount": len(members),
            "knownOtherYearPaperCount": len(projections) - len(candidates),
            "knownOtherFieldOrDocumentTypeCount": known_other,
            "unknownTargetMembershipPaperCount": unknown_membership,
            "unmeasurableKnownFieldPaperCount": unmeasurable_known,
            "includedPartialFieldPaperCount": partial_members,
            "sourceYearKnownTargetFieldMass": math.fsum(
                dict(item.field_weights).get(field_id, 0.0) for item in candidates
            ),
            "sourceYearUnmappedFieldMass": math.fsum(
                item.unmapped_field_mass for item in candidates
            ),
            "sourceQualityFailuresRetained": sum(
                item.state != "certified"
                for source_year in self.population.source_years
                for item in source_year.coverage
            ),
        }
        return tuple(sorted(members)), metadata, document_types

    @property
    def frozen_observed_paper_ids(self) -> tuple[str, ...]:
        return self._frozen_membership()[0]

    @property
    def reference_population_metadata(self) -> dict[str, str | int | float | bool]:
        return self._frozen_membership()[1]

    @property
    def observations(self) -> tuple[CitationObservationCertification, ...]:
        return derive_observed_session_citation_observations(
            self.session,
            self.cohort_key,
            frozen_observed_paper_ids=self.frozen_observed_paper_ids,
        )


def citation_reference_membership_version(value: CertifiedSessionCitationCohort) -> str:
    return (
        value.reference_membership_version
        if isinstance(value, CertifiedObservedSessionCitationCohort)
        else COMPLETE_FIELD_REFERENCE_MEMBERSHIP_VERSION
    )


def citation_reference_result_metadata(
    cohorts: Sequence[CertifiedSessionCitationCohort],
) -> dict[str, str | bool | int]:
    """Compact semantics only; export each cohort's detailed counts once."""
    versions = {citation_reference_membership_version(item) for item in cohorts}
    if not versions or versions == {COMPLETE_FIELD_REFERENCE_MEMBERSHIP_VERSION}:
        return {}  # Preserve legacy result shape and hashes exactly.
    if versions != {OBSERVED_POSITIVE_FIELD_CITATION_MEMBERSHIP_VERSION}:
        raise CertificationError("citation reference population meanings cannot mix")
    return {
        "citation_reference_membership_version": (
            OBSERVED_POSITIVE_FIELD_CITATION_MEMBERSHIP_VERSION
        ),
        "citation_reference_universe": "observed-positive-field-membership",
        "citation_reference_complete_field_universe": False,
        "citation_reference_population_count": len(cohorts),
    }


def require_session_cohort(
    value: object,
    *,
    dataset_version: str,
    acquisition_scope: str,
    evaluation_horizon: date,
) -> CertifiedSessionCitationCohort:
    if not isinstance(value, CertifiedSessionCitationCohort):
        raise CertificationError("Impact session needs a certified measured cohort")
    value.__post_init__()
    if (
        value.dataset_version != dataset_version
        or value.acquisition_scope != acquisition_scope
        or value.ended_at.date() > evaluation_horizon
    ):
        raise CertificationError(
            "measurement cohort exceeds its dataset or evaluation horizon"
        )
    return value


def session_comparison_key(
    proofs: Sequence[CertifiedSessionCitationCohort],
) -> tuple[str, str, str]:
    if not proofs:
        raise CertificationError("measurement comparison needs citation cohorts")
    for proof in proofs:
        if not isinstance(proof, CertifiedSessionCitationCohort):
            raise CertificationError(
                "session comparison cannot mix point-cutoff evidence"
            )
        proof.__post_init__()
    keys = {
        (
            item.session_id,
            item.population.content_digest,
            item.policy_version,
            item.started_at,
            item.ended_at,
            citation_reference_membership_version(item),
        )
        for item in proofs
    }
    if len(keys) != 1:
        raise CertificationError(
            "citation comparison mixes sessions or frozen populations"
        )
    first = proofs[0]
    return first.session_id, first.started_at.isoformat(), first.ended_at.isoformat()
