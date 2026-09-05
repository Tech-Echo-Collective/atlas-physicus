from dataclasses import dataclass
from datetime import date, datetime

from ..fields import PHYSICS_FIELD_ONTOLOGY_V1
from .contracts import (
    CertificationError,
    CertificationState,
    CertifiedCitationCohort,
    EvidenceReference,
    canonical_digest,
)

CITATION_CERTIFICATION_RULE_VERSION = "common-cutoff-non-self-citation-v1"
CITATION_POLICY_VERSION = "non-self-citation-cutoff-v1"
IMPACT_REFERENCE_COHORT_MINIMUM_V1 = 50
CITATION_MATURITY_MONTHS_V1 = 24


def _months_elapsed(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + end.month - start.month
    return months - (1 if end.day < start.day else 0)


def _timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


@dataclass(frozen=True)
class CitationCohortPopulationEvidence:
    """Reviewed exact eligible paper universe for one citation cohort."""

    cohort_key: tuple[str, int, str]
    cutoff: datetime
    dataset_version: str
    acquisition_scope: str
    eligible_paper_ids: tuple[str, ...]
    source_manifest_digest: str
    review_state: str
    reviewed_by: str
    reviewed_at: datetime

    @property
    def content_digest(self) -> str:
        return canonical_digest(
            (
                self.cohort_key,
                self.cutoff,
                self.dataset_version,
                self.acquisition_scope,
                tuple(sorted(self.eligible_paper_ids)),
            )
        )


def _validate_citation_cohort_population(
    evidence: CitationCohortPopulationEvidence,
) -> None:
    field_id, publication_year, document_type = evidence.cohort_key
    if (
        not PHYSICS_FIELD_ONTOLOGY_V1.contains(field_id)
        or PHYSICS_FIELD_ONTOLOGY_V1.get(field_id).node_kind != "field"
        or publication_year < 1900
        or not document_type.strip()
        or not evidence.dataset_version.strip()
        or not evidence.acquisition_scope.strip()
        or not evidence.reviewed_by.strip()
    ):
        raise CertificationError("citation cohort population identifiers are invalid")
    if (
        evidence.cutoff.tzinfo is None
        or evidence.cutoff.utcoffset() is None
        or evidence.reviewed_at.tzinfo is None
        or evidence.reviewed_at.utcoffset() is None
        or evidence.review_state != "reviewed-approved"
    ):
        raise CertificationError(
            "citation cohort population requires dated reviewed approval"
        )
    if not evidence.eligible_paper_ids or len(set(evidence.eligible_paper_ids)) != len(
        evidence.eligible_paper_ids
    ):
        raise CertificationError(
            "citation cohort population paper ids must be non-empty and unique"
        )
    if any(not paper_id.strip() for paper_id in evidence.eligible_paper_ids):
        raise CertificationError("citation cohort population paper id is empty")
    if evidence.source_manifest_digest != evidence.content_digest:
        raise CertificationError(
            "citation cohort population manifest does not match reviewed content"
        )


@dataclass(frozen=True)
class CitationObservationEvidence:
    paper_id: str
    dataset_version: str
    acquisition_scope: str
    citation_source: str
    raw_citation_count: int | None
    non_self_citation_count: int | None
    observed_at: datetime | None
    selected_cutoff: datetime | None
    publication_date: date
    field_id: str
    document_type: str
    source_reference: EvidenceReference | None
    citation_policy_version: str

    def __post_init__(self) -> None:
        if self.source_reference is not None and not isinstance(
            self.source_reference, EvidenceReference
        ):
            raise ValueError(
                "citation observation requires an exact evidence reference"
            )
        if any(
            not value.strip()
            for value in (
                self.paper_id,
                self.dataset_version,
                self.acquisition_scope,
                self.citation_source,
                self.field_id,
                self.document_type,
                self.citation_policy_version,
            )
        ):
            raise ValueError("citation observation identifiers must be non-empty")
        for value in (self.raw_citation_count, self.non_self_citation_count):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError("citation counts must be nonnegative integers")
        if (
            not PHYSICS_FIELD_ONTOLOGY_V1.contains(self.field_id)
            or PHYSICS_FIELD_ONTOLOGY_V1.get(self.field_id).node_kind != "field"
        ):
            raise ValueError("citation field must exist in the approved ontology")
        if (
            self.source_reference is not None
            and self.source_reference.provider != self.citation_source
        ):
            raise ValueError(
                "citation source must match the retained evidence provider"
            )


@dataclass(frozen=True)
class CitationObservationCertification:
    evidence: CitationObservationEvidence
    paper_id: str
    state: CertificationState
    non_self_citation_count: int | None
    cutoff: datetime | None
    cohort_key: tuple[str, int, str] | None
    mature: bool
    maturity_months: int
    evidence_digest: str
    reasons: tuple[str, ...]
    rule_version: str = CITATION_CERTIFICATION_RULE_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, CitationObservationEvidence):
            raise ValueError(
                "citation certification requires exact observation evidence"
            )
        if not self.paper_id.strip() or self.paper_id != self.evidence.paper_id:
            raise ValueError("citation certification must bind one non-empty paper id")
        if len(self.evidence_digest) != 64:
            raise ValueError("citation evidence digest must be SHA-256")
        try:
            int(self.evidence_digest, 16)
        except ValueError as error:
            raise ValueError("citation evidence digest must be hexadecimal") from error
        if self.evidence_digest != canonical_digest(self.evidence):
            raise ValueError(
                "citation certification digest does not match its evidence"
            )
        if self.maturity_months <= 0:
            raise ValueError("citation maturity months must be positive")
        if self.rule_version != CITATION_CERTIFICATION_RULE_VERSION:
            raise ValueError("citation observation certification rule is stale")
        if (
            self.state == "certified"
            and self.maturity_months != CITATION_MATURITY_MONTHS_V1
        ):
            raise ValueError(
                "certified citation observations require the v1 maturity window"
            )
        expected_key = (
            self.evidence.field_id,
            self.evidence.publication_date.year,
            self.evidence.document_type,
        )
        expected_mature = bool(
            self.evidence.selected_cutoff
            and _months_elapsed(
                self.evidence.publication_date,
                self.evidence.selected_cutoff.date(),
            )
            >= self.maturity_months
        )
        if (
            self.non_self_citation_count != self.evidence.non_self_citation_count
            or self.cutoff != self.evidence.selected_cutoff
            or self.cohort_key != expected_key
            or self.mature != expected_mature
        ):
            raise ValueError(
                "citation certification outputs do not reconstruct from evidence"
            )
        if (
            self.state == "certified"
            and self.cutoff is not None
            and not _timezone_aware(self.cutoff)
        ):
            raise ValueError("certified citation cutoff must include a timezone")
        if self.cohort_key is not None:
            field_id, year, document_type = self.cohort_key
            if not field_id.strip() or not document_type.strip() or year < 1900:
                raise ValueError("citation cohort key is invalid")
        if self.state == "certified" and (
            self.evidence.citation_policy_version != CITATION_POLICY_VERSION
            or self.evidence.source_reference is None
            or self.evidence.raw_citation_count is None
            or self.non_self_citation_count is None
            or self.non_self_citation_count < 0
            or self.non_self_citation_count > self.evidence.raw_citation_count
            or self.evidence.observed_at is None
            or self.cutoff is None
            or self.evidence.observed_at != self.cutoff
            or self.cutoff.date() < self.evidence.publication_date
            or self.cohort_key is None
            or not self.mature
            or self.reasons
        ):
            raise ValueError(
                "certified citation observations require count, cutoff, cohort, "
                "maturity, and no unresolved reasons"
            )
        if self.state != "certified" and not self.reasons:
            raise ValueError("non-certified citation observations require reasons")

    @property
    def certification_id(self) -> str:
        return f"citation-observation-{canonical_digest(self)}"


def certify_citation_observation(
    evidence: CitationObservationEvidence,
    *,
    maturity_months: int = CITATION_MATURITY_MONTHS_V1,
) -> CitationObservationCertification:
    """Require explicit non-self, cutoff, maturity, and immutable lineage."""

    if maturity_months <= 0:
        raise ValueError("citation maturity months must be positive")
    reasons: list[str] = []
    state: CertificationState = "certified"
    if maturity_months != CITATION_MATURITY_MONTHS_V1:
        state = "conflicted"
        reasons.append("citation observation uses a non-v1 maturity window")
    if evidence.citation_policy_version != CITATION_POLICY_VERSION:
        state = "conflicted"
        reasons.append("citation observation uses an unapproved policy version")
    if evidence.source_reference is None:
        state = "insufficient_evidence"
        reasons.append("citation source snapshot/checksum provenance is missing")
    if evidence.raw_citation_count is None:
        state = "insufficient_evidence"
        reasons.append("provider raw citation count is missing")
    if evidence.non_self_citation_count is None:
        state = "insufficient_evidence"
        reasons.append("provider non-self citation count is missing")
    if (
        evidence.raw_citation_count is not None
        and evidence.non_self_citation_count is not None
        and evidence.non_self_citation_count > evidence.raw_citation_count
    ):
        state = "conflicted"
        reasons.append("non-self citation count exceeds the provider raw count")
    if evidence.observed_at is None or evidence.selected_cutoff is None:
        state = "insufficient_evidence"
        reasons.append("citation observation or selected cutoff timestamp is missing")
    elif not _timezone_aware(evidence.observed_at) or not _timezone_aware(
        evidence.selected_cutoff
    ):
        state = "conflicted"
        reasons.append("citation timestamps must include an explicit timezone")
    elif evidence.observed_at != evidence.selected_cutoff:
        state = "conflicted"
        reasons.append("citation observation timestamp differs from the common cutoff")
    if (
        evidence.selected_cutoff is not None
        and evidence.selected_cutoff.date() < evidence.publication_date
    ):
        state = "conflicted"
        reasons.append("citation cutoff precedes the paper publication date")

    mature = bool(
        evidence.selected_cutoff
        and _months_elapsed(evidence.publication_date, evidence.selected_cutoff.date())
        >= maturity_months
    )
    if not mature:
        if state == "certified":
            state = "withheld"
        reasons.append("paper has not reached the configured citation maturity age")

    cohort_key = (
        evidence.field_id,
        evidence.publication_date.year,
        evidence.document_type,
    )
    return CitationObservationCertification(
        evidence=evidence,
        paper_id=evidence.paper_id,
        state=state,
        non_self_citation_count=evidence.non_self_citation_count,
        cutoff=evidence.selected_cutoff,
        cohort_key=cohort_key,
        mature=mature,
        maturity_months=maturity_months,
        evidence_digest=canonical_digest(evidence),
        reasons=tuple(dict.fromkeys(reasons)),
    )


@dataclass(frozen=True)
class CitationCohortCertification:
    cohort_key: tuple[str, int, str]
    cutoff: datetime
    dataset_version: str
    acquisition_scope: str
    state: CertificationState
    population_evidence: CitationCohortPopulationEvidence | None
    observations: tuple[CitationObservationCertification, ...]
    observation_certification_ids: tuple[str, ...]
    paper_count: int
    minimum_paper_count: int
    reasons: tuple[str, ...]
    rule_version: str = CITATION_CERTIFICATION_RULE_VERSION

    def __post_init__(self) -> None:
        if any(
            not isinstance(item, CitationObservationCertification)
            for item in self.observations
        ):
            raise ValueError(
                "citation cohorts require exact observation certifications"
            )
        if self.population_evidence is not None and not isinstance(
            self.population_evidence, CitationCohortPopulationEvidence
        ):
            raise ValueError("citation cohorts require exact population evidence")
        if not self.dataset_version.strip() or not self.acquisition_scope.strip():
            raise ValueError("citation cohort lineage identifiers must be non-empty")
        if self.cutoff.tzinfo is None or self.cutoff.utcoffset() is None:
            raise ValueError("citation cohort cutoff must include a timezone")
        if self.rule_version != CITATION_CERTIFICATION_RULE_VERSION:
            raise ValueError("citation cohort certification rule is stale")
        if self.population_evidence is not None:
            _validate_citation_cohort_population(self.population_evidence)
        if self.minimum_paper_count < 2:
            raise ValueError("citation cohort minimum must be at least two")
        if len(set(self.observation_certification_ids)) != len(
            self.observation_certification_ids
        ):
            raise ValueError("citation cohort observation proofs must be unique")
        expected_ids = tuple(
            sorted(item.certification_id for item in self.observations)
        )
        if expected_ids != self.observation_certification_ids:
            raise ValueError(
                "citation cohort proof ids must bind its exact observations"
            )
        if len({item.paper_id for item in self.observations}) != self.paper_count:
            raise ValueError("citation cohort paper count must match its observations")
        if self.state == "certified" and any(
            item.state != "certified"
            or item.maturity_months != CITATION_MATURITY_MONTHS_V1
            or item.cutoff != self.cutoff
            or item.cohort_key != self.cohort_key
            or item.evidence.dataset_version != self.dataset_version
            or item.evidence.acquisition_scope != self.acquisition_scope
            for item in self.observations
        ):
            raise ValueError(
                "certified citation cohorts require matching certified observations"
            )
        if self.state == "certified" and (
            self.population_evidence is None
            or self.population_evidence.cohort_key != self.cohort_key
            or self.population_evidence.cutoff != self.cutoff
            or self.population_evidence.dataset_version != self.dataset_version
            or self.population_evidence.acquisition_scope != self.acquisition_scope
            or set(self.population_evidence.eligible_paper_ids)
            != {item.paper_id for item in self.observations}
        ):
            raise ValueError(
                "certified citation cohort must bind its exact reviewed population"
            )
        if self.state == "certified" and not self.observation_certification_ids:
            raise ValueError("certified citation cohorts require observation proofs")
        if self.state == "certified" and self.paper_count < self.minimum_paper_count:
            raise ValueError("certified citation cohort is below its minimum size")
        if self.state != "certified" and not self.reasons:
            raise ValueError("non-certified citation cohorts must retain a reason")

    @property
    def certification_id(self) -> str:
        return f"citation-cohort-{canonical_digest(self)}"


def certify_citation_cohort(
    observations: tuple[CitationObservationCertification, ...],
    *,
    dataset_version: str,
    acquisition_scope: str,
    minimum_paper_count: int = IMPACT_REFERENCE_COHORT_MINIMUM_V1,
    population_evidence: CitationCohortPopulationEvidence | None = None,
) -> CitationCohortCertification:
    if minimum_paper_count < 2:
        raise ValueError("citation reference cohort minimum must be at least two")
    if not observations:
        raise ValueError("citation cohort requires observation evidence")
    if any(
        not isinstance(item, CitationObservationCertification) for item in observations
    ):
        raise ValueError("citation cohort requires exact observation certifications")
    keys = {item.cohort_key for item in observations}
    cutoffs = {item.cutoff for item in observations}
    if None in keys or None in cutoffs:
        raise ValueError("citation cohort observations require keys and cutoffs")
    reasons: list[str] = []
    state: CertificationState = "certified"
    if population_evidence is None:
        state = "insufficient_evidence"
        reasons.append("citation cohort lacks a reviewed exact eligible population")
    else:
        try:
            _validate_citation_cohort_population(population_evidence)
        except CertificationError as error:
            state = "conflicted"
            reasons.append(str(error))
    paper_ids = [item.paper_id for item in observations]
    unique_paper_count = len(set(paper_ids))
    certification_ids = [item.certification_id for item in observations]
    if unique_paper_count != len(paper_ids):
        state = "conflicted"
        reasons.append("citation cohort contains duplicate paper observations")
    if len(set(certification_ids)) != len(certification_ids):
        state = "conflicted"
        reasons.append("citation cohort contains duplicate observation proofs")
    if len(keys) != 1:
        state = "conflicted"
        reasons.append("citation cohort mixes field, year, or document type")
    if len(cutoffs) != 1:
        state = "conflicted"
        reasons.append("citation cohort does not share one exact observation cutoff")
    if any(item.state != "certified" for item in observations):
        if state == "certified":
            state = "insufficient_evidence"
        reasons.append("citation cohort contains non-certified observations")
    if any(
        item.maturity_months != CITATION_MATURITY_MONTHS_V1 for item in observations
    ):
        state = "conflicted"
        reasons.append("citation cohort observations use a non-v1 maturity window")
    if any(
        item.evidence.dataset_version != dataset_version
        or item.evidence.acquisition_scope != acquisition_scope
        for item in observations
    ):
        state = "conflicted"
        reasons.append("citation cohort observation lineage does not match")
    if population_evidence is not None and (
        population_evidence.cohort_key not in keys
        or population_evidence.cutoff not in cutoffs
        or population_evidence.dataset_version != dataset_version
        or population_evidence.acquisition_scope != acquisition_scope
        or set(population_evidence.eligible_paper_ids) != set(paper_ids)
    ):
        state = "conflicted"
        reasons.append(
            "citation observations differ from the reviewed eligible population"
        )
    if unique_paper_count < minimum_paper_count:
        if state == "certified":
            state = "insufficient_evidence"
        reasons.append("citation cohort is below the configured minimum size")

    key = next(iter(keys))
    cutoff = next(iter(cutoffs))
    assert key is not None
    assert cutoff is not None
    unique_observations = tuple(
        {item.certification_id: item for item in observations}[certification_id]
        for certification_id in sorted(set(certification_ids))
    )
    return CitationCohortCertification(
        cohort_key=key,
        cutoff=cutoff,
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        state=state,
        population_evidence=population_evidence,
        observations=unique_observations,
        observation_certification_ids=tuple(sorted(set(certification_ids))),
        paper_count=unique_paper_count,
        minimum_paper_count=minimum_paper_count,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def wrap_certified_citation_cohort[CohortT](
    cohort: CohortT,
    certification: CitationCohortCertification,
    *,
    dataset_version: str,
    acquisition_scope: str,
) -> CertifiedCitationCohort[CohortT]:
    if certification.state != "certified":
        raise ValueError("only a certified citation cohort can reach Impact")
    if (
        certification.dataset_version != dataset_version
        or certification.acquisition_scope != acquisition_scope
    ):
        raise ValueError("citation cohort certification lineage does not match")
    key = getattr(cohort, "key", None)
    observed_at = getattr(cohort, "observed_at", None)
    citations = getattr(cohort, "citations", None)
    if (
        key != certification.cohort_key
        or observed_at != certification.cutoff.date()
        or not isinstance(citations, tuple)
    ):
        raise ValueError("citation reference cohort does not match its certification")
    certified_values = {
        item.paper_id: item.non_self_citation_count
        for item in certification.observations
        if item.state == "certified"
    }
    supplied_values = dict(citations)
    if len(supplied_values) != len(citations) or supplied_values != certified_values:
        raise ValueError(
            "citation reference cohort values do not match certified observations"
        )
    return CertifiedCitationCohort(
        cohort=cohort,
        certification_proof=certification,
        certification_id=certification.certification_id,
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        cutoff=certification.cutoff,
        evidence_digest=canonical_digest(cohort),
        rule_version=CITATION_CERTIFICATION_RULE_VERSION,
    )


def impact_comparable_paper_ids(
    partition: object,
    cohorts: tuple[CertifiedCitationCohort[object], ...],
) -> tuple[str, ...]:
    """Return exact partition papers backed by activation-grade Impact cohorts."""

    field_id = getattr(partition, "field_id", None)
    cutoff = getattr(partition, "as_of_date", None)
    papers = getattr(partition, "papers", None)
    if (
        not isinstance(field_id, str)
        or not isinstance(cutoff, date)
        or not isinstance(papers, tuple)
    ):
        raise CertificationError("Impact partition structure is invalid")
    cohorts_by_key = {getattr(item.cohort, "key", None): item for item in cohorts}
    if len(cohorts_by_key) != len(cohorts):
        raise CertificationError("Impact cohort inventory contains duplicate keys")
    comparable: list[str] = []
    for paper in papers:
        publication_date = getattr(paper, "publication_date", None)
        document_type = getattr(paper, "document_type", None)
        paper_id = getattr(paper, "paper_id", None)
        if (
            not isinstance(publication_date, date)
            or not isinstance(document_type, str)
            or not isinstance(paper_id, str)
        ):
            raise CertificationError("Impact paper structure is invalid")
        key = (field_id, publication_date.year, document_type)
        certified = cohorts_by_key.get(key)
        if certified is None:
            raise CertificationError(
                "Impact cohort inventory is incomplete for the partition"
            )
        proof = certified.certification_proof
        if (
            not isinstance(proof, CitationCohortCertification)
            or proof.minimum_paper_count != IMPACT_REFERENCE_COHORT_MINIMUM_V1
            or proof.paper_count < IMPACT_REFERENCE_COHORT_MINIMUM_V1
            or any(
                item.maturity_months != CITATION_MATURITY_MONTHS_V1
                for item in proof.observations
            )
            or certified.cutoff.date() != cutoff
        ):
            raise CertificationError(
                "Impact cohort does not satisfy the v1 cohort policy"
            )
        values = dict(getattr(certified.cohort, "citations", ()))
        supplied = getattr(paper, "citation_count", None)
        certified_value = values.get(paper_id)
        if supplied is None:
            if certified_value is not None:
                raise CertificationError(
                    "partition citation value differs from its certified cohort"
                )
            continue
        if certified_value is None or supplied != certified_value:
            raise CertificationError(
                "partition citation value differs from its certified cohort"
            )
        if getattr(paper, "citation_observed_at", None) != cutoff:
            raise CertificationError("Impact partition citation cutoff differs")
        comparable.append(paper_id)
    return tuple(sorted(comparable))
