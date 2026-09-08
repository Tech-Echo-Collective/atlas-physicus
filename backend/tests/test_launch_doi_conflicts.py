"""Malformed scientific roles remain evidence blockers, not fatal query errors."""

import json
from datetime import timedelta
from unittest.mock import Mock

from test_launch_capture import NOW, PLAN, page_payload
from test_launch_inputs import launch_occurrence

from physics_atlas_api.certification.build_cache import bounded_build_verification_cache
from physics_atlas_api.certification.launch_attribution import attribute_launch_record
from physics_atlas_api.certification.launch_capture import (
    FetchedLaunchPage,
    collect_launch_year,
)
from physics_atlas_api.certification.launch_inputs import (
    canonicalize_launch_inputs,
    capture_launch_occurrence,
)
from physics_atlas_api.certification.launch_years import build_launch_source_year
from physics_atlas_api.certification.years import (
    ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
)
from physics_atlas_api.connectors.inspire import InspireConnector
from physics_atlas_api.historical_replay import build_canonical_paper_merge_plan

ROLES = [
    {"value": "10.1234/MAIN", "material": "publication"},
    {"value": "10.1234/main", "material": "erratum"},
]


def test_entire_ambiguous_component_withheld_and_ordinary_identity_unchanged() -> None:
    bad = launch_occurrence("101", dois=ROLES)
    linked = launch_occurrence("102", dois=[{"value": "10.1234/main"}])
    unrelated = launch_occurrence("103", dois=[{"value": "10.1234/other"}])
    baseline = canonicalize_launch_inputs((unrelated,))
    result = canonicalize_launch_inputs((bad, linked, unrelated))
    assert result.occurrence_count == 3 and len(result.papers) == 2
    ordinary = next(
        paper for paper in result.papers if paper.component.status == "matched"
    )
    assert ordinary == baseline.papers[0]
    withheld = next(
        paper for paper in result.papers if paper.component.status == "needs_review"
    )
    assert (
        withheld.component.canonical_id is withheld.component.primary_identifier is None
    )
    assert {item.reference.source_record_id for item in withheld.occurrences} == {
        "101",
        "102",
    }
    assert (
        len(withheld.occurrences[0].doi_assertions)
        + len(withheld.occurrences[1].doi_assertions)
        == 3
    )
    assert (
        canonicalize_launch_inputs(tuple(reversed((bad, linked, unrelated)))) == result
    )
    assert canonicalize_launch_inputs(withheld.occurrences).papers == (withheld,)
    legacy = build_canonical_paper_merge_plan(
        (unrelated.identity,), enable_secondary_merge=False
    )
    assert (
        baseline.merge_digest == legacy.digest
        and baseline.papers[0].component == legacy.components[0]
    )


def test_bounded_query_retains_all_records_and_uncertain_attribution_mass() -> None:
    with bounded_build_verification_cache():
        decoded = json.loads(page_payload([1, 2, 3], 3))
        decoded["hits"]["hits"][0]["metadata"]["dois"] = ROLES
        decoded["hits"]["hits"][1]["metadata"]["dois"] = [{"value": "10.1234/main"}]
        payload = json.dumps(decoded).encode()
        connector = InspireConnector(Mock(), "https://inspirehep.net/api")
        attributions = []

        def process(record, reference):  # type: ignore[no-untyped-def]
            occurrence = capture_launch_occurrence(
                record,
                reference=reference,
                connector=connector,
                dataset_version=PLAN.dataset_version,
            )
            attributions.append(
                attribute_launch_record(
                    record,
                    reference=reference,
                    source_facts=occurrence.source_facts,
                    institution_lookup=lambda _: None,
                    ror_lookup=lambda _: None,
                )
            )

        captured = collect_launch_year(
            PLAN,
            connector=connector,
            fetch=lambda uri: FetchedLaunchPage(uri, NOW, NOW, payload),
            process_record=process,
        )
        assert captured.partition.reconciles and len(captured.occurrences) == 3
        assert (
            captured.partition.observed_unique_records
            == captured.partition.expected_unique_records
            == 3
        )
        canonical = canonicalize_launch_inputs(captured.occurrences)
        built = build_launch_source_year(
            captured,
            canonical,
            tuple(attributions),
            entity_type="institution",
            evidence_cutoff=NOW + timedelta(seconds=1),
            identity_completeness_policy=ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
        )
        assert built.source_year is not None
        assert built.measured_counts["provider_occurrences"] == 3
        assert built.measured_counts["canonical_identity_matched_papers"] == 1
        unresolved = next(
            item
            for item in built.source_year.evidence.structural_decisions
            if item.evidence_kind == "canonical-paper-identity"
            and item.state == "needs_review"
        )
        projection = next(
            item
            for item in built.source_year.evidence.paper_projections
            if item.paper_id == unresolved.subject_id
        )
        assert len(projection.occurrence_references) == 2
        assert projection.entity_shares == ()
        assert dict(projection.unresolved_entity_mass) == {
            "researcher": 1,
            "institution": 1,
            "country": 1,
        }
        assert projection.field_weight_total == 1
        assert unresolved.reasons
