"""Compact scientific facts reproduce bounded inputs without retaining a proof DAG."""

import hashlib
import json
from dataclasses import replace

import pytest
from test_conditional_observed_release import source_year as unknown_source_year
from test_launch_calculations import _window, _year
from test_observed_citation_membership import KEY, _case

from physics_atlas_api.certification import CertificationError, EvidenceReference
from physics_atlas_api.certification.build_cache import bounded_build_verification_cache
from physics_atlas_api.certification.launch_calculations import (
    calculate_launch_metric_cohort,
)
from physics_atlas_api.certification.launch_retained import (
    _Export,
    build_launch_retained,
    rehydrate_launch_metric_input,
)
from physics_atlas_api.certification.measurement_windows import (
    CertifiedObservedSessionCitationCohort,
)
from physics_atlas_api.certification.years import (
    EnumeratedLaunchSourceYearEvidence,
    certify_source_year,
    qualify_observed_release_source_year,
)
from physics_atlas_api.fields import PHYSICS_FIELD_ONTOLOGY_V1
from physics_atlas_api.metrics.aggregation import (
    aggregate_ontology_branch,
    certify_field_population,
    derive_ontology_branch_population,
)
from physics_atlas_api.metrics.calculators import (
    calculate_activity_raw,
    calculate_connectivity,
    calculate_diversity,
    calculate_momentum_raw,
)
from physics_atlas_api.metrics.presentation import (
    CertifiedMetricCalculation,
    apply_atlas_scale,
)


@pytest.fixture(scope="module")
def retained_case():  # type: ignore[no-untyped-def]
    with bounded_build_verification_cache():
        years = []
        for year in (2021, 2022, 2023):
            original = _year(year)
            years.append(
                qualify_observed_release_source_year(
                    certify_source_year(
                        EnumeratedLaunchSourceYearEvidence(**vars(original.evidence)),
                        original.coverage,
                    )
                )
            )
        observations = calculate_launch_metric_cohort(
            _window(tuple(years), "collaboration"), field_id="nucl-th"
        )
        extra = EvidenceReference(
            "ror", "test-only-extra", "a" * 64, "snapshot-extra", "source:extra"
        )
        built = build_launch_retained(
            tuple(years), observations, source_references=(extra,)
        )
        yield tuple(years), observations, built


def test_deterministic_compact_export_preserves_exact_metric_inputs(retained_case):  # type: ignore[no-untyped-def]
    years, observations, built = retained_case
    assert built.sha256 == hashlib.sha256(built.content).hexdigest()
    assert built.byte_length == len(built.content)
    document = json.loads(built.content)
    assert len(document["papers"]) == 6
    assert len(document["sourceYears"]) == 3
    assert len(document["published_observations"]) == len(observations) == 2
    assert any(
        ref["source_snapshot_id"] == "snapshot-extra"
        for ref in document["references"].values()
    )
    for observation in observations:
        proof = observation.certification_proof
        assert isinstance(proof, CertifiedMetricCalculation)
        recovered = rehydrate_launch_metric_input(
            document, proof.partition.certification.input_digest
        )
        assert recovered == proof.partition.partition
        # A bare restored input is NOT a certified calculator boundary.
        with pytest.raises((CertificationError, TypeError)):
            calculate_connectivity(recovered)
        rebound = replace(proof.partition, partition=recovered)
        assert calculate_connectivity(rebound) == proof.calculation
    replay = build_launch_retained(
        tuple(reversed(years)),
        tuple(reversed(observations)),
        source_references=(
            EvidenceReference(
                "ror", "test-only-extra", "a" * 64, "snapshot-extra", "source:extra"
            ),
        ),
    )
    assert replay.content == built.content
    assert b'"source_proof"' not in built.content
    assert b'"raw_payload"' not in built.content


def test_conservation_missing_and_compact_certification_are_preserved(retained_case):  # type: ignore[no-untyped-def]
    _, _, built = retained_case
    doc = json.loads(built.content)
    for paper in doc["papers"].values():
        assert (
            sum(weight for _, weight in paper["field_weights"])
            + paper["unmapped_field_mass"]
            == 1
        )
        for kind in ("institution", "country", "researcher"):
            assert sum(
                weight
                for item_kind, _, weight in paper["entity_shares"]
                if kind == item_kind
            ) + dict(paper["unresolved_entity_mass"])[kind] == pytest.approx(1)
        assert paper["attribution"][0]["fractional"]["total_weight"] == [1, 1]
        assert len(paper["known_researcher_ids"]) == 5
    for input_digest in doc["partitions"]:
        recovered = rehydrate_launch_metric_input(doc, input_digest)
        assert all(paper.citation_count is None for paper in recovered.papers)
    for calculation in doc["calculations"].values():
        assert calculation["certification"]["state"] == "certified"
        assert calculation["certification"]["decisions"]
        assert all(
            key in doc["decisions"] for key in calculation["certification"]["decisions"]
        )
    broken = json.loads(built.content)
    key = next(iter(broken["partitions"]))
    paper_id = broken["partitions"][key]["papers"][0]
    broken["papers"][paper_id]["unambiguous_researcher_subset"]["researcher_ids"] = []
    with pytest.raises(CertificationError, match="checksum mismatch"):
        rehydrate_launch_metric_input(broken, key)


def test_repeated_sources_deduplicate_and_legacy_sources_are_rejected(retained_case):  # type: ignore[no-untyped-def]
    years, _, _ = retained_case
    duplicated = build_launch_retained((*years, *years), ())
    assert dict(duplicated.counts)["papers"] == 6
    assert dict(duplicated.counts)["sourceYears"] == 3
    with (
        bounded_build_verification_cache(),
        pytest.raises(CertificationError, match="qualified observed"),
    ):
        build_launch_retained((_year(2020),), ())


def test_full_citation_receipts_and_count_independent_membership_retained() -> None:
    with bounded_build_verification_cache():
        population, session = _case()
        cohort = CertifiedObservedSessionCitationCohort(population, session, KEY)
        exporter = _Export(
            (
                population.source_years[0].dataset_version,
                population.source_years[0].acquisition_scope,
            )
        )
        key = exporter.cohort(cohort)
        exporter.cohort(cohort)
        assert len(exporter.tables["citationPages"]) == 1
        assert len(exporter.tables["citationCohorts"]) == 1
        row = exporter.tables["citationCohorts"][key]
        assert len(row["frozen_observed_paper_ids"]) == 50
        assert row["reference_population"]["unknownTargetMembershipPaperCount"] == 1
        page = next(iter(exporter.tables["citationPages"].values()))
        assert len(page["records"]) == 51
        assert page["requested_at"] == session.pages[0].requested_at.isoformat()
        assert page["received_at"] == session.pages[0].received_at.isoformat()
        missing = next(
            record for record in page["records"] if record["source_record_id"] == "51"
        )
        assert missing["non_self_citation_count"] is None
        assert missing["raw_citation_count"] == 53
        assert missing["unresolved_membership"]
        assert row["reference_population"]["completeFieldUniverse"] is False


@pytest.mark.parametrize(
    "metric,field,calculator",
    [
        ("research_activity_score", "nucl-th", calculate_activity_raw),
        ("research_diversity", "nuclear", calculate_diversity),
        ("momentum", "nucl-th", calculate_momentum_raw),
    ],
)
def test_other_raw_calculators_reconstruct_without_new_certification(
    retained_case,
    metric,
    field,
    calculator,
):  # type: ignore[no-untyped-def]
    years, _, _ = retained_case
    if metric == "momentum":
        earlier = []
        for year in (2018, 2019, 2020):
            original = _year(year)
            earlier.append(
                qualify_observed_release_source_year(
                    certify_source_year(
                        EnumeratedLaunchSourceYearEvidence(**vars(original.evidence)),
                        original.coverage,
                    )
                )
            )
        years = (*earlier, *years)
    observations = calculate_launch_metric_cohort(
        _window(years, metric), field_id=field
    )
    built = build_launch_retained(years, observations)
    doc = json.loads(built.content)
    for observation in observations:
        proof = observation.certification_proof
        recovered = rehydrate_launch_metric_input(
            doc, proof.partition.certification.input_digest
        )
        assert recovered == proof.partition.partition
        assert (
            calculator(replace(proof.partition, partition=recovered))
            == proof.calculation
        )
        assert observation.value is None  # no synthetic small-sample zero fabrication


def test_unresolved_identities_and_source_quality_failures_are_retained() -> None:
    with bounded_build_verification_cache():
        year = qualify_observed_release_source_year(unknown_source_year())
        built = build_launch_retained((year,), ())
        doc = json.loads(built.content)
        assert len(doc["papers"]) == len(year.evidence.paper_projections)
        quality = next(iter(doc["sourceYears"].values()))["source_quality"]
        assert quality["state"] == "insufficient_evidence" and quality["reasons"]
        original_states = {
            item.decision_id: (item.state, list(item.reasons), item.rule_version)
            for item in year.evidence.structural_decisions
        }
        assert all(
            (
                doc["decisions"][key]["state"],
                doc["decisions"][key]["reasons"],
                doc["decisions"][key]["rule_version"],
            )
            == value
            for key, value in original_states.items()
        )
        assert any(paper["unmapped_field_mass"] > 0 for paper in doc["papers"].values())
        unresolved = [
            paper
            for paper in doc["papers"].values()
            if paper["canonical_identity_state"] != "matched"
        ]
        assert unresolved and all(paper["entity_shares"] == [] for paper in unresolved)
        assert not doc["published_observations"]


def test_branch_observation_retains_leaf_and_peer_proofs_once(retained_case):  # type: ignore[no-untyped-def]
    years, original, _ = retained_case
    leaves = (
        original[0],
        calculate_launch_metric_cohort(
            _window(years, "collaboration"),
            field_id="nucl-ex",
        )[0],
    )
    population = certify_field_population(
        derive_ontology_branch_population(
            PHYSICS_FIELD_ONTOLOGY_V1.get("nuclear"),
            leaves,
        )
    )
    branch = apply_atlas_scale(aggregate_ontology_branch(leaves, (population,)))
    built = build_launch_retained(years, branch)
    doc = json.loads(built.content)
    assert len(doc["aggregations"]) == len(doc["published_observations"]) == 1
    assert len(doc["observations"]) == 3  # branch plus its two exact leaves
    aggregation = next(iter(doc["aggregations"].values()))
    assert len(aggregation["field_observations"]) == 2
    assert set(map(tuple, aggregation["field_population"]["field_weights"])) == {
        ("nucl-th", 1),
        ("nucl-ex", 1),
    }
    assert len(doc["papers"]) == 6  # no per-field/per-entity copies
