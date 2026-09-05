import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from test_paired_enrichment import (
    CAPTURED_AT,
    INSPIRE_BASE,
    ROR_BASE,
    AuthorityFixtureTransport,
    BaseCaptureFixtureTransport,
    paired_fixture,
)

from physics_atlas_api.certification.citations import (
    CITATION_POLICY_VERSION,
    CitationObservationEvidence,
    certify_citation_observation,
)
from physics_atlas_api.certification.contracts import EvidenceReference
from physics_atlas_api.connectors.base import NormalizedRecord, SourceRecord
from physics_atlas_api.paired_capture import PAIR_ID
from physics_atlas_api.paired_enrichment import execute_paired_enrichment
from physics_atlas_api.paired_trial_certification import (
    CERTIFICATION_ID,
    PairedTrialCertificationError,
    _align_affiliation_ror_evidence,
    _canonicalize,
    _citation_rows,
    _CitationCandidate,
    _lower_precedence_affiliation_crosscheck,
    _Occurrence,
    _raw_affiliations,
    _researcher_ids,
    _select_citation_candidate,
    _selected_relationship_occurrence,
    certification_plan,
    certify_paired_trial,
    run,
    verify_paired_trial_certification_manifest,
)


def _canonical_json(value: object, *, pretty: bool = False) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
            sort_keys=True,
        )
        + ("\n" if pretty else "")
    ).encode("utf-8")


def _checksum(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _fixture_bundle(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path, Path]:
    raw_root, raw_manifest = paired_fixture(tmp_path)
    enrichment_root = tmp_path / "enrichment"
    _enrichment, enrichment_manifest = execute_paired_enrichment(
        paired_manifest_path=raw_manifest,
        output=enrichment_root,
        transport=AuthorityFixtureTransport(),
        inspire_base_url=INSPIRE_BASE,
        ror_base_url=ROR_BASE,
        completed_at=CAPTURED_AT + timedelta(hours=1),
    )
    output = tmp_path / "certification"
    _manifest, certification_manifest = certify_paired_trial(
        raw_root=raw_root,
        raw_manifest_path=raw_manifest,
        enrichment_root=enrichment_root,
        enrichment_manifest_path=enrichment_manifest,
        output=output,
    )
    return (
        raw_root,
        raw_manifest,
        enrichment_root,
        enrichment_manifest,
        output,
        certification_manifest,
    )


def _artifact(
    manifest: dict[str, Any], output: Path, role: str
) -> tuple[dict[str, Any], Path]:
    entry = next(item for item in manifest["artifacts"] if item["role"] == role)
    return entry, output / entry["path"]


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_plan_is_pure_bounded_and_never_metric_eligible(capsys: Any) -> None:
    plan = certification_plan()

    assert plan["certification_id"] == CERTIFICATION_ID
    assert plan["executed"] is False
    assert plan["staging_only"] is True
    assert plan["network_access"] is False
    assert plan["database_writes"] is False
    assert plan["metric_observations_created"] == 0
    assert plan["certified_complete_year_count"] == 0
    assert plan["certified_metric_window_count"] == 0

    assert run([]) == 0
    assert json.loads(capsys.readouterr().out) == plan


def test_researcher_record_reference_and_recid_are_one_exact_identifier() -> None:
    identifiers = _researcher_ids(
        {
            "record": {"$ref": "https://inspirehep.net/api/authors/997721"},
            "recid": 997721,
            "ids": [{"schema": "INSPIRE BAI", "value": "R.Mertig.1"}],
        }
    )

    assert identifiers == (
        ("inspire-author", "997721"),
        ("inspire-bai", "R.Mertig.1"),
    )


def test_empty_affiliation_objects_are_not_evidence() -> None:
    assert _raw_affiliations(
        {"affiliations": [{}, {"value": "  "}, {"value": "Institute A"}]}
    ) == ({"value": "Institute A"},)


def test_author_level_rors_align_only_to_one_compatible_affiliation() -> None:
    direct, alignment, reasons = _align_affiliation_ror_evidence(
        local_rors=("01aaaaaaa",),
        author_rors=("02bbbbbbb",),
        affiliation_count=1,
    )
    assert direct == ("01aaaaaaa", "02bbbbbbb")
    assert alignment == "conflicted-single-affiliation-local-vs-author-ror"
    assert reasons

    direct, alignment, reasons = _align_affiliation_ror_evidence(
        local_rors=("01aaaaaaa",),
        author_rors=("01aaaaaaa",),
        affiliation_count=1,
    )
    assert direct == ("01aaaaaaa",)
    assert alignment == "single-affiliation-local-author-ror-corroborated"
    assert reasons == ()

    direct, alignment, reasons = _align_affiliation_ror_evidence(
        local_rors=("01aaaaaaa",),
        author_rors=("01aaaaaaa", "02bbbbbbb"),
        affiliation_count=2,
    )
    assert direct == ("01aaaaaaa",)
    assert alignment == "affiliation-local-ror-author-level-set-unaligned"
    assert reasons == ()

    direct, alignment, reasons = _align_affiliation_ror_evidence(
        local_rors=(),
        author_rors=("01aaaaaaa", "02bbbbbbb"),
        affiliation_count=2,
    )
    assert direct == ()
    assert alignment == "unresolved-author-ror-not-positionally-aligned"
    assert reasons == ()


def test_affiliation_precedence_falls_back_and_preserves_disagreement() -> None:
    shared_ids = (("arxiv", "2001.00001"),)
    inspire = _occurrence(
        scope_id="hep",
        provider="inspire",
        record_id="1",
        identifiers=shared_ids,
    )
    arxiv = _occurrence(
        scope_id="hep",
        provider="arxiv",
        record_id="2001.00001",
        identifiers=shared_ids,
    )
    inspire_without_affiliation = replace(
        inspire,
        normalized=replace(
            inspire.normalized,
            attributes={
                "authors": [{"full_name": "Exact Author", "affiliations": [{}]}]
            },
        ),
    )
    arxiv_with_affiliation = replace(
        arxiv,
        normalized=replace(
            arxiv.normalized,
            attributes={
                "authors": [
                    {"full_name": "Exact Author", "affiliations": [{"value": "B"}]}
                ]
            },
        ),
    )
    paper = _canonicalize((inspire_without_affiliation, arxiv_with_affiliation))[0]

    selected, status = _selected_relationship_occurrence(paper)

    assert selected == arxiv_with_affiliation
    assert status.endswith("after-inspire-affiliation-absence")

    inspire_with_affiliation = replace(
        inspire,
        normalized=replace(
            inspire.normalized,
            attributes={
                "authors": [
                    {"full_name": "Exact Author", "affiliations": [{"value": "A"}]}
                ]
            },
        ),
    )
    paper = _canonicalize((inspire_with_affiliation, arxiv_with_affiliation))[0]
    selected, _status = _selected_relationship_occurrence(paper)
    assert selected is not None
    crosscheck, references, reasons = _lower_precedence_affiliation_crosscheck(
        paper,
        selected,
        {"full_name": "Exact Author", "affiliations": [{"value": "A"}]},
    )
    assert crosscheck == "needs-review-provider-disagreement"
    assert references == (arxiv_with_affiliation.page_reference,)
    assert reasons


def test_affiliation_crosscheck_rejects_partial_overlap() -> None:
    shared_ids = (("arxiv", "2001.00001"),)
    inspire = _occurrence(
        scope_id="hep", provider="inspire", record_id="1", identifiers=shared_ids
    )
    arxiv = _occurrence(
        scope_id="hep",
        provider="arxiv",
        record_id="2001.00001",
        identifiers=shared_ids,
    )
    inspire_author = {
        "full_name": "Exact Author",
        "affiliations": [{"value": "MIT"}, {"value": "Princeton"}],
    }
    arxiv_author = {
        "full_name": "Exact Author",
        "affiliations": [{"value": "MIT"}],
    }
    inspire = replace(
        inspire,
        normalized=replace(
            inspire.normalized, attributes={"authors": [inspire_author]}
        ),
    )
    arxiv = replace(
        arxiv,
        normalized=replace(arxiv.normalized, attributes={"authors": [arxiv_author]}),
    )
    paper = _canonicalize((inspire, arxiv))[0]

    status, references, reasons = _lower_precedence_affiliation_crosscheck(
        paper, inspire, inspire_author
    )

    assert status == "needs-review-provider-disagreement"
    assert references == (arxiv.page_reference,)
    assert "normalized-name" in reasons[0]


def test_affiliation_crosscheck_rejects_identifier_only_disagreement() -> None:
    shared_ids = (("arxiv", "2001.00001"),)
    inspire = _occurrence(
        scope_id="hep", provider="inspire", record_id="1", identifiers=shared_ids
    )
    arxiv = _occurrence(
        scope_id="hep",
        provider="arxiv",
        record_id="2001.00001",
        identifiers=shared_ids,
    )
    inspire_author = {
        "full_name": "Exact Author",
        "affiliations": [{"identifiers": [{"schema": "ROR", "value": "042nb2s44"}]}],
    }
    arxiv_author = {
        "full_name": "Exact Author",
        "affiliations": [{"identifiers": [{"schema": "ROR", "value": "00hx57361"}]}],
    }
    inspire = replace(
        inspire,
        normalized=replace(
            inspire.normalized, attributes={"authors": [inspire_author]}
        ),
    )
    arxiv = replace(
        arxiv,
        normalized=replace(arxiv.normalized, attributes={"authors": [arxiv_author]}),
    )
    paper = _canonicalize((inspire, arxiv))[0]

    status, _references, reasons = _lower_precedence_affiliation_crosscheck(
        paper, inspire, inspire_author
    )

    assert status == "needs-review-provider-disagreement"
    assert "ror" in reasons[0]


def test_affiliation_crosscheck_allows_asymmetric_identifier_enrichment() -> None:
    shared_ids = (("arxiv", "2001.00001"),)
    inspire = _occurrence(
        scope_id="hep", provider="inspire", record_id="1", identifiers=shared_ids
    )
    arxiv = _occurrence(
        scope_id="hep",
        provider="arxiv",
        record_id="2001.00001",
        identifiers=shared_ids,
    )
    inspire_author = {
        "full_name": "Exact Author",
        "affiliations": [
            {
                "value": "MIT",
                "identifiers": [{"schema": "ROR", "value": "042nb2s44"}],
            }
        ],
    }
    arxiv_author = {
        "full_name": "Exact Author",
        "affiliations": [{"value": "MIT"}],
    }
    inspire = replace(
        inspire,
        normalized=replace(
            inspire.normalized, attributes={"authors": [inspire_author]}
        ),
    )
    arxiv = replace(
        arxiv,
        normalized=replace(arxiv.normalized, attributes={"authors": [arxiv_author]}),
    )
    paper = _canonicalize((inspire, arxiv))[0]

    status, _references, reasons = _lower_precedence_affiliation_crosscheck(
        paper, inspire, inspire_author
    )

    assert status == "corroborated-exact-assertions"
    assert reasons == ()


def _occurrence(
    *,
    scope_id: str,
    provider: str,
    record_id: str,
    identifiers: tuple[tuple[str, str], ...],
    title: str = "Same title is not identity evidence",
) -> _Occurrence:
    typed_provider = cast(Any, provider)
    raw = {"title": title}
    record = SourceRecord(
        provider=typed_provider,
        source_record_id=record_id,
        raw=raw,
    )
    normalized = NormalizedRecord(
        provider=typed_provider,
        kind="paper",
        source_record_id=record_id,
        canonical_name=title,
        external_ids=identifiers,
        attributes={"authors": []},
        raw=raw,
        provenance={},
    )
    checksum = "a" * 64
    return _Occurrence(
        occurrence_id=f"{scope_id}:{provider}:{record_id}",
        scope_id=scope_id,
        atlas_field_id="hep-th" if scope_id == "hep" else "cond-mat",
        provider=typed_provider,
        record=record,
        normalized=normalized,
        page_reference=EvidenceReference(
            provider=provider,
            source_record_id=f"{scope_id}:{record_id}",
            checksum=checksum,
        ),
        page_path="pages/fixture",
        page_response_received_at=datetime(2026, 9, 4, tzinfo=UTC),
        strong_identifiers=identifiers,
        invalid_identifiers=(),
    )


def test_canonicalization_uses_only_exact_strong_ids_and_retains_conflicts() -> None:
    papers = _canonicalize(
        (
            _occurrence(
                scope_id="hep",
                provider="inspire",
                record_id="1",
                identifiers=(
                    ("inspire", "1"),
                    ("arxiv", "2001.00001"),
                    ("doi", "10.1/a"),
                ),
            ),
            _occurrence(
                scope_id="cond",
                provider="arxiv",
                record_id="2001.00001",
                identifiers=(
                    ("arxiv", "2001.00001"),
                    ("doi", "10.1/b"),
                ),
            ),
            _occurrence(
                scope_id="cond",
                provider="arxiv",
                record_id="2001.00002",
                identifiers=(("arxiv", "2001.00002"),),
            ),
        )
    )

    assert len(papers) == 2
    shared = next(item for item in papers if len(item.occurrences) == 2)
    assert {item.scope_id for item in shared.occurrences} == {"hep", "cond"}
    assert shared.identity_state == "conflicted"
    singleton = next(item for item in papers if len(item.occurrences) == 1)
    assert singleton.identity_state == "certified"


def test_citation_selection_retains_cross_provider_count_or_cutoff_conflict() -> None:
    first_cutoff = datetime(2026, 9, 4, 12, tzinfo=UTC)
    second_cutoff = first_cutoff + timedelta(seconds=1)

    def candidate(
        provider: str,
        raw_count: int,
        non_self_count: int,
        cutoff: datetime,
        checksum_character: str,
    ) -> _CitationCandidate:
        reference = EvidenceReference(
            provider=provider,
            source_record_id=f"{provider}:paper",
            checksum=checksum_character * 64,
        )
        evidence = CitationObservationEvidence(
            paper_id="paper-1",
            dataset_version=CERTIFICATION_ID,
            acquisition_scope=PAIR_ID,
            citation_source=provider,
            raw_citation_count=raw_count,
            non_self_citation_count=non_self_count,
            observed_at=cutoff,
            selected_cutoff=cutoff,
            publication_date=datetime(2020, 1, 13).date(),
            field_id="hep-th",
            document_type="article",
            source_reference=reference,
            citation_policy_version=CITATION_POLICY_VERSION,
        )
        certification = certify_citation_observation(evidence)
        return _CitationCandidate(
            certification=certification,
            reference=reference,
            provider=provider,
            raw_citation_count=raw_count,
        )

    first = candidate("inspire", 12, 10, first_cutoff, "a")
    conflicting = candidate("arxiv", 13, 11, second_cutoff, "b")

    selected, state, references, reasons = _select_citation_candidate(
        (first, conflicting)
    )

    assert selected is None
    assert state == "conflicted"
    assert set(references) == {first.reference, conflicting.reference}
    assert "disagree" in reasons[0]

    corroborating = candidate("arxiv", 12, 10, first_cutoff, "b")
    selected, state, references, reasons = _select_citation_candidate(
        (first, corroborating)
    )
    assert selected is not None
    assert state == "certified"
    assert set(references) == {first.reference, corroborating.reference}
    assert reasons == ()


def test_multi_field_citation_evidence_remains_explicitly_uncertified() -> None:
    occurrence = _occurrence(
        scope_id="hep",
        provider="inspire",
        record_id="citation-paper",
        identifiers=(("inspire", "citation-paper"),),
    )
    raw = {
        **occurrence.record.raw,
        "citation_count": 3,
        "citation_count_without_self_citations": 2,
        "preprint_date": "2020-01-13",
    }
    occurrence = replace(
        occurrence,
        record=replace(occurrence.record, raw=raw),
        normalized=replace(
            occurrence.normalized,
            raw=raw,
            attributes={"authors": [], "document_type": "article"},
        ),
    )
    paper = _canonicalize((occurrence,))[0]

    rows, certifications = _citation_rows(
        paper,
        {
            "assignments": [
                {"field_id": "hep-th", "weight": {"exact": "1/2"}},
                {"field_id": "math-ph", "weight": {"exact": "1/2"}},
            ],
            "certification_state": "needs_review",
        },
    )

    assert certifications == []
    assert len(rows) == 1
    assert rows[0]["certifier_invoked"] is False
    assert rows[0]["state"] == "insufficient_evidence"
    assert rows[0]["field_assignments"] == [
        {"field_id": "hep-th", "weight": {"exact": "1/2"}},
        {"field_id": "math-ph", "weight": {"exact": "1/2"}},
    ]


def test_bundle_traces_evidence_and_withholds_unreviewed_science(
    tmp_path: Path,
) -> None:
    (
        raw_root,
        raw_manifest,
        enrichment_root,
        enrichment_manifest,
        output,
        path,
    ) = _fixture_bundle(tmp_path)

    manifest = verify_paired_trial_certification_manifest(
        path,
        output=output,
        raw_root=raw_root,
        raw_manifest_path=raw_manifest,
        enrichment_root=enrichment_root,
        enrichment_manifest_path=enrichment_manifest,
    )
    _entry, report_path = _artifact(manifest, output, "report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    coverage = {item["evidence_kind"]: item for item in report["coverage"]}

    assert report["source_occurrence_count"] == 2
    assert report["canonical_paper_count"] == 2
    assert report["certified_complete_years"] == []
    assert report["certified_metric_windows"] == []
    assert report["metric_observations_created"] == 0
    assert report["joint_activation_gate"]["state"] == "withheld"
    assert report["projection_pipeline_version"].endswith("-v2")
    assert report["supersedes_certification_id"].endswith("-v1")
    assert report["institution_authority_version"].startswith("ror-authority-")
    assert report["provider_endpoints_official"] is False
    assert report["evidence_environment"] == "fixture-or-non-official-endpoint"
    assert manifest["provider_endpoints_official"] is False
    assert manifest["generator_rule_versions"] == sorted(
        manifest["generator_rule_versions"]
    )
    assert coverage["canonical-paper-identity"]["ratio"] == 1.0
    assert coverage["paper-time-affiliation"]["ratio"] == 1.0
    assert coverage["canonical-institution"]["certified_mass"]["exact"] == "0"
    assert coverage["canonical-institution"]["total_mass"]["exact"] == "2"
    assert coverage["field-classification"]["ratio"] == 0.0
    assert coverage["field-weight-conservation"]["ratio"] == 1.0
    assert coverage["publication-metric-date"]["ratio"] == 0.0
    assert coverage["researcher-identity"]["ratio"] == 0.0
    by_scope = {item["atlas_field_id"]: item for item in report["coverage_by_scope"]}
    assert set(by_scope) == {"hep-th", "cond-mat"}
    assert by_scope["hep-th"]["canonical_paper_count"] == 1
    assert by_scope["cond-mat"]["canonical_paper_count"] == 1
    assert report["shared_canonical_paper_count"] == 0
    for scope in by_scope.values():
        scope_coverage = {item["evidence_kind"]: item for item in scope["coverage"]}
        assert scope_coverage["field-weight-conservation"]["ratio"] == 1.0
        assert scope_coverage["field-classification"]["ratio"] == 0.0

    _entry, source_path = _artifact(manifest, output, "source-rows")
    source_rows = _jsonl(source_path)
    assert {item["raw"]["control_number"] for item in source_rows} == {1, 2}
    assert all(item["page_checksum"] for item in source_rows)

    _entry, field_path = _artifact(manifest, output, "field-ledgers")
    assert all(row["conservation_total"]["exact"] == "1" for row in _jsonl(field_path))
    _entry, shares_path = _artifact(manifest, output, "affiliation-shares")
    shares = _jsonl(shares_path)
    assert (
        sum(
            cast(int, item["mass"]["numerator"])
            / cast(int, item["mass"]["denominator"])
            for item in shares
        )
        == 2.0
    )
    assert any(item["institution_state"] == "insufficient_evidence" for item in shares)
    assert any(item["name_only_resolution_withheld"] is True for item in shares)
    assert all(
        item["institution_authority_version"] == report["institution_authority_version"]
        for item in shares
        if item["raw_affiliation"] is not None
    )
    assert all(item["eligible_for_metrics"] is False for item in shares)

    repeated, repeated_path = certify_paired_trial(
        raw_root=raw_root,
        raw_manifest_path=raw_manifest,
        enrichment_root=enrichment_root,
        enrichment_manifest_path=enrichment_manifest,
        output=output,
    )
    assert repeated_path == path
    assert repeated["manifest_checksum"] == manifest["manifest_checksum"]


def test_bundle_fails_closed_on_single_affiliation_ror_disagreement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = BaseCaptureFixtureTransport._inspire_hit

    def conflicting_inspire_hit(
        transport: BaseCaptureFixtureTransport, is_cond_mat: bool
    ) -> dict[str, Any]:
        hit = original(transport, is_cond_mat)
        if not is_cond_mat:
            exact_author = hit["metadata"]["authors"][0]
            exact_author["affiliations"][0]["identifiers"] = [
                {"schema": "ROR", "value": "https://ror.org/02bbbbbbb"}
            ]
        return hit

    monkeypatch.setattr(
        BaseCaptureFixtureTransport, "_inspire_hit", conflicting_inspire_hit
    )
    (
        _raw_root,
        _raw_manifest,
        _enrichment_root,
        _enrichment_manifest,
        output,
        path,
    ) = _fixture_bundle(tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _entry, shares_path = _artifact(manifest, output, "affiliation-shares")
    share = next(
        item
        for item in _jsonl(shares_path)
        if item.get("raw_name") == "Institution 101"
    )

    assert share["affiliation_local_ror_ids"] == ["02bbbbbbb"]
    assert share["author_level_ror_ids"] == ["01aaaaaaa"]
    assert share["direct_ror_ids"] == ["01aaaaaaa", "02bbbbbbb"]
    assert share["ror_alignment"] == (
        "conflicted-single-affiliation-local-vs-author-ror"
    )
    assert share["same_source_ror_conflict"] is True
    assert share["paper_time_affiliation_state"] == "conflicted"
    assert share["institution_state"] == "conflicted"
    assert share["canonical_institution_id"] is None


def test_recomputed_verifier_rejects_a_resigned_false_activation(
    tmp_path: Path,
) -> None:
    (
        raw_root,
        raw_manifest,
        enrichment_root,
        enrichment_manifest,
        output,
        path,
    ) = _fixture_bundle(tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    report_entry, report_path = _artifact(manifest, output, "report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["metric_observations_created"] = 1
    tampered_payload = _canonical_json(report, pretty=True)
    tampered_checksum = hashlib.sha256(tampered_payload).hexdigest()
    tampered_relative = Path("artifacts") / "report" / f"{tampered_checksum}.json"
    tampered_path = output / tampered_relative
    tampered_path.parent.mkdir(parents=True, exist_ok=True)
    tampered_path.write_bytes(tampered_payload)
    report_entry.update(
        {
            "path": tampered_relative.as_posix(),
            "checksum": tampered_checksum,
            "byte_count": len(tampered_payload),
        }
    )
    manifest["artifact_set_checksum"] = _checksum(
        [(item["role"], item["checksum"]) for item in manifest["artifacts"]]
    )
    manifest.pop("manifest_checksum")
    manifest_checksum = _checksum(manifest)
    manifest["manifest_checksum"] = manifest_checksum
    resigned = output / "manifests" / f"{manifest_checksum}.json"
    resigned.write_bytes(_canonical_json(manifest, pretty=True))

    with pytest.raises(PairedTrialCertificationError, match="recomputation"):
        verify_paired_trial_certification_manifest(
            resigned,
            output=output,
            raw_root=raw_root,
            raw_manifest_path=raw_manifest,
            enrichment_root=enrichment_root,
            enrichment_manifest_path=enrichment_manifest,
        )


def test_verifier_rejects_missing_or_mutated_content_addressed_artifact(
    tmp_path: Path,
) -> None:
    (
        raw_root,
        raw_manifest,
        enrichment_root,
        enrichment_manifest,
        output,
        path,
    ) = _fixture_bundle(tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _entry, decisions_path = _artifact(manifest, output, "decisions")
    decisions_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(PairedTrialCertificationError, match="recomputation"):
        verify_paired_trial_certification_manifest(
            path,
            output=output,
            raw_root=raw_root,
            raw_manifest_path=raw_manifest,
            enrichment_root=enrichment_root,
            enrichment_manifest_path=enrichment_manifest,
        )
