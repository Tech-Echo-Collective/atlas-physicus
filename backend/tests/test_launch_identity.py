"""Bounded synthetic fixtures for exact source-native duplicate authority."""

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from test_launch_inputs import launch_occurrence
from test_launch_years import captured_fixture

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.launch_identity import (
    MAXIMUM_ARXIV_IDENTITY_PAGE_BYTES,
    capture_arxiv_admin_duplicate,
    resolve_launch_admin_duplicate,
)
from physics_atlas_api.certification.launch_inputs import canonicalize_launch_inputs
from physics_atlas_api.certification.launch_years import build_launch_source_year

_SOURCE = "1803.05701"
_TARGET = "1806.03050"
_TIME = datetime(2026, 9, 8, tzinfo=UTC)
_PAGE = f"""<html><meta name="citation_arxiv_id" content="{_SOURCE}">
<span class="error">This paper has been withdrawn by arXiv Admin</span>
<td class="tablecell comments mathjax"><em>arXiv admin note: This submission
has been withdrawn by arXiv administrators as it is a duplicate of
<a href="https://arxiv.org/abs/{_TARGET}">arXiv:{_TARGET}</a>. Please refer to that
document for any more recent versions</em></td></html>""".encode()


def _authority(payload: bytes = _PAGE, **changes):
    return capture_arxiv_admin_duplicate(
        payload,
        **{
            "request_uri": f"https://arxiv.org/abs/{_SOURCE}",
            "requested_at": _TIME,
            "received_at": _TIME,
            "source_snapshot_id": "synthetic-authority-only-v1",
            **changes,
        },
    )


def _occurrence():
    return launch_occurrence(
        arxiv_eprints=[{"value": _SOURCE}, {"value": _TARGET}],
        dois=[{"value": "10.1234/synthetic-fixture"}],
    )


def test_exact_admin_duplicate_resolves_without_losing_original_assertions():
    original = _occurrence()
    assert canonicalize_launch_inputs((original,)).papers[0].component.status == (
        "needs_review"
    )
    authority = _authority()
    resolved = resolve_launch_admin_duplicate(original, authority)
    assert resolved.original_identity == original.identity
    assert resolved.source_facts == original.source_facts
    assert resolved.authors == original.authors
    assert resolved.field_evidence == original.field_evidence
    assert resolved.doi_assertions == original.doi_assertions
    assert set(resolved.identity_references) == {
        original.reference,
        authority.reference,
    }
    assert authority.reference.checksum == hashlib.sha256(_PAGE).hexdigest()
    result = canonicalize_launch_inputs((resolved,))
    assert result.occurrence_count == 1
    assert result.papers[0].component.status == "matched"
    assert result.papers[0].occurrences[0].duplicate_authority == authority
    assert (
        canonicalize_launch_inputs(result.papers[0].occurrences).papers == result.papers
    )


@pytest.mark.parametrize(
    "before,after",
    [
        (b"arXiv admin note:", b"Author note:"),
        (b"arXiv administrators", b"the authors"),
        (b"duplicate of", b"related to"),
        (b"This paper has been withdrawn by arXiv Admin", b"Withdrawn by author"),
        (b"https://arxiv.org/abs/1806.03050", b"https://example.org/abs/1806.03050"),
        (b"arXiv:1806.03050", b"arXiv:1806.03051"),
        (b'content="1803.05701"', b'content="1803.05702"'),
        (b'class="tablecell comments mathjax"', b'class="abstract"'),
    ],
)
def test_related_or_forged_notice_does_not_become_duplicate_authority(before, after):
    with pytest.raises(CertificationError):
        _authority(_PAGE.replace(before, after))


def test_authority_page_requires_bounded_exact_inventory_and_source_origin():
    with pytest.raises(CertificationError):
        _authority(_PAGE + _PAGE)
    with pytest.raises(CertificationError):
        _authority(request_uri="https://example.org/abs/1803.05701")
    with pytest.raises(CertificationError):
        _authority(b"a" * (MAXIMUM_ARXIV_IDENTITY_PAGE_BYTES + 1))
    with pytest.raises(CertificationError):
        _authority(source_snapshot_id="")


def test_no_unasserted_target_or_favorable_other_identity_change():
    authority = _authority()
    original = _occurrence()
    only_source = launch_occurrence(arxiv_eprints=[{"value": _SOURCE}])
    with pytest.raises(CertificationError, match="both source asserted"):
        resolve_launch_admin_duplicate(only_source, authority)
    resolved = resolve_launch_admin_duplicate(original, authority)
    with pytest.raises(CertificationError, match="unrelated source facts"):
        replace(resolved, identity=replace(resolved.identity, title="Other work"))
    with pytest.raises(CertificationError):
        replace(resolved, duplicate_authority=replace(authority, notice="guessed"))


def test_duplicate_authority_does_not_resolve_unrelated_doi_conflict():
    original = launch_occurrence(
        arxiv_eprints=[{"value": _SOURCE}, {"value": _TARGET}],
        dois=[{"value": "10.1234/first"}, {"value": "10.1234/second"}],
    )
    resolved = resolve_launch_admin_duplicate(original, _authority())
    component = canonicalize_launch_inputs((resolved,)).papers[0].component
    assert component.status == "needs_review"
    assert component.conflict_schemes == ("doi",)


def test_source_year_retains_external_authority_separate_from_page_inventory():
    captured, _, attributions = captured_fixture(duplicate_arxiv=True)
    authority = _authority()
    captured = replace(
        captured,
        occurrences=(
            resolve_launch_admin_duplicate(captured.occurrences[0], authority),
            captured.occurrences[1],
        ),
    )
    canonical = canonicalize_launch_inputs(captured.occurrences)
    built = build_launch_source_year(
        captured,
        canonical,
        attributions,
        entity_type="institution",
        evidence_cutoff=_TIME + timedelta(seconds=1),
    )
    assert built.source_year is not None
    assert built.source_year.state == "certified"
    resolved_paper = next(
        paper
        for paper in canonical.papers
        if authority.reference in paper.occurrences[0].identity_references
    )
    decisions = tuple(
        decision
        for decision in built.source_year.evidence.structural_decisions
        if decision.subject_id == resolved_paper.paper_id
        and decision.evidence_kind
        in {"canonical-paper-identity", "provenance-completeness"}
    )
    assert len(decisions) == 2
    assert all(authority.reference in decision.evidence for decision in decisions)
    assert all(
        authority.reference not in projection.occurrence_references
        for projection in built.source_year.evidence.paper_projections
    )
    with pytest.raises(CertificationError, match="capture, cutoff"):
        build_launch_source_year(
            captured,
            canonical,
            attributions,
            entity_type="institution",
            evidence_cutoff=_TIME - timedelta(seconds=1),
        )
