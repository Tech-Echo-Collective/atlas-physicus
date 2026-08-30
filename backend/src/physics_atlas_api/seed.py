import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pycountry
from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute, Session

from . import models
from .attribution import FRACTIONAL_ATTRIBUTION_V1
from .config import get_settings
from .database import SessionLocal
from .fields import (
    CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION,
    FIELD_WEIGHTING_POLICY_VERSION,
    PHYSICS_FIELD_ONTOLOGY_V1,
    PHYSICS_FIELD_ONTOLOGY_VERSION,
)
from .fields.mapping import PROVIDER_FIELD_MAPPING_VERSION
from .metrics.activation import field_validation_manifest_is_current
from .metrics.contracts import METRIC_CONTRACTS, get_metric_contract
from .metrics.thresholds import METRIC_VALIDATION_THRESHOLDS_V1
from .search_index import refresh_search_terms

ISO_ALPHA3_TO_ALPHA2 = {
    "USA": "US",
    "GBR": "GB",
    "CHE": "CH",
    "DEU": "DE",
    "JPN": "JP",
    "CHN": "CN",
    "TWN": "TW",
    "CAN": "CA",
    "AUS": "AU",
}

REFERENCE_PROVENANCE = {
    "source": "Physics Atlas reference taxonomy and ISO 3166",
    "sourceType": "derived",
    "version": "v3.0.5-alpha",
    "status": "unverified",
}

BROAD_PHYSICS_FIELDS = {
    item.id: (item.label, item.description) for item in PHYSICS_FIELD_ONTOLOGY_V1.fields
}

REFERENCE_METRIC_TEXT = {
    "research_activity_score": (
        "Research Activity",
        "Vocabulary for research-output volume and continuity within a scope.",
        "No live value is calculated until a reviewed method is registered.",
    ),
    "research_impact": (
        "Research Impact",
        "Vocabulary for how research is received or used in a defined context.",
        "It is not an institutional-quality ranking; no live formula is implemented.",
    ),
    "collaboration": (
        "Collaboration / Connectivity",
        "Vocabulary for supported scientific relationships across entities.",
        "It does not allocate contribution or value individual participants.",
    ),
    "research_diversity": (
        "Research Diversity",
        "Vocabulary for subfield, topic, and research breadth.",
        "No validated diversity value is calculated in this release.",
    ),
    "momentum": (
        "Research Momentum / Sustainability",
        "Vocabulary for observed change and continuity over time.",
        "It is not a prediction and no live formula is implemented.",
    ),
    "talent_ecosystem": (
        "Talent Ecosystem",
        "Vocabulary for developing and sustaining researchers.",
        "Researcher growth and mobility methods remain future work.",
    ),
    "concentration_vulnerability": (
        "Concentration / Vulnerability",
        "Vocabulary for structural concentration and ecosystem dependency.",
        "No resilience or vulnerability claim is calculated in this release.",
    ),
}


def _metric_system_versions_are_current(
    release: models.MetricSystemRelease | None,
) -> bool:
    """Compare a persisted manifest with the implemented system tuple."""
    if release is None:
        return False
    return (
        set(release.metric_ids) == set(METRIC_CONTRACTS)
        and release.algorithm_versions
        == {
            metric_id: contract.algorithm_version
            for metric_id, contract in METRIC_CONTRACTS.items()
        }
        and release.attribution_policy_version == FRACTIONAL_ATTRIBUTION_V1.version
        and release.ontology_version == PHYSICS_FIELD_ONTOLOGY_VERSION
        and release.mapping_policy_version == PROVIDER_FIELD_MAPPING_VERSION
        and release.threshold_version == METRIC_VALIDATION_THRESHOLDS_V1.version
        and field_validation_manifest_is_current(release.validation_evidence)
    )


def _reviewed_metric_system_is_current(
    release: models.MetricSystemRelease | None,
) -> bool:
    """Recognize reviewed state without creating or promoting it."""
    if release is None or release.status not in {"eligible", "active"}:
        return False
    if release.status == "active" and release.activated_at is None:
        return False
    return (
        _metric_system_versions_are_current(release)
        and release.validation_evidence.get("jointGatePassed") is True
    )


def _reference_metric_values(item: dict[str, Any]) -> dict[str, Any]:
    contract = get_metric_contract(item["id"])
    if contract is not None:
        return {
            "name": contract.name,
            "description": (
                f"Experimental candidate {contract.version}. {contract.formula}"
            ),
            "interpretation": contract.interpretation,
            "unit": "candidate normalized visualization index (0-100), withheld",
            "version": contract.version,
            "required_data": contract.required_data_metadata(),
            "implementation_status": contract.implementation_status,
            "provenance_json": {
                "source": contract.provenance.source,
                "sourceType": "derived",
                "version": contract.version,
                "status": "unverified",
                "acquisitionScope": contract.provenance.source_scope,
                "algorithmVersion": contract.algorithm_version,
                "normalizationVersion": contract.normalization_version,
                "scientificStatus": contract.implementation_status,
            },
        }

    name, description, interpretation = REFERENCE_METRIC_TEXT.get(
        item["id"],
        (item["name"], item["description"], item["interpretation"]),
    )
    return {
        "name": name,
        "description": description,
        "interpretation": interpretation,
        "unit": "taxonomy definition only",
        "version": item["version"],
        "required_data": ["future validated source data and reviewed methodology"],
        "implementation_status": "taxonomy-only",
        "provenance_json": REFERENCE_PROVENANCE,
    }


def seed_reference_data(session: Session, payload: dict[str, Any]) -> None:
    """Seed non-observational reference data without copying demo entities."""
    metric_system_release = session.get(models.MetricSystemRelease, "metric-system-v1")
    preserve_reviewed_metrics = _reviewed_metric_system_is_current(
        metric_system_release
    )
    session.merge(
        models.ScienceDomain(
            id="physics",
            label="Physics",
            description="The Physics science domain.",
            provenance_json=REFERENCE_PROVENANCE,
        )
    )
    demo_fields = {item["id"]: item for item in payload.get("fields", [])}
    for definition in PHYSICS_FIELD_ONTOLOGY_V1.fields:
        field_id = definition.id
        label, description = BROAD_PHYSICS_FIELDS[field_id]
        item = demo_fields.get(field_id, {})
        session.merge(
            models.ResearchField(
                id=field_id,
                domain_id="physics",
                label=item.get("label", label),
                description=item.get("description", description),
                parent_field_id=definition.parent_id,
                aliases=list(definition.aliases),
                ontology_version=definition.ontology_version,
                node_kind=definition.node_kind,
                is_explorable=definition.node_kind == "field",
                display_order=definition.display_order,
                provider_mappings={},
                provenance_json={
                    **REFERENCE_PROVENANCE,
                    "source": definition.provenance.source,
                    "version": definition.ontology_version,
                    "ontologyStatus": definition.provenance.status,
                    "note": definition.provenance.note,
                },
            )
        )
    for country in pycountry.countries:
        numeric = getattr(country, "numeric", None)
        if numeric is None:
            continue
        country_id = f"country-{country.alpha_2.casefold()}"
        session.merge(
            models.Country(
                id=country_id,
                iso_alpha3=country.alpha_3,
                iso_alpha2=country.alpha_2,
                iso_numeric=numeric,
                name=country.name,
                region="Global",
                provenance_json=REFERENCE_PROVENANCE,
            )
        )
        session.merge(
            models.GeographicView(
                id=f"geographic-view-{country.alpha_2.casefold()}",
                country_id=country_id,
                geometry_iso_numerics=[numeric],
                location_country_ids=[country_id],
                provenance_json=REFERENCE_PROVENANCE,
            )
        )
    # Explicit geographic groupings remain display configuration, never
    # scientific attribution. They override the generic per-location view.
    for item in payload.get("geographicViews", []):
        session.merge(
            models.GeographicView(
                id=item["id"],
                country_id=item["countryId"],
                geometry_iso_numerics=item["geometryIsoNumerics"],
                location_country_ids=item["locationCountryIds"],
                provenance_json=REFERENCE_PROVENANCE,
            )
        )
    for item in payload.get("metricDefinitions", []):
        values = _reference_metric_values(item)
        existing_definition = session.get(models.MetricDefinition, item["id"])
        if (
            preserve_reviewed_metrics
            and get_metric_contract(item["id"]) is not None
            and existing_definition is not None
            and existing_definition.version == values["version"]
            and existing_definition.implementation_status == "live-calculated"
        ):
            continue
        session.merge(
            models.MetricDefinition(
                id=item["id"],
                name=values["name"],
                category=item["category"],
                description=values["description"],
                interpretation=values["interpretation"],
                unit=values["unit"],
                version=values["version"],
                required_data=values["required_data"],
                implementation_status=values["implementation_status"],
                provenance_json=values["provenance_json"],
            )
        )
    if metric_system_release is None:
        session.add(
            models.MetricSystemRelease(
                id="metric-system-v1",
                status="experimental-withheld",
                metric_ids=list(METRIC_CONTRACTS),
                algorithm_versions={
                    metric_id: contract.algorithm_version
                    for metric_id, contract in METRIC_CONTRACTS.items()
                },
                attribution_policy_version=FRACTIONAL_ATTRIBUTION_V1.version,
                ontology_version=PHYSICS_FIELD_ONTOLOGY_VERSION,
                mapping_policy_version=PROVIDER_FIELD_MAPPING_VERSION,
                threshold_version=METRIC_VALIDATION_THRESHOLDS_V1.version,
                validation_evidence={
                    "jointGatePassed": False,
                    "fieldWeightingPolicyVersion": FIELD_WEIGHTING_POLICY_VERSION,
                    "fieldReconciliationVersion": (
                        CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION
                    ),
                    "fieldWeightConservationPassed": False,
                    "reason": (
                        "Algorithms are implemented as an experimental framework; "
                        "live coverage and scientific validation gates have not passed."
                    ),
                },
                activated_at=None,
                provenance_json={
                    "source": "Physics Atlas Metric System v1 activation gate",
                    "sourceType": "derived",
                    "version": "metric-system-v1",
                    "status": "unverified",
                },
            )
        )
    elif metric_system_release.status == "experimental-withheld":
        metric_system_release.metric_ids = list(METRIC_CONTRACTS)
        metric_system_release.algorithm_versions = {
            metric_id: contract.algorithm_version
            for metric_id, contract in METRIC_CONTRACTS.items()
        }
        metric_system_release.attribution_policy_version = (
            FRACTIONAL_ATTRIBUTION_V1.version
        )
        metric_system_release.ontology_version = PHYSICS_FIELD_ONTOLOGY_VERSION
        metric_system_release.mapping_policy_version = PROVIDER_FIELD_MAPPING_VERSION
        metric_system_release.threshold_version = (
            METRIC_VALIDATION_THRESHOLDS_V1.version
        )
        metric_system_release.validation_evidence = {
            "jointGatePassed": False,
            "fieldWeightingPolicyVersion": FIELD_WEIGHTING_POLICY_VERSION,
            "fieldReconciliationVersion": (CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION),
            "fieldWeightConservationPassed": False,
            "reason": (
                "Algorithms are implemented as an experimental framework; "
                "live coverage and scientific validation gates have not passed."
            ),
        }
        metric_system_release.activated_at = None
    session.commit()


def _reference_data_is_complete(session: Session, payload: dict[str, Any]) -> bool:
    """Return whether every required non-observational reference row exists."""
    country_ids = {
        f"country-{country.alpha_2.casefold()}"
        for country in pycountry.countries
        if getattr(country, "numeric", None) is not None
    }
    geographic_view_ids = {
        f"geographic-view-{country_id.removeprefix('country-')}"
        for country_id in country_ids
    } | {item["id"] for item in payload.get("geographicViews", [])}
    metric_items = {
        item["id"]: _reference_metric_values(item)
        for item in payload.get("metricDefinitions", [])
    }
    metric_ids = set(metric_items)
    metric_system_release = session.get(models.MetricSystemRelease, "metric-system-v1")
    reviewed_metric_system_is_current = _reviewed_metric_system_is_current(
        metric_system_release
    )

    def present(id_column: InstrumentedAttribute[str], expected: set[str]) -> bool:
        if not expected:
            return True
        found = set(session.scalars(select(id_column).where(id_column.in_(expected))))
        return found == expected

    metric_definitions = {
        item.id: item
        for item in session.scalars(
            select(models.MetricDefinition).where(
                models.MetricDefinition.id.in_(metric_ids)
            )
        )
    }
    metric_definitions_are_current = set(metric_definitions) == metric_ids and all(
        definition.version == metric_items[metric_id]["version"]
        and (
            definition.implementation_status == "live-calculated"
            if reviewed_metric_system_is_current
            and get_metric_contract(metric_id) is not None
            else (
                definition.implementation_status
                == metric_items[metric_id]["implementation_status"]
                and definition.required_data == metric_items[metric_id]["required_data"]
            )
        )
        for metric_id, definition in metric_definitions.items()
    )

    field_definitions = {
        item.id: item
        for item in session.scalars(
            select(models.ResearchField).where(
                models.ResearchField.id.in_(set(BROAD_PHYSICS_FIELDS))
            )
        )
    }
    ontology_is_current = len(field_definitions) == len(BROAD_PHYSICS_FIELDS) and all(
        field_definitions[definition.id].domain_id == "physics"
        and field_definitions[definition.id].parent_field_id == definition.parent_id
        and field_definitions[definition.id].aliases == list(definition.aliases)
        and field_definitions[definition.id].ontology_version
        == definition.ontology_version
        and field_definitions[definition.id].node_kind == definition.node_kind
        and field_definitions[definition.id].is_explorable
        == (definition.node_kind == "field")
        and field_definitions[definition.id].display_order == definition.display_order
        for definition in PHYSICS_FIELD_ONTOLOGY_V1.fields
    )
    return (
        session.get(models.ScienceDomain, "physics") is not None
        and ontology_is_current
        and present(models.Country.id, country_ids)
        and present(models.GeographicView.id, geographic_view_ids)
        and metric_definitions_are_current
        and metric_system_release is not None
        and (
            reviewed_metric_system_is_current
            or (
                metric_system_release.status == "experimental-withheld"
                and _metric_system_versions_are_current(metric_system_release)
                and metric_system_release.validation_evidence.get("jointGatePassed")
                is False
            )
            or (
                metric_system_release.status == "retired"
                and _metric_system_versions_are_current(metric_system_release)
            )
        )
    )


def ensure_reference_data(session: Session) -> None:
    reference_path = get_settings().reference_data_path or (
        Path(__file__).resolve().parents[3] / "src" / "data" / "demo" / "atlas.json"
    )
    if not reference_path.is_file():
        raise FileNotFoundError(
            "Physics Atlas reference data is unavailable. Configure "
            "PHYSICS_ATLAS_REFERENCE_DATA_PATH for an installed deployment."
        )
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if _reference_data_is_complete(session, payload):
        return
    seed_reference_data(session, payload)


def parsed_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result if result.tzinfo else result.replace(tzinfo=UTC)


def parsed_date(value: str | None, year: int | None = None) -> date | None:
    if value:
        segments = [int(item) for item in value.split("-")]
        return date(
            segments[0],
            segments[1] if len(segments) > 1 else 1,
            segments[2] if len(segments) > 2 else 1,
        )
    return date(year, 1, 1) if year else None


def provenance(item: dict[str, Any], default: dict[str, Any]) -> dict[str, Any]:
    value = item.get("provenance", default)
    return value if isinstance(value, dict) else default


def seed_dataset(session: Session, payload: dict[str, Any]) -> None:
    metadata = payload["metadata"]
    default_provenance = metadata["provenance"]
    state = models.DatasetState(
        id="current",
        schema_version=metadata["schemaVersion"],
        dataset_kind=metadata["datasetKind"],
        period=metadata["period"],
        generated_at=parsed_datetime(metadata["generatedAt"]),
        latest_update_at=parsed_datetime(metadata["latestUpdateAt"])
        if metadata.get("latestUpdateAt")
        else None,
        source_snapshot_ids=metadata.get("sourceSnapshotIds", []),
        update_sequence=metadata.get("updateSequence", 0),
        disclaimer=metadata["disclaimer"],
        provenance_json=provenance(metadata, default_provenance),
    )
    session.merge(state)
    for item in payload.get("scienceDomains", []):
        session.merge(
            models.ScienceDomain(
                id=item["id"],
                label=item["label"],
                description=item["description"],
                provenance_json=provenance(item, default_provenance),
            )
        )
    field_domain = {
        field_id: domain["id"]
        for domain in payload.get("scienceDomains", [])
        for field_id in domain.get("fieldIds", [])
    }
    payload_field_ids = {
        str(item["id"]) for item in payload.get("fields", []) if item.get("id")
    }
    required_ancestors = {
        ancestor.id: ancestor
        for field_id in payload_field_ids
        if PHYSICS_FIELD_ONTOLOGY_V1.contains(field_id)
        for ancestor in PHYSICS_FIELD_ONTOLOGY_V1.ancestors_of(field_id)
        if ancestor.id not in payload_field_ids
    }
    for ancestor_definition in sorted(
        required_ancestors.values(), key=lambda item: item.display_order
    ):
        session.merge(
            models.ResearchField(
                id=ancestor_definition.id,
                domain_id="physics",
                label=ancestor_definition.label,
                description=ancestor_definition.description,
                parent_field_id=ancestor_definition.parent_id,
                aliases=list(ancestor_definition.aliases),
                ontology_version=ancestor_definition.ontology_version,
                node_kind=ancestor_definition.node_kind,
                is_explorable=ancestor_definition.node_kind == "field",
                display_order=ancestor_definition.display_order,
                provider_mappings={},
                provenance_json={
                    **default_provenance,
                    "source": ancestor_definition.provenance.source,
                    "version": ancestor_definition.ontology_version,
                    "ontologyStatus": ancestor_definition.provenance.status,
                    "note": ancestor_definition.provenance.note,
                },
            )
        )
    for item in payload.get("fields", []):
        field_definition = (
            PHYSICS_FIELD_ONTOLOGY_V1.get(item["id"])
            if PHYSICS_FIELD_ONTOLOGY_V1.contains(item["id"])
            else None
        )
        session.merge(
            models.ResearchField(
                id=item["id"],
                domain_id=field_domain[item["id"]],
                label=item["label"],
                description=item["description"],
                parent_field_id=(
                    field_definition.parent_id if field_definition else None
                ),
                aliases=list(field_definition.aliases) if field_definition else [],
                ontology_version=(
                    field_definition.ontology_version
                    if field_definition
                    else "legacy-flat-physics-fields-v1"
                ),
                node_kind=field_definition.node_kind if field_definition else "field",
                is_explorable=(
                    field_definition is None or field_definition.node_kind == "field"
                ),
                display_order=(
                    field_definition.display_order if field_definition else 0
                ),
                provider_mappings={},
                provenance_json=provenance(item, default_provenance),
            )
        )
    for item in payload.get("countries", []):
        session.merge(
            models.Country(
                id=item["id"],
                iso_alpha3=item["isoAlpha3"],
                iso_alpha2=ISO_ALPHA3_TO_ALPHA2.get(item["isoAlpha3"]),
                iso_numeric=item["isoNumeric"],
                name=item["name"],
                region=item["region"],
                provenance_json=provenance(item, default_provenance),
            )
        )
    session.flush()
    for item in payload.get("geographicViews", []):
        session.merge(
            models.GeographicView(
                id=item["id"],
                country_id=item["countryId"],
                geometry_iso_numerics=item["geometryIsoNumerics"],
                location_country_ids=item["locationCountryIds"],
                provenance_json=provenance(item, default_provenance),
            )
        )
    for item in payload.get("institutions", []):
        location = item.get("location") or {}
        session.merge(
            models.Institution(
                id=item["id"],
                canonical_name=item.get("canonicalName", item["name"]),
                aliases=item.get("aliases", []),
                historical_names=item.get("historicalNames", []),
                external_ids=item.get("externalIds", []),
                identity_confidence=item.get("identityConfidence"),
                country_id=item["countryId"],
                city=item["city"],
                longitude=location.get("longitude"),
                latitude=location.get("latitude"),
                field_ids=item["fieldIds"],
                provenance_json=provenance(item, default_provenance),
            )
        )
    for item in payload.get("researchers", []):
        session.merge(
            models.Researcher(
                id=item["id"],
                canonical_name=item.get("canonicalName", item["name"]),
                aliases=item.get("aliases", []),
                historical_names=item.get("historicalNames", []),
                external_ids=item.get("externalIds", []),
                identity_confidence=item.get("identityConfidence"),
                field_ids=item["fieldIds"],
                provenance_json=provenance(item, default_provenance),
            )
        )
    session.flush()
    for entity_type, items in (
        ("institution", payload.get("institutions", [])),
        ("researcher", payload.get("researchers", [])),
    ):
        for item in items:
            refresh_search_terms(
                session,
                entity_type=entity_type,
                entity_id=item["id"],
                canonical_name=item.get("canonicalName", item["name"]),
                aliases=item.get("aliases", []),
                historical_names=item.get("historicalNames", []),
                external_ids=item.get("externalIds", []),
            )
    for entity_type, items in (
        ("institution", payload.get("institutions", [])),
        ("researcher", payload.get("researchers", [])),
    ):
        for item in items:
            for identifier in item.get("externalIds", []):
                digest = hashlib.sha256(identifier["value"].encode()).hexdigest()[:20]
                session.merge(
                    models.AuthorityIdentifier(
                        id=f"authority-{identifier['scheme']}-{digest}",
                        entity_type=entity_type,
                        entity_id=item["id"],
                        scheme=identifier["scheme"],
                        value=identifier["value"],
                        is_authoritative=True,
                        provenance_json=provenance(item, default_provenance),
                    )
                )
    for item in payload.get("researchGroups", []):
        session.merge(
            models.ResearchGroup(
                id=item["id"],
                name=item["name"],
                institution_id=item["institutionId"],
                description=item["description"],
                field_ids=item["fieldIds"],
                provenance_json=provenance(item, default_provenance),
            )
        )
    for item in payload.get("papers", []):
        session.merge(
            models.Paper(
                id=item["id"],
                title=item["title"],
                summary=item["summary"],
                publication_year=item["year"],
                publication_date=parsed_date(
                    item.get("publicationDate"), item.get("year")
                ),
                publication_date_precision=(
                    "day"
                    if item.get("publicationDate")
                    and len(item["publicationDate"]) == 10
                    else "month"
                    if item.get("publicationDate") and len(item["publicationDate"]) == 7
                    else "year"
                ),
                document_type=item.get("documentType", "article"),
                doi=item.get("doi"),
                arxiv_id=item.get("arxivId"),
                external_ids=item.get("externalIdentifiers", []),
                provenance_json=provenance(item, default_provenance),
            )
        )
        paper_external_ids = [
            *item.get("externalIdentifiers", []),
            *([{"scheme": "doi", "value": item["doi"]}] if item.get("doi") else []),
            *(
                [{"scheme": "arxiv", "value": item["arxivId"]}]
                if item.get("arxivId")
                else []
            ),
        ]
        refresh_search_terms(
            session,
            entity_type="paper",
            entity_id=item["id"],
            canonical_name=item["title"],
            aliases=[],
            historical_names=[],
            external_ids=paper_external_ids,
        )
        for field_id in item["fieldIds"]:
            session.merge(
                models.PaperField(
                    paper_id=item["id"],
                    field_id=field_id,
                    classification_method="checked-in-dataset",
                    confidence=None,
                    weight=1,
                    classification_role="unspecified",
                    ontology_version=(
                        PHYSICS_FIELD_ONTOLOGY_VERSION
                        if PHYSICS_FIELD_ONTOLOGY_V1.contains(field_id)
                        else "legacy-flat-physics-fields-v1"
                    ),
                    mapping_rule_version="checked-in-dataset-field-label-v1",
                    weighting_policy_version="synthetic-fixture-membership-v1",
                    provider_categories=[],
                    uncertainty_note=(
                        "Checked-in fixture membership; not provider-mapped evidence."
                    ),
                    provenance_json=provenance(item, default_provenance),
                )
            )
    for item in payload.get("authorships", []):
        session.merge(
            models.Authorship(
                id=item["id"],
                paper_id=item["paperId"],
                researcher_id=item["researcherId"],
                author_position=item["authorPosition"],
                provenance_json=provenance(item, default_provenance),
            )
        )
    for item in payload.get("affiliations", []):
        session.merge(
            models.Affiliation(
                id=item["id"],
                researcher_id=item["researcherId"],
                institution_id=item["institutionId"],
                research_group_id=item.get("researchGroupId"),
                start_date=parsed_date(item.get("startDate"), item.get("startYear")),
                end_date=parsed_date(item.get("endDate"), item.get("endYear")),
                source=item.get("source"),
                confidence=item.get("confidence"),
                provenance_json=provenance(item, default_provenance),
            )
        )
    metric_definition_items = {
        item["id"]: item for item in payload.get("metricDefinitions", [])
    }
    for item in metric_definition_items.values():
        session.merge(
            models.MetricDefinition(
                id=item["id"],
                name=item["name"],
                category=item["category"],
                description=item["description"],
                interpretation=item["interpretation"],
                unit=item["unit"],
                version=item["version"],
                required_data=item["requiredData"],
                implementation_status=item["implementationStatus"],
                provenance_json=provenance(item, default_provenance),
            )
        )
    session.flush()
    for item in payload.get("metricObservations", []):
        definition = metric_definition_items[item["metricId"]]
        definition_version = item.get("metricDefinitionVersion", definition["version"])
        is_legacy_observation = definition_version == "legacy-v1"
        session.merge(
            models.MetricObservation(
                id=item["id"],
                entity_type=item["entityType"],
                entity_id=item["entityId"],
                science_domain_id=item.get("scienceDomainId"),
                field_id=item.get("fieldId"),
                metric_id=item["metricId"],
                period=item["period"],
                value=item["value"],
                source=item.get("source", "checked-in-dataset"),
                metric_definition_version=definition_version,
                algorithm_version=item.get("algorithmVersion", "checked-in"),
                calculation_version=item.get(
                    "calculationVersion", metadata["schemaVersion"]
                ),
                data_source_version=item.get(
                    "dataSourceVersion", default_provenance["version"]
                ),
                acquisition_scope=item.get(
                    "acquisitionScope",
                    None
                    if is_legacy_observation
                    else f"{metadata['datasetKind']}:checked-in-fixture",
                ),
                raw_value=item.get(
                    "rawValue", None if is_legacy_observation else item["value"]
                ),
                raw_unit=item.get(
                    "rawUnit", None if is_legacy_observation else definition["unit"]
                ),
                normalization_method=item.get(
                    "normalizationMethod",
                    None if is_legacy_observation else "synthetic-fixture-identity-v1",
                ),
                normalization_parameters=item.get(
                    "normalizationParameters",
                    {} if is_legacy_observation else {"mode": "identity"},
                ),
                input_count=item.get(
                    "inputCount", None if is_legacy_observation else 1
                ),
                quality_flags=item.get(
                    "qualityFlags",
                    [] if is_legacy_observation else ["synthetic-demo"],
                ),
                calculated_at=parsed_datetime(
                    item.get("calculatedAt") or metadata["generatedAt"]
                ),
                provenance_json=provenance(item, default_provenance),
            )
        )
    for item in payload.get("historicalEvents", []):
        session.merge(
            models.HistoricalEvent(
                id=item["id"],
                title=item["title"],
                summary=item["summary"],
                year=item["year"],
                field_id=item["fieldId"],
                related_researcher_ids=item.get("relatedResearcherIds", []),
                related_institution_ids=item.get("relatedInstitutionIds", []),
                provenance_json=provenance(item, default_provenance),
            )
        )
    for item in payload.get("externalResources", []):
        session.merge(
            models.ExternalResource(
                id=item["id"],
                entity_type=item["entityType"],
                entity_id=item["entityId"],
                resource_type=item["resourceType"],
                label=item["label"],
                url=item["url"],
                source=provenance(item, default_provenance).get(
                    "source", "checked-in-dataset"
                ),
                external_id=item.get("externalId"),
                is_primary=item.get("isPrimary", False),
                verified=item.get("lastVerifiedAt") is not None,
                verification_method="checked-in-dataset"
                if item.get("lastVerifiedAt")
                else None,
                health_status="reachable" if item.get("lastVerifiedAt") else "unknown",
                last_checked_at=parsed_datetime(item["lastVerifiedAt"])
                if item.get("lastVerifiedAt")
                else None,
                valid_from=parsed_date(item.get("validFrom")),
                valid_to=parsed_date(item.get("validTo")),
                provenance_json=provenance(item, default_provenance),
            )
        )
    session.commit()


def run() -> None:
    parser = argparse.ArgumentParser(
        description="Load an explicit checked-in Atlas dataset"
    )
    parser.add_argument(
        "dataset", type=Path, help="Path to a validated Atlas JSON export"
    )
    args = parser.parse_args()
    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    with SessionLocal() as session:
        seed_dataset(session, payload)


if __name__ == "__main__":
    run()
