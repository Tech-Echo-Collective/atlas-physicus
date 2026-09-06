"""Synthetic parser/admission fixtures: no acquired or production evidence."""

import json
from dataclasses import fields, replace
from datetime import date
from typing import Any
from unittest.mock import Mock

import pytest
from test_evidence_certification import _year_evidence
from test_metric_system_v1 import paper, partition

from physics_atlas_api.certification import (
    CertificationError,
    CertifiedSourceYear,
    CoveragePopulationEvidence,
    EvidenceCertificationDecision,
    EvidenceReference,
    canonical_digest,
    certify_coverage,
    certify_metric_window,
    certify_source_year,
    paper_evidence_value_digest,
    source_record_inventory_digest,
)
from physics_atlas_api.certification.automation import (
    AutomaticEvidenceContext,
    AutomaticPaperIdentityDecision,
    SourceBoundPaperFacts,
    automatic_paper_identity_decision,
    capture_automatic_paper_facts,
    verify_automatic_date_axis,
)
from physics_atlas_api.certification.materialization import (
    build_certified_metric_partition,
)
from physics_atlas_api.certification.populations import (
    derive_metric_population,
    metric_population_coverage_ledger,
)
from physics_atlas_api.certification.rules import (
    evidence_decision_is_current,
    evidence_rule_version,
    required_paper_evidence,
)
from physics_atlas_api.certification.source_pages import (
    SourceRecordPageReceipt,
    capture_inspire_source_page,
)
from physics_atlas_api.certification.years import RecordPageSourcePartitionEvidence
from physics_atlas_api.connectors.base import SourceRecord
from physics_atlas_api.connectors.inspire import InspireConnector
from physics_atlas_api.metrics.calculators import calculate_activity_raw


def _captured(
    year: int = 2023, index: int = 1, **changes: Any
) -> tuple[SourceBoundPaperFacts, SourceRecordPageReceipt]:
    metadata = {
        "control_number": year * 100 + index,
        "titles": [{"title": "Explicit synthetic admission fixture"}],
        "preprint_date": f"{year}-01-01",
        "earliest_date": "1999-01-01",
        "authors": [{"recid": str(item)} for item in range(1, 6)],
        **changes,
    }
    connector = InspireConnector(Mock(), "https://inspirehep.net/api")
    payload = json.dumps(
        {
            "hits": {
                "total": 1,
                "hits": [{"id": str(year * 100 + index), "metadata": metadata}],
            }
        }
    ).encode()
    receipt, records = capture_inspire_source_page(
        payload, connector=connector, partition_id=f"inspire-{year}"
    )
    record = records[0]
    reference = EvidenceReference(
        "inspire", record.source_record_id, record.checksum, f"inspire-{year}"
    )
    facts = capture_automatic_paper_facts(
        record,
        context=AutomaticEvidenceContext(
            f"paper-{year}-{index}", "paired-trial-v1", "paired-field-trial-v1"
        ),
        reference=reference,
        declared_date_basis="inspire-preprint-date",
    )
    return facts, receipt


def _facts(year: int = 2023, index: int = 1, **changes: Any) -> SourceBoundPaperFacts:
    return _captured(year, index, **changes)[0]


def _source_year(
    year: int,
) -> tuple[CertifiedSourceYear, tuple[SourceBoundPaperFacts, ...]]:
    original = _year_evidence(year)
    captures = tuple(_captured(year, index) for index in range(1, 11))
    facts = tuple(item for item, _ in captures)
    pages = tuple(page for _, page in captures)
    projections = tuple(
        replace(
            original.paper_projections[0],
            paper_id=item.context.paper_id,
            occurrence_references=(item.reference,),
            entity_shares=(("researcher", "inspire-author:1", 1.0),),
        )
        for item in facts
    )
    projections = tuple(sorted(projections, key=lambda item: item.paper_id))
    by_id = {item.context.paper_id: item for item in facts}
    structural = tuple(
        automatic_paper_identity_decision(
            by_id[projection.paper_id], evidence_kind="publication-metric-date"
        )
        if original_decision.evidence_kind == "publication-metric-date"
        else replace(
            original_decision,
            subject_id=projection.paper_id,
            evidence=projection.occurrence_references,
            certified_value_digest=projection.decision_value_digest(
                original_decision.evidence_kind
            ),
        )
        for projection in projections
        for original_decision in original.structural_decisions
    )
    coverage_decisions = tuple(
        replace(
            original.coverage_decisions[0],
            subject_id=item.paper_id,
            evidence=item.occurrence_references,
        )
        for item in projections
    )
    coverage = certify_coverage(
        "field-classification",
        coverage_decisions,
        CoveragePopulationEvidence(
            "field-classification",
            tuple((item.paper_id, 1.0) for item in projections),
            tuple((item.paper_id, 1.0) for item in projections),
            canonical_digest(projections),
        ),
    )
    partition_evidence = replace(
        original.partitions[0],
        expected_unique_records=10,
        observed_records=10,
        observed_unique_records=10,
        page_checksums=tuple(item.page_checksum for item in pages),
        record_inventory_digest=source_record_inventory_digest(
            tuple(item.reference for item in facts)
        ),
    )
    bound_partition = RecordPageSourcePartitionEvidence(
        **partition_evidence.__dict__, pages=pages
    )
    evidence = replace(
        original,
        paper_projections=projections,
        structural_decisions=structural,
        coverage_decisions=coverage_decisions,
        partitions=(bound_partition,),
    )
    result = certify_source_year(evidence, (coverage,))
    assert result.state == "certified", result.reasons
    return result, facts


def _admitted():  # type: ignore[no-untyped-def]
    sources = tuple(_source_year(year) for year in (2023, 2024, 2025))
    facts = {
        item.context.paper_id: item for _, year_facts in sources for item in year_facts
    }
    years = tuple(item for item, _ in sources)
    window = certify_metric_window(
        metric_id="research_activity_score",
        entity_type="researcher",
        terminal_year=2025,
        source_years=years,
        threshold_version="metric-validation-thresholds-v1",
    )
    value = replace(
        partition(
            "inspire-author:1",
            tuple(
                replace(
                    paper(index, year),
                    paper_id=f"paper-{year}-{index}",
                    researcher_ids=tuple(
                        f"inspire-author:{item}" for item in range(1, 6)
                    ),
                )
                for year in (2023, 2024, 2025)
                for index in range(1, 11)
            ),
        ),
        entity_type="researcher",
        dataset_version="paired-trial-v1",
        acquisition_scope="paired-field-trial-v1",
        as_of_date=window.cutoff.date(),
    )
    population = derive_metric_population(
        window, entity_id=value.entity_id, field_id="hep-th", assessed_at=window.cutoff
    )
    decisions = tuple(
        automatic_paper_identity_decision(facts[item.paper_id], evidence_kind=kind)
        if kind in {"publication-metric-date", "researcher-identity"}
        else EvidenceCertificationDecision(
            subject_type="paper",
            subject_id=item.paper_id,
            evidence_kind=kind,
            state="certified",
            rule_version=evidence_rule_version(kind),
            dataset_version=value.dataset_version,
            acquisition_scope=value.acquisition_scope,
            evidence=(facts[item.paper_id].reference,),
            certified_value_digest=paper_evidence_value_digest(value, item, kind),
        )
        for item in value.papers
        for kind in required_paper_evidence("research_activity_score", "researcher")
    )
    ledger = metric_population_coverage_ledger(population.certification.evidence)
    coverage_decisions = tuple(
        EvidenceCertificationDecision(
            subject_type="coverage-unit",
            subject_id=item.unit_id,
            evidence_kind="field-classification",
            state="certified",
            rule_version=evidence_rule_version("field-classification"),
            dataset_version=value.dataset_version,
            acquisition_scope=value.acquisition_scope,
            evidence=(facts[item.paper_id].reference,),
        )
        for item in ledger
    )
    coverage = certify_coverage(
        "field-classification",
        coverage_decisions,
        CoveragePopulationEvidence(
            "field-classification",
            tuple((item.unit_id, item.mass) for item in ledger),
            tuple(
                sorted(
                    (item.paper_id, item.attribution_weight) for item in value.papers
                )
            ),
            population.certification.projection_digest,
        ),
    )
    return build_certified_metric_partition(
        value,
        metric_id="research_activity_score",
        decisions=(*decisions, *coverage_decisions),
        coverage=(coverage,),
        window=window,
        population=population,
    )


def test_parser_to_source_year_to_calculator_admission_is_reconstructable() -> None:
    certified = _admitted()
    result = calculate_activity_raw(certified)
    assert result.raw_value == 30.0
    assert result.components["distinct_researchers"] == 5
    automatic = tuple(
        item
        for item in certified.certification.evidence_decisions
        if isinstance(item, AutomaticPaperIdentityDecision)
    )
    assert len(automatic) == 60
    assert all(
        item.state == "certified" and item.reviewed_by is item.reviewed_at is None
        for item in automatic
    )
    assert all(evidence_decision_is_current(item) for item in automatic)


def test_declared_exact_date_and_fixed_native_identity_do_not_use_fallbacks() -> None:
    facts = _facts()
    assert facts.exact_date == date(2023, 1, 1)
    assert facts.researcher_ids == tuple(
        f"inspire-author:{item}" for item in range(1, 6)
    )
    no_date = _facts(preprint_date=None)
    assert no_date.exact_date is None  # earliest_date must never substitute.
    assert (
        automatic_paper_identity_decision(
            no_date, evidence_kind="publication-metric-date"
        ).state
        == "insufficient_evidence"
    )
    orcid_only = _facts(authors=[{"ORCID": "0000-0002-1825-0097"}])
    assert orcid_only.researcher_ids == ()
    assert (
        automatic_paper_identity_decision(
            orcid_only, evidence_kind="researcher-identity"
        ).state
        == "insufficient_evidence"
    )


def test_capture_reuses_provider_record_checksum_for_unicode_names() -> None:
    facts = _facts(authors=[{"recid": "1", "full_name": "张伟"}])
    assert facts.researcher_ids == ("inspire-author:1",)
    assert (
        automatic_paper_identity_decision(
            facts, evidence_kind="researcher-identity"
        ).state
        == "certified"
    )


@pytest.mark.parametrize(
    "authors",
    [
        [],
        [{"full_name": "No persistent identity"}],
        [{"recid": "1"}, {"recid": "1"}],
        [{"recid": "1", "record": {"$ref": "https://inspirehep.net/api/authors/2"}}],
        [
            {"recid": "1", "ORCID": "0000-0002-1825-0097"},
            {"recid": "2", "ORCID": "0000-0002-1825-0097"},
        ],
    ],
)
def test_missing_and_conflicting_paper_native_identifiers_fail_closed(
    authors: list[dict[str, Any]],
) -> None:
    decision = automatic_paper_identity_decision(
        _facts(authors=authors), evidence_kind="researcher-identity"
    )
    assert decision.state != "certified"


def test_source_record_and_consumed_proof_mutations_are_rejected() -> None:
    facts = _facts()
    with pytest.raises(CertificationError, match="checksum"):
        capture_automatic_paper_facts(
            SourceRecord("inspire", facts.reference.source_record_id, {}),
            context=facts.context,
            reference=facts.reference,
            declared_date_basis="inspire-preprint-date",
        )
    with pytest.raises(CertificationError, match="inventory"):
        replace(facts, authors=facts.authors[:-1])
    decision = automatic_paper_identity_decision(
        facts, evidence_kind="researcher-identity"
    )
    with pytest.raises(CertificationError, match="reconstruct"):
        replace(decision, certified_value_digest="f" * 64)
    bare = EvidenceCertificationDecision(
        **{
            item.name: getattr(decision, item.name)
            for item in fields(EvidenceCertificationDecision)
        }
    )
    assert not evidence_decision_is_current(bare)


def test_source_year_rejects_equal_date_from_unrelated_source_occurrence() -> None:
    source, facts = _source_year(2023)
    altered = replace(
        facts[0],
        reference=replace(facts[0].reference, checksum="f" * 64),
        date_facts=tuple(
            replace(item, reference=replace(item.reference, checksum="f" * 64))
            for item in facts[0].date_facts
        ),
        authors=(),
        author_count=None,
    )
    wrong = automatic_paper_identity_decision(
        altered, evidence_kind="publication-metric-date"
    )
    changed = replace(
        source.evidence,
        structural_decisions=tuple(
            wrong
            if item.subject_id == wrong.subject_id
            and item.evidence_kind == wrong.evidence_kind
            else item
            for item in source.evidence.structural_decisions
        ),
    )
    assert certify_source_year(changed, source.coverage).state == "conflicted"


def test_calculator_rejects_changed_researcher_consumed_values() -> None:
    certified = _admitted()
    changed = replace(
        certified.partition,
        papers=(
            replace(
                certified.partition.papers[0], researcher_ids=("invented-name-id",)
            ),
            *certified.partition.papers[1:],
        ),
    )
    with pytest.raises(CertificationError):
        replace(certified, partition=changed)


@pytest.mark.parametrize("value", ["2023", "2023-01", "not-a-date"])
def test_partial_dates_cannot_supply_a_fabricated_exact_metric_date(value: str) -> None:
    facts = _facts(preprint_date=value)
    assert facts.exact_date is None
    assert (
        automatic_paper_identity_decision(
            facts, evidence_kind="publication-metric-date"
        ).state
        != "certified"
    )


def test_automatic_metric_date_cannot_borrow_an_unlabelled_legacy_year() -> None:
    source, facts = _source_year(2023)
    decision = automatic_paper_identity_decision(
        facts[0], evidence_kind="publication-metric-date"
    )
    verify_automatic_date_axis((decision,), (source,))
    legacy_dates = tuple(
        EvidenceCertificationDecision(
            **{
                item.name: (
                    evidence_rule_version(original.evidence_kind)
                    if item.name == "rule_version"
                    else getattr(original, item.name)
                )
                for item in fields(EvidenceCertificationDecision)
            }
        )
        if original.evidence_kind == "publication-metric-date"
        else original
        for original in source.evidence.structural_decisions
    )
    legacy = certify_source_year(
        replace(source.evidence, structural_decisions=legacy_dates), source.coverage
    )
    assert legacy.state == "certified"
    with pytest.raises(CertificationError, match="explicitly based"):
        verify_automatic_date_axis((decision,), (legacy,))


def test_actual_page_and_record_checksums_remain_distinct_through_source_year() -> None:
    facts, page = _captured()
    assert facts.reference.checksum != page.page_checksum
    assert page.record_checksums == (
        (facts.reference.source_record_id, facts.reference.checksum),
    )
    source, _ = _source_year(2023)
    bound = source.evidence.partitions[0]
    assert isinstance(bound, RecordPageSourcePartitionEvidence)
    assert bound.reconciles
    assert facts.reference.checksum not in bound.page_checksums
    assert page.page_checksum in bound.page_checksums
    assert source.state == "certified"


def test_record_page_bridge_rejects_changed_or_omitted_membership() -> None:
    _, receipt = _captured()
    with pytest.raises(CertificationError):
        replace(receipt, record_checksums=())
    source, _ = _source_year(2023)
    bound = source.evidence.partitions[0]
    assert isinstance(bound, RecordPageSourcePartitionEvidence)
    with pytest.raises(CertificationError):
        replace(bound, pages=bound.pages[:-1])
    with pytest.raises(CertificationError):
        replace(
            bound,
            page_checksums=tuple(
                checksum
                for page in bound.pages
                for _, checksum in page.record_checksums
            ),
        )


@pytest.mark.parametrize("payload", [b"{", b"[]", b'{"hits":{"hits":[{}]}}'])
def test_record_page_bridge_fails_closed_on_malformed_provider_bytes(
    payload: bytes,
) -> None:
    with pytest.raises(CertificationError):
        capture_inspire_source_page(
            payload,
            connector=InspireConnector(Mock(), "https://inspirehep.net/api"),
            partition_id="test-only",
        )
