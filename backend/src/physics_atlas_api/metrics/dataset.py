"""Opt-in immutable frontend export; no acquisition, database writes or activation.

The caller supplies provider-backed UI facts and retains the compact scientific
facts referenced by the manifest. A checksum is integrity, not source authority.
In particular past citation counts cannot be reconstructed from a mutable URL.
This module never serializes the expanded nested certification proof graph.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import Field

from .. import schemas
from ..certification import CertificationError, canonical_digest
from ..certification.years import CertifiedMetricWindow
from .activation import MetricSystemActivationEvidence, assess_joint_metric_activation
from .aggregation import CertifiedPhysicsAggregation
from .contracts import CANDIDATE_METRIC_IDS, METRIC_CONTRACTS
from .presentation import (
    ATLAS_SCALE_VERSION,
    AtlasScaleObservation,
    CertifiedMetricCalculation,
)
from .scoped_activation import CertifiedDatasetScope
from .thresholds import METRIC_VALIDATION_THRESHOLDS_V1

ATLAS_DATASET_RELEASE_VERSION = "certified-atlas-dataset-v1"
MAX_DATASET_BYTES = 64 * 1024 * 1024  # Operational export bound, not a scientific gate.
MAX_MANIFEST_BYTES = 8 * 1024 * 1024


class AtlasDatasetEntities(schemas.StrictApiModel):
    """Existing UI contracts only, with no provider payloads or replay traces."""

    science_domains: list[schemas.ScienceDomainOut]
    fields: list[schemas.ResearchFieldOut]
    countries: list[schemas.CountryOut]
    geographic_views: list[schemas.GeographicViewOut] = Field(default_factory=list)
    institutions: list[schemas.InstitutionOut] = Field(default_factory=list)
    researchers: list[schemas.ResearcherOut] = Field(default_factory=list)
    research_groups: list[schemas.ResearchGroupOut] = Field(default_factory=list)
    affiliations: list[schemas.AffiliationOut] = Field(default_factory=list)
    papers: list[schemas.PaperOut] = Field(default_factory=list)
    authorships: list[schemas.AuthorshipOut] = Field(default_factory=list)
    external_resources: list[schemas.ExternalResourceOut] = Field(default_factory=list)
    historical_events: list[schemas.HistoricalEventOut] = Field(default_factory=list)
    source_snapshots: list[schemas.SourceSnapshotOut] = Field(default_factory=list)


@dataclass(frozen=True)
class RetainedScientificEvidence:
    """Published compact facts, including irrecoverable measured citation history.

    Publication must verify this artifact is present and checksum-exact. This is
    a reference, not permission to throw away the facts or an authenticity claim.
    """

    storage_reference: str
    sha256: str
    byte_length: int
    schema_version: str

    def __post_init__(self) -> None:
        parts = urlsplit(self.storage_reference)
        if (
            parts.scheme
            or parts.netloc
            or parts.query
            or parts.fragment
            or self.storage_reference.startswith("/")
            or any(part in ("", ".", "..") for part in parts.path.split("/"))
            or "\\" in self.storage_reference
            or "%" in self.storage_reference
        ):
            raise CertificationError(
                "scientific evidence reference must be release-relative"
            )
        if (
            len(self.sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.sha256)
            or self.byte_length <= 0
            or not self.schema_version.strip()
        ):
            raise CertificationError("retained scientific evidence metadata is invalid")


@dataclass(frozen=True)
class AtlasDatasetExport:
    dataset_bytes: bytes
    manifest_bytes: bytes


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _entity_payload(entities: AtlasDatasetEntities) -> dict[str, Any]:
    payload = entities.model_dump(mode="json", by_alias=True, exclude_none=True)
    for records in payload.values():
        ids = [record["id"] for record in records]
        if len(ids) != len(set(ids)):
            raise CertificationError("dataset entity identifiers must be unique")
        for record in records:
            provenance = record["provenance"]
            if (
                provenance["status"] == "synthetic"
                or provenance["sourceType"] == "synthetic-demo"
            ):
                raise CertificationError(
                    "synthetic facts cannot enter a certified dataset"
                )
    if (
        not payload["scienceDomains"]
        or not payload["fields"]
        or not payload["countries"]
    ):
        raise CertificationError(
            "dataset requires domain, field and geographic metadata"
        )
    return payload


def _observation_payload(
    observation: AtlasScaleObservation, generated_at: datetime
) -> dict[str, Any]:
    result = observation.calculation
    # Preserve actual intervals, cutoffs, cohort parameters and compact proof
    # references; never substitute completion time for an observed citation time.
    parameters: dict[str, Any] = {
        **result.normalization_parameters,
        **result.components,
        "atlasScaleVersion": observation.scale_version,
        "comparisonCohort": observation.comparison_cohort,
        "coverage": observation.coverage,
        "inputManifestDigest": result.input_manifest_digest,
        "certificationManifestDigest": result.certification_manifest_digest,
        "evaluationHorizon": result.evidence_cutoff,
        "citationCutoff": observation.cutoff,
        "thresholdVersion": result.threshold_version,
        "attributionPolicyVersion": result.attribution_policy_version,
        "ontologyVersion": result.ontology_version,
        "mappingPolicyVersion": result.mapping_policy_version,
        "citationPolicyVersion": result.citation_policy_version,
    }
    key = (
        result.entity_type,
        result.entity_id,
        result.field_id,
        result.period,
        result.metric_id,
    )
    payload: dict[str, Any] = {
        "id": f"atlas-{canonical_digest(key)}",
        "entityType": result.entity_type,
        "entityId": result.entity_id,
        "scienceDomainId": "physics",
        "metricId": result.metric_id,
        "period": result.period,
        "value": observation.value,
        "source": "certified-atlas-dataset",
        "metricDefinitionVersion": result.metric_definition_version,
        "algorithmVersion": result.algorithm_version,
        "calculationVersion": ATLAS_DATASET_RELEASE_VERSION,
        "dataSourceVersion": result.dataset_version,
        "acquisitionScope": result.acquisition_scope,
        "rawValue": result.raw_value,
        "rawUnit": result.raw_unit,
        "normalizationMethod": result.normalization_version,
        "normalizationParameters": parameters,
        "inputCount": result.input_count,
        "qualityFlags": list(observation.uncertainty_reasons),
        "calculatedAt": generated_at.isoformat(),
        "provenance": {
            "source": "Certified Metric System v1",
            "sourceType": "derived",
            "version": result.dataset_version,
            "status": "verified",
            "acquisitionScope": result.acquisition_scope,
        },
    }
    if result.field_id != "physics":
        payload["fieldId"] = result.field_id
    return payload


def _verify_observation(
    observation: AtlasScaleObservation,
    verified: set[int],
    dataset_scope: CertifiedDatasetScope | None = None,
) -> None:
    if id(observation) in verified:
        return
    proof = observation.certification_proof
    if isinstance(proof, CertifiedMetricCalculation):
        for calculation in (proof, *observation.normalization_proofs):
            if id(calculation) not in verified:
                calculation.__post_init__()
                window = calculation.partition.window_proof
                if not isinstance(window, CertifiedMetricWindow) or any(
                    partition.provider not in {"inspire", "arxiv"}
                    for year in window.source_years
                    for partition in year.evidence.partitions
                ):
                    raise CertificationError(
                        "fixture or unsupported source years cannot be published"
                    )
                if dataset_scope is not None and id(window) not in verified:
                    dataset_scope.require_metric_window(window)
                    verified.add(id(window))
                verified.add(id(calculation))
        if observation.normalization_population_proof is not None:
            observation.normalization_population_proof.__post_init__()
    elif isinstance(proof, CertifiedPhysicsAggregation):
        for field_observation in proof.field_observations:
            _verify_observation(field_observation, verified, dataset_scope)
        proof.field_population_proof.__post_init__()
        proof.__post_init__()
    observation.__post_init__()
    verified.add(id(observation))


def build_atlas_dataset(
    entities: AtlasDatasetEntities,
    observations: tuple[AtlasScaleObservation, ...],
    activation_evidence: MetricSystemActivationEvidence,
    scientific_evidence: RetainedScientificEvidence,
    *,
    generated_at: datetime,
    dataset_scope: CertifiedDatasetScope | None = None,
) -> AtlasDatasetExport:
    """Export only after the unchanged exact-five gate and typed proof checks.

    This produces bytes for the caller's single ephemeral build directory or
    direct publisher. It performs no writes, persistence or public activation.
    """
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise CertificationError("dataset generation time must be timezone-aware")
    decision = assess_joint_metric_activation(
        activation_evidence, dataset_scope=dataset_scope
    )
    if not decision.may_activate:
        raise CertificationError(
            "Joint Activation Gate withheld: " + "; ".join(decision.reasons)
        )
    scientific_evidence.__post_init__()
    payload = _entity_payload(entities)
    entity_ids = {
        "country": {item["id"] for item in payload["countries"]},
        "institution": {item["id"] for item in payload["institutions"]},
        "researcher": {item["id"] for item in payload["researchers"]},
    }
    field_ids = {item["id"] for item in payload["fields"]}
    if "physics" not in {item["id"] for item in payload["scienceDomains"]}:
        raise CertificationError("the launch dataset requires the Physics domain")
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    keys: set[tuple[str, ...]] = set()
    verified: set[int] = set()
    for observation in observations:
        if not isinstance(observation, AtlasScaleObservation):
            raise CertificationError(
                "export requires certified Atlas Scale observations"
            )
        if dataset_scope is not None:
            result = observation.calculation
            if result.field_id not in {
                dataset_scope.root_field_id,
                *dataset_scope.leaf_field_ids,
            } or result.entity_type not in {
                year.evidence.entity_type for year in dataset_scope.source_years
            }:
                raise CertificationError(
                    "scoped release cannot relabel branch evidence as broad Physics"
                )
        _verify_observation(observation, verified, dataset_scope)
        result = observation.calculation
        contract = METRIC_CONTRACTS.get(result.metric_id)
        if (
            contract is None
            or observation.thresholds != METRIC_VALIDATION_THRESHOLDS_V1
            or result.dataset_version != activation_evidence.data_source_version
            or result.acquisition_scope != activation_evidence.acquisition_scope
            or result.metric_definition_version != contract.version
            or result.algorithm_version != contract.algorithm_version
            or result.normalization_version != contract.normalization_version
            or len(result.period) != 4
            or not result.period.isdecimal()
            or result.entity_id not in entity_ids.get(result.entity_type, set())
            or (result.field_id != "physics" and result.field_id not in field_ids)
        ):
            raise CertificationError(
                "observation lineage, entity or current metric contract differs"
            )
        key = (
            result.entity_type,
            result.entity_id,
            result.field_id,
            result.period,
            result.metric_id,
        )
        if key in keys:
            raise CertificationError("duplicate dataset observation scope")
        keys.add(key)
        row = _observation_payload(observation, generated_at)
        if observation.value is None:
            # Existing UI observation values are numbers. Withheld facts live in
            # the public release manifest, never as invented zero-valued rows.
            missing.append(row)
        else:
            rows.append(row)
    if {row["metricId"] for row in rows} != set(CANDIDATE_METRIC_IDS):
        raise CertificationError(
            "all five metrics require a real certified numeric observation"
        )
    provenance = {
        "source": "Certified Atlas Dataset",
        "sourceType": "derived",
        "status": "verified",
        "version": activation_evidence.data_source_version,
        "acquisitionScope": activation_evidence.acquisition_scope,
    }
    payload["metricDefinitions"] = [
        {
            "id": metric_id,
            "name": contract.name,
            "category": contract.name,
            "description": contract.formula,
            "interpretation": contract.interpretation,
            "unit": "normalized Atlas value (0–100)",
            "version": contract.version,
            "requiredData": [
                item
                for item in contract.required_data_metadata()
                if not item.startswith("source-scope:")
            ]
            + [f"source-scope:{activation_evidence.acquisition_scope}"],
            "implementationStatus": "live-calculated",
            "provenance": provenance,
        }
        for metric_id in CANDIDATE_METRIC_IDS
        for contract in (METRIC_CONTRACTS[metric_id],)
    ]
    payload["metricObservations"] = sorted(rows, key=lambda row: row["id"])
    payload["metadata"] = {
        "schemaVersion": ATLAS_DATASET_RELEASE_VERSION,
        "datasetKind": "live-api",
        "deliveryMode": "versioned-dataset",
        "period": max(row["period"] for row in rows),
        "generatedAt": generated_at.isoformat(),
        "sourceSnapshotIds": [row["id"] for row in payload["sourceSnapshots"]],
        "updateSequence": 0,
        "disclaimer": (
            "Certified source-backed Atlas dataset with explicitly limited coverage. "
            "Historical citation Impact is retrospective. Missing is not zero. "
            "Not a scientific ranking."
        ),
        "provenance": provenance,
    }
    dataset_bytes = _json_bytes(payload)
    if len(dataset_bytes) > MAX_DATASET_BYTES:
        raise CertificationError("dataset exceeds the bounded 64 MiB export size")
    manifest = {
        "schemaVersion": ATLAS_DATASET_RELEASE_VERSION,
        "datasetPath": "atlas-dataset.json",
        "datasetSha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "datasetBytes": len(dataset_bytes),
        "dataSourceVersion": activation_evidence.data_source_version,
        "acquisitionScope": activation_evidence.acquisition_scope,
        "atlasScaleVersion": ATLAS_SCALE_VERSION,
        "metricIds": list(CANDIDATE_METRIC_IDS),
        "observationCounts": {
            metric_id: sum(row["metricId"] == metric_id for row in rows)
            for metric_id in CANDIDATE_METRIC_IDS
        },
        "periods": sorted({row["period"] for row in rows}),
        "jointGateEvidence": asdict(activation_evidence),
        "jointGateDecision": asdict(decision),
        "scientificEvidence": asdict(scientific_evidence),
        "missingObservations": sorted(missing, key=lambda row: row["id"]),
    }
    if dataset_scope is not None:
        # The first release must support a genuine five-way user composite,
        # not five disjoint results that happen to exist somewhere in the file.
        groups: dict[tuple[str, str, str], set[str]] = {}
        for row in rows:
            if row.get("fieldId") == dataset_scope.root_field_id:
                composite_key = (row["entityType"], row["entityId"], row["period"])
                groups.setdefault(composite_key, set()).add(row["metricId"])
        if not any(set(CANDIDATE_METRIC_IDS) == ids for ids in groups.values()):
            raise CertificationError(
                "scoped release requires co-located real observations "
                "for all five metrics"
            )
        manifest["datasetScope"] = dataset_scope.release_metadata()
    manifest_bytes = _json_bytes(manifest)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise CertificationError("dataset manifest exceeds the bounded 8 MiB size")
    return AtlasDatasetExport(dataset_bytes, manifest_bytes)
