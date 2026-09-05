import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock

import pytest

from physics_atlas_api.certification.automatic_citations import (
    build_automatic_citation_population,
    capture_single_response_citations,
    citation_population_query,
    derive_citation_observations,
    validate_automatic_citation_population,
)
from physics_atlas_api.certification.automation import (
    AutomaticDateEvidence,
    AutomaticEvidenceContext,
    ProviderDateFact,
)
from physics_atlas_api.certification.citations import (
    CitationCohortPopulationEvidence,
    certify_citation_cohort,
    certify_citation_observation,
)
from physics_atlas_api.certification.contracts import (
    CertificationError,
    EvidenceReference,
    canonical_digest,
)
from physics_atlas_api.connectors.inspire import InspireConnector

_CUTOFF = datetime(2026, 9, 5, 12, tzinfo=UTC)
_KEY = ("hep-th", 2020, "article")


def _payload(count: int = 50) -> dict[str, Any]:
    return {
        "hits": {
            "total": count,
            "hits": [
                {
                    "id": str(index + 1),
                    "metadata": {
                        "titles": [{"title": f"Explicit test fixture {index}"}],
                        "earliest_date": "2020-01-01",
                        "preprint_date": "2020-01-01",
                        "document_type": ["article"],
                        "inspire_categories": [{"term": "Theory-HEP"}],
                        "citation_count": index + 1,
                        "citation_count_without_self_citations": index,
                    },
                }
                for index in range(count)
            ],
        },
        "links": {},
    }


def _capture(payload: dict[str, Any], **changes: Any) -> Any:
    transport = Mock()
    connector = InspireConnector(transport, "https://inspirehep.net/api")
    receipt = capture_single_response_citations(
        json.dumps(payload).encode(),
        **{
            "connector": connector,
            "query": citation_population_query("hep-th-v1", 2020),
            "calendar_year": 2020,
            "observed_at": _CUTOFF,
            "source_snapshot_id": "test-only-single-response",
            "dataset_version": "test-only-dataset-v1",
            "declared_date_basis": "inspire-preprint-date",
            "canonical_paper_ids": {
                hit["id"]: f"paper-{hit['id']}" for hit in payload["hits"]["hits"]
            },
            **changes,
        },
    )
    transport.get_json.assert_not_called()
    return receipt


def _cohort(receipt: Any, *, minimum: int = 50) -> Any:
    return certify_citation_cohort(
        derive_citation_observations(receipt, _KEY),
        dataset_version=receipt.dataset_version,
        acquisition_scope=receipt.acquisition_scope,
        population_evidence=build_automatic_citation_population(receipt, _KEY),
        minimum_paper_count=minimum,
    )


def test_complete_response_certifies_without_a_fictitious_reviewer() -> None:
    payload = _payload()
    receipt = _capture(payload)
    assert (
        receipt.response_sha256
        == hashlib.sha256(json.dumps(payload).encode()).hexdigest()
    )
    cohort = _cohort(receipt)
    assert cohort.state == "certified"
    assert cohort.paper_count == cohort.minimum_paper_count == 50
    assert cohort.population_evidence.reviewed_by is None
    assert cohort.population_evidence.reviewed_at is None
    assert cohort.population_evidence.review_state == "automatic-evidence-derived"
    assert all(item.maturity_months == 24 for item in cohort.observations)
    first = next(item for item in cohort.observations if item.paper_id == "paper-1")
    assert first.non_self_citation_count == 0
    assert (
        first.evidence.source_reference.source_snapshot_id == receipt.source_snapshot_id
    )
    assert _cohort(receipt).certification_id == cohort.certification_id


def test_no_minimum_size_or_maturity_relaxation() -> None:
    assert _cohort(_capture(_payload(49))).state == "insufficient_evidence"
    with pytest.raises(CertificationError, match="exact v1 minimum"):
        _cohort(_capture(_payload()), minimum=2)
    immature = _capture(_payload(), observed_at=datetime(2021, 12, 31, tzinfo=UTC))
    assert _cohort(immature).state == "insufficient_evidence"


@pytest.mark.parametrize("failure", ["truncated", "next", "inexact", "over-budget"])
def test_incomplete_or_unbounded_response_is_rejected(failure: str) -> None:
    payload = _payload()
    if failure == "truncated":
        payload["hits"]["total"] += 1
    elif failure == "next":
        payload["links"]["next"] = "https://inspirehep.net/api/literature?page=2"
    elif failure == "inexact":
        payload["hits"]["total"] = {"value": 50, "relation": "gte"}
    else:
        payload["hits"]["total"] = 1_001
    with pytest.raises(CertificationError):
        _capture(payload)


def test_arbitrary_query_or_omitted_identity_cannot_define_population() -> None:
    payload = _payload()
    with pytest.raises(CertificationError, match="source/query/version"):
        _capture(payload, query="top cited institution papers")
    with pytest.raises(CertificationError, match="all source records"):
        _capture(payload, canonical_paper_ids={"1": "paper-1"})
    payload["hits"]["hits"].append(payload["hits"]["hits"][0])
    payload["hits"]["total"] += 1
    with pytest.raises(CertificationError, match="duplicated"):
        _capture(payload)


@pytest.mark.parametrize(
    "missing", ["preprint_date", "inspire_categories", "document_type"]
)
def test_unknown_membership_is_retained_and_never_silently_excluded(
    missing: str,
) -> None:
    payload = _payload()
    del payload["hits"]["hits"][0]["metadata"][missing]
    receipt = _capture(payload)
    assert len(receipt.records) == 50
    assert receipt.records[0].unresolved_membership
    with pytest.raises(CertificationError, match="unresolved source records"):
        build_automatic_citation_population(receipt, _KEY)


def test_missing_count_remains_missing_and_does_not_shrink_population() -> None:
    payload = _payload()
    del payload["hits"]["hits"][0]["metadata"]["citation_count_without_self_citations"]
    receipt = _capture(payload)
    cohort = _cohort(receipt)
    assert cohort.paper_count == 50
    assert cohort.state == "insufficient_evidence"
    assert any(item.non_self_citation_count is None for item in cohort.observations)


def test_all_returned_records_are_retained_even_outside_target_cohort() -> None:
    payload = _payload(51)
    payload["hits"]["hits"][-1]["metadata"]["preprint_date"] = "2019-12-31"
    receipt = _capture(payload)
    assert len(receipt.records) == 51
    cohort = _cohort(receipt)
    assert cohort.paper_count == 50
    # This proves only declared query completeness, never canonical-year coverage.
    assert cohort.state == "certified"


def test_mixed_earliest_date_is_not_promoted_to_a_declared_metric_date() -> None:
    payload = _payload()
    first = payload["hits"]["hits"][0]["metadata"]
    first["earliest_date"] = "2018-01-01"
    receipt = _capture(payload)
    assert receipt.records[0].publication_date.isoformat() == "2020-01-01"
    assert receipt.records[0].date_evidence.declared_basis == "inspire-preprint-date"
    del first["preprint_date"]
    missing = _capture(payload)
    assert missing.records[0].publication_date is None
    assert len(missing.records) == 50
    with pytest.raises(CertificationError, match="unresolved source records"):
        build_automatic_citation_population(missing, _KEY)


def test_date_projection_cannot_be_changed_without_its_source_evidence() -> None:
    receipt = _capture(_payload())
    with pytest.raises(CertificationError, match="declared source basis"):
        replace(
            receipt,
            records=(
                replace(receipt.records[0], publication_date=_CUTOFF.date()),
                *receipt.records[1:],
            ),
        )
    with pytest.raises(CertificationError, match="does not bind the record"):
        replace(receipt, declared_date_basis="journal-online-publication")


@pytest.mark.parametrize("value", ["2020", "2020-01", "invalid"])
def test_partial_or_invalid_declared_dates_remain_unresolved(value: str) -> None:
    payload = _payload()
    payload["hits"]["hits"][0]["metadata"]["preprint_date"] = value
    receipt = _capture(payload)
    assert receipt.records[0].publication_date is None
    assert receipt.records[0].date_evidence.facts[0].value == value
    with pytest.raises(CertificationError, match="unresolved source records"):
        build_automatic_citation_population(receipt, _KEY)


def test_journal_basis_requires_source_bound_supported_journal_facts() -> None:
    payload = _payload()
    missing = _capture(payload, declared_date_basis="journal-online-publication")
    assert all(row.publication_date is None for row in missing.records)
    with pytest.raises(CertificationError, match="unresolved source records"):
        build_automatic_citation_population(missing, _KEY)

    evidence = {}
    for hit in payload["hits"]["hits"]:
        doi = f"10.1234/test-{hit['id']}"
        hit["metadata"]["dois"] = [{"value": doi}]
        evidence[hit["id"]] = AutomaticDateEvidence(
            context=AutomaticEvidenceContext(
                paper_id=f"paper-{hit['id']}",
                dataset_version="test-only-dataset-v1",
                acquisition_scope="hep-th-v1",
            ),
            declared_basis="journal-online-publication",
            facts=(
                ProviderDateFact(
                    reference=EvidenceReference(
                        provider="crossref",
                        source_record_id=doi,
                        checksum=canonical_digest((doi, "2020-08-01")),
                        source_snapshot_id="test-only-crossref-source",
                    ),
                    basis="journal-online-publication",
                    source_field="published-online",
                    value="2020-08-01",
                ),
            ),
        )
    receipt = _capture(
        payload,
        declared_date_basis="journal-online-publication",
        canonical_date_evidence=evidence,
    )
    assert _cohort(receipt).state == "certified"
    assert receipt.records[0].publication_date.isoformat() == "2020-08-01"
    wrong_reference = replace(
        evidence["1"].facts[0].reference, source_record_id="10.1234/unrelated-paper"
    )
    unrelated = {
        **evidence,
        "1": replace(
            evidence["1"],
            facts=(replace(evidence["1"].facts[0], reference=wrong_reference),),
        ),
    }
    with pytest.raises(CertificationError, match="does not bind a source paper ID"):
        _capture(
            payload,
            declared_date_basis="journal-online-publication",
            canonical_date_evidence=unrelated,
        )
    bad = replace(evidence["1"].facts[0], value="2021-08-01")
    conflicting = {
        **evidence,
        "1": replace(evidence["1"], facts=(*evidence["1"].facts, bad)),
    }
    conflicted = _capture(
        payload,
        declared_date_basis="journal-online-publication",
        canonical_date_evidence=conflicting,
    )
    assert conflicted.records[0].publication_date is None
    with pytest.raises(CertificationError, match="unresolved source records"):
        build_automatic_citation_population(conflicted, _KEY)


def test_one_complete_multi_year_response_preserves_one_exact_cutoff() -> None:
    payload = _payload(150)
    for index, hit in enumerate(payload["hits"]["hits"]):
        hit["metadata"]["preprint_date"] = f"{2020 + index // 50}-01-01"
    receipt = _capture(
        payload,
        query=citation_population_query("hep-th-v1", 2020, 2022),
        end_calendar_year=2022,
    )
    cohorts = []
    for year in (2020, 2021, 2022):
        key = ("hep-th", year, "article")
        cohorts.append(
            certify_citation_cohort(
                derive_citation_observations(receipt, key),
                dataset_version=receipt.dataset_version,
                acquisition_scope=receipt.acquisition_scope,
                population_evidence=build_automatic_citation_population(receipt, key),
            )
        )
    assert all(item.state == "certified" and item.paper_count == 50 for item in cohorts)
    assert {item.cutoff for item in cohorts} == {_CUTOFF}
    assert all(item.population_evidence.receipt is receipt for item in cohorts)
    with pytest.raises(CertificationError, match="scope or year"):
        citation_population_query("hep-th-v1", 2020, 2026)


def test_validator_rederives_population_and_exact_observations() -> None:
    receipt = _capture(_payload())
    population = build_automatic_citation_population(receipt, _KEY)
    with pytest.raises(CertificationError, match="source derivation"):
        validate_automatic_citation_population(
            replace(population, eligible_paper_ids=population.eligible_paper_ids[:-1])
        )
    with pytest.raises(CertificationError, match="source derivation"):
        validate_automatic_citation_population(
            replace(population, reviewed_by="invented-reviewer", reviewed_at=_CUTOFF)
        )
    observations = derive_citation_observations(receipt, _KEY)
    changed = certify_citation_observation(
        replace(observations[0].evidence, non_self_citation_count=1)
    )
    with pytest.raises(CertificationError, match="complete response"):
        certify_citation_cohort(
            (changed, *observations[1:]),
            dataset_version=receipt.dataset_version,
            acquisition_scope=receipt.acquisition_scope,
            population_evidence=population,
        )
    changed_cutoff = certify_citation_observation(
        replace(
            observations[0].evidence,
            observed_at=_CUTOFF + timedelta(seconds=1),
            selected_cutoff=_CUTOFF + timedelta(seconds=1),
        )
    )
    with pytest.raises(CertificationError, match="complete response"):
        certify_citation_cohort(
            (changed_cutoff, *observations[1:]),
            dataset_version=receipt.dataset_version,
            acquisition_scope=receipt.acquisition_scope,
            population_evidence=population,
        )


def test_legacy_population_digest_is_unchanged() -> None:
    legacy = CitationCohortPopulationEvidence(
        cohort_key=_KEY,
        cutoff=_CUTOFF,
        dataset_version="historical-fixture-v1",
        acquisition_scope="hep-th-v1",
        eligible_paper_ids=("paper-2", "paper-1"),
        source_manifest_digest="0" * 64,
        review_state="reviewed-approved",
        reviewed_by="historical-fixture-reviewer",
        reviewed_at=_CUTOFF,
    )
    assert legacy.content_digest == canonical_digest(
        (_KEY, _CUTOFF, "historical-fixture-v1", "hep-th-v1", ("paper-1", "paper-2"))
    )
