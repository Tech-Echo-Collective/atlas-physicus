from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

JsonType = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ProvenanceMixin:
    provenance_json: Mapped[dict[str, Any]] = mapped_column(
        "provenance", JsonType, default=dict, nullable=False
    )


class ScienceDomain(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "science_domains"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    label: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class ResearchField(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "research_fields"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    domain_id: Mapped[str] = mapped_column(
        ForeignKey("science_domains.id", ondelete="RESTRICT"), index=True
    )
    label: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    provider_mappings: Mapped[dict[str, Any]] = mapped_column(
        JsonType, default=dict, nullable=False
    )


class Country(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "countries"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    iso_alpha3: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    iso_alpha2: Mapped[str | None] = mapped_column(String(2), unique=True)
    iso_numeric: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    region: Mapped[str] = mapped_column(String(160), nullable=False)


class GeographicView(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "geographic_views"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    country_id: Mapped[str] = mapped_column(
        ForeignKey("countries.id", ondelete="CASCADE"), unique=True, index=True
    )
    geometry_iso_numerics: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    location_country_ids: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )


class DatasetState(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "dataset_state"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default="current")
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    period: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    latest_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_snapshot_ids: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    update_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False)


class Institution(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "institutions"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    aliases: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    historical_names: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    external_ids: Mapped[list[dict[str, str]]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    identity_confidence: Mapped[float | None] = mapped_column(Float)
    country_id: Mapped[str] = mapped_column(
        ForeignKey("countries.id", ondelete="RESTRICT"), index=True
    )
    city: Mapped[str] = mapped_column(String(240), nullable=False)
    longitude: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    field_ids: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="institution_longitude",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="institution_latitude",
        ),
    )


class ResearchGroup(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "research_groups"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    institution_id: Mapped[str] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    field_ids: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)


class Researcher(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "researchers"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    aliases: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    historical_names: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    external_ids: Mapped[list[dict[str, str]]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    identity_confidence: Mapped[float | None] = mapped_column(Float)
    field_ids: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)


class AuthorityIdentifier(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "authority_identifiers"
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    scheme: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    is_authoritative: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    __table_args__ = (
        UniqueConstraint("scheme", "value"),
        Index("ix_authority_entity", "entity_type", "entity_id"),
    )


class EntitySearchTerm(Base, TimestampMixin):
    __tablename__ = "entity_search_terms"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    term: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(500), nullable=False)
    match_method: Mapped[str] = mapped_column(String(80), nullable=False)
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "match_method", "normalized_term"),
        Index("ix_entity_search_term_lookup", "normalized_term", "entity_type"),
    )


class Paper(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "papers"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    publication_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    doi: Mapped[str | None] = mapped_column(String(500), unique=True, index=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    external_ids: Mapped[list[dict[str, str]]] = mapped_column(
        JsonType, default=list, nullable=False
    )


class PaperField(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "paper_fields"
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    field_id: Mapped[str] = mapped_column(
        ForeignKey("research_fields.id", ondelete="RESTRICT"), primary_key=True
    )
    classification_method: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)


class Authorship(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "authorships"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    researcher_id: Mapped[str] = mapped_column(
        ForeignKey("researchers.id", ondelete="RESTRICT"), index=True
    )
    author_position: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("paper_id", "researcher_id"),
        CheckConstraint("author_position > 0", name="authorship_position"),
    )


class Affiliation(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "affiliations"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    researcher_id: Mapped[str] = mapped_column(
        ForeignKey("researchers.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[str] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), index=True
    )
    research_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_groups.id", ondelete="SET NULL"), index=True
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(200))
    confidence: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="affiliation_date_order",
        ),
    )


class Citation(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "citations"
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    citing_paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    cited_paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(300))
    __table_args__ = (UniqueConstraint("citing_paper_id", "cited_paper_id", "source"),)


class MetricDefinition(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "metric_definitions"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    category: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    interpretation: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    required_data: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    implementation_status: Mapped[str] = mapped_column(String(80), nullable=False)


class MetricObservation(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "metric_observations"
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    science_domain_id: Mapped[str | None] = mapped_column(String(120), index=True)
    field_id: Mapped[str | None] = mapped_column(String(120), index=True)
    metric_id: Mapped[str] = mapped_column(
        ForeignKey("metric_definitions.id", ondelete="RESTRICT"), index=True
    )
    period: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    value: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(240), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(120), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(120), nullable=False)
    data_source_version: Mapped[str | None] = mapped_column(String(160))
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "science_domain_id",
            "field_id",
            "metric_id",
            "period",
            "calculation_version",
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "ix_metric_observation_partition",
            "metric_id",
            "field_id",
            "period",
            "entity_type",
        ),
    )


class HistoricalEvent(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "historical_events"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int] = mapped_column(Integer, index=True)
    field_id: Mapped[str] = mapped_column(
        ForeignKey("research_fields.id", ondelete="RESTRICT"), index=True
    )
    related_researcher_ids: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    related_institution_ids: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )


class ExternalResource(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "external_resources"
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(160), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(400))
    external_id: Mapped[dict[str, str] | None] = mapped_column(JsonType)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_method: Mapped[str | None] = mapped_column(String(120))
    health_status: Mapped[str] = mapped_column(
        String(40), default="unknown", nullable=False, index=True
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    redirect_target: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "resource_type", "url"),
    )


class ResourceCheck(Base):
    __tablename__ = "resource_checks"
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    resource_id: Mapped[str] = mapped_column(
        ForeignKey("external_resources.id", ondelete="CASCADE"), index=True
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    redirect_target: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class SourceSnapshot(Base, ProvenanceMixin):
    __tablename__ = "source_snapshots"
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_version: Mapped[str] = mapped_column(String(120), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    update_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="SET NULL")
    )
    content_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_reference: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    __table_args__ = (UniqueConstraint("source", "content_checksum"),)


class RawEntityRecord(Base, ProvenanceMixin):
    __tablename__ = "raw_entity_records"
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_record_id: Mapped[str] = mapped_column(String(400), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="RESTRICT"), index=True
    )
    raw_name: Mapped[str] = mapped_column(Text, nullable=False)
    external_ids: Mapped[list[dict[str, str]]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    attributes_json: Mapped[dict[str, Any]] = mapped_column(
        "attributes", JsonType, default=dict, nullable=False
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("source", "source_record_id", "source_snapshot_id"),
    )


class IdentityResolution(Base, ProvenanceMixin):
    __tablename__ = "identity_resolutions"
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    raw_entity_record_id: Mapped[str] = mapped_column(
        ForeignKey("raw_entity_records.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    canonical_entity_id: Mapped[str | None] = mapped_column(String(200), index=True)
    method: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    resolver_version: Mapped[str] = mapped_column(String(120), nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class IdentityReview(Base, TimestampMixin):
    __tablename__ = "identity_reviews"
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    resolution_id: Mapped[str] = mapped_column(
        ForeignKey("identity_resolutions.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(
        String(40), default="needs_review", nullable=False, index=True
    )
    candidate_entity_ids: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    decision_entity_id: Mapped[str | None] = mapped_column(String(200))
    decision_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(240))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceCursor(Base):
    __tablename__ = "source_cursors"
    source: Mapped[str] = mapped_column(String(120), primary_key=True)
    cursor: Mapped[str | None] = mapped_column(Text)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(
        JsonType, default=dict, nullable=False
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )


class DatasetUpdate(Base, ProvenanceMixin):
    __tablename__ = "dataset_updates"
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    update_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    source_snapshot_ids: Mapped[list[str]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    previous_dataset_version: Mapped[str | None] = mapped_column(String(120))
    dataset_version: Mapped[str] = mapped_column(String(120), nullable=False)
    resolver_version: Mapped[str] = mapped_column(String(120), nullable=False)
    metric_calculation_version: Mapped[str | None] = mapped_column(String(120))
    changes: Mapped[dict[str, int]] = mapped_column(JsonType, nullable=False)
    affected_entities: Mapped[list[dict[str, str]]] = mapped_column(
        JsonType, default=list, nullable=False
    )


class UpdateRun(Base):
    __tablename__ = "update_runs"
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cursor_before: Mapped[str | None] = mapped_column(Text)
    cursor_after: Mapped[str | None] = mapped_column(Text)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_changed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_unresolved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    affected_entities: Mapped[list[dict[str, str]]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    affected_metric_partitions: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text)
