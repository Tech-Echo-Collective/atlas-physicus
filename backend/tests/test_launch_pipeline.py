"""Offline orchestration fixtures: no providers or private real state read."""

import gzip
import hashlib
import json
import pickle
import runpy
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from test_launch_years import captured_fixture

from physics_atlas_api import launch_pipeline
from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.launch_capture import FetchedLaunchPage
from physics_atlas_api.certification.years import (
    CONDITIONAL_OBSERVED_SOURCE_YEAR_RULE_VERSION,
    source_quality_certification,
)
from physics_atlas_api.launch_build import _write_checkpoint


def test_private_root_metadata_guard() -> None:
    # Mock metadata avoids creating a second physical build root.
    root, resolved = Mock(spec=Path), Mock(spec=Path)
    root.resolve.return_value = resolved
    root.is_symlink.return_value = False
    resolved.parent = Path("/private/tmp")
    resolved.name = "atlas-live-launch.synthetic-test-only"
    resolved.is_dir.return_value = True
    resolved.stat.return_value = SimpleNamespace(st_mode=0o700)
    assert launch_pipeline._private_root(root) is resolved
    for attribute, value in (
        ("parent", Path("/unrelated")),
        ("name", "another-project"),
    ):
        previous = getattr(resolved, attribute)
        setattr(resolved, attribute, value)
        with pytest.raises(ValueError, match="private ephemeral root"):
            launch_pipeline._private_root(root)
        setattr(resolved, attribute, previous)
    root.is_symlink.return_value = True
    with pytest.raises(ValueError, match="private ephemeral root"):
        launch_pipeline._private_root(root)
    root.is_symlink.return_value = False
    resolved.stat.return_value = SimpleNamespace(st_mode=0o755)
    with pytest.raises(ValueError, match="private ephemeral root"):
        launch_pipeline._private_root(root)


def test_checkpoint_read_refuses_escape_links_and_corruption(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="private ephemeral root"):
        launch_pipeline._private_root(tmp_path)
    fixture = tmp_path / "fixture.pickle.gz"
    _write_checkpoint(tmp_path, fixture, {"synthetic-test-only": 42})
    assert launch_pipeline._load(tmp_path, fixture.name) == {"synthetic-test-only": 42}
    (tmp_path / "link.pickle.gz").symlink_to(fixture)
    for name in ("link.pickle.gz", "missing.pickle.gz", "../outside.pickle.gz"):
        with pytest.raises(ValueError, match="checkpoint missing or outside"):
            launch_pipeline._load(tmp_path, name)
    broken = tmp_path / "corrupt.pickle.gz"
    broken.write_bytes(b"explicit corrupt test fixture")
    with pytest.raises((OSError, EOFError, pickle.UnpicklingError)):
        launch_pipeline._load(tmp_path, broken.name)


@pytest.fixture(scope="module")
def source_inputs():  # type: ignore[no-untyped-def]
    return {
        year: captured_fixture(year=year, record_offset=(year - 2018) * 10)
        for year in range(2018, 2024)
    }


@pytest.fixture
def prepared_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_inputs):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(launch_pipeline, "_private_root", lambda root: root)
    original_load = launch_pipeline._load
    calls: list[str] = []

    def load(root: Path, name: str) -> object:
        if name.startswith("source-"):
            calls.append(name)
            year = int(name.removeprefix("source-").removesuffix(".pickle.gz"))
            captured, _, attribution = source_inputs[year]
            return captured, attribution
        return original_load(root, name)

    monkeypatch.setattr(launch_pipeline, "_load", load)
    monkeypatch.setattr(launch_pipeline, "_progress", lambda *args, **kwargs: None)
    launch_pipeline.prepare(tmp_path)
    assert calls == [f"source-{year}.pickle.gz" for year in range(2018, 2024)]
    result = original_load(tmp_path, "prepared-launch.pickle.gz")
    assert isinstance(result, launch_pipeline.PreparedLaunch)
    return result


def test_prepare_preserves_quality_and_freezes_exact_shared_ids(
    prepared_launch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    assert len(prepared_launch.source_years) == 12
    assert len(prepared_launch.canonical.papers) == 12
    assert {year.rule_version for year in prepared_launch.source_years} == {
        CONDITIONAL_OBSERVED_SOURCE_YEAR_RULE_VERSION
    }
    assert all(year.state == "certified" for year in prepared_launch.source_years)
    assert all(
        source_quality_certification(year).state == "insufficient_evidence"
        for year in prepared_launch.source_years
    )
    first, second = prepared_launch.frozen_populations
    assert (
        first.measurement_population.provider_to_canonical
        == second.measurement_population.provider_to_canonical
    )
    assert len(first.measurement_population.provider_to_canonical) == 12
    assert first.frozen_at >= max(year.cutoff for year in first.source_years)
    assert first.frozen_at == second.frozen_at
    summaries = json.loads((tmp_path / "prepared-launch-summary.json").read_text())
    assert len(summaries) == 12
    assert all(
        row["sourceQualityState"] == "insufficient_evidence" for row in summaries
    )
    with pytest.raises(ValueError, match="already exists"):
        launch_pipeline.prepare(tmp_path)


def test_cli_uses_stable_module_entry_and_checkpoint_class(
    prepared_launch, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    assert prepared_launch.__class__.__module__ == "physics_atlas_api.launch_pipeline"
    restored = pickle.loads(pickle.dumps(prepared_launch))  # noqa: S301 -- own fixture only
    assert restored.__class__ is launch_pipeline.PreparedLaunch
    assert restored.source_years == prepared_launch.source_years
    entry = Mock()
    monkeypatch.setattr(launch_pipeline, "main", entry)
    with pytest.warns(RuntimeWarning, match="found in sys.modules"):
        runpy.run_module(
            "physics_atlas_api.launch_pipeline", run_name="__main__", alter_sys=True
        )
    entry.assert_called_once_with()


@pytest.mark.parametrize(
    "stage,name",
    [
        ("prepare", "prepared-launch-summary.json"),
        ("prepare", "prepared-launch.pickle.gz"),
        ("citations", "measured-citations.pickle.gz"),
    ],
)
def test_existing_lineage_refused_before_fetch_or_overwrite(
    stage: str, name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(launch_pipeline, "_private_root", lambda root: root)
    existing = tmp_path / name
    existing.write_bytes(b"retained synthetic proof; never overwrite")
    load = Mock(return_value=Mock(spec=launch_pipeline.PreparedLaunch))
    transport = Mock(side_effect=AssertionError("guard must precede fetch"))
    monkeypatch.setattr(launch_pipeline, "_load", load)
    monkeypatch.setattr(launch_pipeline, "LaunchTransport", transport)
    action = (
        launch_pipeline.prepare
        if stage == "prepare"
        else launch_pipeline.capture_citations
    )
    with pytest.raises(ValueError, match="already exists"):
        action(tmp_path)
    if stage == "prepare":
        load.assert_not_called()
    transport.assert_not_called()
    assert existing.read_bytes() == b"retained synthetic proof; never overwrite"


def fake_transport(prepared, *, corrupt_membership=False):  # type: ignore[no-untyped-def]
    population = prepared.frozen_populations[0]
    dates = {
        item.paper_id: item.publication_date.isoformat()
        for item in population.paper_projections
    }
    pairs = dict(population.measurement_population.provider_to_canonical)
    captured_urls: list[str] = []
    receipts: list[dict[str, object]] = []
    started = population.frozen_at + timedelta(seconds=1)

    def fetch(uri: str) -> FetchedLaunchPage:
        captured_urls.append(uri)
        parameters = parse_qs(urlsplit(uri).query)
        assert parameters["page"] == ["1"] and parameters["size"] == ["250"]
        assert "citation_count_without_self_citations" in parameters["fields"][0]
        hits = []
        for index, (provider_id, paper_id) in enumerate(pairs.items()):
            metadata = {
                "control_number": int(provider_id),
                "preprint_date": dates[paper_id],
                "document_type": ["article"],
                "inspire_categories": [{"term": "Theory-Nucl"}],
                "citation_count": index + 2,
            }
            if index != 1:
                metadata["citation_count_without_self_citations"] = index
            hits.append({"id": provider_id, "metadata": metadata})
        if corrupt_membership:
            hits[-1]["id"] = "999999999"
            hits[-1]["metadata"]["control_number"] = 999999999
        payload = json.dumps(
            {"hits": {"total": len(hits), "hits": hits}, "links": {}}
        ).encode()
        receipts.append(
            {
                "uri": uri,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "requestedAt": started.isoformat(),
                "receivedAt": (started + timedelta(seconds=2)).isoformat(),
            }
        )
        return FetchedLaunchPage(uri, started, started + timedelta(seconds=2), payload)

    return SimpleNamespace(
        fetch=fetch,
        receipts=receipts,
        client=SimpleNamespace(close=Mock()),
        captured_urls=captured_urls,
        started=started,
    )


def test_capture_keeps_exact_ids_timestamps_and_missing_not_zero(
    prepared_launch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    transport = fake_transport(prepared_launch)
    monkeypatch.setattr(launch_pipeline, "LaunchTransport", lambda: transport)
    launch_pipeline.capture_citations(tmp_path)
    with gzip.open(tmp_path / "measured-citations.pickle.gz", "rb") as stream:
        sessions = pickle.load(stream)  # noqa: S301 -- own test output only
    assert len(sessions) == 2 and len(sessions[0].pages) == 1
    assert sessions[0].pages == sessions[1].pages
    page = sessions[0].pages[0]
    assert page.requested_at == transport.started
    assert page.received_at == transport.started + timedelta(seconds=2)
    rows = page.records
    assert {item.source_record_id for item in rows} == {
        item[0]
        for item in prepared_launch.frozen_populations[
            0
        ].measurement_population.provider_to_canonical
    }
    counts = [item.non_self_citation_count for item in rows]
    assert counts[0] == 0 and counts[1] is None
    assert len(counts) == 12
    receipts = tuple(tmp_path.glob("citation-acquisition-receipts-*.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text()) == transport.receipts
    transport.client.close.assert_called_once()
    assert len(transport.captured_urls) == 1


def test_wrong_membership_never_writes_measured_checkpoint(
    prepared_launch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    transport = fake_transport(prepared_launch, corrupt_membership=True)
    monkeypatch.setattr(launch_pipeline, "LaunchTransport", lambda: transport)
    with pytest.raises((CertificationError, ValueError)):
        launch_pipeline.capture_citations(tmp_path)
    assert not (tmp_path / "measured-citations.pickle.gz").exists()
    assert len(tuple(tmp_path.glob("citation-acquisition-receipts-*.json"))) == 1
    transport.client.close.assert_called_once()


def test_failed_citation_attempt_can_retry_without_overwriting_any_receipt(
    prepared_launch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    legacy = tmp_path / "citation-acquisition-receipts.json"
    legacy.write_bytes(b"[]")
    failed = fake_transport(prepared_launch, corrupt_membership=True)
    successful = fake_transport(prepared_launch)
    transports = iter((failed, successful))
    factory = Mock(side_effect=lambda: next(transports))
    monkeypatch.setattr(launch_pipeline, "LaunchTransport", factory)
    with pytest.raises((CertificationError, ValueError)):
        launch_pipeline.capture_citations(tmp_path)
    first = tuple(tmp_path.glob("citation-acquisition-receipts-*.json"))
    assert len(first) == 1
    original_bytes = first[0].read_bytes()
    assert json.loads(original_bytes) == failed.receipts
    assert not (tmp_path / "measured-citations.pickle.gz").exists()

    launch_pipeline.capture_citations(tmp_path)
    assert len(tuple(tmp_path.glob("citation-acquisition-receipts-*.json"))) == 2
    assert first[0].read_bytes() == original_bytes and legacy.read_bytes() == b"[]"
    restored = launch_pipeline._load(tmp_path, "measured-citations.pickle.gz")
    assert restored[0].pages[0].requested_at == successful.started
    assert restored[0].frozen_population == (
        prepared_launch.frozen_populations[0].measurement_population
    )
    # A successfully completed session, unlike a failure receipt, still stops
    # reacquisition before any additional transport is constructed.
    with pytest.raises(ValueError, match="already exists"):
        launch_pipeline.capture_citations(tmp_path)
    assert factory.call_count == 2
    failed.client.close.assert_called_once()
    successful.client.close.assert_called_once()


def test_batch_dispatch_is_exact_and_reuses_pages_for_both_existing_certifiers(
    prepared_launch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    # Pure orchestration boundary only. Actual parser/session science is exercised
    # above with typed 12-paper fixtures; these mocks are never a scientific proof.
    pairs = tuple((str(index), f"test-paper-{index}") for index in range(1, 252))
    inventory = SimpleNamespace(provider_to_canonical=pairs)
    population = SimpleNamespace(
        measurement_population=inventory, __post_init__=lambda: None
    )
    prepared = replace(prepared_launch, frozen_populations=(population, population))
    monkeypatch.setattr(launch_pipeline, "_load", lambda *_: prepared)
    calls: list[dict[str, object]] = []
    started = prepared_launch.frozen_populations[0].frozen_at + timedelta(seconds=1)

    def fetch(uri: str) -> FetchedLaunchPage:
        return FetchedLaunchPage(uri, started, started + timedelta(seconds=1), b"test")

    def capture(payload: bytes, **kwargs):  # type: ignore[no-untyped-def]
        assert payload == b"test"
        calls.append(kwargs)
        return SimpleNamespace(records=())

    session = Mock(
        side_effect=lambda pages, _: SimpleNamespace(
            pages=pages,
            measurement_started_at=started,
            measurement_finished_at=started + timedelta(seconds=1),
        )
    )
    write = Mock(return_value=0)
    transport = SimpleNamespace(
        fetch=fetch, receipts=[], client=SimpleNamespace(close=Mock())
    )
    monkeypatch.setattr(launch_pipeline, "LaunchTransport", lambda: transport)
    monkeypatch.setattr(launch_pipeline, "capture_citation_session_page", capture)
    monkeypatch.setattr(launch_pipeline, "CitationMeasurementSession", session)
    monkeypatch.setattr(launch_pipeline, "_write_checkpoint", write)
    launch_pipeline.capture_citations(tmp_path)
    assert [len(call["expected_source_ids"]) for call in calls] == [250, 1]
    assert tuple(
        identifier for call in calls for identifier in call["expected_source_ids"]
    ) == tuple(key for key, _ in pairs)
    assert all(
        dict(call["canonical_paper_ids"])
        == dict(pairs[index * 250 : (index + 1) * 250])
        for index, call in enumerate(calls)
    )
    assert all(
        call["requested_at"] == started
        and call["received_at"] == started + timedelta(seconds=1)
        for call in calls
    )
    assert session.call_count == 2
    assert session.call_args_list[0].args == session.call_args_list[1].args
    write.assert_called_once()
    transport.client.close.assert_called_once()


def test_calculation_preserves_unsupported_windows_and_never_fabricates_scores(
    prepared_launch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """Tiny 12-paper fixture cannot pass the unchanged scientific minimums."""
    transport = fake_transport(prepared_launch)
    monkeypatch.setattr(launch_pipeline, "LaunchTransport", lambda: transport)
    launch_pipeline.capture_citations(tmp_path)

    class AfterMeasuredWindow(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            return transport.started + timedelta(seconds=10)

    monkeypatch.setattr(launch_pipeline, "datetime", AfterMeasuredWindow)
    launch_pipeline.calculate(tmp_path)
    calculated = launch_pipeline._load(tmp_path, "calculated-launch.pickle.gz")
    assert isinstance(calculated, launch_pipeline.CalculatedLaunch)
    assert calculated.prepared == prepared_launch
    assert not any(item.value is not None for item in calculated.observations)
    assert calculated.diagnostics
    assert calculated.diagnostics[0]["entityType"] == "country"
    summary = json.loads((tmp_path / "calculated-launch-summary.json").read_text())
    assert summary["numericObservationCounts"] == {}
    assert summary["coLocatedFiveMetricGroups"] == 0
    assert summary["availablePeriods"] == []
    # The actual measurement distinguishes missing self-citation evidence from zero.
    counts = [
        item.non_self_citation_count for item in calculated.sessions[0].pages[0].records
    ]
    assert counts[0] == 0 and counts[1] is None
    with pytest.raises(ValueError, match="already exists"):
        launch_pipeline.calculate(tmp_path)


def test_calculation_rejects_non_typed_sessions_before_any_calculation(
    prepared_launch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    original = launch_pipeline._load
    monkeypatch.setattr(
        launch_pipeline,
        "_load",
        lambda root, name: (
            ({"synthetic": "not a citation proof"},)
            if name == "measured-citations.pickle.gz"
            else original(root, name)
        ),
    )
    with pytest.raises(CertificationError, match="measured sessions required"):
        launch_pipeline.calculate(tmp_path)
    assert not (tmp_path / "calculated-launch.pickle.gz").exists()
