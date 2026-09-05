from dataclasses import dataclass

from .citations import CITATION_CERTIFICATION_RULE_VERSION
from .contracts import (
    CERTIFICATION_COVERAGE_MINIMUMS_V1,
    CERTIFICATION_POLICY_VERSION,
    EvidenceKind,
)
from .fields import FIELD_CERTIFICATION_RULE_VERSION
from .institutions import INSTITUTION_CERTIFICATION_RULE_VERSION

_BASE_PAPER_EVIDENCE: tuple[EvidenceKind, ...] = (
    "canonical-paper-identity",
    "publication-metric-date",
    "researcher-identity",
    "field-classification",
    "field-weight-conservation",
    "provenance-completeness",
)

_METRIC_WINDOW_YEARS = {
    "research_activity_score": 3,
    "research_impact": 3,
    "collaboration": 3,
    "research_diversity": 3,
    "momentum": 6,
}


def evidence_rule_version(evidence_kind: EvidenceKind) -> str:
    return {
        "canonical-institution": INSTITUTION_CERTIFICATION_RULE_VERSION,
        "field-classification": FIELD_CERTIFICATION_RULE_VERSION,
        "field-weight-conservation": FIELD_CERTIFICATION_RULE_VERSION,
        "citation-observation": CITATION_CERTIFICATION_RULE_VERSION,
        "citation-cutoff-compatibility": CITATION_CERTIFICATION_RULE_VERSION,
    }.get(evidence_kind, CERTIFICATION_POLICY_VERSION)


@dataclass(frozen=True)
class CertificationCoveragePolicy:
    paper_time_affiliation: float = 0.90
    canonical_institution: float = 0.95
    citation: float = 0.90
    field_attribution: float = 0.90
    collaboration_relationship: float = 0.90

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if not 0 <= value <= 1:
                raise ValueError(f"{name} certification threshold must be within [0,1]")


METRIC_CERTIFICATION_COVERAGE_V1 = CertificationCoveragePolicy()


def required_paper_evidence(
    metric_id: str,
    entity_type: str,
) -> tuple[EvidenceKind, ...]:
    """Return evidence kinds required before one paper can reach a v1 formula."""

    if metric_id not in _METRIC_WINDOW_YEARS:
        raise ValueError(f"unknown Metric System v1 metric: {metric_id}")
    if entity_type not in {"researcher", "institution", "country"}:
        raise ValueError(f"unsupported metric entity type: {entity_type}")

    kinds = list(_BASE_PAPER_EVIDENCE)
    if entity_type in {"institution", "country"}:
        kinds.extend(("paper-time-affiliation", "canonical-institution"))
    if metric_id == "research_impact":
        kinds.extend(("citation-observation", "citation-cutoff-compatibility"))
    if metric_id == "collaboration":
        kinds.append("collaboration-relationship")
    return tuple(kinds)


def required_coverage_evidence(
    metric_id: str,
    entity_type: str,
) -> tuple[EvidenceKind, ...]:
    if metric_id not in _METRIC_WINDOW_YEARS:
        raise ValueError(f"unknown Metric System v1 metric: {metric_id}")
    kinds: list[EvidenceKind] = ["field-classification"]
    if entity_type in {"institution", "country"}:
        kinds.extend(("paper-time-affiliation", "canonical-institution"))
    if metric_id == "research_impact":
        kinds.append("citation-observation")
    if metric_id == "collaboration":
        kinds.append("collaboration-relationship")
    return tuple(kinds)


def required_window_years(metric_id: str, terminal_year: int) -> tuple[int, ...]:
    try:
        count = _METRIC_WINDOW_YEARS[metric_id]
    except KeyError as error:
        raise ValueError(f"unknown Metric System v1 metric: {metric_id}") from error
    return tuple(range(terminal_year - count + 1, terminal_year + 1))


def coverage_minimum(
    evidence_kind: EvidenceKind,
    policy: CertificationCoveragePolicy = METRIC_CERTIFICATION_COVERAGE_V1,
) -> float:
    values = {
        "paper-time-affiliation": policy.paper_time_affiliation,
        "canonical-institution": policy.canonical_institution,
        "citation-observation": policy.citation,
        "field-classification": policy.field_attribution,
        "collaboration-relationship": policy.collaboration_relationship,
    }
    try:
        value = values[evidence_kind]
    except KeyError as error:
        raise ValueError(
            f"{evidence_kind} does not define a coverage threshold"
        ) from error
    if policy is METRIC_CERTIFICATION_COVERAGE_V1:
        assert value == CERTIFICATION_COVERAGE_MINIMUMS_V1[evidence_kind]
    return value
