"""Bounded synthetic source proofs; no acquisition, files or live-data claim."""

import json
from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_launch_attribution import (
    _ROR_A,
    _author,
    _institution,
    _link,
    _lookup,
    _reference,
    _ror,
)

from physics_atlas_api import schemas
from physics_atlas_api.certification.contracts import (
    CertificationError,
    canonical_digest,
)
from physics_atlas_api.certification.fields import automatic_field_ledger
from physics_atlas_api.certification.launch_attribution import attribute_launch_record
from physics_atlas_api.certification.launch_entities import build_launch_entities
from physics_atlas_api.certification.launch_inputs import (
    canonicalize_launch_inputs,
    capture_launch_occurrence,
)
from physics_atlas_api.connectors.base import SourceRecord
from physics_atlas_api.connectors.inspire import InspireConnector


def _fixture(
    *, author_name=True, missing_id=False, missing_location=False, extra_paper=False
):  # type: ignore[no-untyped-def]
    records = tuple(
        SourceRecord(
            "inspire",
            str(index),
            {
                "control_number": index,
                "titles": [{"title": f"Synthetic source paper {index}"}],
                "preprint_date": "2020-01-09",
                "document_type": ["article"],
                "dois": [{"value": f"10.1234/synthetic-{index}"}],
                "inspire_categories": [{"term": "Theory-Nucl"}],
                "authors": [
                    _author(
                        123,
                        [_link("200")] if index == 1 else [],
                        **({"full_name": "Synthetic Author"} if author_name else {}),
                        **({"recid": None} if missing_id else {}),
                    )
                ],
            },
        )
        for index in ((1, 2) if extra_paper else (1,))
    )
    occurrences = tuple(
        capture_launch_occurrence(
            record,
            reference=_reference(record),
            connector=InspireConnector(Mock(), "https://inspirehep.net/api"),
            dataset_version="test-only-launch-ui-v1",
        )
        for record in records
    )
    ror = _ror(
        _ROR_A,
        locations=[
            {
                "geonames_details": {
                    "country_code": "US",
                    "name": "Boston",
                    **({} if missing_location else {"lat": 42.36, "lng": -71.06}),
                }
            }
        ],
    )
    attributions = tuple(
        attribute_launch_record(
            record,
            reference=occurrence.reference,
            source_facts=occurrence.source_facts,
            institution_lookup=_lookup((_institution("200", _ROR_A),)),
            ror_lookup=_lookup((ror,)),
        )
        for record, occurrence in zip(records, occurrences, strict=True)
    )
    return canonicalize_launch_inputs(occurrences).papers, attributions


def _build(**changes):  # type: ignore[no-untyped-def]
    papers, attributions = _fixture(**changes)
    return build_launch_entities(papers, attributions, geographic_views=())


def test_all_captured_source_profiles_and_exact_paper_time_links_are_preserved() -> (
    None
):
    built = _build(extra_paper=True)
    entities = built.entities
    assert len(entities.papers) == len(entities.authorships) == 2
    assert len(entities.affiliations) == len(entities.institutions) == 1
    assert len(entities.researchers) == 1
    researcher = entities.researchers[0]
    institution = entities.institutions[0]
    assert researcher.id == "inspire-author:123"
    assert institution.id == f"institution-ror-{_ROR_A}"
    assert institution.country_id == "country-us"
    assert institution.location == schemas.InstitutionLocation(
        longitude=-71.06, latitude=42.36
    )
    assert institution.name == "Example University"
    assert institution.field_ids == researcher.field_ids == ["nucl-th"]
    affiliation = entities.affiliations[0]
    assert affiliation.paper_id == next(
        item.id for item in entities.papers if item.title.endswith("1")
    )
    assert affiliation.start_date == affiliation.end_date == "2020-01-09"
    assert "not current or continuous employment" in (affiliation.source or "")
    assert not entities.research_groups and not entities.historical_events
    assert all(not resource.verified for resource in entities.external_resources)
    assert {item.provider for item in built.source_references} == {"inspire", "ror"}
    assert all(item.checksum for item in built.source_references)
    assert not built.omitted_counts


def test_size_and_order_are_deterministic_without_truncating_papers() -> None:
    papers, attributions = _fixture(extra_paper=True)
    first = build_launch_entities(papers, attributions, geographic_views=())
    second = build_launch_entities(
        tuple(reversed(papers)), tuple(reversed(attributions)), geographic_views=()
    )
    assert first == second
    payload = first.entities.model_dump(mode="json", by_alias=True, exclude_none=True)
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    assert first.byte_length == len(raw)
    assert dict(first.entity_counts)["papers"] == 2
    assert all(
        item["provenance"]["sourceType"] != "synthetic-demo"
        for collection in payload.values()
        for item in collection
    )


@pytest.mark.parametrize("missing", ["missing_id", "author_name"])
def test_missing_identity_or_name_does_not_invent_a_researcher(missing: str) -> None:
    built = _build(**{missing: missing == "missing_id"})
    assert built.entities.papers and built.entities.institutions
    assert not built.entities.researchers
    assert not built.entities.authorships and not built.entities.affiliations
    assert built.omitted_counts


def test_missing_coordinate_keeps_profile_without_an_invented_map_node() -> None:
    built = _build(missing_location=True)
    assert len(built.entities.institutions) == 1
    assert built.entities.institutions[0].location is None
    assert (
        dict(built.omitted_counts)["institution_without_single_supported_map_position"]
        == 1
    )


def test_supplied_geographic_policy_does_not_change_research_location_attribution() -> (
    None
):
    papers, attributions = _fixture()
    view = schemas.GeographicViewOut(
        id="geography-china",
        country_id="country-cn",
        geometry_iso_numerics=["156", "158"],
        location_country_ids=["country-cn", "country-tw"],
        provenance=schemas.Provenance(
            source="Existing geographic rendering policy",
            source_type="derived",
            version="geography-v1",
            status="verified",
        ),
    )
    built = build_launch_entities(papers, attributions, geographic_views=(view,))
    assert built.entities.geographic_views == [view]
    assert built.entities.institutions[0].country_id == "country-us"
    assert "country-tw" in {item.id for item in built.entities.countries}
    invalid = view.model_copy(update={"id": "duplicate"})
    with pytest.raises(CertificationError, match="geographic"):
        build_launch_entities(papers, attributions, geographic_views=(view, invalid))


def test_reference_inventory_and_certified_fractions_are_independently_checked() -> (
    None
):
    papers, attributions = _fixture()
    with pytest.raises(CertificationError, match="inventory"):
        build_launch_entities(papers, (), geographic_views=())
    changed = replace(attributions[0], paper_time_affiliation_weight=None)
    with pytest.raises(CertificationError, match="attribution"):
        build_launch_entities(papers, (changed,), geographic_views=())


def test_legacy_affiliations_do_not_acquire_paper_time_semantics() -> None:
    affiliation = _build().entities.affiliations[0]
    payload = affiliation.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert payload["paperId"] == affiliation.paper_id
    payload.pop("paperId")
    assert schemas.AffiliationOut.model_validate(payload).paper_id is None


def test_ui_projection_cannot_change_certification_or_conservation() -> None:
    papers, attributions = _fixture(extra_paper=True)
    before = canonical_digest((papers, attributions))
    built = build_launch_entities(papers, attributions, geographic_views=())
    assert canonical_digest((papers, attributions)) == before
    assert all(
        automatic_field_ledger(item.field_evidence).conservation_total == 1
        for item in papers
    )
    assert all(
        item.fractional and item.fractional.total_weight == 1 for item in attributions
    )
    assert len(built.entities.papers) == len(papers)
    assert "metricObservations" not in built.entities.model_dump(by_alias=True)
