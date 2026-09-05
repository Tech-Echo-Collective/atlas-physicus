import math
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from certification_helpers import (
    certify_citation_reference_cohort,
    certify_normalization_populations,
    certify_partition,
)

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.fields import PHYSICS_FIELD_ONTOLOGY_V1
from physics_atlas_api.metrics import (
    METRIC_VALIDATION_THRESHOLDS_V1,
    AttributedPaperEvidence,
    CertifiedPhysicsAggregation,
    CitationReferenceCohort,
    FieldPopulationEvidence,
    MetricCoverageEvidence,
    MetricPartitionInput,
    aggregate_physics_wide,
    apply_atlas_scale,
    bind_metric_calculation,
    certify_field_population,
    normalize_activity_results,
    normalize_momentum_results,
)
from physics_atlas_api.metrics import (
    calculate_activity_raw as calculate_certified_activity_raw,
)
from physics_atlas_api.metrics import (
    calculate_connectivity as calculate_certified_connectivity,
)
from physics_atlas_api.metrics import (
    calculate_diversity as calculate_certified_diversity,
)
from physics_atlas_api.metrics import (
    calculate_impact_raw as calculate_certified_impact_raw,
)
from physics_atlas_api.metrics import (
    calculate_momentum_raw as calculate_certified_momentum_raw,
)


def calculate_activity_raw(
    input_partition: MetricPartitionInput,
    thresholds=METRIC_VALIDATION_THRESHOLDS_V1,  # type: ignore[no-untyped-def]
):  # type: ignore[no-untyped-def]
    return calculate_certified_activity_raw(
        certify_partition(
            input_partition,
            "research_activity_score",
            threshold_version=thresholds.version,
        ),
        thresholds,
    )


def calculate_impact_raw(
    input_partition: MetricPartitionInput,
    cohorts: tuple[CitationReferenceCohort, ...],
    thresholds=METRIC_VALIDATION_THRESHOLDS_V1,  # type: ignore[no-untyped-def]
):  # type: ignore[no-untyped-def]
    certified_cohorts = tuple(
        certify_citation_reference_cohort(item, input_partition) for item in cohorts
    )
    return calculate_certified_impact_raw(
        certify_partition(
            input_partition,
            "research_impact",
            threshold_version=thresholds.version,
            citation_cohorts=certified_cohorts,
        ),
        certified_cohorts,
        thresholds,
    )


def calculate_connectivity(
    input_partition: MetricPartitionInput,
    thresholds=METRIC_VALIDATION_THRESHOLDS_V1,  # type: ignore[no-untyped-def]
):  # type: ignore[no-untyped-def]
    return calculate_certified_connectivity(
        certify_partition(
            input_partition,
            "collaboration",
            threshold_version=thresholds.version,
        ),
        thresholds,
    )


def calculate_diversity(
    input_partition: MetricPartitionInput,
    thresholds=METRIC_VALIDATION_THRESHOLDS_V1,  # type: ignore[no-untyped-def]
):  # type: ignore[no-untyped-def]
    return calculate_certified_diversity(
        certify_partition(
            input_partition,
            "research_diversity",
            threshold_version=thresholds.version,
        ),
        thresholds,
    )


def calculate_momentum_raw(
    input_partition: MetricPartitionInput,
    thresholds=METRIC_VALIDATION_THRESHOLDS_V1,  # type: ignore[no-untyped-def]
):  # type: ignore[no-untyped-def]
    return calculate_certified_momentum_raw(
        certify_partition(
            input_partition,
            "momentum",
            threshold_version=thresholds.version,
        ),
        thresholds,
    )


def complete_coverage(**changes: float | None) -> MetricCoverageEvidence:
    values: dict[str, float | None] = {
        "paper_time_affiliation": 1.0,
        "canonical_institution": 1.0,
        "citation": 1.0,
        "field_attribution": 1.0,
        "collaboration_relationship": 1.0,
    }
    values.update(changes)
    return MetricCoverageEvidence(**values)


def paper(
    index: int,
    year: int,
    *,
    weight: float = 1.0,
    citations: float | None = None,
    citation_cutoff: date | None = None,
    collaborative: bool | None = True,
    cross_institution: bool | None = True,
    international: bool | None = True,
    categories: tuple[tuple[str, float], ...] = (),
) -> AttributedPaperEvidence:
    return AttributedPaperEvidence(
        paper_id=f"paper-{year}-{index}",
        publication_date=date(year, 1, 1),
        document_type="article",
        attribution_weight=weight,
        researcher_ids=(f"researcher-{index % 5}",),
        citation_count=citations,
        citation_observed_at=citation_cutoff,
        collaborative=collaborative,
        cross_institution=cross_institution,
        international=international,
        partner_entity_ids=(f"partner-{index % 3}",) if cross_institution else (),
        category_weights=categories,
    )


def partition(
    entity_id: str,
    papers: tuple[AttributedPaperEvidence, ...],
    *,
    field_id: str = "hep-th",
    terminal_year: int = 2025,
    as_of_date: date = date(2026, 8, 30),
    complete_years: tuple[int, ...] = (2020, 2021, 2022, 2023, 2024, 2025),
    coverage: MetricCoverageEvidence | None = None,
    categories: tuple[str, ...] = (),
    entity_type: str = "institution",
) -> MetricPartitionInput:
    assert entity_type in {"researcher", "institution", "country"}
    return MetricPartitionInput(
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_id=entity_id,
        field_id=field_id,
        terminal_year=terminal_year,
        as_of_date=as_of_date,
        dataset_version="dataset-test-v1",
        acquisition_scope="hep-th-v1",
        attribution_policy_version="fractional-attribution-v1",
        ontology_version="physics-field-ontology-v1",
        mapping_policy_version="provider-field-mapping-v1",
        citation_policy_version="non-self-citation-cutoff-v1",
        coverage=coverage or complete_coverage(),
        complete_source_years=complete_years,
        papers=papers,
        eligible_category_ids=categories,
    )


def test_threshold_configuration_is_explicit_and_matches_v1_policy() -> None:
    thresholds = METRIC_VALIDATION_THRESHOLDS_V1
    assert thresholds.version == "metric-validation-thresholds-v1"
    assert thresholds.coverage.paper_time_affiliation == 0.90
    assert thresholds.coverage.canonical_institution == 0.95
    assert thresholds.coverage.citation == 0.90
    assert thresholds.coverage.field_attribution == 0.90
    assert thresholds.activity.minimum_fractional_papers == 10
    assert thresholds.activity.minimum_distinct_researchers == 5
    assert thresholds.impact.minimum_eligible_papers == 10
    assert thresholds.connectivity.minimum_fractional_papers == 10
    assert thresholds.connectivity.minimum_identifiable_researchers == 5
    assert thresholds.diversity.minimum_fractional_papers == 15
    assert thresholds.momentum.required_complete_years == 6
    assert thresholds.momentum.minimum_fractional_papers_per_window == 10


def test_activity_uses_fractional_output_and_exact_minimum_boundaries() -> None:
    papers = tuple(paper(index, 2025, weight=0.5) for index in range(20))
    result = calculate_activity_raw(partition("institution-a", papers))

    assert result.raw_value == pytest.approx(10.0)
    assert result.raw_unit == "fractional attributed canonical papers"
    assert result.components["distinct_papers"] == 20
    assert result.components["distinct_researchers"] == 5
    assert result.threshold_version == "metric-validation-thresholds-v1"
    assert result.attribution_policy_version == "fractional-attribution-v1"
    assert result.ontology_version == "physics-field-ontology-v1"
    assert len(result.input_manifest_digest) == 64
    assert result.missing_reasons == ()

    insufficient = calculate_activity_raw(
        partition(
            "institution-b",
            tuple(paper(index, 2025, weight=0.499) for index in range(20)),
        )
    )
    assert insufficient.raw_value is None
    assert "fractional paper output" in " ".join(insufficient.missing_reasons)


def test_activity_normalization_is_field_specific_and_reconstructable() -> None:
    thresholds = replace(
        METRIC_VALIDATION_THRESHOLDS_V1,
        version="metric-validation-test-small-cohort-v1",
        activity=replace(
            METRIC_VALIDATION_THRESHOLDS_V1.activity,
            minimum_normalization_cohort=2,
        ),
    )
    first_partition = partition(
        "institution-a", tuple(paper(index, 2025) for index in range(10))
    )
    second_partition = partition(
        "institution-b",
        tuple(paper(index + 100, 2025) for index in range(20)),
    )
    raw_results = (
        calculate_activity_raw(first_partition, thresholds),
        calculate_activity_raw(second_partition, thresholds),
    )
    normalized = normalize_activity_results(raw_results, thresholds)

    assert normalized[0].raw_value == 10
    assert normalized[1].raw_value == 20
    assert normalized[0].normalized_value == 0
    assert normalized[1].normalized_value == 100
    assert normalized[0].normalization_parameters["field_id"] == "hep-th"
    assert normalized[0].normalization_parameters["input_transform"] == "log1p"

    reversed_partition = replace(first_partition, papers=first_partition.papers[::-1])
    assert (
        calculate_activity_raw(reversed_partition, thresholds).input_manifest_digest
        == raw_results[0].input_manifest_digest
    )

    other_field = calculate_activity_raw(
        partition(
            "institution-c",
            tuple(paper(index + 200, 2025) for index in range(10)),
            field_id="cond-mat",
        ),
        thresholds,
    )
    separated = normalize_activity_results((raw_results[0], other_field), thresholds)
    assert all(result.normalized_value is None for result in separated)
    assert all(
        "insufficient normalization cohort" in " ".join(result.missing_reasons)
        for result in separated
    )


def impact_fixture() -> tuple[
    MetricPartitionInput, tuple[CitationReferenceCohort, ...]
]:
    cutoff = date(2026, 12, 31)
    evidence = tuple(
        paper(index, 2022, citations=20, citation_cutoff=cutoff) for index in range(10)
    )
    reference = tuple(
        (f"paper-2022-{index}", 20.0 if index < 10 else 10.0) for index in range(50)
    )
    cohort = CitationReferenceCohort(
        field_id="hep-th",
        publication_year=2022,
        document_type="article",
        observed_at=cutoff,
        citations=reference,
    )
    return (
        partition(
            "institution-impact",
            evidence,
            terminal_year=2024,
            as_of_date=cutoff,
            complete_years=(2022, 2023, 2024),
        ),
        (cohort,),
    )


def test_impact_calculates_fractional_mncs_and_pp_top_10_companion() -> None:
    input_partition, cohorts = impact_fixture()
    result = calculate_impact_raw(input_partition, cohorts)

    assert result.raw_value == pytest.approx(20 / 12)
    assert result.components["mncs"] == pytest.approx(20 / 12)
    assert result.components["pp_top_10_share"] == 1.0
    assert result.components["eligible_papers"] == 10
    assert result.components["citation_cutoff"] == "2026-12-31T00:00:00+00:00"
    assert result.normalized_value is None
    assert result.missing_reasons == ()


def test_impact_distinguishes_missing_citations_from_recorded_zero() -> None:
    input_partition, cohorts = impact_fixture()
    missing_papers = (
        replace(
            input_partition.papers[0],
            citation_count=None,
            citation_observed_at=None,
        ),
        *input_partition.papers[1:],
    )
    with pytest.raises(CertificationError, match="differs from its certified cohort"):
        calculate_impact_raw(replace(input_partition, papers=missing_papers), cohorts)

    zero_papers = (
        replace(input_partition.papers[0], citation_count=0),
        *input_partition.papers[1:],
    )
    zero_reference = replace(
        cohorts[0],
        citations=((cohorts[0].citations[0][0], 0.0), *cohorts[0].citations[1:]),
    )
    measured_zero = calculate_impact_raw(
        replace(input_partition, papers=zero_papers), (zero_reference,)
    )
    assert measured_zero.components["eligible_papers"] == 10
    assert measured_zero.raw_value is not None


def test_connectivity_uses_mature_proportions_and_preserves_graph_companions() -> None:
    papers = tuple(
        paper(index, 2025, cross_institution=index < 5) for index in range(10)
    )
    result = calculate_connectivity(partition("institution-network", papers))

    assert result.raw_value == 0.5
    assert result.normalized_value == 50
    assert result.components["primary_indicator"] == "cross_institution"
    assert result.components["unique_supported_partners"] == 3
    assert result.components["network_centrality_used"] is False

    isolated = calculate_connectivity(
        partition(
            "institution-isolated",
            tuple(
                paper(
                    index + 100,
                    2025,
                    cross_institution=False,
                    international=False,
                )
                for index in range(10)
            ),
        )
    )
    assert isolated.raw_value == 0
    assert isolated.normalized_value == 0
    assert isolated.missing_reasons == ()


def test_connectivity_withholds_unresolved_relationships_instead_of_zeroing() -> None:
    papers = tuple(
        paper(index, 2025, cross_institution=None if index < 2 else False)
        for index in range(10)
    )
    with pytest.raises(CertificationError, match="coverage is not certified"):
        calculate_connectivity(
            partition(
                "institution-unresolved",
                papers,
                coverage=complete_coverage(collaboration_relationship=0.8),
            )
        )


def test_researcher_connectivity_does_not_require_geographic_attribution() -> None:
    papers = tuple(paper(index, 2025, collaborative=True) for index in range(10))
    result = calculate_connectivity(
        partition(
            "researcher-network",
            papers,
            entity_type="researcher",
            coverage=complete_coverage(
                paper_time_affiliation=None,
                canonical_institution=None,
            ),
        )
    )

    assert result.raw_value == 1
    assert result.normalized_value == 100
    assert result.missing_reasons == ()


def test_diversity_distinguishes_concentration_from_missing_classification() -> None:
    balanced = calculate_diversity(
        partition(
            "institution-balanced",
            tuple(
                paper(
                    index,
                    2025,
                    categories=(("theory", 1.0),)
                    if index < 8
                    else (("phenomenology", 1.0),),
                )
                for index in range(15)
            ),
            categories=("theory", "phenomenology"),
        )
    )
    assert balanced.raw_value == pytest.approx(
        -(8 / 15 * math.log(8 / 15) + 7 / 15 * math.log(7 / 15)) / math.log(2)
    )
    assert balanced.components["variety"] == 2
    assert balanced.components["disparity"] is None

    concentrated = calculate_diversity(
        partition(
            "institution-concentrated",
            tuple(
                paper(index + 100, 2025, categories=(("theory", 1.0),))
                for index in range(15)
            ),
            categories=("theory", "phenomenology"),
        )
    )
    assert concentrated.raw_value == 0
    assert concentrated.normalized_value == 0
    assert concentrated.missing_reasons == ()

    incomplete = calculate_diversity(
        partition(
            "institution-unclassified",
            tuple(
                paper(
                    index + 200,
                    2025,
                    categories=(("theory", 1.0),) if index < 13 else (),
                )
                for index in range(15)
            ),
            categories=("theory", "phenomenology"),
        )
    )
    assert incomplete.raw_value is None
    assert "field attribution coverage" in " ".join(incomplete.missing_reasons)


def momentum_partition(
    entity_id: str, baseline_per_year: int, recent_per_year: int
) -> MetricPartitionInput:
    records: list[AttributedPaperEvidence] = []
    index = 0
    for year in (2020, 2021, 2022):
        for _ in range(baseline_per_year):
            records.append(paper(index, year))
            index += 1
    for year in (2023, 2024, 2025):
        for _ in range(recent_per_year):
            records.append(paper(index, year))
            index += 1
    return partition(entity_id, tuple(records))


def test_momentum_is_backward_looking_field_relative_and_robust() -> None:
    thresholds = replace(
        METRIC_VALIDATION_THRESHOLDS_V1,
        version="metric-validation-test-momentum-cohort-v1",
        momentum=replace(
            METRIC_VALIDATION_THRESHOLDS_V1.momentum,
            minimum_normalization_cohort=3,
        ),
    )
    raw = tuple(
        calculate_momentum_raw(item, thresholds)
        for item in (
            momentum_partition("decline", 7, 4),
            momentum_partition("median", 4, 4),
            momentum_partition("growth", 4, 7),
        )
    )
    assert raw[0].raw_value == pytest.approx(math.log(12 / 21))
    assert raw[1].raw_value == 0
    assert raw[2].raw_value == pytest.approx(math.log(21 / 12))
    normalized = normalize_momentum_results(raw, thresholds)
    scores = {item.entity_id: item.normalized_value for item in normalized}
    assert scores["decline"] < 50
    assert scores["median"] == 50
    assert scores["growth"] > 50
    assert normalized[1].components["field_relative_log_change"] == 0
    assert normalized[1].components["persistence_fraction_of_years"] == 1

    with pytest.raises(CertificationError, match="metric window is not certified"):
        calculate_momentum_raw(
            replace(momentum_partition("current-year", 4, 4), terminal_year=2026),
            thresholds,
        )


def test_physics_wide_aggregation_is_field_balanced_and_coverage_aware() -> None:
    leaf_fields = tuple(
        item.id
        for item in PHYSICS_FIELD_ONTOLOGY_V1.fields
        if item.node_kind == "field"
    )
    field_calculations = tuple(
        bind_metric_calculation(
            calculate_certified_connectivity(certified),
            certified,
        )
        for field_index, field_id in enumerate(leaf_fields)
        for certified in (
            certify_partition(
                partition(
                    "institution-domain",
                    tuple(
                        paper(
                            field_index * 100 + index,
                            2025,
                            cross_institution=index
                            < ({"hep-th": 2, "cond-mat": 8}.get(field_id, 5)),
                        )
                        for index in range(10)
                    ),
                    field_id=field_id,
                ),
                "collaboration",
            ),
        )
    )
    field_observations = apply_atlas_scale(
        field_calculations,
        normalization_populations=certify_normalization_populations(field_calculations),
    )

    def field_population():  # type: ignore[no-untyped-def]
        complete_weights = tuple((field_id, 1.0) for field_id in leaf_fields)
        evidence = FieldPopulationEvidence(
            entity_id="institution-domain",
            metric_id="collaboration",
            period="2025",
            dataset_version="dataset-test-v1",
            acquisition_scope="hep-th-v1",
            ontology_version="physics-field-ontology-v1",
            field_weights=complete_weights,
            source_manifest_digest="a" * 64,
            review_state="reviewed-approved",
            reviewed_by="test-fixture-reviewer",
            reviewed_at=datetime(2026, 8, 30, tzinfo=UTC),
        )
        return certify_field_population(
            replace(evidence, source_manifest_digest=evidence.content_digest)
        )

    population_proof = field_population()
    aggregated = aggregate_physics_wide(
        field_observations,
        (population_proof,),
    )[0]
    assert aggregated.calculation.normalized_value == 50
    assert (
        aggregated.calculation.components["publication_volume_used_as_final_weight"]
        is False
    )
    assert aggregated.calculation.components["field_evidence_coverage"] == 1
    with pytest.raises(CertificationError, match="Atlas field observations"):
        CertifiedPhysicsAggregation(  # type: ignore[arg-type]
            calculation=aggregated.calculation,
            field_observations=(object(),),
            field_population_proof=population_proof,
            thresholds=aggregated.thresholds,
            proof_digest=aggregated.proof_digest,
        )
    with pytest.raises(CertificationError, match="field-population proof"):
        CertifiedPhysicsAggregation(  # type: ignore[arg-type]
            calculation=aggregated.calculation,
            field_observations=aggregated.field_observations,
            field_population_proof=object(),
            thresholds=aggregated.thresholds,
            proof_digest=aggregated.proof_digest,
        )

    withheld = aggregate_physics_wide(
        field_observations[:-2],
        (field_population(),),
    )[0]
    assert withheld.calculation.normalized_value is None
    assert "field evidence coverage" in " ".join(withheld.calculation.missing_reasons)
