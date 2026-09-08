"""Observed researcher tuples, not complete author identity certification."""

from dataclasses import fields, replace
from types import SimpleNamespace

import pytest
from test_automatic_identity_date_admission import _facts
from test_metric_system_v1 import (
    calculate_activity_raw,
    calculate_connectivity,
    paper,
    partition,
)

from physics_atlas_api.certification import (
    CertificationError,
    EvidenceCertificationDecision,
)
from physics_atlas_api.certification.automation import (
    automatic_known_researcher_decision,
    automatic_paper_identity_decision,
    verify_automatic_source_binding,
)
from physics_atlas_api.certification.contracts import canonical_digest
from physics_atlas_api.certification.rules import evidence_decision_is_current


def known_authors():
    return [{"recid": str(item)} for item in range(1, 6)]


def test_partial_roster_certifies_only_the_exact_known_tuple():
    facts = _facts(authors=[*known_authors(), {}])
    before = automatic_paper_identity_decision(
        facts, evidence_kind="researcher-identity"
    )
    assert before.state == "insufficient_evidence"
    result = automatic_known_researcher_decision(facts, entity_type="institution")
    assert result.state == "certified"
    assert result.certified_value_digest == canonical_digest(
        {
            "paper_id": facts.context.paper_id,
            "researcher_ids": tuple(f"inspire-author:{item}" for item in range(1, 6)),
        }
    )
    assert result.source_facts.author_count == 6
    assert result.omitted_author_positions == (6,)
    assert result.conflicted_author_positions == ()
    assert result.source_facts == facts
    assert evidence_decision_is_current(result)
    assert (
        automatic_paper_identity_decision(facts, evidence_kind="researcher-identity")
        == before
    )


def test_unrelated_conflicted_slot_remains_explicit_and_is_not_counted():
    facts = _facts(
        authors=[
            *known_authors(),
            {
                "recid": "98",
                "record": {"$ref": "https://inspirehep.net/api/authors/99"},
            },
        ]
    )
    result = automatic_known_researcher_decision(facts, entity_type="country")
    assert result.state == "certified"
    assert result.omitted_author_positions == result.conflicted_author_positions == (6,)
    assert len(facts.researcher_ids) == 5
    assert result.source_facts.researcher_assessments[-1].decision.state == "conflicted"


@pytest.mark.parametrize(
    "last",
    [
        {"recid": "1"},
        {"recid": "1", "record": {"$ref": "https://inspirehep.net/api/authors/99"}},
    ],
)
def test_conflicts_referencing_known_identity_fail_closed(last):
    facts = _facts(authors=[*known_authors(), last])
    result = automatic_known_researcher_decision(facts, entity_type="country")
    assert result.state == "conflicted"
    with pytest.raises(CertificationError):
        replace(result, state="certified", reasons=())


def test_shared_orcid_cannot_merge_or_certify_distinct_native_people():
    facts = _facts(
        authors=[
            {
                "recid": str(item),
                "ids": [{"schema": "ORCID", "value": "0000-0002-1825-0097"}],
            }
            for item in (1, 2)
        ]
    )
    result = automatic_known_researcher_decision(facts, entity_type="institution")
    assert result.state == "conflicted"
    assert facts.researcher_ids == ("inspire-author:1", "inspire-author:2")


@pytest.mark.parametrize("authors", [None, [], [{}], [{"recid": "not-an-id"}]])
def test_empty_observed_tuple_does_not_claim_zero_actual_authors(authors):
    facts = _facts(authors=authors)
    legacy = automatic_paper_identity_decision(
        facts, evidence_kind="researcher-identity"
    )
    result = automatic_known_researcher_decision(facts, entity_type="institution")
    assert result.state == "certified"
    assert facts.researcher_ids == ()
    assert result.source_facts == facts
    assert result.omitted_author_positions == tuple(range(1, len(authors or []) + 1))
    assert result.certified_value_digest == canonical_digest(
        {"paper_id": facts.context.paper_id, "researcher_ids": ()}
    )
    assert legacy.state != "certified"
    assert (
        automatic_paper_identity_decision(facts, evidence_kind="researcher-identity")
        == legacy
    )
    assert evidence_decision_is_current(result)


def test_all_unknown_author_slots_remain_explicit_without_inventing_people():
    facts = _facts(authors=[{}, {}, {}])
    result = automatic_known_researcher_decision(facts, entity_type="country")
    assert result.state == "certified"
    assert result.source_facts.author_count == 3
    assert result.omitted_author_positions == (1, 2, 3)
    assert not result.source_facts.researcher_ids
    assert all(
        item.decision.state == "insufficient_evidence"
        for item in result.source_facts.researcher_assessments
    )


def test_empty_observed_tuple_cannot_hide_conflicting_raw_identity_claims():
    facts = _facts(
        authors=[
            {
                "recid": "98",
                "record": {"$ref": "https://inspirehep.net/api/authors/99"},
            }
        ]
    )
    assert facts.researcher_ids == ()
    result = automatic_known_researcher_decision(facts, entity_type="institution")
    assert result.state == "conflicted"
    assert result.omitted_author_positions == result.conflicted_author_positions == (1,)
    with pytest.raises(CertificationError):
        replace(result, state="certified", reasons=())


@pytest.mark.parametrize("calculator", [calculate_activity_raw, calculate_connectivity])
def test_empty_observed_people_cannot_bypass_minimum_or_create_a_zero_score(calculator):
    facts = _facts(authors=[{}, {}])
    assert (
        automatic_known_researcher_decision(facts, entity_type="institution").state
        == "certified"
    )
    # Isolate the unchanged calculator gate with otherwise sufficient fixtures.
    raw = partition(
        "institution-test-only",
        tuple(
            replace(paper(index, 2025), researcher_ids=facts.researcher_ids)
            for index in range(15)
        ),
    )
    result = calculator(raw)
    assert result.raw_value is None and result.normalized_value is None
    assert result.components["distinct_researchers"] == 0
    assert any("researcher" in reason for reason in result.missing_reasons)


def test_scope_source_and_consumed_value_are_independently_bound():
    facts = _facts(authors=[*known_authors(), {}])
    result = automatic_known_researcher_decision(facts, entity_type="institution")
    projection = SimpleNamespace(
        paper_id=facts.context.paper_id,
        occurrence_references=(facts.reference,),
    )
    verify_automatic_source_binding(result, projection, entity_type="institution")
    for scope in (None, "researcher", "country"):
        with pytest.raises(CertificationError, match="entity scope"):
            verify_automatic_source_binding(result, projection, entity_type=scope)
    with pytest.raises(CertificationError, match="institution/country"):
        automatic_known_researcher_decision(facts, entity_type="researcher")
    with pytest.raises(CertificationError, match="source occurrence"):
        verify_automatic_source_binding(
            result,
            SimpleNamespace(paper_id="other", occurrence_references=()),
            entity_type="institution",
        )
    with pytest.raises(CertificationError, match="reconstruct"):
        replace(result, certified_value_digest="f" * 64)
    stripped = EvidenceCertificationDecision(
        **{
            field.name: getattr(result, field.name)
            for field in fields(EvidenceCertificationDecision)
        }
    )
    assert not evidence_decision_is_current(stripped)
