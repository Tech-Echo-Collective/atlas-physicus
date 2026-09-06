"""Synthetic ROR responses: no provider access and no live-certification claim."""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest

from physics_atlas_api.certification.contracts import (
    CertificationError,
    EvidenceReference,
)
from physics_atlas_api.certification.ror_affiliation_match import (
    MAXIMUM_ROR_MATCH_BYTES,
    ROR_AFFILIATION_MATCH_VERSION,
    certify_paper_raw_affiliation_match,
    ror_affiliation_reference_id,
    ror_affiliation_request_uri,
)
from physics_atlas_api.connectors.base import SourceRecord

_RAW = "Department of Physics, Example University, Boston, United States"
_TIME = datetime(2026, 9, 5, 12, tzinfo=UTC)


def _organization(**changes):  # type: ignore[no-untyped-def]
    value = {
        "id": "https://ror.org/02vwzrd76",
        "names": [
            {"value": "Example University", "types": ["ror_display", "label"]},
            {"value": "EU", "types": ["acronym"]},
        ],
        "status": "active",
        "established": 1900,
        "relationships": [],
        "locations": [
            {
                "geonames_details": {
                    "country_code": "US",
                    "country_name": "United States",
                    "name": "Boston",
                }
            }
        ],
    }
    value.update(changes)
    return value


def _arguments(raw=_RAW, *, items=None):  # type: ignore[no-untyped-def]
    record = SourceRecord(
        "inspire",
        "123456",
        {
            "control_number": 123456,
            "preprint_date": "2018-01-09",
            "authors": [
                {
                    "record": {"$ref": "https://inspirehep.net/api/authors/123"},
                    "raw_affiliations": [{"value": raw}],
                }
            ],
        },
    )
    payload = json.dumps(
        {
            "items": items
            if items is not None
            else [
                {
                    "chosen": True,
                    "score": 0.01,
                    "matching_type": "SINGLE SEARCH",
                    "organization": _organization(),
                }
            ]
        }
    ).encode()
    return dict(
        paper_record=record,
        paper_reference=EvidenceReference(
            "inspire",
            record.source_record_id,
            record.checksum,
            "synthetic-paper-snapshot",
        ),
        author_index=0,
        raw_affiliation_index=0,
        request_uri=ror_affiliation_request_uri(raw),
        response_payload=payload,
        response_reference=EvidenceReference(
            "ror",
            ror_affiliation_reference_id(raw),
            hashlib.sha256(payload).hexdigest(),
            "synthetic-ror-snapshot",
        ),
        requested_at=_TIME,
        received_at=_TIME + timedelta(seconds=1),
        http_status=200,
    )


def test_exact_paper_text_and_ror_choice_crosscheck_without_reviewer() -> None:
    result = certify_paper_raw_affiliation_match(**_arguments())
    assert result.state == "certified"
    assert result.canonical_institution_id == "institution-ror-02vwzrd76"
    assert result.receipt.source_field == "authors[0].raw_affiliations[0].value"
    assert result.receipt.raw_affiliation == _RAW
    assert result.receipt.country_code == "US" and result.receipt.city == "Boston"
    assert result.receipt.matched_label == "Example University"
    assert result.certification is not None
    assert result.certification.evidence.reviewed_by is None
    assert result.certification.evidence.reviewed_at is None
    assert result.certification.match_method == ROR_AFFILIATION_MATCH_VERSION
    assert (
        result.certification.evidence.source_manifest_digest
        == result.receipt.input_digest
    )
    assert "response_payload" not in asdict(result.receipt)
    # The numeric ROR score is not an Atlas scientific threshold.
    assert "score" not in asdict(result.receipt)


@pytest.mark.parametrize(
    "raw",
    ["EU, Boston, United States", "Example University Press, Boston, United States"],
)
def test_acronym_or_substring_alone_is_not_a_full_institutional_clause(
    raw: str,
) -> None:
    result = certify_paper_raw_affiliation_match(**_arguments(raw))
    assert result.state == "needs_review" and result.canonical_institution_id is None
    assert "whole institutional clause" in result.receipt.reasons[0]


@pytest.mark.parametrize(
    "raw",
    [
        "Example University, Boston, Canada",
        "Example University, Toronto, United States",
        "Example University, Toronto",
        "Other Institute, Example University, Boston, United States",
        "Example University, Unreturned Other Company, Boston, United States",
        "Example University, Other University Boston, United States",
        "Example University, Boston, United States and Other University",
        "Department of Physics at Other University, "
        "Example University, Boston, United States",
        "Department of Other University, Example University, Boston, United States",
        "School of Physics CERN, Example University, Boston, United States",
    ],
)
def test_geographic_or_additional_organization_ambiguity_stays_unresolved(
    raw: str,
) -> None:
    result = certify_paper_raw_affiliation_match(**_arguments(raw))
    assert result.state == "needs_review"
    assert result.canonical_institution_id is None and result.receipt.reasons


def test_country_only_corroboration_does_not_invent_a_city() -> None:
    result = certify_paper_raw_affiliation_match(
        **_arguments("Example University, United States")
    )
    assert result.state == "certified" and result.receipt.city is None
    assert result.receipt.country_code == "US"


@pytest.mark.parametrize(
    "raw", ["Example University", "Department of Physics, Example University"]
)
def test_whole_name_without_independent_geography_stays_unresolved(raw: str) -> None:
    result = certify_paper_raw_affiliation_match(**_arguments(raw))
    assert result.state == "needs_review" and result.canonical_institution_id is None
    assert result.receipt.country_code is None and result.receipt.city is None
    assert "geographic corroboration is missing" in result.receipt.reasons[0]


def test_known_simple_subunits_remain_address_components_only() -> None:
    for prefix in (
        "Department of Nuclear Physics",
        "Dept. Physics",
        "School of Physics and Astronomy",
    ):
        result = certify_paper_raw_affiliation_match(
            **_arguments(f"{prefix}, Example University, Boston, United States")
        )
        assert result.state == "certified"


def test_chosen_flag_alone_and_multiple_chosen_results_are_insufficient() -> None:
    no_choice = [{"chosen": False, "score": 1.0, "organization": _organization()}]
    multiple = [
        {"chosen": True, "organization": _organization()},
        {"chosen": True, "organization": _organization(id="https://ror.org/05vt9qd57")},
    ]
    for items in ([], no_choice, multiple):
        result = certify_paper_raw_affiliation_match(**_arguments(items=items))
        assert (
            result.state == "needs_review" and result.canonical_institution_id is None
        )


def test_two_exact_organization_clauses_are_not_forced_into_one_owner() -> None:
    items = [
        {"chosen": True, "organization": _organization()},
        {
            "chosen": False,
            "organization": _organization(
                id="https://ror.org/05vt9qd57",
                names=[
                    {"value": "Other University", "types": ["ror_display", "label"]}
                ],
            ),
        },
    ]
    result = certify_paper_raw_affiliation_match(
        **_arguments(
            "Example University, Other University, Boston, United States", items=items
        )
    )
    assert result.state == "needs_review" and result.canonical_institution_id is None


@pytest.mark.parametrize(
    "change",
    [
        {"status": "inactive"},
        {"established": 2020},
        {"relationships": [{"type": "successor", "id": "https://ror.org/05vt9qd57"}]},
    ],
)
def test_existing_lifecycle_boundaries_are_not_bypassed(
    change: dict,
) -> None:
    result = certify_paper_raw_affiliation_match(
        **_arguments(
            items=[
                {
                    "chosen": True,
                    "organization": _organization(**change),
                }
            ]
        )
    )
    assert result.state == "needs_review" and result.canonical_institution_id is None


def test_independent_child_ror_is_retained_without_parent_rollup() -> None:
    result = certify_paper_raw_affiliation_match(
        **_arguments(
            items=[
                {
                    "chosen": True,
                    "organization": _organization(
                        relationships=[
                            {"type": "parent", "id": "https://ror.org/05vt9qd57"},
                        ]
                    ),
                }
            ]
        )
    )
    assert result.state == "certified"
    assert result.canonical_institution_id == "institution-ror-02vwzrd76"
    assert result.certification is not None
    assert result.certification.source_institution_id == result.canonical_institution_id


def test_unknown_relation_cannot_silently_bypass_lifecycle_checks() -> None:
    with pytest.raises(CertificationError, match="relationship type is unsupported"):
        certify_paper_raw_affiliation_match(
            **_arguments(
                items=[
                    {
                        "chosen": True,
                        "organization": _organization(
                            relationships=[
                                {
                                    "type": "Parent",
                                    "id": "https://ror.org/05vt9qd57",
                                }
                            ]
                        ),
                    }
                ]
            )
        )


def test_source_path_query_checksum_timestamp_and_status_are_bound() -> None:
    arguments = _arguments()
    mutations = [
        {"author_index": 1},
        {"raw_affiliation_index": 1},
        {"author_index": True},
        {"request_uri": ror_affiliation_request_uri("Different University")},
        {"request_uri": arguments["request_uri"] + "&filter=country:US"},
        {"request_uri": arguments["request_uri"].replace("api.ror.org", "example.org")},
        {"response_payload": arguments["response_payload"][:-1]},
        {
            "response_reference": replace(
                arguments["response_reference"], checksum="a" * 64
            )
        },
        {"paper_reference": replace(arguments["paper_reference"], checksum="a" * 64)},
        {"received_at": _TIME - timedelta(seconds=1)},
        {"requested_at": _TIME.replace(tzinfo=None)},
        {"http_status": 500},
    ]
    for mutation in mutations:
        with pytest.raises(CertificationError):
            certify_paper_raw_affiliation_match(**(arguments | mutation))


def test_payload_bound_and_result_receipt_are_fail_closed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    arguments = _arguments()
    result = certify_paper_raw_affiliation_match(**arguments)
    with pytest.raises(CertificationError, match="exact receipt"):
        replace(
            result,
            receipt=replace(result.receipt, raw_affiliation="Changed source text"),
        )
    with pytest.raises(CertificationError, match="claim certification"):
        replace(result, certification=None)
    assert MAXIMUM_ROR_MATCH_BYTES == 8 * 1024 * 1024
    monkeypatch.setattr(
        "physics_atlas_api.certification.ror_affiliation_match.MAXIMUM_ROR_MATCH_BYTES",
        32,
    )
    with pytest.raises(CertificationError, match="bytes and times"):
        certify_paper_raw_affiliation_match(**arguments)
