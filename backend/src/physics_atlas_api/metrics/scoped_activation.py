"""An explicitly limited release boundary, never a claim of broad Physics.

PA-056 permits a first complete five-metric release on a certified ontology
branch. The scientific gates remain unchanged. Scope identity must reconstruct
from complete, source-bound years, not a caller's favourable field subset.
"""

from dataclasses import dataclass, replace

from ..certification import CertificationError, canonical_digest
from ..certification.launch_scope import BoundedLaunchSourcePlan
from ..certification.years import CertifiedMetricWindow, CertifiedSourceYear
from ..fields import PHYSICS_FIELD_ONTOLOGY_V1

SCOPED_DATASET_ACTIVATION_VERSION = "certified-ontology-branch-release-v1"


@dataclass(frozen=True)
class CertifiedDatasetScope:
    source_years: tuple[CertifiedSourceYear, ...]
    certification_digest: str
    version: str = SCOPED_DATASET_ACTIVATION_VERSION

    def __post_init__(self) -> None:
        if self.version != SCOPED_DATASET_ACTIVATION_VERSION:
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
