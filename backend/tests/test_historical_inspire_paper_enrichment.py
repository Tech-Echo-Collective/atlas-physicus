import hashlib
import json
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from physics_atlas_api.historical_inspire_paper_enrichment import (
    acquire_inspire_paper_records,
    build_inspire_paper_target_manifest,
    materialize_paper_time_affiliation_enrichment,
    write_inspire_paper_target_manifest,
)
from physics_atlas_api.historical_ror import _checksum

_CAPTURED = datetime(2026, 9, 4, 8, 0, tzinfo=UTC)


def _weight(numerator: int, denominator: int = 1) -> dict[str, int | str]:
    value = Fraction(numerator, denominator)
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "exact": f"{value.numerator}/{value.denominator}",
    }


def _fraction(payload: dict[str, Any]) -> Fraction:
    return Fraction(int(payload["numerator"]), int(payload["denominator"]))


def _component(candidate_id: str, arxiv_id: str, authors: list[str]) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "status": "matched",
        "occurrences": [
            {
                "provider": "arxiv",
                "source_record_id": arxiv_id,
                "occurrence_id": f"arxiv:{arxiv_id}",
                "authors": authors,
            }
        ],
    }


def _share(
    candidate_id: str,
    position: int,
    *,
    evidence: bool,
    denominator: int,
    affiliation: str | None = None,
    share_suffix: str | None = None,
) -> dict[str, Any]:
    share_id = f"share-{candidate_id}-{position}"
    if share_suffix is not None:
        share_id = f"{share_id}-{share_suffix}"
    raw_affiliations = (
        [{"value": affiliation or f"Existing {candidate_id}-{position}"}]
        if evidence
        else []
    )
    return {
        "candidate_id": candidate_id,
        "paper_time_affiliation_share_id": share_id,
        "author_position": position,
        "affiliation_assertion_ids": (
            [f"existing-assertion-{candidate_id}-{position}-{share_suffix or 'only'}"]
            if evidence
            else []
        ),
        "raw_affiliations": raw_affiliations,
        "resolution_evidence": [
            {"raw_affiliation": raw_affiliation} for raw_affiliation in raw_affiliations
        ],
        "attribution_weight": _weight(1, denominator),
    }


def _write_replay(
    root: Path,
    components: list[dict[str, Any]],
    shares: list[dict[str, Any]],
) -> Path:
    occurrence_by_candidate = {
        str(component["candidate_id"]): component["occurrences"][0].get("occurrence_id")
        for component in components
    }
    shares = [
        {
            **share,
            "paper_identity_status": "matched",
            "source_occurrence_id": occurrence_by_candidate.get(
                str(share["candidate_id"])
            ),
        }
        for share in shares
    ]
    share_candidates = {str(share["candidate_id"]) for share in shares}
    ledgers = []
    for candidate_id in sorted(share_candidates):
        candidate_shares = [
            share for share in shares if share["candidate_id"] == candidate_id
        ]
        total_weight = sum(
            (
                Fraction(
                    int(share["attribution_weight"]["numerator"]),
                    int(share["attribution_weight"]["denominator"]),
                )
                for share in candidate_shares
            ),
            start=Fraction(0),
        )
        ledgers.append(
            {
                "candidate_id": candidate_id,
                "total_weight": _weight(
                    total_weight.numerator, total_weight.denominator
                ),
                "unmaterialized_paper_mass": _weight(0),
            }
        )
    artifacts = []
    for role, directory, rows in (
        ("paper-components", "papers", components),
        ("paper-time-affiliation-shares", "relationships/affiliations", shares),
        ("fractional-attribution-ledgers", "relationships/attribution", ledgers),
    ):
        payload = b"".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n"
            for row in rows
        )
        checksum = hashlib.sha256(payload).hexdigest()
        relative = Path(directory) / f"{checksum}.jsonl"
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        artifacts.append(
            {
                "role": role,
                "path": relative.as_posix(),
                "checksum": checksum,
                "row_count": len(rows),
                "byte_count": len(payload),
            }
        )
    manifest: dict[str, Any] = {
        "bundle_version": "hep-th-v1-historical-replay-bundle-v1",
        "source_manifest_checksum": "source-manifest-checksum",
        "network_access": False,
        "database_access": False,
        "metric_observations_created": 0,
        "artifacts": artifacts,
    }
    manifest["bundle_manifest_checksum"] = _checksum(manifest)
    path = root / "manifests" / f"{manifest['bundle_manifest_checksum']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return path


def _enrichment_rows(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    artifact = manifest["artifact"]
    path = root / str(artifact["path"])
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _replay_snapshot(manifest_path: Path) -> dict[Path, bytes]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent.parent
    paths = [manifest_path]
    paths.extend(root / str(artifact["path"]) for artifact in manifest["artifacts"])
    return {path: path.read_bytes() for path in paths}


class ExactPaperTransport:
    def __init__(self, payload_by_id: dict[str, dict[str, Any]]):
        self.payload_by_id = payload_by_id
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
        del headers
        self.calls.append((url, params))
        assert params is not None
        arxiv_id = str(params["q"]).removeprefix("arxiv:")
        return self.payload_by_id[arxiv_id]

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        del url, params, headers
        raise AssertionError("paper enrichment uses JSON only")


def _hit(
    arxiv_id: str,
    authors: list[tuple[str, list[str]]],
    *,
    record_id: str = "12345",
) -> dict[str, Any]:
    return {
        "id": record_id,
        "metadata": {
            "arxiv_eprints": [{"value": arxiv_id}],
            "authors": [
                {
                    "full_name": name,
                    "affiliations": [{"value": affiliation} for affiliation in affs],
                    "raw_affiliations": [],
                }
                for name, affs in authors
            ],
        },
    }


def _response(*hits: dict[str, Any], total: int | None = None) -> dict[str, Any]:
    return {
        "hits": {"total": len(hits) if total is None else total, "hits": list(hits)}
    }


def test_targeting_is_existing_arxiv_only_and_mass_prioritized(tmp_path: Path) -> None:
    replay = _write_replay(
        tmp_path / "replay",
        [
            _component("paper-a", "2001.00001", ["Alpha, Alice", "Beta, Bob"]),
            _component("paper-b", "2001.00002", ["Gamma, Grace", "Delta, Dan"]),
            {
                **_component("paper-inspire", "2001.00003", ["Other, One"]),
                "occurrences": [
                    {
                        "provider": "inspire",
                        "source_record_id": "99",
                        "authors": ["Other, One"],
                    }
                ],
            },
        ],
        [
            _share("paper-a", 1, evidence=False, denominator=2),
            _share("paper-a", 2, evidence=False, denominator=2),
            _share("paper-b", 1, evidence=True, denominator=2),
            _share("paper-b", 2, evidence=False, denominator=2),
            _share("paper-inspire", 1, evidence=False, denominator=1),
        ],
    )

    target = build_inspire_paper_target_manifest(replay)

    assert [row["arxiv_id"] for row in target["targets"]] == [
        "2001.00001",
        "2001.00002",
    ]
    assert target["target_missing_attribution_mass"] == _weight(3, 2)
    assert target["canonical_corpus_widening"] is False


def test_exact_prefix_preserves_outcomes_and_recovers_only_missing_slots(
    tmp_path: Path,
) -> None:
    replay = _write_replay(
        tmp_path / "replay",
        [
            _component("paper-a", "2001.00001", ["Alice Alpha", "Bob Beta"]),
            _component("paper-b", "2001.00002", ["Grace Gamma", "Ben Baseline"]),
            _component("paper-c", "2001.00003", ["Casey Conflict", "Chris Baseline"]),
        ],
        [
            _share(
                "paper-a",
                1,
                evidence=True,
                denominator=2,
                affiliation="Existing A",
            ),
            _share("paper-a", 2, evidence=False, denominator=2),
            _share("paper-b", 1, evidence=False, denominator=2),
            _share("paper-b", 2, evidence=True, denominator=2),
            _share("paper-c", 1, evidence=False, denominator=2),
            _share("paper-c", 2, evidence=True, denominator=2),
        ],
    )
    output = tmp_path / "paper-evidence"
    target_path, _target = write_inspire_paper_target_manifest(replay, output)
    transport = ExactPaperTransport(
        {
            "2001.00001": _response(
                _hit(
                    "2001.00001",
                    [("Alpha, Alice", ["Existing A"]), ("Beta, Bob", ["Recovered B"])],
                )
            ),
            "2001.00002": _response(),
            "2001.00003": _response(
                _hit(
                    "2001.00003",
                    [
                        ("Wrong Person", ["Unsafe affiliation"]),
                        ("Baseline, Chris", ["Existing C"]),
                    ],
                )
            ),
        }
    )

    first_path, first = acquire_inspire_paper_records(
        target_path,
        output,
        transport,
        max_new_records=2,
        base_url="https://inspire.test/api",
        now=lambda: _CAPTURED,
    )
    assert first["terminal_status"] == "paused-limit"
    assert first["records_completed"] == 2
    first_enrichment_path, first_enrichment = (
        materialize_paper_time_affiliation_enrichment(replay, first_path, output)
    )
    assert first_enrichment_path.is_file()
    assert first_enrichment["outcome_status_counts"] == {"no-hit": 1, "recovered": 1}
    assert first_enrichment["recovered_share_count"] == 1
    assert first_enrichment["baseline_affiliation_evidence_mass"] == _weight(3, 2)
    assert first_enrichment["recovered_affiliation_evidence_mass"] == _weight(1, 2)
    assert first_enrichment["corroborated_existing_affiliation_mass"] == _weight(1, 2)
    assert first_enrichment["higher_precedence_superseded_affiliation_mass"] == _weight(
        1, 2
    )
    assert first_enrichment["unresolved_cross_provider_conflict_mass"] == _weight(0)
    assert first_enrichment["cross_provider_classification_counts"] == {
        "corroborated": 1,
        "formerly-missing-recovered": 1,
    }
    assert first_enrichment["combined_affiliation_evidence_mass"] == _weight(2)
    first_rows = _enrichment_rows(output, first_enrichment)
    exact = next(row for row in first_rows if row["arxivId"] == "2001.00001")
    assert (
        exact["positionalAffiliationEvidence"][0]["crossProviderClassification"]
        == "corroborated"
    )
    assert (
        exact["positionalAffiliationEvidence"][0]["precedenceDisposition"]
        == "inspire-supersedes-corroborated-arxiv"
    )
    assert exact["positionalAffiliationEvidence"][0][
        "inspirePaperNativeAffiliationEvidence"
    ]["affiliations"] == [{"value": "Existing A"}]

    second_path, second = acquire_inspire_paper_records(
        target_path,
        output,
        transport,
        max_new_records=1,
        base_url="https://inspire.test/api",
        now=lambda: _CAPTURED,
    )
    assert second["acquisition_complete"] is True
    assert [params for _url, params in transport.calls] == [
        {"q": "arxiv:2001.00001", "size": 2},
        {"q": "arxiv:2001.00002", "size": 2},
        {"q": "arxiv:2001.00003", "size": 2},
    ]
    _path, enrichment = materialize_paper_time_affiliation_enrichment(
        replay, second_path, output
    )
    assert enrichment["outcome_status_counts"] == {
        "conflict-author-order-or-name": 1,
        "no-hit": 1,
        "recovered": 1,
    }
    assert enrichment["combined_affiliation_coverage"] == _weight(2, 3)
    assert enrichment["canonical_corpus_widening"] is False
    assert enrichment["metric_observations_created"] == 0


def test_multi_affiliation_slots_preserve_each_share_and_recover_only_missing_mass(
    tmp_path: Path,
) -> None:
    replay = _write_replay(
        tmp_path / "replay",
        [_component("paper-a", "2001.00001", ["Alice Alpha", "Bob Beta"])],
        [
            _share(
                "paper-a",
                1,
                evidence=True,
                denominator=4,
                affiliation="Alpha Laboratory",
                share_suffix="alpha",
            ),
            _share(
                "paper-a",
                1,
                evidence=True,
                denominator=4,
                affiliation="Beta Laboratory",
                share_suffix="beta",
            ),
            _share("paper-a", 2, evidence=False, denominator=2),
        ],
    )
    baseline_snapshot = _replay_snapshot(replay)
    output = tmp_path / "paper-evidence"
    target_path, target = write_inspire_paper_target_manifest(replay, output)
    assert target["target_missing_attribution_mass"] == _weight(1, 2)
    transport = ExactPaperTransport(
        {
            "2001.00001": _response(
                _hit(
                    "2001.00001",
                    [
                        ("Alpha, Alice", ["Alpha Laboratory", "Beta Laboratory"]),
                        ("Beta, Bob", ["Recovered Laboratory"]),
                    ],
                )
            )
        }
    )
    acquisition_path, acquisition = acquire_inspire_paper_records(
        target_path,
        output,
        transport,
        base_url="https://inspire.test/api",
        now=lambda: _CAPTURED,
    )
    assert acquisition["acquisition_complete"] is True

    _path, enrichment = materialize_paper_time_affiliation_enrichment(
        replay, acquisition_path, output
    )

    assert enrichment["outcome_status_counts"] == {"recovered": 1}
    assert enrichment["cross_provider_classification_counts"] == {
        "corroborated": 1,
        "formerly-missing-recovered": 1,
    }
    assert enrichment["recovered_share_count"] == 1
    assert enrichment["baseline_affiliation_evidence_mass"] == _weight(1, 2)
    assert enrichment["recovered_affiliation_evidence_mass"] == _weight(1, 2)
    assert enrichment["corroborated_existing_affiliation_mass"] == _weight(1, 2)
    assert enrichment["higher_precedence_superseded_affiliation_mass"] == _weight(1, 2)
    assert enrichment["combined_affiliation_coverage"] == _weight(1)
    rows = _enrichment_rows(output, enrichment)
    assert len(rows) == 1
    positions = {
        item["authorPosition"]: item
        for item in rows[0]["positionalAffiliationEvidence"]
    }
    assert positions[1]["authorSlotAttributionMass"] == _weight(1, 2)
    assert [
        item["paperTimeAffiliationShareId"]
        for item in positions[1]["baselineArxivShares"]
    ] == ["share-paper-a-1-alpha", "share-paper-a-1-beta"]
    assert [
        item["attributionWeight"] for item in positions[1]["baselineArxivShares"]
    ] == [_weight(1, 4), _weight(1, 4)]
    assert positions[1]["crossProviderClassification"] == "corroborated"
    assert positions[1]["eligibleForCanonicalResolution"] is True
    assert positions[2]["crossProviderClassification"] == ("formerly-missing-recovered")
    assert [item["authorPosition"] for item in rows[0]["recoveredShares"]] == [2]
    assert _replay_snapshot(replay) == baseline_snapshot


def test_cross_provider_conflict_stays_unresolved_while_missing_slot_recovers(
    tmp_path: Path,
) -> None:
    replay = _write_replay(
        tmp_path / "replay",
        [_component("paper-a", "2001.00001", ["Alice Alpha", "Bob Beta"])],
        [
            _share(
                "paper-a",
                1,
                evidence=True,
                denominator=2,
                affiliation="arXiv Institute",
            ),
            _share("paper-a", 2, evidence=False, denominator=2),
        ],
    )
    baseline_snapshot = _replay_snapshot(replay)
    output = tmp_path / "paper-evidence"
    target_path, _target = write_inspire_paper_target_manifest(replay, output)
    transport = ExactPaperTransport(
        {
            "2001.00001": _response(
                _hit(
                    "2001.00001",
                    [
                        ("Alpha, Alice", ["Different INSPIRE Institute"]),
                        ("Beta, Bob", ["Recovered Institute"]),
                    ],
                )
            )
        }
    )
    acquisition_path, _acquisition = acquire_inspire_paper_records(
        target_path,
        output,
        transport,
        base_url="https://inspire.test/api",
        now=lambda: _CAPTURED,
    )

    _path, enrichment = materialize_paper_time_affiliation_enrichment(
        replay, acquisition_path, output
    )

    assert enrichment["outcome_status_counts"] == {"unresolved-affiliation-conflict": 1}
    assert enrichment["cross_provider_classification_counts"] == {
        "conflict": 1,
        "formerly-missing-recovered": 1,
    }
    assert enrichment["recovered_share_count"] == 1
    assert enrichment["recovered_affiliation_evidence_mass"] == _weight(1, 2)
    assert enrichment["unresolved_cross_provider_conflict_mass"] == _weight(1, 2)
    # The assertion still counts as paper-time evidence, but the independent
    # resolution partition withholds its exact mass from canonical resolution.
    assert enrichment["combined_affiliation_evidence_mass"] == _weight(1)
    assert enrichment["combined_affiliation_coverage"] == _weight(1)
    assert enrichment["combined_nonconflicting_affiliation_evidence_mass"] == _weight(
        1, 2
    )
    assert enrichment["combined_missing_affiliation_mass"] == _weight(0)
    assert enrichment["combined_unresolved_affiliation_mass"] == _weight(1, 2)
    assert enrichment["affiliation_evidence_mass_conservation_passed"] is True
    assert enrichment["affiliation_resolution_partition_conservation_passed"] is True
    assert _fraction(enrichment["combined_affiliation_evidence_mass"]) + _fraction(
        enrichment["combined_missing_affiliation_mass"]
    ) + _fraction(enrichment["unmaterialized_paper_mass"]) == _fraction(
        enrichment["expected_paper_mass"]
    )
    assert _fraction(
        enrichment["combined_nonconflicting_affiliation_evidence_mass"]
    ) + _fraction(enrichment["combined_unresolved_affiliation_mass"]) + _fraction(
        enrichment["unmaterialized_paper_mass"]
    ) == _fraction(enrichment["expected_paper_mass"])
    rows = _enrichment_rows(output, enrichment)
    assert rows[0]["existingAffiliationEvidenceReplaced"] is False
    positions = {
        item["authorPosition"]: item
        for item in rows[0]["positionalAffiliationEvidence"]
    }
    assert positions[1]["crossProviderClassification"] == "conflict"
    assert positions[1]["precedenceDisposition"] == "unresolved-source-conflict"
    assert positions[1]["evidenceSelectionStatus"] == "unresolved-conflict"
    assert positions[1]["eligibleForCanonicalResolution"] is False
    assert positions[1]["inspirePaperNativeAffiliationEvidence"]["affiliations"] == [
        {"value": "Different INSPIRE Institute"}
    ]
    assert [item["authorPosition"] for item in rows[0]["recoveredShares"]] == [2]
    assert enrichment["immutable_baseline_modified"] is False
    assert _replay_snapshot(replay) == baseline_snapshot


def test_multiple_and_nonexact_hits_remain_conflicts(tmp_path: Path) -> None:
    replay = _write_replay(
        tmp_path / "replay",
        [
            _component("paper-a", "2001.00001", ["Alice Alpha"]),
            _component("paper-b", "2001.00002", ["Bob Beta"]),
        ],
        [
            _share("paper-a", 1, evidence=False, denominator=1),
            _share("paper-b", 1, evidence=False, denominator=1),
        ],
    )
    output = tmp_path / "paper-evidence"
    target_path, _target = write_inspire_paper_target_manifest(replay, output)
    transport = ExactPaperTransport(
        {
            "2001.00001": _response(
                _hit("2001.00001", [("Alice Alpha", ["A"])]),
                _hit("2001.00001", [("Alice Alpha", ["B"])], record_id="54321"),
            ),
            "2001.00002": _response(_hit("2001.99999", [("Bob Beta", ["Unsafe"])])),
        }
    )
    acquisition_path, acquisition = acquire_inspire_paper_records(
        target_path,
        output,
        transport,
        base_url="https://inspire.test/api",
        now=lambda: _CAPTURED,
    )
    assert acquisition["acquisition_complete"] is True

    _path, enrichment = materialize_paper_time_affiliation_enrichment(
        replay, acquisition_path, output
    )
    assert enrichment["outcome_status_counts"] == {
        "conflict-multiple-hits": 1,
        "conflict-nonexact-hit": 1,
    }
    assert enrichment["recovered_affiliation_evidence_mass"] == _weight(0)
    assert enrichment["mass_conservation_passed"] is True
