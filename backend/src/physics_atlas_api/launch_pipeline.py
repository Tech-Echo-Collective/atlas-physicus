"""Bounded launch orchestration; not imported by the production ingestion path.

Only this task's trusted private checkpoints are consumed. Every scientific step
uses the existing source-bound certification implementation. Raw responses are
discarded; expanded proof objects are ephemeral and never a release artifact.
"""

from __future__ import annotations

import argparse
import gzip
import json
import pickle
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlencode
from uuid import uuid4

from .certification.build_cache import bounded_build_verification_cache
from .certification.citation_sessions import (
    CitationMeasurementSession,
    CitationSessionPage,
    capture_citation_session_page,
    explicit_citation_id_query,
)
from .certification.contracts import CertificationError
from .certification.launch_attribution import LaunchAttributionResult
from .certification.launch_calculations import (
    NoEligibleLaunchPeers,
    calculate_launch_metric_cohort,
    certify_launch_citation_coverage,
)
from .certification.launch_capture import CapturedLaunchYear
from .certification.launch_inputs import (
    LaunchCanonicalInputs,
    canonicalize_launch_inputs,
)
from .certification.launch_metric_coverage import certify_launch_source_coverage
from .certification.launch_scope import (
    BOUNDED_LAUNCH_DATE_BASIS,
    BOUNDED_LAUNCH_SCOPE,
    BOUNDED_LAUNCH_YEARS,
)
from .certification.launch_years import build_launch_source_year
from .certification.measurement_windows import (
    CertifiedObservedSessionCitationCohort,
    CertifiedSessionCitationCohort,
    FrozenScientificCitationPopulation,
)
from .certification.years import (
    ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
    CertifiedSourceYear,
    certify_metric_window,
    qualify_observed_release_source_year,
    source_quality_certification,
)
from .connectors.acquisition import AcquisitionScope
from .connectors.inspire import InspireConnector
from .fields import PHYSICS_FIELD_ONTOLOGY_V1
from .launch_build import (
    MAX_EPHEMERAL_BYTES,
    LaunchTransport,
    _publish_checkpoint,
    _storage_bytes,
    _write_checkpoint,
)
from .metrics.aggregation import (
    aggregate_ontology_branch,
    certify_field_population,
    derive_ontology_branch_population,
)
from .metrics.contracts import CANDIDATE_METRIC_IDS
from .metrics.presentation import AtlasScaleObservation, apply_atlas_scale
from .metrics.thresholds import METRIC_VALIDATION_THRESHOLDS_V1


@dataclass(frozen=True)
class PreparedLaunch:
    captured: tuple[CapturedLaunchYear, ...]
    attributions: tuple[LaunchAttributionResult, ...]
    canonical: LaunchCanonicalInputs
    source_years: tuple[CertifiedSourceYear, ...]
    frozen_populations: tuple[FrozenScientificCitationPopulation, ...]


@dataclass(frozen=True)
class CalculatedLaunch:
    prepared: PreparedLaunch
    sessions: tuple[CitationMeasurementSession, ...]
    citation_cohorts: tuple[CertifiedSessionCitationCohort, ...]
    observations: tuple[AtlasScaleObservation, ...]
    diagnostics: tuple[dict[str, object], ...]


def _private_root(root: Path) -> Path:
    result = root.resolve(strict=True)
    if (
        root.is_symlink()
        or result.parent != Path("/private/tmp")
        or not result.name.startswith("atlas-live-launch.")
        or not result.is_dir()
        or result.stat().st_mode & 0o077
    ):
        raise ValueError("only the explicit owner-private ephemeral root is accepted")
    return result


def _load(root: Path, name: str) -> object:
    source = root / name
    if source.parent != root or source.is_symlink() or not source.is_file():
        raise ValueError("trusted launch checkpoint missing or outside private root")
    with gzip.open(source, "rb") as stream:
        return pickle.load(stream)  # noqa: S301 -- task-owned private state, never external input


def _progress(stage: str, **values: object) -> None:
    print(json.dumps({"stage": stage, **values}, default=str), flush=True)


def prepare(root: Path) -> None:
    root = _private_root(root)
    if any(
        (root / name).exists() or (root / name).is_symlink()
        for name in ("prepared-launch.pickle.gz", "prepared-launch-summary.json")
    ):
        raise ValueError("prepared launch already exists; do not overwrite its freeze")
    captured: list[CapturedLaunchYear] = []
    attributions: list[LaunchAttributionResult] = []
    for year in BOUNDED_LAUNCH_YEARS:
        value = _load(root, f"source-{year}.pickle.gz")
        if not isinstance(value, tuple) or len(value) != 2:
            raise CertificationError("invalid owner-produced launch checkpoint")
        source, attributed = value
        if not isinstance(source, CapturedLaunchYear) or not isinstance(
            attributed, tuple
        ):
            raise CertificationError("launch checkpoint has unexpected types")
        if source.plan.calendar_year != year or any(
            not isinstance(item, LaunchAttributionResult) for item in attributed
        ):
            raise CertificationError("launch checkpoint scope differs")
        captured.append(source)
        attributions.extend(attributed)
    cutoff = datetime.now(UTC)
    canonical = canonicalize_launch_inputs(
        tuple(item for source in captured for item in source.occurrences)
    )
    _progress("canonical-six-years", papers=len(canonical.papers))
    years: list[CertifiedSourceYear] = []
    summaries: list[dict[str, object]] = []
    with bounded_build_verification_cache(
        maximum_entries=20_000, maximum_key_nodes=1_000_000, stream_large_keys=True
    ) as cache:
        for entity_type in ("institution", "country"):
            for source in captured:
                build = build_launch_source_year(
                    source,
                    canonical,
                    tuple(attributions),
                    entity_type=entity_type,
                    evidence_cutoff=cutoff,
                    identity_completeness_policy=ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
                )
                if build.source_year is None:
                    raise CertificationError(
                        f"source membership unavailable: {build.blockers}"
                    )
                covered = certify_launch_source_coverage(build)
                qualified = qualify_observed_release_source_year(covered.source_year)
                if qualified.state != "certified":
                    raise CertificationError(
                        "conditional source enumeration is not certified"
                    )
                quality = source_quality_certification(qualified)
                summary: dict[str, object] = {
                    "year": source.plan.calendar_year,
                    "entityType": entity_type,
                    "counts": build.measured_counts,
                    "sourceQualityState": quality.state,
                    "sourceQualityReasons": quality.reasons,
                    "coverage": covered.measured_coverage,
                }
                summaries.append(summary)
                years.append(qualified)
                _progress("qualified-source-year", **summary, cache=asdict(cache.stats))
        frozen_at = datetime.now(UTC)
        populations = tuple(
            FrozenScientificCitationPopulation(
                tuple(item for item in years if item.evidence.entity_type == kind),
                frozen_at,
                BOUNDED_LAUNCH_DATE_BASIS,
            )
            for kind in ("institution", "country")
        )
        inventories = [
            item.measurement_population.provider_to_canonical for item in populations
        ]
        if inventories[0] != inventories[1]:
            raise CertificationError(
                "country and institution citation identities differ"
            )
        prepared = PreparedLaunch(
            tuple(captured), tuple(attributions), canonical, tuple(years), populations
        )
        size = _write_checkpoint(root, root / "prepared-launch.pickle.gz", prepared)
        (root / "prepared-launch-summary.json").write_text(
            json.dumps(summaries, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        _progress(
            "prepared-launch", checkpointBytes=size, citationIds=len(inventories[0])
        )


def capture_citations(root: Path) -> None:
    root = _private_root(root)
    prepared = _load(root, "prepared-launch.pickle.gz")
    if not isinstance(prepared, PreparedLaunch):
        raise CertificationError("a certified frozen launch is required")
    if any(
        (root / name).exists() or (root / name).is_symlink()
        for name in ("measured-citations.pickle.gz",)
    ):
        raise ValueError(
            "measured citation state already exists; never overwrite a cutoff"
        )
    with bounded_build_verification_cache(
        maximum_entries=20_000, maximum_key_nodes=1_000_000, stream_large_keys=True
    ):
        populations = prepared.frozen_populations
        for population in populations:
            population.__post_init__()
        pairs = populations[0].measurement_population.provider_to_canonical
        if any(
            item.measurement_population.provider_to_canonical != pairs
            for item in populations
        ):
            raise CertificationError("frozen citation identity inventories differ")
        # Failed attempts retain their actual requests without preventing a fresh
        # measurement over the same frozen population. Completed sessions remain
        # immutable, and no partial earlier page enters the next attempt.
        receipt_path = root / f"citation-acquisition-receipts-{uuid4().hex}.json"
        transport = LaunchTransport()
        connector = InspireConnector(
            transport,  # type: ignore[arg-type]
            "https://inspirehep.net/api",
            acquisition_scope=AcquisitionScope(BOUNDED_LAUNCH_SCOPE, "", ""),
        )
        pages: list[CitationSessionPage] = []
        try:
            for offset in range(0, len(pairs), 250):
                batch = pairs[offset : offset + 250]
                ids = tuple(identifier for identifier, _ in batch)
                uri = "https://inspirehep.net/api/literature?" + urlencode(
                    {
                        "q": explicit_citation_id_query(ids),
                        "page": 1,
                        "size": 250,
                        "fields": (
                            "control_number,preprint_date,document_type,arxiv_eprints,"
                            "inspire_categories,citation_count,citation_count_without_self_citations"
                        ),
                    }
                )
                response = transport.fetch(uri)
                page = capture_citation_session_page(
                    response.payload,
                    connector=connector,
                    request_url=uri,
                    requested_at=response.requested_at,
                    received_at=response.received_at,
                    dataset_version=prepared.source_years[0].dataset_version,
                    calendar_year=2018,
                    end_calendar_year=2023,
                    declared_date_basis=BOUNDED_LAUNCH_DATE_BASIS,
                    source_snapshot_id=f"launch-citation:{response.requested_at.isoformat()}:{offset}",
                    canonical_paper_ids=dict(batch),
                    expected_source_ids=ids,
                )
                pages.append(page)
                del response
                _progress(
                    "citation-measurement",
                    measured=offset + len(batch),
                    total=len(pairs),
                )
            sessions = tuple(
                CitationMeasurementSession(tuple(pages), item.measurement_population)
                for item in populations
            )
            size = _write_checkpoint(
                root, root / "measured-citations.pickle.gz", sessions
            )
            _progress(
                "citation-session-complete",
                checkpointBytes=size,
                pages=len(pages),
                measured=len(pairs),
                nonSelfCounts=sum(
                    row.non_self_citation_count is not None
                    for page in pages
                    for row in page.records
                ),
                startedAt=sessions[0].measurement_started_at,
                finishedAt=sessions[0].measurement_finished_at,
            )
        finally:
            transport.client.close()
            with receipt_path.open("x", encoding="utf-8") as stream:
                json.dump(transport.receipts, stream, separators=(",", ":"))


def calculate(root: Path) -> None:
    """Evaluate all exact peers; unsupported evidence stays explicit, not zero."""
    root = _private_root(root)
    if any(
        (root / name).exists() or (root / name).is_symlink()
        for name in ("calculated-launch.pickle.gz", "calculated-launch-summary.json")
    ):
        raise ValueError("calculated launch already exists; never overwrite evidence")
    prepared = _load(root, "prepared-launch.pickle.gz")
    sessions = _load(root, "measured-citations.pickle.gz")
    if (
        not isinstance(prepared, PreparedLaunch)
        or not isinstance(sessions, tuple)
        or len(sessions) != len(prepared.frozen_populations)
        or any(not isinstance(item, CitationMeasurementSession) for item in sessions)
    ):
        raise CertificationError("exact prepared source and measured sessions required")
    diagnostics: list[dict[str, object]] = []
    observations: list[AtlasScaleObservation] = []
    all_cohorts: list[CertifiedSessionCitationCohort] = []
    horizon = datetime.now(UTC)
    with bounded_build_verification_cache(
        maximum_entries=20_000, maximum_key_nodes=1_000_000, stream_large_keys=True
    ) as cache:
        # Exercise the global-map release path before the larger institution
        # cohort. This changes scheduling only, not any frozen inventory or rule.
        for population, session in sorted(
            zip(prepared.frozen_populations, sessions, strict=True),
            key=lambda pair: pair[0].source_years[0].evidence.entity_type != "country",
        ):
            entity_type = population.source_years[0].evidence.entity_type
            cohorts: list[CertifiedSessionCitationCohort] = []
            for year in BOUNDED_LAUNCH_YEARS:
                for field in ("nucl-th", "nucl-ex"):
                    _progress(
                        "certifying-reference-cohort",
                        entityType=entity_type,
                        year=year,
                        field=field,
                    )
                    try:
                        cohort = CertifiedObservedSessionCitationCohort(
                            population, session, (field, year, "article")
                        )
                    except CertificationError as error:
                        # Explicit proof rejection is reported for review. No
                        # invalid cohort or fabricated count reaches a calculator.
                        diagnostic = {
                            "kind": "citation-cohort-rejected",
                            "entityType": entity_type,
                            "year": year,
                            "field": field,
                            "reason": str(error),
                        }
                        diagnostics.append(diagnostic)
                        _progress("citation-cohort-rejected", **diagnostic)
                    else:
                        cohorts.append(cohort)
                        _progress(
                            "citation-cohort-certified",
                            entityType=entity_type,
                            year=year,
                            field=field,
                            referenceCoverage=cohort.reference_population_metadata,
                        )
            all_cohorts.extend(cohorts)
            citation_years = (
                tuple(
                    certify_launch_citation_coverage(
                        year, tuple(cohorts), evaluation_cutoff=horizon
                    )
                    for year in population.source_years
                )
                if cohorts
                else ()
            )
            # Prove current exact-five availability first; then retain every
            # supported earlier closed three-year observation for the timeline.
            for terminal in (2023, 2020, 2021, 2022):
                for metric in CANDIDATE_METRIC_IDS:
                    if metric == "momentum" and terminal != 2023:
                        continue  # Six earlier years were not acquired or guessed.
                    source_years = (
                        citation_years
                        if metric == "research_impact"
                        else population.source_years
                    )
                    if not source_years:
                        continue
                    selected = tuple(
                        item
                        for item in source_years
                        if terminal - (5 if metric == "momentum" else 2)
                        <= item.calendar_year
                        <= terminal
                    )
                    window = certify_metric_window(
                        metric_id=metric,
                        entity_type=entity_type,
                        terminal_year=terminal,
                        source_years=selected,
                        threshold_version=METRIC_VALIDATION_THRESHOLDS_V1.version,
                        citation_cohorts=tuple(cohorts)
                        if metric == "research_impact"
                        else (),
                    )
                    if window.state != "certified":
                        diagnostic = {
                            "kind": "metric-window-withheld",
                            "entityType": entity_type,
                            "metric": metric,
                            "terminalYear": terminal,
                            "reasons": window.reasons,
                        }
                        diagnostics.append(diagnostic)
                        _progress("metric-window-withheld", **diagnostic)
                        continue
                    leaves: list[AtlasScaleObservation] = []
                    for field in (
                        ("nuclear",)
                        if metric == "research_diversity"
                        else ("nucl-th", "nucl-ex")
                    ):
                        _progress(
                            "calculating-cohort",
                            entityType=entity_type,
                            terminalYear=terminal,
                            metric=metric,
                            field=field,
                        )
                        try:
                            values = calculate_launch_metric_cohort(
                                window, field_id=field
                            )
                        except NoEligibleLaunchPeers as error:
                            diagnostic = {
                                "kind": "no-certified-peers",
                                "entityType": entity_type,
                                "metric": metric,
                                "terminalYear": terminal,
                                "field": field,
                                "excludedPeerCount": len(error.ineligible_peers),
                            }
                            diagnostics.append(diagnostic)
                            _progress("no-certified-peers", **diagnostic)
                            continue
                        observations.extend(values)
                        leaves.extend(values)
                        _progress(
                            "calculated-cohort",
                            entityType=entity_type,
                            terminalYear=terminal,
                            metric=metric,
                            field=field,
                            representedPeers=len(values),
                            numeric=sum(item.value is not None for item in values),
                            cache=asdict(cache.stats),
                        )
                    if metric != "research_diversity" and leaves:
                        by_entity: dict[str, list[AtlasScaleObservation]] = defaultdict(
                            list
                        )
                        for item in leaves:
                            by_entity[item.calculation.entity_id].append(item)
                        branch = PHYSICS_FIELD_ONTOLOGY_V1.get("nuclear")
                        field_populations = tuple(
                            certify_field_population(
                                derive_ontology_branch_population(branch, tuple(items))
                            )
                            for _, items in sorted(by_entity.items())
                        )
                        aggregated = apply_atlas_scale(
                            aggregate_ontology_branch(leaves, field_populations)
                        )
                        observations.extend(aggregated)
                        _progress(
                            "calculated-nuclear-branch",
                            entityType=entity_type,
                            metric=metric,
                            terminalYear=terminal,
                            numeric=sum(item.value is not None for item in aggregated),
                        )
        counts = Counter(
            item.calculation.metric_id
            for item in observations
            if item.value is not None
        )
        groups: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        for item in observations:
            if item.value is not None and item.calculation.field_id == "nuclear":
                result = item.calculation
                groups[(result.entity_type, result.entity_id, result.period)].add(
                    result.metric_id
                )
        summary = {
            "numericObservationCounts": dict(counts),
            "coLocatedFiveMetricGroups": sum(
                value == set(CANDIDATE_METRIC_IDS) for value in groups.values()
            ),
            "availablePeriods": sorted(
                {
                    item.calculation.period
                    for item in observations
                    if item.value is not None
                }
            ),
            "diagnostics": diagnostics,
        }
        size = _write_checkpoint(
            root,
            root / "calculated-launch.pickle.gz",
            CalculatedLaunch(
                prepared,
                sessions,
                tuple(all_cohorts),
                tuple(observations),
                tuple(diagnostics),
            ),
        )
        (root / "calculated-launch-summary.json").write_text(
            json.dumps(summary, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        _progress("metric-calculation-complete", **summary, checkpointBytes=size)


def export(root: Path, *, geographic_reference: Path) -> None:
    """Materialize final assets only after scientific and map-UX readiness.

    This still does not publish, change deployment configuration or activate the
    API. The operator validates these files before immutable remote publication.
    """
    from . import schemas
    from .launch_export import build_launch_export

    root = _private_root(root)
    names = (
        "manifest.json",
        "atlas-dataset.json",
        "scientific-evidence.json.gz",
        "launch-export-summary.json",
    )
    if any((root / name).exists() or (root / name).is_symlink() for name in names):
        raise ValueError("final launch assets already exist; never overwrite")
    calculated = _load(root, "calculated-launch.pickle.gz")
    if not isinstance(calculated, CalculatedLaunch):
        raise CertificationError("actual calculated launch is required")
    # Installed wheels have no relationship to a frontend checkout. The operator
    # supplies the exact display-only reference; never infer a repository path.
    policy = json.loads(geographic_reference.read_text(encoding="utf-8"))
    if policy.get("version") != "atlas-geographic-view-policy-v1":
        raise CertificationError("unsupported display-only geographic policy")
    provenance = schemas.Provenance(
        source=policy["source"],
        source_type="derived",
        version=policy["version"],
        status="verified",
    )
    views = tuple(
        schemas.GeographicViewOut.model_validate(
            {**view, "provenance": provenance.model_dump(by_alias=True)}
        )
        for view in policy["views"]
    )
    with bounded_build_verification_cache(
        maximum_entries=20_000, maximum_key_nodes=1_000_000, stream_large_keys=True
    ):
        result = build_launch_export(
            calculated, geographic_views=views, generated_at=datetime.now(UTC)
        )
    # An institution-only passing scientific slice cannot honestly satisfy this
    # task's global heatmap/composite requirement. This is a product check, not a
    # changed scientific threshold or reason to fabricate geographic estimates.
    if result.summary["coLocatedFiveMetricGroups"].get("country", 0) < 1:
        raise CertificationError(
            "scientific slice lacks a five-metric country heatmap/composite group"
        )
    if len(result.summary["countryHeatmapPeriods"]) < 2:
        raise CertificationError("country heatmap lacks supported historical periods")
    assets = tuple((path, content) for _, path, content in result.assets)
    if tuple(path for path, _ in assets) != names[:3]:
        raise CertificationError("unexpected final asset inventory")
    summary = json.dumps(result.summary, sort_keys=True, separators=(",", ":")).encode()
    assets += ((names[3], summary),)
    if _storage_bytes(root) + sum(len(data) for _, data in assets) > (
        MAX_EPHEMERAL_BYTES - 100_000_000
    ):
        raise RuntimeError("final assets exceed reserved temporary budget; not written")
    for path, content in assets:
        _publish_checkpoint(root, root / path, b"", content)
    _progress("final-assets-validated", **result.summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ephemeral-root", type=Path, required=True)
    parser.add_argument(
        "--geographic-reference",
        type=Path,
        help="Explicit versioned geographic-views.json; required for export only",
    )
    parser.add_argument(
        "stage", choices=("prepare", "citations", "calculate", "export")
    )
    arguments = parser.parse_args()
    stage = cast(str, arguments.stage)
    if stage == "export":
        if arguments.geographic_reference is None:
            parser.error("export requires --geographic-reference")
        export(
            arguments.ephemeral_root,
            geographic_reference=arguments.geographic_reference,
        )
        return
    if arguments.geographic_reference is not None:
        parser.error("--geographic-reference is only applicable to export")
    {
        "prepare": prepare,
        "citations": capture_citations,
        "calculate": calculate,
    }[stage](arguments.ephemeral_root)


if __name__ == "__main__":
    # Keep private checkpoint class names stable across the CLI stages and the
    # final exporter; never pickle these dataclasses under the name __main__.
    from .launch_pipeline import main as _stable_main

    _stable_main()
