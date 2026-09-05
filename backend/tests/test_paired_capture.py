import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import pytest

from physics_atlas_api.capture_lineage import (
    CapturedTextResponse,
    HttpCaptureLineage,
    LineageProviderHttpTransport,
)
from physics_atlas_api.connectors.acquisition import SUPPORTED_ACQUISITION_SCOPES
from physics_atlas_api.paired_capture import (
    COND_MAT_TRIAL_SCOPE,
    DOWNSTREAM_TARGET_CAPS,
    HEP_TH_TRIAL_SCOPE,
    MANIFEST_VERSION,
    PAIR_ID,
    PairedCaptureSafetyError,
    PairedCaptureVerificationError,
    TrialScope,
    build_arxiv_query,
    build_inspire_query,
    build_trial_partitions,
    capture_plan,
    execute_paired_capture,
    validate_staging_output,
    verify_paired_capture_manifest,
)

CAPTURED_AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
COMPLETED_AT = CAPTURED_AT + timedelta(minutes=1)


def _checksum_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _resign_manifest(
    path: Path,
    value: dict[str, Any],
) -> Path:
    partitions = value["partitions"]
    assert isinstance(partitions, list)
    partition_checksums: list[str] = []
    for partition in partitions:
        assert isinstance(partition, dict)
        partition.pop("partition_checksum", None)
        partition["partition_checksum"] = _checksum_json(partition)
        partition_checksums.append(partition["partition_checksum"])
    value["partition_checksums"] = partition_checksums
    value["evidence_set_checksum"] = _checksum_json(partition_checksums)
    value.pop("manifest_checksum", None)
    checksum = _checksum_json(value)
    value["manifest_checksum"] = checksum
    destination = path.parent / f"{checksum}.json"
    destination.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


class PairedFixtureTransport:
    def __init__(
        self,
        provider: str,
        *,
        hep_total: int,
        cond_total: int,
        page_limit: int | None = None,
    ):
        self.provider = provider
        self.hep_total = hep_total
        self.cond_total = cond_total
        self.page_limit = page_limit
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_captured_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> CapturedTextResponse:
        del headers
        assert params is not None
        self.calls.append((url, params))
        query = str(params.get("q") or params.get("search_query"))
        is_cond_mat = "Condensed Matter" in query or "cond-mat" in query
        total = self.cond_total if is_cond_mat else self.hep_total
        if self.provider == "inspire":
            body = self._inspire(total)
        else:
            body = self._arxiv(
                total,
                start=int(params["start"]),
                maximum=int(params["max_results"]),
            )
        timestamp = CAPTURED_AT + timedelta(seconds=len(self.calls))
        request_url = f"{url}?{urlencode(params)}"
        return CapturedTextResponse(
            body=body,
            lineage=HttpCaptureLineage(
                request_started_at=timestamp,
                response_received_at=timestamp + timedelta(milliseconds=50),
                request_url=request_url,
                response_url=request_url,
                status_code=200,
                provider_date="Fri, 04 Sep 2026 12:00:00 GMT",
                etag='"fixture-etag"',
                last_modified="Fri, 04 Sep 2026 11:55:00 GMT",
                content_type=(
                    "application/json"
                    if self.provider == "inspire"
                    else "application/atom+xml"
                ),
            ),
        )

    @staticmethod
    def _inspire(total: int) -> str:
        identifiers = range(1, min(total, 250) + 1)
        return json.dumps(
            {
                "hits": {
                    "total": {"value": total, "relation": "eq"},
                    "hits": [
                        {
                            "id": str(identifier),
                            "metadata": {
                                "control_number": identifier,
                                "titles": [{"title": f"Paper {identifier}"}],
                            },
                        }
                        for identifier in identifiers
                    ],
                },
                "links": (
                    {"next": "https://inspire.test/api/literature?page=2"}
                    if total > 250
                    else {}
                ),
            },
            sort_keys=True,
        )

    def _arxiv(self, total: int, *, start: int, maximum: int) -> str:
        available = max(0, total - start)
        count = min(available, maximum)
        if self.page_limit is not None:
            count = min(count, self.page_limit)
        entries = "".join(
            f"""
            <entry>
              <id>https://arxiv.org/abs/2001.{index:05d}v1</id>
              <updated>2020-01-13T00:00:00Z</updated>
              <published>2020-01-13T00:00:00Z</published>
              <title>Paper {index}</title>
              <summary>Fixture evidence</summary>
              <author><name>Fixture Author</name></author>
              <category term="hep-th" />
            </entry>
            """
            for index in range(start + 1, start + count + 1)
        )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
          <opensearch:totalResults>{total}</opensearch:totalResults>
          {entries}
        </feed>"""


def fixture_partitions() -> tuple[Any, ...]:
    return build_trial_partitions(
        inspire_endpoint="https://inspire.test/api/literature",
        arxiv_endpoint="https://arxiv.test/api/query",
    )


def fixture_transports(
    *,
    inspire_hep: int = 2,
    inspire_cond: int = 1,
    arxiv_hep: int = 3,
    arxiv_cond: int = 201,
    arxiv_page_limit: int | None = None,
) -> dict[str, PairedFixtureTransport]:
    return {
        "inspire": PairedFixtureTransport(
            "inspire", hep_total=inspire_hep, cond_total=inspire_cond
        ),
        "arxiv": PairedFixtureTransport(
            "arxiv",
            hep_total=arxiv_hep,
            cond_total=arxiv_cond,
            page_limit=arxiv_page_limit,
        ),
    }


def test_fixed_pair_uses_exact_queries_caps_and_unregistered_scopes() -> None:
    partitions = build_trial_partitions()

    assert len(partitions) == 4
    assert build_inspire_query(HEP_TH_TRIAL_SCOPE) == (
        "document_type:article and subject:Theory-HEP and "
        "de >= 2020-01-13 and de <= 2020-01-19"
    )
    assert build_arxiv_query(HEP_TH_TRIAL_SCOPE) == (
        "(cat:hep-th) AND submittedDate:[202001130000 TO 202001192359]"
    )
    assert build_inspire_query(COND_MAT_TRIAL_SCOPE) == (
        'document_type:article and subject:"Condensed Matter" and '
        "de >= 2020-01-13 and de <= 2020-01-19"
    )
    assert build_arxiv_query(COND_MAT_TRIAL_SCOPE) == (
        "(cat:cond-mat.*) AND submittedDate:[202001130000 TO 202001192359]"
    )
    observed_caps = [
        (item.provider, item.caps.page_size, item.caps.maximum_pages)
        for item in partitions
    ]
    assert observed_caps == [
        ("inspire", 250, 1),
        ("arxiv", 100, 10),
        ("inspire", 250, 1),
        ("arxiv", 100, 10),
    ]
    assert HEP_TH_TRIAL_SCOPE.id not in SUPPORTED_ACQUISITION_SCOPES
    assert COND_MAT_TRIAL_SCOPE.id not in SUPPORTED_ACQUISITION_SCOPES
    assert set(SUPPORTED_ACQUISITION_SCOPES) == {"hep-th-v1"}


def test_unknown_or_modified_scope_cannot_build_a_query() -> None:
    changed = TrialScope(
        id=HEP_TH_TRIAL_SCOPE.id,
        atlas_field_id="hep-th",
        inspire_filter="subject:Experiment-HEP",
        arxiv_filter="cat:hep-ex",
    )
    with pytest.raises(PairedCaptureSafetyError, match="fixed paired trial"):
        build_inspire_query(changed)


def test_plan_is_pure_and_explicitly_non_production() -> None:
    plan = capture_plan()

    assert plan["pair_id"] == PAIR_ID
    assert plan["manifest_version"] == MANIFEST_VERSION
    assert plan["executed"] is False
    assert plan["staging_only"] is True
    assert plan["database_access"] is False
    assert plan["database_writes"] is False
    assert plan["production_scope_registration"] is False
    assert plan["public_metric_activation"] is False
    assert len(plan["partitions"]) == 4


def test_downstream_caps_fail_closed_without_prefix_truncation() -> None:
    DOWNSTREAM_TARGET_CAPS.validate(
        paper_lookups=400,
        institution_recids=250,
        child_ror_records=250,
        parent_ror_records=250,
    )
    with pytest.raises(PairedCaptureSafetyError, match="shrink the trial"):
        DOWNSTREAM_TARGET_CAPS.validate(
            paper_lookups=401,
            institution_recids=0,
            child_ror_records=0,
            parent_ror_records=0,
        )


def test_output_must_be_external_to_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    with pytest.raises(PairedCaptureSafetyError, match="outside"):
        validate_staging_output(repository / "evidence", repo_root=repository)
    assert (
        validate_staging_output(tmp_path / "evidence", repo_root=repository)
        == (tmp_path / "evidence").resolve()
    )


def test_complete_capture_preserves_pages_http_lineage_and_pair_binding(
    tmp_path: Path,
) -> None:
    output = tmp_path / "paired-evidence"
    transports = fixture_transports()
    manifest, manifest_path = execute_paired_capture(
        output=output,
        partitions=fixture_partitions(),
        transports=transports,
        completed_at=COMPLETED_AT,
    )

    assert manifest.complete is True
    assert [item.expected_total for item in manifest.partitions] == [2, 3, 1, 201]
    assert len(transports["inspire"].calls) == 2
    assert len(transports["arxiv"].calls) == 4
    verified = verify_paired_capture_manifest(manifest_path, output=output)
    assert verified["capture_complete"] is True
    assert verified["database_writes"] is False
    assert verified["public_metric_activation"] is False
    assert (
        verified["evidence_set_checksum"]
        == hashlib.sha256(
            json.dumps(
                verified["partition_checksums"],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
    )
    cond_arxiv = verified["partitions"][3]
    assert cond_arxiv["page_count"] == 3
    assert cond_arxiv["records_seen"] == 201
    first_lineage = cond_arxiv["pages"][0]["http_lineage"]
    assert first_lineage["provider_date"].endswith("GMT")
    assert first_lineage["etag"] == '"fixture-etag"'
    for partition in verified["partitions"]:
        for page in partition["pages"]:
            assert (output / page["path"]).is_file()


def test_injected_transport_cannot_claim_official_provider_capture(
    tmp_path: Path,
) -> None:
    output = tmp_path / "paired-evidence"
    _manifest, path = execute_paired_capture(
        output=output,
        partitions=build_trial_partitions(),
        transports=fixture_transports(arxiv_cond=2),
        completed_at=COMPLETED_AT,
    )

    verified = verify_paired_capture_manifest(path, output=output)

    assert verified["transport_attestation"] == "injected-transport"
    assert verified["provider_endpoints_official"] is False


@pytest.mark.parametrize(
    ("kwargs", "failed_index", "expected_status", "expected_calls"),
    (
        (
            {"inspire_hep": 251},
            0,
            "total-cap-exceeded",
            (1, 0),
        ),
        (
            {"arxiv_hep": 1_000},
            1,
            "total-cap-exceeded",
            (1, 1),
        ),
    ),
)
def test_provider_totals_fail_closed_and_stop_the_pair(
    tmp_path: Path,
    kwargs: dict[str, int],
    failed_index: int,
    expected_status: str,
    expected_calls: tuple[int, int],
) -> None:
    transports = fixture_transports(**kwargs)
    manifest, path = execute_paired_capture(
        output=tmp_path / "evidence",
        partitions=fixture_partitions(),
        transports=transports,
        completed_at=COMPLETED_AT,
    )

    assert manifest.complete is False
    assert manifest.partitions[failed_index].terminal_status == expected_status
    assert all(
        item.terminal_status == "not-executed"
        for item in manifest.partitions[failed_index + 1 :]
    )
    assert (
        len(transports["inspire"].calls),
        len(transports["arxiv"].calls),
    ) == expected_calls
    assert (
        verify_paired_capture_manifest(path, output=tmp_path / "evidence")[
            "capture_complete"
        ]
        is False
    )


def test_short_arxiv_pages_hit_page_cap_without_claiming_completeness(
    tmp_path: Path,
) -> None:
    transports = fixture_transports(arxiv_hep=20, arxiv_page_limit=1)
    manifest, _ = execute_paired_capture(
        output=tmp_path / "evidence",
        partitions=fixture_partitions(),
        transports=transports,
        completed_at=COMPLETED_AT,
    )

    assert manifest.complete is False
    assert manifest.partitions[1].terminal_status == "page-cap-exceeded"
    assert manifest.partitions[1].records_seen == 10
    assert len(transports["arxiv"].calls) == 10


def test_manifest_verification_rejects_tampered_page(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    manifest, path = execute_paired_capture(
        output=output,
        partitions=fixture_partitions(),
        transports=fixture_transports(arxiv_cond=2),
        completed_at=COMPLETED_AT,
    )
    first_page = manifest.partitions[0].pages[0]
    (output / first_page.path).write_text("tampered", encoding="utf-8")

    with pytest.raises(PairedCaptureVerificationError, match="page checksum"):
        verify_paired_capture_manifest(path, output=output)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("records_seen", 99, "records_seen differs"),
        ("unique_records_seen", 99, "unique_records_seen differs"),
        ("unique_ids_checksum", "b" * 64, "unique_ids_checksum differs"),
        ("duplicate_count", 1, "duplicate_count differs"),
        ("terminal_status", "count-mismatch", "terminal_status differs"),
    ),
)
def test_manifest_verification_recomputes_partition_summary_from_raw_pages(
    tmp_path: Path,
    field: str,
    replacement: object,
    message: str,
) -> None:
    output = tmp_path / "evidence"
    _, path = execute_paired_capture(
        output=output,
        partitions=fixture_partitions(),
        transports=fixture_transports(arxiv_cond=2),
        completed_at=COMPLETED_AT,
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    value["partitions"][0][field] = replacement
    resigned = _resign_manifest(path, value)

    with pytest.raises(PairedCaptureVerificationError, match=message):
        verify_paired_capture_manifest(resigned, output=output)


def test_manifest_verification_recomputes_page_counts_and_time_order(
    tmp_path: Path,
) -> None:
    output = tmp_path / "evidence"
    _, path = execute_paired_capture(
        output=output,
        partitions=fixture_partitions(),
        transports=fixture_transports(arxiv_cond=2),
        completed_at=COMPLETED_AT,
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    value["partitions"][0]["pages"][0]["record_count"] = 99
    wrong_count = _resign_manifest(path, value)
    with pytest.raises(PairedCaptureVerificationError, match="page record count"):
        verify_paired_capture_manifest(wrong_count, output=output)

    value = json.loads(path.read_text(encoding="utf-8"))
    value["completed_at"] = CAPTURED_AT.isoformat()
    early_completion = _resign_manifest(path, value)
    with pytest.raises(PairedCaptureVerificationError, match="completion precedes"):
        verify_paired_capture_manifest(early_completion, output=output)

    value = json.loads(path.read_text(encoding="utf-8"))
    value["partitions"][0]["pages"][0]["http_lineage"]["status_code"] = "200"
    wrong_status_type = _resign_manifest(path, value)
    with pytest.raises(PairedCaptureVerificationError, match="lineage status"):
        verify_paired_capture_manifest(wrong_status_type, output=output)


@pytest.mark.parametrize(
    ("url_field", "replacement", "message"),
    (
        (
            "request_url",
            "https://inspire.test/api/literature?q=different&sort=mostrecent&size=250",
            "fixed page request",
        ),
        (
            "response_url",
            "https://inspire.test/api/other?q=document_type%3Aarticle+and+subject%3ATheory-HEP+and+de+%3E%3D+2020-01-13+and+de+%3C%3D+2020-01-19&sort=mostrecent&size=250",
            "fixed page request",
        ),
    ),
)
def test_manifest_verification_binds_exact_endpoint_query_and_page_parameters(
    tmp_path: Path,
    url_field: str,
    replacement: str,
    message: str,
) -> None:
    output = tmp_path / "evidence"
    _, path = execute_paired_capture(
        output=output,
        partitions=fixture_partitions(),
        transports=fixture_transports(arxiv_cond=2),
        completed_at=COMPLETED_AT,
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    value["partitions"][0]["pages"][0]["http_lineage"][url_field] = replacement
    resigned = _resign_manifest(path, value)

    with pytest.raises(PairedCaptureVerificationError, match=message):
        verify_paired_capture_manifest(resigned, output=output)


def test_modified_partition_plan_is_rejected_before_transport_calls(
    tmp_path: Path,
) -> None:
    partitions = list(fixture_partitions())
    partitions[0] = replace(partitions[0], query="document_type:article")
    transports = fixture_transports()

    with pytest.raises(PairedCaptureSafetyError, match="fixed paired capture"):
        execute_paired_capture(
            output=tmp_path / "unused-paired-capture-test",
            partitions=partitions,
            transports=transports,
        )
    assert transports["inspire"].calls == []
    assert transports["arxiv"].calls == []


def test_lineage_transport_preserves_final_response_metadata_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            text="provider body",
            headers={
                "Date": "Fri, 04 Sep 2026 12:00:00 GMT",
                "ETag": '"abc"',
                "Last-Modified": "Thu, 03 Sep 2026 12:00:00 GMT",
                "Content-Type": "text/plain; charset=utf-8",
            },
        )

    transport = LineageProviderHttpTransport(
        allowed_hosts={"provider.test"}, minimum_intervals={}
    )
    transport.client.close()
    transport.client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        captured = transport.get_captured_text(
            "https://provider.test/records", params={"q": "fixed query"}
        )
    finally:
        transport.close()

    assert captured.body == "provider body"
    assert captured.lineage.status_code == 200
    assert captured.lineage.request_url.endswith("q=fixed+query")
    assert captured.lineage.response_url == captured.lineage.request_url
    assert captured.lineage.provider_date == "Fri, 04 Sep 2026 12:00:00 GMT"
    assert captured.lineage.etag == '"abc"'
    assert captured.lineage.last_modified is not None
    assert captured.lineage.content_type == "text/plain; charset=utf-8"
    assert captured.lineage.response_received_at >= captured.lineage.request_started_at


def test_http_lineage_rejects_naive_or_reversed_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        HttpCaptureLineage(
            request_started_at=datetime(2026, 9, 4),
            response_received_at=CAPTURED_AT,
            request_url="https://provider.test",
            response_url="https://provider.test",
            status_code=200,
        )
    with pytest.raises(ValueError, match="precedes"):
        HttpCaptureLineage(
            request_started_at=CAPTURED_AT,
            response_received_at=CAPTURED_AT - timedelta(seconds=1),
            request_url="https://provider.test",
            response_url="https://provider.test",
            status_code=200,
        )
