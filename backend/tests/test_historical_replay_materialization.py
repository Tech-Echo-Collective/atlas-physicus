import hashlib
import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import pytest

from physics_atlas_api.backfill import build_partitions, execute_backfill
from physics_atlas_api.config import Settings
from physics_atlas_api.connectors.base import normalize_external_id
from physics_atlas_api.historical_replay import StrongIdentifier
from physics_atlas_api.historical_replay_materialization import (
    HistoricalReplayBundle,
    HistoricalReplaySafetyError,
    build_historical_replay_bundle,
    materialize_historical_replay,
    run,
    validate_replay_request,
    verify_historical_staging,
)

_CUTOFF = datetime(2026, 8, 31, 0, 0, tzinfo=UTC)


def test_inspire_api_author_and_institution_urls_are_entity_safe() -> None:
    assert normalize_external_id(
        "inspire-author", "https://inspirehep.net/api/authors/2664905"
    ) == ("inspire-author", "2664905")
    assert normalize_external_id(
        "inspire-author", "https://inspirehep.net/authors/2664905"
    ) == ("inspire-author", "2664905")
    assert normalize_external_id(
        "inspire-institution", "https://inspirehep.net/api/institutions/123"
    ) == ("inspire-institution", "123")
    assert normalize_external_id(
        "inspire-institution", "https://inspirehep.net/institutions/123"
    ) == ("inspire-institution", "123")
    assert (
        normalize_external_id(
            "inspire-author", "https://inspirehep.net/api/institutions/123"
        )
        is None
    )
    assert (
        normalize_external_id(
            "inspire-institution", "https://inspirehep.net/api/authors/2664905"
        )
        is None
    )
    assert normalize_external_id("inspire-bai", "G.Y.Oyadomari.1") == (
        "inspire-bai",
        "G.Y.Oyadomari.1",
    )
    assert normalize_external_id("inspire-bai", "INSPIRE BAI: G.Y.Oyadomari.1") == (
        "inspire-bai",
        "G.Y.Oyadomari.1",
    )
    assert normalize_external_id("inspire-bai", "not a BAI") is None


class _HistoricalStagingTransport:
    """Tiny deterministic acquisition fixture used to create immutable pages."""

    def __init__(self, provider: str):
        self.provider = provider

    def close(self) -> None:
        return None

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
        raise AssertionError("historical acquisition stores provider text envelopes")

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        del url, headers
        assert params is not None
        if self.provider == "inspire":
            return self._inspire(str(params["q"]))
        return self._arxiv(str(params["search_query"]))

    @staticmethod
    def _inspire(query: str) -> str:
        year_match = re.search(r"de >= (\d{4})-01-01", query)
        assert year_match is not None
        year = int(year_match.group(1))
        hits: list[dict[str, object]] = []
        if year == 2020:
            hits.append(
                {
                    "id": "777",
                    "updated": "2026-08-30T23:00:00Z",
                    "metadata": {
                        "control_number": 777,
                        "document_type": ["article"],
                        "titles": [{"title": "A deterministic replay paper"}],
                        "abstracts": [{"value": "Immutable fixture evidence."}],
                        "authors": [
                            {
                                "full_name": "Ada Example",
                                "recid": 17,
                                "record": {
                                    "$ref": "https://inspirehep.net/api/authors/17"
                                },
                                "ids": [
                                    {
                                        "schema": "ORCID",
                                        "value": "0000-0002-1825-0097",
                                    },
                                    {
                                        "schema": "INSPIRE BAI",
                                        "value": "A.Example.1",
                                    },
                                ],
                                "affiliations": [
                                    {
                                        "value": "Example Institute",
                                        "identifiers": [
                                            {
                                                "schema": "ROR",
                                                "value": "03vek6s52",
                                            }
                                        ],
                                    }
                                ],
                                "raw_affiliations": [{"value": "Example Institute"}],
                            },
                            {
                                "full_name": "Bert Example",
                                "affiliations": [
                                    {"value": "First unresolved institute"},
                                    {"value": "Second unresolved institute"},
                                ],
                                "affiliations_identifiers": [
                                    {"schema": "ROR", "value": "00hx57361"},
                                    {"schema": "ROR", "value": "01bj3aw27"},
                                ],
                            },
                        ],
                        "arxiv_eprints": [{"value": "2001.00001"}],
                        "dois": [{"value": "10.1234/replay"}],
                        "inspire_categories": [
                            {"term": "Theory-HEP", "source": "INSPIRE"}
                        ],
                        "publication_info": [
                            {
                                "year": 2021,
                                "journal_title": "JHEP",
                                "journal_volume": "03",
                                "artid": "001",
                            }
                        ],
                        "imprints": [{"date": "2021-03-01"}],
                        "preprint_date": "2020-01-03",
                        "earliest_date": "2020-01-03",
                        "citation_count": 7,
                        "citation_count_without_self_citations": 5,
                    },
                }
            )
        return json.dumps(
            {
                "hits": {
                    "total": {"value": len(hits), "relation": "eq"},
                    "hits": hits,
                },
                "links": {},
            },
            sort_keys=True,
        )

    @staticmethod
    def _arxiv(query: str) -> str:
        year_match = re.search(r"submittedDate:\[(\d{4})", query)
        assert year_match is not None
        year = int(year_match.group(1))
        entry = ""
        if year == 2020:
            entry = """
            <entry>
              <id>https://arxiv.org/abs/2001.00001v2</id>
              <updated>2021-03-02T00:00:00Z</updated>
              <published>2020-01-03T00:00:00Z</published>
              <title>A deterministic replay paper</title>
              <summary>Immutable fixture evidence.</summary>
              <author>
                <name>Ada Example</name>
                <arxiv:affiliation>Example Institute</arxiv:affiliation>
              </author>
              <author>
                <name>Bert Example</name>
                <arxiv:affiliation>First unresolved institute</arxiv:affiliation>
                <arxiv:affiliation>Second unresolved institute</arxiv:affiliation>
              </author>
              <category term="hep-th"
                scheme="http://arxiv.org/schemas/atom" />
              <arxiv:primary_category term="hep-th"
                scheme="http://arxiv.org/schemas/atom" />
              <arxiv:doi>10.1234/replay</arxiv:doi>
              <arxiv:journal_ref>JHEP 03 2021 001</arxiv:journal_ref>
            </entry>
            """
        total = 1 if entry else 0
        return f"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
              xmlns:arxiv="http://arxiv.org/schemas/atom">
          <opensearch:totalResults>{total}</opensearch:totalResults>
          {entry}
        </feed>"""


def _staged_acquisition(tmp_path: Path) -> tuple[Path, Path]:
    staging = tmp_path / "staging"
    manifest = execute_backfill(
        "acquire",
        output=staging,
        settings=Settings(database_url="sqlite://", fixture_mode=True),
        now=_CUTOFF,
        partitions=build_partitions(),
        transports={
            "inspire": _HistoricalStagingTransport("inspire"),
            "arxiv": _HistoricalStagingTransport("arxiv"),
        },
    )
    assert manifest.successful is True
    assert manifest.output_path is not None
    return staging, manifest.output_path


def _artifact_rows(bundle: HistoricalReplayBundle, role: str) -> list[dict[str, Any]]:
    artifact = next(item for item in bundle.artifacts if item.role == role)
    return [
        json.loads(line)
        for line in artifact.content.decode("utf-8").splitlines()
        if line
    ]


def test_plan_verifies_pages_and_builds_withheld_evidence_bundle(
    tmp_path: Path,
) -> None:
    staging, manifest = _staged_acquisition(tmp_path)

    result = materialize_historical_replay(
        staging_root=staging,
        source_manifest=manifest,
    )
    verified = verify_historical_staging(staging, manifest)
    bundle = build_historical_replay_bundle(verified)

    assert result.mode == "plan"
    assert result.output_manifest_path is None
    assert result.report["verified_page_count"] == 12
    assert result.report["provider_record_counts"] == {"arxiv": 1, "inspire": 1}
    assert result.report["source_occurrence_count"] == 2
    assert result.report["paper_component_count"] == 1
    assert result.report["paper_status_counts"] == {
        "matched": 1,
        "needs_review": 0,
    }
    assert result.report["merged_paper_component_count"] == 1
    assert result.report["singleton_paper_component_count"] == 0
    assert result.report["cross_provider_paper_component_count"] == 1
    assert result.report["provider_records_in_merged_components"] == {
        "arxiv": 1,
        "inspire": 1,
    }
    assert result.report["components_with_valid_date_evidence"] == 1
    assert result.report["normalized_date_evidence_coverage"] == pytest.approx(1.0)
    assert result.report["date_evidence_precision_counts"] == {"day": 5, "year": 1}
    assert result.report["invalid_date_evidence_count"] == 0
    assert result.report["citation_observation_count"] == 1
    assert result.report["citation_cutoff_comparable_observation_count"] == 0
    assert result.report["mature_citation_cohort_count"] == 0
    assert result.report["citation_cutoff_semantics"] == (
        "acquisition-manifest-completion-upper-bound"
    )
    assert result.report["citation_page_capture_timestamp_available"] is False
    assert result.report["citation_simultaneous_observation_claimed"] is False
    assert result.report["source_occurrence_raw_citation_coverage_rate"] == (
        pytest.approx(0.5)
    )
    assert result.report["canonical_components_with_raw_citation_evidence"] == 1
    assert result.report["canonical_component_raw_citation_coverage_rate"] == (
        pytest.approx(1.0)
    )
    assert result.report["canonical_components_with_non_self_citation_evidence"] == 1
    assert result.report["field_ledger_count"] == 1
    assert result.report["field_conservation_failures"] == 0
    assert result.report["multi_field_ledger_count"] == 0
    assert result.report["field_ledgers_with_unmapped_mass"] == 0
    assert result.report["total_assigned_field_mass"] == pytest.approx(1.0)
    assert result.report["total_explicit_unmapped_field_mass"] == pytest.approx(0.0)
    assert result.report["field_ledger_review_status_counts"] == {
        "reviewed": 0,
        "needs_review": 0,
        "unreviewed": 1,
    }
    assert result.report["reviewed_field_ledger_count"] == 0
    assert result.report["canonical_cohort_count"] == 0
    assert result.report["certified_complete_canonical_years"] == []
    assert result.report["momentum_window_readiness"] == {
        "2020-2022": False,
        "2023-2025": False,
    }
    assert result.report["metric_observations_created"] == 0
    assert result.report["researcher_appearance_count"] == 2
    assert result.report["paper_time_affiliation_share_count"] == 3
    assert result.report["institution_authority_anchor_count"] == 1
    assert result.report["direct_ror_alignment_count"] == 1
    assert result.report["relationship_mass_conservation_passed"] is True
    assert result.report["evaluated_attribution_paper_mass"] == {
        "numerator": 1,
        "denominator": 1,
        "exact": "1/1",
    }
    assert result.report["allocated_attribution_mass"]["exact"] == "0/1"
    assert result.report["withheld_attribution_mass"]["exact"] == "1/1"
    assert result.report["paper_time_affiliation_evidence_mass"]["exact"] == "1/1"
    assert result.report["paper_time_no_affiliation_evidence_mass"]["exact"] == ("0/1")
    assert result.report["paper_time_affiliation_evidence_coverage"] == pytest.approx(
        1.0
    )
    assert result.report["affiliation_evidence_mass_conservation_passed"] is True
    assert result.bundle_manifest["database_access"] is False
    assert result.bundle_manifest["source_cursor_access"] is False
    assert result.bundle_manifest["network_access"] is False
    assert result.bundle_manifest["canonical_paper_merge_policy_version"] == (
        "canonical-paper-merge-policy-v1"
    )
    assert result.bundle_manifest["merge_plan_version"] == (
        "historical-paper-merge-plan-v1"
    )
    assert result.bundle_manifest["merge_plan_digest"]

    occurrences = _artifact_rows(bundle, "source-occurrences")
    assert {item["provider"] for item in occurrences} == {"inspire", "arxiv"}
    assert all(item["lineage"]["page_checksum"] for item in occurrences)
    assert all(item["author_evidence_embedded"] is False for item in occurrences)
    assert {item["author_count"] for item in occurrences} == {2}
    assert all(
        item["lineage"]["source_manifest_checksum"] == result.source_manifest_checksum
        for item in occurrences
    )
    assert {
        (date["kind"], date["value"], date["precision"])
        for item in occurrences
        for date in item["dates"]
    } >= {
        ("formal-publication", "2021-03-01", "day"),
        ("preprint-submission", "2020-01-03", "day"),
        ("provider-update", "2021-03-02", "day"),
    }
    assert {item["document_type"] for item in occurrences} == {
        "article",
        "preprint",
    }
    assert {
        value for item in occurrences for value in item["document_type_evidence"]
    } == {"article", "preprint"}

    components = _artifact_rows(bundle, "paper-components")
    assert components[0]["canonical_id"].startswith("paper-doi-10-1234-replay-")
    assert len(components[0]["source_lineage"]) == 2
    assert components[0]["canonical_date_selected"] is False
    assert components[0]["canonical_document_type_selected"] is False
    assert components[0]["canonical_cohort_selected"] is False
    assert components[0]["merge_policy_version"] == ("canonical-paper-merge-policy-v1")
    assert components[0]["eligible_for_public_metrics"] is False

    citations = _artifact_rows(bundle, "citation-observations")
    assert citations[0]["raw_citation_count"] == 7
    assert citations[0]["non_self_citation_count"] == 5
    assert citations[0]["cutoff_timestamp"] == _CUTOFF.isoformat()
    assert citations[0]["cutoff_semantics"] == (
        "acquisition-manifest-completion-upper-bound"
    )
    assert citations[0]["page_capture_timestamp"] is None
    assert citations[0]["simultaneous_observation_claimed"] is False
    assert citations[0]["source_manifest_checksum"] == result.source_manifest_checksum
    assert citations[0]["page_path"].endswith(".json")
    assert len(citations[0]["page_checksum"]) == 64
    assert citations[0]["common_cutoff_comparable"] is False
    assert citations[0]["eligible_for_impact"] is False

    fields = _artifact_rows(bundle, "field-ledgers")
    assert fields[0]["review_status"] == "unreviewed"
    assert fields[0]["assigned_field_mass"] == pytest.approx(1.0)
    assert fields[0]["unmapped_field_mass"] == pytest.approx(0.0)
    assert fields[0]["conservation_total"] == pytest.approx(1.0)
    assert fields[0]["conservation_passed"] is True
    assert fields[0]["eligible_for_public_metrics"] is False

    researcher_appearances = _artifact_rows(bundle, "researcher-appearances")
    assert len(researcher_appearances) == 2
    ada = next(
        item
        for item in researcher_appearances
        if item["raw_author_name"] == "Ada Example"
    )
    bert = next(
        item
        for item in researcher_appearances
        if item["raw_author_name"] == "Bert Example"
    )
    assert ada["provider"] == "inspire"
    assert ada["identity_status"] == "unreviewed-authority-evidence"
    assert ada["canonical_researcher_id"] is None
    assert ada["authority_identifiers"] == [
        {"scheme": "inspire-author", "value": "17"},
        {"scheme": "inspire-bai", "value": "A.Example.1"},
        {"scheme": "orcid", "value": "0000-0002-1825-0097"},
    ]
    assert ada["conflict_schemes"] == []
    assert bert["identity_status"] == "unresolved-no-authority-identifier"

    affiliation_shares = _artifact_rows(bundle, "paper-time-affiliation-shares")
    assert len(affiliation_shares) == 3
    assert {item["attribution_weight"]["exact"] for item in affiliation_shares} == {
        "1/2",
        "1/4",
    }
    assert sum(
        item["attribution_weight"]["numerator"]
        / item["attribution_weight"]["denominator"]
        for item in affiliation_shares
    ) == pytest.approx(1.0)
    assert all(item["canonical_institution_id"] is None for item in affiliation_shares)
    assert all(item["country_id"] is None for item in affiliation_shares)
    ada_share = next(
        item for item in affiliation_shares if item["author_position"] == 1
    )
    assert ada_share["institution_authority_anchor_ids"] == [
        "institution-authority-ror-03vek6s52"
    ]
    bert_shares = [item for item in affiliation_shares if item["author_position"] == 2]
    assert all(item["institution_authority_anchor_ids"] == [] for item in bert_shares)
    assert {
        item["resolution_evidence"][0]["alignment_status"] for item in bert_shares
    } == {"unresolved-author-level-rors-not-positionally-aligned"}

    anchors = _artifact_rows(bundle, "institution-authority-anchors")
    assert anchors == [
        {
            "authority_identifier": {"scheme": "ror", "value": "03vek6s52"},
            "canonical_institution_id": None,
            "eligible_for_public_metrics": False,
            "institution_authority_anchor_id": ("institution-authority-ror-03vek6s52"),
            "metadata_status": "metadata-pending",
            "relationship_projection_version": (
                "hep-th-v1-historical-relationship-projection-v1"
            ),
            "required_authority_bundle_version": (
                "hep-th-v1-historical-canonical-institutions-v2"
            ),
            "source_assertion_ids": [ada_share["affiliation_assertion_ids"][0]],
            "source_occurrence_ids": ["inspire:777"],
        }
    ]

    attribution_ledgers = _artifact_rows(bundle, "fractional-attribution-ledgers")
    assert attribution_ledgers[0]["projection_status"] == (
        "selected-inspire-paper-time-evidence"
    )
    assert attribution_ledgers[0]["total_weight"]["exact"] == "1/1"
    assert attribution_ledgers[0]["conservation_passed"] is True


def test_execute_is_content_addressed_idempotent_and_checksum_verified(
    tmp_path: Path,
) -> None:
    staging, manifest = _staged_acquisition(tmp_path)
    output = tmp_path / "replay-output"

    first = materialize_historical_replay(
        staging_root=staging,
        source_manifest=manifest,
        output=output,
        execute=True,
    )
    second = materialize_historical_replay(
        staging_root=staging,
        source_manifest=manifest,
        output=output,
        execute=True,
    )

    assert first.replay_digest == second.replay_digest
    assert first.bundle_manifest == second.bundle_manifest
    assert first.output_manifest_path == second.output_manifest_path
    assert first.output_manifest_path is not None
    assert first.output_manifest_path.is_file()
    assert len(list((output / "manifests").glob("*.json"))) == 1
    for artifact in first.bundle_manifest["artifacts"]:
        assert isinstance(artifact, dict)
        path = output / str(artifact["path"])
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["checksum"]


def test_execute_refuses_to_overwrite_nonidentical_content(tmp_path: Path) -> None:
    staging, manifest = _staged_acquisition(tmp_path)
    output = tmp_path / "replay-output"
    result = materialize_historical_replay(
        staging_root=staging,
        source_manifest=manifest,
        output=output,
        execute=True,
    )
    artifact = next(
        item
        for item in result.bundle_manifest["artifacts"]
        if isinstance(item, dict) and item["role"] == "source-occurrences"
    )
    (output / str(artifact["path"])).write_bytes(b"different content\n")

    with pytest.raises(HistoricalReplaySafetyError, match="refusing to overwrite"):
        materialize_historical_replay(
            staging_root=staging,
            source_manifest=manifest,
            output=output,
            execute=True,
        )


def test_tampered_staged_page_fails_before_output(tmp_path: Path) -> None:
    staging, manifest = _staged_acquisition(tmp_path)
    source_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    page = staging / source_manifest["partitions"][0]["pages"][0]["path"]
    page.write_bytes(page.read_bytes() + b" ")
    output = tmp_path / "should-not-exist"

    with pytest.raises(HistoricalReplaySafetyError, match="page checksum failed"):
        materialize_historical_replay(
            staging_root=staging,
            source_manifest=manifest,
            output=output,
            execute=True,
        )

    assert not output.exists()


def test_bundle_is_invariant_to_verified_occurrence_order(tmp_path: Path) -> None:
    staging, manifest = _staged_acquisition(tmp_path)
    verified = verify_historical_staging(staging, manifest)

    forward = build_historical_replay_bundle(verified)
    reverse = build_historical_replay_bundle(
        replace(verified, occurrences=tuple(reversed(verified.occurrences)))
    )

    assert forward.replay_digest == reverse.replay_digest
    assert forward.bundle_manifest == reverse.bundle_manifest
    assert [item.checksum for item in forward.artifacts] == [
        item.checksum for item in reverse.artifacts
    ]


def test_missing_affiliation_evidence_remains_exact_withheld_mass(
    tmp_path: Path,
) -> None:
    staging, manifest = _staged_acquisition(tmp_path)
    verified = verify_historical_staging(staging, manifest)
    inspire = next(
        item for item in verified.occurrences if item.evidence.provider == "inspire"
    )
    authors = list(inspire.authors)
    missing_author = dict(authors[1])
    missing_author.pop("affiliations", None)
    missing_author.pop("raw_affiliations", None)
    missing_author.pop("affiliations_identifiers", None)
    authors[1] = missing_author
    occurrences = tuple(
        replace(item, authors=tuple(authors)) if item is inspire else item
        for item in verified.occurrences
    )

    bundle = build_historical_replay_bundle(replace(verified, occurrences=occurrences))

    assert bundle.report["paper_time_affiliation_evidence_mass"]["exact"] == "1/2"
    assert bundle.report["paper_time_no_affiliation_evidence_mass"]["exact"] == "1/2"
    assert bundle.report["paper_time_affiliation_evidence_coverage"] == pytest.approx(
        0.5
    )
    assert bundle.report["affiliation_evidence_mass_conservation_passed"] is True
    shares = _artifact_rows(bundle, "paper-time-affiliation-shares")
    missing_share = next(
        item
        for item in shares
        if item["resolution_status"] == "withheld-no-affiliation"
    )
    assert missing_share["affiliation_assertion_ids"] == []
    assert missing_share["attribution_weight"]["exact"] == "1/2"


def test_unmaterialized_projection_is_not_a_conservation_failure(
    tmp_path: Path,
) -> None:
    staging, manifest = _staged_acquisition(tmp_path)
    verified = verify_historical_staging(staging, manifest)
    inspire = next(
        item for item in verified.occurrences if item.evidence.provider == "inspire"
    )
    duplicate_id = "inspire:778"
    duplicate_evidence = replace(
        inspire.evidence,
        occurrence_id=duplicate_id,
        source_record_id="778",
        source_reference=f"{inspire.lineage.page_path}#{duplicate_id}",
        identifiers=tuple(
            StrongIdentifier("inspire", "778") if item.scheme == "inspire" else item
            for item in inspire.evidence.identifiers
        ),
        dates=tuple(
            replace(item, source_occurrence_id=duplicate_id)
            for item in inspire.evidence.dates
        ),
    )
    duplicate = replace(
        inspire,
        evidence=duplicate_evidence,
        source_record_checksum="f" * 64,
    )

    bundle = build_historical_replay_bundle(
        replace(verified, occurrences=(*verified.occurrences, duplicate))
    )

    assert bundle.report["unmaterialized_attribution_ledger_count"] == 1
    assert bundle.report["unevaluable_attribution_ledger_count"] == 1
    assert bundle.report["attribution_conservation_failures"] == 0
    assert bundle.report["evaluated_attribution_conservation_failures"] == 0
    assert bundle.report["unmaterialized_paper_mass"]["exact"] == "1/1"
    assert bundle.report["relationship_mass_conservation_passed"] is True


def test_request_and_cli_fail_closed_before_replay_writes(tmp_path: Path) -> None:
    staging, manifest = _staged_acquisition(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()

    with pytest.raises(HistoricalReplaySafetyError, match="plan mode"):
        validate_replay_request(
            staging_root=staging,
            source_manifest=manifest,
            output=tmp_path / "unexpected-output",
            execute=False,
            repo_root=repository,
        )
    with pytest.raises(HistoricalReplaySafetyError, match="requires an output"):
        validate_replay_request(
            staging_root=staging,
            source_manifest=manifest,
            output=None,
            execute=True,
            repo_root=repository,
        )
    with pytest.raises(HistoricalReplaySafetyError, match="outside the repository"):
        validate_replay_request(
            staging_root=staging,
            source_manifest=manifest,
            output=repository / "bundle",
            execute=True,
            repo_root=repository,
        )
    with pytest.raises(HistoricalReplaySafetyError, match="must not modify"):
        validate_replay_request(
            staging_root=staging,
            source_manifest=manifest,
            output=staging / "bundle",
            execute=True,
            repo_root=repository,
        )
    with pytest.raises(HistoricalReplaySafetyError, match="explicit --execute"):
        run(
            [
                "execute",
                "--staging-root",
                str(staging),
                "--source-manifest",
                str(manifest),
                "--output",
                str(tmp_path / "bundle"),
            ]
        )
    with pytest.raises(HistoricalReplaySafetyError, match="plan mode"):
        run(
            [
                "plan",
                "--staging-root",
                str(staging),
                "--source-manifest",
                str(manifest),
                "--execute",
            ]
        )
