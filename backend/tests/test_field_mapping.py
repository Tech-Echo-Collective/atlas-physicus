import pytest

from physics_atlas_api.fields import (
    ARXIV_CATEGORY_TAXONOMY,
    FIELD_WEIGHTING_POLICY_VERSION,
    PHYSICS_FIELD_ONTOLOGY_VERSION,
    PROVIDER_FIELD_MAPPING_VERSION,
    ProviderCategoryEvidence,
    ProviderFieldProjection,
    map_provider_categories,
    reconcile_cross_provider_field_evidence,
)


def test_mapping_preserves_roles_but_weights_unique_fields_equally() -> None:
    mapping = map_provider_categories(
        "arxiv",
        [
            ProviderCategoryEvidence(
                "astro-ph.CO",
                role="primary",
                taxonomy=ARXIV_CATEGORY_TAXONOMY,
            ),
            ProviderCategoryEvidence(
                "gr-qc",
                role="secondary",
                taxonomy=ARXIV_CATEGORY_TAXONOMY,
            ),
        ],
    )

    assert mapping.atlas_field_ids == ("gr-qc", "astro-ph")
    assert [assignment.weight for assignment in mapping.assignments] == [0.5, 0.5]
    assert sum(assignment.weight for assignment in mapping.assignments) == 1.0
    gravity = next(
        assignment
        for assignment in mapping.assignments
        if assignment.field_id == "gr-qc"
    )
    assert gravity.provider_roles == ("primary", "secondary")
    assert gravity.supporting_rule_ids == (
        "arxiv-astro-ph-co-provider-field-mapping-v1",
        "arxiv-gr-qc-provider-field-mapping-v1",
    )
    assert mapping.unmapped_field_mass == 0.0
    assert mapping.confidence is None


def test_primary_category_status_does_not_change_field_weight() -> None:
    mapping = map_provider_categories(
        "arxiv",
        [
            ProviderCategoryEvidence("hep-th", role="primary"),
            ProviderCategoryEvidence("gr-qc", role="secondary"),
        ],
    )

    assert {
        assignment.field_id: assignment.weight for assignment in mapping.assignments
    } == {"hep-th": 0.5, "gr-qc": 0.5}


def test_unmapped_category_is_retained_and_reduces_mapping_coverage() -> None:
    mapping = map_provider_categories("arxiv", ["hep-th", "unknown-provider-label"])

    assert mapping.raw_categories == ("hep-th", "unknown-provider-label")
    assert mapping.atlas_field_ids == ("hep-th",)
    assert mapping.unmapped_categories == ("unknown-provider-label",)
    assert mapping.mapping_coverage == pytest.approx(0.5)
    assert mapping.category_mappings[-1].status == "unmapped"
    assert mapping.category_mappings[-1].rule_id is None
    assert mapping.assignments[0].weight == pytest.approx(0.5)
    assert mapping.unmapped_field_mass == pytest.approx(0.5)
    assert (
        sum(assignment.weight for assignment in mapping.assignments)
        + mapping.unmapped_field_mass
    ) == pytest.approx(1.0)


def test_mapping_does_not_apply_an_implicit_provider_prefix() -> None:
    mapping = map_provider_categories("arxiv", ["cond-mat.unreviewed-future-category"])

    assert mapping.atlas_field_ids == ()
    assert mapping.unmapped_categories == ("cond-mat.unreviewed-future-category",)
    assert mapping.mapping_coverage == 0.0
    assert mapping.unmapped_field_mass == 1.0


def test_duplicate_provider_categories_do_not_create_additional_field_mass() -> None:
    mapping = map_provider_categories(
        "arxiv",
        ["hep-th", "hep-th", "unknown-provider-label"],
    )

    assert mapping.assignments[0].weight == pytest.approx(0.5)
    assert mapping.unmapped_field_mass == pytest.approx(0.5)
    assert mapping.mapping_coverage == pytest.approx(0.5)


def test_one_provider_category_splits_its_mass_across_all_mapped_fields() -> None:
    mapping = map_provider_categories("arxiv", ["astro-ph.CO"])

    assert {
        assignment.field_id: assignment.weight for assignment in mapping.assignments
    } == {"gr-qc": 0.5, "astro-ph": 0.5}
    assert mapping.unmapped_field_mass == 0.0


def test_lattice_categories_map_to_the_lattice_field() -> None:
    arxiv = map_provider_categories("arxiv", ["hep-lat"])
    inspire = map_provider_categories("inspire", ["Lattice"])

    assert arxiv.atlas_field_ids == ("hep-lat",)
    assert inspire.atlas_field_ids == ("hep-lat",)
    assert "hep-th" not in arxiv.atlas_field_ids
    assert "hep-ph" not in inspire.atlas_field_ids


def test_inspire_categories_remain_unspecified_without_provider_role_evidence() -> None:
    mapping = map_provider_categories(
        "inspire",
        [ProviderCategoryEvidence("Theory-HEP", source="INSPIRE")],
    )

    assert mapping.atlas_field_ids == ("hep-th",)
    assert mapping.category_mappings[0].evidence.role == "unspecified"
    assert mapping.assignments[0].provider_roles == ("unspecified",)


def test_mapping_versions_and_evidence_are_reconstructable() -> None:
    mapping = map_provider_categories("arxiv", ["cond-mat.stat-mech", "physics.bio-ph"])
    payload = mapping.provenance_payload()

    assert mapping.mapping_version == PROVIDER_FIELD_MAPPING_VERSION
    assert mapping.ontology_version == PHYSICS_FIELD_ONTOLOGY_VERSION
    assert mapping.weighting_policy_version == FIELD_WEIGHTING_POLICY_VERSION
    assert mapping.atlas_field_ids == (
        "cond-mat",
        "stat-nonlinear",
        "biophysics",
    )
    total_weight = sum(assignment.weight for assignment in mapping.assignments)
    assert total_weight == pytest.approx(1.0)
    assert payload["confidence"] is None
    assert payload["mapping_version"] == PROVIDER_FIELD_MAPPING_VERSION
    assert payload["unmapped_field_mass"] == 0.0
    assert len(payload["category_mappings"]) == 2  # type: ignore[arg-type]


def test_empty_evidence_does_not_invent_a_field_or_zero_observation() -> None:
    mapping = map_provider_categories("arxiv", [])

    assert mapping.atlas_field_ids == ()
    assert mapping.assignments == ()
    assert mapping.unmapped_field_mass == 1.0
    assert mapping.mapping_coverage is None


def test_cross_provider_evidence_produces_one_conserved_paper_ledger() -> None:
    ledger = reconcile_cross_provider_field_evidence(
        (
            ProviderFieldProjection(
                "inspire",
                "inspire-1",
                (ProviderCategoryEvidence("Theory-HEP", role="primary"),),
                "snapshot-inspire",
            ),
            ProviderFieldProjection(
                "arxiv",
                "arxiv-1",
                (ProviderCategoryEvidence("gr-qc", role="secondary"),),
                "snapshot-arxiv",
            ),
        )
    )

    assert {
        assignment.field_id: assignment.weight for assignment in ledger.assignments
    } == {"hep-th": 0.5, "gr-qc": 0.5}
    assert ledger.unmapped_field_mass == 0.0
    assert sum(item.weight for item in ledger.assignments) == 1.0


def test_cross_provider_duplicate_field_support_does_not_duplicate_mass() -> None:
    ledger = reconcile_cross_provider_field_evidence(
        (
            ProviderFieldProjection(
                "inspire", "1", (ProviderCategoryEvidence("Theory-HEP"),)
            ),
            ProviderFieldProjection(
                "arxiv", "2", (ProviderCategoryEvidence("hep-th"),)
            ),
        )
    )

    assert [(item.field_id, item.weight) for item in ledger.assignments] == [
        ("hep-th", 1.0)
    ]
    assert len(ledger.assignments[0].supporting_rule_ids) == 2


def test_cross_provider_ledger_retains_unmapped_mass_and_is_order_independent() -> None:
    projections = (
        ProviderFieldProjection(
            "inspire", "1", (ProviderCategoryEvidence("Theory-HEP"),)
        ),
        ProviderFieldProjection(
            "arxiv",
            "2",
            (ProviderCategoryEvidence("unknown-provider-label"),),
        ),
    )

    forward = reconcile_cross_provider_field_evidence(projections)
    reverse = reconcile_cross_provider_field_evidence(tuple(reversed(projections)))

    assert forward == reverse
    assert forward.assignments[0].weight == pytest.approx(0.5)
    assert forward.unmapped_field_mass == pytest.approx(0.5)
    assert forward.provenance_payload()["unmapped_field_mass"] == pytest.approx(0.5)
