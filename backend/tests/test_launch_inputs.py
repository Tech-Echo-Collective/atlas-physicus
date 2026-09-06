"""Synthetic bounded record projection; no provider access or scientific replay."""

from dataclasses import asdict, replace
from datetime import date
from typing import Any
from unittest.mock import Mock

import pytest

from physics_atlas_api.certification import CertificationError, EvidenceReference
from physics_atlas_api.certification.automation import automatic_paper_identity_decision
from physics_atlas_api.certification.contracts import canonical_digest
from physics_atlas_api.certification.fields import (
    automatic_field_ledger,
    certify_field_ledger,
)
from physics_atlas_api.certification.launch_inputs import (
    MAXIMUM_LAUNCH_INPUT_OCCURRENCES,
    LaunchSourceOccurrence,
    canonicalize_launch_inputs,
    capture_launch_occurrence,
)
from physics_atlas_api.certification.launch_scope import BOUNDED_LAUNCH_SCOPE
from physics_atlas_api.connectors.base import SourceRecord
from physics_atlas_api.connectors.inspire import InspireConnector


def launch_occurrence(
    record_id: str = "1001", **changes: Any
) -> LaunchSourceOccurrence:
    raw = {
        "control_number": int(record_id),
        "titles": [{"title": "Synthetic source projection fixture"}],
        "preprint_date": "2020-02-01",
        "earliest_date": "1999-01-01",
        "document_type": ["article"],
        "inspire_categories": [
            {"term": "Theory-Nucl"},
            {"term": "Experiment-Nucl"},
        ],
        "authors": [
            {
                "full_name": "Explicit synthetic author",
                "record": {"$ref": "https://inspirehep.net/api/authors/10"},
                "affiliations": [
                    {
                        "value": "Synthetic Institute",
                        "record": {
                            "$ref": "https://inspirehep.net/api/institutions/20"
                        },
                    }
                ],
                "raw_affiliations": [{"value": "Synthetic Institute, Synthetic City"}],
                "affiliations_identifiers": [{"schema": "ROR", "value": "03yrm5c26"}],
            }
        ],
        "abstracts": [{"value": "DO-NOT-RETAIN-THIS-PROVIDER-ABSTRACT"}],
        "references": [{"record": {"$ref": "DO-NOT-RETAIN-PROVIDER-REFERENCES"}}],
        **changes,
    }
    record = SourceRecord("inspire", record_id, raw)
    reference = EvidenceReference(
        "inspire", record_id, record.checksum, f"{BOUNDED_LAUNCH_SCOPE}:inspire:2020"
    )
    transport = Mock()
    result = capture_launch_occurrence(
        record,
        reference=reference,
        connector=InspireConnector(transport, "https://inspirehep.net/api"),
        dataset_version="test-only-nuclear-inputs-v1",
    )
    transport.get_json.assert_not_called()
    transport.get_text.assert_not_called()
    return result


def test_source_bound_packet_discards_whole_payload_but_keeps_scientific_inputs() -> (
    None
):
    item = launch_occurrence()
    assert not hasattr(item, "raw")
    serialized = str(asdict(item))
    assert "DO-NOT-RETAIN-THIS-PROVIDER-ABSTRACT" not in serialized
    assert "DO-NOT-RETAIN-PROVIDER-REFERENCES" not in serialized
    assert item.source_facts.exact_date == date(2020, 2, 1)
    assert item.source_facts.researcher_ids == ("inspire-author:10",)
    assert item.identity.year == 2020
    assert item.authors[0].structured[0].provider_reference == (
        "https://inspirehep.net/api/institutions/20"
    )
    assert item.authors[0].raw[0].text == "Synthetic Institute, Synthetic City"
    assert item.authors[0].author_affiliation_identifiers == (("ROR", "03yrm5c26"),)
    ledger = automatic_field_ledger(item.field_evidence)
    assert certify_field_ledger(ledger).state == "certified"
    assert {row.field_id: row.weight for row in ledger.assignments} == {
        "nucl-th": 0.5,
        "nucl-ex": 0.5,
    }
    assert ledger.conservation_total == 1.0


def test_canonicalization_deduplicates_sources_and_rebinds_fact_context() -> None:
    item = launch_occurrence()
    result = canonicalize_launch_inputs((item, item))
    assert result.occurrence_count == 1 and result.duplicate_occurrences == 1
    assert len(result.papers) == 1
    paper = result.papers[0]
    assert paper.component.status == "matched"
    assert paper.component.canonical_id is not None
    captured = paper.occurrences[0]
    assert captured.reference == item.reference
    assert captured.source_facts.context.paper_id == paper.paper_id
    assert captured.source_facts.authors[0].context.paper_id == paper.paper_id
    assert (
        automatic_paper_identity_decision(
            captured.source_facts, evidence_kind="researcher-identity"
        ).state
        == "certified"
    )
    assert (
        certify_field_ledger(automatic_field_ledger(paper.field_evidence)).state
        == "certified"
    )


def test_exact_identifier_conflict_is_not_resolved_by_names() -> None:
    shared = {"dois": [{"value": "10.1234/synthetic-shared"}]}
    result = canonicalize_launch_inputs(
        (
            launch_occurrence("1001", **shared),
            launch_occurrence("1002", **shared),
        )
    )
    assert len(result.papers) == 1
    assert result.papers[0].component.status == "needs_review"
    assert result.papers[0].component.canonical_id is None
    assert result.papers[0].component.conflict_schemes == ("inspire",)


def test_same_title_author_and_date_without_shared_identifier_never_merge() -> None:
    result = canonicalize_launch_inputs(
        (launch_occurrence("1001"), launch_occurrence("1002"))
    )
    assert len(result.papers) == 2
    assert all(item.component.status == "matched" for item in result.papers)
    assert not any(item.component.merge_evidence for item in result.papers)


def test_partial_date_is_retained_as_missing_exact_date_not_earliest_fallback() -> None:
    item = launch_occurrence(preprint_date="2020")
    assert item.source_facts.exact_date is None
    assert item.identity.year is None
    assert item.source_facts.date_facts[0].value == "2020"
    assert (
        automatic_paper_identity_decision(
            item.source_facts, evidence_kind="publication-metric-date"
        ).state
        != "certified"
    )


def test_unknown_field_mass_remains_explicit() -> None:
    item = launch_occurrence(
        inspire_categories=[{"term": "Theory-Nucl"}, {"term": "unknown-field"}]
    )
    ledger = automatic_field_ledger(item.field_evidence)
    assert ledger.unmapped_mass > 0
    assert ledger.conservation_total == 1
    assert certify_field_ledger(ledger).state != "certified"


def test_invalid_identifier_is_not_silently_dropped_from_evidence() -> None:
    item = launch_occurrence(dois=[{"value": "not-a-valid-doi"}])
    assert ("doi", "not-a-valid-doi") in item.invalid_identifiers
    assert len(item.identity.identifiers) == 1


@pytest.mark.parametrize("related_first", [False, True])
def test_primary_and_explicit_erratum_dois_are_distinct_document_roles(
    related_first: bool,
) -> None:
    # The DOI/material shape mirrors INSPIRE 1705646; every other fact is synthetic.
    primary = {"value": "10.1103/PhysRevLett.122.122001", "material": "publication"}
    related = {
        "value": "10.1103/PhysRevLett.124.199901",
        "material": "erratum",
        "source": "APS",
    }
    values = [related, primary] if related_first else [primary, related]
    item = launch_occurrence(dois=values)
    result = canonicalize_launch_inputs((item,))
    assert result.papers[0].component.status == "matched"
    assert {doi.value for doi in item.identity.identifiers if doi.scheme == "doi"} == {
        "10.1103/physrevlett.122.122001"
    }
    assert len(item.doi_assertions) == 2
    for position, (assertion, raw) in enumerate(
        zip(item.doi_assertions, values, strict=True), start=1
    ):
        assert assertion.position == position
        assert assertion.value == raw["value"]
        assert assertion.material == raw["material"]
        assert assertion.source_reference == canonical_digest(item.reference)
    retained = next(row for row in item.doi_assertions if row.is_related_document)
    assert retained.identifier is not None
    assert retained.identifier.value == "10.1103/physrevlett.124.199901"
    assert retained.source == "APS"


def test_explicit_addendum_is_retained_without_creating_primary_identity() -> None:
    item = launch_occurrence(
        dois=[
            {"value": "10.1234/main", "material": "publication"},
            {"value": "10.1234/extension", "material": "addendum"},
        ]
    )
    assert canonicalize_launch_inputs((item,)).papers[0].component.status == "matched"
    assert item.doi_assertions[1].is_related_document
    assert item.doi_assertions[1].identifier is not None


@pytest.mark.parametrize("material", [None, "publication", "reprint", "preprint"])
def test_distinct_primary_or_unresolved_equivalence_dois_still_conflict(
    material: str | None,
) -> None:
    second = {"value": "10.1234/distinct"}
    if material is not None:
        second["material"] = material
    item = launch_occurrence(dois=[{"value": "10.1234/main"}, second])
    component = canonicalize_launch_inputs((item,)).papers[0].component
    assert component.status == "needs_review"
    assert component.conflict_schemes == ("doi",)
    assert component.canonical_id is None


def test_case_variant_duplicates_preserve_assertions_without_false_conflict() -> None:
    item = launch_occurrence(
        dois=[
            {"value": "10.1234/MAIN", "material": "publication"},
            {"value": "10.1234/main"},
            {"value": "10.1234/ERRATUM", "material": "erratum"},
            {"value": "10.1234/erratum", "material": "erratum"},
        ]
    )
    assert len(item.doi_assertions) == 4
    assert canonicalize_launch_inputs((item,)).papers[0].component.status == "matched"
    assert len([row for row in item.identity.identifiers if row.scheme == "doi"]) == 1


def test_same_doi_with_primary_and_related_roles_fails_closed() -> None:
    with pytest.raises(CertificationError, match="conflicting primary and related"):
        launch_occurrence(
            dois=[
                {"value": "10.1234/MAIN", "material": "publication"},
                {"value": "10.1234/main", "material": "erratum"},
            ]
        )


@pytest.mark.parametrize("material", ["corrigendum", "unknown-role", "", None, 42])
def test_unknown_or_malformed_explicit_doi_material_fails_closed(
    material: object,
) -> None:
    with pytest.raises(CertificationError, match="material"):
        launch_occurrence(dois=[{"value": "10.1234/main", "material": material}])


def test_role_aware_doi_provenance_and_identity_cannot_be_stripped() -> None:
    item = launch_occurrence(dois=[{"value": "10.1234/main"}])
    with pytest.raises(CertificationError, match="source checksum"):
        replace(
            item,
            doi_assertions=(
                replace(item.doi_assertions[0], source_reference="f" * 64),
            ),
        )
    with pytest.raises(CertificationError, match="primary DOI identity"):
        replace(item, doi_assertions=())


def test_changed_reference_rejected_before_packet_can_be_consumed() -> None:
    item = launch_occurrence()
    with pytest.raises(CertificationError):
        replace(item, reference=replace(item.reference, checksum="f" * 64))


def test_multiple_source_revisions_are_not_silently_selected() -> None:
    first = launch_occurrence()
    second = launch_occurrence(preprint_date="2020-03-01")
    with pytest.raises(CertificationError, match="multiple selected occurrences"):
        canonicalize_launch_inputs((first, second))


def test_missing_author_inventory_never_becomes_zero_researchers() -> None:
    item = launch_occurrence(authors=None)
    assert item.source_facts.author_count is None
    assert item.authors == ()
    assert (
        automatic_paper_identity_decision(
            item.source_facts, evidence_kind="researcher-identity"
        ).state
        != "certified"
    )


def test_unbounded_input_is_rejected_before_canonicalization() -> None:
    item = launch_occurrence()
    with pytest.raises(CertificationError, match="1–20,000"):
        canonicalize_launch_inputs((item,) * (MAXIMUM_LAUNCH_INPUT_OCCURRENCES + 1))


@pytest.mark.parametrize(
    "authors",
    ["not-an-array", ["not-an-author"], [{"recid": "1", "affiliations": "bad"}]],
)
def test_malformed_author_affiliation_inventory_fails_closed(authors: object) -> None:
    with pytest.raises((CertificationError, ValueError)):
        launch_occurrence(authors=authors)
