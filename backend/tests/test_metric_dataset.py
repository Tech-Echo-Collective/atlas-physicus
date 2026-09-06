"""Bounded exporter safeguards. Test fixtures are never production evidence."""

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from certification_helpers import certify_normalization_populations
from test_automatic_normalization import calculation
from test_metric_activation import complete_evidence

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.metrics.dataset import (
    AtlasDatasetEntities,
    RetainedScientificEvidence,
    _json_bytes,
    _observation_payload,
    build_atlas_dataset,
)
from physics_atlas_api.metrics.presentation import apply_atlas_scale

NOW = datetime(2026, 9, 5, tzinfo=UTC)
REFERENCE = RetainedScientificEvidence(
    "scientific-evidence.json", "a" * 64, 100, "compact-scientific-facts-v1"
)


def entities() -> AtlasDatasetEntities:
    provenance = {
        "source": "explicit transport test fixture, not scientific evidence",
        "sourceType": "external-api",
        "version": "fixture-only-v1",
        "status": "unverified",
    }
    return AtlasDatasetEntities.model_validate(
        {
            "scienceDomains": [
                {
                    "id": "physics",
                    "label": "Physics",
                    "description": "Fixture",
                    "fieldIds": ["hep-th"],
                    "provenance": provenance,
                }
            ],
            "fields": [
                {
                    "id": "hep-th",
                    "label": "Theory",
                    "description": "Fixture",
                    "ontologyVersion": "physics-field-ontology-v1",
                    "nodeKind": "field",
                    "isExplorable": True,
                    "displayOrder": 0,
                    "provenance": provenance,
                }
            ],
            "countries": [
                {
                    "id": "country-test",
                    "isoAlpha3": "USA",
                    "isoNumeric": "840",
                    "name": "Fixture geography",
                    "region": "Fixture",
                    "provenance": provenance,
                }
            ],
        }
    )


def test_export_is_joint_gate_bound_before_serialization() -> None:
    with pytest.raises(CertificationError, match="Joint Activation Gate withheld"):
        build_atlas_dataset(
            entities(),
            (),
            replace(complete_evidence(), normalization_validated=False),
            REFERENCE,
            generated_at=NOW,
        )
    with pytest.raises(CertificationError, match="all five metrics require"):
        build_atlas_dataset(
            entities(), (), complete_evidence(), REFERENCE, generated_at=NOW
        )


def test_export_rejects_raw_values_and_fixture_scientific_proofs() -> None:
    with pytest.raises(CertificationError, match="certified Atlas Scale"):
        build_atlas_dataset(
            entities(),
            (object(),),
            complete_evidence(),
            REFERENCE,
            generated_at=NOW,  # type: ignore[arg-type]
        )
    proof = calculation()
    atlas = apply_atlas_scale(
        (proof,), normalization_populations=certify_normalization_populations((proof,))
    )
    with pytest.raises(CertificationError, match="fixture or unsupported source years"):
        build_atlas_dataset(
            entities(), atlas, complete_evidence(), REFERENCE, generated_at=NOW
        )


def test_export_rejects_synthetic_ui_facts() -> None:
    content = entities()
    content.countries[0].provenance.status = "synthetic"
    with pytest.raises(CertificationError, match="synthetic facts"):
        build_atlas_dataset(
            content, (), complete_evidence(), REFERENCE, generated_at=NOW
        )


def test_missing_scale_output_preserves_raw_and_missing_not_zero() -> None:
    proof = calculation()
    atlas = apply_atlas_scale(
        (proof,), normalization_populations=certify_normalization_populations((proof,))
    )[0]
    # One peer cannot pass unchanged 30-peer normalization.
    row = _observation_payload(atlas, NOW)
    assert row["value"] is None
    assert row["rawValue"] == 15
    assert row["qualityFlags"]
    assert (
        row["normalizationParameters"]["certificationManifestDigest"]
        == atlas.certification_manifest_digest
    )
    assert (
        row["normalizationParameters"]["inputManifestDigest"]
        == atlas.calculation.input_manifest_digest
    )
    assert row["period"] == "2025"
    assert "certification_proof" not in json.dumps(row)


@pytest.mark.parametrize(
    "path",
    [
        "../facts.json",
        "/facts.json",
        "https://other/facts.json",
        "a//b",
        "a?x=1",
        "a\\b",
    ],
)
def test_scientific_evidence_reference_is_bounded_to_release(path: str) -> None:
    with pytest.raises(CertificationError, match="release-relative"):
        RetainedScientificEvidence(path, "a" * 64, 1, "facts-v1")


def test_scientific_evidence_is_required_and_exact() -> None:
    for changes in ({"sha256": "wrong"}, {"byte_length": 0}, {"schema_version": ""}):
        with pytest.raises(CertificationError, match="metadata is invalid"):
            replace(REFERENCE, **changes)  # type: ignore[arg-type]
    assert _json_bytes({"b": 2, "a": 1}) == _json_bytes({"a": 1, "b": 2})
    with pytest.raises(ValueError):
        _json_bytes({"invalid": float("nan")})
