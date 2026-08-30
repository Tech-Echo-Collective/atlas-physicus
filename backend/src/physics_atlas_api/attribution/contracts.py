"""Durable, versioned contracts for conservative scientific attribution."""

from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

AffiliationResolutionStatus = Literal["resolved", "unresolved", "ambiguous"]


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


@dataclass(frozen=True)
class ScientificAttributionPolicy:
    """Human-readable contract that fixes the meaning of one calculation version."""

    policy_id: str
    version: str
    paper_total_weight: Fraction
    author_weight_rule: str
    affiliation_weight_rule: str
    unresolved_evidence_rule: str
    author_order_rule: str
    corresponding_author_rule: str
    contribution_evidence_rule: str

    def __post_init__(self) -> None:
        for field_name in (
            "policy_id",
            "version",
            "author_weight_rule",
            "affiliation_weight_rule",
            "unresolved_evidence_rule",
            "author_order_rule",
            "corresponding_author_rule",
            "contribution_evidence_rule",
        ):
            _require_text(str(getattr(self, field_name)), field_name)
        if self.paper_total_weight != Fraction(1, 1):
            raise ValueError("a scientific attribution policy must conserve one paper")


FRACTIONAL_ATTRIBUTION_V1 = ScientificAttributionPolicy(
    policy_id="physics-atlas-fractional-attribution",
    version="fractional-attribution-v1",
    paper_total_weight=Fraction(1, 1),
    author_weight_rule=(
        "Each provider author appearance receives exactly 1 / N_authors."
    ),
    affiliation_weight_rule=(
        "Each author share is divided equally across distinct paper-time "
        "affiliation assertions."
    ),
    unresolved_evidence_rule=(
        "Unresolved or absent paper-time affiliation evidence remains an explicit "
        "withheld share and is never reassigned or converted to zero."
    ),
    author_order_rule="Author order does not change contribution weight.",
    corresponding_author_rule=(
        "Corresponding-author status does not change contribution weight."
    ),
    contribution_evidence_rule=(
        "Contribution statements are preserved as non-numeric provenance and do "
        "not change v1 weights."
    ),
)


@dataclass(frozen=True)
class ContributionEvidence:
    """Non-numeric contribution provenance deliberately excluded from v1 weights."""

    evidence_type: str
    statement: str
    source: str
    version: str

    def __post_init__(self) -> None:
        for field_name in ("evidence_type", "statement", "source", "version"):
            _require_text(str(getattr(self, field_name)), field_name)


@dataclass(frozen=True)
class PaperTimeAffiliationAssertion:
    """One source assertion about an author's affiliation on a specific paper."""

    assertion_id: str
    resolution_status: AffiliationResolutionStatus
    source: str
    source_record_id: str
    evidence_version: str
    institution_id: str | None = None
    country_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "assertion_id",
            "source",
            "source_record_id",
            "evidence_version",
        ):
            _require_text(str(getattr(self, field_name)), field_name)
        if self.resolution_status == "resolved":
            if self.institution_id is None or self.country_id is None:
                raise ValueError(
                    "a resolved affiliation requires canonical institution and country"
                )
            _require_text(self.institution_id, "institution_id")
            _require_text(self.country_id, "country_id")
        elif self.institution_id is not None or self.country_id is not None:
            raise ValueError(
                "an unresolved or ambiguous affiliation cannot name a canonical entity"
            )


@dataclass(frozen=True)
class AuthorAttributionInput:
    """One provider author slot, whether or not researcher identity resolved."""

    author_slot_id: str
    author_position: int
    researcher_id: str | None = None
    affiliations: tuple[PaperTimeAffiliationAssertion, ...] = ()
    contribution_evidence: tuple[ContributionEvidence, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.author_slot_id, "author_slot_id")
        if self.author_position < 1:
            raise ValueError("author_position must be positive")
        if self.researcher_id is not None:
            _require_text(self.researcher_id, "researcher_id")
        object.__setattr__(self, "affiliations", tuple(self.affiliations))
        object.__setattr__(
            self, "contribution_evidence", tuple(self.contribution_evidence)
        )
