"""An explicitly limited release boundary, never a claim of broad Physics.

PA-056 permits a first complete five-metric release on a certified ontology
branch. The scientific gates remain unchanged. Scope identity must reconstruct
from complete, source-bound years, not a caller's favourable field subset.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ..certification import CertificationError, canonical_digest
from ..certification.launch_scope import BoundedLaunchSourcePlan
from ..certification.years import (
    CertifiedMetricWindow,
    CertifiedSourceYear,
    ConditionalObservedSourceYearEvidence,
    source_quality_certification,
)
from ..fields import PHYSICS_FIELD_ONTOLOGY_V1

if TYPE_CHECKING:
    from .presentation import AtlasScaleObservation

SCOPED_DATASET_ACTIVATION_VERSION = "certified-ontology-branch-release-v1"
CONDITIONAL_OBSERVED_DATASET_VERSION = "conditional-observed-ontology-branch-release-v1"


@dataclass(frozen=True)
class CertifiedDatasetScope:
    source_years: tuple[CertifiedSourceYear, ...]
    certification_digest: str
    version: str = SCOPED_DATASET_ACTIVATION_VERSION

    def __post_init__(self) -> None:
        conditional = isinstance(self, ConditionalObservedDatasetScope)
        expected_version = (
            CONDITIONAL_OBSERVED_DATASET_VERSION
            if conditional
            else SCOPED_DATASET_ACTIVATION_VERSION
        )
        if self.version != expected_version:
            raise CertificationError("unsupported scoped dataset activation version")
        if not self.source_years or any(
            not isinstance(year, CertifiedSourceYear) for year in self.source_years
        ):
            raise CertificationError(
                "scoped activation requires certified source years"
            )
        keys: set[tuple[str, int]] = set()
        lineages: set[tuple[str, str, str, str]] = set()
        by_type: dict[str, set[int]] = {}
        for year in self.source_years:
            year.__post_init__()
            if (
                isinstance(year.evidence, ConditionalObservedSourceYearEvidence)
                != conditional
            ):
                raise CertificationError(
                    "release scope mixes full-source and conditional source authority"
                )
            plan = year.evidence.acquisition_plan
            if not isinstance(plan, BoundedLaunchSourcePlan):
                raise CertificationError(
                    "scoped activation requires the fixed launch plan"
                )
            plan.__post_init__()
            if year.state != "certified":
                raise CertificationError(
                    "scoped activation has an uncertified source year"
                )
            key = (year.evidence.entity_type, year.calendar_year)
            if key in keys:
                raise CertificationError(
                    "scoped activation source years are duplicated"
                )
            keys.add(key)
            by_type.setdefault(key[0], set()).add(key[1])
            lineages.add(
                (
                    plan.root_field_id,
                    year.dataset_version,
                    year.acquisition_scope,
                    year.cutoff.isoformat(),
                )
            )
        if len(lineages) != 1 or any(
            years != set(range(2018, 2024)) for years in by_type.values()
        ):
            raise CertificationError(
                "scoped activation requires one complete six-year lineage"
            )
        if self.certification_digest != self.content_digest:
            raise CertificationError("scoped activation proof does not reconstruct")

    @property
    def content_digest(self) -> str:
        return canonical_digest(
            (
                self.version,
                tuple(
                    sorted(
                        (
                            year.evidence.entity_type,
                            year.calendar_year,
                            year.certification_id,
                        )
                        for year in self.source_years
                    )
                ),
            )
        )

    @property
    def root_field_id(self) -> str:
        plan = self.source_years[0].evidence.acquisition_plan
        if not isinstance(plan, BoundedLaunchSourcePlan):
            raise CertificationError("scoped activation has no fixed launch plan")
        return plan.root_field_id

    @property
    def leaf_field_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                item.id
                for item in PHYSICS_FIELD_ONTOLOGY_V1.fields
                if item.node_kind == "field"
                and any(
                    ancestor.id == self.root_field_id
                    for ancestor in PHYSICS_FIELD_ONTOLOGY_V1.ancestors_of(item.id)
                )
            )
        )

    @property
    def dataset_version(self) -> str:
        return self.source_years[0].dataset_version

    @property
    def acquisition_scope(self) -> str:
        return self.source_years[0].acquisition_scope

    def require_source_inventory(
        self, year: CertifiedSourceYear
    ) -> CertifiedSourceYear:
        """Find exact retained authority; equal version labels are insufficient.

        The canonical projection digest includes affiliations, field weights and
        unresolved mass. Exact page/record receipts and the complete acquisition
        recipe additionally bind the denominator and source population. Cutoff
        compatibility is enforced separately by ``require_metric_window``.
        """
        if not isinstance(year, CertifiedSourceYear):
            raise CertificationError("scoped export requires certified source years")
        year.__post_init__()
        authority = next(
            (
                item
                for item in self.source_years
                if (
                    item.evidence.entity_type == year.evidence.entity_type
                    and item.calendar_year == year.calendar_year
                )
            ),
            None,
        )
        if authority is None or year.state != "certified":
            raise CertificationError(
                "source year is outside the retained release scope"
            )
        plan = year.evidence.acquisition_plan
        authority_plan = authority.evidence.acquisition_plan
        if (
            not isinstance(plan, BoundedLaunchSourcePlan)
            or not isinstance(authority_plan, BoundedLaunchSourcePlan)
            or replace(plan, cutoff=authority_plan.cutoff) != authority_plan
            or year.certification.canonical_paper_population_digest
            != authority.certification.canonical_paper_population_digest
            or year.evidence.partitions != authority.evidence.partitions
            or year.evidence.required_partition_ids
            != authority.evidence.required_partition_ids
            or year.rule_version != authority.rule_version
        ):
            raise CertificationError(
                "metric source inventory, pages or acquisition recipe "
                "differs from release authority"
            )
        return authority

    def require_metric_window(self, window: CertifiedMetricWindow) -> None:
        """Bind every calculation/normalization window to this release authority.

        Normally the final source-year certifications must match exactly. The
        only permitted later horizon is the existing PA-055 Impact measurement
        session over this exact earlier frozen authority, not a cutoff relabel.
        """
        from ..certification.measurement_windows import (
            CertifiedSessionCitationCohort,
            require_session_cohort,
            session_comparison_key,
        )

        if not isinstance(window, CertifiedMetricWindow):
            raise CertificationError("scoped export requires a certified metric window")
        window.__post_init__()
        sessions = tuple(
            item
            for item in window.citation_cohorts
            if isinstance(item, CertifiedSessionCitationCohort)
        )
        if sessions:
            if len(sessions) != len(window.citation_cohorts):
                raise CertificationError(
                    "scoped source authority cannot mix citation policies"
                )
            session_comparison_key(sessions)
            for cohort in sessions:
                require_session_cohort(
                    cohort,
                    dataset_version=self.dataset_version,
                    acquisition_scope=self.acquisition_scope,
                    evaluation_horizon=window.cutoff.date(),
                )
                if cohort.ended_at > window.cutoff:
                    raise CertificationError(
                        "citation measurement exceeds its release horizon"
                    )
                # Frozen population evidence must come from these exact pages and
                # projections too, not another population bearing the same label.
                for frozen_year in cohort.population.source_years:
                    self.require_source_inventory(frozen_year)
        for year in window.source_years:
            authority = self.require_source_inventory(year)
            if year.certification_id == authority.certification_id:
                continue
            if (
                window.certification.metric_id != "research_impact"
                or year.cutoff <= authority.cutoff
                or not sessions
                or any(
                    not any(
                        frozen.certification_id == authority.certification_id
                        for frozen in cohort.population.source_years
                    )
                    for cohort in sessions
                )
            ):
                raise CertificationError(
                    "source-year certification differs without an exact "
                    "frozen measurement bridge"
                )

    def release_metadata(self) -> dict[str, object]:
        return {
            "version": self.version,
            "rootFieldId": self.root_field_id,
            "leafFieldIds": list(self.leaf_field_ids),
            "boundaryKind": "ontology-branch",
            "certificationDigest": self.certification_digest,
            "sourceYearProofs": [
                {
                    "entityType": year.evidence.entity_type,
                    "year": year.calendar_year,
                    "certificationId": year.certification_id,
                }
                for year in self.source_years
            ],
        }


def certify_dataset_scope(
    source_years: tuple[CertifiedSourceYear, ...],
) -> CertifiedDatasetScope:
    digest = canonical_digest(
        (
            SCOPED_DATASET_ACTIVATION_VERSION,
            tuple(
                sorted(
                    (
                        year.evidence.entity_type,
                        year.calendar_year,
                        year.certification_id,
                    )
                    for year in source_years
                )
            ),
        )
    )
    return CertifiedDatasetScope(source_years, digest)


def _observation_key(
    observation: AtlasScaleObservation,
) -> tuple[str, str, str, str, str]:
    item = observation.calculation
    return item.entity_type, item.entity_id, item.field_id, item.period, item.metric_id


def _conditional_digest(
    source_years: tuple[CertifiedSourceYear, ...],
    observations: tuple[AtlasScaleObservation, ...],
) -> str:
    return canonical_digest(
        (
            CONDITIONAL_OBSERVED_DATASET_VERSION,
            tuple(
                sorted(
                    (
                        item.evidence.entity_type,
                        item.calendar_year,
                        item.certification_id,
                    )
                    for item in source_years
                )
            ),
            tuple(
                sorted(
                    (
                        _observation_key(item),
                        item.value,
                        item.certification_manifest_digest,
                    )
                    for item in observations
                )
            ),
        )
    )


@dataclass(frozen=True, kw_only=True)
class ConditionalObservedDatasetScope(CertifiedDatasetScope):
    """PA-062: exact released observations, not source-wide ecosystem estimates."""

    released_observations: tuple[AtlasScaleObservation, ...]
    version: str = CONDITIONAL_OBSERVED_DATASET_VERSION

    def __post_init__(self) -> None:
        from ..certification.populations import (
            OBSERVED_ATTRIBUTION_COVERAGE_VERSION,
            CertifiedMetricPopulation,
            metric_population_coverage_policy,
        )
        from .aggregation import CertifiedOntologyBranchAggregation
        from .contracts import CANDIDATE_METRIC_IDS
        from .presentation import AtlasScaleObservation, CertifiedMetricCalculation
        from .thresholds import METRIC_VALIDATION_THRESHOLDS_V1

        CertifiedDatasetScope.__post_init__(self)
        if not self.released_observations or any(
            not isinstance(item, AtlasScaleObservation)
            for item in self.released_observations
        ):
            raise CertificationError(
                "conditional release requires actual Atlas observations"
            )
        keys = [_observation_key(item) for item in self.released_observations]
        if len(set(keys)) != len(keys) or {key[-1] for key in keys} != set(
            CANDIDATE_METRIC_IDS
        ):
            raise CertificationError(
                "conditional release requires unique exact-five observations"
            )
        groups: dict[tuple[str, ...], set[str]] = {}
        verified: set[int] = set()
        for observation in self.released_observations:
            if (
                observation.value is None
                or observation.thresholds != METRIC_VALIDATION_THRESHOLDS_V1
            ):
                raise CertificationError(
                    "conditional release cannot certify missing values "
                    "or changed thresholds"
                )
            if isinstance(
                observation.certification_proof, CertifiedOntologyBranchAggregation
            ):
                observation.certification_proof.field_population_proof.__post_init__()
                observation.certification_proof.__post_init__()
            for direct in self._direct_observations(observation):
                proof = direct.certification_proof
                if not isinstance(proof, CertifiedMetricCalculation):
                    raise CertificationError("conditional leaf lacks a calculation")
                for calculation in (proof, *direct.normalization_proofs):
                    if id(calculation) in verified:
                        continue
                    calculation.__post_init__()
                    population = calculation.partition.population_proof
                    if (
                        not isinstance(population, CertifiedMetricPopulation)
                        or metric_population_coverage_policy(
                            population.certification.evidence
                        )
                        != OBSERVED_ATTRIBUTION_COVERAGE_VERSION
                    ):
                        raise CertificationError(
                            "conditional release cannot mix population "
                            "coverage policies"
                        )
                    window = calculation.partition.window_proof
                    if not isinstance(window, CertifiedMetricWindow):
                        raise CertificationError(
                            "conditional release requires exact source windows"
                        )
                    if id(window) not in verified:
                        self.require_metric_window(window)
                        verified.add(id(window))
                    verified.add(id(calculation))
                if id(direct) not in verified:
                    direct.__post_init__()
                    if direct.normalization_population_proof is not None:
                        direct.normalization_population_proof.__post_init__()
                    verified.add(id(direct))
            observation.__post_init__()
            key = _observation_key(observation)
            if key[2] not in {self.root_field_id, *self.leaf_field_ids}:
                raise CertificationError("conditional field exceeds release scope")
            if key[2] == self.root_field_id:
                groups.setdefault(key[:2] + key[3:4], set()).add(key[-1])
        if not any(ids == set(CANDIDATE_METRIC_IDS) for ids in groups.values()):
            raise CertificationError(
                "conditional release needs co-located five-way observations"
            )

    @property
    def content_digest(self) -> str:
        return _conditional_digest(self.source_years, self.released_observations)

    def _direct_observations(
        self, observation: AtlasScaleObservation
    ) -> tuple[AtlasScaleObservation, ...]:
        from .aggregation import (
            CertifiedOntologyBranchAggregation,
            OntologyBranchPopulationEvidence,
        )
        from .presentation import CertifiedMetricCalculation

        proof = observation.certification_proof
        if isinstance(proof, CertifiedMetricCalculation):
            return (observation,)
        if isinstance(proof, CertifiedOntologyBranchAggregation):
            evidence = proof.field_population_proof.evidence
            if (
                isinstance(evidence, OntologyBranchPopulationEvidence)
                and evidence.branch_id == self.root_field_id
                and all(
                    isinstance(item.certification_proof, CertifiedMetricCalculation)
                    for item in proof.field_observations
                )
            ):
                return proof.field_observations
        raise CertificationError(
            "conditional release requires exact field or named-branch proofs"
        )

    def observed_coverage(self) -> dict[str, float | None]:
        from .presentation import CertifiedMetricCalculation

        kinds = {
            "paper_time_affiliation": "paper-time-affiliation",
            "canonical_institution": "canonical-institution",
            "citation": "citation-observation",
            "field_attribution": "field-classification",
        }
        values: dict[str, list[float]] = {kind: [] for kind in kinds.values()}
        for observation in (
            direct
            for item in self.released_observations
            for direct in self._direct_observations(item)
        ):
            proof = observation.certification_proof
            if not isinstance(proof, CertifiedMetricCalculation):
                raise CertificationError(
                    "conditional coverage lacks a scientific partition"
                )
            for certificate in proof.partition.certification.coverage:
                if certificate.evidence_kind in values:
                    if certificate.state != "certified" or certificate.ratio is None:
                        raise CertificationError(
                            "released entity coverage is not certified"
                        )
                    values[certificate.evidence_kind].append(certificate.ratio)
        return {
            name: min(values[kind]) if values[kind] else None
            for name, kind in kinds.items()
        }

    def require_published_observations(
        self, observations: tuple[AtlasScaleObservation, ...]
    ) -> None:
        numeric = tuple(item for item in observations if item.value is not None)
        if {_observation_key(item): item for item in numeric} != {
            _observation_key(item): item for item in self.released_observations
        } or len(numeric) != len(self.released_observations):
            raise CertificationError(
                "published observations differ from conditional release authority"
            )

    def release_metadata(self) -> dict[str, object]:
        from ..certification.measurement_windows import (
            CertifiedObservedSessionCitationCohort,
            CertifiedSessionCitationCohort,
            citation_reference_membership_version,
        )
        from .automatic_normalization import conditional_normalization_disclosure
        from .presentation import CertifiedMetricCalculation

        result = super().release_metadata()
        result["interpretation"] = (
            "Conditional observations of the recorded research ecosystem, "
            "not complete ecosystem estimates."
        )
        result["momentumCaveat"] = (
            "Momentum compares observed windows; changes in evidence coverage "
            "may affect apparent change."
        )
        result["observedCoverage"] = self.observed_coverage()
        # Keep original frozen quality and later measured citation quality: these
        # are different dated evidence, not a replacement of the original state.
        quality_years = {year.certification_id: year for year in self.source_years}
        citation_cohorts: dict[str, dict[str, object]] = {}
        normalization_cohorts: dict[str, dict[str, object]] = {}
        seen_citations: set[int] = set()
        for observation in (
            direct
            for item in self.released_observations
            for direct in self._direct_observations(item)
        ):
            proof = observation.certification_proof
            if not isinstance(proof, CertifiedMetricCalculation):
                raise CertificationError("conditional quality lacks exact proof")
            window = proof.partition.window_proof
            if not isinstance(window, CertifiedMetricWindow):
                raise CertificationError("conditional quality lacks exact window")
            for year in window.source_years:
                quality_years[year.certification_id] = year
            for cohort in window.citation_cohorts:
                if not isinstance(cohort, CertifiedSessionCitationCohort):
                    continue
                if id(cohort) in seen_citations:
                    continue
                seen_citations.add(id(cohort))
                cohort_id = cohort.certification_id
                citation_cohorts[cohort_id] = {
                    "certificationId": cohort_id,
                    "fieldId": cohort.cohort_key[0],
                    "publicationYear": cohort.cohort_key[1],
                    "documentType": cohort.cohort_key[2],
                    "sessionId": cohort.session_id,
                    "measurementStartedAt": cohort.started_at.isoformat(),
                    "measurementEndedAt": cohort.ended_at.isoformat(),
                    "referenceMembershipVersion": citation_reference_membership_version(
                        cohort
                    ),
                    "referencePopulation": (
                        cohort.reference_population_metadata
                        if isinstance(cohort, CertifiedObservedSessionCitationCohort)
                        else {
                            "completeFieldUniverse": True,
                            "knownReferencePaperCount": len(cohort.counts),
                        }
                    ),
                }
            population = observation.normalization_population_proof
            if (
                population
                and population.certification_digest not in normalization_cohorts
            ):
                disclosure = conditional_normalization_disclosure(population)
                if disclosure:
                    item = observation.calculation
                    normalization_cohorts[population.certification_digest] = {
                        "certificationDigest": population.certification_digest,
                        "metricId": item.metric_id,
                        "entityType": item.entity_type,
                        "fieldId": item.field_id,
                        "period": item.period,
                        **disclosure,
                    }
        # These are once-per-cohort compact counts, not repeated peer lists or
        # per-paper traces. Full source inventories stay in the scientific proof.
        result["citationCohorts"] = [
            citation_cohorts[key] for key in sorted(citation_cohorts)
        ]
        result["normalizationCohorts"] = [
            normalization_cohorts[key] for key in sorted(normalization_cohorts)
        ]
        result["sourceYearQuality"] = [
            {
                "entityType": year.evidence.entity_type,
                "year": year.calendar_year,
                "status": quality.state,
                "reasons": list(quality.reasons),
                "certificationId": quality.certification_id,
                "paperCount": len(year.evidence.paper_projections),
                "cutoff": year.cutoff.isoformat(),
                "coverage": [
                    {
                        "kind": item.evidence_kind,
                        "numerator": item.numerator,
                        "denominator": item.denominator,
                        "ratio": item.ratio,
                        "minimum": item.minimum,
                        "status": item.state,
                        "reasons": list(item.reasons),
                    }
                    for item in year.coverage
                ],
            }
            for year in sorted(
                quality_years.values(),
                key=lambda item: (
                    item.evidence.entity_type,
                    item.calendar_year,
                    item.cutoff,
                    item.certification_id,
                ),
            )
            for quality in (source_quality_certification(year),)
        ]
        return result


def certify_conditional_observed_dataset_scope(
    source_years: tuple[CertifiedSourceYear, ...],
    observations: tuple[AtlasScaleObservation, ...],
) -> ConditionalObservedDatasetScope:
    from .presentation import AtlasScaleObservation

    if any(not isinstance(item, AtlasScaleObservation) for item in observations):
        raise CertificationError(
            "conditional release requires actual Atlas observations"
        )
    numeric = tuple(item for item in observations if item.value is not None)
    return ConditionalObservedDatasetScope(
        source_years=source_years,
        certification_digest=_conditional_digest(source_years, numeric),
        released_observations=numeric,
    )
