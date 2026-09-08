"""Synthetic exact-identifier crosswalk; no scientific source acquisition."""

import json
from datetime import UTC, datetime
from fractions import Fraction
from unittest.mock import Mock

import pytest
from test_launch_attribution import (
    _ROR_A,
    _author,
    _link,
    _paper,
    _reference,
    _ror,
    _run,
)

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.ror_grid_crosswalk import (
    ROR_GRID_CROSSWALK_VERSION,
    capture_ror_grid_crosswalk,
    inspire_grid_id,
    ror_grid_request_uri,
)
from physics_atlas_api.connectors.base import SourceRecord

GRID = "grid.12345.a"
NOW = datetime(2026, 9, 8, tzinfo=UTC)


def institution(**changes):
    return SourceRecord(
        "inspire",
        "200",
        {
            "control_number": 200,
            "external_system_identifiers": [{"schema": "GRID", "value": GRID}],
            "addresses": [{"country_code": "US"}],
            **changes,
        },
    )


def crosswalk(source=None, *, payload=None, **changes):
    source = source or institution()
    ror = _ror(
        _ROR_A,
        external_ids=[{"type": "grid", "all": [GRID], "preferred": GRID}],
        **changes,
    )
    return capture_ror_grid_crosswalk(
        institution_record=source,
        institution_reference=_reference(source),
        response_payload=json.dumps(
            payload
            if payload is not None
            else {"number_of_results": 1, "items": [ror.raw]}
        ).encode(),
        request_uri=ror_grid_request_uri(GRID),
        requested_at=NOW,
        received_at=NOW,
        source_snapshot_id="synthetic-grid-response-v1",
    )


def test_exact_grid_crosswalk_preserves_fraction_and_independent_provenance():
    source = institution()
    match = crosswalk(source)
    paper = _paper([_author(1, [_link("200")]), _author(2)])
    result = _run(
        paper,
        institutions=(source,),
        grid_match=lambda record, reference: match,
    )
    assert result.fractional.allocated_weight == Fraction(1, 2)
    assert result.fractional.withheld_weight == Fraction(1, 2)
    assert result.fractional.total_weight == 1
    resolved = result.affiliations[0]
    assert resolved.state == "certified"
    assert resolved.institution.match_method == ROR_GRID_CROSSWALK_VERSION
    assert resolved.institution.evidence.direct_ror_ids == (_ROR_A,)
    assert resolved.institution.canonical_institution_id == f"institution-ror-{_ROR_A}"
    assert set(resolved.evidence) == {
        _reference(paper),
        _reference(source),
        match.receipt.response_reference,
        match.ror_reference,
    }
    assert "all_status=true" in match.receipt.request_uri


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"status": "inactive"}, "needs_review"),
        ({"established": 2021}, "insufficient_evidence"),
        (
            {
                "relationships": [
                    {"id": "https://ror.org/05vt9qd57", "type": "successor"}
                ]
            },
            "insufficient_evidence",
        ),
    ],
)
def test_identifier_crosswalk_does_not_override_lifecycle_rules(changes, expected):
    match = crosswalk(**changes)
    result = _run(
        _paper([_author(1, [_link("200")])]),
        institutions=(institution(),),
        grid_match=lambda *_: match,
    )
    assert result.affiliations[0].state == expected
    assert result.fractional.withheld_weight == 1


def test_exact_grid_with_conflicting_country_remains_withheld():
    source = institution(addresses=[{"country_code": "FR"}])
    match = crosswalk(source)
    result = _run(
        _paper([_author(1, [_link("200")])]),
        institutions=(source,),
        grid_match=lambda *_: match,
    )
    assert result.affiliations[0].state == "conflicted"
    assert result.affiliations[0].reasons == ("grid-authority-country-conflict",)
    assert result.fractional.withheld_weight == 1


def test_missing_mapping_is_unknown_and_ambiguous_mapping_never_selects_first():
    assert crosswalk(payload={"number_of_results": 0, "items": []}) is None
    ror = _ror(_ROR_A, external_ids=[{"type": "grid", "all": [GRID]}])
    for payload in (
        {"number_of_results": 2, "items": [ror.raw, ror.raw]},
        {"number_of_results": 2, "items": [ror.raw]},
        {"number_of_results": 1, "items": []},
        {"number_of_results": True, "items": [ror.raw]},
    ):
        with pytest.raises(CertificationError):
            crosswalk(payload=payload)
    with pytest.raises(CertificationError):
        crosswalk(payload={"number_of_results": 1, "items": [_ror(_ROR_A).raw]})


def test_source_ids_are_not_names_and_unbound_lookup_cannot_transfer_identity():
    assert inspire_grid_id(institution(external_system_identifiers=[])) is None
    with pytest.raises(CertificationError):
        ror_grid_request_uri("Synthetic University")
    with pytest.raises(CertificationError):
        inspire_grid_id(
            institution(
                external_system_identifiers=[
                    {"schema": "GRID", "value": GRID},
                    {"schema": "GRID", "value": "grid.99999.b"},
                ]
            )
        )
    match = crosswalk()
    other = institution(addresses=[])
    result = _run(
        _paper([_author(1, [_link("200")])]),
        institutions=(other,),
        grid_match=lambda *_: match,
    )
    assert result.affiliations[0].state == "conflicted"


def test_existing_direct_ror_path_does_not_use_crosswalk_fallback():
    source = institution(
        external_system_identifiers=[{"schema": "ROR", "value": _ROR_A}]
    )
    lookup = Mock(side_effect=AssertionError("unnecessary fallback"))
    result = _run(
        _paper([_author(1, [_link("200")])]),
        institutions=(source,),
        rors=(_ror(_ROR_A),),
        grid_match=lookup,
    )
    assert result.fractional.allocated_weight == 1
    lookup.assert_not_called()
