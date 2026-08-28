from datetime import datetime
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    field_validator,
    model_validator,
)


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="ignore",
    )


class StrictApiModel(ApiModel):
    """Transport contracts must reject undocumented response fields."""

    model_config = ConfigDict(extra="forbid")


class Provenance(ApiModel):
    source: str
    source_type: Literal[
        "synthetic-demo", "external-api", "institutional-source", "derived"
    ]
    version: str
    status: Literal["synthetic", "unverified", "verified", "deprecated"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    retrieved_at: datetime | None = None
    source_record_id: str | None = None
    source_snapshot_id: str | None = None


class ExternalIdentifier(ApiModel):
    scheme: str = Field(min_length=1)
    value: str = Field(min_length=1)


class ScienceDomainOut(ApiModel):
    id: str
    label: str
    description: str
    field_ids: list[str]
    provenance: Provenance


class ResearchFieldOut(ApiModel):
    id: str
    label: str
    description: str
    provenance: Provenance


class CountryOut(ApiModel):
    id: str
    iso_alpha3: str = Field(min_length=3, max_length=3)
    iso_numeric: str = Field(pattern=r"^\d{3}$")
    name: str
    region: str
    provenance: Provenance


class GeographicViewOut(ApiModel):
    id: str
    country_id: str
    geometry_iso_numerics: list[str]
    location_country_ids: list[str]
    provenance: Provenance


class InstitutionLocation(ApiModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)


class InstitutionOut(ApiModel):
    id: str
    name: str
    canonical_name: str
    aliases: list[str] = []
    historical_names: list[str] = []
    external_ids: list[ExternalIdentifier] = []
    identity_confidence: float | None = Field(default=None, ge=0, le=1)
    country_id: str
    city: str
    field_ids: list[str]
    location: InstitutionLocation | None = None
    provenance: Provenance


class ResearchGroupOut(ApiModel):
    id: str
    name: str
    institution_id: str
    description: str
    field_ids: list[str]
    provenance: Provenance


class ResearcherOut(ApiModel):
    id: str
    name: str
    canonical_name: str
    aliases: list[str] = []
    historical_names: list[str] = []
    external_ids: list[ExternalIdentifier] = []
    identity_confidence: float | None = Field(default=None, ge=0, le=1)
    field_ids: list[str]
    provenance: Provenance


class PaperOut(ApiModel):
    id: str
    title: str
    summary: str
    year: int
    field_ids: list[str]
    doi: str | None = None
    arxiv_id: str | None = None
    external_identifiers: list[ExternalIdentifier] = []
    provenance: Provenance


class AffiliationOut(ApiModel):
    id: str
    researcher_id: str
    institution_id: str
    research_group_id: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    source: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance: Provenance


class AuthorshipOut(ApiModel):
    id: str
    paper_id: str
    researcher_id: str
    author_position: int = Field(gt=0)
    provenance: Provenance


class HistoricalEventOut(ApiModel):
    id: str
    title: str
    summary: str
    year: int
    field_id: str
    related_researcher_ids: list[str]
    related_institution_ids: list[str]
    provenance: Provenance


class MetricDefinitionOut(ApiModel):
    id: str
    name: str
    category: str
    description: str
    interpretation: str
    unit: str
    version: str
    required_data: list[str]
    implementation_status: str
    provenance: Provenance


class MetricObservationOut(ApiModel):
    id: str
    entity_type: str
    entity_id: str
    science_domain_id: str | None = None
    field_id: str | None = None
    metric_id: str
    period: str
    value: float
    source: str
    algorithm_version: str
    calculation_version: str
    data_source_version: str | None = None
    calculated_at: datetime
    provenance: Provenance


class ExternalResourceOut(ApiModel):
    id: str
    entity_type: str
    entity_id: str
    resource_type: str
    label: str
    url: HttpUrl
    source: str
    source_record_id: str | None = None
    external_id: ExternalIdentifier | None = None
    is_primary: bool
    verified: bool
    verification_method: str | None = None
    health_status: str
    last_checked_at: datetime | None = None
    http_status: int | None = None
    redirect_target: HttpUrl | None = None
    provenance: Provenance


class SearchResultOut(ApiModel):
    entity_id: str
    entity_type: str
    label: str
    context: str
    match_confidence: float = Field(ge=0, le=1)
    matched_on: str
    matched_value: str | None = None
    identity_confidence: float | None = Field(default=None, ge=0, le=1)


class Page[T](ApiModel):
    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class DatasetMetadataOut(StrictApiModel):
    schema_version: str = Field(min_length=1)
    dataset_kind: Literal["synthetic-demo", "inspire-hep-pilot", "live-api"]
    period: str = Field(pattern=r"^\d{4}$")
    generated_at: datetime
    latest_update_at: datetime | None = None
    source_snapshot_ids: list[str]
    update_sequence: int = Field(ge=0)
    disclaimer: str = Field(min_length=1)
    provenance: Provenance


class SourceSnapshotOut(StrictApiModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    captured_at: datetime
    update_mode: Literal["full-snapshot", "incremental"]
    record_count: int = Field(ge=0)
    previous_snapshot_id: str | None = None
    content_checksum: str = Field(min_length=1)
    storage_reference: str | None = None
    provenance: Provenance


class EntityChangeSummaryOut(StrictApiModel):
    created: int = Field(ge=0)
    updated: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    unresolved: int = Field(ge=0)
    failed: int = Field(default=0, ge=0)


class AffectedEntityOut(StrictApiModel):
    entity_type: Literal["institution", "researcher", "paper"]
    entity_id: str = Field(min_length=1)


class DatasetUpdateOut(StrictApiModel):
    id: str = Field(min_length=1)
    applied_at: datetime
    update_mode: Literal["full-snapshot", "incremental", "reprocess"]
    source_snapshot_ids: list[str] = Field(min_length=1)
    previous_dataset_version: str | None = None
    dataset_version: str = Field(min_length=1)
    resolver_version: str = Field(min_length=1)
    metric_calculation_version: str | None = None
    changes: EntityChangeSummaryOut
    affected_entities: list[AffectedEntityOut]
    provenance: Provenance


class RawEntityRecordOut(StrictApiModel):
    id: str = Field(min_length=1)
    entity_type: Literal["institution", "researcher", "paper"]
    source_record_id: str = Field(min_length=1)
    source_snapshot_id: str | None = None
    raw_name: str = Field(min_length=1)
    external_ids: list[ExternalIdentifier]
    attributes: dict[str, JsonValue]
    ingested_at: datetime
    provenance: Provenance


IdentityResolutionMethod = Literal[
    "external-identifier",
    "canonical-name",
    "alias",
    "historical-name",
    "fuzzy-name",
    "source-record-identifier",
    "manual-review",
    "insufficient-metadata",
]


class IdentityEvidenceOut(StrictApiModel):
    method: IdentityResolutionMethod | Literal["required-metadata"]
    input_value: str = Field(min_length=1)
    candidate_entity_id: str | None = None
    canonical_value: str | None = None
    score: float = Field(ge=0, le=1)


class IdentityResolutionOut(StrictApiModel):
    id: str = Field(min_length=1)
    raw_entity_record_id: str = Field(min_length=1)
    entity_type: Literal["institution", "researcher", "paper"]
    status: Literal["matched", "unresolved", "ambiguous"]
    canonical_entity_id: str | None = None
    method: IdentityResolutionMethod | None = None
    confidence: float = Field(ge=0, le=1)
    evidence: list[IdentityEvidenceOut]
    resolver_version: str = Field(min_length=1)
    resolved_at: datetime
    provenance: Provenance

    @model_validator(mode="after")
    def validate_resolution_boundary(self) -> Self:
        if self.status == "matched" and (
            self.canonical_entity_id is None or self.method is None
        ):
            raise ValueError("Matched identity requires a canonical entity and method")
        if self.status != "matched" and self.canonical_entity_id is not None:
            raise ValueError("Unresolved identity cannot reference a canonical entity")
        return self


class KnowledgeGraphNodeOut(StrictApiModel):
    id: str = Field(min_length=1)
    entity_type: Literal["institution", "researcher"]
    label: str = Field(min_length=1)


class KnowledgeGraphEdgeOut(StrictApiModel):
    id: str = Field(min_length=1)
    relationship_type: Literal["affiliated-with"]
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    provenance: Provenance


class KnowledgeGraphOut(StrictApiModel):
    nodes: list[KnowledgeGraphNodeOut]
    edges: list[KnowledgeGraphEdgeOut]
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    node_limit: int = Field(ge=1, le=1000)
    edge_limit: int = Field(ge=1, le=5000)
    truncated: bool


class InstitutionMapNodeOut(ApiModel):
    institution: InstitutionOut
    observation: MetricObservationOut


class InstitutionProfileOut(ApiModel):
    institution: InstitutionOut
    resources: list[ExternalResourceOut]
    research_groups: list[ResearchGroupOut]
    affiliations: list[AffiliationOut]
    researchers: list[ResearcherOut]
    papers: list[PaperOut]
    metrics: list[MetricObservationOut]


class AffiliationHistoryEntryOut(ApiModel):
    affiliation: AffiliationOut
    institution: InstitutionOut
    research_group: ResearchGroupOut | None = None


class ResearcherProfileOut(ApiModel):
    researcher: ResearcherOut
    resources: list[ExternalResourceOut]
    fields: list[ResearchFieldOut]
    affiliation_history: list[AffiliationHistoryEntryOut]
    papers: list[PaperOut]
    collaborators: list[ResearcherOut]
    metrics: list[MetricObservationOut]


class ResearchGroupProfileOut(ApiModel):
    research_group: ResearchGroupOut
    institution: InstitutionOut
    resources: list[ExternalResourceOut]
    fields: list[ResearchFieldOut]
    affiliations: list[AffiliationOut]
    members: list[ResearcherOut]
    papers: list[PaperOut]


class HealthOut(ApiModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["ok", "unavailable"]
    timestamp: datetime


class SourceUpdateStatus(ApiModel):
    source: str
    status: str
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    cursor: str | None = None
    consecutive_failures: int = 0


class UpdateStatusOut(ApiModel):
    last_successful_update: datetime | None = None
    last_failed_update: datetime | None = None
    unresolved_entity_count: int
    resource_check_failures: int
    metric_recalculation_status: str
    sources: list[SourceUpdateStatus]


class ProvenanceOut(ApiModel):
    entity_type: str
    entity_id: str
    provenance: Provenance
    source_records: list[dict[str, Any]] = []
    resolution: dict[str, Any] | None = None


class ErrorDetail(ApiModel):
    code: str
    message: str
    context: dict[str, Any] = {}


class ErrorResponse(ApiModel):
    error: ErrorDetail


class ResourceUrl(ApiModel):
    url: HttpUrl

    @field_validator("url")
    @classmethod
    def only_public_http(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme not in {"http", "https"}:
            raise ValueError("Only HTTP(S) resources are supported")
        return value
