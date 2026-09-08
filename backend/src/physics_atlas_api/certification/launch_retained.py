"""Compact immutable scientific facts for the bounded launch, not a trace mirror.

This exporter consumes already qualified in-memory evidence. It neither certifies
JSON nor fetches providers. Shared fact tables retain historical counts and exact
inputs; certificate digests bind the original proofs without serializing their
recursive implementation DAG. Rehydration returns *untrusted* calculator input.
"""

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import date, datetime
from fractions import Fraction
from typing import Any, cast

from ..metrics.aggregation import CertifiedPhysicsAggregation, FieldPopulationEvidence
from ..metrics.calculators import (
    AttributedPaperEvidence,
    MetricCalculationResult,
    MetricCoverageEvidence,
    MetricPartitionInput,
)
from ..metrics.presentation import AtlasScaleObservation, CertifiedMetricCalculation
from .contracts import (
    CertificationError,
    CoverageCertification,
    EvidenceCertificationDecision,
    EvidenceReference,
    canonical_digest,
)
from .launch_metric_coverage import launch_relationship_status
from .launch_years import LaunchStructuralDecision
from .measurement_windows import (
    CertifiedObservedSessionCitationCohort,
    CertifiedSessionCitationCohort,
    citation_reference_membership_version,
)
from .years import (
    CertifiedMetricWindow,
    CertifiedSourceYear,
    ConditionalObservedSourceYearEvidence,
    SourceEntityType,
    SourceYearPaperProjection,
    source_quality_certification,
)

LAUNCH_RETAINED_VERSION = "compact-launch-scientific-evidence-v1"


def _plain(value: Any) -> Any:
    """Only primitive facts; deliberately reject automatic dataclass traversal."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CertificationError("retained facts must be finite")
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Fraction):
        return [value.numerator, value.denominator]
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    raise CertificationError(f"non-primitive retained fact: {type(value).__name__}")


def _row(value: Any, names: str) -> dict[str, Any]:
    return {name: _plain(getattr(value, name)) for name in names.split()}


def _flat(value: Any, base: type, *, omit: tuple[str, ...] = ()) -> dict[str, Any]:
    return _row(
        value, " ".join(item.name for item in fields(base) if item.name not in omit)
    )


def _encode(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


@dataclass(frozen=True)
class LaunchRetainedBuild:
    content: bytes
    sha256: str
    byte_length: int
    counts: tuple[tuple[str, int], ...]
    version: str = LAUNCH_RETAINED_VERSION


class _Export:
    def __init__(self, lineage: tuple[str, str]) -> None:
        self.lineage = lineage
        self.tables: dict[str, dict[str, Any]] = {
            name: {}
            for name in (
                "references",
                "papers",
                "decisions",
                "sourceYears",
                "coverage",
                "citationPages",
                "citationSessions",
                "citationCohorts",
                "partitions",
                "calculations",
                "normalizationPopulations",
                "aggregations",
                "observations",
            )
        }
        self.seen: dict[tuple[str, int], str] = {}
        # Some existing properties return fresh objects. Hold cache keys alive
        # so Python cannot reuse their ids for unrelated decisions.
        self.seen_objects: list[object] = []

    def put(self, table: str, key: str, value: Any) -> str:
        previous = self.tables[table].get(key)
        if previous is not None and previous != value:
            raise CertificationError(f"conflicting retained {table} identity: {key}")
        self.tables[table][key] = value
        return key

    def reference(self, reference: EvidenceReference) -> str:
        if not isinstance(reference, EvidenceReference):
            raise CertificationError("retained provenance requires typed references")
        return self.put(
            "references",
            canonical_digest(reference),
            _flat(reference, EvidenceReference),
        )

    def decision(self, decision: EvidenceCertificationDecision) -> str:
        key = self.seen.get(("decision", id(decision)))
        if key is not None:
            return key
        key = decision.decision_id
        self.seen["decision", id(decision)] = key
        self.seen_objects.append(decision)
        row = _flat(decision, EvidenceCertificationDecision, omit=("evidence",))
        row["evidence"] = [self.reference(ref) for ref in decision.evidence]
        # Keep the producer's rule/version but never its nested source-proof tree.
        for name in ("producer_version", "automatic_rule_version"):
            if hasattr(decision, name):
                row[name] = _plain(getattr(decision, name))
        return self.put("decisions", key, row)

    def coverage(self, coverage: CoverageCertification) -> str:
        row = _row(
            coverage,
            "evidence_kind numerator denominator minimum state reasons decision_ids",
        )
        row["population"] = _row(
            coverage.population,
            "evidence_kind units formula_inputs source_manifest_digest",
        )
        row["decision_masses"] = [
            _row(item, "decision_id certified_mass denominator_mass")
            for item in coverage.decision_masses
        ]
        return self.put("coverage", canonical_digest(row), row)

    def paper(
        self,
        projection: SourceYearPaperProjection,
        proof: LaunchStructuralDecision | None,
    ) -> None:
        row = _flat(
            projection, SourceYearPaperProjection, omit=("occurrence_references",)
        )
        row["occurrence_references"] = [
            self.reference(ref) for ref in projection.occurrence_references
        ]
        row["occurrences"] = []
        row["relationship_status"] = {
            kind: None for kind in ("researcher", "institution", "country")
        }
        row["known_researcher_ids"] = []
        row["document_type"] = None
        row["attribution"] = []
        if proof is not None:
            source = proof.source_paper
            row["canonical_identity_state"] = source.component.status
            for occurrence in source.occurrences:
                facts = occurrence.source_facts
                item = {
                    "reference": self.reference(occurrence.reference),
                    "identity_references": [
                        self.reference(ref) for ref in occurrence.identity_references
                    ],
                    "document_type": occurrence.identity.document_type,
                    "doi_assertions": [
                        _row(
                            assertion, "position value material source source_reference"
                        )
                        for assertion in occurrence.doi_assertions
                    ],
                    "doi_role_conflicts": [
                        item.value for item in occurrence.doi_role_conflicts
                    ],
                    "declared_date_basis": facts.declared_date_basis,
                    "extraction_version": facts.extraction_version,
                    "date_facts": [
                        {
                            **_row(fact, "basis source_field value"),
                            "reference": self.reference(fact.reference),
                        }
                        for fact in facts.date_facts
                    ],
                    "author_count": facts.author_count,
                    "known_researcher_ids": list(facts.researcher_ids),
                    "author_identity_facts": [
                        {
                            "appearance_id": author.appearance_id,
                            "facts": [
                                {
                                    **_row(fact, "source_field scheme value"),
                                    "reference": self.reference(fact.reference),
                                }
                                for fact in author.facts
                            ],
                        }
                        for author in facts.authors
                    ],
                    "researcher_assessments": [
                        self.decision(assessment.decision)
                        for assessment in facts.researcher_assessments
                    ],
                    "provider_fields": [
                        {
                            **_row(
                                field, "provider source_record_id source_snapshot_id"
                            ),
                            "categories": [
                                _row(category, "category role taxonomy scheme source")
                                for category in field.categories
                            ],
                        }
                        for field in occurrence.field_evidence.projections
                    ],
                }
                row["occurrences"].append(item)
            if source.component.status == "matched" and len(source.occurrences) == 1:
                row["known_researcher_ids"] = list(
                    source.occurrences[0].source_facts.researcher_ids
                )
                row["document_type"] = source.occurrences[0].identity.document_type
            if proof.state == "certified":
                row["relationship_status"] = {
                    kind: launch_relationship_status(
                        proof, cast(SourceEntityType, kind)
                    )
                    for kind in ("researcher", "institution", "country")
                }
            for result in proof.attribution_results:
                attribution_item: dict[str, Any] = {
                    "reference": self.reference(result.paper_reference),
                    **_row(
                        result,
                        "version researcher_state paper_time_affiliation_weight "
                        "unresolved_reason_counts",
                    ),
                    "affiliations": [
                        {
                            **_row(
                                affiliation,
                                "author_position affiliation_position source_field "
                                "assertion_id state reasons country_code",
                            ),
                            "institution": None
                            if affiliation.institution is None
                            else _row(
                                affiliation.institution,
                                "state canonical_institution_id source_institution_id "
                                "match_method candidate_institution_ids reasons "
                                "rule_version",
                            ),
                            "authority_binding": None
                            if affiliation.institution is None
                            else _row(
                                affiliation.institution.evidence,
                                "source_evidence_ids source_manifest_digest "
                                "authority_version direct_ror_ids provider "
                                "provider_institution_id review_state reviewed_by "
                                "reviewed_at reviewed_context_institution_id "
                                "reviewed_rollup_institution_id",
                            ),
                            "evidence": [
                                self.reference(ref) for ref in affiliation.evidence
                            ],
                        }
                        for affiliation in result.affiliations
                    ],
                    "fractional": None,
                }
                if result.fractional is not None:
                    fractional = result.fractional
                    attribution_item["fractional"] = {
                        **_row(
                            fractional,
                            "policy_id policy_version total_weight allocated_weight "
                            "withheld_weight",
                        ),
                        "institution_weights": _plain(fractional.institution_weights()),
                        "country_weights": _plain(fractional.country_weights()),
                        "researcher_weights": _plain(fractional.researcher_weights()),
                    }
                row["attribution"].append(attribution_item)
        self.put("papers", projection.paper_id, row)

    def source_year(self, source: CertifiedSourceYear) -> str:
        cached = self.seen.get(("source_year", id(source)))
        if cached is not None:
            return cached
        if (
            not isinstance(source.evidence, ConditionalObservedSourceYearEvidence)
            or source.state != "certified"
        ):
            raise CertificationError(
                "retained launch source must be qualified observed evidence"
            )
        if (source.dataset_version, source.acquisition_scope) != self.lineage:
            raise CertificationError("retained launch evidence mixes source lineage")
        key = source.certification_id
        self.seen["source_year", id(source)] = key
        self.seen_objects.append(source)
        evidence = source.evidence
        proofs = {
            decision.subject_id: decision
            for decision in evidence.structural_decisions
            if isinstance(decision, LaunchStructuralDecision)
            and decision.evidence_kind == "provenance-completeness"
        }
        for paper in evidence.paper_projections:
            self.paper(paper, proofs.get(paper.paper_id))
        row = _row(
            evidence,
            "calendar_year entity_type cutoff dataset_version acquisition_scope "
            "required_partition_ids required_coverage_kinds",
        )
        row.update(
            {
                "papers": [paper.paper_id for paper in evidence.paper_projections],
                "decisions": [
                    self.decision(item)
                    for item in (
                        *evidence.structural_decisions,
                        *evidence.coverage_decisions,
                    )
                ],
                "coverage": [self.coverage(item) for item in source.coverage],
                "certification": _row(
                    source.certification,
                    "state rule_version input_digest reasons canonical_paper_count "
                    "canonical_paper_population_digest",
                ),
                "source_quality": _row(
                    source_quality_certification(source),
                    "state rule_version input_digest reasons",
                ),
                "partitions": [
                    _row(
                        item,
                        "partition_id provider expected_unique_records "
                        "observed_records observed_unique_records duplicate_records "
                        "truncated "
                        "page_checksums record_inventory_digest complete",
                    )
                    for item in evidence.partitions
                ],
                "acquisition_plan_digest": evidence.acquisition_plan.content_digest,
            }
        )
        return self.put("sourceYears", key, row)

    def cohort(self, cohort: object) -> str:
        cached = self.seen.get(("cohort", id(cohort)))
        if cached is not None:
            return cached
        if not isinstance(cohort, CertifiedSessionCitationCohort):
            raise CertificationError(
                "retained launch requires actual citation measurement sessions"
            )
        key = cohort.certification_id
        self.seen["cohort", id(cohort)] = key
        self.seen_objects.append(cohort)
        session = cohort.session
        session_key = session.session_id
        page_keys = []
        if session_key not in self.tables["citationSessions"]:
            for page in session.pages:
                row = _row(
                    page,
                    "request_url requested_at received_at dataset_version "
                    "acquisition_scope calendar_year end_calendar_year "
                    "declared_date_basis source_snapshot_id response_sha256 "
                    "reported_total next_url source source_version expected_source_ids",
                )
                row["records"] = [
                    _row(
                        item,
                        "source_record_id paper_id source_record_checksum "
                        "publication_date field_ids document_type raw_citation_count "
                        "non_self_citation_count unresolved_membership",
                    )
                    for item in page.records
                ]
                page_keys.append(self.put("citationPages", canonical_digest(row), row))
            population = session.frozen_population
            self.put(
                "citationSessions",
                session_key,
                {
                    **_row(session, "version membership_semantics interpretation"),
                    "pages": page_keys,
                    "frozen_population": {
                        **_row(
                            population,
                            "dataset_version acquisition_scope declared_date_basis "
                            "frozen_at provider_to_canonical",
                        ),
                        "reference": self.reference(population.reference),
                    },
                },
            )
        row = {
            "session": session_key,
            "cohort_key": _plain(cohort.cohort_key),
            "policy_version": cohort.policy_version,
            "reference_membership_version": citation_reference_membership_version(
                cohort
            ),
            "source_years": [
                self.source_year(item) for item in cohort.population.source_years
            ],
            "unmeasurable_paper_ids": list(cohort.population.unmeasurable_paper_ids),
            "observations": [
                {
                    **_row(
                        item,
                        "paper_id state non_self_citation_count maturity_months "
                        "reasons rule_version evidence_digest cutoff mature",
                    ),
                    "observed_at": _plain(item.evidence.observed_at),
                    "source_reference": None
                    if item.evidence.source_reference is None
                    else self.reference(item.evidence.source_reference),
                }
                for item in cohort.observations
            ],
        }
        if isinstance(cohort, CertifiedObservedSessionCitationCohort):
            row["frozen_observed_paper_ids"] = list(cohort.frozen_observed_paper_ids)
            row["reference_population"] = _plain(cohort.reference_population_metadata)
        return self.put("citationCohorts", key, row)

    def calculation(self, proof: CertifiedMetricCalculation) -> str:
        key = canonical_digest(proof.calculation)
        if key in self.tables["calculations"]:
            return key
        certified = proof.partition
        partition = certified.partition
        if (partition.dataset_version, partition.acquisition_scope) != self.lineage:
            raise CertificationError("retained metric calculation mixes source lineage")
        if not isinstance(certified.window_proof, CertifiedMetricWindow):
            raise CertificationError("retained calculation requires source window")
        source_years = [
            self.source_year(year) for year in certified.window_proof.source_years
        ]
        cohorts = [self.cohort(cohort) for cohort in proof.citation_cohorts]
        input_digest = certified.certification.input_digest
        row = _flat(partition, MetricPartitionInput, omit=("papers", "coverage"))
        row["coverage"] = _flat(partition.coverage, MetricCoverageEvidence)
        row["papers"] = [paper.paper_id for paper in partition.papers]
        row["branch_diversity"] = proof.calculation.metric_id == "research_diversity"
        row["citation_cohorts"] = cohorts
        self.put("partitions", input_digest, row)
        certificate = certified.certification
        self.put(
            "calculations",
            key,
            {
                "result": _flat(proof.calculation, MetricCalculationResult),
                "input": input_digest,
                "source_years": source_years,
                "certification": {
                    **_row(
                        certificate,
                        "state rule_version reasons threshold_version evidence_cutoff "
                        "window_certification_id population_certification_id "
                        "certification_digest",
                    ),
                    "decisions": [
                        self.decision(item) for item in certificate.evidence_decisions
                    ],
                    "coverage": [self.coverage(item) for item in certificate.coverage],
                },
            },
        )
        # This is exact input reconstruction, not a new certification route.
        if (
            rehydrate_launch_metric_input(
                {"version": LAUNCH_RETAINED_VERSION, **self.tables}, input_digest
            )
            != partition
        ):
            raise CertificationError(
                "retained facts do not reconstruct exact metric input"
            )
        return key

    def observation(self, observation: AtlasScaleObservation) -> str:
        key = canonical_digest(observation.calculation)
        if key in self.tables["observations"]:
            return key
        proof = observation.certification_proof
        if isinstance(proof, CertifiedMetricCalculation):
            calculation_key = self.calculation(proof)
        elif isinstance(proof, CertifiedPhysicsAggregation):
            calculation_key = proof.proof_digest
            self.put(
                "aggregations",
                calculation_key,
                {
                    "result": _flat(proof.calculation, MetricCalculationResult),
                    "field_observations": [
                        self.observation(item) for item in proof.field_observations
                    ],
                    "field_population": {
                        **_flat(
                            proof.field_population_proof.evidence,
                            FieldPopulationEvidence,
                        ),
                        "certification_digest": (
                            proof.field_population_proof.certification_digest
                        ),
                    },
                },
            )
        else:
            raise CertificationError("unsupported retained observation proof")
        peers = [self.calculation(item) for item in observation.normalization_proofs]
        population = observation.normalization_population_proof
        population_key = None
        if population is not None:
            population_key = population.certification_digest
            evidence = population.evidence
            row = _row(
                evidence,
                "cohort_key entity_ids calculation_certification_digests "
                "source_manifest_digest review_state reviewed_by reviewed_at",
            )
            row["calculations"] = peers
            for name in ("automatic_rule_version", "source_entity_ids"):
                if hasattr(evidence, name):
                    row[name] = _plain(getattr(evidence, name))
            row["ineligible_peers"] = [
                {
                    **_row(
                        item,
                        "entity_id field_id partition_digest "
                        "population_certification_id version",
                    ),
                    "failures": [
                        _row(
                            failure,
                            "evidence_kind subject_type state reasons affected_count "
                            "numerator denominator minimum",
                        )
                        for failure in item.failures
                    ],
                }
                for item in getattr(evidence, "ineligible_peers", ())
            ]
            self.put("normalizationPopulations", population_key, row)
        return self.put(
            "observations",
            key,
            {
                **_row(
                    observation,
                    "value scale_version metric_normalization_version "
                    "certification_manifest_digest comparison_cohort cutoff coverage "
                    "uncertainty_reasons",
                ),
                "result": _flat(observation.calculation, MetricCalculationResult),
                "calculation": calculation_key,
                "normalization_population": population_key,
            },
        )


def build_launch_retained(
    source_years: tuple[CertifiedSourceYear, ...],
    observations: tuple[AtlasScaleObservation, ...],
    *,
    source_references: tuple[EvidenceReference, ...] = (),
) -> LaunchRetainedBuild:
    """Produce one deterministic fact artifact; no files, networking or activation."""
    if not source_years or any(
        not isinstance(item, CertifiedSourceYear) for item in source_years
    ):
        raise CertificationError(
            "retained launch requires exact qualified source years"
        )
    if any(not isinstance(item, AtlasScaleObservation) for item in observations):
        raise CertificationError("retained launch requires typed Atlas observations")
    exporter = _Export(
        (source_years[0].dataset_version, source_years[0].acquisition_scope)
    )
    supplied_years = sorted({exporter.source_year(item) for item in source_years})
    for reference in source_references:
        exporter.reference(reference)
    published = sorted({exporter.observation(item) for item in observations})
    document = {
        "version": LAUNCH_RETAINED_VERSION,
        "dataset_version": exporter.lineage[0],
        "acquisition_scope": exporter.lineage[1],
        "qualification": "conditional observed source; not full-field completeness",
        "source_years": supplied_years,
        "published_observations": published,
        **exporter.tables,
    }
    content = _encode(document)
    return LaunchRetainedBuild(
        content,
        hashlib.sha256(content).hexdigest(),
        len(content),
        tuple(sorted((key, len(value)) for key, value in exporter.tables.items())),
    )


def rehydrate_launch_metric_input(
    document: Mapping[str, Any], input_digest: str
) -> MetricPartitionInput:
    """Recover exact raw facts, never a CertifiedMetricPartition or authorization.

    Integrity of the whole artifact must additionally be checked against its
    release SHA-256. Here the original input digest checks reconstruction.
    """
    from .fields import branch_diversity_field_projection

    if document.get("version") != LAUNCH_RETAINED_VERSION:
        raise CertificationError("unsupported retained evidence version")
    try:
        record = dict(document["partitions"][input_digest])
        branch = record.pop("branch_diversity")
        cohorts = [
            document["citationCohorts"][key] for key in record.pop("citation_cohorts")
        ]
        citation_by_key = {
            (cohort["cohort_key"][0], cohort["cohort_key"][1], item["paper_id"]): item
            for cohort in cohorts
            for item in cohort["observations"]
        }
        papers = []
        for paper_id in record.pop("papers"):
            source = document["papers"][paper_id]
            publication = date.fromisoformat(source["publication_date"])
            field_weights = tuple(
                (field, float(weight)) for field, weight in source["field_weights"]
            )
            field_weight, categories = (
                branch_diversity_field_projection(record["field_id"], field_weights)
                if branch
                else (dict(field_weights).get(record["field_id"], 0.0), ())
            )
            entity_weight = math.fsum(
                weight
                for kind, entity_id, weight in source["entity_shares"]
                if kind == record["entity_type"] and entity_id == record["entity_id"]
            )
            citation = citation_by_key.get(
                (record["field_id"], publication.year, paper_id)
            )
            relationships = source["relationship_status"]
            papers.append(
                AttributedPaperEvidence(
                    paper_id,
                    publication,
                    source["document_type"],
                    entity_weight * field_weight,
                    tuple(source["known_researcher_ids"]),
                    None if citation is None else citation["non_self_citation_count"],
                    None
                    if citation is None or citation["observed_at"] is None
                    else datetime.fromisoformat(citation["observed_at"]).date(),
                    relationships["researcher"],
                    relationships["institution"],
                    relationships["country"],
                    tuple(
                        sorted(
                            entity_id
                            for kind, entity_id, weight in source["entity_shares"]
                            if kind == record["entity_type"]
                            and entity_id != record["entity_id"]
                            and weight > 0
                        )
                    ),
                    categories,
                )
            )
        record["papers"] = tuple(papers)
        record["as_of_date"] = date.fromisoformat(record["as_of_date"])
        record["complete_source_years"] = tuple(record["complete_source_years"])
        record["eligible_category_ids"] = tuple(record["eligible_category_ids"])
        record["coverage"] = MetricCoverageEvidence(**record["coverage"])
        result = MetricPartitionInput(**record)
        if canonical_digest(result) != input_digest:
            raise CertificationError("retained metric input checksum mismatch")
        return result
    except (KeyError, TypeError, ValueError) as exc:
        raise CertificationError(f"invalid retained metric input: {exc}") from exc
