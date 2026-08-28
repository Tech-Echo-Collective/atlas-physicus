from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import __version__, models, schemas
from .config import Settings, get_settings
from .database import get_session
from .repository import AtlasDatabaseRepository

SessionDependency = Annotated[Session, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def repository(session: SessionDependency) -> AtlasDatabaseRepository:
    return AtlasDatabaseRepository(session)


RepositoryDependency = Annotated[AtlasDatabaseRepository, Depends(repository)]

router = APIRouter()


def not_found(entity_type: str, entity_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "entity_not_found",
            "message": f"{entity_type} was not found",
            "context": {"entityType": entity_type, "entityId": entity_id},
        },
    )


def page(
    items: list[dict[str, Any]], total: int, limit: int, offset: int
) -> dict[str, Any]:
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/health", response_model=schemas.HealthOut)
def health(response: Response, session: SessionDependency) -> dict[str, Any]:
    database_status = "ok"
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database_status = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "version": __version__,
        "database": database_status,
        "timestamp": datetime.now(UTC),
    }


@router.get("/dataset", response_model=schemas.DatasetMetadataOut)
def dataset_metadata(repo: RepositoryDependency) -> dict[str, Any]:
    return repo.metadata()


@router.get("/domains", response_model=list[schemas.ScienceDomainOut])
def domains(repo: RepositoryDependency) -> list[dict[str, Any]]:
    return repo.domains()


@router.get("/fields", response_model=list[schemas.ResearchFieldOut])
def fields(
    repo: RepositoryDependency, domain_id: str | None = Query(default=None)
) -> list[dict[str, Any]]:
    return repo.fields(domain_id)


@router.get("/countries", response_model=list[schemas.CountryOut])
def countries(repo: RepositoryDependency) -> list[dict[str, Any]]:
    return repo.countries()


@router.get("/countries/{entity_id}", response_model=schemas.CountryOut)
def country(entity_id: str, repo: RepositoryDependency) -> dict[str, Any]:
    result = repo.country(entity_id)
    if result is None:
        raise not_found("country", entity_id)
    return result


@router.get("/geographic-views", response_model=list[schemas.GeographicViewOut])
def geographic_views(repo: RepositoryDependency) -> list[dict[str, Any]]:
    return repo.geographic_views()


@router.get("/institutions", response_model=schemas.Page[schemas.InstitutionOut])
def institutions(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    country_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    bounded_limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = repo.institutions(country_id, bounded_limit, offset)
    return page(items, total, bounded_limit, offset)


@router.get("/institutions/{entity_id}", response_model=schemas.InstitutionOut)
def institution(entity_id: str, repo: RepositoryDependency) -> dict[str, Any]:
    result = repo.institution(entity_id)
    if result is None:
        raise not_found("institution", entity_id)
    return result


@router.get("/map/institutions", response_model=list[schemas.InstitutionMapNodeOut])
def institution_map_nodes(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    country_id: str = Query(min_length=1, max_length=160),
    science_domain_id: str = Query(min_length=1, max_length=120),
    field_id: str | None = Query(default=None, min_length=1, max_length=120),
    metric_id: str = Query(min_length=1, max_length=160),
    period: str = Query(pattern=r"^\d{4}$"),
    limit: int = Query(default=50, ge=1),
) -> list[dict[str, Any]]:
    bounded_limit = min(limit, settings.max_page_size)
    return repo.institution_map_nodes(
        country_id=country_id,
        science_domain_id=science_domain_id,
        field_id=field_id,
        metric_id=metric_id,
        period=period,
        limit=bounded_limit,
    )


@router.get("/groups", response_model=schemas.Page[schemas.ResearchGroupOut])
def groups(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    institution_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    bounded_limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = repo.groups(institution_id, bounded_limit, offset)
    return page(items, total, bounded_limit, offset)


@router.get("/researchers", response_model=schemas.Page[schemas.ResearcherOut])
def researchers(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    institution_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    bounded_limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = repo.researchers(institution_id, bounded_limit, offset)
    return page(items, total, bounded_limit, offset)


@router.get("/researchers/{entity_id}", response_model=schemas.ResearcherOut)
def researcher(entity_id: str, repo: RepositoryDependency) -> dict[str, Any]:
    result = repo.researcher(entity_id)
    if result is None:
        raise not_found("researcher", entity_id)
    return result


@router.get("/affiliations", response_model=schemas.Page[schemas.AffiliationOut])
def affiliations(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    institution_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    bounded_limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = repo.affiliations(institution_id, bounded_limit, offset)
    return page(items, total, bounded_limit, offset)


@router.get("/authorships", response_model=schemas.Page[schemas.AuthorshipOut])
def authorships(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    researcher_id: str | None = Query(default=None),
    paper_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    bounded_limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = repo.authorships(researcher_id, paper_id, bounded_limit, offset)
    return page(items, total, bounded_limit, offset)


@router.get("/papers", response_model=schemas.Page[schemas.PaperOut])
def papers(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    researcher_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    bounded_limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = repo.papers(researcher_id, bounded_limit, offset)
    return page(items, total, bounded_limit, offset)


@router.get("/papers/{entity_id}", response_model=schemas.PaperOut)
def paper(entity_id: str, repo: RepositoryDependency) -> dict[str, Any]:
    result = repo.paper(entity_id)
    if result is None:
        raise not_found("paper", entity_id)
    return result


@router.get("/historical-events", response_model=list[schemas.HistoricalEventOut])
def historical_events(
    repo: RepositoryDependency, field_id: str | None = Query(default=None)
) -> list[dict[str, Any]]:
    return repo.historical_events(field_id)


@router.get("/metrics", response_model=list[schemas.MetricDefinitionOut])
def metric_definitions(repo: RepositoryDependency) -> list[dict[str, Any]]:
    return repo.metric_definitions()


@router.get("/metrics/{entity_id}", response_model=schemas.MetricDefinitionOut)
def metric_definition(entity_id: str, repo: RepositoryDependency) -> dict[str, Any]:
    result = repo.metric_definition(entity_id)
    if result is None:
        raise not_found("metric definition", entity_id)
    return result


@router.get(
    "/metric-observations", response_model=schemas.Page[schemas.MetricObservationOut]
)
def metric_observations(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    science_domain_id: str | None = Query(default=None),
    field_id: str | None = Query(default=None),
    metric_id: str | None = Query(default=None),
    period: str | None = Query(default=None, pattern=r"^\d{4}$"),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    bounded_limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = repo.metric_observations(
        entity_type=entity_type,
        entity_id=entity_id,
        science_domain_id=science_domain_id,
        field_id=field_id,
        metric_id=metric_id,
        period=period,
        limit=bounded_limit,
        offset=offset,
    )
    return page(items, total, bounded_limit, offset)


@router.get("/search", response_model=list[schemas.SearchResultOut])
def search(
    repo: RepositoryDependency,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=8, ge=1, le=50),
) -> list[dict[str, Any]]:
    return repo.search(q, limit)


@router.get(
    "/profiles/institutions/{entity_id}",
    response_model=schemas.InstitutionProfileOut,
)
def institution_profile(entity_id: str, repo: RepositoryDependency) -> dict[str, Any]:
    result = repo.institution_profile(entity_id)
    if result is None:
        raise not_found("institution", entity_id)
    return result


@router.get(
    "/profiles/researchers/{entity_id}", response_model=schemas.ResearcherProfileOut
)
def researcher_profile(entity_id: str, repo: RepositoryDependency) -> dict[str, Any]:
    result = repo.researcher_profile(entity_id)
    if result is None:
        raise not_found("researcher", entity_id)
    return result


@router.get(
    "/profiles/groups/{entity_id}", response_model=schemas.ResearchGroupProfileOut
)
def group_profile(entity_id: str, repo: RepositoryDependency) -> dict[str, Any]:
    result = repo.group_profile(entity_id)
    if result is None:
        raise not_found("research group", entity_id)
    return result


@router.get(
    "/external-resources", response_model=schemas.Page[schemas.ExternalResourceOut]
)
def external_resources(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    bounded_limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = repo.resources(entity_type, entity_id, bounded_limit, offset)
    return page(items, total, bounded_limit, offset)


@router.get("/source-snapshots", response_model=schemas.Page[schemas.SourceSnapshotOut])
def source_snapshots(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    bounded_limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = repo.snapshots(bounded_limit, offset)
    return page(items, total, bounded_limit, offset)


@router.get("/dataset-updates", response_model=schemas.Page[schemas.DatasetUpdateOut])
def dataset_updates(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    bounded_limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = repo.updates(bounded_limit, offset)
    return page(items, total, bounded_limit, offset)


@router.get(
    "/raw-entity-records", response_model=schemas.Page[schemas.RawEntityRecordOut]
)
def raw_entity_records(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    entity_type: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    bounded_limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = repo.raw_records(entity_type, bounded_limit, offset)
    return page(items, total, bounded_limit, offset)


@router.get(
    "/identity-resolutions",
    response_model=schemas.Page[schemas.IdentityResolutionOut],
)
def identity_resolutions(
    repo: RepositoryDependency,
    settings: SettingsDependency,
    resolution_status: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    bounded_limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = repo.identity_resolutions(resolution_status, bounded_limit, offset)
    return page(items, total, bounded_limit, offset)


@router.get(
    "/provenance/{entity_type}/{entity_id}", response_model=schemas.ProvenanceOut
)
def provenance(
    entity_type: str, entity_id: str, repo: RepositoryDependency
) -> dict[str, Any]:
    result = repo.provenance(entity_type, entity_id)
    if result is None:
        raise not_found(entity_type, entity_id)
    return result


@router.get("/updates/status", response_model=schemas.UpdateStatusOut)
def update_status(session: SessionDependency) -> dict[str, Any]:
    source_rows = list(
        session.scalars(
            select(models.SourceCursor).order_by(models.SourceCursor.source)
        )
    )
    last_success = session.scalar(
        select(func.max(models.UpdateRun.finished_at)).where(
            models.UpdateRun.status == "succeeded"
        )
    )
    last_failure = session.scalar(
        select(func.max(models.UpdateRun.finished_at)).where(
            models.UpdateRun.status == "failed"
        )
    )
    unresolved_count = (
        session.scalar(
            select(func.count())
            .select_from(models.IdentityReview)
            .where(models.IdentityReview.status == "needs_review")
        )
        or 0
    )
    resource_failures = (
        session.scalar(
            select(func.count())
            .select_from(models.ExternalResource)
            .where(models.ExternalResource.health_status.in_(["broken", "timeout"]))
        )
        or 0
    )
    latest_run = session.scalar(
        select(models.UpdateRun).order_by(models.UpdateRun.started_at.desc()).limit(1)
    )
    return {
        "lastSuccessfulUpdate": last_success,
        "lastFailedUpdate": last_failure,
        "unresolvedEntityCount": unresolved_count,
        "resourceCheckFailures": resource_failures,
        "metricRecalculationStatus": (
            "idle"
            if latest_run is None or latest_run.status in {"succeeded", "failed"}
            else "running"
        ),
        "sources": [
            {
                "source": item.source,
                "status": "degraded" if item.consecutive_failures else "healthy",
                "lastAttemptAt": item.last_attempt_at,
                "lastSuccessAt": item.last_success_at,
                "cursor": item.cursor,
                "scopeVersion": item.scope_version,
                "consecutiveFailures": item.consecutive_failures,
            }
            for item in source_rows
        ],
    }


@router.get("/knowledge-graph", response_model=schemas.KnowledgeGraphOut)
def knowledge_graph(
    session: SessionDependency,
    node_limit: int = Query(default=500, ge=1, le=1000),
    edge_limit: int = Query(default=1000, ge=1, le=5000),
) -> dict[str, Any]:
    """Return a bounded graph projection; prefer scoped routes at scale."""
    institution_total = (
        session.scalar(select(func.count()).select_from(models.Institution)) or 0
    )
    researcher_total = (
        session.scalar(select(func.count()).select_from(models.Researcher)) or 0
    )

    # Reserve half of the bounded projection for each node type, then give any
    # unused capacity to the other type. This prevents a large institution table
    # from starving every researcher (and therefore every relationship).
    institution_budget = min(institution_total, (node_limit + 1) // 2)
    researcher_budget = min(researcher_total, node_limit // 2)
    remaining = node_limit - institution_budget - researcher_budget
    institution_extra = min(remaining, institution_total - institution_budget)
    institution_budget += institution_extra
    remaining -= institution_extra
    researcher_budget += min(remaining, researcher_total - researcher_budget)

    institutions = list(
        session.scalars(
            select(models.Institution)
            .order_by(models.Institution.id)
            .limit(institution_budget)
        )
    )
    researchers = list(
        session.scalars(
            select(models.Researcher)
            .order_by(models.Researcher.id)
            .limit(researcher_budget)
        )
    )
    institution_ids = {item.id for item in institutions}
    researcher_ids = {item.id for item in researchers}
    affiliation_rows = (
        list(
            session.scalars(
                select(models.Affiliation)
                .where(
                    models.Affiliation.institution_id.in_(institution_ids),
                    models.Affiliation.researcher_id.in_(researcher_ids),
                )
                .order_by(models.Affiliation.id)
                .limit(edge_limit + 1)
            )
        )
        if institution_ids and researcher_ids
        else []
    )
    edge_truncated = len(affiliation_rows) > edge_limit
    affiliations = affiliation_rows[:edge_limit]
    node_truncated = institution_total + researcher_total > len(institutions) + len(
        researchers
    )
    return {
        "nodes": [
            {"id": item.id, "entityType": "institution", "label": item.canonical_name}
            for item in institutions
        ]
        + [
            {"id": item.id, "entityType": "researcher", "label": item.canonical_name}
            for item in researchers
        ],
        "edges": [
            {
                "id": item.id,
                "relationshipType": "affiliated-with",
                "sourceId": item.researcher_id,
                "targetId": item.institution_id,
                "provenance": item.provenance_json,
            }
            for item in affiliations
        ],
        "nodeCount": len(institutions) + len(researchers),
        "edgeCount": len(affiliations),
        "nodeLimit": node_limit,
        "edgeLimit": edge_limit,
        "truncated": node_truncated or edge_truncated,
    }
