"""Bounded synthetic fixtures for exact paper-time authority traversal."""

from copy import deepcopy
from dataclasses import replace

import pytest

from physics_atlas_api.certification.contracts import (
    CertificationError,
    EvidenceReference,
)
from physics_atlas_api.certification.institutions import certify_paper_institution_link
from physics_atlas_api.connectors.base import SourceRecord


def _reference(record: SourceRecord) -> EvidenceReference:
    return EvidenceReference(
        record.provider,
        record.source_record_id,
        record.checksum,
        f"fixture-{record.provider}-{record.source_record_id}",
    )


def _inputs():  # type: ignore[no-untyped-def]
    paper = SourceRecord(
        "inspire",
        "100",
        {
            "control_number": 100,
            "authors": [
                {
                    "affiliations": [
                        {
                            "value": "Unnormalized paper-time name",
                            "record": {
                                "$ref": "https://inspirehep.net/api/institutions/200"
                            },
                        }
                    ]
                }
            ],
        },
    )
    institution = SourceRecord(
        "inspire",
        "200",
        {
            "control_number": 200,
            "external_system_identifiers": [{"schema": "ROR", "value": "042nb2s44"}],
        },
    )
    authority = SourceRecord(
        "ror",
        "042nb2s44",
        {
            "id": "https://ror.org/042nb2s44",
            "status": "active",
            "names": [{"value": "Synthetic Authority", "types": ["ror_display"]}],
            "relationships": [],
        },
    )
    return dict(
        paper_record=paper,
        paper_reference=_reference(paper),
        paper_time_provider_institution_id="200",
        institution_record=institution,
        institution_reference=_reference(institution),
        ror_record=authority,
        ror_reference=_reference(authority),
        raw_affiliation_name="Unnormalized paper-time name",
    )


def test_exact_paper_native_link_certifies_without_human_or_name_match() -> None:
    result = certify_paper_institution_link(**_inputs())
    assert result.state == "certified"
    assert result.canonical_institution_id == "institution-ror-042nb2s44"
    assert result.match_method == "paper-native-provider-id-explicit-ror"
    assert result.evidence.reviewed_by is None
    assert result.evidence.reviewed_at is None
    assert len(result.evidence.source_evidence_ids) == 3


@pytest.mark.parametrize(
    "record_key", ["paper_record", "institution_record", "ror_record"]
)
def test_changed_source_bytes_cannot_reuse_reference(record_key: str) -> None:
    values = _inputs()
    record = values[record_key]
    values[record_key] = replace(record, raw={**record.raw, "mutation": True})
    with pytest.raises(CertificationError, match="does not bind source"):
        certify_paper_institution_link(**values)


@pytest.mark.parametrize(
    "mutation",
    [
        "profile-only",
        "wrong-host",
        "wrong-institution",
        "wrong-ror",
        "conflicting-ror",
        "missing-ror",
    ],
)
def test_context_or_conflicting_authority_cannot_certify(mutation: str) -> None:
    values = _inputs()
    if mutation in {"profile-only", "wrong-host"}:
        record = values["paper_record"]
        raw = deepcopy(record.raw)
        if mutation == "profile-only":
            raw["authors"] = [
                {"record": {"$ref": "https://inspirehep.net/api/authors/200"}}
            ]
        else:
            raw["authors"][0]["affiliations"][0]["record"]["$ref"] = (
                "https://example.com/api/institutions/200"
            )
        values["paper_record"] = replace(record, raw=raw)
        values["paper_reference"] = _reference(values["paper_record"])
    elif mutation == "wrong-institution":
        values["paper_time_provider_institution_id"] = "201"
    elif mutation == "wrong-ror":
        values["ror_record"] = replace(
            values["ror_record"], source_record_id="03yrm5c26"
        )
        values["ror_reference"] = _reference(values["ror_record"])
    else:
        record = values["institution_record"]
        entries = (
            []
            if mutation == "missing-ror"
            else [
                {"schema": "ROR", "value": "042nb2s44"},
                {"schema": "ROR", "value": "03yrm5c26"},
            ]
        )
        values["institution_record"] = replace(
            record, raw={**record.raw, "external_system_identifiers": entries}
        )
        values["institution_reference"] = _reference(values["institution_record"])
    with pytest.raises(CertificationError):
        certify_paper_institution_link(**values)


def test_inactive_organization_is_not_certified() -> None:
    values = _inputs()
    record = values["ror_record"]
    raw = deepcopy(record.raw)
    raw["status"] = "inactive"
    values["ror_record"] = replace(record, raw=raw)
    values["ror_reference"] = _reference(values["ror_record"])
    result = certify_paper_institution_link(**values)
    assert result.state == "needs_review"
    assert result.canonical_institution_id is None


def test_explicit_child_identity_does_not_request_parent_rollup() -> None:
    values = _inputs()
    record = values["ror_record"]
    raw = deepcopy(record.raw)
    raw["relationships"] = [
        {"type": "parent", "id": "https://ror.org/03yrm5c26"},
        {"type": "parent", "id": "https://ror.org/05vt9qd57"},
    ]
    values["ror_record"] = replace(record, raw=raw)
    values["ror_reference"] = _reference(values["ror_record"])
    result = certify_paper_institution_link(**values)
    assert result.state == "certified"
    assert result.canonical_institution_id == "institution-ror-042nb2s44"
    assert result.source_institution_id == result.canonical_institution_id
    assert result.rule_version == "institution-ror-exact-identity-v1"
    assert result.evidence.reviewed_rollup_institution_id is None
