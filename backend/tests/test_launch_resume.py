"""Offline page interruption/resume, integrity and disk-budget proofs."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from test_launch_capture import NOW, PLAN, page_payload

from physics_atlas_api import launch_build
from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.launch_attribution import LaunchAttributionResult
from physics_atlas_api.certification.launch_capture import (
    CompletedLaunchPage,
    FetchedLaunchPage,
    collect_launch_year,
)
from physics_atlas_api.connectors.inspire import InspireConnector


def _fetch(uri: str) -> FetchedLaunchPage:
    page = int(parse_qs(urlsplit(uri).query)["page"][0])
    return FetchedLaunchPage(uri, NOW, NOW, page_payload([page], 3))


def _pages() -> tuple[CompletedLaunchPage, ...]:
    pages: list[CompletedLaunchPage] = []
    collect_launch_year(
        PLAN,
        connector=InspireConnector(Mock(), "https://inspirehep.net/api"),
        fetch=_fetch,
        request_page_size=1,
        page_completed=pages.append,
    )
    return tuple(pages)


def _results(page: CompletedLaunchPage) -> tuple[LaunchAttributionResult, ...]:
    return tuple(
        LaunchAttributionResult(item.reference, None, (), None, "needs_review", ())
        for item in page.occurrences
    )


def test_interrupted_page_resumes_only_completed_inputs_and_keeps_exact_result() -> (
    None
):
    pages: list[CompletedLaunchPage] = []
    connector = InspireConnector(Mock(), "https://inspirehep.net/api")

    def interrupted(record, reference) -> None:  # type: ignore[no-untyped-def]
        if reference.source_record_id == "2":
            raise RuntimeError("interrupted current page")

    with pytest.raises(RuntimeError, match="interrupted"):
        collect_launch_year(
            PLAN,
            connector=connector,
            fetch=_fetch,
            request_page_size=1,
            process_record=interrupted,
            page_completed=pages.append,
        )
    assert len(pages) == 1
    processed: list[str] = []
    probes: list[str] = []

    def probe(uri: str) -> FetchedLaunchPage:
        probes.append(uri)
        return _fetch(uri)

    resumed = collect_launch_year(
        PLAN,
        connector=connector,
        fetch=_fetch,
        request_page_size=1,
        resume_pages=tuple(pages),
        resume_fetch=probe,
        process_record=lambda record, ref: processed.append(ref.source_record_id),
    )
    original = collect_launch_year(
        PLAN,
        connector=connector,
        fetch=_fetch,
        request_page_size=1,
    )
    assert resumed == original
    assert processed == ["2", "3"] and len(probes) == 1


@pytest.mark.parametrize("failure", ["total", "order", "plan", "size", "gap"])
def test_resume_rejects_incompatible_or_changed_inventory(failure: str) -> None:
    pages = _pages()
    plan = (
        replace(PLAN, dataset_version="another-version") if failure == "plan" else PLAN
    )
    saved = (pages[1],) if failure == "gap" else pages[:1]

    def probe(uri: str) -> FetchedLaunchPage:
        return FetchedLaunchPage(
            uri,
            NOW,
            NOW,
            page_payload(
                [7 if failure == "order" else 1], 4 if failure == "total" else 3
            ),
        )

    with pytest.raises(CertificationError):
        collect_launch_year(
            plan,
            connector=InspireConnector(Mock(), "https://inspirehep.net/api"),
            fetch=_fetch,
            request_page_size=2 if failure == "size" else 1,
            resume_pages=saved,
            resume_fetch=probe,
        )


def test_complete_checkpoint_still_rechecks_total_without_reprocessing() -> None:
    processed = Mock()
    with pytest.raises(CertificationError, match="changed"):
        collect_launch_year(
            PLAN,
            connector=InspireConnector(Mock(), "https://inspirehep.net/api"),
            fetch=_fetch,
            request_page_size=1,
            resume_pages=_pages(),
            process_record=processed,
            resume_fetch=lambda uri: FetchedLaunchPage(
                uri, NOW, NOW, page_payload([1], 4)
            ),
        )
    processed.assert_not_called()


def test_compact_page_roundtrip_preserves_attributions_and_never_overwrites(
    tmp_path: Path,
) -> None:
    page = _pages()[0]
    results = _results(page)
    path = launch_build._write_page_checkpoint(tmp_path, page, results)
    assert launch_build._load_page_checkpoints(
        tmp_path, year=2020, dataset_version=PLAN.dataset_version, page_size=1
    ) == ((page,), results)
    with pytest.raises(ValueError, match="never overwrite"):
        launch_build._write_page_checkpoint(tmp_path, page, results)
    assert len(tuple(tmp_path.iterdir())) == 1
    assert path.stat().st_size > 0


def test_checksum_failure_precedes_deserialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = _pages()[0]
    path = launch_build._write_page_checkpoint(tmp_path, page, _results(page))
    content = path.read_bytes()
    path.write_bytes(content[:-1] + bytes((content[-1] ^ 1,)))
    forbidden = Mock(side_effect=AssertionError("must not deserialize corrupt state"))
    monkeypatch.setattr(launch_build.pickle, "loads", forbidden)
    with pytest.raises(ValueError, match="checksum"):
        launch_build._load_page_checkpoints(
            tmp_path, year=2020, dataset_version=PLAN.dataset_version, page_size=1
        )
    forbidden.assert_not_called()


@pytest.mark.parametrize("failure", ["version", "size", "gap", "symlink"])
def test_disk_checkpoint_rejects_incompatible_scope(
    tmp_path: Path, failure: str
) -> None:
    page = _pages()[1 if failure == "gap" else 0]
    path = launch_build._write_page_checkpoint(tmp_path, page, _results(page))
    if failure == "symlink":
        retained = tmp_path / "retained-original"
        path.rename(retained)
        path.symlink_to(retained)
    with pytest.raises(ValueError):
        launch_build._load_page_checkpoints(
            tmp_path,
            year=2020,
            dataset_version="other" if failure == "version" else PLAN.dataset_version,
            page_size=2 if failure == "size" else 1,
        )


@pytest.mark.parametrize("failure", ["budget", "publish"])
def test_page_write_failure_leaves_no_partial_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    page = _pages()[0]
    if failure == "budget":
        monkeypatch.setattr(launch_build, "MAX_EPHEMERAL_BYTES", 100_000_001)
    else:
        monkeypatch.setattr(
            launch_build.os, "link", Mock(side_effect=OSError("interrupted"))
        )
    with pytest.raises((RuntimeError, OSError)):
        launch_build._write_page_checkpoint(tmp_path, page, _results(page))
    assert not tuple(tmp_path.iterdir())


def test_attribution_reference_cannot_be_attached_to_another_page(
    tmp_path: Path,
) -> None:
    pages = _pages()
    with pytest.raises(ValueError, match="inventory"):
        launch_build._write_page_checkpoint(tmp_path, pages[0], _results(pages[1]))


def test_failed_attempts_keep_independent_receipts_and_allow_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "atlas-live-launch.fixture"
    root.mkdir()
    legacy = root / "acquisition-receipts-2020.json"
    legacy.write_text("[]", encoding="utf-8")
    # Keep this wholly offline and within pytest's owner-supplied scratch root.
    real_path = Path
    monkeypatch.setattr(
        launch_build,
        "Path",
        lambda value: tmp_path if value == "/private/tmp" else real_path(value),
    )
    transports = []

    def transport() -> Mock:
        value = Mock()
        value.receipts = [{"attempt": len(transports) + 1}]
        value.fetch.side_effect = RuntimeError("offline interruption")
        transports.append(value)
        return value

    monkeypatch.setattr(launch_build, "LaunchTransport", transport)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="offline interruption"):
            launch_build.collect(
                root=root, years=(2020,), dataset_version=PLAN.dataset_version
            )
    attempt_files = sorted(root.glob("acquisition-receipts-2020-*.json"))
    assert len(attempt_files) == 2 and legacy.read_text() == "[]"
    assert {json.loads(path.read_text())[0]["attempt"] for path in attempt_files} == {
        1,
        2,
    }
    for value in transports:
        value.client.close.assert_called_once()
