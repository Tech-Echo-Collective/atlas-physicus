"""Citation measurement over independently certified, frozen scientific membership.

This does not pretend mutable pagination is a snapshot. Missing INSPIRE identities
stay outside the measurable reference universe and inside source-year/metric
coverage denominators. Neither freezing IDs nor receiving pages certifies a year.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

from .citation_sessions import (
    CitationMeasurementSession,
    FrozenCitationPopulationEvidence,
    derive_session_citation_observations,
)
from .citations import CITATION_MATURITY_MONTHS_V1, IMPACT_REFERENCE_COHORT_MINIMUM_V1
from .contracts import CertificationError, EvidenceReference, canonical_digest

if TYPE_CHECKING:
    from .citations import CitationObservationCertification
    from .years import CertifiedSourceYear, SourceYearPaperProjection

SESSION_CITATION_POLICY_VERSION = "non-self-citation-measurement-window-v1"


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
        return tuple(
            sorted(
                paper.paper_id
                for paper in self.paper_projections
                if not any(
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
        for paper in self.paper_projections:
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
        )
        for item in proofs
    }
    if len(keys) != 1:
        raise CertificationError(
            "citation comparison mixes sessions or frozen populations"
        )
    first = proofs[0]
    return first.session_id, first.started_at.isoformat(), first.ended_at.isoformat()
