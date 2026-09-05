import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode, urlparse

import pytest

from physics_atlas_api.capture_lineage import CapturedTextResponse, HttpCaptureLineage
from physics_atlas_api.paired_capture import (
    PairedCaptureSafetyError,
    build_trial_partitions,
    execute_paired_capture,
)
from physics_atlas_api.paired_enrichment import (
    ENRICHMENT_ID,
    PairedEnrichmentSafetyError,
    PairedEnrichmentVerificationError,
    enrichment_plan,
    execute_paired_enrichment,
    verify_paired_enrichment_manifest,
)

CAPTURED_AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
INSPIRE_BASE = "https://inspire-authority.test/api/institutions"
ROR_BASE = "https://ror-authority.test/v2/organizations"
CHILD_A = "01aaaaaaa"
CHILD_B = "02bbbbbbb"
CHILD_C = "03ccccccc"
PARENT = "04ppppppp"


class BaseCaptureFixtureTransport:
    def __init__(self, provider: str, *, oversized_hep: bool = False):
        self.provider = provider
        self.oversized_hep = oversized_hep
        self.calls = 0

    def get_captured_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> CapturedTextResponse:
        del headers
        assert params is not None
        self.calls += 1
        query = str(params.get("q") or params.get("search_query"))
        is_cond_mat = "Condensed Matter" in query or "cond-mat" in query
        if self.provider == "inspire":
            body = json.dumps(
                {
                    "hits": {
                        "total": {"value": 1, "relation": "eq"},
                        "hits": [self._inspire_hit(is_cond_mat)],
                    },
                    "links": {},
                },
                sort_keys=True,
            )
        else:
            body = """<?xml version="1.0" encoding="UTF-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom"
                  xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
              <opensearch:totalResults>0</opensearch:totalResults>
            </feed>"""
        request_url = f"{url}?{urlencode(params)}"
        observed = CAPTURED_AT + timedelta(seconds=self.calls)
        return CapturedTextResponse(
            body=body,
            lineage=HttpCaptureLineage(
                request_started_at=observed,
                response_received_at=observed + timedelta(milliseconds=25),
                request_url=request_url,
                response_url=request_url,
                status_code=200,
                content_type=(
                    "application/json"
                    if self.provider == "inspire"
                    else "application/atom+xml"
                ),
            ),
        )

    @staticmethod
    def _affiliation(record_id: str) -> dict[str, Any]:
        return {
            "value": f"Institution {record_id}",
            "record": {"$ref": f"https://inspirehep.net/api/institutions/{record_id}"},
        }

    def _inspire_hit(self, is_cond_mat: bool) -> dict[str, Any]:
        if is_cond_mat:
            authors = [
                {
                    "full_name": "Cond Author",
                    "affiliations": [self._affiliation("201")],
                }
            ]
            record_id = 2
        else:
            if self.oversized_hep:
                authors = [
                    {
                        "full_name": "Oversized Author",
                        "affiliations": [
                            self._affiliation(str(record_id))
                            for record_id in range(1_000, 1_251)
                        ],
                    }
                ]
                return {
                    "id": "1",
                    "metadata": {
                        "control_number": 1,
                        "titles": [{"title": "Oversized paper"}],
                        "authors": authors,
                    },
                }
            authors = [
                {
                    "full_name": "Exact Author",
                    "affiliations": [self._affiliation("101")],
                    "affiliations_identifiers": [
                        {"schema": "ROR", "value": f"https://ror.org/{CHILD_A}"}
                    ],
                },
                {
                    "full_name": "Ambiguous Author",
                    "affiliations": [
                        self._affiliation("102"),
                        self._affiliation("103"),
                    ],
                    "affiliations_identifiers": [
                        {"schema": "ROR", "value": f"https://ror.org/{CHILD_B}"}
                    ],
                },
            ]
            record_id = 1
        return {
            "id": str(record_id),
            "metadata": {
                "control_number": record_id,
                "titles": [{"title": f"Paper {record_id}"}],
                "authors": authors,
            },
        }


class AuthorityFixtureTransport:
    def __init__(self, *, wrong_inspire_identity: bool = False):
        self.wrong_inspire_identity = wrong_inspire_identity
        self.calls: list[str] = []

    def get_captured_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> CapturedTextResponse:
        del params, headers
        self.calls.append(url)
        record_id = urlparse(url).path.rstrip("/").split("/")[-1]
        if url.startswith(INSPIRE_BASE) or "/api/institutions/" in url:
            returned_id = "999" if self.wrong_inspire_identity else record_id
            ror_by_institution = {
                "101": CHILD_A,
                "102": CHILD_B,
                "103": None,
                "201": CHILD_C,
            }
            ror_id = ror_by_institution[record_id]
            body: dict[str, Any] = {
                "id": returned_id,
                "metadata": {
                    "control_number": int(returned_id),
                    "legacy_ICN": f"Institution {record_id}",
                    "external_system_identifiers": (
                        [{"schema": "ROR", "value": f"https://ror.org/{ror_id}"}]
                        if ror_id
                        else []
                    ),
                },
            }
        else:
            relationships = (
                [{"type": "parent", "id": f"https://ror.org/{PARENT}"}]
                if record_id in {CHILD_A, CHILD_B}
                else []
            )
            body = {
                "id": f"https://ror.org/{record_id}",
                "status": "active",
                "names": [{"value": record_id, "types": ["ror_display"]}],
                "relationships": relationships,
            }
        observed = CAPTURED_AT + timedelta(minutes=1, seconds=len(self.calls))
        return CapturedTextResponse(
            body=json.dumps(body, sort_keys=True),
            lineage=HttpCaptureLineage(
                request_started_at=observed,
                response_received_at=observed + timedelta(milliseconds=50),
                request_url=url,
                response_url=url,
                status_code=200,
                content_type="application/json",
            ),
        )


def paired_fixture(tmp_path: Path, *, oversized_hep: bool = False) -> tuple[Path, Path]:
    output = tmp_path / "paired"
    partitions = build_trial_partitions(
        inspire_endpoint="https://inspire-source.test/api/literature",
        arxiv_endpoint="https://arxiv-source.test/api/query",
    )
    _manifest, path = execute_paired_capture(
        output=output,
        partitions=partitions,
        transports={
            "inspire": BaseCaptureFixtureTransport(
                "inspire", oversized_hep=oversized_hep
            ),
            "arxiv": BaseCaptureFixtureTransport("arxiv"),
        },
        completed_at=CAPTURED_AT + timedelta(minutes=1),
    )
    return output, path


def test_plan_derives_only_exact_bounded_base_targets(tmp_path: Path) -> None:
    _paired_output, paired_manifest = paired_fixture(tmp_path)

    plan = enrichment_plan(paired_manifest)

    assert plan["enrichment_id"] == ENRICHMENT_ID
    assert plan["executed"] is False
    assert plan["database_access"] is False
    assert plan["metric_calculation"] is False
    hep, cond = cast(list[dict[str, Any]], plan["scopes"])
    assert hep["inspire_institution_target_ids"] == ["101", "102", "103"]
    assert hep["strict_author_ror_target_ids"] == [CHILD_A]
    assert hep["ambiguous_author_ror_alignment_count"] == 2
    assert cond["inspire_institution_target_ids"] == ["201"]
    assert cond["strict_author_ror_target_ids"] == []


def test_institution_target_cap_fails_without_prefix_truncation(
    tmp_path: Path,
) -> None:
    _paired_output, paired_manifest = paired_fixture(tmp_path, oversized_hep=True)

    with pytest.raises(PairedCaptureSafetyError, match="shrink the trial"):
        enrichment_plan(paired_manifest)


def test_complete_enrichment_preserves_exact_records_lineage_and_parent_targets(
    tmp_path: Path,
) -> None:
    _paired_output, paired_manifest = paired_fixture(tmp_path)
    output = tmp_path / "enrichment"
    transport = AuthorityFixtureTransport()

    manifest, path = execute_paired_enrichment(
        paired_manifest_path=paired_manifest,
        output=output,
        transport=transport,
        inspire_base_url=INSPIRE_BASE,
        ror_base_url=ROR_BASE,
        completed_at=CAPTURED_AT + timedelta(hours=1),
    )
    verified = verify_paired_enrichment_manifest(
        path,
        output=output,
        paired_manifest_path=paired_manifest,
    )

    assert verified == {**manifest, "manifest_checksum": verified["manifest_checksum"]}
    assert verified["enrichment_complete"] is True
    assert verified["provider_endpoints_official"] is False
    assert verified["unique_inspire_institution_fetch_count"] == 4
    assert verified["unique_ror_fetch_count"] == 4
    assert len(transport.calls) == 8
    hep, cond = verified["scopes"]
    assert hep["child_ror_target_ids"] == [CHILD_A, CHILD_B]
    assert hep["parent_ror_relationship_target_ids"] == [PARENT]
    assert hep["active_parent_ror_ids"] == [PARENT]
    assert hep["institutions_without_explicit_ror_count"] == 1
    assert cond["child_ror_target_ids"] == [CHILD_C]
    assert cond["parent_ror_relationship_target_ids"] == []
    for role in ("inspire_institutions", "child_ror", "parent_ror"):
        for record in verified["records"][role]:
            assert (output / record["path"]).is_file()
            assert record["http_lineage"]["response_received_at"].endswith("+00:00")


def test_injected_authority_transport_cannot_claim_official_enrichment(
    tmp_path: Path,
) -> None:
    _paired_output, paired_manifest = paired_fixture(tmp_path)
    output = tmp_path / "enrichment"

    _manifest, path = execute_paired_enrichment(
        paired_manifest_path=paired_manifest,
        output=output,
        transport=AuthorityFixtureTransport(),
        completed_at=CAPTURED_AT + timedelta(hours=1),
    )
    verified = verify_paired_enrichment_manifest(
        path,
        output=output,
        paired_manifest_path=paired_manifest,
    )

    assert verified["transport_attestation"] == "injected-transport"
    assert verified["provider_endpoints_official"] is False


def test_exact_provider_identity_mismatch_fails_without_final_manifest(
    tmp_path: Path,
) -> None:
    _paired_output, paired_manifest = paired_fixture(tmp_path)
    output = tmp_path / "enrichment"

    with pytest.raises(PairedEnrichmentSafetyError, match="did not match target"):
        execute_paired_enrichment(
            paired_manifest_path=paired_manifest,
            output=output,
            transport=AuthorityFixtureTransport(wrong_inspire_identity=True),
            inspire_base_url=INSPIRE_BASE,
            ror_base_url=ROR_BASE,
        )

    assert list((output / "manifests").glob("*.json")) == []


def test_verifier_rejects_tampered_authority_record(tmp_path: Path) -> None:
    _paired_output, paired_manifest = paired_fixture(tmp_path)
    output = tmp_path / "enrichment"
    _manifest, path = execute_paired_enrichment(
        paired_manifest_path=paired_manifest,
        output=output,
        transport=AuthorityFixtureTransport(),
        inspire_base_url=INSPIRE_BASE,
        ror_base_url=ROR_BASE,
        completed_at=CAPTURED_AT + timedelta(hours=1),
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    record_path = output / value["records"]["child_ror"][0]["path"]
    record_path.write_text("tampered", encoding="utf-8")

    with pytest.raises(PairedEnrichmentVerificationError, match="record checksum"):
        verify_paired_enrichment_manifest(
            path,
            output=output,
            paired_manifest_path=paired_manifest,
        )


def test_verifier_rejects_completion_before_authority_responses(
    tmp_path: Path,
) -> None:
    _paired_output, paired_manifest = paired_fixture(tmp_path)
    output = tmp_path / "enrichment"
    _manifest, path = execute_paired_enrichment(
        paired_manifest_path=paired_manifest,
        output=output,
        transport=AuthorityFixtureTransport(),
        inspire_base_url=INSPIRE_BASE,
        ror_base_url=ROR_BASE,
        completed_at=CAPTURED_AT,
    )

    with pytest.raises(PairedEnrichmentVerificationError, match="predates"):
        verify_paired_enrichment_manifest(
            path,
            output=output,
            paired_manifest_path=paired_manifest,
        )
