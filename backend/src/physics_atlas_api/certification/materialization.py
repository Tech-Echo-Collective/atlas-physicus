import math
from collections import defaultdict

from ..attribution import FRACTIONAL_ATTRIBUTION_V1
from ..fields import PHYSICS_FIELD_ONTOLOGY_VERSION, PROVIDER_FIELD_MAPPING_VERSION
from .citations import CITATION_POLICY_VERSION, impact_comparable_paper_ids
from .contracts import (
    CERTIFICATION_POLICY_VERSION,
    CertificationError,
    CertifiedMetricPartition,
    CoverageCertification,
    EvidenceCertificationDecision,
    EvidenceKind,
    MetricPartitionCertification,
    PaperEvidenceCertification,
    canonical_digest,
)
from .coverage import COVERAGE_SUBJECT_TYPE, validate_coverage_certification
from .populations import (
    CertifiedMetricPopulation,
    metric_population_coverage_ledger,
)
from .projections import paper_evidence_value_digest
from .rules import (
    coverage_minimum,
    evidence_rule_version,
    required_coverage_evidence,
    required_paper_evidence,
)
from .years import METRIC_WINDOW_CERTIFICATION_RULE_VERSION, CertifiedMetricWindow

_COVERAGE_ATTRIBUTE: dict[EvidenceKind, str] = {
    "paper-time-affiliation": "paper_time_affiliation",
    "canonical-institution": "canonical_institution",
    "citation-observation": "citation",
    "field-classification": "field_attribution",
    "collaboration-relationship": "collaboration_relationship",
}


def _required_string(value: object, attribute: str) -> str:
    item = getattr(value, attribute, None)
    if not isinstance(item, str) or not item.strip():
        raise CertificationError(f"metric partition lacks {attribute}")
    return item


def _required_integer(value: object, attribute: str) -> int:
    item = getattr(value, attribute, None)
    if not isinstance(item, int) or isinstance(item, bool):
        raise CertificationError(f"metric partition lacks {attribute}")
    return item


def _paper_ids(partition: object) -> tuple[str, ...]:
    papers = getattr(partition, "papers", None)
    if not isinstance(papers, tuple):
        raise CertificationError("metric partition papers must be an immutable tuple")
    identifiers = tuple(_required_string(item, "paper_id") for item in papers)
    if len(set(identifiers)) != len(identifiers):
        raise CertificationError("metric partition contains duplicate papers")
    return identifiers


def _paper_objects(partition: object) -> dict[str, object]:
    papers = getattr(partition, "papers", None)
    if not isinstance(papers, tuple):
        raise CertificationError("metric partition papers must be an immutable tuple")
    return {_required_string(item, "paper_id"): item for item in papers}


def _explicit_missing_is_usable(
    paper: object,
    metric_id: str,
    entity_type: str,
    kind: EvidenceKind,
) -> bool:
    if metric_id == "research_impact" and kind == "citation-observation":
        return getattr(paper, "citation_count", None) is None
    if metric_id == "research_impact" and kind == "citation-cutoff-compatibility":
        return getattr(paper, "citation_observed_at", None) is None
    if metric_id == "collaboration" and kind == "collaboration-relationship":
        attribute = {
            "researcher": "collaborative",
            "institution": "cross_institution",
            "country": "international",
        }[entity_type]
        return getattr(paper, attribute, None) is None
    return False


def _observed_formula_mass(
    papers: tuple[object, ...],
    evidence_kind: EvidenceKind,
    entity_type: str,
    comparable_citation_ids: frozenset[str] = frozenset(),
) -> float:
    relationship_attribute = {
        "researcher": "collaborative",
        "institution": "cross_institution",
        "country": "international",
    }[entity_type]
    return math.fsum(
        float(getattr(paper, "attribution_weight", 0.0))
        for paper in papers
        if (
            evidence_kind != "citation-observation"
            or getattr(paper, "paper_id", None) in comparable_citation_ids
        )
        and (
            evidence_kind != "collaboration-relationship"
            or getattr(paper, relationship_attribute, None) is not None
        )
    )


def _formula_inputs(
    papers: tuple[object, ...],
    evidence_kind: EvidenceKind,
    entity_type: str,
    comparable_citation_ids: frozenset[str] = frozenset(),
) -> tuple[tuple[str, float], ...]:
    relationship_attribute = {
        "researcher": "collaborative",
        "institution": "cross_institution",
        "country": "international",
    }[entity_type]
    return tuple(
        sorted(
            (
                _required_string(paper, "paper_id"),
                float(getattr(paper, "attribution_weight", 0.0)),
            )
            for paper in papers
            if (
                evidence_kind != "citation-observation"
                or getattr(paper, "paper_id", None) in comparable_citation_ids
            )
            and (
                evidence_kind != "collaboration-relationship"
                or getattr(paper, relationship_attribute, None) is not None
            )
        )
    )


def build_certified_metric_partition[PartitionT](
    partition: PartitionT,
    *,
    metric_id: str,
    decisions: tuple[EvidenceCertificationDecision, ...],
    coverage: tuple[CoverageCertification, ...],
    window: CertifiedMetricWindow,
    population: CertifiedMetricPopulation,
) -> CertifiedMetricPartition[PartitionT]:
    """Build the only calculation-eligible projection from reviewed decisions."""

    dataset_version = _required_string(partition, "dataset_version")
    acquisition_scope = _required_string(partition, "acquisition_scope")
    entity_type = _required_string(partition, "entity_type")
    terminal_year = _required_integer(partition, "terminal_year")
    if (
        getattr(partition, "attribution_policy_version", None)
        != FRACTIONAL_ATTRIBUTION_V1.version
        or getattr(partition, "ontology_version", None)
        != PHYSICS_FIELD_ONTOLOGY_VERSION
        or getattr(partition, "mapping_policy_version", None)
        != PROVIDER_FIELD_MAPPING_VERSION
        or getattr(partition, "citation_policy_version", None)
        != CITATION_POLICY_VERSION
    ):
        raise CertificationError(
            "metric partition uses an unapproved scientific policy version"
        )
    if not isinstance(window, CertifiedMetricWindow):
        raise CertificationError(
            "metric partition requires a reconstructable certified window"
        )
    if not isinstance(population, CertifiedMetricPopulation):
        raise CertificationError(
            "metric partition requires a reconstructable eligibility population"
        )
    if population.window != window:
        raise CertificationError("metric population targets another metric window")
    window_certification = window.certification
    if window_certification.state != "certified":
        raise CertificationError("metric window is not certified")
    if window_certification.rule_version != METRIC_WINDOW_CERTIFICATION_RULE_VERSION:
        raise CertificationError("metric-window certification rule is stale")
    if (
        window_certification.metric_id != metric_id
        or window_certification.entity_type != entity_type
        or window_certification.dataset_version != dataset_version
        or window_certification.acquisition_scope != acquisition_scope
        or window_certification.terminal_year != terminal_year
    ):
        raise CertificationError("metric-window lineage does not match the partition")
    as_of_date = getattr(partition, "as_of_date", None)
    if as_of_date is None or window_certification.cutoff.date() != as_of_date:
        raise CertificationError("metric-window cutoff does not match the partition")
    complete_years = getattr(partition, "complete_source_years", None)
    if not isinstance(complete_years, tuple) or not set(
        window_certification.required_years
    ).issubset(complete_years):
        raise CertificationError("partition lacks the certified metric-window years")
    window_projections = {
        projection.paper_id: projection
        for source_year in window.source_years
        for projection in source_year.evidence.paper_projections
    }
    if len(window_projections) != sum(
        len(source_year.evidence.paper_projections)
        for source_year in window.source_years
    ):
        raise CertificationError("metric window repeats canonical papers across years")
    for paper_id, paper in _paper_objects(partition).items():
        projection = window_projections.get(paper_id)
        if projection is None or projection.publication_date != getattr(
            paper, "publication_date", None
        ):
            raise CertificationError(
                "metric partition paper is absent from its certified source window"
            )
    population_evidence = population.certification.evidence
    if (
        population_evidence.metric_id != metric_id
        or population_evidence.terminal_year != terminal_year
        or population_evidence.dataset_version != dataset_version
        or population_evidence.acquisition_scope != acquisition_scope
        or population_evidence.entity_type != entity_type
        or population_evidence.entity_id != _required_string(partition, "entity_id")
        or population_evidence.field_id != _required_string(partition, "field_id")
    ):
        raise CertificationError("metric population context differs from partition")
    if metric_id == "research_diversity":
        category_universe = population_evidence.category_universe
        if category_universe is None or tuple(
            sorted(category_universe.evidence.category_ids)
        ) != tuple(sorted(getattr(partition, "eligible_category_ids", ()))):
            raise CertificationError(
                "Diversity partition category universe differs from reviewed proof"
            )
    included_population = {
        item.paper_id: item
        for item in population_evidence.projections
        if item.status == "included"
    }
    if set(included_population) != set(_paper_objects(partition)) or any(
        included_population[paper_id].publication_date
        != getattr(paper, "publication_date", None)
        or not math.isclose(
            included_population[paper_id].attribution_weight,
            float(getattr(paper, "attribution_weight", 0.0)),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for paper_id, paper in _paper_objects(partition).items()
    ):
        raise CertificationError(
            "partition papers differ from its exact eligibility population"
        )

    decision_ids = [item.decision_id for item in decisions]
    if len(set(decision_ids)) != len(decision_ids):
        raise CertificationError("evidence decisions contain duplicate proofs")
    if any(item.supersedes_decision_id == item.decision_id for item in decisions):
        raise CertificationError("an evidence decision cannot supersede itself")
    superseded_ids = {
        item.supersedes_decision_id
        for item in decisions
        if item.supersedes_decision_id is not None
    }
    current_decisions = tuple(
        item for item in decisions if item.decision_id not in superseded_ids
    )
    current_by_id = {item.decision_id: item for item in current_decisions}
    for decision in current_decisions:
        if decision.rule_version != evidence_rule_version(decision.evidence_kind):
            raise CertificationError(
                f"{decision.evidence_kind} certification rule is stale"
            )

    by_subject_kind: dict[
        tuple[str, EvidenceKind], list[EvidenceCertificationDecision]
    ] = defaultdict(list)
    for decision in current_decisions:
        if (
            decision.dataset_version != dataset_version
            or decision.acquisition_scope != acquisition_scope
        ):
            raise CertificationError(
                "evidence decision lineage does not match partition"
            )
        if decision.subject_type == "paper":
            by_subject_kind[(decision.subject_id, decision.evidence_kind)].append(
                decision
            )

    paper_requirements = required_paper_evidence(metric_id, entity_type)
    paper_certifications: list[PaperEvidenceCertification] = []
    papers_by_id = _paper_objects(partition)
    for paper_id in _paper_ids(partition):
        selected_ids: list[str] = []
        certified_kinds: list[EvidenceKind] = []
        for kind in paper_requirements:
            candidates = by_subject_kind.get((paper_id, kind), [])
            if len(candidates) != 1:
                raise CertificationError(
                    f"paper {paper_id} lacks one current {kind} certification decision"
                )
            if candidates[0].state == "certified":
                certified_kinds.append(kind)
            elif not (
                candidates[0].state == "insufficient_evidence"
                and _explicit_missing_is_usable(
                    papers_by_id[paper_id], metric_id, entity_type, kind
                )
            ):
                raise CertificationError(
                    f"paper {paper_id} contains non-certified {kind} evidence"
                )
            selected_ids.append(candidates[0].decision_id)
        paper_certifications.append(
            PaperEvidenceCertification(
                paper_id=paper_id,
                projection_digest=canonical_digest(papers_by_id[paper_id]),
                decided_kinds=paper_requirements,
                certified_kinds=tuple(certified_kinds),
                decision_ids=tuple(sorted(selected_ids)),
            )
        )

    for paper_certification in paper_certifications:
        paper = papers_by_id[paper_certification.paper_id]
        for decision_id in paper_certification.decision_ids:
            decision = current_by_id[decision_id]
            expected_digest = paper_evidence_value_digest(
                partition, paper, decision.evidence_kind
            )
            if decision.certified_value_digest != expected_digest:
                raise CertificationError(
                    f"paper {paper_certification.paper_id} {decision.evidence_kind} "
                    "decision does not bind its formula input"
                )

    coverage_by_kind = {item.evidence_kind: item for item in coverage}
    if len(coverage_by_kind) != len(coverage):
        raise CertificationError("coverage certifications must be unique by kind")
    partition_coverage = getattr(partition, "coverage", None)
    if partition_coverage is None:
        raise CertificationError("metric partition lacks coverage evidence")
    coverage_ledger = metric_population_coverage_ledger(population_evidence)
    expected_population_units = tuple(
        (item.unit_id, item.mass) for item in coverage_ledger
    )
    expected_coverage_mass = math.fsum(item.mass for item in coverage_ledger)
    if expected_coverage_mass <= 0:
        raise CertificationError("metric partition coverage universe is empty")
    comparable_citation_ids = (
        frozenset(impact_comparable_paper_ids(partition, window.citation_cohorts))
        if metric_id == "research_impact"
        else frozenset()
    )
    for kind in required_coverage_evidence(metric_id, entity_type):
        certificate = coverage_by_kind.get(kind)
        if certificate is None or certificate.state != "certified":
            raise CertificationError(f"{kind} coverage is not certified")
        if not math.isclose(
            certificate.minimum,
            coverage_minimum(kind),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise CertificationError(f"{kind} coverage uses a stale minimum")
        coverage_population = tuple(
            item
            for item in current_decisions
            if item.subject_type == COVERAGE_SUBJECT_TYPE and item.evidence_kind == kind
        )
        if set(certificate.decision_ids) != {
            item.decision_id for item in coverage_population
        }:
            raise CertificationError(
                f"{kind} coverage omits or references an unrelated/stale decision"
            )
        validate_coverage_certification(certificate, coverage_population)
        if (
            certificate.population.source_manifest_digest
            != population.certification.projection_digest
            or certificate.population.units != expected_population_units
        ):
            raise CertificationError(
                f"{kind} coverage population differs from the exact reviewed "
                "metric population"
            )
        observed_formula_mass = _observed_formula_mass(
            tuple(papers_by_id.values()),
            kind,
            entity_type,
            comparable_citation_ids,
        )
        expected_formula_inputs = _formula_inputs(
            tuple(papers_by_id.values()),
            kind,
            entity_type,
            comparable_citation_ids,
        )
        if certificate.population.formula_inputs != expected_formula_inputs:
            raise CertificationError(
                f"{kind} coverage formula-input projection does not match partition"
            )
        if not math.isclose(
            certificate.numerator,
            observed_formula_mass,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise CertificationError(
                f"{kind} certified mass does not match formula-eligible evidence"
            )
        if not math.isclose(
            certificate.denominator,
            expected_coverage_mass,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise CertificationError(
                f"{kind} coverage omits or adds reviewed source-population mass"
            )
        attribute = _COVERAGE_ATTRIBUTE[kind]
        supplied = getattr(partition_coverage, attribute, None)
        if not isinstance(supplied, (int, float)) or isinstance(supplied, bool):
            raise CertificationError(f"partition lacks measured {kind} coverage")
        if certificate.ratio is None or not math.isclose(
            float(supplied), certificate.ratio, rel_tol=0.0, abs_tol=1e-12
        ):
            raise CertificationError(
                f"partition {kind} coverage differs from its certified denominator"
            )

    selected_decision_ids = tuple(
        sorted(
            {
                decision_id
                for paper in paper_certifications
                for decision_id in paper.decision_ids
            }
            | {
                decision_id
                for certificate in coverage_by_kind.values()
                for decision_id in certificate.decision_ids
            }
        )
    )
    selected_decisions = tuple(current_by_id[item] for item in selected_decision_ids)
    certification = MetricPartitionCertification(
        metric_id=metric_id,
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        threshold_version=window_certification.threshold_version,
        state="certified",
        input_digest=canonical_digest(partition),
        evidence_cutoff=window_certification.cutoff,
        window_certification_id=window_certification.certification_id,
        population_certification_id=population.certification.certification_id,
        citation_cohort_certification_ids=(
            window_certification.citation_cohort_certification_ids
        ),
        evidence_decisions=selected_decisions,
        paper_certifications=tuple(paper_certifications),
        coverage=tuple(
            coverage_by_kind[kind]
            for kind in required_coverage_evidence(metric_id, entity_type)
        ),
        decision_ids=selected_decision_ids,
        rule_version=CERTIFICATION_POLICY_VERSION,
    )
    return CertifiedMetricPartition(
        partition=partition,
        certification=certification,
        window_proof=window,
        population_proof=population,
    )
