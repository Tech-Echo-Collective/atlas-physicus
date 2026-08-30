import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
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
    SourceTransport,
)
from physics_atlas_api.connectors.factory import build_connectors
from physics_atlas_api.fields import PHYSICS_FIELD_ONTOLOGY_VERSION
from physics_atlas_api.fields.mapping import (
    FIELD_WEIGHTING_POLICY_VERSION,
    PROVIDER_FIELD_MAPPING_VERSION,
    Provider,
    ProviderCategoryEvidence,
    map_provider_categories,
)
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


class SequencedAuthorityPaperConnector(SourceConnector):
    provider = "inspire"
    source_version = "authority-replay-test-v1"
    min_interval_seconds = 0

    def __init__(
        self,
        transport: SourceTransport,
        base_url: str,
        records: tuple[dict[str, object], ...],
    ):
        super().__init__(transport, base_url)
        self.records = records

    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        del limit
        index = int(cursor or 0)
        raw = self.records[index]
        source_record_id = str(raw["source_record_id"])
        return ConnectorBatch(
            records=(
                SourceRecord(
                    provider="inspire",
                    source_record_id=source_record_id,
                    raw=raw,
                ),
            ),
            next_cursor=str(index + 1),
        )

    def fetch_record(self, record_id: str) -> SourceRecord | None:
        del record_id
        return None

    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        raw_categories = record.raw.get("field_categories", ("Theory-HEP",))
        categories = (
            tuple(str(item) for item in raw_categories)
            if isinstance(raw_categories, (list, tuple))
            else (str(raw_categories),)
        )
        mapping = map_provider_categories(
            "inspire",
            tuple(
                ProviderCategoryEvidence(
                    category=category,
                    role="primary" if index == 0 else "secondary",
                )
                for index, category in enumerate(categories)
            ),
        )
        return NormalizedRecord(
            provider="inspire",
            kind="paper",
            source_record_id=record.source_record_id,
            canonical_name=str(record.raw["title"]),
            external_ids=tuple(record.raw["external_ids"]),  # type: ignore[arg-type]
            attributes={
                "title": str(record.raw["title"]),
                "abstract": str(record.raw.get("abstract", "")),
                "publication_year": int(record.raw["publication_year"]),
                "publication_date": record.raw.get("publication_date"),
                "document_type": str(record.raw.get("document_type", "article")),
                "authors": record.raw.get("authors", []),
                "atlas_field_candidates": list(mapping.atlas_field_ids),
                "field_mapping_confidence": mapping.confidence,
                "field_mapping_method": mapping.method,
                "field_ontology_version": mapping.ontology_version,
                "field_weighting_policy_version": mapping.weighting_policy_version,
                "atlas_field_assignments": [
                    {
                        "field_id": assignment.field_id,
                        "weight": assignment.weight,
                    }
                    for assignment in mapping.assignments
                ],
                "field_mapping_provenance": mapping.provenance_payload(),
                "field_mapping_uncertainty": mapping.uncertainty_note,
            },
            raw=record.raw,
            provenance={
                **PROVENANCE,
                "sourceRecordId": record.source_record_id,
            },
        )


class CrossProviderFieldPaperConnector(SourceConnector):
    source_version = "cross-provider-field-test-v1"
    min_interval_seconds = 0

    def __init__(
        self,
        transport: SourceTransport,
        provider: Provider,
        category: str,
    ) -> None:
        self.provider = provider
        self.category = category
        super().__init__(transport, f"https://{provider}.test")

    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        del cursor, limit
        return ConnectorBatch(
            records=(
                SourceRecord(
                    provider=self.provider,
                    source_record_id=f"{self.provider}-field-paper",
                    raw={"category": self.category},
                ),
            ),
            next_cursor="complete",
        )

    def fetch_record(self, record_id: str) -> SourceRecord | None:
        del record_id
        return None

    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        mapping = map_provider_categories(
            self.provider,
            (ProviderCategoryEvidence(self.category, role="primary"),),
        )
        return NormalizedRecord(
            provider=self.provider,
            kind="paper",
            source_record_id=record.source_record_id,
            canonical_name="Cross-provider field reconciliation fixture",
            external_ids=(
                ("doi", "10.5555/cross-provider-field-fixture"),
                ("arxiv", "2608.09999"),
            ),
            attributes={
                "title": "Cross-provider field reconciliation fixture",
                "publication_year": 2026,
                "authors": [],
                "raw_category_evidence": [
                    {
                        "category": item.evidence.category,
                        "role": item.evidence.role,
                        "taxonomy": item.evidence.taxonomy,
                    }
                    for item in mapping.category_mappings
                ],
                "field_mapping_provenance": mapping.provenance_payload(),
            },
            raw=record.raw,
            provenance={
                **PROVENANCE,
                "sourceRecordId": record.source_record_id,
            },
        )


class ReplayCheckpointConnector(SourceConnector):
    provider = "crossref"
    source_version = "replay-checkpoint-test-v1"
    min_interval_seconds = 0

    def __init__(
        self,
        transport: SourceTransport,
        base_url: str,
        *,
        fail_normalization: bool,
    ):
        super().__init__(
            transport,
            base_url,
            cursor_scope="hep-th-v1:crossref:replay-checkpoint-test-v1",
            dataset_scope="hep-th-v1",
        )
        self.fail_normalization = fail_normalization
        self.observed_checkpoint: dict[str, object] = {}

    def fetch_new_records(self, cursor: str | None, limit: int = 100) -> ConnectorBatch:
        del limit
        self.observed_checkpoint = self.get_checkpoint()
        replay_checkpoint = {
            "since": "2026-08-01T00:00:00+00:00",
            "until": "2026-08-02T00:00:00+00:00",
            "start": 0,
        }
        return self._complete(
            [
                SourceRecord(
                    provider="crossref",
                    source_record_id="replay-paper",
                    raw={"title": "Replay checkpoint paper"},
                )
            ],
            "2026-08-02T00:00:00+00:00",
            {},
            replay_checkpoint=replay_checkpoint,
        )

    def fetch_record(self, record_id: str) -> SourceRecord | None:
        del record_id
        return None

    def normalize_record(self, record: SourceRecord) -> NormalizedRecord:
        if self.fail_normalization:
            raise ValueError("deliberate materialization failure")
        return NormalizedRecord(
            provider="crossref",
            kind="paper",
            source_record_id=record.source_record_id,
            canonical_name="Replay checkpoint paper",
            external_ids=(("doi", "10.1234/replay-checkpoint"),),
            attributes={
                "title": "Replay checkpoint paper",
                "abstract": "A deterministic recovery test.",
                "publication_year": 2026,
                "authors": [],
                "atlas_field_candidates": ["hep-th"],
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
        Settings(
            database_url="sqlite://",
            fixture_mode=True,
            ror_record_ids="03yrm5c26",
        ),
        fixture_directory,
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
        UnresolvedResearcherConnector(
            connector.transport,
            "https://orcid.test",
            dataset_scope=connector.dataset_scope,
        ),
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
        Settings(
            database_url="sqlite://",
            fixture_mode=True,
            ror_record_ids="03yrm5c26",
        ),
        fixture_directory,
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


def test_identical_payload_in_a_new_scope_has_distinct_snapshot_identity(
    session: Session,
    fixture_directory: Path,
) -> None:
    fixture_transport = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["crossref"].transport
    first_connector = VariantIdentifierPaperConnector(
        fixture_transport,
        "https://crossref.test",
        cursor_scope="scope-a:crossref:targeted-v1",
    )
    first = IncrementalUpdateEngine(session, first_connector).run()
    assert first.status == "succeeded"

    cursor = session.get(models.SourceCursor, "crossref")
    assert cursor is not None
    session.delete(cursor)
    session.commit()

    second_connector = VariantIdentifierPaperConnector(
        fixture_transport,
        "https://crossref.test",
        cursor_scope="scope-b:crossref:targeted-v1",
    )
    second = IncrementalUpdateEngine(session, second_connector).run()

    assert second.status == "succeeded"
    assert second.idempotent_replay is False
    assert first.snapshot_id != second.snapshot_id
    assert session.scalar(select(func.count()).select_from(models.SourceSnapshot)) == 2


def test_live_dataset_acquisition_scope_fails_closed_on_missing_or_mismatch(
    session: Session,
    fixture_directory: Path,
) -> None:
    fixture_transport = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["crossref"].transport
    connector = VariantIdentifierPaperConnector(
        fixture_transport,
        "https://crossref.test",
        dataset_scope="hep-th-v1",
    )
    assert IncrementalUpdateEngine(session, connector).run().status == "succeeded"

    dataset_state = session.get(models.DatasetState, "current")
    assert dataset_state is not None
    dataset_state.provenance_json = {
        key: value
        for key, value in dataset_state.provenance_json.items()
        if key != "acquisitionScope"
    }
    session.commit()
    with pytest.raises(RuntimeError, match="missing its acquisition-scope marker"):
        IncrementalUpdateEngine(session, connector).run()

    dataset_state.provenance_json = {
        **dataset_state.provenance_json,
        "acquisitionScope": "broader-physics-v0",
    }
    session.commit()
    with pytest.raises(RuntimeError, match="created for a different scope"):
        IncrementalUpdateEngine(session, connector).run()


def test_failed_batch_replays_the_same_closed_window_after_restart(
    session: Session,
    fixture_directory: Path,
) -> None:
    fixture_transport = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["crossref"].transport
    failing_connector = ReplayCheckpointConnector(
        fixture_transport,
        "https://crossref.test",
        fail_normalization=True,
    )

    failed = IncrementalUpdateEngine(session, failing_connector).run()

    expected_checkpoint = {
        "since": "2026-08-01T00:00:00+00:00",
        "until": "2026-08-02T00:00:00+00:00",
        "start": 0,
    }
    assert failed.status == "failed"
    cursor = session.get(models.SourceCursor, "crossref")
    assert cursor is not None
    assert cursor.cursor is None
    assert cursor.checkpoint == expected_checkpoint
    assert session.scalar(select(func.count()).select_from(models.SourceSnapshot)) == 0

    restarted_connector = ReplayCheckpointConnector(
        fixture_transport,
        "https://crossref.test",
        fail_normalization=False,
    )
    recovered = IncrementalUpdateEngine(session, restarted_connector).run()

    assert restarted_connector.observed_checkpoint == expected_checkpoint
    assert recovered.status == "succeeded"
    assert recovered.records_added == 1
    cursor = session.get(models.SourceCursor, "crossref")
    assert cursor is not None
    assert cursor.cursor == "2026-08-02T00:00:00+00:00"
    assert cursor.checkpoint == {}


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


def test_changed_inspire_paper_replays_by_authority_and_adds_later_identifiers(
    session: Session,
    fixture_directory: Path,
) -> None:
    ensure_reference_data(session)
    fixture_transport = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["inspire"].transport
    connector = SequencedAuthorityPaperConnector(
        fixture_transport,
        "https://inspire.test",
        (
            {
                "source_record_id": "900001",
                "title": "Authority replay paper",
                "abstract": "Initial metadata.",
                "publication_year": 2025,
                "external_ids": (("inspire", "900001"),),
            },
            {
                "source_record_id": "900001",
                "title": "Authority replay paper, revised",
                "abstract": "Revised metadata.",
                "publication_year": 2025,
                "external_ids": (("inspire", "900001"),),
            },
            {
                "source_record_id": "900001",
                "title": "Authority replay paper, identified",
                "abstract": "Identifiers supplied later.",
                "publication_year": 2025,
                "external_ids": (
                    ("inspire", "900001"),
                    ("doi", "10.1234/authority-replay"),
                    ("arxiv", "2501.00001"),
                ),
            },
        ),
    )
    engine = IncrementalUpdateEngine(session, connector)

    results = [engine.run(), engine.run(), engine.run()]

    assert [result.status for result in results] == [
        "succeeded",
        "succeeded",
        "succeeded",
    ]
    assert [result.records_added for result in results] == [1, 0, 0]
    assert [result.records_changed for result in results] == [0, 1, 1]
    papers = list(session.scalars(select(models.Paper)))
    assert len(papers) == 1
    assert papers[0].title == "Authority replay paper, identified"
    assert papers[0].doi == "10.1234/authority-replay"
    assert papers[0].arxiv_id == "2501.00001"
    assert set(
        session.execute(
            select(
                models.AuthorityIdentifier.scheme, models.AuthorityIdentifier.value
            ).where(models.AuthorityIdentifier.entity_type == "paper")
        ).all()
    ) == {
        ("inspire", "900001"),
        ("doi", "10.1234/authority-replay"),
        ("arxiv", "2501.00001"),
    }


def test_conflicting_paper_authorities_are_queued_without_silent_merge(
    session: Session,
    fixture_directory: Path,
) -> None:
    ensure_reference_data(session)
    fixture_transport = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["inspire"].transport
    connector = SequencedAuthorityPaperConnector(
        fixture_transport,
        "https://inspire.test",
        (
            {
                "source_record_id": "910001",
                "title": "First authority paper",
                "publication_year": 2025,
                "external_ids": (("inspire", "910001"),),
            },
            {
                "source_record_id": "910002",
                "title": "Second authority paper",
                "publication_year": 2025,
                "external_ids": (
                    ("inspire", "910002"),
                    ("doi", "10.1234/shared-authority"),
                ),
            },
            {
                "source_record_id": "910001",
                "title": "Conflicting authority evidence",
                "publication_year": 2025,
                "external_ids": (
                    ("inspire", "910001"),
                    ("doi", "10.1234/shared-authority"),
                ),
            },
        ),
    )
    engine = IncrementalUpdateEngine(session, connector)

    first = engine.run()
    second = engine.run()
    conflicting = engine.run()

    assert first.records_added == second.records_added == 1
    assert conflicting.status == "succeeded"
    assert conflicting.records_unresolved == 1
    papers = list(session.scalars(select(models.Paper).order_by(models.Paper.id)))
    assert len(papers) == 2
    assert {paper.title for paper in papers} == {
        "First authority paper",
        "Second authority paper",
    }
    resolution = session.scalar(
        select(models.IdentityResolution)
        .where(models.IdentityResolution.status == "ambiguous")
        .order_by(models.IdentityResolution.resolved_at.desc())
    )
    assert resolution is not None
    assert resolution.canonical_entity_id is None
    assert resolution.method == "external-identifier"
    review = session.scalar(
        select(models.IdentityReview).where(
            models.IdentityReview.resolution_id == resolution.id
        )
    )
    assert review is not None
    assert set(review.candidate_entity_ids) == {paper.id for paper in papers}


def test_update_engine_materializes_versioned_fields_and_paper_time_affiliations(
    session: Session,
    fixture_directory: Path,
) -> None:
    ensure_reference_data(session)
    session.add(
        models.Institution(
            id="institution-attribution-fixture",
            canonical_name="Attribution Fixture Institute",
            aliases=[],
            historical_names=[],
            external_ids=[{"scheme": "ror", "value": "03vek6s52"}],
            identity_confidence=1.0,
            country_id="country-us",
            city="Fixture City",
            longitude=-71.0,
            latitude=42.0,
            field_ids=["hep-th", "gr-qc"],
            provenance_json=PROVENANCE,
        )
    )
    session.add(
        models.AuthorityIdentifier(
            id="authority-attribution-fixture-institution",
            entity_type="institution",
            entity_id="institution-attribution-fixture",
            scheme="ror",
            value="03vek6s52",
            is_authoritative=True,
            provenance_json=PROVENANCE,
        )
    )
    session.commit()

    authors = [
        {
            "full_name": "Resolved, Alice",
            "recid": 71001,
            "affiliations": [
                {
                    "value": ("Department of Physics, Attribution Fixture Institute"),
                    "identifiers": [{"schema": "ROR", "value": "03vek6s52"}],
                }
            ],
        },
        {
            "full_name": "Partial, Bob",
            "recid": 71002,
            "corresponding": True,
            "affiliations": [
                {
                    "value": "Attribution Fixture Institute",
                    "identifiers": [{"schema": "ROR", "value": "03vek6s52"}],
                },
                {"value": "Unresolved Historical Laboratory"},
            ],
        },
    ]
    fixture_transport = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["inspire"].transport
    connector = SequencedAuthorityPaperConnector(
        fixture_transport,
        "https://inspire.test",
        (
            {
                "source_record_id": "920001",
                "title": "Scientific materialization fixture",
                "abstract": "Initial two-field evidence.",
                "publication_year": 2025,
                "publication_date": "2025-03-14",
                "document_type": "article",
                "external_ids": (("inspire", "920001"),),
                "field_categories": (
                    "Theory-HEP",
                    "Gravitation and Cosmology",
                ),
                "authors": authors,
            },
            {
                "source_record_id": "920001",
                "title": "Scientific materialization fixture, revised",
                "abstract": "Revised single-field evidence.",
                "publication_year": 2025,
                "publication_date": "2025-03-14",
                "document_type": "article",
                "external_ids": (("inspire", "920001"),),
                "field_categories": ("Theory-HEP",),
                "authors": authors,
            },
        ),
    )
    engine = IncrementalUpdateEngine(session, connector)

    first = engine.run()

    assert first.status == "succeeded"
    paper = session.scalar(select(models.Paper))
    assert paper is not None
    assert paper.publication_date is not None
    assert paper.publication_date.isoformat() == "2025-03-14"
    assert paper.publication_date_precision == "day"
    assert paper.document_type == "article"
    initial_field_links = list(
        session.scalars(select(models.PaperField).order_by(models.PaperField.field_id))
    )
    assert [item.field_id for item in initial_field_links] == ["gr-qc", "hep-th"]
    assert {item.weight for item in initial_field_links} == {Decimal("0.5")}
    assert {item.ontology_version for item in initial_field_links} == {
        PHYSICS_FIELD_ONTOLOGY_VERSION
    }
    assert {item.mapping_rule_version for item in initial_field_links} == {
        PROVIDER_FIELD_MAPPING_VERSION
    }
    assert {item.weighting_policy_version for item in initial_field_links} == {
        FIELD_WEIGHTING_POLICY_VERSION
    }
    assert {item.classification_role for item in initial_field_links} == {
        "primary",
        "secondary",
    }
    assert all(item.provider_categories for item in initial_field_links)

    initial_affiliations = list(
        session.scalars(
            select(models.PaperAffiliation).where(models.PaperAffiliation.is_current)
        )
    )
    assert len(initial_affiliations) == 3
    assert sum(
        (
            Fraction(
                item.attribution_weight_numerator,
                item.attribution_weight_denominator,
            )
            for item in initial_affiliations
        ),
        start=Fraction(0),
    ) == Fraction(1)
    assert sum(
        item.attribution_weight
        for item in initial_affiliations
        if item.affiliation_resolution_status == "resolved"
    ) == Decimal("0.75")
    assert [item.affiliation_resolution_status for item in initial_affiliations].count(
        "unresolved"
    ) == 1
    assert any(
        item.subunit_label == "Department of Physics, Attribution Fixture Institute"
        for item in initial_affiliations
    )
    assert all(
        evidence["numericWeightApplied"] is False
        for item in initial_affiliations
        for evidence in item.contribution_evidence
    )

    second = engine.run()

    assert second.status == "succeeded"
    current_field_links = list(session.scalars(select(models.PaperField)))
    assert len(current_field_links) == 1
    assert current_field_links[0].field_id == "hep-th"
    assert current_field_links[0].weight == Decimal("1")
    all_affiliations = list(session.scalars(select(models.PaperAffiliation)))
    assert len(all_affiliations) == 6
    assert sum(item.is_current for item in all_affiliations) == 3
    first_update = session.get_one(
        models.DatasetUpdate, f"dataset-update-{first.snapshot_id[-32:]}"
    )
    second_update = session.get_one(
        models.DatasetUpdate, f"dataset-update-{second.snapshot_id[-32:]}"
    )
    assert {item.dataset_version for item in all_affiliations if item.is_current} == {
        second_update.dataset_version
    }
    assert {
        item.dataset_version for item in all_affiliations if not item.is_current
    } == {first_update.dataset_version}


@pytest.mark.parametrize(
    "provider_categories",
    [
        (("inspire", "Theory-HEP"), ("arxiv", "gr-qc")),
        (("arxiv", "gr-qc"), ("inspire", "Theory-HEP")),
    ],
)
def test_update_engine_reconciles_one_order_independent_cross_provider_field_ledger(
    session: Session,
    fixture_directory: Path,
    provider_categories: tuple[tuple[Provider, str], tuple[Provider, str]],
) -> None:
    ensure_reference_data(session)
    fixture_transport = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["inspire"].transport
    connectors = [
        CrossProviderFieldPaperConnector(fixture_transport, provider, category)
        for provider, category in provider_categories
    ]

    for connector in connectors:
        result = IncrementalUpdateEngine(session, connector).run()
        assert result.status == "succeeded"

    field_links = list(
        session.scalars(select(models.PaperField).order_by(models.PaperField.field_id))
    )
    assert [(item.field_id, item.weight) for item in field_links] == [
        ("gr-qc", Decimal("0.5")),
        ("hep-th", Decimal("0.5")),
    ]
    paper = session.scalar(select(models.Paper))
    assert paper is not None
    ledger = paper.provenance_json["fieldMapping"]
    assert ledger["unmapped_field_mass"] == 0.0
    assert {item["provider"] for item in ledger["category_mappings"]} == {
        "arxiv",
        "inspire",
    }
    assert all(item.provenance_json["fieldMapping"] == ledger for item in field_links)

    replay = IncrementalUpdateEngine(session, connectors[-1]).run()

    assert replay.status == "succeeded"
    assert replay.idempotent_replay is True
    replayed_links = list(
        session.scalars(select(models.PaperField).order_by(models.PaperField.field_id))
    )
    assert [(item.field_id, item.weight) for item in replayed_links] == [
        ("gr-qc", Decimal("0.5")),
        ("hep-th", Decimal("0.5")),
    ]
    assert session.scalar(select(func.count()).select_from(models.PaperField)) == 2


def test_update_engine_stores_an_all_unmapped_ledger_and_deletes_stale_fields(
    session: Session,
    fixture_directory: Path,
) -> None:
    ensure_reference_data(session)
    fixture_transport = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["arxiv"].transport

    first = CrossProviderFieldPaperConnector(fixture_transport, "arxiv", "hep-th")
    assert IncrementalUpdateEngine(session, first).run().status == "succeeded"
    assert session.scalar(select(func.count()).select_from(models.PaperField)) == 1

    replacement = CrossProviderFieldPaperConnector(
        fixture_transport,
        "arxiv",
        "unknown-provider-label",
    )
    assert IncrementalUpdateEngine(session, replacement).run().status == "succeeded"

    assert session.scalar(select(func.count()).select_from(models.PaperField)) == 0
    paper = session.scalar(select(models.Paper))
    assert paper is not None
    ledger = paper.provenance_json["fieldMapping"]
    assert ledger["assignments"] == []
    assert ledger["unmapped_field_mass"] == 1.0
    assert ledger["category_mappings"][0]["category"] == "unknown-provider-label"


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
    paper_field = session.scalar(select(models.PaperField))
    paper_affiliation = session.scalar(select(models.PaperAffiliation))
    assert paper is not None
    assert authorship is not None
    assert paper_field is not None
    assert paper_affiliation is not None
    assert authorship.paper_id == paper.id
    assert paper_field.field_id == "hep-th"
    assert paper_field.weight == Decimal("1")
    assert paper_field.ontology_version == PHYSICS_FIELD_ONTOLOGY_VERSION
    assert paper_field.mapping_rule_version == PROVIDER_FIELD_MAPPING_VERSION
    assert paper_field.weighting_policy_version == FIELD_WEIGHTING_POLICY_VERSION
    assert paper_field.provider_categories[0]["category"] == "Theory-HEP"
    assert paper_affiliation.authorship_id == authorship.id
    assert paper_affiliation.affiliation_resolution_status == "missing"
    assert Fraction(
        paper_affiliation.attribution_weight_numerator,
        paper_affiliation.attribution_weight_denominator,
    ) == Fraction(1)
    assert paper_affiliation.is_current is True
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
