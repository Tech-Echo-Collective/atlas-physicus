import hashlib
import math
from dataclasses import replace
from datetime import UTC, date, datetime, time

from physics_atlas_api.attribution import FRACTIONAL_ATTRIBUTION_V1
from physics_atlas_api.certification import (
    CERTIFICATION_POLICY_VERSION,
    CITATION_CERTIFICATION_RULE_VERSION,
    COVERAGE_SUBJECT_TYPE,
    FIELD_CERTIFICATION_RULE_VERSION,
    INSTITUTION_CERTIFICATION_RULE_VERSION,
    METRIC_POPULATION_SUBJECT_TYPE,
    CategoryUniverseEvidence,
    CertifiedCitationCohort,
    CitationCohortPopulationEvidence,
    CitationObservationEvidence,
    CoverageCertification,
    CoveragePopulationEvidence,
    EvidenceCertificationDecision,
    EvidenceReference,
    MetricPopulationEvidence,
    MetricPopulationProjection,
    SourceAcquisitionPlanEvidence,
    SourcePartitionEvidence,
    SourceYearEvidence,
    SourceYearPaperProjection,
    build_certified_metric_partition,
    canonical_digest,
    certify_category_universe,
    certify_citation_cohort,
    certify_citation_observation,
    certify_coverage,
    certify_metric_window,
    certify_source_year,
    metric_population_coverage_ledger,
    paper_evidence_value_digest,
    required_coverage_evidence,
    required_paper_evidence,
    required_window_years,
    source_record_inventory_digest,
    wrap_certified_citation_cohort,
    wrap_certified_metric_population,
)
from physics_atlas_api.certification.citations import impact_comparable_paper_ids
from physics_atlas_api.fields import FIELD_WEIGHTING_POLICY_VERSION
from physics_atlas_api.metrics.calculators import (
    CitationReferenceCohort,
    MetricPartitionInput,
)
from physics_atlas_api.metrics.presentation import (
    CertifiedMetricCalculation,
    NormalizationPopulationEvidence,
    certify_normalization_population,
)


def _checksum(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def certify_normalization_populations(
    calculations: tuple[CertifiedMetricCalculation, ...],
):  # type: ignore[no-untyped-def]
    groups: dict[tuple[str, ...], list[str]] = {}
    for item in calculations:
        result = item.calculation
        key = (
            result.metric_id,
            result.entity_type,
            result.field_id,
            result.period,
            result.metric_definition_version,
            result.algorithm_version,
            result.normalization_version,
            result.dataset_version,
            result.acquisition_scope,
            result.evidence_cutoff,
            result.attribution_policy_version,
            result.ontology_version,
            result.mapping_policy_version,
            result.citation_policy_version,
            result.threshold_version,
        )
        groups.setdefault(key, []).append(result.entity_id)
    return tuple(
        certify_normalization_population(evidence)
        for key, entity_ids in sorted(groups.items())
        for evidence in (
            NormalizationPopulationEvidence(
                cohort_key=key,
                entity_ids=tuple(sorted(entity_ids)),
                calculation_certification_digests=tuple(
                    sorted(
                        (
                            item.calculation.entity_id,
                            item.calculation.certification_manifest_digest,
                        )
                        for item in calculations
                        if _normalization_key(item) == key
                    )
                ),
                source_manifest_digest="0" * 64,
                review_state="reviewed-approved",
                reviewed_by="test-fixture-reviewer",
                reviewed_at=datetime(2026, 12, 31, tzinfo=UTC),
            ),
        )
        for evidence in (
            NormalizationPopulationEvidence(
                cohort_key=evidence.cohort_key,
                entity_ids=evidence.entity_ids,
                calculation_certification_digests=(
                    evidence.calculation_certification_digests
                ),
                source_manifest_digest=evidence.content_digest,
                review_state=evidence.review_state,
                reviewed_by=evidence.reviewed_by,
                reviewed_at=evidence.reviewed_at,
            ),
        )
    )


def _normalization_key(item: CertifiedMetricCalculation) -> tuple[str, ...]:
    result = item.calculation
    return (
        result.metric_id,
        result.entity_type,
        result.field_id,
        result.period,
        result.metric_definition_version,
        result.algorithm_version,
        result.normalization_version,
        result.dataset_version,
        result.acquisition_scope,
        result.evidence_cutoff,
        result.attribution_policy_version,
        result.ontology_version,
        result.mapping_policy_version,
        result.citation_policy_version,
        result.threshold_version,
    )


def certify_partition(
    partition: MetricPartitionInput,
    metric_id: str,
    *,
    threshold_version: str = "metric-validation-thresholds-v1",
    citation_cohorts: tuple[CertifiedCitationCohort[object], ...] = (),
    unresolved_entity_remainder: bool = False,
):  # type: ignore[no-untyped-def]
    reference = EvidenceReference(
        provider="test-fixture",
        source_record_id="fixture",
        checksum=_checksum("fixture"),
    )
    decisions: list[EvidenceCertificationDecision] = []
    primary_relationship = {
        "researcher": "collaborative",
        "institution": "cross_institution",
        "country": "international",
    }[partition.entity_type]
    for paper in partition.papers:
        for kind in required_paper_evidence(metric_id, partition.entity_type):
            rule_version = {
                "canonical-institution": INSTITUTION_CERTIFICATION_RULE_VERSION,
                "field-classification": FIELD_CERTIFICATION_RULE_VERSION,
                "field-weight-conservation": FIELD_CERTIFICATION_RULE_VERSION,
                "citation-observation": CITATION_CERTIFICATION_RULE_VERSION,
                "citation-cutoff-compatibility": CITATION_CERTIFICATION_RULE_VERSION,
            }.get(kind, CERTIFICATION_POLICY_VERSION)
            is_explicit_missing = (
                (kind == "citation-observation" and paper.citation_count is None)
                or (
                    kind == "citation-cutoff-compatibility"
                    and paper.citation_observed_at is None
                )
                or (
                    kind == "collaboration-relationship"
                    and getattr(paper, primary_relationship) is None
                )
            )
            decisions.append(
                EvidenceCertificationDecision(
                    subject_type="paper",
                    subject_id=paper.paper_id,
                    evidence_kind=kind,
                    state=(
                        "insufficient_evidence" if is_explicit_missing else "certified"
                    ),
                    rule_version=rule_version,
                    dataset_version=partition.dataset_version,
                    acquisition_scope=partition.acquisition_scope,
                    evidence=(reference,),
                    certified_value_digest=paper_evidence_value_digest(
                        partition, paper, kind
                    ),
                    reasons=("fixture records explicit missing evidence",)
                    if is_explicit_missing
                    else (),
                )
            )

    years = required_window_years(metric_id, partition.terminal_year)
    cutoff = datetime.combine(partition.as_of_date, time.min, tzinfo=UTC)

    def source_year(year: int):  # type: ignore[no-untyped-def]
        partition_id = f"fixture-{year}"
        page_checksum = _checksum(f"fixture-year-{year}")
        selected_papers = tuple(
            item for item in partition.papers if item.publication_date.year == year
        )
        source_paper_ids = tuple(item.paper_id for item in selected_papers) or (
            f"source-paper-{year}-filler",
        )
        references = tuple(
            EvidenceReference(
                provider="test-fixture",
                source_record_id=paper_id,
                checksum=page_checksum,
                source_snapshot_id=partition_id,
            )
            for paper_id in source_paper_ids
        )
        selected_by_id = {item.paper_id: item for item in selected_papers}

        def source_projection(index: int, paper_id: str) -> SourceYearPaperProjection:
            selected = selected_by_id.get(paper_id)
            entity_weight = selected.attribution_weight if selected is not None else 0.0
            entity_shares = (
                ((partition.entity_type, partition.entity_id, entity_weight),)
                if entity_weight > 0
                else ()
            )
            unresolved_mass = (
                1.0 - entity_weight
                if selected is not None and unresolved_entity_remainder
                else 0.0
            )
            if entity_weight < 1 and unresolved_mass == 0:
                entity_shares += (
                    (
                        partition.entity_type,
                        f"fixture-other-{partition.entity_type}",
                        1.0 - entity_weight,
                    ),
                )
            return SourceYearPaperProjection(
                paper_id=paper_id,
                publication_date=(
                    selected.publication_date
                    if selected is not None
                    else date(year, 1, 1)
                ),
                occurrence_references=(references[index],),
                field_weights=((partition.field_id, 1.0),),
                unmapped_field_mass=0.0,
                field_weight_total=1.0,
                field_weighting_policy_version=FIELD_WEIGHTING_POLICY_VERSION,
                entity_shares=entity_shares,
                unresolved_entity_mass=((partition.entity_type, unresolved_mass),),
                attribution_policy_version=FRACTIONAL_ATTRIBUTION_V1.version,
            )

        projections = tuple(
            source_projection(index, paper_id)
            for index, paper_id in enumerate(source_paper_ids)
        )
        structural_decisions = tuple(
            EvidenceCertificationDecision(
                subject_type="paper",
                subject_id=projection.paper_id,
                evidence_kind=kind,
                state="certified",
                rule_version=(
                    FIELD_CERTIFICATION_RULE_VERSION
                    if kind == "field-weight-conservation"
                    else CERTIFICATION_POLICY_VERSION
                ),
                dataset_version=partition.dataset_version,
                acquisition_scope=partition.acquisition_scope,
                evidence=projection.occurrence_references,
                certified_value_digest=projection.decision_value_digest(kind),
            )
            for projection in projections
            for kind in (
                "canonical-paper-identity",
                "publication-metric-date",
                "field-weight-conservation",
                "provenance-completeness",
            )
        )
        source_population_digest = canonical_digest(
            tuple(sorted(projections, key=lambda item: item.paper_id))
        )
        source_coverage: list[CoverageCertification] = []
        source_coverage_decisions: list[EvidenceCertificationDecision] = []
        for kind in required_coverage_evidence(metric_id, partition.entity_type):
            kind_decisions = tuple(
                EvidenceCertificationDecision(
                    subject_type=COVERAGE_SUBJECT_TYPE,
                    subject_id=projection.paper_id,
                    evidence_kind=kind,
                    state="certified",
                    rule_version={
                        "canonical-institution": (
                            INSTITUTION_CERTIFICATION_RULE_VERSION
                        ),
                        "field-classification": FIELD_CERTIFICATION_RULE_VERSION,
                        "citation-observation": CITATION_CERTIFICATION_RULE_VERSION,
                    }.get(kind, CERTIFICATION_POLICY_VERSION),
                    dataset_version=partition.dataset_version,
                    acquisition_scope=partition.acquisition_scope,
                    evidence=projection.occurrence_references,
                )
                for projection in projections
            )
            source_coverage_decisions.extend(kind_decisions)
            source_coverage.append(
                certify_coverage(
                    kind,
                    kind_decisions,
                    CoveragePopulationEvidence(
                        evidence_kind=kind,
                        units=tuple((item.subject_id, 1.0) for item in kind_decisions),
                        formula_inputs=tuple(
                            (paper_id, 1.0)
                            for paper_id in sorted(
                                projection.paper_id for projection in projections
                            )
                        ),
                        source_manifest_digest=source_population_digest,
                    ),
                )
            )
        return certify_source_year(
            SourceYearEvidence(
                calendar_year=year,
                entity_type=partition.entity_type,
                cutoff=cutoff,
                dataset_version=partition.dataset_version,
                acquisition_scope=partition.acquisition_scope,
                acquisition_plan=SourceAcquisitionPlanEvidence(
                    calendar_year=year,
                    cutoff=cutoff,
                    dataset_version=partition.dataset_version,
                    acquisition_scope=partition.acquisition_scope,
                    partitions=((partition_id, "test-fixture"),),
                    source_manifest_digest=canonical_digest(
                        (
                            year,
                            cutoff,
                            partition.dataset_version,
                            partition.acquisition_scope,
                            ((partition_id, "test-fixture"),),
                        )
                    ),
                    review_state="reviewed-approved",
                    reviewed_by="test-fixture-reviewer",
                    reviewed_at=cutoff,
                ),
                required_partition_ids=(partition_id,),
                required_coverage_kinds=required_coverage_evidence(
                    metric_id, partition.entity_type
                ),
                paper_projections=projections,
                partitions=(
                    SourcePartitionEvidence(
                        partition_id=partition_id,
                        provider="test-fixture",
                        expected_unique_records=len(references),
                        observed_records=len(references),
                        observed_unique_records=len(references),
                        duplicate_records=0,
                        truncated=False,
                        page_checksums=(page_checksum,),
                        record_inventory_digest=source_record_inventory_digest(
                            references
                        ),
                        complete=True,
                    ),
                ),
                structural_decisions=structural_decisions,
                coverage_decisions=tuple(source_coverage_decisions),
            ),
            tuple(source_coverage),
        )

    source_years = tuple(source_year(year) for year in years)
    window = certify_metric_window(
        metric_id=metric_id,
        entity_type=partition.entity_type,
        terminal_year=partition.terminal_year,
        source_years=source_years,
        threshold_version=threshold_version,
        citation_cohorts=citation_cohorts,
    )
    papers_by_id = {item.paper_id: item for item in partition.papers}
    population_projections = tuple(
        MetricPopulationProjection(
            paper_id=source_projection.paper_id,
            publication_date=source_projection.publication_date,
            entity_type=partition.entity_type,
            entity_id=partition.entity_id,
            field_id=partition.field_id,
            status=(
                "included" if source_projection.paper_id in papers_by_id else "excluded"
            ),
            entity_attribution_weight=math.fsum(
                weight
                for entity_type, entity_id, weight in source_projection.entity_shares
                if entity_type == partition.entity_type
                and entity_id == partition.entity_id
            ),
            field_weight=dict(source_projection.field_weights).get(
                partition.field_id, 0.0
            ),
            attribution_weight=(
                papers_by_id[source_projection.paper_id].attribution_weight
                if source_projection.paper_id in papers_by_id
                else 0.0
            ),
            coverage_weight=(
                math.fsum(
                    weight
                    for entity_type, entity_id, weight in (
                        source_projection.entity_shares
                    )
                    if entity_type == partition.entity_type
                    and entity_id == partition.entity_id
                )
                + math.fsum(
                    weight
                    for entity_type, weight in (
                        source_projection.unresolved_entity_mass
                    )
                    if entity_type == partition.entity_type
                )
            )
            * (
                dict(source_projection.field_weights).get(partition.field_id, 0.0)
                + source_projection.unmapped_field_mass
            ),
            reason=(
                None
                if source_projection.paper_id in papers_by_id
                else "fixture paper is outside this entity/field partition"
            ),
        )
        for source_year_item in window.source_years
        for source_projection in source_year_item.evidence.paper_projections
    )
    population_decisions = tuple(
        EvidenceCertificationDecision(
            subject_type=METRIC_POPULATION_SUBJECT_TYPE,
            subject_id=item.paper_id,
            evidence_kind="provenance-completeness",
            state="certified",
            rule_version=CERTIFICATION_POLICY_VERSION,
            dataset_version=partition.dataset_version,
            acquisition_scope=partition.acquisition_scope,
            evidence=next(
                source_projection.occurrence_references
                for source_year_item in window.source_years
                for source_projection in source_year_item.evidence.paper_projections
                if source_projection.paper_id == item.paper_id
            ),
            certified_value_digest=item.value_digest,
            reviewed_by="test-fixture-reviewer",
            reviewed_at=cutoff,
        )
        for item in population_projections
    )
    category_evidence = (
        CategoryUniverseEvidence(
            field_id=partition.field_id,
            dataset_version=partition.dataset_version,
            acquisition_scope=partition.acquisition_scope,
            category_universe_version="test-category-universe-v1",
            category_ids=partition.eligible_category_ids,
            source_manifest_digest="0" * 64,
            review_state="reviewed-approved",
            reviewed_by="test-fixture-reviewer",
            reviewed_at=cutoff,
        )
        if metric_id == "research_diversity"
        else None
    )
    population = wrap_certified_metric_population(
        MetricPopulationEvidence(
            metric_id=metric_id,
            terminal_year=partition.terminal_year,
            dataset_version=partition.dataset_version,
            acquisition_scope=partition.acquisition_scope,
            entity_type=partition.entity_type,
            entity_id=partition.entity_id,
            field_id=partition.field_id,
            source_manifest_digest=canonical_digest(
                tuple(sorted(population_projections, key=lambda item: item.paper_id))
            ),
            review_state="reviewed-approved",
            reviewed_by="test-fixture-reviewer",
            reviewed_at=cutoff,
            source_year_certification_ids=(
                window.certification.source_year_certification_ids
            ),
            projections=population_projections,
            decisions=population_decisions,
            category_universe=(
                certify_category_universe(
                    replace(
                        category_evidence,
                        source_manifest_digest=category_evidence.content_digest,
                    )
                )
                if category_evidence is not None
                else None
            ),
        ),
        window,
    )
    source_projection_by_id = {
        item.paper_id: item
        for source_year_item in window.source_years
        for item in source_year_item.evidence.paper_projections
    }
    coverage_ledger = metric_population_coverage_ledger(
        population.certification.evidence
    )
    coverage_units = tuple((item.unit_id, item.mass) for item in coverage_ledger)
    comparable_citation_ids = (
        frozenset(impact_comparable_paper_ids(partition, citation_cohorts))
        if metric_id == "research_impact"
        else frozenset()
    )
    coverage_items: list[CoverageCertification] = []
    primary_relationship = {
        "researcher": "collaborative",
        "institution": "cross_institution",
        "country": "international",
    }[partition.entity_type]
    for kind in required_coverage_evidence(metric_id, partition.entity_type):
        formula_inputs = tuple(
            sorted(
                (item.paper_id, item.attribution_weight)
                for item in partition.papers
                if (
                    kind != "citation-observation"
                    or item.paper_id in comparable_citation_ids
                )
                and (
                    kind != "collaboration-relationship"
                    or getattr(item, primary_relationship) is not None
                )
            )
        )
        formula_ids = {paper_id for paper_id, _ in formula_inputs}
        kind_decisions = tuple(
            EvidenceCertificationDecision(
                subject_type=COVERAGE_SUBJECT_TYPE,
                subject_id=unit.unit_id,
                evidence_kind=kind,
                state=(
                    "certified"
                    if unit.status == "known" and unit.paper_id in formula_ids
                    else "insufficient_evidence"
                ),
                rule_version={
                    "canonical-institution": INSTITUTION_CERTIFICATION_RULE_VERSION,
                    "field-classification": FIELD_CERTIFICATION_RULE_VERSION,
                    "citation-observation": CITATION_CERTIFICATION_RULE_VERSION,
                }.get(kind, CERTIFICATION_POLICY_VERSION),
                dataset_version=partition.dataset_version,
                acquisition_scope=partition.acquisition_scope,
                evidence=source_projection_by_id[unit.paper_id].occurrence_references,
                reasons=()
                if unit.status == "known" and unit.paper_id in formula_ids
                else ("fixture retains unresolved or unavailable evidence mass",),
            )
            for unit in coverage_ledger
        )
        decisions.extend(kind_decisions)
        coverage_items.append(
            certify_coverage(
                kind,
                kind_decisions,
                CoveragePopulationEvidence(
                    evidence_kind=kind,
                    units=coverage_units,
                    formula_inputs=formula_inputs,
                    source_manifest_digest=(population.certification.projection_digest),
                ),
            )
        )
    coverage = tuple(coverage_items)
    return build_certified_metric_partition(
        partition,
        metric_id=metric_id,
        decisions=tuple(decisions),
        coverage=coverage,
        window=window,
        population=population,
    )


def certify_citation_reference_cohort(
    cohort: CitationReferenceCohort,
    partition: MetricPartitionInput,
) -> CertifiedCitationCohort[CitationReferenceCohort]:
    cutoff = datetime.combine(cohort.observed_at, time.min, tzinfo=UTC)
    observations = tuple(
        certify_citation_observation(
            CitationObservationEvidence(
                paper_id=paper_id,
                dataset_version=partition.dataset_version,
                acquisition_scope=partition.acquisition_scope,
                citation_source="test-fixture",
                raw_citation_count=int(count),
                non_self_citation_count=int(count),
                observed_at=cutoff,
                selected_cutoff=cutoff,
                publication_date=date(cohort.key[1], 1, 1),
                field_id=cohort.key[0],
                document_type=cohort.key[2],
                source_reference=EvidenceReference(
                    provider="test-fixture",
                    source_record_id=paper_id,
                    checksum=_checksum(f"citation-{paper_id}"),
                ),
                citation_policy_version="non-self-citation-cutoff-v1",
            )
        )
        for paper_id, count in cohort.citations
    )
    population_evidence = CitationCohortPopulationEvidence(
        cohort_key=cohort.key,
        cutoff=cutoff,
        dataset_version=partition.dataset_version,
        acquisition_scope=partition.acquisition_scope,
        eligible_paper_ids=tuple(sorted(paper_id for paper_id, _ in cohort.citations)),
        source_manifest_digest="0" * 64,
        review_state="reviewed-approved",
        reviewed_by="test-fixture-reviewer",
        reviewed_at=cutoff,
    )
    certification = certify_citation_cohort(
        observations,
        dataset_version=partition.dataset_version,
        acquisition_scope=partition.acquisition_scope,
        minimum_paper_count=50,
        population_evidence=replace(
            population_evidence,
            source_manifest_digest=population_evidence.content_digest,
        ),
    )
    return wrap_certified_citation_cohort(
        cohort,
        certification,
        dataset_version=partition.dataset_version,
        acquisition_scope=partition.acquisition_scope,
    )
