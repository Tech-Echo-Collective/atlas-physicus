"""Quarantine ambiguous source slots without changing the scientific denominator."""

from dataclasses import replace

import pytest
from test_automatic_identity_date_admission import _facts
from test_launch_attribution import _ROR_A, _author, _link
from test_launch_metric_coverage import _build, _proofs
from test_metric_system_v1 import calculate_activity_raw, paper, partition

from physics_atlas_api.certification import CertificationError, canonical_digest
from physics_atlas_api.certification.automation import (
    UNAMBIGUOUS_RESEARCHER_RULE_VERSION,
    automatic_known_researcher_decision,
    automatic_paper_identity_decision,
    automatic_unambiguous_researcher_decision,
    unambiguous_researcher_subset,
)
from physics_atlas_api.certification.build_cache import bounded_build_verification_cache
from physics_atlas_api.certification.launch_calculations import (
    LaunchPaperBinding,
    UnambiguousLaunchPaperBinding,
    _paper,
)
from physics_atlas_api.certification.rules import evidence_decision_is_current


@pytest.mark.parametrize(
    "ambiguous",
    [
        [
            {"recid": "1", "orcid": "0000-0003-2250-4181"},
            {"recid": "1", "orcid": "0000-0002-5211-7177"},
        ],
        [
            {"recid": "1", "orcid": "0000-0002-1825-0097"},
            {"recid": "2", "orcid": "0000-0002-1825-0097"},
        ],
        [
            {"recid": "1", "record": {"$ref": "https://inspirehep.net/api/authors/2"}},
            {"recid": "2"},
        ],
    ],
)
def test_exact_ambiguities_remain_unknown_while_unaffected_ids_survive(ambiguous):
    facts = _facts(authors=[*ambiguous, *({"recid": str(i)} for i in range(3, 8))])
    original_digest = canonical_digest(facts)
    legacy = automatic_known_researcher_decision(facts, entity_type="institution")
    strict = automatic_paper_identity_decision(
        facts, evidence_kind="researcher-identity"
    )
    assert legacy.state == strict.state == "conflicted"
    with bounded_build_verification_cache():
        result = automatic_unambiguous_researcher_decision(
            facts, entity_type="institution"
        )
        subset = result.subset
        assert result.state == "certified"
        assert result.rule_version == UNAMBIGUOUS_RESEARCHER_RULE_VERSION
        assert subset.researcher_ids == tuple(
            f"inspire-author:{i}" for i in range(3, 8)
        )
        assert subset.admitted_author_positions == (3, 4, 5, 6, 7)
        assert (
            subset.omitted_author_positions
            == subset.conflicted_author_positions
            == (1, 2)
        )
        assert subset.omission_reasons
        assert len(facts.authors) == facts.author_count == 7
        assert canonical_digest(facts) == original_digest
        assert (
            automatic_known_researcher_decision(facts, entity_type="institution")
            == legacy
        )
        assert (
            automatic_paper_identity_decision(
                facts, evidence_kind="researcher-identity"
            )
            == strict
        )
        assert evidence_decision_is_current(result)
        with pytest.raises(CertificationError, match="does not reconstruct"):
            replace(result, certified_value_digest=legacy.certified_value_digest)


def test_all_ambiguous_positions_produce_empty_known_set_not_zero_authors_or_score():
    facts = _facts(authors=[{"recid": "1"}, {"recid": "1"}])
    result = automatic_unambiguous_researcher_decision(facts, entity_type="country")
    assert result.state == "certified" and result.subset.researcher_ids == ()
    assert (
        result.omitted_author_positions == result.conflicted_author_positions == (1, 2)
    )
    assert facts.author_count == 2
    raw = partition(
        "country-test",
        tuple(replace(paper(i, 2025), researcher_ids=()) for i in range(15)),
    )
    calculated = calculate_activity_raw(raw)
    assert calculated.raw_value is None and calculated.normalized_value is None
    assert any("researcher" in reason for reason in calculated.missing_reasons)


def test_repeated_orcid_on_an_unidentified_position_cannot_verify_known_identity():
    facts = _facts(
        authors=[
            {"recid": "1", "orcid": "0000-0002-1825-0097"},
            {"orcid": "0000-0002-1825-0097"},
            {"recid": "3"},
        ]
    )
    subset = unambiguous_researcher_subset(facts)
    assert subset.researcher_ids == ("inspire-author:3",)
    assert subset.omitted_author_positions == (1, 2)


def test_binding_preserves_fractional_mass_provenance_and_legacy_projection():
    build = _build(
        [
            [
                _author(1, [_link("200")]),
                _author(1, [_link("200")]),
                _author(3, [_link("200")]),
            ]
        ]
    )
    proof = _proofs(build)[0]
    before = canonical_digest(proof)
    base = LaunchPaperBinding("institution", f"institution-ror-{_ROR_A}", "nucl-th")
    old = _paper(proof, base)
    new = _paper(
        proof,
        UnambiguousLaunchPaperBinding(base.entity_type, base.entity_id, base.field_id),
    )
    assert old.researcher_ids == (
        "inspire-author:1",
        "inspire-author:1",
        "inspire-author:3",
    )
    assert new.researcher_ids == ("inspire-author:3",)
    assert replace(new, researcher_ids=old.researcher_ids) == old
    assert new.attribution_weight == old.attribution_weight == 1
    assert proof.attribution_results[0].fractional.total_weight == 1
    assert canonical_digest(proof) == before
    with pytest.raises(CertificationError):
        UnambiguousLaunchPaperBinding("researcher", "inspire-author:3", "nucl-th")


def test_changed_nested_source_fact_cannot_reuse_old_subset_cache():
    facts = _facts(authors=[{"recid": "1"}, {"recid": "2"}])
    with bounded_build_verification_cache():
        original = automatic_unambiguous_researcher_decision(
            facts, entity_type="institution"
        )
        object.__setattr__(facts.authors[1].facts[0], "value", "1")
        assert unambiguous_researcher_subset(facts).researcher_ids == ()
        with pytest.raises(CertificationError, match="does not reconstruct"):
            original.__post_init__()


def test_conditional_bridge_retention_and_ui_consume_one_identical_subset():
    import json

    from test_launch_calculations import _window, _year

    from physics_atlas_api.certification.automation import (
        AutomaticUnambiguousResearcherDecision,
    )
    from physics_atlas_api.certification.launch_calculations import (
        build_launch_metric_partition,
        calculate_launch_metric_cohort,
    )
    from physics_atlas_api.certification.launch_entities import build_launch_entities
    from physics_atlas_api.certification.launch_retained import (
        build_launch_retained,
        rehydrate_launch_metric_input,
    )
    from physics_atlas_api.certification.launch_years import LaunchStructuralDecision
    from physics_atlas_api.certification.materialization import (
        build_certified_metric_partition,
    )
    from physics_atlas_api.certification.years import (
        EnumeratedLaunchSourceYearEvidence,
        certify_source_year,
        qualify_observed_release_source_year,
    )

    with bounded_build_verification_cache():
        years = tuple(
            _year(year, conflicting_researcher=True) for year in (2021, 2022, 2023)
        )
        with pytest.raises(
            CertificationError, match="non-certified researcher-identity"
        ):
            build_launch_metric_partition(
                _window(years, "research_activity_score"),
                entity_id=f"institution-ror-{_ROR_A}",
                field_id="nucl-th",
            )
        qualified = tuple(
            qualify_observed_release_source_year(
                certify_source_year(
                    EnumeratedLaunchSourceYearEvidence(**vars(year.evidence)),
                    year.coverage,
                )
            )
            for year in years
        )
        window = _window(qualified, "collaboration")
        partition_proof = build_launch_metric_partition(
            window, entity_id=f"institution-ror-{_ROR_A}", field_id="nucl-th"
        )
        expected = tuple(f"inspire-author:{i}" for i in range(2, 7))
        assert all(
            paper.researcher_ids == expected
            for paper in partition_proof.partition.papers
        )
        admissions = tuple(
            item
            for item in partition_proof.certification.evidence_decisions
            if isinstance(item, AutomaticUnambiguousResearcherDecision)
        )
        assert len(admissions) == 6
        assert all(
            item.subset.researcher_ids == expected
            and item.omitted_author_positions == (1, 6)
            for item in admissions
        )
        assert all(item.source_facts.author_count == 7 for item in admissions)
        mixed = tuple(
            automatic_known_researcher_decision(
                item.source_facts, entity_type=item.entity_type
            )
            if item is admissions[0]
            else item
            for item in partition_proof.certification.evidence_decisions
        )
        with pytest.raises(
            CertificationError, match="mixes observed researcher policies"
        ):
            build_certified_metric_partition(
                partition_proof.partition,
                metric_id="collaboration",
                decisions=mixed,
                coverage=partition_proof.certification.coverage,
                window=window,
                population=partition_proof.population_proof,
            )
        observations = calculate_launch_metric_cohort(window, field_id="nucl-th")
        document = json.loads(build_launch_retained(qualified, observations).content)
        for row in document["papers"].values():
            assert row["known_researcher_ids"].count("inspire-author:1") == 2
            assert row["unambiguous_researcher_subset"]["researcher_ids"] == list(
                expected
            )
            assert row["attribution"][0]["fractional"]["total_weight"] == [1, 1]
        for observation in observations:
            proof = observation.certification_proof.partition
            assert (
                rehydrate_launch_metric_input(
                    document, proof.certification.input_digest
                )
                == proof.partition
            )
        input_digest = next(iter(document["partitions"]))
        paper_id = document["partitions"][input_digest]["papers"][0]
        altered = json.loads(json.dumps(document))
        altered["papers"][paper_id]["unambiguous_researcher_subset"]["version"] = (
            "invalid-rule"
        )
        with pytest.raises(CertificationError, match="subset lineage"):
            rehydrate_launch_metric_input(altered, input_digest)
        altered = json.loads(json.dumps(document))
        altered["papers"][paper_id]["unambiguous_researcher_subset"][
            "researcher_ids"
        ].append("inspire-author:1")
        with pytest.raises(CertificationError, match="checksum mismatch"):
            rehydrate_launch_metric_input(altered, input_digest)
        source_proof = next(
            item
            for item in qualified[0].evidence.structural_decisions
            if isinstance(item, LaunchStructuralDecision)
            and item.evidence_kind == "provenance-completeness"
        )
        ui = build_launch_entities(
            (source_proof.source_paper,),
            source_proof.attribution_results,
            geographic_views=(),
            researcher_projection_version=UNAMBIGUOUS_RESEARCHER_RULE_VERSION,
        )
        assert {item.id for item in ui.entities.researchers} == set(expected)
        assert {item.author_position for item in ui.entities.authorships} == {
            2,
            3,
            4,
            5,
            7,
        }
        assert all(
            item.researcher_id != "inspire-author:1"
            for item in ui.entities.affiliations
        )
        assert len(ui.entities.papers) == 1 and len(ui.entities.institutions) == 2
        legacy_ui = build_launch_entities(
            (source_proof.source_paper,),
            source_proof.attribution_results,
            geographic_views=(),
        )
        assert not legacy_ui.entities.researchers
        assert legacy_ui.entities.papers == ui.entities.papers
        assert legacy_ui.entities.institutions == ui.entities.institutions


def test_public_partition_admission_rejects_subset_injection_into_legacy_window():
    from copy import copy

    from test_launch_calculations import _window, _year

    from physics_atlas_api.certification.automation import (
        AutomaticKnownResearcherDecision,
    )
    from physics_atlas_api.certification.launch_calculations import (
        build_launch_metric_partition,
    )
    from physics_atlas_api.certification.materialization import (
        build_certified_metric_partition,
    )

    with bounded_build_verification_cache():
        years = tuple(_year(year) for year in (2021, 2022, 2023))
        original = build_launch_metric_partition(
            _window(years, "research_activity_score"),
            entity_id=f"institution-ror-{_ROR_A}",
            field_id="nucl-th",
        )
        injected = tuple(
            automatic_unambiguous_researcher_decision(
                item.source_facts, entity_type=item.entity_type
            )
            if isinstance(item, AutomaticKnownResearcherDecision)
            else item
            for item in original.certification.evidence_decisions
        )
        with pytest.raises(CertificationError, match="conditional geographic window"):
            build_certified_metric_partition(
                original.partition,
                metric_id="research_activity_score",
                decisions=injected,
                coverage=original.certification.coverage,
                window=original.window_proof,
                population=original.population_proof,
            )
        altered = copy(original.certification)
        object.__setattr__(altered, "evidence_decisions", injected)
        with pytest.raises(CertificationError, match="conditional geographic window"):
            replace(original, certification=altered)
