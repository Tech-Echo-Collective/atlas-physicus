"""Bounded offline export checks; these fixtures never authorize production."""

import gzip
import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_launch_pipeline import (  # noqa: F401
    fake_transport,
    prepared_launch,
    source_inputs,
)

from physics_atlas_api import launch_export, launch_pipeline
from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.build_cache import bounded_build_verification_cache
from physics_atlas_api.certification.launch_entities import _reference_entities
from physics_atlas_api.metrics.contracts import CANDIDATE_METRIC_IDS
from physics_atlas_api.metrics.dataset import AtlasDatasetExport


@pytest.fixture
def measured_launch(prepared_launch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def] # noqa: F811
    """The real source->freeze->capture route on just twelve explicit fixtures."""
    transport = fake_transport(prepared_launch)
    monkeypatch.setattr(launch_pipeline, "LaunchTransport", lambda: transport)
    launch_pipeline.capture_citations(tmp_path)
    sessions = launch_pipeline._load(tmp_path, "measured-citations.pickle.gz")
    return launch_pipeline.CalculatedLaunch(prepared_launch, sessions, (), (), ())


def test_real_twelve_paper_pipeline_cannot_fabricate_a_release(measured_launch):  # type: ignore[no-untyped-def]
    with bounded_build_verification_cache():
        launch_export._verify_prepared_lineage(measured_launch)
        generated = measured_launch.sessions[0].measurement_finished_at + timedelta(
            seconds=1
        )
        with pytest.raises(CertificationError, match="actual Atlas observations"):
            launch_export.build_launch_export(
                measured_launch, geographic_views=(), generated_at=generated
            )
        with pytest.raises(CertificationError, match="timestamp"):
            launch_export.build_launch_export(
                measured_launch,
                geographic_views=(),
                generated_at=generated.replace(tzinfo=None),
            )


def test_changed_inventory_or_citation_lineage_is_refused(measured_launch):  # type: ignore[no-untyped-def]
    with bounded_build_verification_cache():
        changed = replace(
            measured_launch.prepared,
            canonical=replace(
                measured_launch.prepared.canonical,
                papers=measured_launch.prepared.canonical.papers[:-1],
            ),
        )
        with pytest.raises(CertificationError, match="inventories differ"):
            launch_export._verify_prepared_lineage(
                replace(measured_launch, prepared=changed)
            )
        with pytest.raises(CertificationError, match="sessions differ"):
            launch_export._verify_prepared_lineage(
                replace(measured_launch, sessions=measured_launch.sessions[:1])
            )
        with pytest.raises(CertificationError, match="freeze/source lineage"):
            launch_export._verify_prepared_lineage(
                replace(measured_launch, sessions=measured_launch.sessions[::-1])
            )
    with pytest.raises(CertificationError, match="exact calculated launch"):
        launch_export._verify_prepared_lineage(object())  # type: ignore[arg-type]


def test_exact_reconstruction_of_one_metric_never_implies_five() -> None:
    from test_launch_calculations import _window, _year

    from physics_atlas_api.certification.launch_calculations import (
        calculate_launch_metric_cohort,
    )
    from physics_atlas_api.certification.years import (
        EnumeratedLaunchSourceYearEvidence,
        certify_source_year,
        qualify_observed_release_source_year,
    )

    with bounded_build_verification_cache():
        years = []
        for year in (2021, 2022, 2023):
            original = _year(year)
            years.append(
                qualify_observed_release_source_year(
                    certify_source_year(
                        EnumeratedLaunchSourceYearEvidence(**vars(original.evidence)),
                        original.coverage,
                    )
                )
            )
        values = calculate_launch_metric_cohort(
            _window(tuple(years), "collaboration"), field_id="nucl-th"
        )
        assert values and all(value.value is None for value in values)
        # Isolate the reconstruction helper, not an activation authority. Real
        # source/window/raw/normalization checks run; the missing-four guard must
        # still refuse. No changed thresholds or fabricated metric outputs.
        scope = SimpleNamespace(
            _direct_observations=lambda observation: (observation,),
            require_metric_window=lambda window: window.__post_init__(),
            source_years=tuple(years),
        )
        calculated = SimpleNamespace(sessions=(), observations=values)
        with pytest.raises(CertificationError, match="all five implemented"):
            launch_export._reconstruct_calculations(scope, calculated)


def _transport_stubs(monkeypatch, measured):  # type: ignore[no-untyped-def]
    """Package-contract stubs only, deliberately not a scientific-positive fixture.

    The real science refusal above is not patched. Here upstream certified
    exporters are replaced to isolate final gzip/hash/manifest transport.
    """
    scope = SimpleNamespace(
        source_years=measured.prepared.source_years,
        dataset_version="explicit-transport-fixture-only",
        version="explicit-non-scientific-transport-scope",
        released_observations=(),
        root_field_id="nuclear",
        observed_coverage=lambda: {"fixture_only": None},
    )
    raw_facts = b'{"explicit-test-fixture":"not scientific evidence"}'
    retained = SimpleNamespace(
        content=raw_facts,
        sha256=hashlib.sha256(raw_facts).hexdigest(),
        byte_length=len(raw_facts),
        version="explicit-fixture-facts-v1",
        counts=(("papers", 12),),
    )
    entities = SimpleNamespace(
        entities=_reference_entities(()),
        source_references=(),
        omitted_counts=(("fixture_unknown_location", 1),),
        entity_counts=(("papers", 12),),
    )
    reconstruction = {
        "version": "explicit-transport-fixture-only",
        "externalBenchmarkClaim": False,
        "scientificPositiveClaim": False,
    }
    monkeypatch.setattr(
        launch_export, "certify_conditional_observed_dataset_scope", lambda *args: scope
    )
    monkeypatch.setattr(
        launch_export, "_reconstruct_calculations", lambda *args: dict(reconstruction)
    )
    monkeypatch.setattr(
        launch_export, "build_launch_entities", lambda *a, **k: entities
    )
    monkeypatch.setattr(
        launch_export, "build_launch_retained", lambda *a, **k: retained
    )
    # No fake activation decision is generated: science is outside this transport
    # unit and the summary is explicitly withheld by the mocked decision.
    monkeypatch.setattr(launch_export, "_activation", lambda *args: object())
    monkeypatch.setattr(
        launch_export,
        "assess_joint_metric_activation",
        lambda *a, **k: SimpleNamespace(status="withheld"),
    )

    def export(*args, **kwargs):  # type: ignore[no-untyped-def]
        reference = args[3]
        dataset = b'{"explicit-test-fixture":"not scientific data"}'
        manifest = {
            "scientificEvidence": {
                "storage_reference": reference.storage_reference,
                "sha256": reference.sha256,
                "byte_length": reference.byte_length,
                "schema_version": reference.schema_version,
            },
            "observationCounts": {metric: 0 for metric in CANDIDATE_METRIC_IDS},
            "periods": [],
            "uiShards": kwargs["ui_shards"].metadata,
        }
        return AtlasDatasetExport(dataset, json.dumps(manifest).encode())

    sink = Mock(side_effect=export)
    monkeypatch.setattr(launch_export, "build_atlas_dataset", sink)
    return retained, sink


def test_final_asset_transport_is_deterministic_and_recoverable(
    measured_launch, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    retained, sink = _transport_stubs(monkeypatch, measured_launch)
    generated = measured_launch.sessions[0].measurement_finished_at + timedelta(
        seconds=1
    )
    with bounded_build_verification_cache():
        first = launch_export.build_launch_export(
            measured_launch, geographic_views=(), generated_at=generated
        )
        second = launch_export.build_launch_export(
            measured_launch, geographic_views=(), generated_at=generated
        )
    assert first == second
    assert sink.call_count == 2
    assert gzip.decompress(first.scientific_evidence_bytes) == retained.content
    manifest = json.loads(first.manifest_bytes)
    ref = manifest["scientificEvidence"]
    assert ref["sha256"] == hashlib.sha256(first.scientific_evidence_bytes).hexdigest()
    assert ref["byte_length"] == len(first.scientific_evidence_bytes)
    assert manifest["scientificEvidenceFormat"]["decodedSha256"] == retained.sha256
    assert manifest["scientificEvidenceFormat"]["decodedBytes"] == retained.byte_length
    assert manifest["unavailableEntityFacts"] == {"fixture_unknown_location": 1}
    assert manifest["launchValidation"]["scientificPositiveClaim"] is False
    assert first.summary["jointGate"] == "withheld"
    assert first.summary["totalProductionBytes"] == sum(
        len(content) for _, _, content in first.assets
    )
    assert {path for _, path, _ in first.assets} == {
        "manifest.json",
        "atlas-dataset.json",
        "scientific-evidence.json.gz",
        "ui-index.json.gz",
    }


def test_transport_bounds_fail_without_truncating_entities_or_evidence(
    measured_launch, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    _, sink = _transport_stubs(monkeypatch, measured_launch)
    monkeypatch.setattr(launch_export, "MAX_EVIDENCE_BYTES", 1)
    generated = measured_launch.sessions[0].measurement_finished_at + timedelta(
        seconds=1
    )
    with (
        bounded_build_verification_cache(),
        pytest.raises(CertificationError, match="no evidence was truncated"),
    ):
        launch_export.build_launch_export(
            measured_launch, geographic_views=(), generated_at=generated
        )
    sink.assert_not_called()
