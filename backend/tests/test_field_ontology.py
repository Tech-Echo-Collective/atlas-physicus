from dataclasses import FrozenInstanceError

import pytest

from physics_atlas_api.fields import (
    PHYSICS_FIELD_ONTOLOGY_V1,
    PHYSICS_FIELD_ONTOLOGY_VERSION,
    PROVIDER_FIELD_MAPPING_RULES_V1,
)


def test_physics_field_ontology_v1_contains_the_required_hierarchy() -> None:
    ontology = PHYSICS_FIELD_ONTOLOGY_V1

    assert ontology.version == "physics-field-ontology-v1"
    assert ontology.domain_id == "physics"
    assert [field.id for field in ontology.children_of("hep")] == [
        "hep-th",
        "hep-ph",
        "hep-ex",
        "hep-lat",
    ]
    assert [field.id for field in ontology.children_of("nuclear")] == [
        "nucl-th",
        "nucl-ex",
    ]
    assert [
        field.id for field in ontology.children_of("bio-soft-interdisciplinary")
    ] == ["biophysics", "soft-matter"]

    required = {
        "hep",
        "gr-qc",
        "astro-ph",
        "cond-mat",
        "amo",
        "quant-ph",
        "nuclear",
        "plasma",
        "math-ph",
        "stat-nonlinear",
        "bio-soft-interdisciplinary",
    }
    assert required.issubset({field.id for field in ontology.fields})


def test_ontology_preserves_legacy_public_leaf_ids() -> None:
    legacy_ids = {
        "hep-th",
        "hep-ph",
        "hep-ex",
        "gr-qc",
        "quant-ph",
        "astro-ph",
        "cond-mat",
        "amo",
        "nucl-th",
        "nucl-ex",
        "plasma",
        "biophysics",
        "math-ph",
    }

    assert all(PHYSICS_FIELD_ONTOLOGY_V1.contains(field_id) for field_id in legacy_ids)
    assert [field.id for field in PHYSICS_FIELD_ONTOLOGY_V1.ancestors_of("hep-th")] == [
        "hep"
    ]


def test_ontology_definitions_have_immutable_versioned_metadata() -> None:
    definition = PHYSICS_FIELD_ONTOLOGY_V1.get("quant-ph")

    assert definition.aliases
    assert isinstance(definition.aliases, tuple)
    assert definition.node_kind == "field"
    assert definition.display_order > 0
    assert definition.ontology_version == PHYSICS_FIELD_ONTOLOGY_VERSION
    assert definition.provenance.version == PHYSICS_FIELD_ONTOLOGY_VERSION
    with pytest.raises(FrozenInstanceError):
        definition.label = "Mutated label"  # type: ignore[misc]


def test_every_provider_mapping_target_exists_in_ontology_v1() -> None:
    for rule in PROVIDER_FIELD_MAPPING_RULES_V1:
        assert rule.mapping_version == "provider-field-mapping-v1"
        assert rule.ontology_version == PHYSICS_FIELD_ONTOLOGY_VERSION
        assert rule.atlas_field_ids
        assert all(
            PHYSICS_FIELD_ONTOLOGY_V1.contains(field_id)
            for field_id in rule.atlas_field_ids
        )
