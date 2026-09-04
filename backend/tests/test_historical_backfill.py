import hashlib
import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self
from urllib.parse import parse_qs, urlencode, urlparse

import pytest

from physics_atlas_api.backfill import (
    ARXIV_QUERY_VERSION,
    BACKFILL_SCOPE,
    BACKFILL_YEARS,
    COND_MAT_HISTORICAL_BACKFILL,
    INSPIRE_QUERY_VERSION,
    LEGACY_INSPIRE_QUERY_VERSION,
    BackfillAcquisitionError,
    BackfillSafetyError,
    HistoricalPartition,
    PartitionResult,
    StoredPage,
    _exact_inspire_total,
    _json_checksum,
    _partition_result_from_dict,
    _print_progress,
    _write_partition_state,
    build_partitions,
    execute_backfill,
    load_partition_states,
    load_resume_manifest,
    run,
    validate_request,
)
from physics_atlas_api.config import Settings
from physics_atlas_api.connectors.acquisition import resolve_acquisition_scope
from physics_atlas_api.connectors.base import ConnectorConfigurationError


class HistoricalFixtureTransport:
    def __init__(
        self,
        provider: str,
        *,
        duplicate_year: int | None = None,
        fail_once: tuple[int, int] | None = None,
    ):
        self.provider = provider
        self.duplicate_year = duplicate_year
        self.fail_once = fail_once
        self.failed = False
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def close(self) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del url, params, headers
        raise AssertionError("historical raw acquisition preserves text envelopes")

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        del headers
        self.calls.append((url, params))
        if self.provider == "inspire":
            return self._inspire(url, params)
        return self._arxiv(params)

    def _inspire(self, url: str, params: dict[str, Any] | None) -> str:
        query = (
            str(params["q"])
            if params is not None
            else parse_qs(urlparse(url).query)["q"][0]
        )
        year_match = re.search(r"de >= (\d{4})-01-01", query)
        assert year_match is not None
        year = int(year_match.group(1))
        parsed_query = parse_qs(urlparse(url).query)
        page = int(parsed_query.get("page", ["1"])[0])
        page_size = int(
            str(params["size"])
            if params is not None
            else parsed_query.get("size", ["2"])[0]
        )
        if self.fail_once == (year, page) and not self.failed:
            self.failed = True
            raise RuntimeError("deterministic page failure")
        all_ids = [str(year * 100 + index) for index in (1, 2, 3)]
        start = (page - 1) * page_size
        identifiers = all_ids[start : start + page_size]
        next_link = None
        if start + len(identifiers) < len(all_ids):
            next_link = "https://inspire.test/api/literature?" + urlencode(
                {"q": query, "page": page + 1, "size": page_size}
            )
        return json.dumps(
            {
                "hits": {
                    "total": {"value": len(all_ids), "relation": "eq"},
                    "hits": [
                        {
                            "id": identifier,
                            "metadata": {
                                "control_number": int(identifier),
                                "earliest_date": f"{year}-01-01",
                                "titles": [{"title": f"Paper {identifier}"}],
                            },
                        }
                        for identifier in identifiers
                    ],
                },
                "links": {"next": next_link} if next_link else {},
            },
            sort_keys=True,
        )

    def _arxiv(self, params: dict[str, Any] | None) -> str:
        assert params is not None
        query = str(params["search_query"])
        year_match = re.search(r"submittedDate:\[(\d{4})", query)
        assert year_match is not None
        year = int(year_match.group(1))
        start = int(params["start"])
        page_size = int(params["max_results"])
        page = start // max(page_size, 1) + 1
        if self.fail_once == (year, page) and not self.failed:
            self.failed = True
            raise RuntimeError("deterministic page failure")
        all_ids = [
            f"{str(year)[2:]}01.00001",
            f"{str(year)[2:]}01.00002",
            f"{str(year)[2:]}01.00003",
        ]
        identifiers = all_ids[start : start + page_size]
        if self.duplicate_year == year and start > 0 and identifiers:
            identifiers[0] = all_ids[1]
        entries = "".join(
            f"""
            <entry>
              <id>https://arxiv.org/abs/{identifier}v1</id>
              <updated>{year}-01-01T00:00:00Z</updated>
              <published>{year}-01-01T00:00:00Z</published>
              <title>Paper {identifier}</title>
              <summary>Fixture</summary>
              <author><name>Fixture Author</name></author>
              <category term="hep-th"
                scheme="http://arxiv.org/schemas/atom" />
            </entry>
            """
            for identifier in identifiers
        )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
          <opensearch:totalResults>3</opensearch:totalResults>
          {entries}
        </feed>"""


class _OverLimitArxivTransport(HistoricalFixtureTransport):
    def _arxiv(self, params: dict[str, Any] | None) -> str:
        return (
            super()
            ._arxiv(params)
            .replace(
                "<opensearch:totalResults>3</opensearch:totalResults>",
                "<opensearch:totalResults>10000</opensearch:totalResults>",
            )
        )


def settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        fixture_mode=True,
        inspire_base_url="https://inspire.test/api",
        arxiv_base_url="https://arxiv.test/api/query",
    )


def partitions() -> tuple[HistoricalPartition, ...]:
    return build_partitions(
        inspire_base_url="https://inspire.test/api",
        arxiv_base_url="https://arxiv.test/api/query",
        inspire_page_size=2,
        arxiv_page_size=2,
    )


def cond_mat_partitions() -> tuple[HistoricalPartition, ...]:
    return build_partitions(
        scope=COND_MAT_HISTORICAL_BACKFILL.id,
        inspire_base_url="https://inspire.test/api",
        arxiv_base_url="https://arxiv.test/api/query",
        inspire_page_size=2,
        arxiv_page_size=2,
    )


def transports(
    *,
    duplicate_year: int | None = None,
    inspire_failure: tuple[int, int] | None = None,
) -> dict[str, HistoricalFixtureTransport]:
    return {
        "inspire": HistoricalFixtureTransport("inspire", fail_once=inspire_failure),
        "arxiv": HistoricalFixtureTransport("arxiv", duplicate_year=duplicate_year),
    }


def test_partitions_use_exact_fixed_scope_and_closed_year_queries() -> None:
    planned = partitions()

    assert INSPIRE_QUERY_VERSION == "hep-th-v1:inspire:earliest-record-date-v1"
    assert len(planned) == 12
    assert {(item.provider, item.year) for item in planned} == {
        (provider, year) for year in BACKFILL_YEARS for provider in ("inspire", "arxiv")
    }
    for item in planned:
        if item.provider == "inspire":
            assert item.query == (
                "document_type:article and subject:Theory-HEP and "
                f"de >= {item.year}-01-01 and de <= {item.year}-12-31"
            )
            assert item.query_version == INSPIRE_QUERY_VERSION
        else:
            assert item.query == (
                f"(cat:hep-th) AND submittedDate:[{item.year}01010000 "
                f"TO {item.year}12312359]"
            )
            assert item.query_version == ARXIV_QUERY_VERSION
        assert (
            item.query_checksum
            == hashlib.sha256(item.query.encode("utf-8")).hexdigest()
        )


def test_condensed_matter_trial_uses_exact_staging_only_provider_queries() -> None:
    planned = build_partitions(scope=COND_MAT_HISTORICAL_BACKFILL.id)

    assert len(planned) == 30
    assert {item.acquisition_scope for item in planned} == {"cond-mat-validation-v1"}
    assert [item.provider for item in planned[:6]] == ["inspire"] * 6
    assert [item.year for item in planned[:6]] == list(BACKFILL_YEARS)
    for item in planned:
        if item.provider == "inspire":
            assert item.query == (
                'document_type:article and subject:"Condensed Matter" and '
                f"de >= {item.year}-01-01 and de <= {item.year}-12-31"
            )
            assert item.query_version == (
                "cond-mat-validation-v1:inspire:earliest-record-date-v1"
            )
        else:
            boundaries = {
                "q1": ("0101", "0331"),
                "q2": ("0401", "0630"),
                "q3": ("0701", "0930"),
                "q4": ("1001", "1231"),
            }
            start, end = boundaries[item.segment]
            assert item.query == (
                f"(cat:cond-mat.*) AND submittedDate:[{item.year}{start}0000 "
                f"TO {item.year}{end}2359]"
            )
            assert item.query_version == (
                "cond-mat-validation-v1:arxiv:quarterly-submission-window-v2:"
                f"{item.segment}"
            )
            assert item.page_size == 100

    with pytest.raises(ConnectorConfigurationError, match="Unsupported"):
        resolve_acquisition_scope(COND_MAT_HISTORICAL_BACKFILL.id)


def test_condensed_matter_trial_rejects_an_unexpected_annual_arxiv_segment(
    tmp_path: Path,
) -> None:
    planned = list(cond_mat_partitions())
    q1_index = next(
        index
        for index, item in enumerate(planned)
        if item.provider == "arxiv" and item.year == 2020 and item.segment == "q1"
    )
    planned[q1_index] = replace(planned[q1_index], segment="annual")

    with pytest.raises(BackfillSafetyError, match="approved provider/year segments"):
        execute_backfill(
            "acquire",
            output=tmp_path / "invalid-segment",
            settings=settings(),
            partitions=planned,
            transports=transports(),
        )


def test_condensed_matter_segment_failure_resumes_in_its_own_state_directory(
    tmp_path: Path,
) -> None:
    output = tmp_path / "cond-resume"
    first_transports = transports()
    first_transports["arxiv"].fail_once = (2020, 2)
    first = execute_backfill(
        "acquire",
        output=output,
        settings=settings(),
        partitions=cond_mat_partitions(),
        transports=first_transports,
    )

    q1_first = next(
        item
        for item in first.partitions
        if item.partition.provider == "arxiv"
        and item.partition.year == 2020
        and item.partition.segment == "q1"
    )
    assert q1_first.complete is False
    assert q1_first.records_seen == 2
    assert list((output / "partition-state" / "arxiv" / "2020" / "q1").glob("*.json"))

    resumed_transports = transports()
    resumed = execute_backfill(
        "acquire",
        output=output,
        settings=settings(),
        partitions=cond_mat_partitions(),
        transports=resumed_transports,
    )

    assert resumed.successful is True
    q1_calls = [
        params
        for _url, params in resumed_transports["arxiv"].calls
        if params is not None and "202001010000" in str(params.get("search_query"))
    ]
    assert q1_calls == [
        {
            "search_query": (
                "(cat:cond-mat.*) AND submittedDate:[202001010000 TO 202003312359]"
            ),
            "start": 2,
            "max_results": 2,
            "sortBy": "submittedDate",
            "sortOrder": "ascending",
        }
    ]


def test_condensed_matter_segment_rejects_provider_total_at_offset_boundary(
    tmp_path: Path,
) -> None:
    result = execute_backfill(
        "acquire",
        output=tmp_path / "offset-boundary",
        settings=settings(),
        partitions=cond_mat_partitions(),
        transports={
            "inspire": HistoricalFixtureTransport("inspire"),
            "arxiv": _OverLimitArxivTransport("arxiv"),
        },
    )

    q1 = next(
        item
        for item in result.partitions
        if item.partition.provider == "arxiv"
        and item.partition.year == 2020
        and item.partition.segment == "q1"
    )
    assert q1.complete is False
    assert q1.records_seen == 0
    assert q1.error is not None
    assert "must remain below the provider offset boundary 10000" in q1.error

    raw = PartitionResult(q1.partition, expected_total=10_000).as_dict()
    with pytest.raises(BackfillSafetyError, match="provider offset boundary"):
        _partition_result_from_dict(raw, {q1.partition.id: q1.partition})


def test_condensed_matter_resume_metadata_rejects_segment_tampering() -> None:
    q1 = next(
        item
        for item in cond_mat_partitions()
        if item.provider == "arxiv" and item.year == 2020 and item.segment == "q1"
    )
    raw = {
        **PartitionResult(q1).as_dict(),
        "segment": "q2",
    }
    raw.pop("partition_checksum")
    raw["partition_checksum"] = _json_checksum(raw)

    with pytest.raises(BackfillSafetyError, match="metadata changed"):
        _partition_result_from_dict(raw, {q1.id: q1})


def test_annual_resume_metadata_rejects_an_explicit_segment_field() -> None:
    annual = partitions()[0]
    raw = {
        **PartitionResult(annual).as_dict(),
        "segment": "annual",
    }
    raw.pop("partition_checksum")
    raw["partition_checksum"] = _json_checksum(raw)

    with pytest.raises(BackfillSafetyError, match="metadata changed"):
        _partition_result_from_dict(raw, {annual.id: annual})


def test_same_rank_partition_state_conflict_fails_closed(tmp_path: Path) -> None:
    planned = cond_mat_partitions()
    q1 = next(
        item
        for item in planned
        if item.provider == "arxiv" and item.year == 2020 and item.segment == "q1"
    )
    for marker in ("a", "b"):
        checksum = marker * 64
        _write_partition_state(
            tmp_path,
            PartitionResult(
                partition=q1,
                expected_total=3,
                records_seen=1,
                seen_unique_ids=1,
                unique_ids_checksum="c" * 64,
                duplicate_count=0,
                page_count=1,
                terminal_status="failed",
                complete=False,
                pages=[
                    StoredPage(
                        page_number=1,
                        record_count=1,
                        checksum=checksum,
                        path=f"pages/arxiv/2020/{checksum}.xml",
                    )
                ],
                resume_checkpoint={"start": 1},
                error="fixture interruption",
            ),
        )

    with pytest.raises(BackfillSafetyError, match="same-rank partition states"):
        load_partition_states(tmp_path, planned)


def test_same_rank_manifest_and_partition_state_conflict_fails_closed(
    tmp_path: Path,
) -> None:
    output = tmp_path / "resume-conflict"
    planned = partitions()
    first = execute_backfill(
        "acquire",
        output=output,
        settings=settings(),
        partitions=planned,
        transports=transports(inspire_failure=(2020, 2)),
    )
    assert first.output_path is not None
    failed = next(
        item
        for item in first.partitions
        if item.partition.provider == "inspire" and item.partition.year == 2020
    )
    state_directory = output / "partition-state" / "inspire" / "2020"
    for path in state_directory.glob("*.json"):
        path.unlink()
    _write_partition_state(
        output,
        replace(failed, error="different same-progress failure evidence"),
    )
    retry_transports = transports()

    with pytest.raises(BackfillSafetyError, match="same-rank resume evidence"):
        execute_backfill(
            "acquire",
            output=output,
            settings=settings(),
            partitions=planned,
            transports=retry_transports,
            resume_manifest=first.output_path,
        )

    assert retry_transports["inspire"].calls == []
    assert retry_transports["arxiv"].calls == []


def test_inspire_count_requires_explicit_exact_relation() -> None:
    with pytest.raises(BackfillAcquisitionError, match="exact bounded result total"):
        _exact_inspire_total({"hits": {"total": {"value": 12}}})

    with pytest.raises(BackfillAcquisitionError, match="exact bounded result total"):
        _exact_inspire_total({"hits": {"total": {"value": 12, "relation": "gte"}}})


def test_cli_is_network_free_and_does_not_write_without_execute(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_transport(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("preview constructed a live transport")

    monkeypatch.setattr(
        "physics_atlas_api.backfill._provider_transport", forbidden_transport
    )

    assert run(["acquire", "--output", str(tmp_path / "unused")]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["executed"] is False
    assert output["acquisition_complete"] is False
    assert all(
        item["terminal_status"] == "not-executed" for item in output["partitions"]
    )
    assert not (tmp_path / "unused").exists()


def test_live_execution_rejects_nonofficial_provider_origins(tmp_path: Path) -> None:
    output = tmp_path / "blocked"

    with pytest.raises(BackfillSafetyError, match="official provider endpoint"):
        execute_backfill(
            "plan",
            output=output,
            settings=settings(),
            partitions=partitions(),
        )

    assert not output.exists()


def test_executed_plan_uses_only_one_count_page_per_partition(
    tmp_path: Path,
) -> None:
    fixture_transports = transports()
    result = execute_backfill(
        "plan",
        output=tmp_path / "plan",
        settings=settings(),
        now=datetime(2026, 8, 30, tzinfo=UTC),
        partitions=partitions(),
        transports=fixture_transports,
    )

    assert result.successful is True
    assert all(item.expected_total == 3 for item in result.partitions)
    assert all(item.page_count == 1 for item in result.partitions)
    assert all(item.terminal_status == "counted" for item in result.partitions)
    assert len(fixture_transports["inspire"].calls) == 6
    assert len(fixture_transports["arxiv"].calls) == 6
    assert all(call[1]["size"] == 1 for call in fixture_transports["inspire"].calls)  # type: ignore[index]
    assert all(
        call[1]["max_results"] == 1
        for call in fixture_transports["arxiv"].calls  # type: ignore[index]
    )


def test_partition_progress_is_stderr_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = execute_backfill(
        "plan",
        output=tmp_path / "progress",
        settings=settings(),
        partitions=partitions(),
        transports=transports(),
        progress=_print_progress,
    )

    assert result.successful is True
    captured = capsys.readouterr()
    assert captured.out == ""
    lines = captured.err.splitlines()
    assert len(lines) == 12
    assert lines[0] == (
        "mode=plan provider=inspire year=2020 status=counted seen=1 expected=3"
    )
    assert lines[-1] == (
        "mode=plan provider=arxiv year=2025 status=counted seen=1 expected=3"
    )


def test_acquisition_is_complete_content_addressed_and_deterministic(
    tmp_path: Path,
) -> None:
    fixed_time = datetime(2026, 8, 30, tzinfo=UTC)
    first = execute_backfill(
        "acquire",
        output=tmp_path / "first",
        settings=settings(),
        now=fixed_time,
        partitions=partitions(),
        transports=transports(),
    )
    second = execute_backfill(
        "acquire",
        output=tmp_path / "second",
        settings=settings(),
        now=fixed_time,
        partitions=partitions(),
        transports=transports(),
    )

    assert first.successful is True
    assert all(item.complete for item in first.partitions)
    assert all(item.expected_total == 3 for item in first.partitions)
    assert all(item.records_seen == 3 for item in first.partitions)
    assert all(item.seen_unique_ids == 3 for item in first.partitions)
    assert all(item.duplicate_count == 0 for item in first.partitions)
    assert all(item.page_count == 2 for item in first.partitions)
    assert first.as_dict()["manifest_checksum"] == second.as_dict()["manifest_checksum"]
    assert first.output_path is not None and first.output_path.is_file()
    page = first.partitions[0].pages[0]
    payload = (tmp_path / "first" / page.path).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == page.checksum


def test_failed_partition_resumes_without_refetching_prior_or_complete_pages(
    tmp_path: Path,
) -> None:
    output = tmp_path / "resume"
    first_transports = transports(inspire_failure=(2020, 2))
    first = execute_backfill(
        "acquire",
        output=output,
        settings=settings(),
        now=datetime(2026, 8, 30, 1, tzinfo=UTC),
        partitions=partitions(),
        transports=first_transports,
    )
    failed = next(
        item
        for item in first.partitions
        if item.partition.provider == "inspire" and item.partition.year == 2020
    )
    assert failed.complete is False
    assert failed.terminal_status == "failed"
    assert failed.page_count == 1
    assert failed.resume_checkpoint is not None
    assert first.output_path is not None

    retry_transports = transports()
    resumed = execute_backfill(
        "acquire",
        output=output,
        settings=settings(),
        now=datetime(2026, 8, 30, 2, tzinfo=UTC),
        partitions=partitions(),
        transports=retry_transports,
        resume_manifest=first.output_path,
    )

    assert resumed.successful is True
    assert all(item.complete for item in resumed.partitions)
    assert len(retry_transports["inspire"].calls) == 1
    assert retry_transports["inspire"].calls[0][1] is None
    assert retry_transports["arxiv"].calls == []


def test_resume_rejects_tampered_page_before_any_provider_request(
    tmp_path: Path,
) -> None:
    output = tmp_path / "tampered"
    first = execute_backfill(
        "acquire",
        output=output,
        settings=settings(),
        partitions=partitions(),
        transports=transports(inspire_failure=(2020, 2)),
    )
    assert first.output_path is not None
    page = output / first.partitions[-1].pages[0].path
    page.write_text(page.read_text(encoding="utf-8") + " ", encoding="utf-8")
    retry_transports = transports()

    with pytest.raises(BackfillSafetyError, match="page checksum failed"):
        execute_backfill(
            "acquire",
            output=output,
            settings=settings(),
            partitions=partitions(),
            transports=retry_transports,
            resume_manifest=first.output_path,
        )

    assert retry_transports["inspire"].calls == []
    assert retry_transports["arxiv"].calls == []


def test_partition_state_resumes_when_final_manifest_is_unavailable(
    tmp_path: Path,
) -> None:
    output = tmp_path / "partition-state"
    first = execute_backfill(
        "acquire",
        output=output,
        settings=settings(),
        partitions=partitions(),
        transports=transports(inspire_failure=(2020, 2)),
    )
    assert first.output_path is not None
    first.output_path.unlink()
    retry_transports = transports()

    resumed = execute_backfill(
        "acquire",
        output=output,
        settings=settings(),
        partitions=partitions(),
        transports=retry_transports,
    )

    assert resumed.successful is True
    assert len(retry_transports["inspire"].calls) == 1
    assert retry_transports["inspire"].calls[0][1] is None
    assert retry_transports["arxiv"].calls == []


def _replace_inspire_query_label(value: dict[str, Any]) -> None:
    partition = value["partition"] if "partition" in value else value
    if partition["provider"] != "inspire":
        return
    partition["query_version"] = LEGACY_INSPIRE_QUERY_VERSION
    unsigned_partition = dict(partition)
    unsigned_partition.pop("partition_checksum", None)
    partition["partition_checksum"] = _json_checksum(unsigned_partition)


def test_corrected_query_label_reopens_exact_legacy_manifest(tmp_path: Path) -> None:
    output = tmp_path / "legacy-manifest"
    acquired = execute_backfill(
        "acquire",
        output=output,
        settings=settings(),
        partitions=partitions(),
        transports=transports(),
    )
    assert acquired.output_path is not None
    payload = json.loads(acquired.output_path.read_text(encoding="utf-8"))
    for partition in payload["partitions"]:
        _replace_inspire_query_label(partition)
    unsigned = dict(payload)
    unsigned.pop("manifest_checksum", None)
    payload["manifest_checksum"] = _json_checksum(unsigned)
    legacy_manifest = output / "manifests" / f"{payload['manifest_checksum']}.json"
    legacy_manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    restored = load_resume_manifest(
        legacy_manifest,
        output=output,
        partitions=partitions(),
    )

    assert len(restored) == 12
    assert all(
        result.partition.query_version == INSPIRE_QUERY_VERSION
        for result in restored.values()
        if result.partition.provider == "inspire"
    )


def test_corrected_query_label_reopens_exact_legacy_partition_state(
    tmp_path: Path,
) -> None:
    output = tmp_path / "legacy-partition-state"
    acquired = execute_backfill(
        "acquire",
        output=output,
        settings=settings(),
        partitions=partitions(),
        transports=transports(),
    )
    assert acquired.successful is True
    state_directory = output / "partition-state" / "inspire" / "2020"
    state_path = next(state_directory.glob("*.json"))
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    _replace_inspire_query_label(payload)
    unsigned = dict(payload)
    unsigned.pop("state_checksum", None)
    payload["state_checksum"] = _json_checksum(unsigned)
    legacy_state = state_directory / f"{payload['state_checksum']}.json"
    legacy_state.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    state_path.unlink()

    restored = load_partition_states(output, partitions())

    assert restored["hep-th-v1:inspire:2020"].partition.query_version == (
        INSPIRE_QUERY_VERSION
    )


def test_legacy_query_label_does_not_relax_other_partition_identity(
    tmp_path: Path,
) -> None:
    output = tmp_path / "legacy-tamper"
    acquired = execute_backfill(
        "acquire",
        output=output,
        settings=settings(),
        partitions=partitions(),
        transports=transports(),
    )
    assert acquired.output_path is not None
    payload = json.loads(acquired.output_path.read_text(encoding="utf-8"))
    _replace_inspire_query_label(payload["partitions"][0])
    payload["partitions"][0]["query"] = "document_type:article"
    unsigned_partition = dict(payload["partitions"][0])
    unsigned_partition.pop("partition_checksum", None)
    payload["partitions"][0]["partition_checksum"] = _json_checksum(unsigned_partition)
    unsigned = dict(payload)
    unsigned.pop("manifest_checksum", None)
    payload["manifest_checksum"] = _json_checksum(unsigned)
    tampered_manifest = output / "manifests" / f"{payload['manifest_checksum']}.json"
    tampered_manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(BackfillSafetyError, match="partition metadata changed"):
        load_resume_manifest(
            tampered_manifest,
            output=output,
            partitions=partitions(),
        )


def test_duplicate_provider_records_fail_completeness_without_certification(
    tmp_path: Path,
) -> None:
    result = execute_backfill(
        "acquire",
        output=tmp_path / "duplicates",
        settings=settings(),
        partitions=partitions(),
        transports=transports(duplicate_year=2023),
    )
    duplicate = next(
        item
        for item in result.partitions
        if item.partition.provider == "arxiv" and item.partition.year == 2023
    )

    assert result.successful is False
    assert duplicate.expected_total == 3
    assert duplicate.records_seen == 3
    assert duplicate.seen_unique_ids == 2
    assert duplicate.duplicate_count == 1
    assert duplicate.terminal_status == "duplicate-records"
    assert duplicate.complete is False
    assert result.as_dict()["acquisition_complete"] is False


def test_scope_year_and_repository_output_safety(tmp_path: Path) -> None:
    with pytest.raises(BackfillSafetyError, match="unsupported historical scope"):
        validate_request(
            scope="all-physics",
            start_year=2020,
            end_year=2025,
            output=tmp_path / "out",
            execute=True,
        )
    with pytest.raises(BackfillSafetyError, match="fixed to the closed years"):
        build_partitions(start_year=2019, end_year=2025)

    fake_repository = tmp_path / "repository"
    with pytest.raises(BackfillSafetyError, match="outside the repository"):
        validate_request(
            scope=BACKFILL_SCOPE,
            start_year=2020,
            end_year=2025,
            output=fake_repository / "pipeline" / "data" / "backfill",
            execute=True,
            repo_root=fake_repository,
        )
