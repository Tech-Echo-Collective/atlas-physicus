"""Synthetic authoritative attribution glue; no provider calls or files."""

from dataclasses import asdict, replace
from fractions import Fraction
from typing import Any
from unittest.mock import Mock

import pytest
from test_ror_affiliation_match import _arguments, _organization

from physics_atlas_api.certification.automation import (
    AutomaticEvidenceContext,
    capture_automatic_paper_facts,
)
from physics_atlas_api.certification.contracts import (
    CertificationError,
    EvidenceReference,
)
from physics_atlas_api.certification.launch_attribution import attribute_launch_record
from physics_atlas_api.certification.launch_scope import BOUNDED_LAUNCH_SCOPE
from physics_atlas_api.certification.ror_affiliation_match import (
    certify_paper_raw_affiliation_match,
)
from physics_atlas_api.connectors.base import SourceRecord

_ROR_A = "02vwzrd76"
_ROR_B = "05vt9qd57"


def _reference(record: SourceRecord) -> EvidenceReference:
    return EvidenceReference(
        record.provider,
        record.source_record_id,
        record.checksum,
        f"synthetic-{record.provider}-{record.source_record_id}",
    )


def _facts(record: SourceRecord):  # type: ignore[no-untyped-def]
    return capture_automatic_paper_facts(
        record,
        context=AutomaticEvidenceContext(
            "test-only-paper", "test-only-attribution-v1", BOUNDED_LAUNCH_SCOPE
        ),
        reference=_reference(record),
        declared_date_basis="inspire-preprint-date",
    )


def _paper(authors: object) -> SourceRecord:
    return SourceRecord(
        "inspire",
        "100",
        {
            "control_number": 100,
            "preprint_date": "2020-01-01",
            "authors": authors,
            "abstracts": [{"value": "DO-NOT-RETAIN-SOURCE-PAYLOAD"}],
        },
    )


def _author(
    index: int, affiliations: list[dict[str, Any]] | None = None, **changes: Any
) -> dict[str, Any]:
    return {"recid": str(index), "affiliations": affiliations or [], **changes}


def _link(identifier: str) -> dict[str, Any]:
    return {
        "value": f"Synthetic Institute {identifier}",
        "record": {"$ref": f"https://inspirehep.net/api/institutions/{identifier}"},
    }


def _institution(identifier: str, ror: str) -> SourceRecord:
    return SourceRecord(
        "inspire",
        identifier,
        {
            "control_number": int(identifier),
            "external_system_identifiers": [{"schema": "ROR", "value": ror}],
        },
    )


def _ror(identifier: str, **changes: Any) -> SourceRecord:
    return SourceRecord(
        "ror", identifier, _organization(id=f"https://ror.org/{identifier}", **changes)
    )


def _lookup(records: tuple[SourceRecord, ...]):  # type: ignore[no-untyped-def]
    values = {item.source_record_id: (item, _reference(item)) for item in records}
    return lambda identifier: values.get(identifier)


def _run(record: SourceRecord, *, institutions=(), rors=(), **changes):  # type: ignore[no-untyped-def]
    return attribute_launch_record(
        record,
        reference=_reference(record),
        source_facts=_facts(record),
        institution_lookup=_lookup(institutions),
        ror_lookup=_lookup(rors),
        **changes,
    )


def test_each_author_receives_only_their_own_paper_native_institution() -> None:
    record = _paper([_author(1, [_link("200")]), _author(2, [_link("201")])])
    result = _run(
        record,
        institutions=(_institution("200", _ROR_A), _institution("201", _ROR_B)),
        rors=(_ror(_ROR_A), _ror(_ROR_B)),
    )
    assert result.fractional is not None
    assert result.fractional.total_weight == result.fractional.allocated_weight == 1
    assert result.fractional.institution_weights() == {
        f"institution-ror-{_ROR_A}": Fraction(1, 2),
        f"institution-ror-{_ROR_B}": Fraction(1, 2),
    }
    assert result.fractional.shares[0].researcher_id == "inspire-author:1"
    assert result.fractional.shares[0].institution_id == f"institution-ror-{_ROR_A}"
    assert result.fractional.shares[1].institution_id == f"institution-ror-{_ROR_B}"
    assert result.fractional.country_weights() == {"country-us": Fraction(1)}
    assert (
        result.paper_time_affiliation_weight == 1
        and result.researcher_state == "certified"
    )
    assert not result.unresolved_reason_counts
    assert "DO-NOT-RETAIN-SOURCE-PAYLOAD" not in str(asdict(result))


def test_duplicate_same_institution_rows_use_existing_distinct_affiliation_rule() -> (
    None
):
    record = _paper([_author(1, [_link("200"), _link("200")]), _author(2)])
    result = _run(
        record, institutions=(_institution("200", _ROR_A),), rors=(_ror(_ROR_A),)
    )
    assert result.fractional is not None
    assert result.fractional.allocated_weight == Fraction(1, 2)
    assert result.fractional.withheld_weight == Fraction(1, 2)
    assert result.paper_time_affiliation_weight == Fraction(1, 2)
    assert result.fractional.total_weight == 1


def test_author_ror_applies_only_to_single_affiliation_not_multiple() -> None:
    single = _paper(
        [
            _author(
                1,
                [{"value": "Synthetic name"}],
                affiliations_identifiers=[{"schema": "ROR", "value": _ROR_A}],
            )
        ]
    )
    result = _run(single, rors=(_ror(_ROR_A),))
    assert result.fractional is not None and result.fractional.allocated_weight == 1
    multiple = _paper(
        [
            _author(
                1,
                [{"value": "First"}, {"value": "Second"}],
                affiliations_identifiers=[{"schema": "ROR", "value": _ROR_A}],
            )
        ]
    )
    result = _run(multiple, rors=(_ror(_ROR_A),))
    assert result.fractional is not None and result.fractional.withheld_weight == 1
    assert result.paper_time_affiliation_weight == 1


def test_affiliation_local_ror_resolves_one_row_without_stealing_mass() -> None:
    record = _paper(
        [
            _author(
                1,
                [
                    {
                        "value": "Known",
                        "identifiers": [{"schema": "ROR", "value": _ROR_A}],
                    },
                    {"value": "Unknown"},
                ],
            )
        ]
    )
    result = _run(record, rors=(_ror(_ROR_A),))
    assert result.fractional is not None
    assert (
        result.fractional.allocated_weight
        == result.fractional.withheld_weight
        == Fraction(1, 2)
    )
    assert result.fractional.total_weight == 1


def test_conflicting_direct_and_provider_ror_never_choose_either() -> None:
    record = _paper(
        [
            _author(
                1,
                [{**_link("200"), "identifiers": [{"schema": "ROR", "value": _ROR_B}]}],
            )
        ]
    )
    result = _run(
        record,
        institutions=(_institution("200", _ROR_A),),
        rors=(_ror(_ROR_A), _ror(_ROR_B)),
    )
    assert result.fractional is not None and result.fractional.withheld_weight == 1
    assert result.affiliations[0].state == "conflicted"


def test_structured_affiliations_take_precedence_without_matching_raw_rows() -> None:
    record = _paper(
        [_author(1, [_link("200")], raw_affiliations=[{"value": "Other Institute"}])]
    )
    raw_match = Mock(side_effect=AssertionError("must not align unrelated raw rows"))
    result = _run(
        record,
        institutions=(_institution("200", _ROR_A),),
        rors=(_ror(_ROR_A),),
        raw_match=raw_match,
    )
    assert result.fractional is not None and result.fractional.allocated_weight == 1
    raw_match.assert_not_called()


def test_raw_match_requires_same_paper_author_slot_and_exact_candidate_authority() -> (
    None
):
    arguments = _arguments()
    record = arguments["paper_record"]
    reference = arguments["paper_reference"]
    result = certify_paper_raw_affiliation_match(**arguments)
    source_facts = capture_automatic_paper_facts(
        record,
        context=AutomaticEvidenceContext(
            "raw-test-paper", "test-v1", BOUNDED_LAUNCH_SCOPE
        ),
        reference=reference,
        declared_date_basis="inspire-preprint-date",
    )
    authority = _ror(_ROR_A)
    actual = attribute_launch_record(
        record,
        reference=reference,
        source_facts=source_facts,
        institution_lookup=lambda _: None,
        ror_lookup=_lookup((authority,)),
        raw_match=lambda paper, ref, author_index, row_index: result,
    )
    assert actual.fractional is not None and actual.fractional.allocated_weight == 1
    assert actual.affiliations[0].source_field == "authors[0].raw_affiliations[0]"
    with pytest.raises(CertificationError, match="candidate payload"):
        attribute_launch_record(
            record,
            reference=reference,
            source_facts=source_facts,
            institution_lookup=lambda _: None,
            ror_lookup=_lookup((_ror(_ROR_A, established=1899),)),
            raw_match=lambda paper, ref, author_index, row_index: result,
        )
    changed = replace(
        result.receipt, source_field="authors[1].raw_affiliations[0].value"
    )
    # This mutation is also invalid at the typed receipt/result boundary.
    with pytest.raises(CertificationError):
        swapped = replace(result, receipt=changed)
        attribute_launch_record(
            record,
            reference=reference,
            source_facts=source_facts,
            institution_lookup=lambda _: None,
            ror_lookup=_lookup((authority,)),
            raw_match=lambda paper, ref, author_index, row_index: swapped,
        )


@pytest.mark.parametrize(
    "locations",
    [
        [],
        [
            {"geonames_details": {"country_code": "US", "name": "Boston"}},
            {"geonames_details": {"country_code": "CA", "name": "Toronto"}},
        ],
    ],
)
def test_missing_or_multicountry_authority_is_not_guessed(
    locations: list[dict],
) -> None:
    record = _paper([_author(1, [_link("200")])])
    result = _run(
        record,
        institutions=(_institution("200", _ROR_A),),
        rors=(_ror(_ROR_A, locations=locations),),
    )
    assert result.fractional is not None and result.fractional.withheld_weight == 1
    assert result.affiliations[0].state == "insufficient_evidence"
    assert result.affiliations[0].country_code is None


def test_unknown_authority_and_absent_affiliation_preserve_missing_states() -> None:
    record = _paper([_author(1, [_link("200")]), _author(2)])
    result = _run(record)
    assert result.fractional is not None and result.fractional.withheld_weight == 1
    assert result.paper_time_affiliation_weight == Fraction(1, 2)
    assert {item.status for item in result.fractional.shares} == {
        "withheld-unresolved-affiliation",
        "withheld-no-affiliation",
    }


@pytest.mark.parametrize("authors", [None, []])
def test_missing_author_inventory_is_not_a_zero_scientific_result(
    authors: object,
) -> None:
    result = _run(_paper(authors))
    assert result.fractional is None and result.paper_time_affiliation_weight is None
    assert result.researcher_state != "certified"


def test_authority_record_or_source_fact_substitution_fails_closed() -> None:
    record = _paper([_author(1, [_link("200")])])
    wrong = _institution("201", _ROR_A)
    with pytest.raises(CertificationError, match="actual source record"):
        attribute_launch_record(
            record,
            reference=_reference(record),
            source_facts=_facts(record),
            institution_lookup=lambda _: (wrong, _reference(wrong)),
            ror_lookup=lambda _: None,
        )
    with pytest.raises(CertificationError):
        attribute_launch_record(
            record,
            reference=_reference(record),
            source_facts=_facts(_paper([_author(2)])),
            institution_lookup=lambda _: None,
            ror_lookup=lambda _: None,
        )


def test_authority_callback_cannot_supply_bare_canonical_identifier() -> None:
    record = _paper([_author(1, [_link("200")])])
    with pytest.raises(CertificationError, match="actual record and reference"):
        attribute_launch_record(
            record,
            reference=_reference(record),
            source_facts=_facts(record),
            institution_lookup=lambda _: "institution-ror-pretend",  # type: ignore[arg-type,return-value]
            ror_lookup=lambda _: None,
        )


def test_raw_match_cannot_substitute_canonical_id_behind_valid_receipt() -> None:
    arguments = _arguments()
    record, reference = arguments["paper_record"], arguments["paper_reference"]
    result = certify_paper_raw_affiliation_match(**arguments)
    assert result.certification is not None
    wrong = replace(
        result,
        certification=replace(
            result.certification, canonical_institution_id=f"institution-ror-{_ROR_B}"
        ),
    )
    source_facts = capture_automatic_paper_facts(
        record,
        context=AutomaticEvidenceContext(
            "raw-test-paper", "test-v1", BOUNDED_LAUNCH_SCOPE
        ),
        reference=reference,
        declared_date_basis="inspire-preprint-date",
    )
    with pytest.raises(CertificationError, match="different authority target"):
        attribute_launch_record(
            record,
            reference=reference,
            source_facts=source_facts,
            institution_lookup=lambda _: None,
            ror_lookup=_lookup((_ror(_ROR_A),)),
            raw_match=lambda paper, ref, author_index, row_index: wrong,
        )


def test_raw_match_is_not_acquired_when_its_required_exact_date_is_missing() -> None:
    record = _paper([_author(1, raw_affiliations=[{"value": "Example University"}])])
    record = replace(record, raw={**record.raw, "preprint_date": "2020"})
    lookup = Mock(side_effect=AssertionError("cannot certify without exact date"))
    result = _run(record, raw_match=lookup)
    assert result.fractional is not None and result.fractional.withheld_weight == 1
    assert "raw-affiliation-exact-paper-date-missing" in dict(
        result.unresolved_reason_counts
    )
    lookup.assert_not_called()


def test_author_ror_cannot_turn_an_empty_placeholder_into_affiliation_evidence() -> (
    None
):
    record = _paper(
        [
            _author(
                1, [{}], affiliations_identifiers=[{"schema": "ROR", "value": _ROR_A}]
            )
        ]
    )
    result = _run(record, rors=(_ror(_ROR_A),))
    assert result.fractional is not None and result.fractional.withheld_weight == 1
    assert result.paper_time_affiliation_weight == 0
    assert result.affiliations[0].state == "insufficient_evidence"


@pytest.mark.parametrize("direct", [False, True])
@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"established": 2021}, "institution-authority-established-after-paper"),
        (
            {
                "relationships": [
                    {"type": "successor", "id": f"https://ror.org/{_ROR_B}"}
                ]
            },
            "institution-lifecycle-requires-dated-resolution",
        ),
        (
            {
                "relationships": [
                    {"type": "predecessor", "id": f"https://ror.org/{_ROR_B}"}
                ]
            },
            "institution-lifecycle-requires-dated-resolution",
        ),
    ],
)
def test_source_bound_authority_lifecycle_does_not_rewrite_paper_time_identity(
    direct: bool,
    changes: dict[str, Any],
    reason: str,
) -> None:
    affiliation = (
        {
            "value": "Direct scientific institution",
            "identifiers": [{"schema": "ROR", "value": _ROR_A}],
        }
        if direct
        else _link("200")
    )
    record = _paper([_author(1, [affiliation])])
    result = _run(
        record,
        institutions=(_institution("200", _ROR_A),),
        rors=(_ror(_ROR_A, **changes),),
    )
    assert result.fractional is not None and result.fractional.withheld_weight == 1
    assert reason in dict(result.unresolved_reason_counts)


def test_exact_child_ror_is_retained_without_parent_metadata_or_rollup() -> None:
    record = _paper([_author(1, [_link("200")])])
    result = _run(
        record,
        institutions=(_institution("200", _ROR_A),),
        rors=(
            _ror(
                _ROR_A,
                relationships=[{"type": "parent", "id": f"https://ror.org/{_ROR_B}"}],
            ),
        ),
    )
    assert result.fractional is not None and result.fractional.allocated_weight == 1
    assert result.fractional.institution_weights() == {
        f"institution-ror-{_ROR_A}": Fraction(1)
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"established": "1800"},
        {"established": True},
        {"relationships": "missing-array"},
        {"relationships": ["bad-entry"]},
        {"relationships": [{"type": "unknown", "id": f"https://ror.org/{_ROR_B}"}]},
        {"relationships": [{"type": [], "id": f"https://ror.org/{_ROR_B}"}]},
        {"relationships": [{"type": "parent", "id": "invalid-ror"}]},
    ],
)
def test_malformed_lifecycle_metadata_fails_closed(changes: dict[str, Any]) -> None:
    record = _paper([_author(1, [_link("200")])])
    with pytest.raises(CertificationError):
        _run(
            record,
            institutions=(_institution("200", _ROR_A),),
            rors=(_ror(_ROR_A, **changes),),
        )


def test_partial_paper_date_cannot_guess_historical_institution_identity() -> None:
    record = _paper([_author(1, [_link("200")])])
    record = replace(record, raw={**record.raw, "preprint_date": "2020"})
    result = _run(
        record, institutions=(_institution("200", _ROR_A),), rors=(_ror(_ROR_A),)
    )
    assert result.fractional is not None and result.fractional.withheld_weight == 1
    assert "institution-exact-paper-time-date-missing" in dict(
        result.unresolved_reason_counts
    )
