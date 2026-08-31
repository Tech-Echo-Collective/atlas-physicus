from datetime import UTC, datetime
from fractions import Fraction

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from physics_atlas_api import models
from physics_atlas_api.attribution.materialization import (
    AFFILIATION_EVIDENCE_PRECEDENCE_VERSION,
    MATERIALIZATION_VERSION,
    MaterializedAuthorIdentity,
    materialize_paper_time_affiliations,
)
from physics_atlas_api.connectors.base import NormalizedRecord


def _snapshot(session: Session, snapshot_id: str, *, source: str = "inspire") -> None:
    session.add(
        models.SourceSnapshot(
            id=snapshot_id,
            source=source,
            source_version="fixture-v1",
            captured_at=datetime(2026, 8, 30, tzinfo=UTC),
            update_mode="incremental",
            record_count=1,
            previous_snapshot_id=None,
            content_checksum=snapshot_id,
            storage_reference=None,
            raw_payload=[],
            provenance_json={"source": "fixture"},
        )
    )


def _seed_linked_entities(session: Session) -> None:
    session.add(
        models.Country(
            id="country-us",
            iso_alpha3="USA",
            iso_alpha2="US",
            iso_numeric="840",
            name="United States",
            region="Global",
            provenance_json={"source": "fixture"},
        )
    )
    for institution_id, name, ror in (
        ("institution-a", "Institution A", "03vek6s52"),
        ("institution-b", "Institution B", "00hx57361"),
    ):
        session.add(
            models.Institution(
                id=institution_id,
                canonical_name=name,
                aliases=[],
                historical_names=[],
                external_ids=[{"scheme": "ror", "value": ror}],
                identity_confidence=1.0,
                country_id="country-us",
                city="Test City",
                longitude=0,
                latitude=0,
                field_ids=["hep-th"],
                provenance_json={"source": "fixture"},
            )
        )
        session.add(
            models.AuthorityIdentifier(
                id=f"authority-{institution_id}",
                entity_type="institution",
                entity_id=institution_id,
                scheme="ror",
                value=ror,
                is_authoritative=True,
                provenance_json={"source": "fixture"},
            )
        )
    for position in (1, 2):
        researcher_id = f"researcher-{position}"
        authorship_id = f"authorship-{position}"
        session.add(
            models.Researcher(
                id=researcher_id,
                canonical_name=f"Researcher {position}",
                aliases=[],
                historical_names=[],
                external_ids=[],
                identity_confidence=1.0,
                field_ids=["hep-th"],
                provenance_json={"source": "fixture"},
            )
        )
        session.add(
            models.Authorship(
                id=authorship_id,
                paper_id="paper-1",
                researcher_id=researcher_id,
                author_position=position,
                provenance_json={"source": "fixture"},
            )
        )


def _record(*, provider: str = "inspire") -> NormalizedRecord:
    return NormalizedRecord(
        provider=provider,
        kind="paper",
        source_record_id="1001",
        canonical_name="Paper-time attribution fixture",
        external_ids=(("inspire", "1001"),),
        attributes={
            "authors": [
                {
                    "full_name": "Researcher, One",
                    "affiliations": [
                        {
                            "value": "Department Alpha, Institution A",
                            "identifiers": [{"schema": "ROR", "value": "03vek6s52"}],
                        }
                    ],
                },
                {
                    "full_name": "Researcher, Two",
                    "corresponding": True,
                    "affiliations": [
                        {
                            "value": "Institution B",
                            "identifiers": [{"schema": "ROR", "value": "00hx57361"}],
                        },
                        {"value": "Unresolved Historical Laboratory"},
                    ],
                },
            ]
        },
        raw={},
        provenance={
            "source": "fixture",
            "sourceType": "synthetic-demo",
            "version": "fixture-v1",
            "status": "synthetic",
        },
    )


def test_materializes_conserved_paper_time_shares_and_withheld_mass(
    session: Session,
) -> None:
    session.add(
        models.Paper(
            id="paper-1",
            title="Paper-time attribution fixture",
            summary="",
            publication_year=2025,
            publication_date=None,
            publication_date_precision=None,
            document_type="article",
            doi=None,
            arxiv_id=None,
            external_ids=[],
            provenance_json={"source": "fixture"},
        )
    )
    _seed_linked_entities(session)
    _snapshot(session, "snapshot-1")
    session.flush()

    identities = {
        position: MaterializedAuthorIdentity(
            author_position=position,
            raw_author_name=f"Researcher {position}",
            researcher_id=f"researcher-{position}",
            authorship_id=f"authorship-{position}",
            resolution_status="resolved",
        )
        for position in (1, 2)
    }
    result = materialize_paper_time_affiliations(
        session,
        record=_record(),
        paper_id="paper-1",
        source_snapshot_id="snapshot-1",
        dataset_version="dataset-1",
        author_identities=identities,
    )
    session.flush()

    assert result.total_weight == Fraction(1)
    assert result.allocated_weight == Fraction(3, 4)
    assert result.withheld_weight == Fraction(1, 4)
    rows = list(
        session.scalars(
            select(models.PaperAffiliation).order_by(
                models.PaperAffiliation.author_position,
                models.PaperAffiliation.id,
            )
        )
    )
    exact_total = sum(
        (
            Fraction(
                row.attribution_weight_numerator,
                row.attribution_weight_denominator,
            )
            for row in rows
        ),
        start=Fraction(0),
    )
    assert exact_total == Fraction(1)
    assert [row.affiliation_resolution_status for row in rows].count("resolved") == 2
    assert [row.affiliation_resolution_status for row in rows].count("unresolved") == 1
    institution_a_row = next(
        row for row in rows if row.institution_id == "institution-a"
    )
    assert institution_a_row.subunit_label == "Department Alpha, Institution A"
    contribution_row = next(row for row in rows if row.author_position == 2)
    assert contribution_row.contribution_evidence[0]["numericWeightApplied"] is False
    assert contribution_row.materialization_version == MATERIALIZATION_VERSION


def test_raw_affiliation_is_preserved_as_unresolved_historical_evidence(
    session: Session,
) -> None:
    session.add(
        models.Paper(
            id="paper-1",
            title="Paper-time attribution fixture",
            summary="",
            publication_year=2025,
            publication_date=None,
            publication_date_precision=None,
            document_type="article",
            doi=None,
            arxiv_id=None,
            external_ids=[],
            provenance_json={"source": "fixture"},
        )
    )
    _seed_linked_entities(session)
    _snapshot(session, "snapshot-raw")
    session.flush()
    record = _record()
    first_author = record.attributes["authors"][0]
    first_author["affiliations"] = []
    first_author["raw_affiliations"] = [
        {"value": "Historical laboratory without an authority identifier"}
    ]

    materialize_paper_time_affiliations(
        session,
        record=record,
        paper_id="paper-1",
        source_snapshot_id="snapshot-raw",
        dataset_version="dataset-raw",
        author_identities={},
    )
    session.flush()

    row = session.scalar(
        select(models.PaperAffiliation).where(
            models.PaperAffiliation.author_position == 1
        )
    )
    assert row is not None
    assert row.raw_affiliation == (
        "Historical laboratory without an authority identifier"
    )
    assert row.affiliation_resolution_status == "unresolved"
    assert row.institution_id is None


def test_single_author_level_ror_aligns_only_to_one_effective_affiliation(
    session: Session,
) -> None:
    session.add(
        models.Paper(
            id="paper-1",
            title="Paper-time attribution fixture",
            summary="",
            publication_year=2025,
            publication_date=None,
            publication_date_precision=None,
            document_type="article",
            doi=None,
            arxiv_id=None,
            external_ids=[],
            provenance_json={"source": "fixture"},
        )
    )
    _seed_linked_entities(session)
    _snapshot(session, "snapshot-author-ror")
    session.flush()
    record = _record()
    first_author = record.attributes["authors"][0]
    first_author["affiliations"] = [{"value": "A historical subunit"}]
    first_author["affiliations_identifiers"] = [
        {"schema": "GRID", "value": "grid.fixture"},
        {"schema": "ROR", "value": "https://ror.org/03vek6s52"},
    ]

    materialize_paper_time_affiliations(
        session,
        record=record,
        paper_id="paper-1",
        source_snapshot_id="snapshot-author-ror",
        dataset_version="dataset-author-ror",
        author_identities={},
    )
    session.flush()

    row = session.scalar(
        select(models.PaperAffiliation).where(
            models.PaperAffiliation.author_position == 1
        )
    )
    assert row is not None
    assert row.affiliation_resolution_status == "resolved"
    assert row.institution_id == "institution-a"


def test_multi_affiliation_author_level_identifiers_are_not_positionally_zipped(
    session: Session,
) -> None:
    session.add(
        models.Paper(
            id="paper-1",
            title="Paper-time attribution fixture",
            summary="",
            publication_year=2025,
            publication_date=None,
            publication_date_precision=None,
            document_type="article",
            doi=None,
            arxiv_id=None,
            external_ids=[],
            provenance_json={"source": "fixture"},
        )
    )
    _seed_linked_entities(session)
    _snapshot(session, "snapshot-multi-ror")
    session.flush()
    record = _record()
    first_author = record.attributes["authors"][0]
    first_author["affiliations"] = [
        {"value": "Historical subunit one"},
        {"value": "Historical subunit two"},
    ]
    first_author["affiliations_identifiers"] = [
        {"schema": "ROR", "value": "03vek6s52"},
        {"schema": "ROR", "value": "00hx57361"},
    ]

    materialize_paper_time_affiliations(
        session,
        record=record,
        paper_id="paper-1",
        source_snapshot_id="snapshot-multi-ror",
        dataset_version="dataset-multi-ror",
        author_identities={},
    )
    session.flush()

    rows = list(
        session.scalars(
            select(models.PaperAffiliation).where(
                models.PaperAffiliation.author_position == 1
            )
        )
    )
    assert len(rows) == 2
    assert {row.affiliation_resolution_status for row in rows} == {"unresolved"}
    assert {row.institution_id for row in rows} == {None}


def test_exact_name_fallback_rejects_non_ror_canonical_institution(
    session: Session,
) -> None:
    session.add(
        models.Paper(
            id="paper-1",
            title="Paper-time attribution fixture",
            summary="",
            publication_year=2025,
            publication_date=None,
            publication_date_precision=None,
            document_type="article",
            doi=None,
            arxiv_id=None,
            external_ids=[],
            provenance_json={"source": "fixture"},
        )
    )
    _seed_linked_entities(session)
    session.add(
        models.Institution(
            id="institution-unbacked",
            canonical_name="Unbacked Historical Institute",
            aliases=[],
            historical_names=[],
            external_ids=[],
            identity_confidence=None,
            country_id="country-us",
            city="Test City",
            longitude=None,
            latitude=None,
            field_ids=[],
            provenance_json={"source": "fixture"},
        )
    )
    session.add(
        models.EntitySearchTerm(
            id="search-institution-unbacked",
            entity_type="institution",
            entity_id="institution-unbacked",
            term="Unbacked Historical Institute",
            normalized_term="unbacked historical institute",
            match_method="canonical-name",
        )
    )
    _snapshot(session, "snapshot-unbacked")
    session.flush()
    record = _record()
    record.attributes["authors"][0]["affiliations"] = [
        {"value": "Unbacked Historical Institute"}
    ]

    materialize_paper_time_affiliations(
        session,
        record=record,
        paper_id="paper-1",
        source_snapshot_id="snapshot-unbacked",
        dataset_version="dataset-unbacked",
        author_identities={},
    )
    session.flush()

    row = session.scalar(
        select(models.PaperAffiliation).where(
            models.PaperAffiliation.author_position == 1
        )
    )
    assert row is not None
    assert row.affiliation_resolution_status == "unresolved"
    assert row.institution_id is None


def test_new_snapshot_supersedes_projection_without_erasing_history(
    session: Session,
) -> None:
    test_materializes_conserved_paper_time_shares_and_withheld_mass(session)
    _snapshot(session, "snapshot-2")
    materialize_paper_time_affiliations(
        session,
        record=_record(),
        paper_id="paper-1",
        source_snapshot_id="snapshot-2",
        dataset_version="dataset-2",
        author_identities={
            position: MaterializedAuthorIdentity(
                author_position=position,
                raw_author_name=f"Researcher {position}",
                researcher_id=f"researcher-{position}",
                authorship_id=f"authorship-{position}",
                resolution_status="resolved",
            )
            for position in (1, 2)
        },
    )
    session.flush()

    rows = list(session.scalars(select(models.PaperAffiliation)))
    assert len(rows) == 6
    assert sum(row.is_current for row in rows) == 3
    assert {row.dataset_version for row in rows if row.is_current} == {"dataset-2"}
    assert {row.dataset_version for row in rows if not row.is_current} == {"dataset-1"}


def test_lower_precedence_provider_does_not_replace_inspire_projection(
    session: Session,
) -> None:
    session.add(
        models.Paper(
            id="paper-1",
            title="Paper-time attribution fixture",
            summary="",
            publication_year=2025,
            publication_date=None,
            publication_date_precision=None,
            document_type="article",
            doi=None,
            arxiv_id=None,
            external_ids=[],
            provenance_json={"source": "fixture"},
        )
    )
    _seed_linked_entities(session)
    _snapshot(session, "snapshot-inspire")
    _snapshot(session, "snapshot-arxiv", source="arxiv")
    session.flush()
    identities = {
        position: MaterializedAuthorIdentity(
            author_position=position,
            raw_author_name=f"Researcher {position}",
            researcher_id=f"researcher-{position}",
            authorship_id=f"authorship-{position}",
            resolution_status="resolved",
        )
        for position in (1, 2)
    }

    materialize_paper_time_affiliations(
        session,
        record=_record(),
        paper_id="paper-1",
        source_snapshot_id="snapshot-inspire",
        dataset_version="dataset-inspire",
        author_identities=identities,
    )
    materialize_paper_time_affiliations(
        session,
        record=_record(provider="arxiv"),
        paper_id="paper-1",
        source_snapshot_id="snapshot-arxiv",
        dataset_version="dataset-arxiv",
        author_identities=identities,
    )
    session.flush()

    rows = list(session.scalars(select(models.PaperAffiliation)))
    current_rows = [row for row in rows if row.is_current]
    superseded_rows = [row for row in rows if not row.is_current]
    assert len(rows) == 6
    assert {row.provider for row in current_rows} == {"inspire"}
    assert {row.dataset_version for row in current_rows} == {"dataset-inspire"}
    assert {row.provider for row in superseded_rows} == {"arxiv"}
    assert all(
        row.provenance_json["affiliationEvidencePrecedenceVersion"]
        == AFFILIATION_EVIDENCE_PRECEDENCE_VERSION
        for row in rows
    )
    assert all(
        row.provenance_json["selectedAsCurrentProjection"] is False
        for row in superseded_rows
    )


def test_current_profile_source_is_rejected_for_paper_time_history(
    session: Session,
) -> None:
    with pytest.raises(
        ValueError, match="not an approved paper-time affiliation provider"
    ):
        materialize_paper_time_affiliations(
            session,
            record=_record(provider="homepage"),
            paper_id="paper-1",
            source_snapshot_id="snapshot-homepage",
            dataset_version="dataset-homepage",
            author_identities={},
        )


def test_orcid_cannot_become_a_paper_time_projection_without_dated_cross_check(
    session: Session,
) -> None:
    with pytest.raises(
        ValueError, match="not an approved paper-time affiliation provider"
    ):
        materialize_paper_time_affiliations(
            session,
            record=_record(provider="orcid"),
            paper_id="paper-1",
            source_snapshot_id="snapshot-orcid",
            dataset_version="dataset-orcid",
            author_identities={},
        )


def test_partial_cross_provider_evidence_cannot_erase_resolved_author_slots(
    session: Session,
) -> None:
    session.add(
        models.Paper(
            id="paper-1",
            title="Paper-time attribution fixture",
            summary="",
            publication_year=2025,
            publication_date=None,
            publication_date_precision=None,
            document_type="article",
            doi=None,
            arxiv_id=None,
            external_ids=[],
            provenance_json={"source": "fixture"},
        )
    )
    _seed_linked_entities(session)
    _snapshot(session, "snapshot-inspire")
    _snapshot(session, "snapshot-crossref", source="crossref")
    session.flush()
    identities = {
        position: MaterializedAuthorIdentity(
            author_position=position,
            raw_author_name=f"Researcher {position}",
            researcher_id=f"researcher-{position}",
            authorship_id=f"authorship-{position}",
            resolution_status="resolved",
        )
        for position in (1, 2)
    }
    materialize_paper_time_affiliations(
        session,
        record=_record(),
        paper_id="paper-1",
        source_snapshot_id="snapshot-inspire",
        dataset_version="dataset-inspire",
        author_identities=identities,
    )
    partial = _record(provider="crossref")
    partial.attributes["authors"][1]["affiliations"] = []
    materialize_paper_time_affiliations(
        session,
        record=partial,
        paper_id="paper-1",
        source_snapshot_id="snapshot-crossref",
        dataset_version="dataset-crossref",
        author_identities=identities,
    )
    session.flush()

    rows = list(session.scalars(select(models.PaperAffiliation)))
    current_rows = [row for row in rows if row.is_current]
    partial_rows = [row for row in rows if row.provider == "crossref"]
    assert {(row.author_position, row.provider) for row in current_rows} == {
        (1, "crossref"),
        (2, "inspire"),
        (2, "inspire"),
    }
    assert {row.author_position for row in current_rows} == {1, 2}
    assert {row.author_position for row in partial_rows if row.is_current} == {1}
    assert {row.author_position for row in partial_rows if not row.is_current} == {2}
    assert all(
        row.provenance_json["crossProviderEvidenceLossPrevented"] is True
        for row in partial_rows
    )


def test_equal_precedence_conflict_is_withheld_without_erasing_sources(
    session: Session,
) -> None:
    session.add(
        models.Paper(
            id="paper-1",
            title="Paper-time attribution fixture",
            summary="",
            publication_year=2025,
            publication_date=None,
            publication_date_precision=None,
            document_type="article",
            doi=None,
            arxiv_id=None,
            external_ids=[],
            provenance_json={"source": "fixture"},
        )
    )
    _seed_linked_entities(session)
    _snapshot(session, "snapshot-inspire")
    _snapshot(session, "snapshot-crossref", source="crossref")
    session.flush()
    identities = {
        position: MaterializedAuthorIdentity(
            author_position=position,
            raw_author_name=f"Researcher {position}",
            researcher_id=f"researcher-{position}",
            authorship_id=f"authorship-{position}",
            resolution_status="resolved",
        )
        for position in (1, 2)
    }
    materialize_paper_time_affiliations(
        session,
        record=_record(),
        paper_id="paper-1",
        source_snapshot_id="snapshot-inspire",
        dataset_version="dataset-inspire",
        author_identities=identities,
    )
    crossref_record = _record(provider="crossref")
    crossref_record.attributes["authors"][0]["affiliations"][0]["identifiers"] = [
        {"schema": "ROR", "value": "00hx57361"}
    ]
    result = materialize_paper_time_affiliations(
        session,
        record=crossref_record,
        paper_id="paper-1",
        source_snapshot_id="snapshot-crossref",
        dataset_version="dataset-crossref",
        author_identities=identities,
    )
    session.flush()

    rows = list(session.scalars(select(models.PaperAffiliation)))
    current_rows = [row for row in rows if row.is_current]
    historical_rows = [row for row in rows if not row.is_current]
    conflicting_rows = [row for row in current_rows if row.author_position == 1]
    assert result.allocated_weight == Fraction(1, 4)
    assert result.withheld_weight == Fraction(3, 4)
    assert {row.provider for row in current_rows} == {"crossref"}
    assert {row.provider for row in historical_rows} == {"inspire"}
    assert len(conflicting_rows) == 1
    assert conflicting_rows[0].affiliation_resolution_status == "unresolved"
    assert conflicting_rows[0].institution_id is None
    assert conflicting_rows[0].resolution_evidence[-1] == {
        "method": "cross-provider-affiliation-precedence",
        "status": "unresolved-conflict",
        "providers": ["crossref", "inspire"],
        "version": AFFILIATION_EVIDENCE_PRECEDENCE_VERSION,
    }


def test_higher_precedence_conflict_stays_unresolved_without_dated_evidence(
    session: Session,
) -> None:
    session.add(
        models.Paper(
            id="paper-1",
            title="Paper-time attribution fixture",
            summary="",
            publication_year=2025,
            publication_date=None,
            publication_date_precision=None,
            document_type="article",
            doi=None,
            arxiv_id=None,
            external_ids=[],
            provenance_json={"source": "fixture"},
        )
    )
    _seed_linked_entities(session)
    _snapshot(session, "snapshot-arxiv", source="arxiv")
    _snapshot(session, "snapshot-inspire")
    session.flush()
    identities = {
        position: MaterializedAuthorIdentity(
            author_position=position,
            raw_author_name=f"Researcher {position}",
            researcher_id=f"researcher-{position}",
            authorship_id=f"authorship-{position}",
            resolution_status="resolved",
        )
        for position in (1, 2)
    }
    materialize_paper_time_affiliations(
        session,
        record=_record(provider="arxiv"),
        paper_id="paper-1",
        source_snapshot_id="snapshot-arxiv",
        dataset_version="dataset-arxiv",
        author_identities=identities,
    )
    conflicting_inspire = _record()
    conflicting_inspire.attributes["authors"][0]["affiliations"][0]["identifiers"] = [
        {"schema": "ROR", "value": "00hx57361"}
    ]

    result = materialize_paper_time_affiliations(
        session,
        record=conflicting_inspire,
        paper_id="paper-1",
        source_snapshot_id="snapshot-inspire",
        dataset_version="dataset-inspire",
        author_identities=identities,
    )
    session.flush()

    current_conflict = session.scalar(
        select(models.PaperAffiliation).where(
            models.PaperAffiliation.is_current,
            models.PaperAffiliation.author_position == 1,
        )
    )
    assert current_conflict is not None
    assert current_conflict.provider == "inspire"
    assert current_conflict.affiliation_resolution_status == "unresolved"
    assert current_conflict.institution_id is None
    assert current_conflict.provenance_json["crossProviderConflictUnresolved"] is True
    assert result.withheld_weight == Fraction(3, 4)


def test_lower_precedence_conflict_does_not_replace_nonconflicting_stronger_slot(
    session: Session,
) -> None:
    session.add(
        models.Paper(
            id="paper-1",
            title="Paper-time attribution fixture",
            summary="",
            publication_year=2025,
            publication_date=None,
            publication_date_precision=None,
            document_type="article",
            doi=None,
            arxiv_id=None,
            external_ids=[],
            provenance_json={"source": "fixture"},
        )
    )
    _seed_linked_entities(session)
    _snapshot(session, "snapshot-inspire")
    _snapshot(session, "snapshot-arxiv", source="arxiv")
    session.flush()
    identities = {
        position: MaterializedAuthorIdentity(
            author_position=position,
            raw_author_name=f"Researcher {position}",
            researcher_id=f"researcher-{position}",
            authorship_id=f"authorship-{position}",
            resolution_status="resolved",
        )
        for position in (1, 2)
    }
    materialize_paper_time_affiliations(
        session,
        record=_record(),
        paper_id="paper-1",
        source_snapshot_id="snapshot-inspire",
        dataset_version="dataset-inspire",
        author_identities=identities,
    )
    conflicting_arxiv = _record(provider="arxiv")
    conflicting_arxiv.attributes["authors"][0]["affiliations"][0]["identifiers"] = [
        {"schema": "ROR", "value": "00hx57361"}
    ]
    materialize_paper_time_affiliations(
        session,
        record=conflicting_arxiv,
        paper_id="paper-1",
        source_snapshot_id="snapshot-arxiv",
        dataset_version="dataset-arxiv",
        author_identities=identities,
    )
    session.flush()

    current_rows = list(
        session.scalars(
            select(models.PaperAffiliation).where(models.PaperAffiliation.is_current)
        )
    )
    conflicting_rows = [row for row in current_rows if row.author_position == 1]
    nonconflicting_rows = [row for row in current_rows if row.author_position == 2]
    assert len(conflicting_rows) == 1
    assert conflicting_rows[0].provider == "arxiv"
    assert conflicting_rows[0].affiliation_resolution_status == "unresolved"
    assert {row.provider for row in nonconflicting_rows} == {"inspire"}
    assert {
        Fraction(row.attribution_weight_numerator, row.attribution_weight_denominator)
        for row in current_rows
    } == {Fraction(1, 2), Fraction(1, 4)}
    assert (
        sum(
            (
                Fraction(
                    row.attribution_weight_numerator,
                    row.attribution_weight_denominator,
                )
                for row in current_rows
            ),
            start=Fraction(0),
        )
        == 1
    )
