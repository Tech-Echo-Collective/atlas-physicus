"""Pure, proof-derived release adapter for the bounded launch.

No files, provider reads, database writes, or public activation occur here. The
returned three immutable assets are suitable for the existing Pages publisher.
An eligible flag is derived from reconstruction of these actual observations,
never from passing synthetic tests or a caller-supplied approval boolean.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from . import schemas
from .attribution import FRACTIONAL_ATTRIBUTION_V1
from .certification.contracts import CertificationError
from .certification.launch_entities import build_launch_entities
from .certification.launch_retained import build_launch_retained
from .certification.launch_years import LaunchStructuralDecision
from .certification.measurement_windows import CertifiedSessionCitationCohort
from .certification.years import CertifiedMetricWindow
from .fields import (
    CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION,
    FIELD_WEIGHTING_POLICY_VERSION,
    PHYSICS_FIELD_ONTOLOGY_VERSION,
    PROVIDER_FIELD_MAPPING_VERSION,
)
from .launch_pipeline import CalculatedLaunch
from .metrics.activation import (
    METRIC_SYSTEM_V1_VERSION,
    MetricAlgorithmActivationEvidence,
    MetricSystemActivationEvidence,
    MetricSystemCoverageEvidence,
    assess_joint_metric_activation,
)
from .metrics.contracts import CANDIDATE_METRIC_IDS, METRIC_CONTRACTS
from .metrics.dataset import (
    MAX_MANIFEST_BYTES,
    RetainedScientificEvidence,
    build_atlas_dataset,
)
from .metrics.presentation import AtlasScaleObservation, CertifiedMetricCalculation
from .metrics.scoped_activation import (
    ConditionalObservedDatasetScope,
    certify_conditional_observed_dataset_scope,
)
from .metrics.thresholds import METRIC_VALIDATION_THRESHOLDS_V1

LAUNCH_EXPORT_VERSION = "proof-derived-conditional-launch-export-v1"
EVIDENCE_PATH = "scientific-evidence.json.gz"
MAX_EVIDENCE_BYTES = 128 * 1024 * 1024


def _encode(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


@dataclass(frozen=True)
class LaunchExport:
    """Only final production assets and small measured diagnostics."""

    manifest_bytes: bytes
    dataset_bytes: bytes
    scientific_evidence_bytes: bytes
    summary: dict[str, Any]
    version: str = LAUNCH_EXPORT_VERSION

    @property
    def assets(self) -> tuple[tuple[str, str, bytes], ...]:
        return (
            ("manifest", "manifest.json", self.manifest_bytes),
            ("dataset", "atlas-dataset.json", self.dataset_bytes),
            ("evidence", EVIDENCE_PATH, self.scientific_evidence_bytes),
        )


def _verify_prepared_lineage(calculated: CalculatedLaunch) -> None:
    """UI facts, source authority and citation history must be the same run."""
    if not isinstance(calculated, CalculatedLaunch):
        raise CertificationError("launch export requires an exact calculated launch")
    prepared = calculated.prepared
    expected = {paper.paper_id: paper for paper in prepared.canonical.papers}
    if not expected or len(expected) != len(prepared.canonical.papers):
        raise CertificationError("launch canonical inventory is empty or duplicated")
    actual = {}
    for year in prepared.source_years:
        for decision in year.evidence.structural_decisions:
            if not isinstance(decision, LaunchStructuralDecision):
                # Dated publication proofs have their own typed producer; the
                # scope reconstructs those separately from canonical identity.
                continue
            paper = decision.source_paper
            if expected.get(paper.paper_id) != paper:
                raise CertificationError(
                    "launch UI/scientific paper inventories differ"
                )
            actual[paper.paper_id] = paper
    if actual != expected:
        raise CertificationError("launch source authority omits canonical input papers")
    populations = prepared.frozen_populations
    if not populations or len(calculated.sessions) != len(populations):
        raise CertificationError(
            "launch citation sessions differ from frozen inventory"
        )
    for population, session in zip(populations, calculated.sessions, strict=True):
        population.__post_init__()
        session.__post_init__()
        if session.frozen_population != population.measurement_population or any(
            year not in prepared.source_years for year in population.source_years
        ):
            raise CertificationError("launch citation freeze/source lineage differs")
    sessions = {session.session_id: session for session in calculated.sessions}
    for cohort in calculated.citation_cohorts:
        if not isinstance(cohort, CertifiedSessionCitationCohort):
            raise CertificationError("launch citation cohort is not source-certified")
        cohort.__post_init__()
        if sessions.get(cohort.session_id) != cohort.session:
            raise CertificationError("launch cohort refers to another measurement")


def _reconstruct_calculations(
    scope: ConditionalObservedDatasetScope, calculated: CalculatedLaunch
) -> dict[str, Any]:
    """Current calculators/normalization re-evaluate their exact typed inputs.

    This is reproducibility of this dataset, not a claim of an external empirical
    benchmark. Existing source/window rules enforce historical closure, citation
    maturity, conservation, observed coverage, and preserved unresolved evidence.
    """
    sessions = {session.session_id: session for session in calculated.sessions}
    counts: Counter[str] = Counter()
    windows: set[str] = set()
    checked_windows: set[int] = set()
    seen: set[int] = set()
    for observation in calculated.observations:
        if not isinstance(observation, AtlasScaleObservation):
            raise CertificationError("launch requires exact Atlas observations")
        for direct in scope._direct_observations(observation):
            proof = direct.certification_proof
            if not isinstance(proof, CertifiedMetricCalculation):
                raise CertificationError("launch leaf has no raw calculation proof")
            for calculation in (proof, *direct.normalization_proofs):
                if id(calculation) in seen:
                    continue
                calculation.__post_init__()  # Exact existing raw calculator equality.
                window = calculation.partition.window_proof
                if not isinstance(window, CertifiedMetricWindow):
                    raise CertificationError("launch calculation lacks a source window")
                if id(window) not in checked_windows:
                    scope.require_metric_window(window)
                    windows.add(window.certification.certification_id)
                    checked_windows.add(id(window))
                for cohort in calculation.citation_cohorts:
                    if (
                        not isinstance(cohort, CertifiedSessionCitationCohort)
                        or sessions.get(cohort.session_id) != cohort.session
                    ):
                        raise CertificationError(
                            "metric citation history is substituted"
                        )
                counts[calculation.calculation.metric_id] += 1
                seen.add(id(calculation))
            direct.__post_init__()  # Exact existing cohort normalization equality.
            if direct.normalization_population_proof is not None:
                direct.normalization_population_proof.__post_init__()
        observation.__post_init__()
    if set(counts) != set(CANDIDATE_METRIC_IDS):
        raise CertificationError("all five implemented calculations must reconstruct")
    return {
        "version": LAUNCH_EXPORT_VERSION,
        "basis": "exact source/window/raw-calculator/normalization reconstruction",
        "externalBenchmarkClaim": False,
        "reconstructedCalculations": dict(sorted(counts.items())),
        "reconstructedWindowCount": len(windows),
        "sourceYearCount": len(scope.source_years),
        "thresholdVersion": METRIC_VALIDATION_THRESHOLDS_V1.version,
    }


def _activation(
    scope: ConditionalObservedDatasetScope, reconstruction: dict[str, Any]
) -> MetricSystemActivationEvidence:
    counts = reconstruction["reconstructedCalculations"]
    passed = all(counts.get(metric, 0) > 0 for metric in CANDIDATE_METRIC_IDS)
    return MetricSystemActivationEvidence(
        metric_system_version=METRIC_SYSTEM_V1_VERSION,
        algorithms=tuple(
            MetricAlgorithmActivationEvidence(
                metric,
                METRIC_CONTRACTS[metric].version,
                METRIC_CONTRACTS[metric].algorithm_version,
                METRIC_CONTRACTS[metric].normalization_version,
                counts.get(metric, 0) > 0,
                counts.get(metric, 0) > 0,
            )
            for metric in CANDIDATE_METRIC_IDS
        ),
        attribution_policy_version=FRACTIONAL_ATTRIBUTION_V1.version,
        attribution_validation_passed=passed,
        ontology_version=PHYSICS_FIELD_ONTOLOGY_VERSION,
        provider_mapping_versions=tuple(
            (provider, PROVIDER_FIELD_MAPPING_VERSION)
            for provider in ("inspire", "arxiv")
        ),
        threshold_version=METRIC_VALIDATION_THRESHOLDS_V1.version,
        coverage=MetricSystemCoverageEvidence(**scope.observed_coverage()),
        historical_coverage_validated=passed,
        citation_maturity_validated=passed,
        normalization_validated=passed,
        provenance_complete=passed,
        deterministic_reproduction_passed=passed,
        field_weighting_policy_version=FIELD_WEIGHTING_POLICY_VERSION,
        field_reconciliation_version=CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION,
        field_weight_conservation_passed=passed,
        acquisition_scope=scope.acquisition_scope,
        acquisition_boundary_kind="ontology-branch",
        data_source_version=scope.dataset_version,
        diversity_breadth_review_version=scope.version,
        diversity_breadth_review_passed=passed,
    )


def build_launch_export(
    calculated: CalculatedLaunch,
    *,
    geographic_views: tuple[schemas.GeographicViewOut, ...],
    generated_at: datetime,
) -> LaunchExport:
    """Return all three final assets, or fail without writing anything.

    The caller should use the existing bounded verification-cache context for
    repeated immutable proof checks. Missing observations and diagnosed source
    failures remain explicit; no entity is dropped to fit a transport size cap.
    """
    _verify_prepared_lineage(calculated)
    if (
        generated_at.tzinfo is None
        or generated_at.utcoffset() is None
        or generated_at < max(year.cutoff for year in calculated.prepared.source_years)
        or generated_at
        < max(session.measurement_finished_at for session in calculated.sessions)
    ):
        raise CertificationError("launch generation timestamp precedes its evidence")
    scope = certify_conditional_observed_dataset_scope(
        calculated.prepared.source_years, calculated.observations
    )
    reconstruction = _reconstruct_calculations(scope, calculated)
    entities = build_launch_entities(
        calculated.prepared.canonical.papers,
        calculated.prepared.attributions,
        geographic_views=geographic_views,
    )
    retained = build_launch_retained(
        scope.source_years,
        calculated.observations,
        source_references=entities.source_references,
    )
    # The retained exporter checks every decoded MetricPartitionInput for exact
    # equality with the certified original before returning these bytes.
    reconstruction["retainedFactCounts"] = dict(retained.counts)
    evidence_bytes = gzip.compress(retained.content, compresslevel=9, mtime=0)
    if len(evidence_bytes) > MAX_EVIDENCE_BYTES:
        raise CertificationError(
            f"compact evidence is {len(evidence_bytes)} bytes, above the "
            f"{MAX_EVIDENCE_BYTES}-byte publisher limit; no evidence was truncated"
        )
    activation = _activation(scope, reconstruction)
    reference = RetainedScientificEvidence(
        EVIDENCE_PATH,
        hashlib.sha256(evidence_bytes).hexdigest(),
        len(evidence_bytes),
        retained.version,
    )
    exported = build_atlas_dataset(
        entities.entities,
        calculated.observations,
        activation,
        reference,
        generated_at=generated_at,
        dataset_scope=scope,
    )
    manifest = json.loads(exported.manifest_bytes)
    manifest["scientificEvidenceFormat"] = {
        "compression": "gzip",
        "decodedSha256": retained.sha256,
        "decodedBytes": retained.byte_length,
    }
    manifest["launchValidation"] = reconstruction
    manifest["launchDiagnostics"] = list(calculated.diagnostics)
    manifest["unavailableEntityFacts"] = dict(entities.omitted_counts)
    manifest_bytes = _encode(manifest)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise CertificationError(
            f"launch manifest is {len(manifest_bytes)} bytes; no diagnostics truncated"
        )
    groups: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    country_periods: set[str] = set()
    for observation in scope.released_observations:
        result = observation.calculation
        if result.entity_type == "country":
            country_periods.add(result.period)
        if result.field_id == scope.root_field_id:
            groups[(result.entity_type, result.entity_id, result.period)].add(
                result.metric_id
            )
    group_counts = Counter(
        key[0]
        for key, metrics in groups.items()
        if metrics == set(CANDIDATE_METRIC_IDS)
    )
    return LaunchExport(
        manifest_bytes,
        exported.dataset_bytes,
        evidence_bytes,
        {
            "datasetVersion": scope.dataset_version,
            "scopeVersion": scope.version,
            "observationCounts": manifest["observationCounts"],
            "periods": manifest["periods"],
            "countryHeatmapPeriods": sorted(country_periods),
            "coLocatedFiveMetricGroups": dict(sorted(group_counts.items())),
            "entityCounts": dict(entities.entity_counts),
            "unavailableEntityFacts": dict(entities.omitted_counts),
            "observedCoverage": scope.observed_coverage(),
            "jointGate": assess_joint_metric_activation(
                activation, dataset_scope=scope
            ).status,
            "manifestBytes": len(manifest_bytes),
            "datasetBytes": len(exported.dataset_bytes),
            "scientificEvidenceBytes": len(evidence_bytes),
            "scientificEvidenceDecodedBytes": retained.byte_length,
            "totalProductionBytes": len(manifest_bytes)
            + len(exported.dataset_bytes)
            + len(evidence_bytes),
        },
    )
