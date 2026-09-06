"""Bounded plan tests use only explicit synthetic transport/parser fixtures."""

import json
from dataclasses import fields, replace
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from test_evidence_certification import _year_evidence

from physics_atlas_api.backfill import build_partitions
from physics_atlas_api.certification import (
    CertificationError,
    CertifiedSourceYear,
    CoveragePopulationEvidence,
    EvidenceCertificationDecision,
    EvidenceReference,
    canonical_digest,
    certify_coverage,
    certify_source_year,
    source_record_inventory_digest,
)
from physics_atlas_api.certification.automation import (
    AutomaticEvidenceContext,
    AutomaticPaperIdentityDecision,
    automatic_paper_identity_decision,
    capture_automatic_paper_facts,
)
from physics_atlas_api.certification.launch_scope import (
    BOUNDED_LAUNCH_DATE_BASIS,
    BOUNDED_LAUNCH_PLAN_VERSION,
    BOUNDED_LAUNCH_QUERY_VERSION,
    BOUNDED_LAUNCH_SCOPE,
    bounded_launch_partitions,
    bounded_launch_source_plan,
)
from physics_atlas_api.certification.rules import evidence_rule_version
from physics_atlas_api.certification.source_pages import capture_inspire_source_page
from physics_atlas_api.certification.years import (
    RecordPageSourcePartitionEvidence,
    SourceEntityType,
)
from physics_atlas_api.connectors.inspire import InspireConnector

_CUTOFF = datetime(2026, 9, 6, tzinfo=UTC)


def launch_source_year(
    year: int, entity_type: SourceEntityType = "researcher"
) -> CertifiedSourceYear:
    """One reconciled synthetic source year, not a metric-threshold/full-gate proof."""
    original = _year_evidence(year)
    plan = bounded_launch_source_plan(
        calendar_year=year,
        cutoff=_CUTOFF,
        dataset_version="test-only-nuclear-launch-v1",
    )
    partition_id = plan.partitions[0][0]
    record_id = year * 100 + 1
    payload = json.dumps(
        {
            "hits": {
                "total": 1,
                "hits": [
                    {
                        "id": str(record_id),
                        "metadata": {
                            "control_number": record_id,
                            "titles": [
                                {"title": "Explicit synthetic nuclear launch fixture"}
                            ],
                            "preprint_date": f"{year}-01-01",
                            "document_type": ["article"],
                            "authors": [{"recid": "1"}],
                            "arxiv_eprints": [
                                {
                                    "value": f"{year % 100:02d}01.00001",
                                    "categories": ["nucl-th", "nucl-ex"],
                                }
                            ],
                        },
                    }
                ],
            },
        }
    ).encode()
    page, records = capture_inspire_source_page(
        payload,
        connector=InspireConnector(Mock(), "https://inspirehep.net/api"),
        partition_id=partition_id,
    )
    record = records[0]
    reference = EvidenceReference(
        "inspire", record.source_record_id, record.checksum, partition_id
    )
    facts = capture_automatic_paper_facts(
        record,
        context=AutomaticEvidenceContext(
            f"launch-paper-{year}", plan.dataset_version, plan.acquisition_scope
        ),
        reference=reference,
        declared_date_basis=plan.declared_date_basis,
    )
    assert facts.exact_date is not None
    projection = replace(
        original.paper_projections[0],
        paper_id=facts.context.paper_id,
        publication_date=facts.exact_date,
        occurrence_references=(reference,),
        field_weights=(("nucl-th", 0.5), ("nucl-ex", 0.5)),
        entity_shares=((entity_type, "test-only-entity", 1.0),),
        unresolved_entity_mass=((entity_type, 0.0),),
    )
    structural = tuple(
        automatic_paper_identity_decision(
            facts, evidence_kind="publication-metric-date"
        )
        if item.evidence_kind == "publication-metric-date"
        else replace(
            item,
            subject_id=projection.paper_id,
            dataset_version=plan.dataset_version,
            acquisition_scope=plan.acquisition_scope,
            evidence=(reference,),
            certified_value_digest=projection.decision_value_digest(item.evidence_kind),
        )
        for item in original.structural_decisions
    )
    coverage_decision = replace(
        original.coverage_decisions[0],
        subject_id=projection.paper_id,
        dataset_version=plan.dataset_version,
        acquisition_scope=plan.acquisition_scope,
        evidence=(reference,),
    )
    coverage = certify_coverage(
        "field-classification",
        (coverage_decision,),
        CoveragePopulationEvidence(
            "field-classification",
            ((projection.paper_id, 1.0),),
            ((projection.paper_id, 1.0),),
            canonical_digest((projection,)),
        ),
    )
    base_partition = replace(
        original.partitions[0],
        partition_id=partition_id,
        page_checksums=(page.page_checksum,),
        record_inventory_digest=source_record_inventory_digest((reference,)),
    )
    source_partition = RecordPageSourcePartitionEvidence(
        **vars(base_partition), pages=(page,)
    )
    evidence = replace(
        original,
        entity_type=entity_type,
        cutoff=plan.cutoff,
        dataset_version=plan.dataset_version,
        acquisition_scope=plan.acquisition_scope,
        acquisition_plan=plan,
        required_partition_ids=(partition_id,),
        paper_projections=(projection,),
        partitions=(source_partition,),
        structural_decisions=structural,
        coverage_decisions=(coverage_decision,),
    )
    result = certify_source_year(evidence, (coverage,))
    assert result.state == "certified", result.reasons
    return result


def test_actual_page_receipt_and_explicit_date_basis_certify_each_bounded_year() -> (
    None
):
    for year in range(2018, 2024):
        result = launch_source_year(year)
        assert result.state == "certified"
        assert result.calendar_year == year
        assert result.acquisition_scope == BOUNDED_LAUNCH_SCOPE
        assert len(result.evidence.paper_projections) == 1
        page = result.evidence.partitions[0]
        assert isinstance(page, RecordPageSourcePartitionEvidence)
        record_reference = result.evidence.paper_projections[0].occurrence_references[0]
        assert page.page_checksums != (record_reference.checksum,)


def test_bounded_year_rejects_record_hash_relabelled_as_parent_page_hash() -> None:
    result = launch_source_year(2020)
    partition = result.evidence.partitions[0]
    record_reference = result.evidence.paper_projections[0].occurrence_references[0]
    with pytest.raises(ValueError):
        replace(partition, page_checksums=(record_reference.checksum,))


def test_bounded_year_rejects_unlabelled_date_even_when_literal_date_is_equal() -> None:
    result = launch_source_year(2020)
    actual = next(
        item
        for item in result.evidence.structural_decisions
        if item.evidence_kind == "publication-metric-date"
    )
    assert isinstance(actual, AutomaticPaperIdentityDecision)
    base_fields = {
        item.name: getattr(actual, item.name)
        for item in fields(EvidenceCertificationDecision)
    }
    unlabelled = EvidenceCertificationDecision(
        **{
            **base_fields,
            "rule_version": evidence_rule_version("publication-metric-date"),
        }
    )
    evidence = replace(
        result.evidence,
        structural_decisions=tuple(
            unlabelled if item is actual else item
            for item in result.evidence.structural_decisions
        ),
    )
    changed = certify_source_year(evidence, result.coverage)
    assert changed.state == "conflicted"
    assert (
        "bounded launch year lacks exact source-bound dates or record/page receipts"
        in changed.certification.reasons
    )


def test_bounded_recipe_is_exact_six_year_nuclear_scope_not_global_registry() -> None:
    legacy = build_partitions()
    partitions = bounded_launch_partitions()
    assert len(partitions) == 6
    assert tuple(item.year for item in partitions) == tuple(range(2018, 2024))
    for item in partitions:
        assert item.query == (
            "document_type:article and "
            "(subject:Theory-Nucl or subject:Experiment-Nucl) "
            f"and preprint_date:{item.year}-01-01->{item.year}-12-31"
        )
        assert item.query_version == BOUNDED_LAUNCH_QUERY_VERSION
        assert item.acquisition_scope == BOUNDED_LAUNCH_SCOPE
        assert item.endpoint == "https://inspirehep.net/api/literature"
        assert item.page_size == 250 and item.provider == "inspire"
    assert legacy == build_partitions()
    assert {item.year for item in legacy} == set(range(2020, 2026))


def test_plan_declares_frozen_ontology_members_without_claiming_certification() -> None:
    plan = bounded_launch_source_plan(
        calendar_year=2020, cutoff=_CUTOFF, dataset_version="test-only-launch"
    )
    assert plan.root_field_id == "nuclear"
    assert set(plan.expected_leaf_ids) == {"nucl-th", "nucl-ex"}
    assert plan.declared_date_basis == BOUNDED_LAUNCH_DATE_BASIS
    assert plan.rule_version == BOUNDED_LAUNCH_PLAN_VERSION
    assert plan.partitions == ((f"{BOUNDED_LAUNCH_SCOPE}:inspire:2020", "inspire"),)
    assert plan.source_manifest_digest == plan.content_digest
    assert not hasattr(plan, "state")
    assert not hasattr(plan, "reviewed_by")


@pytest.mark.parametrize("year", [2017, 2024, 2025, 2026])
def test_unsupported_year_cannot_widen_bounded_launch(year: int) -> None:
    with pytest.raises(CertificationError):
        bounded_launch_source_plan(
            calendar_year=year, cutoff=_CUTOFF, dataset_version="test-only"
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"root_field_id": "physics"},
        {"root_field_id": "nuclear-physics"},
        {"acquisition_scope": "hep-th-v1"},
        {"declared_date_basis": "journal-online-publication"},
        {"rule_version": "approved-unbounded"},
        {"dataset_version": ""},
        {"cutoff": datetime(2020, 1, 1, tzinfo=UTC)},
        {"cutoff": datetime(2026, 1, 1)},
    ],
)
def test_plan_rejects_scope_basis_version_or_closed_year_drift(
    changes: dict[str, object],
) -> None:
    plan = bounded_launch_source_plan(
        calendar_year=2020, cutoff=_CUTOFF, dataset_version="test-only"
    )
    with pytest.raises(CertificationError):
        replace(plan, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"query": "document_type:article"},
        {"endpoint": "https://example.invalid"},
        {"page_size": 1000},
        {"query_version": "earliest-record-date-v1"},
    ],
)
def test_plan_reconstructs_exact_query_and_limits(changes: dict[str, object]) -> None:
    plan = bounded_launch_source_plan(
        calendar_year=2020, cutoff=_CUTOFF, dataset_version="test-only"
    )
    altered = replace(plan.query_partitions[0], **changes)
    with pytest.raises(CertificationError):
        replace(plan, query_partitions=(altered,))
