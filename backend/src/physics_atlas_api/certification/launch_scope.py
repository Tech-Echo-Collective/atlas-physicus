"""One bounded, exact-date nuclear recipe, separate from production acquisition.

This verifies the requested recipe and frozen ontology boundary, not successful
acquisition, canonical completeness, scientific coverage, or metric activation.
"""

from dataclasses import dataclass
from datetime import datetime

from ..backfill import HistoricalPartition
from ..connectors.inspire import InspireConnector
from ..fields import PHYSICS_FIELD_ONTOLOGY_V1, PHYSICS_FIELD_ONTOLOGY_VERSION
from .contracts import CertificationError, canonical_digest

BOUNDED_LAUNCH_SCOPE = "nuclear-physics-launch-v1"
BOUNDED_LAUNCH_ROOT_FIELD = "nuclear"
BOUNDED_LAUNCH_YEARS = tuple(range(2018, 2024))
BOUNDED_LAUNCH_QUERY_VERSION = "nuclear:inspire:exact-preprint-year-v1"
BOUNDED_LAUNCH_PLAN_VERSION = "bounded-nuclear-launch-source-plan-v1"
BOUNDED_LAUNCH_DATE_BASIS = "inspire-preprint-date"


def bounded_launch_partitions() -> tuple[HistoricalPartition, ...]:
    """Return six fixed partitions; no registry mutation or network access."""
    return tuple(
        HistoricalPartition(
            provider="inspire",
            year=year,
            query=(
                "document_type:article and (subject:Theory-Nucl or "
                f"subject:Experiment-Nucl) and preprint_date:{year}-01-01->{year}-12-31"
            ),
            query_version=BOUNDED_LAUNCH_QUERY_VERSION,
            source_version=InspireConnector.source_version,
            endpoint="https://inspirehep.net/api/literature",
            page_size=250,
            acquisition_scope=BOUNDED_LAUNCH_SCOPE,
        )
        for year in BOUNDED_LAUNCH_YEARS
    )


@dataclass(frozen=True)
class BoundedLaunchSourcePlan:
    root_field_id: str
    calendar_year: int
    cutoff: datetime
    dataset_version: str
    acquisition_scope: str
    query_partitions: tuple[HistoricalPartition, ...]
    declared_date_basis: str = BOUNDED_LAUNCH_DATE_BASIS
    ontology_version: str = PHYSICS_FIELD_ONTOLOGY_VERSION
    rule_version: str = BOUNDED_LAUNCH_PLAN_VERSION

    def __post_init__(self) -> None:
        expected = tuple(
            item
            for item in bounded_launch_partitions()
            if item.year == self.calendar_year
        )
        if (
            self.root_field_id != BOUNDED_LAUNCH_ROOT_FIELD
            or self.acquisition_scope != BOUNDED_LAUNCH_SCOPE
            or not isinstance(self.calendar_year, int)
            or isinstance(self.calendar_year, bool)
            or self.calendar_year not in BOUNDED_LAUNCH_YEARS
            or self.cutoff.tzinfo is None
            or self.cutoff.utcoffset() is None
            or self.calendar_year >= self.cutoff.year
            or not self.dataset_version.strip()
            or self.declared_date_basis != BOUNDED_LAUNCH_DATE_BASIS
            or self.ontology_version != PHYSICS_FIELD_ONTOLOGY_VERSION
            or self.rule_version != BOUNDED_LAUNCH_PLAN_VERSION
            or self.query_partitions != expected
            or set(self.expected_leaf_ids) != {"nucl-th", "nucl-ex"}
        ):
            raise CertificationError(
                "bounded launch source plan differs from its exact approved recipe"
            )

    @property
    def expected_leaf_ids(self) -> tuple[str, ...]:
        return tuple(
            item.id
            for item in PHYSICS_FIELD_ONTOLOGY_V1.fields
            if item.parent_id == self.root_field_id and item.node_kind == "field"
        )

    @property
    def partitions(self) -> tuple[tuple[str, str], ...]:
        return tuple((item.id, item.provider) for item in self.query_partitions)

    @property
    def content_digest(self) -> str:
        return canonical_digest(self)

    @property
    def source_manifest_digest(self) -> str:
        return self.content_digest


def bounded_launch_source_plan(
    *,
    calendar_year: int,
    cutoff: datetime,
    dataset_version: str,
    root_field_id: str = BOUNDED_LAUNCH_ROOT_FIELD,
    acquisition_scope: str = BOUNDED_LAUNCH_SCOPE,
) -> BoundedLaunchSourcePlan:
    return BoundedLaunchSourcePlan(
        root_field_id,
        calendar_year,
        cutoff,
        dataset_version,
        acquisition_scope,
        tuple(
            item for item in bounded_launch_partitions() if item.year == calendar_year
        ),
    )
