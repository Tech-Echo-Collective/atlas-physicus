"""Opt-in exact organization retention does not change legacy rollup policy."""

from dataclasses import replace

import pytest

from physics_atlas_api.certification.contracts import CertificationError
from physics_atlas_api.certification.institutions import (
    EXACT_ROR_IDENTITY_RULE_VERSION,
    InstitutionAuthorityRecord,
    InstitutionResolutionEvidence,
    certify_institution,
    institution_authority_version,
)


def _values():  # type: ignore[no-untyped-def]
    child = InstitutionAuthorityRecord(
        "institution-ror-02vwzrd76",
        "02vwzrd76",
        "Synthetic independently identified child",
        parent_ror_ids=("05vt9qd57",),
    )
    evidence = InstitutionResolutionEvidence(
        raw_name="Synthetic child",
        source_evidence_ids=("synthetic-source-id",),
        source_manifest_digest="a" * 64,
        authority_version=institution_authority_version((child,)),
        direct_ror_ids=(child.ror_id,),
    )
    return child, evidence


def test_exact_child_retention_preserves_legacy_rollup_requirement() -> None:
    child, evidence = _values()
    old = certify_institution(evidence, (child,))
    assert old.state == "needs_review" and old.canonical_institution_id is None
    current = certify_institution(evidence, (child,), retain_exact_ror_identity=True)
    assert current.state == "certified"
    assert (
        current.canonical_institution_id
        == current.source_institution_id
        == child.institution_id
    )
    assert current.rule_version == EXACT_ROR_IDENTITY_RULE_VERSION
    assert current.evidence.reviewed_by is None


def test_exact_retention_does_not_accept_inactive_or_conflicting_authority() -> None:
    child, evidence = _values()
    inactive = replace(child, active=False)
    current = certify_institution(
        replace(evidence, authority_version=institution_authority_version((inactive,))),
        (inactive,),
        retain_exact_ror_identity=True,
    )
    assert current.state == "needs_review" and current.canonical_institution_id is None
    conflicting = replace(evidence, direct_ror_ids=(child.ror_id, "05vt9qd57"))
    assert (
        certify_institution(conflicting, (child,), retain_exact_ror_identity=True).state
        != "certified"
    )


def test_exact_retention_cannot_be_combined_with_parent_rollup_request() -> None:
    child, evidence = _values()
    with pytest.raises(CertificationError, match="cannot request a parent rollup"):
        certify_institution(
            replace(evidence, reviewed_rollup_institution_id="parent-id"),
            (child,),
            retain_exact_ror_identity=True,
        )


def test_exact_retention_still_requires_authority_checksum_and_direct_id() -> None:
    child, evidence = _values()
    assert (
        certify_institution(
            replace(evidence, authority_version="b" * 64),
            (child,),
            retain_exact_ror_identity=True,
        ).state
        == "conflicted"
    )
    no_direct = replace(evidence, direct_ror_ids=())
    assert (
        certify_institution(no_direct, (child,), retain_exact_ror_identity=True).state
        != "certified"
    )
