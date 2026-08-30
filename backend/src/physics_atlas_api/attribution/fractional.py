"""Pure, exact Fractional Attribution v1 calculation."""

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from .contracts import (
    FRACTIONAL_ATTRIBUTION_V1,
    AuthorAttributionInput,
    PaperTimeAffiliationAssertion,
    ScientificAttributionPolicy,
)

AttributionShareStatus = Literal[
    "allocated",
    "withheld-unresolved-affiliation",
    "withheld-ambiguous-affiliation",
    "withheld-no-affiliation",
]


@dataclass(frozen=True)
class AttributionShare:
    """One exact allocated or explicitly withheld part of a paper."""

    paper_id: str
    author_slot_id: str
    author_position: int
    researcher_id: str | None
    affiliation_assertion_ids: tuple[str, ...]
    institution_id: str | None
    country_id: str | None
    author_weight: Fraction
    weight: Fraction
    status: AttributionShareStatus


@dataclass(frozen=True)
class FractionalAttributionResult:
    """Conserved paper shares with missing evidence kept separate from zero."""

    paper_id: str
    policy_id: str
    policy_version: str
    shares: tuple[AttributionShare, ...]

    @property
    def total_weight(self) -> Fraction:
        return sum((share.weight for share in self.shares), start=Fraction(0, 1))

    @property
    def allocated_weight(self) -> Fraction:
        return sum(
            (share.weight for share in self.shares if share.status == "allocated"),
            start=Fraction(0, 1),
        )

    @property
    def withheld_weight(self) -> Fraction:
        return sum(
            (share.weight for share in self.shares if share.status != "allocated"),
            start=Fraction(0, 1),
        )

    @property
    def coverage(self) -> Fraction:
        """Return allocated evidence share without converting absence to zero."""

        return self.allocated_weight / self.total_weight

    def institution_weights(self) -> dict[str, Fraction]:
        weights: dict[str, Fraction] = {}
        for share in self.shares:
            if share.status != "allocated" or share.institution_id is None:
                continue
            weights[share.institution_id] = (
                weights.get(share.institution_id, Fraction(0, 1)) + share.weight
            )
        return weights

    def country_weights(self) -> dict[str, Fraction]:
        weights: dict[str, Fraction] = {}
        for share in self.shares:
            if share.status != "allocated" or share.country_id is None:
                continue
            weights[share.country_id] = (
                weights.get(share.country_id, Fraction(0, 1)) + share.weight
            )
        return weights

    def researcher_weights(self) -> dict[str, Fraction]:
        """Aggregate known researchers only; unresolved identity remains absent."""

        weights: dict[str, Fraction] = {}
        for share in self.shares:
            if share.researcher_id is None:
                continue
            weights[share.researcher_id] = (
                weights.get(share.researcher_id, Fraction(0, 1)) + share.weight
            )
        return weights


@dataclass
class _EffectiveAffiliation:
    assertion_ids: list[str]
    assertion: PaperTimeAffiliationAssertion


def _effective_affiliations(
    assertions: Sequence[PaperTimeAffiliationAssertion],
) -> list[_EffectiveAffiliation]:
    """Deduplicate exact evidence and repeated canonical institution assertions."""

    by_assertion_id: dict[str, PaperTimeAffiliationAssertion] = {}
    for assertion in assertions:
        existing_assertion = by_assertion_id.get(assertion.assertion_id)
        if existing_assertion is not None and existing_assertion != assertion:
            raise ValueError(
                f"conflicting affiliation assertion: {assertion.assertion_id}"
            )
        by_assertion_id.setdefault(assertion.assertion_id, assertion)

    effective: list[_EffectiveAffiliation] = []
    effective_by_key: dict[tuple[str, str], _EffectiveAffiliation] = {}
    for assertion in by_assertion_id.values():
        key = (
            ("resolved", str(assertion.institution_id))
            if assertion.resolution_status == "resolved"
            else (assertion.resolution_status, assertion.assertion_id)
        )
        effective_item = effective_by_key.get(key)
        if effective_item is None:
            item = _EffectiveAffiliation([assertion.assertion_id], assertion)
            effective_by_key[key] = item
            effective.append(item)
            continue
        if (
            effective_item.assertion.institution_id != assertion.institution_id
            or effective_item.assertion.country_id != assertion.country_id
            or effective_item.assertion.resolution_status != assertion.resolution_status
        ):
            raise ValueError(
                "canonical affiliation evidence is internally inconsistent"
            )
        effective_item.assertion_ids.append(assertion.assertion_id)
    return effective


def _authors_by_position(
    authors: Sequence[AuthorAttributionInput],
) -> list[AuthorAttributionInput]:
    if not authors:
        raise ValueError(
            "paper attribution requires author evidence; missing authors are not zero"
        )
    count = len(authors)
    by_position: list[AuthorAttributionInput | None] = [None] * count
    slot_ids: set[str] = set()
    for author in authors:
        if author.author_slot_id in slot_ids:
            raise ValueError(f"duplicate author slot: {author.author_slot_id}")
        slot_ids.add(author.author_slot_id)
        if author.author_position > count:
            raise ValueError("author positions must be contiguous from one")
        index = author.author_position - 1
        if by_position[index] is not None:
            raise ValueError(f"duplicate author position: {author.author_position}")
        by_position[index] = author
    if any(author is None for author in by_position):
        raise ValueError("author positions must be contiguous from one")
    return [author for author in by_position if author is not None]


def calculate_fractional_attribution(
    paper_id: str,
    authors: Sequence[AuthorAttributionInput],
    *,
    policy: ScientificAttributionPolicy = FRACTIONAL_ATTRIBUTION_V1,
) -> FractionalAttributionResult:
    """Allocate exactly one paper without inferring contribution or missing evidence."""

    if not paper_id.strip():
        raise ValueError("paper_id must be non-empty")
    ordered_authors = _authors_by_position(authors)
    author_weight = policy.paper_total_weight / len(ordered_authors)
    shares: list[AttributionShare] = []

    for author in ordered_authors:
        effective_affiliations = _effective_affiliations(author.affiliations)
        if not effective_affiliations:
            shares.append(
                AttributionShare(
                    paper_id=paper_id,
                    author_slot_id=author.author_slot_id,
                    author_position=author.author_position,
                    researcher_id=author.researcher_id,
                    affiliation_assertion_ids=(),
                    institution_id=None,
                    country_id=None,
                    author_weight=author_weight,
                    weight=author_weight,
                    status="withheld-no-affiliation",
                )
            )
            continue

        affiliation_weight = author_weight / len(effective_affiliations)
        for effective in effective_affiliations:
            assertion = effective.assertion
            status: AttributionShareStatus
            if assertion.resolution_status == "resolved":
                status = "allocated"
            elif assertion.resolution_status == "ambiguous":
                status = "withheld-ambiguous-affiliation"
            else:
                status = "withheld-unresolved-affiliation"
            shares.append(
                AttributionShare(
                    paper_id=paper_id,
                    author_slot_id=author.author_slot_id,
                    author_position=author.author_position,
                    researcher_id=author.researcher_id,
                    affiliation_assertion_ids=tuple(effective.assertion_ids),
                    institution_id=assertion.institution_id,
                    country_id=assertion.country_id,
                    author_weight=author_weight,
                    weight=affiliation_weight,
                    status=status,
                )
            )

    result = FractionalAttributionResult(
        paper_id=paper_id,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        shares=tuple(shares),
    )
    if result.total_weight != policy.paper_total_weight:
        raise AssertionError("fractional attribution failed to conserve paper weight")
    return result
