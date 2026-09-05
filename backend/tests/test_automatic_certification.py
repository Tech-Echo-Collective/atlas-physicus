from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from physics_atlas_api.certification.automation import (
    AutomaticCertification,
    AutomaticDateEvidence,
    AutomaticEvidenceContext,
    AutomaticFieldEvidence,
    AutomaticResearcherEvidence,
    ProviderDateFact,
    ResearcherIdentifierFact,
    ResolvedDateBasis,
    ResolvedResearcherIdentifiers,
    verify_automatic_decision,
)
from physics_atlas_api.certification.contracts import (
    CertificationError,
    EvidenceReference,
    canonical_digest,
)
from physics_atlas_api.certification.fields import (
    FieldLedgerEvidence,
    FieldWeight,
    certify_field_ledger,
)
from physics_atlas_api.fields.mapping import (
    FIELD_WEIGHTING_POLICY_VERSION,
    CrossProviderFieldLedger,
    ProviderCategoryEvidence,
    ProviderFieldProjection,
)

CONTEXT = AutomaticEvidenceContext("paper-1", "bounded-test-v1", "fixture-only")


def reference(
    provider: str = "arxiv", record_id: str = "2001.00001"
) -> EvidenceReference:
    return EvidenceReference(provider, record_id, "a" * 64, "snapshot-1")


def fields(*categories: str) -> AutomaticFieldEvidence:
    source = reference()
    return AutomaticFieldEvidence(
        CONTEXT,
        (
            ProviderFieldProjection(
                "arxiv",
                source.source_record_id,
                tuple(ProviderCategoryEvidence(category) for category in categories),
                source.source_snapshot_id,
            ),
        ),
        (source,),
    )


def dates(value: str, basis: str = "arxiv-initial-submission") -> AutomaticDateEvidence:
    return AutomaticDateEvidence(
        CONTEXT,
        basis,
        (ProviderDateFact(reference(), basis, "published", value),),
    )


def researcher(value: str = "12345") -> AutomaticResearcherEvidence:
    return AutomaticResearcherEvidence(
        CONTEXT,
        "appearance-1",
        (
            ResearcherIdentifierFact(
                reference("inspire", "999"),
                "authors[].record",
                "inspire-author",
                value,
            ),
        ),
    )


def test_exact_provider_fields_rebuild_conserved_ledger_without_human_review() -> None:
    evidence = fields("hep-th", "gr-qc", "hep-th")
    assessment = AutomaticCertification(evidence)
    assert assessment.decision.state == "certified"
    assert assessment.decision.reviewed_by is None
    assert assessment.decision.reviewed_at is None
    assert isinstance(assessment.value, CrossProviderFieldLedger)
    assert {item.field_id: item.weight for item in assessment.value.assignments} == {
        "hep-th": 0.5,
        "gr-qc": 0.5,
    }
    assert assessment.input_digest == canonical_digest(evidence)
    assert verify_automatic_decision(evidence, assessment.decision)


def test_multifield_evidence_preserves_roles_and_is_not_a_duplicate_paper() -> None:
    original = fields("hep-th", "gr-qc")
    projection = replace(
        original.projections[0],
        categories=(
            ProviderCategoryEvidence("hep-th", "primary"),
            ProviderCategoryEvidence("gr-qc", "secondary"),
        ),
    )
    result = AutomaticCertification(replace(original, projections=(projection,)))
    assert isinstance(result.value, CrossProviderFieldLedger)
    assert sum(item.weight for item in result.value.assignments) == 1
    assert result.value.assignments[0].provider_roles == ("primary",)
    assert result.value.assignments[1].provider_roles == ("secondary",)


def test_cross_provider_support_does_not_duplicate_attribution_mass() -> None:
    original = fields("hep-th", "gr-qc")
    inspire = reference("inspire", "999")
    supporting = ProviderFieldProjection(
        "inspire",
        inspire.source_record_id,
        (ProviderCategoryEvidence("Theory-HEP"),),
        inspire.source_snapshot_id,
    )
    assessment = AutomaticCertification(
        replace(
            original,
            projections=(*original.projections, supporting),
            references=(*original.references, inspire),
        )
    )
    assert assessment.decision.state == "certified"
    assert isinstance(assessment.value, CrossProviderFieldLedger)
    assert {item.field_id: item.weight for item in assessment.value.assignments} == {
        "hep-th": 0.5,
        "gr-qc": 0.5,
    }


def test_broad_source_branch_cannot_become_a_leaf_field_certification() -> None:
    source = reference("crossref", "10.1234/example")
    assessment = AutomaticCertification(
        AutomaticFieldEvidence(
            CONTEXT,
            (
                ProviderFieldProjection(
                    "crossref",
                    source.source_record_id,
                    (ProviderCategoryEvidence("Nuclear and High Energy Physics"),),
                    source.source_snapshot_id,
                ),
            ),
            (source,),
        )
    )
    assert assessment.decision.state == "insufficient_evidence"
    assert "leaf fields" in assessment.decision.reasons[0]


@pytest.mark.parametrize(
    "categories", [(), ("unknown-category",), ("hep-th", "unknown")]
)
def test_absent_unknown_or_partially_unmapped_fields_are_not_certified(
    categories: tuple[str, ...],
) -> None:
    assessment = AutomaticCertification(fields(*categories))
    assert assessment.decision.state == "insufficient_evidence"
    assert isinstance(assessment.value, CrossProviderFieldLedger)
    assert assessment.value.unmapped_field_mass > 0
    assert (
        sum(item.weight for item in assessment.value.assignments)
        + assessment.value.unmapped_field_mass
    ) == 1


def test_field_source_occurrence_mismatch_is_rejected() -> None:
    original = fields("hep-th")
    with pytest.raises(CertificationError, match="exact source occurrences"):
        AutomaticCertification(
            replace(original, references=(reference(record_id="2"),))
        )


def test_two_selected_revisions_of_one_provider_record_are_rejected() -> None:
    original = fields("hep-th")
    second = replace(original.projections[0], source_snapshot_id="snapshot-2")
    second_reference = replace(original.references[0], source_snapshot_id="snapshot-2")
    with pytest.raises(CertificationError, match="multiple selected revisions"):
        AutomaticCertification(
            replace(
                original,
                projections=(*original.projections, second),
                references=(*original.references, second_reference),
            )
        )


def test_legacy_review_contract_and_digest_shape_are_unchanged() -> None:
    legacy = FieldLedgerEvidence(
        "paper-1",
        (FieldWeight("hep-th", 1.0),),
        0.0,
        "unreviewed",
        "physics-field-ontology-v1",
        "provider-field-mapping-v1",
        FIELD_WEIGHTING_POLICY_VERSION,
        ("source-1",),
        "a" * 64,
    )
    before = canonical_digest(legacy)
    AutomaticCertification(fields("hep-th"))
    assert certify_field_ledger(legacy).state == "needs_review"
    assert canonical_digest(legacy) == before


def test_exact_initial_submission_retains_its_actual_date_basis() -> None:
    assessment = AutomaticCertification(dates("2020-01-13T12:30:00Z"))
    assert assessment.decision.state == "certified"
    assert assessment.value == ResolvedDateBasis(
        "arxiv-initial-submission",
        date(2020, 1, 13),
        "day",
        date(2020, 1, 13),
        date(2020, 1, 13),
    )


@pytest.mark.parametrize(
    ("value", "precision", "begin", "end"),
    [
        ("2020", "year", date(2020, 1, 1), date(2020, 12, 31)),
        ("2020-02", "month", date(2020, 2, 1), date(2020, 2, 29)),
    ],
)
def test_partial_dates_preserve_intervals_without_imputing_day(
    value: str, precision: str, begin: date, end: date
) -> None:
    assessment = AutomaticCertification(dates(value))
    assert assessment.decision.state == "insufficient_evidence"
    assert assessment.value == ResolvedDateBasis(
        "arxiv-initial-submission", None, precision, begin, end
    )


def test_no_earliest_mixed_date_selection_or_basis_fallback() -> None:
    original = dates("2020-01-13")
    online = ProviderDateFact(
        reference("crossref", "10.1234/example"),
        "journal-online-publication",
        "published-online",
        "2019-12-01",
    )
    combined = replace(original, facts=(*original.facts, online))
    assessment = AutomaticCertification(combined)
    assert isinstance(assessment.value, ResolvedDateBasis)
    assert assessment.value.exact_date == date(2020, 1, 13)
    assert assessment.evidence == combined
    selected_online = AutomaticCertification(
        replace(combined, declared_basis="journal-online-publication")
    )
    assert isinstance(selected_online.value, ResolvedDateBasis)
    assert selected_online.value.exact_date == date(2019, 12, 1)
    missing_print = AutomaticCertification(
        replace(combined, declared_basis="journal-print-publication")
    )
    assert missing_print.decision.state == "insufficient_evidence"


@pytest.mark.parametrize("source_field", ["updated", "ingested_at", "earliest_date"])
def test_unrelated_timestamps_cannot_substitute_for_declared_date(
    source_field: str,
) -> None:
    original = dates("2020-01-13")
    altered = replace(original.facts[0], source_field=source_field)
    assert AutomaticCertification(
        replace(original, facts=(altered,))
    ).decision.state == ("insufficient_evidence")


def test_same_basis_conflicting_dates_remain_conflicted() -> None:
    original = dates("2020-01-13")
    conflicting = replace(original.facts[0], value="2020-01-14")
    result = AutomaticCertification(
        replace(original, facts=(*original.facts, conflicting))
    )
    assert result.decision.state == "conflicted"
    assert isinstance(result.value, ResolvedDateBasis)
    assert result.value.exact_date is None


@pytest.mark.parametrize("value", ["2020-02-30", "2020-13", "2020-01-13T12:30:00", ""])
def test_invalid_or_timezone_ambiguous_dates_are_missing(value: str) -> None:
    assert (
        AutomaticCertification(dates(value)).decision.state == "insufficient_evidence"
    )


def test_inspire_exact_paper_native_id_is_not_a_human_signoff() -> None:
    result = AutomaticCertification(
        researcher("https://inspirehep.net/api/authors/12345")
    )
    assert result.decision.state == "certified"
    assert result.decision.reviewed_by is None
    assert result.decision.reviewed_at is None
    assert result.value == ResolvedResearcherIdentifiers((("inspire-author", "12345"),))


def test_orcid_requires_valid_checksum_and_paper_native_linkage() -> None:
    original = researcher()
    valid = ResearcherIdentifierFact(
        reference("inspire", "999"),
        "authors[].ORCID",
        "orcid",
        "0000-0002-1825-0097",
    )
    result = AutomaticCertification(replace(original, facts=(valid,)))
    assert result.decision.state == "certified"
    invalid = replace(valid, value="0000-0002-1825-0098")
    assert AutomaticCertification(
        replace(original, facts=(invalid,))
    ).decision.state == ("insufficient_evidence")
    current_profile = replace(valid, source_field="current_profile.orcid")
    assert (
        AutomaticCertification(
            replace(original, facts=(current_profile,))
        ).decision.state
        == "insufficient_evidence"
    )


@pytest.mark.parametrize(
    "value", ["Ada.Example.1", "Ada Example", "0", "https://evil.test/123"]
)
def test_arbitrary_strings_and_names_are_not_inspire_authority_ids(value: str) -> None:
    assert AutomaticCertification(researcher(value)).decision.state == (
        "insufficient_evidence"
    )


def test_two_same_namespace_identifiers_are_not_merged() -> None:
    original = researcher()
    conflicting = replace(original.facts[0], value="67890")
    assert (
        AutomaticCertification(
            replace(original, facts=(*original.facts, conflicting))
        ).decision.state
        == "conflicted"
    )


def test_no_input_has_a_caller_controlled_approval_flag() -> None:
    assessment = AutomaticCertification(fields("hep-th"))
    assert not verify_automatic_decision(
        fields("unknown"), replace(assessment.decision, state="certified")
    )
    forged_review = replace(
        assessment.decision,
        reviewed_by="fake-reviewer",
        reviewed_at=datetime(2026, 9, 5, tzinfo=UTC),
    )
    assert not verify_automatic_decision(assessment.evidence, forged_review)


def test_changed_fact_checksum_or_scope_invalidates_previous_decision() -> None:
    original = dates("2020-01-13")
    decision = AutomaticCertification(original).decision
    changed_fact = replace(original.facts[0], value="2020-01-14")
    assert not verify_automatic_decision(
        replace(original, facts=(changed_fact,)), decision
    )
    changed_reference = replace(original.facts[0].reference, checksum="b" * 64)
    changed = replace(original.facts[0], reference=changed_reference)
    assert not verify_automatic_decision(replace(original, facts=(changed,)), decision)
    changed_context = replace(CONTEXT, acquisition_scope="different-scope")
    assert not verify_automatic_decision(
        replace(original, context=changed_context), decision
    )


def test_missing_source_snapshot_fails_closed() -> None:
    original = dates("2020-01-13")
    changed = replace(
        original.facts[0],
        reference=replace(original.facts[0].reference, source_snapshot_id=None),
    )
    with pytest.raises(CertificationError, match="source snapshot"):
        AutomaticCertification(replace(original, facts=(changed,)))
