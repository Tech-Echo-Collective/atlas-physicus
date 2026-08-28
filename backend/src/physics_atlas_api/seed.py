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
from .config import get_settings
from .database import SessionLocal
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
    "version": "v3.0.4-alpha",
    "status": "unverified",
}

BROAD_PHYSICS_FIELDS = {
    "hep-th": ("High Energy Theory", "Theoretical high-energy physics."),
    "hep-ph": ("High Energy Phenomenology", "Phenomenology of high-energy physics."),
    "hep-ex": ("High Energy Experiment", "Experimental high-energy physics."),
    "gr-qc": ("General Relativity / Quantum Cosmology", "Gravitation and cosmology."),
    "quant-ph": ("Quantum Information", "Quantum information and foundations."),
    "astro-ph": ("Astrophysics", "Astrophysics and cosmology."),
    "cond-mat": ("Condensed Matter", "Condensed-matter physics."),
    "amo": (
        "Atomic / Molecular / Optical Physics",
        "Atomic, molecular, and optical physics.",
    ),
    "nucl-th": ("Nuclear Theory", "Theoretical nuclear physics."),
    "nucl-ex": ("Nuclear Experiment", "Experimental nuclear physics."),
    "plasma": ("Plasma Physics", "Plasma physics."),
    "biophysics": ("Biophysics", "Physics methods applied to biological systems."),
    "math-ph": ("Mathematical Physics", "Mathematical structures in physics."),
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


def seed_reference_data(session: Session, payload: dict[str, Any]) -> None:
    """Seed non-observational reference data without copying demo entities."""
    session.merge(
        models.ScienceDomain(
            id="physics",
            label="Physics",
            description="The Physics science domain.",
            provenance_json=REFERENCE_PROVENANCE,
        )
    )
    demo_fields = {item["id"]: item for item in payload.get("fields", [])}
    for field_id, (label, description) in BROAD_PHYSICS_FIELDS.items():
        item = demo_fields.get(field_id, {})
        session.merge(
            models.ResearchField(
                id=field_id,
                domain_id="physics",
                label=item.get("label", label),
                description=item.get("description", description),
                provider_mappings={},
                provenance_json=REFERENCE_PROVENANCE,
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
        name, description, interpretation = REFERENCE_METRIC_TEXT.get(
            item["id"],
            (item["name"], item["description"], item["interpretation"]),
        )
        session.merge(
            models.MetricDefinition(
                id=item["id"],
                name=name,
                category=item["category"],
                description=description,
                interpretation=interpretation,
                unit="taxonomy definition only",
                version=item["version"],
                required_data=["future validated source data and reviewed methodology"],
                implementation_status="taxonomy-only",
                provenance_json=REFERENCE_PROVENANCE,
            )
        )
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
    metric_ids = {item["id"] for item in payload.get("metricDefinitions", [])}

    def present(id_column: InstrumentedAttribute[str], expected: set[str]) -> bool:
        if not expected:
            return True
        found = set(session.scalars(select(id_column).where(id_column.in_(expected))))
        return found == expected

    return (
        session.get(models.ScienceDomain, "physics") is not None
        and present(models.ResearchField.id, set(BROAD_PHYSICS_FIELDS))
        and present(models.Country.id, country_ids)
        and present(models.GeographicView.id, geographic_view_ids)
        and present(models.MetricDefinition.id, metric_ids)
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
    for item in payload.get("fields", []):
        session.merge(
            models.ResearchField(
                id=item["id"],
                domain_id=field_domain[item["id"]],
                label=item["label"],
                description=item["description"],
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
    for item in payload.get("metricDefinitions", []):
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
                algorithm_version=item.get("algorithmVersion", "checked-in"),
                calculation_version=item.get(
                    "calculationVersion", metadata["schemaVersion"]
                ),
                data_source_version=metadata["schemaVersion"],
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
