from dataclasses import asdict, dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from ..connectors.base import NormalizedRecord


@dataclass(frozen=True, order=True)
class AffectedMetricPartition:
    entity_type: str
    entity_id: str
    field_id: str | None
    country_id: str | None
    institution_id: str | None
    period: str | None
    metric_id: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


class MetricRecalculationContract(Protocol):
    def recalculate(
        self,
        session: Session,
        partitions: set[AffectedMetricPartition],
        *,
        dataset_version: str,
    ) -> int:
        """Write new versioned observations and return the number created."""


class MetricRecomputationPlanner:
    """Derives bounded partitions; it never treats missing values as zero."""

    def for_records(
        self, records: list[tuple[NormalizedRecord, str | None]]
    ) -> set[AffectedMetricPartition]:
        partitions: set[AffectedMetricPartition] = set()
        for record, canonical_entity_id in records:
            entity_id = (
                canonical_entity_id or f"{record.provider}:{record.source_record_id}"
            )
            period_value = record.attributes.get("publication_year")
            period = str(period_value) if period_value else None
            field_ids = record.attributes.get("atlas_field_candidates") or [None]
            for field_id in field_ids:
                partitions.add(
                    AffectedMetricPartition(
                        entity_type=record.kind,
                        entity_id=entity_id,
                        field_id=field_id,
                        country_id=record.attributes.get("country_id"),
                        institution_id=record.attributes.get("institution_id"),
                        period=period,
                    )
                )
        return partitions


class NoFormulaMetricRecalculator:
    """Alpha boundary: records planned work without inventing scientific formulae."""

    def __init__(self) -> None:
        self.last_partitions: set[AffectedMetricPartition] = set()

    def recalculate(
        self,
        session: Session,
        partitions: set[AffectedMetricPartition],
        *,
        dataset_version: str,
    ) -> int:
        del session, dataset_version
        self.last_partitions = set(partitions)
        return 0
