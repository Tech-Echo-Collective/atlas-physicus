from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from certification_helpers import (
    certify_citation_reference_cohort,
    certify_normalization_populations,
    certify_partition,
)
from test_metric_system_v1 import complete_coverage, impact_fixture, paper, partition

from physics_atlas_api.attribution import FRACTIONAL_ATTRIBUTION_V1
from physics_atlas_api.certification import (
    CERTIFICATION_POLICY_VERSION,
    CITATION_CERTIFICATION_RULE_VERSION,
    COVERAGE_SUBJECT_TYPE,
    FIELD_CERTIFICATION_RULE_VERSION,
    CertificationError,
    CertifiedCategoryUniverse,
    CertifiedMetricPartition,
    CertifiedMetricWindow,
    CertifiedSourceYear,
    CitationCohortPopulationEvidence,
    CitationObservationCertification,
    CitationObservationEvidence,
    CoverageCertification,
    CoverageDecisionMass,
    CoveragePopulationEvidence,
    EvidenceCertificationDecision,
    EvidenceKind,
    EvidenceReference,
    FieldLedgerEvidence,
    FieldWeight,
    InstitutionAuthorityRecord,
    InstitutionResolutionEvidence,
    SourceAcquisitionPlanEvidence,
    SourcePartitionEvidence,
    SourceYearEvidence,
    SourceYearPaperProjection,
    build_certified_metric_partition,
    canonical_digest,
    certify_citation_cohort,
    certify_citation_observation,
    certify_coverage,
    certify_field_ledger,
    certify_institution,
    certify_metric_window,
    certify_source_year,
    institution_authority_version,
    source_record_inventory_digest,
    validate_coverage_certification,
    wrap_certified_citation_cohort,
    wrap_certified_metric_population,
)
from physics_atlas_api.fields import FIELD_WEIGHTING_POLICY_VERSION
from physics_atlas_api.metrics import (
    METRIC_VALIDATION_THRESHOLDS_V1,
    CitationReferenceCohort,
    apply_atlas_scale,
    bind_metric_calculation,
    calculate_activity_raw,
    calculate_impact_raw,
)

_CHECKSUM = "a" * 64
_CUTOFF = datetime(2026, 12, 31, tzinfo=UTC)


def _institution_evidence(
    raw_name: str | None,
    authority_records: tuple[InstitutionAuthorityRecord, ...],
    **changes: object,
) -> InstitutionResolutionEvidence:
    values: dict[str, object] = {
        "raw_name": raw_name,
        "source_evidence_ids": ("inspire:1",),
        "source_manifest_digest": _CHECKSUM,
        "authority_version": institution_authority_version(authority_records),
    }
    values.update(changes)
    return InstitutionResolutionEvidence(**values)  # type: ignore[arg-type]


def test_raw_partition_cannot_reach_a_metric_formula() -> None:
    raw = partition("institution-a", tuple(paper(index, 2025) for index in range(10)))
    with pytest.raises(CertificationError, match="certify evidence first"):
        calculate_activity_raw(raw)  # type: ignore[arg-type]

    certified = certify_partition(raw, "research_activity_score")
    result = calculate_activity_raw(certified)
    assert result.raw_value == 10
    assert len(result.certification_manifest_digest) == 64
    assert result.certification_manifest_digest == (
        certified.certification.certification_digest
    )


def test_certified_partition_digest_prevents_post_certification_changes() -> None:
    raw = partition("institution-a", tuple(paper(index, 2025) for index in range(10)))
    certified = certify_partition(raw, "research_activity_score")
    changed = replace(raw, entity_id="institution-b")
    with pytest.raises(CertificationError, match="digest does not match"):
        replace(certified, partition=changed)

    with pytest.raises(CertificationError, match="paper certifications are incomplete"):
        replace(
            certified,
            certification=replace(
                certified.certification,
                paper_certifications=(),
            ),
        )


def test_partition_proof_rejects_unvalidated_nested_payloads() -> None:
    raw = partition("institution-a", (paper(1, 2025),))
    certified = certify_partition(raw, "research_activity_score")
    proof = certified.certification
    with pytest.raises(CertificationError, match="exact certification result"):
        replace(certified, certification=SimpleNamespace(**vars(proof)))

    decision = proof.evidence_decisions[0]
    with pytest.raises(CertificationError, match="exact evidence decisions"):
        replace(
            proof,
            evidence_decisions=(
                SimpleNamespace(**vars(decision), decision_id=decision.decision_id),
                *proof.evidence_decisions[1:],
            ),
        )
    with pytest.raises(CertificationError, match="exact paper certifications"):
        replace(
            proof,
            paper_certifications=(
                SimpleNamespace(**vars(proof.paper_certifications[0])),
            ),
        )
    coverage = proof.coverage[0]
    with pytest.raises(CertificationError, match="exact coverage certifications"):
        replace(
            proof, coverage=(SimpleNamespace(**vars(coverage)), *proof.coverage[1:])
        )
    with pytest.raises(CertificationError, match="exact population evidence"):
        replace(coverage, population=SimpleNamespace(**vars(coverage.population)))
    with pytest.raises(CertificationError, match="exact decision masses"):
        replace(
            coverage,
            decision_masses=(SimpleNamespace(**vars(coverage.decision_masses[0])),),
        )


def test_population_proofs_reject_unvalidated_category_and_population_payloads() -> (
    None
):
    raw = partition(
        "institution-diversity",
        (paper(1, 2025, categories=(("theory", 1.0),)),),
        categories=("theory", "phenomenology"),
    )
    certified = certify_partition(raw, "research_diversity")
    population = certified.population_proof
    evidence = population.certification.evidence
    category = evidence.category_universe
    assert category is not None
    with pytest.raises(
        CertificationError, match="certified reviewed category universe"
    ):
        replace(evidence, category_universe=SimpleNamespace(**vars(category)))
    with pytest.raises(CertificationError, match="exact reviewed evidence"):
        CertifiedCategoryUniverse(
            SimpleNamespace(
                **vars(category.evidence),
                content_digest=category.evidence.content_digest,
            ),
            category.certification_digest,
        )
    with pytest.raises(CertificationError, match="exact projections"):
        replace(
            evidence, projections=(SimpleNamespace(**vars(evidence.projections[0])),)
        )
    with pytest.raises(CertificationError, match="exact decisions"):
        replace(evidence, decisions=(SimpleNamespace(**vars(evidence.decisions[0])),))
    with pytest.raises(CertificationError, match="exact certification result"):
        replace(
            population, certification=SimpleNamespace(**vars(population.certification))
        )
    with pytest.raises(CertificationError, match="exact reviewed evidence"):
        wrap_certified_metric_population(
            SimpleNamespace(**vars(evidence)), certified.window_proof
        )
    with pytest.raises(CertificationError, match="certified window proof"):
        wrap_certified_metric_population(
            evidence, SimpleNamespace(**vars(certified.window_proof))
        )


def test_coverage_certification_binds_v1_minimum_and_evidence_ids() -> None:
    with pytest.raises(ValueError, match="v1 evidence policy"):
        CoverageCertification(
            evidence_kind="field-classification",
            numerator=1,
            denominator=1,
            minimum=0,
            state="certified",
            population=CoveragePopulationEvidence(
                "field-classification",
                (("coverage-field-1", 1.0),),
                (("paper-1", 1.0),),
                _CHECKSUM,
            ),
            decision_ids=("decision-1",),
            decision_masses=(CoverageDecisionMass("decision-1", 1, 1),),
        )
    with pytest.raises(ValueError, match="non-empty and unique"):
        CoverageCertification(
            evidence_kind="field-classification",
            numerator=1,
            denominator=1,
            minimum=0.9,
            state="certified",
            population=CoveragePopulationEvidence(
                "field-classification",
                (("coverage-field-1", 1.0),),
                (("paper-1", 1.0),),
                _CHECKSUM,
            ),
            decision_ids=(),
            decision_masses=(),
        )
    with pytest.raises(ValueError, match="either zero or its full mass"):
        CoverageDecisionMass("decision-1", 95, 100)

    evidence = EvidenceCertificationDecision(
        subject_type=COVERAGE_SUBJECT_TYPE,
        subject_id="coverage-field-1",
        evidence_kind="field-classification",
        state="certified",
        rule_version=FIELD_CERTIFICATION_RULE_VERSION,
        dataset_version="dataset-test-v1",
        acquisition_scope="hep-th-v1",
        evidence=(
            EvidenceReference(
                provider="test",
                source_record_id="field-1",
                checksum=_CHECKSUM,
            ),
        ),
    )
    forged = CoverageCertification(
        evidence_kind="field-classification",
        numerator=0,
        denominator=1,
        minimum=0.9,
        state="insufficient_evidence",
        population=CoveragePopulationEvidence(
            "field-classification",
            (("coverage-field-1", 1.0),),
            (),
            _CHECKSUM,
        ),
        decision_ids=(evidence.decision_id,),
        decision_masses=(CoverageDecisionMass(evidence.decision_id, 0, 1),),
        reasons=("fabricated state",),
    )
    with pytest.raises(CertificationError, match="current evidence decisions"):
        validate_coverage_certification(forged, (evidence,))


def test_calculator_rejects_stale_threshold_certification() -> None:
    raw = partition("institution-a", tuple(paper(index, 2025) for index in range(10)))
    certified = certify_partition(raw, "research_activity_score")
    with pytest.raises(CertificationError, match="window lineage differs"):
        replace(
            certified,
            certification=replace(
                certified.certification,
                threshold_version="metric-validation-thresholds-v0",
            ),
        )

    forged_v1 = replace(
        METRIC_VALIDATION_THRESHOLDS_V1,
        activity=replace(
            METRIC_VALIDATION_THRESHOLDS_V1.activity,
            minimum_fractional_papers=1,
        ),
    )
    with pytest.raises(CertificationError, match="canonical definition"):
        calculate_activity_raw(certified, forged_v1)


def _activity_boundary_inputs():  # type: ignore[no-untyped-def]
    raw = partition("institution-a", (paper(1, 2025),))
    certified = certify_partition(raw, "research_activity_score")
    decisions = certified.certification.evidence_decisions
    ordered_decisions = (
        *tuple(item for item in decisions if item.subject_type == "paper"),
        *tuple(item for item in decisions if item.subject_type != "paper"),
    )
    return (
        raw,
        ordered_decisions,
        certified.certification.coverage,
        certified.window_proof,
        certified.population_proof,
    )


def test_materializer_rejects_stale_unreviewed_and_wrong_window_evidence() -> None:
    raw, decisions, coverage, window, population = _activity_boundary_inputs()
    stale = (replace(decisions[0], rule_version="stale-rule-v0"), *decisions[1:])
    with pytest.raises(CertificationError, match="rule is stale"):
        build_certified_metric_partition(
            raw,
            metric_id="research_activity_score",
            decisions=stale,
            coverage=coverage,
            window=window,
            population=population,
        )

    unreviewed = (
        replace(decisions[0], state="needs_review", reasons=("review pending",)),
        *decisions[1:],
    )
    with pytest.raises(CertificationError, match="non-certified"):
        build_certified_metric_partition(
            raw,
            metric_id="research_activity_score",
            decisions=unreviewed,
            coverage=coverage,
            window=window,
            population=population,
        )

    with pytest.raises(CertificationError, match="does not reconstruct"):
        replace(
            window,
            certification=replace(window.certification, rule_version="stale-window-v0"),
        )


def test_certified_partition_reconstructs_window_population_and_category_context() -> (
    None
):
    raw = partition(
        "institution-diversity",
        tuple(paper(index, 2025, categories=(("theory", 1.0),)) for index in range(15)),
        categories=("theory", "phenomenology"),
    )
    certified = certify_partition(raw, "research_diversity")

    wrong_year = replace(raw, terminal_year=2024)
    with pytest.raises(CertificationError, match="window lineage differs"):
        CertifiedMetricPartition(
            wrong_year,
            replace(
                certified.certification,
                input_digest=canonical_digest(wrong_year),
            ),
            certified.window_proof,
            certified.population_proof,
        )

    wrong_categories = replace(raw, eligible_category_ids=("theory",))
    with pytest.raises(CertificationError, match="category universe"):
        CertifiedMetricPartition(
            wrong_categories,
            replace(
                certified.certification,
                input_digest=canonical_digest(wrong_categories),
            ),
            certified.window_proof,
            certified.population_proof,
        )

    population = certified.population_proof
    original = next(
        item
        for item in population.certification.evidence.projections
        if item.status == "included"
    )
    forged_projection = replace(
        original,
        status="excluded",
        entity_attribution_weight=0.0,
        attribution_weight=0.0,
        coverage_weight=0.0,
        reason="caller chose to omit eligible evidence",
    )
    forged_projections = tuple(
        forged_projection if item.paper_id == original.paper_id else item
        for item in population.certification.evidence.projections
    )
    forged_decisions = tuple(
        replace(item, certified_value_digest=forged_projection.value_digest)
        if item.subject_id == forged_projection.paper_id
        else item
        for item in population.certification.evidence.decisions
    )
    forged_evidence = replace(
        population.certification.evidence,
        projections=forged_projections,
        decisions=forged_decisions,
        source_manifest_digest=canonical_digest(
            tuple(sorted(forged_projections, key=lambda item: item.paper_id))
        ),
    )
    with pytest.raises(CertificationError, match="conserved source"):
        wrap_certified_metric_population(forged_evidence, certified.window_proof)


def test_partition_coverage_cannot_omit_unresolved_population_mass() -> None:
    raw = partition(
        "institution-a",
        (paper(1, 2025, weight=0.95),),
        coverage=complete_coverage(
            paper_time_affiliation=0.95,
            canonical_institution=0.95,
            field_attribution=0.95,
        ),
    )
    certified = certify_partition(
        raw,
        "research_activity_score",
        unresolved_entity_remainder=True,
    )
    field_coverage = next(
        item
        for item in certified.certification.coverage
        if item.evidence_kind == "field-classification"
    )
    assert field_coverage.ratio == pytest.approx(0.95)
    current = tuple(
        item
        for item in certified.certification.evidence_decisions
        if item.subject_type == COVERAGE_SUBJECT_TYPE
        and item.evidence_kind == field_coverage.evidence_kind
    )
    known = next(item for item in current if item.state == "certified")
    known_mass = dict(field_coverage.population.units)[known.subject_id]
    forged = certify_coverage(
        field_coverage.evidence_kind,
        (known,),
        CoveragePopulationEvidence(
            evidence_kind=field_coverage.evidence_kind,
            units=((known.subject_id, known_mass),),
            formula_inputs=field_coverage.population.formula_inputs,
            source_manifest_digest=(
                certified.population_proof.certification.projection_digest
            ),
        ),
    )
    forged_coverage = tuple(
        forged if item.evidence_kind == forged.evidence_kind else item
        for item in certified.certification.coverage
    )
    retained_decisions = tuple(
        item
        for item in certified.certification.evidence_decisions
        if not (
            item.subject_type == COVERAGE_SUBJECT_TYPE
            and item.evidence_kind == forged.evidence_kind
            and item.decision_id != known.decision_id
        )
    )
    with pytest.raises(CertificationError, match="exact reviewed metric population"):
        build_certified_metric_partition(
            raw,
            metric_id="research_activity_score",
            decisions=retained_decisions,
            coverage=forged_coverage,
            window=certified.window_proof,
            population=certified.population_proof,
        )


def test_materializer_uses_current_decision_and_rejects_stale_coverage_links() -> None:
    raw, decisions, coverage, window, population = _activity_boundary_inputs()
    old = decisions[0]
    newer = replace(
        old,
        evidence=(
            *old.evidence,
            EvidenceReference(
                provider="review",
                source_record_id="review-1",
                checksum="b" * 64,
            ),
        ),
        supersedes_decision_id=old.decision_id,
    )
    current = build_certified_metric_partition(
        raw,
        metric_id="research_activity_score",
        decisions=(*decisions, newer),
        coverage=coverage,
        window=window,
        population=population,
    )
    assert old.decision_id not in current.certification.decision_ids
    assert newer.decision_id in current.certification.decision_ids

    field = next(
        item
        for item in decisions
        if item.evidence_kind == "field-classification"
        and item.subject_type == COVERAGE_SUBJECT_TYPE
    )
    new_field = replace(
        field,
        evidence=(
            *field.evidence,
            EvidenceReference(
                provider="review",
                source_record_id="field-review",
                checksum="c" * 64,
            ),
        ),
        supersedes_decision_id=field.decision_id,
    )
    with pytest.raises(CertificationError, match="stale decision"):
        build_certified_metric_partition(
            raw,
            metric_id="research_activity_score",
            decisions=(*decisions, new_field),
            coverage=coverage,
            window=window,
            population=population,
        )


def test_institution_certification_uses_exact_ror_and_single_parent_rollup() -> None:
    parent = InstitutionAuthorityRecord(
        institution_id="institution-parent",
        ror_id="01parent00",
        canonical_name="Example University",
    )
    child = InstitutionAuthorityRecord(
        institution_id="institution-lab",
        ror_id="02child000",
        canonical_name="Example Physics Laboratory",
        parent_ror_ids=(parent.ror_id,),
        parent_rollup_eligible=True,
    )
    result = certify_institution(
        InstitutionResolutionEvidence(
            raw_name="Example Physics Laboratory",
            source_evidence_ids=("inspire:1",),
            source_manifest_digest=_CHECKSUM,
            authority_version=institution_authority_version((parent, child)),
            direct_ror_ids=(child.ror_id,),
        ),
        (parent, child),
    )
    assert result.state == "certified"
    assert result.canonical_institution_id == parent.institution_id
    assert result.source_institution_id == child.institution_id
    assert result.retained_subunit_label == child.canonical_name
    assert "parent-rollup" in (result.match_method or "")
    assert result.evidence.source_manifest_digest == _CHECKSUM

    unapproved_rollup = certify_institution(
        _institution_evidence(
            None,
            (parent, replace(child, parent_rollup_eligible=False)),
            direct_ror_ids=(child.ror_id,),
        ),
        (parent, replace(child, parent_rollup_eligible=False)),
    )
    assert unapproved_rollup.state == "needs_review"
    assert "explicitly permit" in " ".join(unapproved_rollup.reasons)


def test_institution_certification_withholds_ambiguous_or_inactive_matches() -> None:
    first = InstitutionAuthorityRecord(
        institution_id="first",
        ror_id="01first000",
        canonical_name="Shared Institute",
    )
    second = InstitutionAuthorityRecord(
        institution_id="second",
        ror_id="02second00",
        canonical_name="Other",
        aliases=("Shared Institute",),
    )
    ambiguous = certify_institution(
        _institution_evidence("Shared Institute", (first, second)),
        (first, second),
    )
    assert ambiguous.state == "needs_review"
    assert ambiguous.canonical_institution_id is None

    inactive = replace(first, active=False)
    result = certify_institution(
        _institution_evidence(None, (inactive,), direct_ror_ids=(inactive.ror_id,)),
        (inactive,),
    )
    assert result.state == "needs_review"
    assert result.canonical_institution_id is None

    raw_context = certify_institution(
        _institution_evidence(
            None,
            (first,),
            context_candidate_ids=(first.institution_id,),
        ),
        (first,),
    )
    assert raw_context.state == "needs_review"
    reviewed_context = certify_institution(
        _institution_evidence(
            None,
            (first,),
            context_candidate_ids=(first.institution_id,),
            reviewed_context_institution_id=first.institution_id,
            review_state="reviewed-approved",
            reviewed_by="reviewer-1",
            reviewed_at=_CUTOFF,
            confidence=0.9,
        ),
        (first,),
    )
    assert reviewed_context.state == "certified"
    assert reviewed_context.match_method == "reviewed-context-match"
    assert reviewed_context.evidence.confidence == 0.9


def test_field_certification_requires_review_and_exact_mass_conservation() -> None:
    evidence = FieldLedgerEvidence(
        paper_id="paper-1",
        assignments=(FieldWeight("hep-th", 0.5),),
        unmapped_mass=0.5,
        review_state="unreviewed",
        ontology_version="physics-field-ontology-v1",
        mapping_policy_version="provider-field-mapping-v1",
        weighting_policy_version="provider-evidence-conservation-v2",
        source_evidence_ids=("inspire:1", "arxiv:1"),
        source_manifest_digest=_CHECKSUM,
    )
    assert certify_field_ledger(evidence).state == "needs_review"
    approved = certify_field_ledger(
        replace(
            evidence,
            review_state="reviewed-approved",
            reviewed_by="reviewer-1",
            reviewed_at=_CUTOFF,
            review_confidence=0.95,
        )
    )
    assert approved.state == "certified"
    assert approved.conservation_total == 1
    assert approved.unmapped_mass == 0.5
    assert approved.evidence.mapping_policy_version == "provider-field-mapping-v1"
    assert approved.evidence.review_confidence == 0.95

    broken = replace(
        evidence,
        review_state="reviewed-approved",
        assignments=(FieldWeight("hep-th", 0.75),),
    )
    assert certify_field_ledger(broken).state == "conflicted"
    invented_field = replace(
        approved.evidence,
        assignments=(FieldWeight("invented-physics", 1.0),),
        unmapped_mass=0.0,
    )
    assert certify_field_ledger(invented_field).state == "conflicted"


def _citation_evidence(
    paper_id: str,
    *,
    non_self_count: int | None = 0,
    cutoff: datetime = _CUTOFF,
    publication_year: int = 2022,
) -> CitationObservationEvidence:
    return CitationObservationEvidence(
        paper_id=paper_id,
        dataset_version="paired-trial-v1",
        acquisition_scope="paired-field-trial-v1",
        citation_source="inspire",
        raw_citation_count=1,
        non_self_citation_count=non_self_count,
        observed_at=cutoff,
        selected_cutoff=cutoff,
        publication_date=date(publication_year, 1, 1),
        field_id="hep-th",
        document_type="article",
        source_reference=EvidenceReference(
            provider="inspire",
            source_record_id=paper_id,
            checksum=_CHECKSUM,
        ),
        citation_policy_version="non-self-citation-cutoff-v1",
    )


def _citation_population(
    observations: tuple[CitationObservationCertification, ...],
    *,
    dataset_version: str = "paired-trial-v1",
    acquisition_scope: str = "paired-field-trial-v1",
) -> CitationCohortPopulationEvidence:
    first = observations[0]
    assert first.cohort_key is not None
    assert first.cutoff is not None
    evidence = CitationCohortPopulationEvidence(
        cohort_key=first.cohort_key,
        cutoff=first.cutoff,
        dataset_version=dataset_version,
        acquisition_scope=acquisition_scope,
        eligible_paper_ids=tuple(sorted({item.paper_id for item in observations})),
        source_manifest_digest="0" * 64,
        review_state="reviewed-approved",
        reviewed_by="test-fixture-reviewer",
        reviewed_at=_CUTOFF,
    )
    return replace(evidence, source_manifest_digest=evidence.content_digest)


def test_citation_certification_preserves_zero_and_rejects_raw_only_counts() -> None:
    measured_zero = certify_citation_observation(_citation_evidence("paper-1"))
    assert measured_zero.state == "certified"
    assert measured_zero.non_self_citation_count == 0
    with pytest.raises(ValueError, match="do not reconstruct"):
        replace(measured_zero, non_self_citation_count=99)
    with pytest.raises(ValueError, match="rule is stale"):
        replace(measured_zero, rule_version="citation-rule-v0")
    with pytest.raises(ValueError, match="v1 maturity window"):
        replace(measured_zero, maturity_months=1)
    non_v1_maturity = certify_citation_observation(
        _citation_evidence(
            "paper-short-maturity",
            publication_year=2026,
        ),
        maturity_months=1,
    )
    assert non_v1_maturity.state == "conflicted"
    assert "non-v1 maturity" in " ".join(non_v1_maturity.reasons)
    raw_only = certify_citation_observation(
        _citation_evidence("paper-2", non_self_count=None)
    )
    assert raw_only.state == "insufficient_evidence"
    assert "non-self" in " ".join(raw_only.reasons)

    with pytest.raises(ValueError, match="do not reconstruct"):
        CitationObservationCertification(
            evidence=_citation_evidence("paper-forged"),
            paper_id="paper-forged",
            state="certified",
            non_self_citation_count=None,
            cutoff=_CUTOFF,
            cohort_key=("hep-th", 2022, "article"),
            mature=True,
            maturity_months=24,
            evidence_digest=canonical_digest(_citation_evidence("paper-forged")),
            reasons=(),
        )


def test_citation_cohort_requires_one_cutoff_and_minimum_size() -> None:
    first = certify_citation_observation(_citation_evidence("paper-1"))
    second = certify_citation_observation(_citation_evidence("paper-2"))
    cohort = certify_citation_cohort(
        (first, second),
        dataset_version="paired-trial-v1",
        acquisition_scope="paired-field-trial-v1",
        minimum_paper_count=2,
        population_evidence=_citation_population((first, second)),
    )
    assert cohort.state == "certified"
    with pytest.raises(ValueError, match="exact observation certifications"):
        replace(cohort, observations=(object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exact population evidence"):
        replace(cohort, population_evidence=object())  # type: ignore[arg-type]

    unreviewed_population = certify_citation_cohort(
        (first, second),
        dataset_version="paired-trial-v1",
        acquisition_scope="paired-field-trial-v1",
        minimum_paper_count=2,
    )
    assert unreviewed_population.state == "insufficient_evidence"
    third = certify_citation_observation(_citation_evidence("paper-3"))
    omitted_eligible_paper = certify_citation_cohort(
        (first, second),
        dataset_version="paired-trial-v1",
        acquisition_scope="paired-field-trial-v1",
        minimum_paper_count=2,
        population_evidence=_citation_population((first, second, third)),
    )
    assert omitted_eligible_paper.state == "conflicted"

    small = certify_citation_cohort(
        (first,),
        dataset_version="paired-trial-v1",
        acquisition_scope="paired-field-trial-v1",
        minimum_paper_count=2,
        population_evidence=_citation_population((first,)),
    )
    assert small.state == "insufficient_evidence"
    later = certify_citation_observation(
        _citation_evidence("paper-3", cutoff=datetime(2027, 1, 1, tzinfo=UTC))
    )
    mixed = certify_citation_cohort(
        (first, later),
        dataset_version="paired-trial-v1",
        acquisition_scope="paired-field-trial-v1",
        minimum_paper_count=2,
        population_evidence=_citation_population((first, later)),
    )
    assert mixed.state == "conflicted"
    same_day_later = certify_citation_observation(
        _citation_evidence("paper-4", cutoff=datetime(2026, 12, 31, 12, tzinfo=UTC))
    )
    mixed_same_day = certify_citation_cohort(
        (first, same_day_later),
        dataset_version="dataset-test-v1",
        acquisition_scope="hep-th-v1",
        minimum_paper_count=2,
        population_evidence=_citation_population(
            (first, same_day_later),
            dataset_version="dataset-test-v1",
            acquisition_scope="hep-th-v1",
        ),
    )
    assert mixed_same_day.state == "conflicted"

    duplicate = certify_citation_cohort(
        (first, first),
        dataset_version="dataset-test-v1",
        acquisition_scope="hep-th-v1",
        minimum_paper_count=2,
        population_evidence=_citation_population(
            (first, first),
            dataset_version="dataset-test-v1",
            acquisition_scope="hep-th-v1",
        ),
    )
    assert duplicate.state == "conflicted"
    assert duplicate.paper_count == 1


def test_citation_certification_rejects_count_and_timestamp_inconsistency() -> None:
    with pytest.raises(ValueError, match="nonnegative integers"):
        replace(_citation_evidence("paper-bool"), raw_citation_count=True)
    with pytest.raises(ValueError, match="nonnegative integers"):
        replace(_citation_evidence("paper-float"), raw_citation_count=1.5)
    impossible_count = certify_citation_observation(
        replace(
            _citation_evidence("paper-count"),
            raw_citation_count=1,
            non_self_citation_count=2,
        )
    )
    assert impossible_count.state == "conflicted"

    naive = datetime(2026, 12, 31)
    timestamp = certify_citation_observation(
        replace(
            _citation_evidence("paper-time"),
            observed_at=naive,
            selected_cutoff=naive,
        )
    )
    assert timestamp.state == "conflicted"

    missing_raw = certify_citation_observation(
        replace(_citation_evidence("paper-raw"), raw_citation_count=None)
    )
    assert missing_raw.state == "insufficient_evidence"


def _coverage_components(
    source_manifest_digest: str = _CHECKSUM,
    paper_id: str = "paper-2022-1",
    evidence_kind: EvidenceKind = "field-classification",
) -> tuple[
    tuple[CoverageCertification, ...],
    tuple[EvidenceCertificationDecision, ...],
]:
    decision = EvidenceCertificationDecision(
        subject_type=COVERAGE_SUBJECT_TYPE,
        subject_id=paper_id,
        evidence_kind=evidence_kind,
        state="certified",
        rule_version={
            "field-classification": FIELD_CERTIFICATION_RULE_VERSION,
            "citation-observation": CITATION_CERTIFICATION_RULE_VERSION,
        }.get(evidence_kind, CERTIFICATION_POLICY_VERSION),
        dataset_version="paired-trial-v1",
        acquisition_scope="paired-field-trial-v1",
        evidence=(
            EvidenceReference(
                provider="test",
                source_record_id="field-review",
                checksum=_CHECKSUM,
            ),
        ),
    )
    return (
        (
            certify_coverage(
                evidence_kind,
                (decision,),
                CoveragePopulationEvidence(
                    evidence_kind=evidence_kind,
                    units=((decision.subject_id, 1.0),),
                    formula_inputs=((paper_id, 1.0),),
                    source_manifest_digest=source_manifest_digest,
                ),
            ),
        ),
        (decision,),
    )


def _coverage(
    year: int,
    kinds: tuple[EvidenceKind, ...] = ("field-classification",),
) -> tuple[CoverageCertification, ...]:
    projection = _source_year_projection(year)
    return tuple(
        _coverage_components(
            canonical_digest((projection,)), projection.paper_id, kind
        )[0][0]
        for kind in kinds
    )


def _source_year_projection(year: int) -> SourceYearPaperProjection:
    partition_id = f"inspire-{year}"
    source_reference = EvidenceReference(
        provider="inspire",
        source_record_id=f"paper-{year}-1",
        checksum=_CHECKSUM,
        source_snapshot_id=partition_id,
    )
    return SourceYearPaperProjection(
        paper_id=f"paper-{year}-1",
        publication_date=date(year, 1, 1),
        occurrence_references=(source_reference,),
        field_weights=(("hep-th", 1.0),),
        unmapped_field_mass=0.0,
        field_weight_total=1.0,
        field_weighting_policy_version=FIELD_WEIGHTING_POLICY_VERSION,
        entity_shares=(("researcher", "researcher-test", 1.0),),
        unresolved_entity_mass=(("researcher", 0.0),),
        attribution_policy_version=FRACTIONAL_ATTRIBUTION_V1.version,
    )


def _year_evidence(
    year: int,
    *,
    complete: bool = True,
    coverage_kinds: tuple[EvidenceKind, ...] = ("field-classification",),
) -> SourceYearEvidence:
    partition_id = f"inspire-{year}"
    projection = _source_year_projection(year)
    source_reference = projection.occurrence_references[0]
    source_manifest_digest = canonical_digest((projection,))
    return SourceYearEvidence(
        calendar_year=year,
        entity_type="researcher",
        cutoff=_CUTOFF,
        dataset_version="paired-trial-v1",
        acquisition_scope="paired-field-trial-v1",
        acquisition_plan=SourceAcquisitionPlanEvidence(
            calendar_year=year,
            cutoff=_CUTOFF,
            dataset_version="paired-trial-v1",
            acquisition_scope="paired-field-trial-v1",
            partitions=((partition_id, "inspire"),),
            source_manifest_digest=canonical_digest(
                (
                    year,
                    _CUTOFF,
                    "paired-trial-v1",
                    "paired-field-trial-v1",
                    ((partition_id, "inspire"),),
                )
            ),
            review_state="reviewed-approved",
            reviewed_by="test-fixture-reviewer",
            reviewed_at=_CUTOFF,
        ),
        required_partition_ids=(partition_id,),
        required_coverage_kinds=coverage_kinds,
        paper_projections=(projection,),
        partitions=(
            SourcePartitionEvidence(
                partition_id=partition_id,
                provider="inspire",
                expected_unique_records=1,
                observed_records=1,
                observed_unique_records=1,
                duplicate_records=0,
                truncated=False,
                page_checksums=(_CHECKSUM,),
                record_inventory_digest=source_record_inventory_digest(
                    (source_reference,)
                ),
                complete=complete,
            ),
        ),
        structural_decisions=tuple(
            EvidenceCertificationDecision(
                subject_type="paper",
                subject_id=f"paper-{year}-1",
                evidence_kind=kind,  # type: ignore[arg-type]
                state="certified",
                rule_version=(
                    FIELD_CERTIFICATION_RULE_VERSION
                    if kind == "field-weight-conservation"
                    else CERTIFICATION_POLICY_VERSION
                ),
                dataset_version="paired-trial-v1",
                acquisition_scope="paired-field-trial-v1",
                evidence=(source_reference,),
                certified_value_digest=projection.decision_value_digest(kind),
            )
            for kind in (
                "canonical-paper-identity",
                "publication-metric-date",
                "field-weight-conservation",
                "provenance-completeness",
            )
        ),
        coverage_decisions=tuple(
            decision
            for kind in coverage_kinds
            for decision in _coverage_components(
                source_manifest_digest, projection.paper_id, kind
            )[1]
        ),
    )


def test_source_year_requires_closed_complete_partitions_and_structural_proof() -> None:
    certified = certify_source_year(_year_evidence(2022), _coverage(2022))
    assert certified.state == "certified"
    assert certified.verified_partition_ids == ("inspire-2022",)
    with pytest.raises(CertificationError, match="exact source-year evidence"):
        CertifiedSourceYear(  # type: ignore[arg-type]
            evidence=object(),
            coverage=certified.coverage,
            certification=certified.certification,
        )
    with pytest.raises(CertificationError, match="exact coverage certifications"):
        CertifiedSourceYear(  # type: ignore[arg-type]
            evidence=certified.evidence,
            coverage=(object(),),
            certification=certified.certification,
        )

    incomplete = certify_source_year(
        _year_evidence(2022, complete=False), _coverage(2022)
    )
    assert incomplete.state == "conflicted"
    current = certify_source_year(_year_evidence(2026), _coverage(2026))
    assert current.state == "withheld"
    empty_coverage = certify_source_year(_year_evidence(2022), ())
    assert empty_coverage.state == "insufficient_evidence"
    invalid_checksum = replace(
        _year_evidence(2022),
        partitions=(
            replace(_year_evidence(2022).partitions[0], page_checksums=("z" * 64,)),
        ),
    )
    assert certify_source_year(invalid_checksum, _coverage(2022)).state == "conflicted"
    missing_required = replace(
        _year_evidence(2022),
        required_coverage_kinds=(
            "field-classification",
            "paper-time-affiliation",
        ),
    )
    assert (
        certify_source_year(missing_required, _coverage(2022)).state
        == "insufficient_evidence"
    )


def test_metric_windows_require_exact_certified_years_and_impact_cohorts() -> None:
    empty = certify_metric_window(
        metric_id="research_activity_score",
        entity_type="researcher",
        terminal_year=2025,
        source_years=(),
        threshold_version="metric-validation-thresholds-v1",
    )
    assert empty.state == "insufficient_evidence"
    assert empty.cutoff.tzinfo is not None

    years = tuple(
        certify_source_year(_year_evidence(year), _coverage(year))
        for year in (2023, 2024, 2025)
    )
    activity = certify_metric_window(
        metric_id="research_activity_score",
        entity_type="researcher",
        terminal_year=2025,
        source_years=years,
        threshold_version="metric-validation-thresholds-v1",
    )
    assert activity.state == "certified"
    with pytest.raises(CertificationError, match="reconstructable source years"):
        CertifiedMetricWindow(  # type: ignore[arg-type]
            source_years=(object(),),
            citation_cohorts=(),
            certification=activity.certification,
        )
    with pytest.raises(CertificationError, match="reconstructable citation cohorts"):
        CertifiedMetricWindow(  # type: ignore[arg-type]
            source_years=activity.source_years,
            citation_cohorts=(object(),),
            certification=activity.certification,
        )

    impact = certify_metric_window(
        metric_id="research_impact",
        entity_type="researcher",
        terminal_year=2025,
        source_years=years,
        threshold_version="metric-validation-thresholds-v1",
    )
    assert impact.state == "insufficient_evidence"
    impact_cutoff = datetime(2027, 12, 31, tzinfo=UTC)
    impact_coverage_kinds: tuple[EvidenceKind, ...] = (
        "field-classification",
        "citation-observation",
    )

    def impact_year_evidence(year: int) -> SourceYearEvidence:
        evidence = _year_evidence(year, coverage_kinds=impact_coverage_kinds)
        plan = evidence.acquisition_plan
        updated_plan = replace(
            plan,
            cutoff=impact_cutoff,
            source_manifest_digest=canonical_digest(
                (
                    plan.calendar_year,
                    impact_cutoff,
                    plan.dataset_version,
                    plan.acquisition_scope,
                    tuple(sorted(plan.partitions)),
                )
            ),
        )
        return replace(evidence, cutoff=impact_cutoff, acquisition_plan=updated_plan)

    impact_years = tuple(
        certify_source_year(
            impact_year_evidence(year),
            _coverage(year, impact_coverage_kinds),
        )
        for year in (2023, 2024, 2025)
    )

    def impact_cohort(year: int):  # type: ignore[no-untyped-def]
        observations = tuple(
            certify_citation_observation(
                _citation_evidence(
                    f"paper-{year}-{index}",
                    cutoff=impact_cutoff,
                    publication_year=year,
                )
            )
            for index in range(50)
        )
        return certify_citation_cohort(
            observations,
            dataset_version="paired-trial-v1",
            acquisition_scope="paired-field-trial-v1",
            minimum_paper_count=50,
            population_evidence=_citation_population(observations),
        )

    citation_certifications = tuple(impact_cohort(year) for year in (2023, 2024, 2025))
    citation_cohorts = tuple(
        wrap_certified_citation_cohort(
            CitationReferenceCohort(
                field_id=item.cohort_key[0],
                publication_year=item.cohort_key[1],
                document_type=item.cohort_key[2],
                observed_at=item.cutoff.date(),
                citations=tuple(
                    sorted(
                        (
                            observation.paper_id,
                            observation.non_self_citation_count or 0,
                        )
                        for observation in item.observations
                    )
                ),
            ),
            item,
            dataset_version="paired-trial-v1",
            acquisition_scope="paired-field-trial-v1",
        )
        for item in citation_certifications
    )
    certified_impact = certify_metric_window(
        metric_id="research_impact",
        entity_type="researcher",
        terminal_year=2025,
        source_years=impact_years,
        threshold_version="metric-validation-thresholds-v1",
        citation_cohorts=citation_cohorts,
    )
    assert certified_impact.state == "certified"
    assert len(certified_impact.citation_cohort_certification_ids) == 3
    incomplete = certify_metric_window(
        metric_id="momentum",
        entity_type="researcher",
        terminal_year=2025,
        source_years=years,
        threshold_version="metric-validation-thresholds-v1",
    )
    assert incomplete.state == "insufficient_evidence"


def test_atlas_scale_preserves_raw_values_versions_cohorts_and_missing() -> None:
    thresholds = replace(
        METRIC_VALIDATION_THRESHOLDS_V1,
        version="metric-validation-presentation-test-v1",
        activity=replace(
            METRIC_VALIDATION_THRESHOLDS_V1.activity,
            minimum_normalization_cohort=2,
        ),
        impact=replace(
            METRIC_VALIDATION_THRESHOLDS_V1.impact,
            minimum_normalization_cohort=2,
        ),
        momentum=replace(
            METRIC_VALIDATION_THRESHOLDS_V1.momentum,
            minimum_normalization_cohort=2,
        ),
    )
    first_partition = partition(
        "institution-a", tuple(paper(index, 2025) for index in range(10))
    )
    second_partition = partition(
        "institution-b", tuple(paper(index + 20, 2025) for index in range(20))
    )
    first_certified = certify_partition(
        first_partition,
        "research_activity_score",
        threshold_version=thresholds.version,
    )
    second_certified = certify_partition(
        second_partition,
        "research_activity_score",
        threshold_version=thresholds.version,
    )
    first = calculate_activity_raw(first_certified, thresholds)
    second = calculate_activity_raw(second_certified, thresholds)

    results = (
        bind_metric_calculation(first, first_certified, thresholds),
        bind_metric_calculation(second, second_certified, thresholds),
    )
    with pytest.raises(CertificationError, match="bind certification first"):
        apply_atlas_scale((first,), thresholds)  # type: ignore[arg-type]
    atlas = apply_atlas_scale(
        results,
        thresholds,
        normalization_populations=certify_normalization_populations(results),
    )
    assert {item.calculation.metric_id for item in atlas} == {"research_activity_score"}
    assert all(item.value is not None and 0 <= item.value <= 100 for item in atlas)
    assert all(item.scale_version == "normalized-atlas-scale-v1" for item in atlas)
    assert all(
        item.calculation.raw_value == source.calculation.raw_value
        for item, source in zip(atlas, results, strict=True)
    )
    assert all(len(item.certification_manifest_digest) == 64 for item in atlas)
    assert atlas[0].comparison_cohort["cohort_size"] == 2
    with pytest.raises(CertificationError, match="certified calculations"):
        replace(atlas[0], normalization_proofs=(object(),))  # type: ignore[arg-type]
    with pytest.raises(CertificationError, match="population proof"):
        replace(  # type: ignore[arg-type]
            atlas[0], normalization_population_proof=object()
        )

    full_population = certify_normalization_populations(results)
    with pytest.raises(CertificationError, match="exact reviewed"):
        apply_atlas_scale(
            results[:1],
            thresholds,
            normalization_populations=full_population,
        )

    with pytest.raises(CertificationError, match="does not reconstruct"):
        bind_metric_calculation(
            replace(first, raw_value=999), first_certified, thresholds
        )

    sparse_partition = partition("institution-sparse", (paper(99, 2025),))
    sparse_certified = certify_partition(
        sparse_partition,
        "research_activity_score",
        threshold_version=thresholds.version,
    )
    missing_result = calculate_activity_raw(sparse_certified, thresholds)
    missing_inputs = (
        bind_metric_calculation(missing_result, sparse_certified, thresholds),
    )
    missing = apply_atlas_scale(
        missing_inputs,
        thresholds,
        normalization_populations=certify_normalization_populations(missing_inputs),
    )[0]
    assert missing.value is None
    assert missing.uncertainty_reasons

    different_partition = replace(
        second_partition,
        as_of_date=date(2026, 9, 1),
    )
    different_certified = certify_partition(
        different_partition,
        "research_activity_score",
        threshold_version=thresholds.version,
    )
    different_cutoff = calculate_activity_raw(different_certified, thresholds)
    separated_inputs = (
        bind_metric_calculation(first, first_certified, thresholds),
        bind_metric_calculation(different_cutoff, different_certified, thresholds),
    )
    separated = apply_atlas_scale(
        separated_inputs,
        thresholds,
        normalization_populations=certify_normalization_populations(separated_inputs),
    )
    assert all(item.value is None for item in separated)
    assert {item.cutoff for item in separated} == {
        "2026-08-30T00:00:00+00:00",
        "2026-09-01T00:00:00+00:00",
    }


def test_impact_calculator_requires_the_window_certified_cohort_ids() -> None:
    raw, cohorts = impact_fixture()
    certified_cohorts = tuple(
        certify_citation_reference_cohort(item, raw) for item in cohorts
    )
    certified = certify_partition(
        raw,
        "research_impact",
        citation_cohorts=certified_cohorts,
    )
    with pytest.raises(CertificationError, match="proof differs"):
        replace(
            certified_cohorts[0],
            certification_id="citation-cohort-wrong-proof",
        )

    with pytest.raises(CertificationError, match="differ from its window"):
        replace(
            certified,
            certification=replace(
                certified.certification,
                citation_cohort_certification_ids=("citation-cohort-forged",),
            ),
        )

    with pytest.raises(CertificationError, match="do not match"):
        calculate_impact_raw(certified, certified_cohorts[:-1])
