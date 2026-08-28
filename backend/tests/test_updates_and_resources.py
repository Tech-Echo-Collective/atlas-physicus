import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from physics_atlas_api import models
from physics_atlas_api.config import Settings
from physics_atlas_api.connectors.base import (
    ConnectorBatch,
    NormalizedRecord,
    SourceConnector,
    SourceRecord,
)
from physics_atlas_api.connectors.factory import build_connectors
from physics_atlas_api.metrics.recomputation import NoFormulaMetricRecalculator
from physics_atlas_api.repository import AtlasDatabaseRepository
from physics_atlas_api.resources.monitor import (
    ResourceMonitor,
    ResourceResponse,
    validate_resource_url,
)
from physics_atlas_api.search_index import refresh_search_terms
from physics_atlas_api.seed import ensure_reference_data
from physics_atlas_api.updates.engine import IncrementalUpdateEngine

PROVENANCE = {
    "source": "deterministic test fixture",
    "sourceType": "external-api",
    "version": "test-v1",
    "status": "unverified",
}


class UnresolvedResearcherConnector(SourceConnector):
    provider = "orcid"
    source_version = "test-v1"
    min_interval_seconds = 0

    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        del cursor, limit
        return ConnectorBatch(
            records=(
                SourceRecord(
                    provider="orcid",
                    source_record_id="name-only-record",
                    raw={"name": "Ambiguous Researcher"},
                ),
            ),
            next_cursor="fixture-cursor",
        )

    def fetch_record(self, record_id: str) -> SourceRecord | None:
        del record_id
        return None

    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        return NormalizedRecord(
            provider="orcid",
            kind="researcher",
            source_record_id=record.source_record_id,
            canonical_name="Ambiguous Researcher",
            external_ids=(),
            attributes={},
            raw=record.raw,
            provenance=PROVENANCE,
        )


class RedirectTransport:
    def request(
        self, method: str, url: str, *, timeout_seconds: float
    ) -> ResourceResponse:
        del method, url, timeout_seconds
        return ResourceResponse(301, "https://example.org/current")


class ProviderModeTransport:
    is_fixture = False

    def get_json(self, *args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        raise AssertionError("dataset-mode validation must happen before network I/O")

    def get_text(self, *args: object, **kwargs: object) -> str:
        del args, kwargs
        raise AssertionError("dataset-mode validation must happen before network I/O")


class VariantIdentifierPaperConnector(SourceConnector):
    provider = "crossref"
    source_version = "identifier-variant-test-v1"
    min_interval_seconds = 0

    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        del cursor, limit
        return ConnectorBatch(
            records=(
                SourceRecord(
                    provider="crossref",
                    source_record_id="variant-paper",
                    raw={"title": "Identifier normalization test"},
                ),
            ),
            next_cursor="variant-complete",
        )

    def fetch_record(self, record_id: str) -> SourceRecord | None:
        del record_id
        return None

    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        return NormalizedRecord(
            provider="crossref",
            kind="paper",
            source_record_id=record.source_record_id,
            canonical_name="Identifier normalization test",
            external_ids=(
                ("DOI", "https://doi.org/10.TEST/Variant"),
                ("arXiv", "arXiv:2608.01234v3"),
            ),
            attributes={
                "title": "Identifier normalization test",
                "abstract": "Canonical identifier variants converge.",
                "publication_year": 2026,
                "authors": [],
                "atlas_field_candidates": [],
            },
            raw=record.raw,
            provenance=PROVENANCE,
        )


class MissingYearPaperConnector(VariantIdentifierPaperConnector):
    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        normalized = super().normalize_record(record)
        attributes = dict(normalized.attributes)
        attributes.pop("publication_year")
        return replace(normalized, attributes=attributes)


class CollidingSlugPaperConnector(VariantIdentifierPaperConnector):
    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        del cursor, limit
        return ConnectorBatch(
            records=tuple(
                SourceRecord(
                    provider="crossref",
                    source_record_id=f"collision-{index}",
                    raw={"title": title, "doi": doi},
                )
                for index, (title, doi) in enumerate(
                    (
                        ("Dot identifier", "10.1234/a.b"),
                        ("Dash identifier", "10.1234/a-b"),
                    )
                )
            ),
            next_cursor="collision-complete",
        )

    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        doi = str(record.raw["doi"])
        title = str(record.raw["title"])
        return NormalizedRecord(
            provider="crossref",
            kind="paper",
            source_record_id=record.source_record_id,
            canonical_name=title,
            external_ids=(("doi", doi),),
            attributes={
                "title": title,
                "abstract": "Collision-resistant paper identifier test.",
                "publication_year": 2026,
                "authors": [],
                "atlas_field_candidates": [],
            },
            raw=record.raw,
            provenance=PROVENANCE,
        )


class RejectUnexpectedResourceRequest:
    def request(
        self, method: str, url: str, *, timeout_seconds: float
    ) -> ResourceResponse:
        del method, url, timeout_seconds
        raise AssertionError("a URL that fails revalidation must not be requested")


def add_country(session: Session) -> None:
    session.add(
        models.Country(
            id="country-ch",
            iso_alpha3="CHE",
            iso_alpha2="CH",
            iso_numeric="756",
            name="Switzerland",
            region="Europe",
            provenance_json=PROVENANCE,
        )
    )
    session.commit()


def test_incremental_update_is_idempotent_and_keeps_ambiguity_visible(
    session: Session,
    fixture_directory: Path,
) -> None:
    add_country(session)
    connector = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["ror"]
    recalculator = NoFormulaMetricRecalculator()
    engine = IncrementalUpdateEngine(
        session,
        connector,
        recalculator=recalculator,
    )

    first = engine.run()
    second = engine.run()

    assert first.status == "succeeded"
    assert first.records_added == 1
    assert second.status == "succeeded"
    assert second.idempotent_replay is True
    assert session.scalar(select(func.count()).select_from(models.Institution)) == 1
    assert session.scalar(select(func.count()).select_from(models.SourceSnapshot)) == 1

    unresolved = IncrementalUpdateEngine(
        session,
        UnresolvedResearcherConnector(connector.transport, "https://orcid.test"),
    ).run()
    assert unresolved.status == "succeeded"
    assert unresolved.records_unresolved == 1
    assert session.scalar(select(func.count()).select_from(models.IdentityReview)) == 1
    resolution = session.scalar(
        select(models.IdentityResolution).where(
            models.IdentityResolution.status == "unresolved"
        )
    )
    assert resolution is not None
    assert resolution.status == "unresolved"
    assert resolution.canonical_entity_id is None


def test_incremental_update_never_mixes_fixture_and_provider_data(
    session: Session,
    fixture_directory: Path,
) -> None:
    add_country(session)
    fixture_connector = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["ror"]
    assert (
        IncrementalUpdateEngine(session, fixture_connector).run().status == "succeeded"
    )

    provider_connector = UnresolvedResearcherConnector(
        ProviderModeTransport(), "https://orcid.test"
    )
    with pytest.raises(RuntimeError, match="cannot be written into the same"):
        IncrementalUpdateEngine(session, provider_connector).run()


def test_update_engine_canonicalizes_authority_identifiers_before_upsert(
    session: Session,
    fixture_directory: Path,
) -> None:
    fixture_transport = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["crossref"].transport
    result = IncrementalUpdateEngine(
        session,
        VariantIdentifierPaperConnector(fixture_transport, "https://crossref.test"),
    ).run()

    assert result.status == "succeeded"
    paper = session.scalar(select(models.Paper))
    assert paper is not None
    assert paper.doi == "10.test/variant"
    assert paper.arxiv_id == "2608.01234"
    authority_values = set(
        session.execute(
            select(models.AuthorityIdentifier.scheme, models.AuthorityIdentifier.value)
        ).all()
    )
    assert authority_values == {
        ("doi", "10.test/variant"),
        ("arxiv", "2608.01234"),
    }


def test_new_paper_without_publication_year_is_quarantined_without_inference(
    session: Session,
    fixture_directory: Path,
) -> None:
    fixture_transport = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["crossref"].transport

    result = IncrementalUpdateEngine(
        session,
        MissingYearPaperConnector(fixture_transport, "https://crossref.test"),
    ).run()

    assert result.status == "succeeded"
    assert result.records_unresolved == 1
    assert session.scalar(select(func.count()).select_from(models.Paper)) == 0
    assert session.scalar(select(func.count()).select_from(models.RawEntityRecord)) == 1
    resolution = session.scalar(select(models.IdentityResolution))
    assert resolution is not None
    assert resolution.status == "unresolved"
    assert resolution.method == "insufficient-metadata"
    assert session.scalar(select(func.count()).select_from(models.IdentityReview)) == 1
    cursor = session.get(models.SourceCursor, "crossref")
    assert cursor is not None
    assert cursor.cursor == "variant-complete"


def test_paper_ids_do_not_collide_when_readable_slugs_match(
    session: Session,
    fixture_directory: Path,
) -> None:
    fixture_transport = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["crossref"].transport

    result = IncrementalUpdateEngine(
        session,
        CollidingSlugPaperConnector(fixture_transport, "https://crossref.test"),
    ).run()

    assert result.status == "succeeded"
    papers = list(session.scalars(select(models.Paper).order_by(models.Paper.doi)))
    assert [paper.doi for paper in papers] == ["10.1234/a-b", "10.1234/a.b"]
    assert len({paper.id for paper in papers}) == 2


def test_live_identity_resolution_uses_alias_history_and_ambiguity_gated_fuzzy(
    session: Session,
    fixture_directory: Path,
) -> None:
    entities = [
        models.Researcher(
            id="researcher-maldacena",
            canonical_name="Juan Maldacena",
            aliases=["J. Maldacena", "Shared Physicist"],
            historical_names=["Juan M. Maldacena"],
            external_ids=[],
            field_ids=["hep-th"],
            provenance_json=PROVENANCE,
        ),
        models.Researcher(
            id="researcher-maldonado",
            canonical_name="Juan Maldonado",
            aliases=["Shared Physicist"],
            historical_names=[],
            external_ids=[],
            field_ids=["hep-th"],
            provenance_json=PROVENANCE,
        ),
    ]
    session.add_all(entities)
    session.flush()
    for entity in entities:
        refresh_search_terms(
            session,
            entity_type="researcher",
            entity_id=entity.id,
            canonical_name=entity.canonical_name,
            aliases=entity.aliases,
            historical_names=entity.historical_names,
            external_ids=entity.external_ids,
        )
    session.commit()
    connector = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["orcid"]
    engine = IncrementalUpdateEngine(session, connector)

    def resolve(name: str) -> tuple[str | None, str, str | None, float]:
        result = engine._resolve_identity(  # noqa: SLF001 - resolver contract test
            NormalizedRecord(
                provider="orcid",
                kind="researcher",
                source_record_id=f"test-{name}",
                canonical_name=name,
                external_ids=(),
                attributes={},
                raw={"name": name},
                provenance=PROVENANCE,
            )
        )
        return result[0], result[1], result[2], result[3]

    assert resolve("J. Maldacena")[:3] == (
        "researcher-maldacena",
        "matched",
        "alias",
    )
    assert resolve("Juan M. Maldacena")[:3] == (
        "researcher-maldacena",
        "matched",
        "historical-name",
    )
    assert resolve("Juan Maldacna")[:3] == (
        "researcher-maldacena",
        "matched",
        "fuzzy-name",
    )
    ambiguous = resolve("Shared Physicist")
    assert ambiguous[0] is None
    assert ambiguous[1] == "ambiguous"


def test_resource_monitor_tracks_redirects_without_crawling(session: Session) -> None:
    session.add(
        models.ExternalResource(
            id="resource-test",
            entity_type="institution",
            entity_id="institution-test",
            resource_type="official-institution-website",
            label="Official website",
            url="https://example.org/old",
            source="test fixture",
            is_primary=True,
            verified=False,
            health_status="unknown",
            provenance_json=PROVENANCE,
        )
    )
    session.commit()

    result = ResourceMonitor(
        session,
        RedirectTransport(),
        max_attempts=1,
        minimum_interval_seconds=0,
        url_validator=lambda _: True,
    ).run(now=datetime(2026, 8, 26, tzinfo=UTC))

    resource = session.get(models.ExternalResource, "resource-test")
    assert result.redirects == 1
    assert resource is not None
    assert resource.verified is True
    assert resource.health_status == "permanent-redirect"
    assert resource.redirect_target == "https://example.org/current"
    assert session.scalar(select(func.count()).select_from(models.ResourceCheck)) == 1
    assert validate_resource_url("http://127.0.0.1/internal") is False
    assert validate_resource_url("http://169.254.169.254/latest/meta-data") is False
    assert validate_resource_url("https://[::1]/internal") is False
    assert validate_resource_url("https://example.org:8443/resource") is False
    assert (
        validate_resource_url(
            "https://api.ror.org/v2/organizations",
            resolve_dns=False,
            allowed_hosts={"ROR.ORG."},
        )
        is True
    )
    assert (
        validate_resource_url(
            "https://example.org/resource",
            resolve_dns=False,
            allowed_hosts={"ror.org"},
        )
        is False
    )


def test_resource_monitor_revalidates_immediately_before_network_io(
    session: Session,
) -> None:
    session.add(
        models.ExternalResource(
            id="resource-revalidation-test",
            entity_type="institution",
            entity_id="institution-test",
            resource_type="official-institution-website",
            label="Official website",
            url="https://example.org/resource",
            source="test fixture",
            is_primary=True,
            verified=False,
            health_status="unknown",
            provenance_json=PROVENANCE,
        )
    )
    session.commit()
    validation_results = iter((True, False))

    ResourceMonitor(
        session,
        RejectUnexpectedResourceRequest(),
        max_attempts=1,
        minimum_interval_seconds=0,
        url_validator=lambda _: next(validation_results),
    ).run(now=datetime(2026, 8, 26, tzinfo=UTC))

    resource = session.get(models.ExternalResource, "resource-revalidation-test")
    check = session.scalar(
        select(models.ResourceCheck).where(
            models.ResourceCheck.resource_id == "resource-revalidation-test"
        )
    )
    assert resource is not None
    assert resource.health_status == "unknown"
    assert check is not None
    assert check.error == "URL failed public HTTP(S) validation before request"


def test_paper_ingestion_preserves_raw_identity_and_author_relationships(
    session: Session,
    fixture_directory: Path,
) -> None:
    ensure_reference_data(session)
    connector = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["inspire"]

    result = IncrementalUpdateEngine(session, connector).run()

    assert result.status == "succeeded"
    paper = session.scalar(select(models.Paper))
    authorship = session.scalar(select(models.Authorship))
    assert paper is not None
    assert authorship is not None
    assert authorship.paper_id == paper.id
    assert (
        session.scalar(
            select(func.count())
            .select_from(models.RawEntityRecord)
            .where(models.RawEntityRecord.entity_type == "paper")
        )
        == 1
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(models.IdentityResolution)
            .where(models.IdentityResolution.entity_type == "paper")
        )
        == 1
    )
    assert paper.provenance_json["sourceSnapshotId"] == result.snapshot_id
    snapshot = session.get(models.SourceSnapshot, result.snapshot_id)
    assert snapshot is not None
    expected_envelope = json.loads(
        (fixture_directory / "inspire.json").read_text(encoding="utf-8")
    )
    assert snapshot.raw_payload == [
        {"contentType": "application/json", "body": expected_envelope}
    ]
    paper_provenance = AtlasDatabaseRepository(session).provenance("paper", paper.id)
    assert paper_provenance is not None
    assert (
        paper_provenance["sourceRecords"][0]["sourceSnapshotId"] == result.snapshot_id
    )
    assert paper_provenance["resolution"]["status"] == "matched"
