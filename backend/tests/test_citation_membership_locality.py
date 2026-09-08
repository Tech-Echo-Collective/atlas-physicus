"""Synthetic, bounded cohort diagnostics; no providers or acquisition."""

import pytest
from test_automatic_citations import _KEY, _capture, _cohort, _payload

from physics_atlas_api.certification.automatic_citations import (
    build_automatic_citation_population,
    citation_population_query,
    derive_citation_observations,
)
from physics_atlas_api.certification.contracts import CertificationError


@pytest.mark.parametrize("known_exclusion", ["different-year", "different-type"])
def test_unresolved_other_cohort_cannot_poison_exact_target_membership(
    known_exclusion: str,
) -> None:
    payload = _payload(51)
    other = payload["hits"]["hits"][-1]["metadata"]
    other.pop("inspire_categories")
    if known_exclusion == "different-year":
        other["preprint_date"] = "2021-01-01"
    else:
        other["document_type"] = ["book"]
    receipt = _capture(
        payload,
        query=citation_population_query("hep-th-v1", 2020, 2021),
        end_calendar_year=2021,
    )
    original = receipt.content_digest
    assert receipt.records[-1].unresolved_membership
    cohort = _cohort(receipt)
    assert cohort.state == "certified" and cohort.paper_count == 50
    assert "paper-51" not in {item.paper_id for item in cohort.observations}
    assert len(receipt.records) == 51 and receipt.content_digest == original


def test_partial_field_mass_preserves_known_membership_and_uncertainty() -> None:
    payload = _payload()
    payload["hits"]["hits"][0]["metadata"]["inspire_categories"].append(
        {"term": "unknown-synthetic-category"}
    )
    receipt = _capture(payload)
    before = receipt.content_digest
    assert receipt.records[0].unresolved_membership == (
        "provider field classification has unmapped mass",
    )
    cohort = _cohort(receipt)
    assert cohort.state == "certified" and cohort.paper_count == 50
    assert "paper-1" in {item.paper_id for item in cohort.observations}
    assert receipt.content_digest == before
    # The same partial record cannot prove whether it belongs to another field.
    with pytest.raises(CertificationError, match="unresolved source records"):
        build_automatic_citation_population(receipt, ("hep-ex", 2020, "article"))


def test_same_year_unknown_target_membership_remains_fail_closed() -> None:
    payload = _payload(51)
    payload["hits"]["hits"][-1]["metadata"].pop("inspire_categories")
    receipt = _capture(payload)
    with pytest.raises(CertificationError, match="unresolved source records"):
        build_automatic_citation_population(receipt, _KEY)
    assert len(receipt.records) == 51


def test_missing_actual_member_count_still_withholds_the_entire_reference_cohort() -> (
    None
):
    payload = _payload(100)
    payload["hits"]["hits"][0]["metadata"].pop("citation_count_without_self_citations")
    receipt = _capture(payload)
    assert len(derive_citation_observations(receipt, _KEY)) == 100
    cohort = _cohort(receipt)
    assert cohort.paper_count == 100
    assert cohort.state == "insufficient_evidence"
    assert (
        next(
            item for item in cohort.observations if item.paper_id == "paper-1"
        ).non_self_citation_count
        is None
    )
    # 99% observed counts does not redefine the exact reference mean denominator.
    assert sum(item.state == "certified" for item in cohort.observations) == 99
