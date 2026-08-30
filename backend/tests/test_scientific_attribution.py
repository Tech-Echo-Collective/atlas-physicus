from fractions import Fraction

import pytest

from physics_atlas_api.attribution import (
    FRACTIONAL_ATTRIBUTION_V1,
    AuthorAttributionInput,
    ContributionEvidence,
    PaperTimeAffiliationAssertion,
    calculate_fractional_attribution,
)


def affiliation(
    assertion_id: str,
    institution_id: str | None = None,
    country_id: str | None = None,
    *,
    status: str = "resolved",
) -> PaperTimeAffiliationAssertion:
    return PaperTimeAffiliationAssertion(
        assertion_id=assertion_id,
        resolution_status=status,  # type: ignore[arg-type]
        source="deterministic attribution fixture",
        source_record_id=f"source-{assertion_id}",
        evidence_version="fixture-v1",
        institution_id=institution_id,
        country_id=country_id,
    )


def author(
    position: int,
    *affiliations: PaperTimeAffiliationAssertion,
    researcher_id: str | None = None,
    contribution_evidence: tuple[ContributionEvidence, ...] = (),
) -> AuthorAttributionInput:
    return AuthorAttributionInput(
        author_slot_id=f"author-slot-{position}",
        author_position=position,
        researcher_id=researcher_id,
        affiliations=affiliations,
        contribution_evidence=contribution_evidence,
    )


def test_policy_is_explicit_versioned_and_conserves_one_paper() -> None:
    policy = FRACTIONAL_ATTRIBUTION_V1

    assert policy.version == "fractional-attribution-v1"
    assert policy.paper_total_weight == Fraction(1, 1)
    assert "Author order does not change" in policy.author_order_rule
    assert "do not change v1 weights" in policy.contribution_evidence_rule


def test_single_author_single_affiliation_receives_one() -> None:
    result = calculate_fractional_attribution(
        "paper-one",
        [author(1, affiliation("a", "institution-a", "country-a"))],
    )

    assert result.total_weight == Fraction(1, 1)
    assert result.withheld_weight == 0
    assert result.institution_weights() == {"institution-a": Fraction(1, 1)}
    assert result.country_weights() == {"country-a": Fraction(1, 1)}


def test_multiple_authors_at_one_institution_aggregate_to_one() -> None:
    result = calculate_fractional_attribution(
        "paper-shared",
        [
            author(2, affiliation("b", "institution-a", "country-a")),
            author(1, affiliation("a", "institution-a", "country-a")),
        ],
    )

    assert [share.author_position for share in result.shares] == [1, 2]
    assert {share.author_weight for share in result.shares} == {Fraction(1, 2)}
    assert result.institution_weights() == {"institution-a": Fraction(1, 1)}


def test_multiple_authors_at_multiple_institutions_split_the_paper() -> None:
    result = calculate_fractional_attribution(
        "paper-two-institutions",
        [
            author(1, affiliation("a", "institution-a", "country-a")),
            author(2, affiliation("b", "institution-b", "country-b")),
        ],
    )

    assert result.institution_weights() == {
        "institution-a": Fraction(1, 2),
        "institution-b": Fraction(1, 2),
    }
    assert result.country_weights() == {
        "country-a": Fraction(1, 2),
        "country-b": Fraction(1, 2),
    }


def test_one_author_with_multiple_affiliations_splits_author_share() -> None:
    result = calculate_fractional_attribution(
        "paper-multiple-affiliations",
        [
            author(
                1,
                affiliation("a", "institution-a", "country-a"),
                affiliation("b", "institution-b", "country-b"),
            )
        ],
    )

    assert [share.weight for share in result.shares] == [
        Fraction(1, 2),
        Fraction(1, 2),
    ]
    assert result.institution_weights() == {
        "institution-a": Fraction(1, 2),
        "institution-b": Fraction(1, 2),
    }


def test_unresolved_affiliation_is_explicitly_withheld_not_zero() -> None:
    result = calculate_fractional_attribution(
        "paper-unresolved",
        [author(1, affiliation("unknown", status="unresolved"))],
    )

    assert result.total_weight == 1
    assert result.allocated_weight == 0
    assert result.withheld_weight == 1
    assert result.institution_weights() == {}
    assert result.country_weights() == {}
    assert result.shares[0].status == "withheld-unresolved-affiliation"


def test_valid_and_unresolved_affiliations_do_not_overcredit_valid_entity() -> None:
    result = calculate_fractional_attribution(
        "paper-partial",
        [
            author(
                1,
                affiliation("known", "institution-a", "country-a"),
                affiliation("unknown", status="unresolved"),
            )
        ],
    )

    assert result.institution_weights() == {"institution-a": Fraction(1, 2)}
    assert result.allocated_weight == Fraction(1, 2)
    assert result.withheld_weight == Fraction(1, 2)
    assert result.coverage == Fraction(1, 2)


def test_absent_affiliation_evidence_is_withheld_not_assumed_zero() -> None:
    result = calculate_fractional_attribution("paper-no-affiliation", [author(1)])

    assert result.total_weight == 1
    assert result.shares[0].status == "withheld-no-affiliation"
    assert result.institution_weights() == {}
    assert "unknown-institution" not in result.institution_weights()


def test_unresolved_researcher_can_retain_resolved_institution_evidence() -> None:
    result = calculate_fractional_attribution(
        "paper-unresolved-researcher",
        [
            author(
                1,
                affiliation("known", "institution-a", "country-a"),
                researcher_id=None,
            )
        ],
    )

    assert result.institution_weights() == {"institution-a": Fraction(1, 1)}
    assert result.country_weights() == {"country-a": Fraction(1, 1)}
    assert result.researcher_weights() == {}


def test_duplicate_assertions_do_not_dilute_an_author_share() -> None:
    first = affiliation("a", "institution-a", "country-a")
    repeated_entity = affiliation("a-second-source", "institution-a", "country-a")
    second = affiliation("b", "institution-b", "country-b")
    result = calculate_fractional_attribution(
        "paper-duplicates",
        [author(1, first, first, repeated_entity, second)],
    )

    assert len(result.shares) == 2
    assert result.institution_weights() == {
        "institution-a": Fraction(1, 2),
        "institution-b": Fraction(1, 2),
    }
    assert result.shares[0].affiliation_assertion_ids == (
        "a",
        "a-second-source",
    )


def test_large_collaboration_conserves_exact_weight() -> None:
    collaboration_size = 2_000
    result = calculate_fractional_attribution(
        "paper-large-collaboration",
        [
            author(
                position,
                affiliation(f"affiliation-{position}", "institution-a", "country-a"),
            )
            for position in range(1, collaboration_size + 1)
        ],
    )

    assert len(result.shares) == collaboration_size
    assert result.shares[0].author_weight == Fraction(1, collaboration_size)
    assert result.total_weight == Fraction(1, 1)
    assert result.institution_weights() == {"institution-a": Fraction(1, 1)}


def test_contribution_evidence_never_changes_numeric_weights() -> None:
    evidence = ContributionEvidence(
        evidence_type="CRediT-like statement",
        statement="Conceptualization and software were reported by the provider.",
        source="deterministic provider fixture",
        version="fixture-v1",
    )
    baseline = calculate_fractional_attribution(
        "paper-contribution",
        [
            author(1, affiliation("a", "institution-a", "country-a")),
            author(2, affiliation("b", "institution-b", "country-b")),
        ],
    )
    with_evidence = calculate_fractional_attribution(
        "paper-contribution",
        [
            author(
                1,
                affiliation("a", "institution-a", "country-a"),
                contribution_evidence=(evidence,),
            ),
            author(2, affiliation("b", "institution-b", "country-b")),
        ],
    )

    assert with_evidence.shares == baseline.shares
    assert with_evidence.institution_weights() == baseline.institution_weights()


def test_missing_author_evidence_fails_instead_of_becoming_zero() -> None:
    with pytest.raises(ValueError, match="missing authors are not zero"):
        calculate_fractional_attribution("paper-missing-authors", [])
