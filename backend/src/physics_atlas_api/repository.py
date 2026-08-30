from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import Select, case, false, func, or_, select
from sqlalchemy.orm import Session

from . import models
from .attribution import FRACTIONAL_ATTRIBUTION_V1
from .fields import PHYSICS_FIELD_ONTOLOGY_VERSION, PROVIDER_FIELD_MAPPING_VERSION
from .metrics.activation import field_validation_manifest_is_current
from .metrics.contracts import METRIC_CONTRACTS
from .metrics.thresholds import METRIC_VALIDATION_THRESHOLDS_V1
from .search_index import normalize_search_term

PROFILE_AFFILIATION_LIMIT = 500
PROFILE_ENTITY_LIMIT = 500
PROFILE_METRIC_LIMIT = 500
PROFILE_PAPER_LIMIT = 200
PROFILE_RESOURCE_LIMIT = 100
METRIC_SYSTEM_V1_IDS = frozenset(METRIC_CONTRACTS)
METRIC_SYSTEM_V1_ALGORITHMS = {
    metric_id: contract.algorithm_version
    for metric_id, contract in METRIC_CONTRACTS.items()
}
METRIC_SYSTEM_V1_DEFINITIONS = {
    metric_id: contract.version for metric_id, contract in METRIC_CONTRACTS.items()
}


def _resource_ordering() -> tuple[Any, ...]:
    active = or_(
        models.ExternalResource.valid_to.is_(None),
        models.ExternalResource.valid_to >= date.today(),
    )
    health_priority = case(
        (models.ExternalResource.health_status == "reachable", 0),
        (models.ExternalResource.health_status == "permanent-redirect", 1),
        (models.ExternalResource.health_status == "redirect", 2),
        (models.ExternalResource.health_status == "unknown", 3),
        (models.ExternalResource.health_status == "timeout", 4),
        (models.ExternalResource.health_status == "broken", 5),
        else_=6,
    )
    return (
        case((active, 0), else_=1),
        models.ExternalResource.verified.desc(),
        health_priority,
        models.ExternalResource.is_primary.desc(),
        models.ExternalResource.label,
    )


def _provenance(value: dict[str, Any] | None) -> dict[str, Any]:
    source = value or {}
    return {
        "source": source.get("source", "Physics Atlas live-data service"),
        "sourceType": source.get("sourceType", source.get("source_type", "derived")),
        "version": source.get("version", "v3.0.5-alpha"),
        "status": source.get("status", "unverified"),
        **(
            {"confidence": source["confidence"]}
            if source.get("confidence") is not None
            else {}
        ),
        **(
            {"retrievedAt": source.get("retrievedAt", source.get("retrieved_at"))}
            if source.get("retrievedAt", source.get("retrieved_at"))
            else {}
        ),
        **(
            {
                "sourceRecordId": source.get(
                    "sourceRecordId", source.get("source_record_id")
                )
            }
            if source.get("sourceRecordId", source.get("source_record_id"))
            else {}
        ),
        **(
            {
                "sourceSnapshotId": source.get(
                    "sourceSnapshotId", source.get("source_snapshot_id")
                )
            }
            if source.get("sourceSnapshotId", source.get("source_snapshot_id"))
            else {}
        ),
        **(
            {
                "acquisitionScope": source.get(
                    "acquisitionScope", source.get("acquisition_scope")
                )
            }
            if source.get("acquisitionScope", source.get("acquisition_scope"))
            else {}
        ),
    }


def _page[ModelT](
    session: Session, statement: Select[tuple[ModelT]], limit: int, offset: int
) -> tuple[Sequence[ModelT], int]:
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = session.scalars(statement.limit(limit).offset(offset)).all()
    return items, total


def _current_metric_observation_ids(
    *criteria: Any,
) -> Select[tuple[str]]:
    """Select one current, reproducible observation per metric partition.

    A row is current only when its definition version matches the published
    MetricDefinition. Multiple calculation runs of the same algorithm resolve
    to the latest calculated timestamp with stable version/id tie-breakers. If
    current rows disagree on algorithm, no implicit winner exists and the
    partition fails closed.
    """

    observation = models.MetricObservation
    partition = (
        observation.entity_type,
        observation.entity_id,
        observation.science_domain_id,
        observation.field_id,
        observation.metric_id,
        observation.period,
    )
    ranked = (
        select(
            observation.id.label("observation_id"),
            func.min(observation.algorithm_version)
            .over(partition_by=partition)
            .label("minimum_algorithm"),
            func.max(observation.algorithm_version)
            .over(partition_by=partition)
            .label("maximum_algorithm"),
            func.row_number()
            .over(
                partition_by=partition,
                order_by=(
                    observation.calculated_at.desc(),
                    observation.calculation_version.desc(),
                    observation.data_source_version.desc(),
                    observation.id.desc(),
                ),
            )
            .label("calculation_rank"),
        )
        .join(
            models.MetricDefinition,
            models.MetricDefinition.id == observation.metric_id,
        )
        .where(
            observation.value.is_not(None),
            observation.metric_definition_version == models.MetricDefinition.version,
            *criteria,
        )
        .subquery("ranked_current_metric_observations")
    )
    return select(ranked.c.observation_id).where(
        ranked.c.minimum_algorithm == ranked.c.maximum_algorithm,
        ranked.c.calculation_rank == 1,
    )


def _current_dataset_metric_criteria(session: Session) -> tuple[Any, ...]:
    """Bind public metric reads to the current immutable dataset lineage."""
    state = session.get(models.DatasetState, "current")
    provenance = state.provenance_json if state is not None else {}
    dataset_version = provenance.get("version")
    if not isinstance(dataset_version, str) or not dataset_version.strip():
        return (false(),)

    if state is not None and state.dataset_kind == "live-api":
        release = session.scalar(
            select(models.MetricSystemRelease)
            .where(models.MetricSystemRelease.status == "active")
            .order_by(models.MetricSystemRelease.activated_at.desc())
            .limit(1)
        )
        definition_states = {
            metric_id: (version, implementation_status)
            for metric_id, version, implementation_status in session.execute(
                select(
                    models.MetricDefinition.id,
                    models.MetricDefinition.version,
                    models.MetricDefinition.implementation_status,
                ).where(models.MetricDefinition.id.in_(METRIC_SYSTEM_V1_IDS))
            )
        }
        definitions_are_complete = definition_states == {
            metric_id: (version, "live-calculated")
            for metric_id, version in METRIC_SYSTEM_V1_DEFINITIONS.items()
        }
        release_is_complete = (
            release is not None
            and set(release.metric_ids) == METRIC_SYSTEM_V1_IDS
            and release.algorithm_versions == METRIC_SYSTEM_V1_ALGORITHMS
            and release.attribution_policy_version == FRACTIONAL_ATTRIBUTION_V1.version
            and release.ontology_version == PHYSICS_FIELD_ONTOLOGY_VERSION
            and release.mapping_policy_version == PROVIDER_FIELD_MAPPING_VERSION
            and release.threshold_version == METRIC_VALIDATION_THRESHOLDS_V1.version
            and release.validation_evidence.get("jointGatePassed") is True
            and field_validation_manifest_is_current(release.validation_evidence)
            and definitions_are_complete
        )
        if not release_is_complete:
            return (false(),)

    criteria: list[Any] = [
        models.MetricObservation.data_source_version == dataset_version,
    ]
    if state is not None and state.dataset_kind == "live-api":
        criteria.append(
            models.MetricDefinition.implementation_status == "live-calculated"
        )
    acquisition_scope = provenance.get("acquisitionScope")
    if isinstance(acquisition_scope, str) and acquisition_scope.strip():
        criteria.append(models.MetricObservation.acquisition_scope == acquisition_scope)
    return tuple(criteria)


def domain_out(item: models.ScienceDomain, field_ids: list[str]) -> dict[str, Any]:
    return {
        "id": item.id,
        "label": item.label,
        "description": item.description,
        "fieldIds": field_ids,
        "provenance": _provenance(item.provenance_json),
    }


def field_out(item: models.ResearchField) -> dict[str, Any]:
    return {
        "id": item.id,
        "label": item.label,
        "description": item.description,
        "parentFieldId": item.parent_field_id,
        "aliases": item.aliases,
        "ontologyVersion": item.ontology_version,
        "nodeKind": item.node_kind,
        "isExplorable": item.is_explorable,
        "displayOrder": item.display_order,
        "provenance": _provenance(item.provenance_json),
    }


def country_out(item: models.Country) -> dict[str, Any]:
    return {
        "id": item.id,
        "isoAlpha3": item.iso_alpha3,
        "isoNumeric": item.iso_numeric,
        "name": item.name,
        "region": item.region,
        "provenance": _provenance(item.provenance_json),
    }


def geographic_view_out(item: models.GeographicView) -> dict[str, Any]:
    return {
        "id": item.id,
        "countryId": item.country_id,
        "geometryIsoNumerics": item.geometry_iso_numerics,
        "locationCountryIds": item.location_country_ids,
        "provenance": _provenance(item.provenance_json),
    }


def institution_out(item: models.Institution) -> dict[str, Any]:
    location = None
    if item.longitude is not None and item.latitude is not None:
        location = {"longitude": item.longitude, "latitude": item.latitude}
    return {
        "id": item.id,
        "name": item.canonical_name,
        "canonicalName": item.canonical_name,
        "aliases": item.aliases,
        "historicalNames": item.historical_names,
        "externalIds": item.external_ids,
        "identityConfidence": item.identity_confidence,
        "countryId": item.country_id,
        "city": item.city,
        "fieldIds": item.field_ids,
        "location": location,
        "provenance": _provenance(item.provenance_json),
    }


def researcher_out(item: models.Researcher) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.canonical_name,
        "canonicalName": item.canonical_name,
        "aliases": item.aliases,
        "historicalNames": item.historical_names,
        "externalIds": item.external_ids,
        "identityConfidence": item.identity_confidence,
        "fieldIds": item.field_ids,
        "provenance": _provenance(item.provenance_json),
    }


def group_out(item: models.ResearchGroup) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "institutionId": item.institution_id,
        "description": item.description,
        "fieldIds": item.field_ids,
        "provenance": _provenance(item.provenance_json),
    }


def affiliation_out(item: models.Affiliation) -> dict[str, Any]:
    return {
        "id": item.id,
        "researcherId": item.researcher_id,
        "institutionId": item.institution_id,
        "researchGroupId": item.research_group_id,
        "startDate": item.start_date.isoformat() if item.start_date else None,
        "endDate": item.end_date.isoformat() if item.end_date else None,
        "source": item.source,
        "confidence": item.confidence,
        "provenance": _provenance(item.provenance_json),
    }


def authorship_out(item: models.Authorship) -> dict[str, Any]:
    return {
        "id": item.id,
        "paperId": item.paper_id,
        "researcherId": item.researcher_id,
        "authorPosition": item.author_position,
        "provenance": _provenance(item.provenance_json),
    }


def paper_out(item: models.Paper, field_ids: list[str]) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "summary": item.summary,
        "year": item.publication_year,
        "publicationDate": item.publication_date,
        "publicationDatePrecision": item.publication_date_precision,
        "documentType": item.document_type,
        "fieldIds": field_ids,
        "doi": item.doi,
        "arxivId": item.arxiv_id,
        "externalIdentifiers": item.external_ids,
        "provenance": _provenance(item.provenance_json),
    }


def metric_definition_out(item: models.MetricDefinition) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "description": item.description,
        "interpretation": item.interpretation,
        "unit": item.unit,
        "version": item.version,
        "requiredData": item.required_data,
        "implementationStatus": item.implementation_status,
        "provenance": _provenance(item.provenance_json),
    }


def metric_observation_out(item: models.MetricObservation) -> dict[str, Any]:
    return {
        "id": item.id,
        "entityType": item.entity_type,
        "entityId": item.entity_id,
        "scienceDomainId": item.science_domain_id,
        "fieldId": item.field_id,
        "metricId": item.metric_id,
        "period": item.period,
        "value": item.value,
        "source": item.source,
        "metricDefinitionVersion": item.metric_definition_version,
        "algorithmVersion": item.algorithm_version,
        "calculationVersion": item.calculation_version,
        "dataSourceVersion": item.data_source_version,
        "acquisitionScope": item.acquisition_scope,
        "rawValue": item.raw_value,
        "rawUnit": item.raw_unit,
        "normalizationMethod": item.normalization_method,
        "normalizationParameters": item.normalization_parameters,
        "inputCount": item.input_count,
        "qualityFlags": item.quality_flags,
        "calculatedAt": item.calculated_at,
        "provenance": _provenance(item.provenance_json),
    }


def resource_out(item: models.ExternalResource) -> dict[str, Any]:
    return {
        "id": item.id,
        "entityType": item.entity_type,
        "entityId": item.entity_id,
        "resourceType": item.resource_type,
        "label": item.label,
        "url": item.url,
        "source": item.source,
        "sourceRecordId": item.source_record_id,
        "externalId": item.external_id,
        "isPrimary": item.is_primary,
        "verified": item.verified,
        "verificationMethod": item.verification_method,
        "healthStatus": item.health_status,
        "lastCheckedAt": item.last_checked_at,
        "httpStatus": item.http_status,
        "redirectTarget": item.redirect_target,
        "provenance": _provenance(item.provenance_json),
    }


def historical_event_out(item: models.HistoricalEvent) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "summary": item.summary,
        "year": item.year,
        "fieldId": item.field_id,
        "relatedResearcherIds": item.related_researcher_ids,
        "relatedInstitutionIds": item.related_institution_ids,
        "provenance": _provenance(item.provenance_json),
    }


class AtlasDatabaseRepository:
    """Database-specific reads stay behind Atlas-shaped response projections."""

    def __init__(self, session: Session):
        self.session = session

    def metadata(self) -> dict[str, Any]:
        state = self.session.get(models.DatasetState, "current")
        if state is None:
            return {
                "schemaVersion": "3.0.5-alpha",
                "datasetKind": "live-api",
                "period": str(date.today().year),
                "generatedAt": models.utcnow(),
                "sourceSnapshotIds": [],
                "updateSequence": 0,
                "disclaimer": "No live records have been ingested into this instance.",
                "provenance": _provenance(None),
            }
        return {
            "schemaVersion": state.schema_version,
            "datasetKind": state.dataset_kind,
            "period": state.period,
            "generatedAt": state.generated_at,
            "latestUpdateAt": state.latest_update_at,
            "sourceSnapshotIds": state.source_snapshot_ids,
            "updateSequence": state.update_sequence,
            "disclaimer": state.disclaimer,
            "provenance": _provenance(state.provenance_json),
        }

    def domains(self) -> list[dict[str, Any]]:
        domains = self.session.scalars(
            select(models.ScienceDomain).order_by(models.ScienceDomain.id)
        ).all()
        fields = self.session.scalars(
            select(models.ResearchField).where(models.ResearchField.is_explorable)
        ).all()
        ids_by_domain: dict[str, list[str]] = {}
        for field in fields:
            ids_by_domain.setdefault(field.domain_id, []).append(field.id)
        return [
            domain_out(item, sorted(ids_by_domain.get(item.id, []))) for item in domains
        ]

    def fields(self, domain_id: str | None = None) -> list[dict[str, Any]]:
        statement = select(models.ResearchField).order_by(
            models.ResearchField.display_order, models.ResearchField.id
        )
        if domain_id:
            statement = statement.where(models.ResearchField.domain_id == domain_id)
        return [field_out(item) for item in self.session.scalars(statement)]

    def countries(self) -> list[dict[str, Any]]:
        return [
            country_out(item)
            for item in self.session.scalars(
                select(models.Country).order_by(models.Country.name)
            )
        ]

    def country(self, entity_id: str) -> dict[str, Any] | None:
        item = self.session.get(models.Country, entity_id)
        return country_out(item) if item else None

    def geographic_views(self) -> list[dict[str, Any]]:
        return [
            geographic_view_out(item)
            for item in self.session.scalars(
                select(models.GeographicView).order_by(models.GeographicView.id)
            )
        ]

    def institutions(
        self, country_id: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        statement = select(models.Institution).order_by(
            models.Institution.canonical_name
        )
        if country_id:
            statement = statement.where(models.Institution.country_id == country_id)
        items, total = _page(self.session, statement, limit, offset)
        return [institution_out(item) for item in items], total

    def institution(self, entity_id: str) -> dict[str, Any] | None:
        item = self.session.get(models.Institution, entity_id)
        return institution_out(item) if item else None

    def institution_map_nodes(
        self,
        *,
        country_id: str,
        science_domain_id: str,
        field_id: str | None,
        metric_id: str,
        period: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return only the highest-activity nodes needed by one country map."""
        current_observation_ids = _current_metric_observation_ids(
            *_current_dataset_metric_criteria(self.session),
            models.MetricObservation.entity_type == "institution",
            models.MetricObservation.science_domain_id == science_domain_id,
            models.MetricObservation.metric_id == metric_id,
            models.MetricObservation.period == period,
            (
                models.MetricObservation.field_id == field_id
                if field_id is not None
                else models.MetricObservation.field_id.is_(None)
            ),
        )
        statement = (
            select(models.Institution, models.MetricObservation)
            .join(
                models.MetricObservation,
                models.MetricObservation.entity_id == models.Institution.id,
            )
            .where(
                models.Institution.country_id == country_id,
                models.Institution.longitude.is_not(None),
                models.Institution.latitude.is_not(None),
                models.MetricObservation.id.in_(current_observation_ids),
            )
            .order_by(
                models.MetricObservation.value.desc(),
                models.Institution.canonical_name,
            )
            .limit(limit)
        )
        return [
            {
                "institution": institution_out(institution),
                "observation": metric_observation_out(observation),
            }
            for institution, observation in self.session.execute(statement).all()
        ]

    def groups(
        self, institution_id: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        statement = select(models.ResearchGroup).order_by(models.ResearchGroup.name)
        if institution_id:
            statement = statement.where(
                models.ResearchGroup.institution_id == institution_id
            )
        items, total = _page(self.session, statement, limit, offset)
        return [group_out(item) for item in items], total

    def researchers(
        self, institution_id: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        statement = select(models.Researcher).order_by(models.Researcher.canonical_name)
        if institution_id:
            statement = (
                statement.join(
                    models.Affiliation,
                    models.Affiliation.researcher_id == models.Researcher.id,
                )
                .where(models.Affiliation.institution_id == institution_id)
                .distinct()
            )
        items, total = _page(self.session, statement, limit, offset)
        return [researcher_out(item) for item in items], total

    def researcher(self, entity_id: str) -> dict[str, Any] | None:
        item = self.session.get(models.Researcher, entity_id)
        return researcher_out(item) if item else None

    def affiliations(
        self, institution_id: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        statement = select(models.Affiliation).order_by(models.Affiliation.id)
        if institution_id:
            statement = statement.where(
                models.Affiliation.institution_id == institution_id
            )
        items, total = _page(self.session, statement, limit, offset)
        return [affiliation_out(item) for item in items], total

    def authorships(
        self,
        researcher_id: str | None,
        paper_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        statement = select(models.Authorship).order_by(
            models.Authorship.paper_id, models.Authorship.author_position
        )
        if researcher_id:
            statement = statement.where(
                models.Authorship.researcher_id == researcher_id
            )
        if paper_id:
            statement = statement.where(models.Authorship.paper_id == paper_id)
        items, total = _page(self.session, statement, limit, offset)
        return [authorship_out(item) for item in items], total

    def _field_ids_for_papers(self, paper_ids: list[str]) -> dict[str, list[str]]:
        if not paper_ids:
            return {}
        links = self.session.execute(
            select(models.PaperField.paper_id, models.PaperField.field_id).where(
                models.PaperField.paper_id.in_(paper_ids)
            )
        ).all()
        result: dict[str, list[str]] = {}
        for paper_id, field_id in links:
            result.setdefault(paper_id, []).append(field_id)
        return result

    def papers(
        self, researcher_id: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        statement = select(models.Paper).order_by(
            models.Paper.publication_year.desc(), models.Paper.id
        )
        if researcher_id:
            statement = (
                statement.join(models.Authorship)
                .where(models.Authorship.researcher_id == researcher_id)
                .distinct()
            )
        items, total = _page(self.session, statement, limit, offset)
        fields = self._field_ids_for_papers([item.id for item in items])
        return [paper_out(item, fields.get(item.id, [])) for item in items], total

    def paper(self, entity_id: str) -> dict[str, Any] | None:
        item = self.session.get(models.Paper, entity_id)
        if item is None:
            return None
        fields = self._field_ids_for_papers([item.id])
        return paper_out(item, fields.get(item.id, []))

    def historical_events(self, field_id: str | None) -> list[dict[str, Any]]:
        statement = select(models.HistoricalEvent).order_by(models.HistoricalEvent.year)
        if field_id:
            statement = statement.where(models.HistoricalEvent.field_id == field_id)
        return [historical_event_out(item) for item in self.session.scalars(statement)]

    def metric_definitions(self) -> list[dict[str, Any]]:
        return [
            metric_definition_out(item)
            for item in self.session.scalars(
                select(models.MetricDefinition).order_by(models.MetricDefinition.id)
            )
        ]

    def metric_definition(self, entity_id: str) -> dict[str, Any] | None:
        item = self.session.get(models.MetricDefinition, entity_id)
        return metric_definition_out(item) if item else None

    def metric_observations(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        science_domain_id: str | None = None,
        field_id: str | None = None,
        metric_id: str | None = None,
        period: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        criteria: list[Any] = []
        filters = {
            models.MetricObservation.entity_type: entity_type,
            models.MetricObservation.entity_id: entity_id,
            models.MetricObservation.science_domain_id: science_domain_id,
            models.MetricObservation.field_id: field_id,
            models.MetricObservation.metric_id: metric_id,
            models.MetricObservation.period: period,
        }
        for column, value in filters.items():
            if value is not None:
                criteria.append(column == value)
        criteria.extend(_current_dataset_metric_criteria(self.session))
        statement = (
            select(models.MetricObservation)
            .where(
                models.MetricObservation.id.in_(
                    _current_metric_observation_ids(*criteria)
                )
            )
            .order_by(models.MetricObservation.period, models.MetricObservation.id)
        )
        items, total = _page(self.session, statement, limit, offset)
        return [metric_observation_out(item) for item in items], total

    def resources(
        self,
        entity_type: str | None,
        entity_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        statement = select(models.ExternalResource).order_by(*_resource_ordering())
        if entity_type:
            statement = statement.where(
                models.ExternalResource.entity_type == entity_type
            )
        if entity_id:
            statement = statement.where(models.ExternalResource.entity_id == entity_id)
        items, total = _page(self.session, statement, limit, offset)
        return [resource_out(item) for item in items], total

    def snapshots(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        items, total = _page(
            self.session,
            select(models.SourceSnapshot).order_by(
                models.SourceSnapshot.captured_at.desc()
            ),
            limit,
            offset,
        )
        return [
            {
                "id": item.id,
                "source": item.source,
                "sourceVersion": item.source_version,
                "capturedAt": item.captured_at,
                "updateMode": item.update_mode,
                "recordCount": item.record_count,
                "previousSnapshotId": item.previous_snapshot_id,
                "contentChecksum": item.content_checksum,
                "storageReference": item.storage_reference,
                "provenance": _provenance(item.provenance_json),
            }
            for item in items
        ], total

    def updates(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        items, total = _page(
            self.session,
            select(models.DatasetUpdate).order_by(
                models.DatasetUpdate.applied_at.desc()
            ),
            limit,
            offset,
        )
        return [
            {
                "id": item.id,
                "appliedAt": item.applied_at,
                "updateMode": item.update_mode,
                "sourceSnapshotIds": item.source_snapshot_ids,
                "previousDatasetVersion": item.previous_dataset_version,
                "datasetVersion": item.dataset_version,
                "resolverVersion": item.resolver_version,
                "metricCalculationVersion": item.metric_calculation_version,
                "changes": item.changes,
                "affectedEntities": item.affected_entities,
                "provenance": _provenance(item.provenance_json),
            }
            for item in items
        ], total

    def raw_records(
        self, entity_type: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        statement = select(models.RawEntityRecord).order_by(models.RawEntityRecord.id)
        if entity_type:
            statement = statement.where(
                models.RawEntityRecord.entity_type == entity_type
            )
        items, total = _page(self.session, statement, limit, offset)
        return [
            {
                "id": item.id,
                "entityType": item.entity_type,
                "sourceRecordId": item.source_record_id,
                "sourceSnapshotId": item.source_snapshot_id,
                "rawName": item.raw_name,
                "externalIds": item.external_ids,
                "attributes": item.attributes_json,
                "ingestedAt": item.ingested_at,
                "provenance": _provenance(item.provenance_json),
            }
            for item in items
        ], total

    def identity_resolutions(
        self, status: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        statement = select(models.IdentityResolution).order_by(
            models.IdentityResolution.id
        )
        if status:
            statement = statement.where(models.IdentityResolution.status == status)
        items, total = _page(self.session, statement, limit, offset)
        return [
            {
                "id": item.id,
                "rawEntityRecordId": item.raw_entity_record_id,
                "entityType": item.entity_type,
                "status": item.status,
                "canonicalEntityId": item.canonical_entity_id,
                "method": item.method,
                "confidence": item.confidence,
                "evidence": item.evidence,
                "resolverVersion": item.resolver_version,
                "resolvedAt": item.resolved_at,
                "provenance": _provenance(item.provenance_json),
            }
            for item in items
        ], total

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        normalized = normalize_search_term(query)
        if not normalized:
            return []
        prefix = f"{normalized}%"
        results: dict[tuple[str, str], dict[str, Any]] = {}

        for term in self.session.scalars(
            select(models.EntitySearchTerm)
            .where(models.EntitySearchTerm.normalized_term.like(prefix))
            .order_by(models.EntitySearchTerm.normalized_term)
            .limit(limit * 4)
        ):
            if term.entity_type == "institution":
                institution = self.session.get(models.Institution, term.entity_id)
                if institution is None:
                    continue
                label = institution.canonical_name
                context = f"Institution · {institution.city}"
                identity_confidence = institution.identity_confidence
            elif term.entity_type == "researcher":
                researcher = self.session.get(models.Researcher, term.entity_id)
                if researcher is None:
                    continue
                label = researcher.canonical_name
                context = "Researcher"
                identity_confidence = researcher.identity_confidence
            elif term.entity_type == "paper":
                paper = self.session.get(models.Paper, term.entity_id)
                if paper is None:
                    continue
                label = paper.title
                context = f"Paper · {paper.publication_year}"
                identity_confidence = None
            else:
                continue
            score = 1.0 if term.normalized_term == normalized else 0.96
            key = (term.entity_type, term.entity_id)
            candidate = {
                "entityId": term.entity_id,
                "entityType": term.entity_type,
                "label": label,
                "context": context,
                "matchConfidence": score,
                "matchedOn": term.match_method,
                "matchedValue": term.term,
                "identityConfidence": identity_confidence,
            }
            if key not in results or score > results[key]["matchConfidence"]:
                results[key] = candidate

        def add_simple(
            entity_type: str, entity_id: str, label: str, context: str
        ) -> None:
            results.setdefault(
                (entity_type, entity_id),
                {
                    "entityId": entity_id,
                    "entityType": entity_type,
                    "label": label,
                    "context": context,
                    "matchConfidence": (1.0 if label.casefold() == normalized else 0.9),
                    "matchedOn": "canonical-name",
                    "matchedValue": label,
                },
            )

        for group in self.session.scalars(
            select(models.ResearchGroup)
            .where(func.lower(models.ResearchGroup.name).like(prefix))
            .limit(limit)
        ):
            add_simple("research-group", group.id, group.name, "Research group")
        for domain in self.session.scalars(
            select(models.ScienceDomain)
            .where(func.lower(models.ScienceDomain.label).like(prefix))
            .limit(limit)
        ):
            add_simple("science-domain", domain.id, domain.label, "Science domain")
        for field in self.session.scalars(
            select(models.ResearchField)
            .where(func.lower(models.ResearchField.label).like(prefix))
            .limit(limit)
        ):
            add_simple("research-field", field.id, field.label, "Research field")

        for country in self.session.scalars(
            select(models.Country)
            .where(
                or_(
                    func.lower(models.Country.name).like(prefix),
                    func.lower(models.Country.iso_alpha3) == normalized,
                )
            )
            .limit(limit)
        ):
            abbreviation = country.iso_alpha3.casefold() == normalized
            results.setdefault(
                ("country", country.id),
                {
                    "entityId": country.id,
                    "entityType": "country",
                    "label": country.name,
                    "context": f"Country · {country.region}",
                    "matchConfidence": 1.0 if abbreviation else 0.9,
                    "matchedOn": "abbreviation" if abbreviation else "canonical-name",
                    "matchedValue": country.iso_alpha3
                    if abbreviation
                    else country.name,
                },
            )

        return sorted(
            results.values(),
            key=lambda item: (-item["matchConfidence"], item["label"]),
        )[:limit]

    def institution_profile(self, entity_id: str) -> dict[str, Any] | None:
        institution = self.session.get(models.Institution, entity_id)
        if not institution:
            return None
        groups = list(
            self.session.scalars(
                select(models.ResearchGroup)
                .where(models.ResearchGroup.institution_id == entity_id)
                .order_by(models.ResearchGroup.name)
                .limit(PROFILE_ENTITY_LIMIT)
            )
        )
        affiliations = list(
            self.session.scalars(
                select(models.Affiliation)
                .where(models.Affiliation.institution_id == entity_id)
                .order_by(models.Affiliation.start_date.desc(), models.Affiliation.id)
                .limit(PROFILE_AFFILIATION_LIMIT)
            )
        )
        researcher_ids = {item.researcher_id for item in affiliations}
        researchers = (
            list(
                self.session.scalars(
                    select(models.Researcher).where(
                        models.Researcher.id.in_(researcher_ids)
                    )
                )
            )
            if researcher_ids
            else []
        )
        papers = (
            list(
                self.session.scalars(
                    select(models.Paper)
                    .join(models.Authorship)
                    .where(models.Authorship.researcher_id.in_(researcher_ids))
                    .distinct()
                    .order_by(models.Paper.publication_year.desc(), models.Paper.id)
                    .limit(PROFILE_PAPER_LIMIT)
                )
            )
            if researcher_ids
            else []
        )
        fields = self._field_ids_for_papers([item.id for item in papers])
        resources = list(
            self.session.scalars(
                select(models.ExternalResource)
                .where(
                    models.ExternalResource.entity_type == "institution",
                    models.ExternalResource.entity_id == entity_id,
                )
                .order_by(*_resource_ordering())
                .limit(PROFILE_RESOURCE_LIMIT)
            )
        )
        institution_metric_criteria = (
            *_current_dataset_metric_criteria(self.session),
            models.MetricObservation.entity_type == "institution",
            models.MetricObservation.entity_id == entity_id,
        )
        metrics = list(
            self.session.scalars(
                select(models.MetricObservation)
                .where(
                    models.MetricObservation.id.in_(
                        _current_metric_observation_ids(*institution_metric_criteria)
                    )
                )
                .order_by(
                    models.MetricObservation.period.desc(),
                    models.MetricObservation.id,
                )
                .limit(PROFILE_METRIC_LIMIT)
            )
        )
        return {
            "institution": institution_out(institution),
            "resources": [resource_out(item) for item in resources],
            "researchGroups": [group_out(item) for item in groups],
            "affiliations": [affiliation_out(item) for item in affiliations],
            "researchers": [researcher_out(item) for item in researchers],
            "papers": [paper_out(item, fields.get(item.id, [])) for item in papers],
            "metrics": [metric_observation_out(item) for item in metrics],
        }

    def researcher_profile(self, entity_id: str) -> dict[str, Any] | None:
        researcher = self.session.get(models.Researcher, entity_id)
        if not researcher:
            return None
        affiliations = list(
            self.session.scalars(
                select(models.Affiliation)
                .where(models.Affiliation.researcher_id == entity_id)
                .order_by(models.Affiliation.start_date.desc(), models.Affiliation.id)
                .limit(PROFILE_AFFILIATION_LIMIT)
            )
        )
        institution_ids = {item.institution_id for item in affiliations}
        institutions = (
            {
                item.id: item
                for item in self.session.scalars(
                    select(models.Institution).where(
                        models.Institution.id.in_(institution_ids)
                    )
                )
            }
            if institution_ids
            else {}
        )
        group_ids = {
            item.research_group_id for item in affiliations if item.research_group_id
        }
        groups = (
            {
                item.id: item
                for item in self.session.scalars(
                    select(models.ResearchGroup).where(
                        models.ResearchGroup.id.in_(group_ids)
                    )
                )
            }
            if group_ids
            else {}
        )
        field_rows = list(
            self.session.scalars(
                select(models.ResearchField).where(
                    models.ResearchField.id.in_(researcher.field_ids)
                )
            )
        )
        papers_data, _ = self.papers(entity_id, 200, 0)
        paper_ids = {item["id"] for item in papers_data}
        collaborator_ids = (
            set(
                self.session.scalars(
                    select(models.Authorship.researcher_id).where(
                        models.Authorship.paper_id.in_(paper_ids),
                        models.Authorship.researcher_id != entity_id,
                    )
                )
            )
            if paper_ids
            else set()
        )
        collaborators = (
            list(
                self.session.scalars(
                    select(models.Researcher)
                    .where(models.Researcher.id.in_(collaborator_ids))
                    .order_by(models.Researcher.canonical_name)
                    .limit(PROFILE_ENTITY_LIMIT)
                )
            )
            if collaborator_ids
            else []
        )
        resources = list(
            self.session.scalars(
                select(models.ExternalResource)
                .where(
                    models.ExternalResource.entity_type == "researcher",
                    models.ExternalResource.entity_id == entity_id,
                )
                .order_by(*_resource_ordering())
                .limit(PROFILE_RESOURCE_LIMIT)
            )
        )
        researcher_metric_criteria = (
            *_current_dataset_metric_criteria(self.session),
            models.MetricObservation.entity_type == "researcher",
            models.MetricObservation.entity_id == entity_id,
        )
        metrics = list(
            self.session.scalars(
                select(models.MetricObservation)
                .where(
                    models.MetricObservation.id.in_(
                        _current_metric_observation_ids(*researcher_metric_criteria)
                    )
                )
                .order_by(
                    models.MetricObservation.period.desc(),
                    models.MetricObservation.id,
                )
                .limit(PROFILE_METRIC_LIMIT)
            )
        )
        return {
            "researcher": researcher_out(researcher),
            "resources": [resource_out(item) for item in resources],
            "fields": [field_out(item) for item in field_rows],
            "affiliationHistory": [
                {
                    "affiliation": affiliation_out(item),
                    "institution": institution_out(institutions[item.institution_id]),
                    "researchGroup": group_out(groups[item.research_group_id])
                    if item.research_group_id in groups
                    else None,
                }
                for item in affiliations
                if item.institution_id in institutions
            ],
            "papers": papers_data,
            "collaborators": [researcher_out(item) for item in collaborators],
            "metrics": [metric_observation_out(item) for item in metrics],
        }

    def group_profile(self, entity_id: str) -> dict[str, Any] | None:
        group = self.session.get(models.ResearchGroup, entity_id)
        if not group:
            return None
        institution = self.session.get(models.Institution, group.institution_id)
        if not institution:
            return None
        affiliations = list(
            self.session.scalars(
                select(models.Affiliation)
                .where(models.Affiliation.research_group_id == entity_id)
                .order_by(models.Affiliation.start_date.desc(), models.Affiliation.id)
                .limit(PROFILE_AFFILIATION_LIMIT)
            )
        )
        member_ids = {item.researcher_id for item in affiliations}
        members = (
            list(
                self.session.scalars(
                    select(models.Researcher).where(
                        models.Researcher.id.in_(member_ids)
                    )
                )
            )
            if member_ids
            else []
        )
        fields = list(
            self.session.scalars(
                select(models.ResearchField).where(
                    models.ResearchField.id.in_(group.field_ids)
                )
            )
        )
        papers = (
            list(
                self.session.scalars(
                    select(models.Paper)
                    .join(models.Authorship)
                    .where(models.Authorship.researcher_id.in_(member_ids))
                    .distinct()
                    .order_by(models.Paper.publication_year.desc(), models.Paper.id)
                    .limit(PROFILE_PAPER_LIMIT)
                )
            )
            if member_ids
            else []
        )
        paper_fields = self._field_ids_for_papers([item.id for item in papers])
        resources = list(
            self.session.scalars(
                select(models.ExternalResource)
                .where(
                    models.ExternalResource.entity_type == "research-group",
                    models.ExternalResource.entity_id == entity_id,
                )
                .order_by(*_resource_ordering())
                .limit(PROFILE_RESOURCE_LIMIT)
            )
        )
        return {
            "researchGroup": group_out(group),
            "institution": institution_out(institution),
            "resources": [resource_out(item) for item in resources],
            "fields": [field_out(item) for item in fields],
            "affiliations": [affiliation_out(item) for item in affiliations],
            "members": [researcher_out(item) for item in members],
            "papers": [
                paper_out(item, paper_fields.get(item.id, [])) for item in papers
            ],
        }

    def provenance(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        table_map: dict[str, Any] = {
            "institution": models.Institution,
            "researcher": models.Researcher,
            "paper": models.Paper,
            "research-group": models.ResearchGroup,
            "metric-observation": models.MetricObservation,
        }
        model = table_map.get(entity_type)
        if model is None:
            return None
        entity = self.session.get(model, entity_id)
        if entity is None:
            return None
        resolutions = list(
            self.session.scalars(
                select(models.IdentityResolution)
                .where(models.IdentityResolution.canonical_entity_id == entity_id)
                .order_by(models.IdentityResolution.resolved_at.desc())
                .limit(100)
            )
        )
        raw_record_ids = [item.raw_entity_record_id for item in resolutions]
        raw_records = (
            list(
                self.session.scalars(
                    select(models.RawEntityRecord)
                    .where(models.RawEntityRecord.id.in_(raw_record_ids))
                    .order_by(models.RawEntityRecord.ingested_at.desc())
                )
            )
            if raw_record_ids
            else []
        )
        resolution = resolutions[0] if resolutions else None
        return {
            "entityType": entity_type,
            "entityId": entity_id,
            "provenance": _provenance(entity.provenance_json),
            "sourceRecords": [
                {
                    "id": item.id,
                    "source": item.source,
                    "sourceRecordId": item.source_record_id,
                    "sourceSnapshotId": item.source_snapshot_id,
                }
                for item in raw_records
            ],
            "resolution": (
                {
                    "id": resolution.id,
                    "status": resolution.status,
                    "method": resolution.method,
                    "confidence": resolution.confidence,
                }
                if resolution
                else None
            ),
        }
