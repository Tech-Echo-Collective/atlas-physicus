from dataclasses import replace

import pytest

from physics_atlas_api.scientific_validation import (
    AuthorshipEvidence,
    FieldAttributionEvidence,
    HistoricalCoverageEvidence,
    IdentityWarningEvidence,
    InstitutionEvidence,
    NormalizationEvidence,
    PaperEvidence,
    PaperTimeAffiliationEvidence,
    ProvenanceEvidence,
    ReferenceEcosystemEvidence,
    ResearcherEvidence,
    SanityAnchorObservation,
    validate_reference_ecosystem,
)

DATASET_VERSION = "reference-ecosystem-fixture-v1"
PROVENANCE = ProvenanceEvidence(DATASET_VERSION, ("snapshot:fixture",))


def healthy_evidence() -> ReferenceEcosystemEvidence:
    return ReferenceEcosystemEvidence(
        dataset_version=DATASET_VERSION,
        expected_ontology_version="physics-field-ontology-v1",
        expected_mapping_versions=(("arxiv", "arxiv-atlas-field-mapping-v1"),),
        expected_normalization_versions=(
            ("research_activity_score", "activity-robust-log-v1"),
        ),
        papers=(PaperEvidence("paper-1", 2024, ("researcher-1",), PROVENANCE),),
        researchers=(
            ResearcherEvidence("researcher-1", (("orcid", "0000-0001"),), PROVENANCE),
        ),
        authorships=(AuthorshipEvidence("paper-1", "researcher-1", PROVENANCE),),
        affiliations=(
            PaperTimeAffiliationEvidence(
                paper_id="paper-1",
                researcher_id="researcher-1",
                institution_id="institution-1",
                resolution_status="resolved",
                raw_affiliation_label="Example Institute, Theory Group",
                candidate_institution_ids=(),
                observed_year=2024,
                fractional_weight=1.0,
                provenance=PROVENANCE,
            ),
        ),
        institutions=(
            InstitutionEvidence(
                "institution-1",
                "Example Institute",
                (("ror", "https://ror.org/example"),),
                PROVENANCE,
            ),
        ),
        identity_warnings=(),
        field_attributions=(
            FieldAttributionEvidence(
                paper_id="paper-1",
                provider="arxiv",
                raw_categories=("hep-th",),
                field_id="hep-th",
                field_weight=1.0,
                mapping_status="mapped",
                mapping_version="arxiv-atlas-field-mapping-v1",
                ontology_version="physics-field-ontology-v1",
                provenance=PROVENANCE,
            ),
        ),
        historical_coverage=HistoricalCoverageEvidence(
            required_complete_years=(2022, 2023, 2024),
            observed_complete_years=(2022, 2023, 2024),
            excluded_partial_years=(2025,),
            provenance=PROVENANCE,
        ),
        normalizations=(
            NormalizationEvidence(
                metric_id="research_activity_score",
                entity_id="institution-1",
                scope_id="hep-th",
                observation_status="available",
                raw_value=1.0,
                normalized_value=50.0,
                reconstructed_normalized_value=50.0,
                normalization_version="activity-robust-log-v1",
                reconstruction_input_refs=("cohort:hep-th:2022-2024",),
                provenance=PROVENANCE,
            ),
            NormalizationEvidence(
                metric_id="research_activity_score",
                entity_id="institution-missing",
                scope_id="hep-th",
                observation_status="missing",
                raw_value=None,
                normalized_value=None,
                reconstructed_normalized_value=None,
                normalization_version="activity-robust-log-v1",
                reconstruction_input_refs=(),
                provenance=PROVENANCE,
            ),
        ),
    )


def issue_codes(evidence: ReferenceEcosystemEvidence) -> set[str]:
    return {item.code for item in validate_reference_ecosystem(evidence).issues}


def test_healthy_linked_reference_ecosystem_passes_without_ranking() -> None:
    report = validate_reference_ecosystem(healthy_evidence())

    assert report.status == "healthy"
    assert report.passes is True
    assert report.issues == ()
    assert report.summary.paper_author_link_coverage == 1.0
    assert report.summary.paper_time_affiliation_coverage == 1.0
    assert report.summary.field_attribution_coverage == 1.0
    assert report.summary.historical_year_coverage == 1.0
    assert report.summary.missing_normalization_count == 1
    assert not hasattr(report, "rank")
    assert not hasattr(report.summary, "score")


def test_broken_paper_author_and_affiliation_links_are_reported() -> None:
    evidence = healthy_evidence()
    broken = replace(
        evidence,
        researchers=(),
        authorships=(AuthorshipEvidence("unknown-paper", "ghost", PROVENANCE),),
        affiliations=(),
    )

    codes = issue_codes(broken)
    assert "paper-author.missing-researcher" in codes
    assert "paper-author.missing-link" in codes
    assert "paper-author.unknown-paper" in codes
    assert "paper-author.unknown-researcher" in codes
    assert "paper-time-affiliation.missing" in codes
    assert validate_reference_ecosystem(broken).status == "invalid"


@pytest.mark.parametrize("status", ["unresolved", "ambiguous"])
def test_unresolved_affiliation_remains_explicit_and_unweighted(status: str) -> None:
    evidence = healthy_evidence()
    unresolved = replace(
        evidence.affiliations[0],
        institution_id=None,
        resolution_status=status,
        candidate_institution_ids=("candidate-a", "candidate-b"),
        fractional_weight=None,
    )
    report = validate_reference_ecosystem(replace(evidence, affiliations=(unresolved,)))

    assert f"paper-time-affiliation.{status}" in {item.code for item in report.issues}
    assert report.status == "review-required"
    assert report.summary.paper_time_affiliation_coverage == 0.0


def test_merge_and_split_evidence_are_warnings_not_identity_decisions() -> None:
    evidence = healthy_evidence()
    second = ResearcherEvidence("researcher-2", (), PROVENANCE)
    warnings = (
        IdentityWarningEvidence(
            "merge-1",
            "possible-merge",
            ("researcher-1", "researcher-2"),
            ("identity-review:1",),
            "Persistent identifiers conflict with a similar name.",
        ),
        IdentityWarningEvidence(
            "split-1",
            "possible-split",
            ("researcher-1",),
            ("identity-review:2",),
            "Provider histories may represent two people.",
        ),
    )
    report = validate_reference_ecosystem(
        replace(
            evidence,
            researchers=(*evidence.researchers, second),
            identity_warnings=warnings,
        )
    )

    assert report.status == "review-required"
    assert {item.code for item in report.issues} == {
        "identity.possible-merge",
        "identity.possible-split",
    }


def test_field_versions_coverage_history_and_provenance_faults_are_reported() -> None:
    evidence = healthy_evidence()
    broken_field = replace(
        evidence.field_attributions[0],
        raw_categories=(),
        field_id=None,
        field_weight=None,
        mapping_status="unmapped",
        mapping_version="stale-mapping",
        ontology_version="stale-ontology",
        provenance=ProvenanceEvidence(None, ()),
    )
    broken_history = replace(
        evidence.historical_coverage,
        observed_complete_years=(2022,),
        excluded_partial_years=(2024,),
    )
    broken_normalization = replace(
        evidence.normalizations[0],
        normalized_value=42.0,
        reconstructed_normalized_value=41.0,
        normalization_version="stale-normalization",
        reconstruction_input_refs=(),
    )
    report = validate_reference_ecosystem(
        replace(
            evidence,
            field_attributions=(broken_field,),
            historical_coverage=broken_history,
            normalizations=(broken_normalization,),
        )
    )
    codes = {item.code for item in report.issues}

    assert report.status == "invalid"
    assert "field.mapping-version-mismatch" in codes
    assert "field.ontology-version-mismatch" in codes
    assert "field.missing-raw-category" in codes
    assert "field.unmapped" in codes
    assert "history.incomplete-required-years" in codes
    assert "history.partial-year-used-as-complete" in codes
    assert "normalization.version-mismatch" in codes
    assert "normalization.missing-reconstruction-inputs" in codes
    assert "normalization.reconstruction-mismatch" in codes
    assert "provenance.missing-source-reference" in codes
    assert "provenance.missing-dataset-version" in codes
    assert report.summary.field_attribution_coverage == 0.0
    assert report.summary.historical_year_coverage == pytest.approx(1 / 3)


def test_missing_is_not_coerced_to_zero() -> None:
    evidence = healthy_evidence()
    missing_as_zero = replace(
        evidence.normalizations[1], raw_value=0.0, normalized_value=0.0
    )
    report = validate_reference_ecosystem(
        replace(evidence, normalizations=(missing_as_zero,))
    )

    assert "normalization.missing-encoded-as-value" in {
        item.code for item in report.issues
    }

    empty = replace(
        evidence,
        papers=(),
        researchers=(),
        authorships=(),
        affiliations=(),
        institutions=(),
        field_attributions=(),
        normalizations=(),
        historical_coverage=replace(
            evidence.historical_coverage,
            required_complete_years=(),
            observed_complete_years=(),
        ),
    )
    summary = validate_reference_ecosystem(empty).summary
    assert summary.paper_author_link_coverage is None
    assert summary.paper_time_affiliation_coverage is None
    assert summary.field_attribution_coverage is None
    assert summary.historical_year_coverage is None


def test_optional_sanity_anchors_do_not_force_ordering_or_scores() -> None:
    evidence = healthy_evidence()
    anchors_a = (
        SanityAnchorObservation("princeton", "institution-1"),
        SanityAnchorObservation("ias", None),
    )
    anchors_b = tuple(reversed(anchors_a))
    report_a = validate_reference_ecosystem(replace(evidence, sanity_anchors=anchors_a))
    report_b = validate_reference_ecosystem(replace(evidence, sanity_anchors=anchors_b))

    assert report_a.status == report_b.status == "healthy"
    assert report_a.issues == report_b.issues == ()
    assert report_a.sanity_anchors == report_b.sanity_anchors
    assert tuple(item.anchor_id for item in report_a.sanity_anchors) == (
        "ias",
        "princeton",
    )
    assert all(not hasattr(item, "score") for item in report_a.sanity_anchors)
