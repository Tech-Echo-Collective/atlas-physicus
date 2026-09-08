"""Synthetic admission-contract fixtures; not scientific release evidence."""

from dataclasses import fields, replace
from datetime import timedelta

import pytest
from test_launch_years import NOW, captured_fixture

from physics_atlas_api.certification import CertificationError, certify_metric_window
from physics_atlas_api.certification.launch_metric_coverage import (
    certify_launch_source_coverage,
)
from physics_atlas_api.certification.launch_years import build_launch_source_year
from physics_atlas_api.certification.measurement_windows import (
    FrozenScientificCitationPopulation,
)
from physics_atlas_api.certification.years import (
    CONDITIONAL_OBSERVED_SOURCE_YEAR_RULE_VERSION,
    ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
    ConditionalObservedSourceYearEvidence,
    EnumeratedLaunchSourceYearEvidence,
    SourceYearEvidence,
    certify_source_year,
    qualify_observed_release_source_year,
    source_quality_certification,
)
from physics_atlas_api.metrics.scoped_activation import (
    certify_conditional_observed_dataset_scope,
    certify_dataset_scope,
)


def source_year(year: int = 2020):  # type: ignore[no-untyped-def]
    captured, canonical, attribution = captured_fixture(
        year=year,
        record_offset=(year - 2018) * 10,
        duplicate_arxiv=True,
        unknown_field=True,
    )
    built = build_launch_source_year(
        captured,
        canonical,
        attribution,
        entity_type="institution",
        evidence_cutoff=NOW + timedelta(seconds=2),
        identity_completeness_policy=ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
    )
    return certify_launch_source_coverage(built).source_year


def test_conditional_enumeration_never_promotes_original_source_quality() -> None:
    original = source_year()
    assert original.state == "insufficient_evidence"
    result = qualify_observed_release_source_year(original)
    assert result.state == "certified"
    assert result.rule_version == CONDITIONAL_OBSERVED_SOURCE_YEAR_RULE_VERSION
    assert isinstance(result.evidence, ConditionalObservedSourceYearEvidence)
    assert result.coverage == original.coverage
    assert source_quality_certification(result) == original.certification
    assert {item.evidence_kind: item.ratio for item in result.coverage} == {
        "paper-time-affiliation": 0,
        "canonical-institution": 0,
        "field-classification": 0.75,
        "collaboration-relationship": 0,
    }
    assert result.evidence.paper_projections == original.evidence.paper_projections
    assert (
        result.evidence.structural_decisions == original.evidence.structural_decisions
    )
    for item in result.evidence.structural_decisions:
        if (
            item.evidence_kind == "canonical-paper-identity"
            and item.state != "certified"
        ):
            assert item.state == "needs_review"
            projection = next(
                paper
                for paper in result.evidence.paper_projections
                if paper.paper_id == item.subject_id
            )
            assert projection.entity_shares == ()
            assert dict(projection.unresolved_entity_mass) == {
                "institution": 1,
                "researcher": 1,
                "country": 1,
            }
    assert all(
        paper.field_weight_total == 1 for paper in result.evidence.paper_projections
    )
    frozen = FrozenScientificCitationPopulation(
        (result,), NOW + timedelta(seconds=3), "inspire-preprint-date"
    )
    assert frozen.paper_projections == result.evidence.paper_projections
    assert len(frozen.unmeasurable_paper_ids) == 1
    assert len(frozen.measurement_population.provider_to_canonical) == 1


def test_conditional_release_cannot_hide_invalid_inventory_or_quality_hash() -> None:
    original = source_year()
    # A missing provider page is not simply missing entity evidence.
    incomplete = certify_source_year(
        replace(original.evidence, partitions=()), original.coverage
    )
    with pytest.raises(CertificationError, match="inventory remains invalid"):
        qualify_observed_release_source_year(incomplete)
    with pytest.raises((CertificationError, ValueError), match="minimum|policy"):
        replace(original.coverage[0], minimum=0.5)
    with pytest.raises(CertificationError, match="reconstruct"):
        replace(
            original, certification=replace(original.certification, state="certified")
        )
    with pytest.raises(CertificationError, match="policy"):
        replace(
            qualify_observed_release_source_year(original).evidence,
            release_policy_version="unversioned",
        )


def test_legacy_default_and_homogeneous_window_boundaries_remain_strict() -> None:
    original = source_year()
    legacy = certify_source_year(
        SourceYearEvidence(
            **{
                field.name: getattr(original.evidence, field.name)
                for field in fields(SourceYearEvidence)
            }
        ),
        original.coverage,
    )
    assert legacy.state == "insufficient_evidence"
    with pytest.raises(CertificationError, match="typed launch enumeration"):
        qualify_observed_release_source_year(legacy)
    originals = tuple(source_year(year) for year in (2020, 2021, 2022))
    conditional = tuple(
        qualify_observed_release_source_year(year) for year in originals
    )
    arguments = dict(
        metric_id="research_activity_score",
        entity_type="institution",
        terminal_year=2022,
        threshold_version="metric-validation-thresholds-v1",
    )
    assert (
        certify_metric_window(source_years=originals, **arguments).state
        == "insufficient_evidence"
    )
    assert (
        certify_metric_window(source_years=conditional, **arguments).state
        == "certified"
    )
    assert (
        certify_metric_window(
            source_years=(originals[0], *conditional[1:]), **arguments
        ).state
        == "conflicted"
    )
    with pytest.raises(CertificationError, match="certified before its freeze"):
        FrozenScientificCitationPopulation(
            (originals[0], *conditional[1:]),
            NOW + timedelta(seconds=3),
            "inspire-preprint-date",
        )


def test_enumeration_alone_never_establishes_a_release() -> None:
    years = tuple(
        qualify_observed_release_source_year(source_year(year))
        for year in range(2018, 2024)
    )
    with pytest.raises(CertificationError, match="mixes full-source and conditional"):
        certify_dataset_scope(years)
    with pytest.raises(CertificationError, match="actual Atlas observations"):
        certify_conditional_observed_dataset_scope(years, ())
    with pytest.raises(CertificationError, match="actual Atlas observations"):
        certify_conditional_observed_dataset_scope(years, (True,))  # type: ignore[arg-type]
    with pytest.raises(CertificationError, match="complete six-year"):
        certify_conditional_observed_dataset_scope(years[:-1], ())


def test_conditional_calculation_keeps_sample_thresholds_and_export_boundary() -> None:
    from test_launch_calculations import _window, _year

    from physics_atlas_api.certification.build_cache import (
        bounded_build_verification_cache,
    )
    from physics_atlas_api.certification.launch_calculations import (
        calculate_launch_metric_cohort,
    )
    from physics_atlas_api.metrics.dataset import _verify_observation

    with bounded_build_verification_cache():
        originals = tuple(_year(year) for year in range(2018, 2024))
        years = tuple(
            qualify_observed_release_source_year(
                certify_source_year(
                    EnumeratedLaunchSourceYearEvidence(
                        **{
                            field.name: getattr(year.evidence, field.name)
                            for field in fields(SourceYearEvidence)
                        }
                    ),
                    year.coverage,
                )
            )
            for year in originals
        )
        values = calculate_launch_metric_cohort(
            _window(years, "research_activity_score"), field_id="nucl-th"
        )
        assert len(values) == 2
        # No threshold override: two tiny fixture entities do not become a
        # 30-peer normalized cohort merely because enumeration is complete.
        assert all(item.value is None and item.uncertainty_reasons for item in values)
        for old, current in zip(originals, years, strict=True):
            assert old.coverage == current.coverage
            assert source_quality_certification(current).state == old.state
        with pytest.raises(CertificationError, match="conditional release authority"):
            _verify_observation(values[0], set())
        with pytest.raises(CertificationError, match="actual Atlas observations"):
            certify_conditional_observed_dataset_scope(years, values)
