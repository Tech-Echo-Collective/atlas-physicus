from datetime import UTC, datetime
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import Session

from physics_atlas_api import models
from physics_atlas_api.attribution.materialization import (
    MATERIALIZATION_VERSION,
    MaterializedAuthorIdentity,
    materialize_paper_time_affiliations,
)
from physics_atlas_api.connectors.base import NormalizedRecord


def _snapshot(session: Session, snapshot_id: str) -> None:
    session.add(
        models.SourceSnapshot(
            id=snapshot_id,
            source="inspire",
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


def _record() -> NormalizedRecord:
    return NormalizedRecord(
        provider="inspire",
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
