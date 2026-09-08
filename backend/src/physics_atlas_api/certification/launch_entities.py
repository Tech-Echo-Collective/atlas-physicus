"""Pure, source-bound UI projection, with no provider reads or payload storage.

This does not certify metrics or invent current employment/abstracts. All supported
papers and profile relationships are retained; the caller measures the result
before choosing a transport. Geographic views are supplied reference policy,
never inferred from scientific affiliation or copied synthetic entity records.
"""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import pycountry

from .. import schemas
from ..fields import PHYSICS_FIELD_ONTOLOGY_V1
from ..metrics.dataset import AtlasDatasetEntities
from .automation import (
    UNAMBIGUOUS_RESEARCHER_RULE_VERSION,
    ResolvedResearcherIdentifiers,
    automatic_known_researcher_decision,
    unambiguous_researcher_subset,
)
from .contracts import CertificationError, EvidenceReference, canonical_digest
from .fields import automatic_field_ledger
from .launch_attribution import (
    LaunchAffiliationResolution,
    LaunchAttributionResult,
)
from .launch_inputs import LaunchCanonicalPaper, canonicalize_launch_inputs
from .launch_years import _validate_attribution

LAUNCH_ENTITIES_VERSION = "source-bound-atlas-entities-v1"


@dataclass(frozen=True)
class LaunchEntitiesBuild:
    entities: AtlasDatasetEntities
    byte_length: int
    entity_counts: tuple[tuple[str, int], ...]
    omitted_counts: tuple[tuple[str, int], ...]
    source_references: tuple[EvidenceReference, ...]
    version: str = LAUNCH_ENTITIES_VERSION


def _provenance(
    reference: EvidenceReference, dataset_version: str, acquisition_scope: str
) -> schemas.Provenance:
    return schemas.Provenance(
        source=f"{reference.provider} source-bound evidence",
        source_type="external-api",
        version=dataset_version,
        status="verified",
        source_record_id=reference.source_record_id,
        source_snapshot_id=reference.source_snapshot_id,
        acquisition_scope=acquisition_scope,
    )


def _reference_entities(
    geographic_views: tuple[schemas.GeographicViewOut, ...],
) -> AtlasDatasetEntities:
    ontology = PHYSICS_FIELD_ONTOLOGY_V1
    provenance = schemas.Provenance(
        source="Atlas Physicus reference vocabulary; not measured research coverage",
        source_type="derived",
        version=ontology.version,
        status="verified",
    )
    countries = [
        schemas.CountryOut(
            id=f"country-{country.alpha_2.casefold()}",
            iso_alpha3=country.alpha_3,
            iso_numeric=country.numeric,
            name=country.name,
            region="Global",
            provenance=schemas.Provenance(
                source="ISO 3166-1 reference geography via pycountry",
                source_type="derived",
                version=f"pycountry-{pycountry.__version__}",
                status="verified",
            ),
        )
        for country in sorted(pycountry.countries, key=lambda item: item.alpha_2)
    ]
    country_ids = {item.id for item in countries}
    geometry_ids = {item.iso_numeric for item in countries}
    used_countries: set[str] = set()
    used_geometries: set[str] = set()
    used_view_ids: set[str] = set()
    for view in geographic_views:
        if (
            view.country_id not in country_ids
            or view.country_id in used_countries
            or view.id in used_view_ids
            or not view.geometry_iso_numerics
            or not view.location_country_ids
            or len(set(view.geometry_iso_numerics)) != len(view.geometry_iso_numerics)
            or len(set(view.location_country_ids)) != len(view.location_country_ids)
            or not set(view.geometry_iso_numerics) <= geometry_ids
            or not set(view.location_country_ids) <= country_ids
            or used_geometries.intersection(view.geometry_iso_numerics)
            or view.provenance.status == "synthetic"
            or view.provenance.source_type == "synthetic-demo"
        ):
            raise CertificationError("launch geographic reference policy is invalid")
        used_countries.add(view.country_id)
        used_view_ids.add(view.id)
        used_geometries.update(view.geometry_iso_numerics)
    return AtlasDatasetEntities(
        science_domains=[
            schemas.ScienceDomainOut(
                id=ontology.domain_id,
                label="Physics",
                description=(
                    "Physics research fields; measured coverage is dataset-specific."
                ),
                field_ids=[item.id for item in ontology.fields],
                provenance=provenance,
            )
        ],
        fields=[
            schemas.ResearchFieldOut(
                id=item.id,
                label=item.label,
                description=item.description,
                parent_field_id=item.parent_id,
                aliases=list(item.aliases),
                ontology_version=item.ontology_version,
                node_kind=item.node_kind,
                is_explorable=item.node_kind == "field",
                display_order=item.display_order,
                provenance=provenance,
            )
            for item in ontology.fields
        ],
        countries=countries,
        geographic_views=list(geographic_views),
    )


def _resources(entities: AtlasDatasetEntities) -> list[schemas.ExternalResourceOut]:
    """Exact identifier links only; no invented homepage or live health claim."""
    links = []
    groups = (
        ("institution", entities.institutions),
        ("researcher", entities.researchers),
        ("paper", entities.papers),
    )
    for entity_type, records in groups:
        for record in records:
            identifiers = (
                record.external_identifiers
                if isinstance(record, schemas.PaperOut)
                else record.external_ids
            )
            for identifier in identifiers:
                scheme, value = identifier.scheme, identifier.value
                prefix = {
                    "ror": "https://ror.org/",
                    "orcid": "https://orcid.org/",
                    "arxiv": "https://arxiv.org/abs/",
                    "doi": "https://doi.org/",
                    "inspire-author": "https://inspirehep.net/authors/",
                    "inspire": "https://inspirehep.net/literature/",
                }.get(scheme)
                if prefix is None:
                    continue
                key = entity_type, record.id, scheme, value
                links.append(
                    schemas.ExternalResourceOut(
                        id=f"resource-{canonical_digest(key)}",
                        entity_type=entity_type,
                        entity_id=record.id,
                        resource_type="inspire"
                        if scheme == "inspire-author"
                        else scheme,
                        label=f"{scheme.upper()}: {value}",
                        url=prefix + quote(value, safe="/"),
                        source=scheme,
                        source_record_id=value,
                        external_id=identifier,
                        is_primary=False,
                        verified=False,
                        health_status="unknown",
                        provenance=record.provenance,
                    )
                )
    return sorted(links, key=lambda item: item.id)


def build_launch_entities(
    papers: tuple[LaunchCanonicalPaper, ...],
    attributions: tuple[LaunchAttributionResult, ...],
    *,
    geographic_views: tuple[schemas.GeographicViewOut, ...],
    source_snapshots: tuple[schemas.SourceSnapshotOut, ...] = (),
    researcher_projection_version: str | None = None,
) -> LaunchEntitiesBuild:
    """Return all supported UI facts and exact size, without truncation or I/O.

    ``source_references`` must remain in the final compact evidence manifest:
    provenance IDs link there to original checksums, not mutable source URLs.
    Missing labels/coordinates remain unavailable, not generated replacements.
    """
    if researcher_projection_version not in {None, UNAMBIGUOUS_RESEARCHER_RULE_VERSION}:
        raise CertificationError("unsupported UI researcher projection version")
    if not papers or len({paper.paper_id for paper in papers}) != len(papers):
        raise CertificationError(
            "launch UI projection requires unique canonical papers"
        )
    occurrences = tuple(item for paper in papers for item in paper.occurrences)
    contexts = {
        (
            item.source_facts.context.dataset_version,
            item.source_facts.context.acquisition_scope,
        )
        for item in occurrences
    }
    if len(contexts) != 1:
        raise CertificationError("launch UI projection cannot mix datasets/scopes")
    version, scope = next(iter(contexts))
    results = {item.paper_reference: item for item in attributions}
    if len(results) != len(attributions) or set(results) != {
        item.reference for item in occurrences
    }:
        raise CertificationError("launch UI attribution inventory is not exact")
    entities = _reference_entities(geographic_views)
    references: set[EvidenceReference] = set()
    omitted: Counter[str] = Counter()
    institution_facts: dict[str, list[LaunchAffiliationResolution]] = defaultdict(list)
    institution_fields: dict[str, set[str]] = defaultdict(set)
    researcher_names: dict[str, set[str]] = defaultdict(set)
    researcher_external_ids: dict[str, set[tuple[str, str]]] = defaultdict(set)
    researcher_fields: dict[str, set[str]] = defaultdict(set)
    researcher_references: dict[str, set[EvidenceReference]] = defaultdict(set)
    authorships: dict[tuple[str, str], schemas.AuthorshipOut] = {}
    affiliations: dict[tuple[str, str, str], schemas.AffiliationOut] = {}

    for paper in sorted(papers, key=lambda item: item.paper_id):
        if canonicalize_launch_inputs(paper.occurrences).papers != (paper,):
            raise CertificationError(
                "launch UI canonical identity does not reconstruct"
            )
        for occurrence in paper.occurrences:
            result = results[occurrence.reference]
            _validate_attribution(occurrence, result)
            references.update(occurrence.identity_references)
            references.update(
                ref
                for affiliation in result.affiliations
                for ref in affiliation.evidence
            )
        if paper.component.status != "matched":
            omitted["unresolved_paper_identity"] += 1
            continue
        dates = {item.source_facts.exact_date for item in paper.occurrences}
        if len(dates) != 1 or None in dates:
            omitted["paper_without_consistent_exact_date"] += 1
            continue
        publication_date = next(iter(dates))
        assert publication_date is not None
        ordered = sorted(
            paper.occurrences, key=lambda item: canonical_digest(item.reference)
        )
        labeled = [item for item in ordered if item.identity.title]
        if not labeled:
            omitted["paper_without_source_title"] += 1
            continue
        primary = labeled[0]
        document_types = {item.identity.document_type for item in ordered}
        if len(document_types) != 1 or None in document_types:
            omitted["paper_without_consistent_document_type"] += 1
            continue
        document_type = next(iter(document_types))
        assert document_type is not None
        field_ids = sorted(
            item.field_id
            for item in automatic_field_ledger(paper.field_evidence).assignments
        )
        identifiers = sorted(
            {identifier for item in ordered for identifier in item.identity.identifiers}
        )
        by_scheme = defaultdict(list)
        for identifier in identifiers:
            by_scheme[identifier.scheme].append(identifier.value)
        provenance = _provenance(primary.reference, version, scope)
        entities.papers.append(
            schemas.PaperOut(
                id=paper.paper_id,
                title=primary.identity.title or "",  # guarded above, never generated
                summary="Abstract not retained in this bounded Atlas dataset.",
                year=publication_date.year,
                publication_date=publication_date,
                publication_date_precision="day",
                document_type=document_type,
                field_ids=field_ids,
                doi=by_scheme["doi"][0] if len(by_scheme["doi"]) == 1 else None,
                arxiv_id=by_scheme["arxiv"][0]
                if len(by_scheme["arxiv"]) == 1
                else None,
                external_identifiers=[
                    schemas.ExternalIdentifier(scheme=item.scheme, value=item.value)
                    for item in identifiers
                ],
                provenance=provenance,
            )
        )
        # Never choose a favorable byline among differing merged source records.
        # Receipt IDs differ across occurrences; compare consumed facts, not paths.
        author_signatures = {
            canonical_digest(
                (
                    item.authors,
                    tuple(
                        tuple((fact.scheme, fact.value) for fact in author.facts)
                        for author in item.source_facts.authors
                    ),
                )
            )
            for item in ordered
        }
        if len(ordered) > 1 and len(author_signatures) > 1:
            omitted["paper_with_multiple_unreconciled_bylines"] += 1
            continue
        occurrence = primary
        result = results[occurrence.reference]
        subset = (
            unambiguous_researcher_subset(occurrence.source_facts)
            if researcher_projection_version is not None
            else None
        )
        safe_authors = subset is not None or (
            automatic_known_researcher_decision(
                occurrence.source_facts, entity_type="institution"
            ).state
            == "certified"
        )
        author_ids: dict[int, str] = {}
        for author, assessment in zip(
            occurrence.authors,
            occurrence.source_facts.researcher_assessments,
            strict=True,
        ):
            value = assessment.value
            assert isinstance(value, ResolvedResearcherIdentifiers)
            known = dict(value.identifiers).get("inspire-author")
            if (
                not safe_authors
                or (
                    subset is not None
                    and author.author_position not in subset.admitted_author_positions
                )
                or assessment.decision.state != "certified"
                or known is None
            ):
                omitted["author_without_supported_identity"] += 1
                continue
            researcher_id = f"inspire-author:{known}"
            if not author.display_name:
                omitted["author_without_source_name"] += 1
                continue
            author_ids[author.author_position] = researcher_id
            researcher_names[researcher_id].add(author.display_name)
            researcher_external_ids[researcher_id].update(value.identifiers)
            researcher_fields[researcher_id].update(field_ids)
            researcher_references[researcher_id].add(occurrence.reference)
            key = paper.paper_id, researcher_id
            authorships[key] = schemas.AuthorshipOut(
                id=f"authorship-{canonical_digest(key)}",
                paper_id=paper.paper_id,
                researcher_id=researcher_id,
                author_position=author.author_position,
                provenance=_provenance(occurrence.reference, version, scope),
            )
        for resolution in result.affiliations:
            institution = resolution.institution
            if (
                resolution.state != "certified"
                or institution is None
                or not institution.canonical_institution_id
                or not resolution.canonical_name
                or not resolution.country_code
            ):
                omitted["affiliation_without_certified_institution"] += 1
                continue
            institution_id = institution.canonical_institution_id
            institution_facts[institution_id].append(resolution)
            institution_fields[institution_id].update(field_ids)
            affiliated_researcher_id = author_ids.get(resolution.author_position)
            if affiliated_researcher_id is None:
                omitted["institution_link_without_supported_researcher"] += 1
                continue
            affiliation_key = paper.paper_id, affiliated_researcher_id, institution_id
            affiliations[affiliation_key] = schemas.AffiliationOut(
                id=f"paper-affiliation-{canonical_digest(affiliation_key)}",
                paper_id=paper.paper_id,
                researcher_id=affiliated_researcher_id,
                institution_id=institution_id,
                start_date=publication_date.isoformat(),
                end_date=publication_date.isoformat(),
                source=(
                    "Paper-time affiliation only; not current or continuous employment"
                ),
                provenance=_provenance(occurrence.reference, version, scope),
            )

    country_ids = {item.id for item in entities.countries}
    for institution_id, facts in sorted(institution_facts.items()):
        country_codes = {item.country_code for item in facts}
        if len(country_codes) != 1:
            raise CertificationError(
                "certified institution has conflicting location countries"
            )
        country_id = f"country-{str(next(iter(country_codes))).casefold()}"
        if country_id not in country_ids:
            raise CertificationError(
                "certified institution country is not in ISO reference"
            )
        names = sorted({item.canonical_name for item in facts if item.canonical_name})
        locations = {location for item in facts for location in item.locations}
        coordinates = {(item.longitude, item.latitude) for item in locations}
        cities = sorted({item.city for item in locations if item.city})
        location = None
        if len(coordinates) == 1:
            longitude, latitude = next(iter(coordinates))
            if longitude is not None and latitude is not None:
                location = schemas.InstitutionLocation(
                    longitude=longitude, latitude=latitude
                )
        if location is None:
            omitted["institution_without_single_supported_map_position"] += 1
        ror_refs = {
            reference
            for item in facts
            for reference in item.evidence
            if reference.provider == "ror"
            and f"institution-ror-{reference.source_record_id}" == institution_id
        }
        if not ror_refs:
            raise CertificationError("institution UI identity lacks exact ROR evidence")
        reference = min(ror_refs, key=canonical_digest)
        entities.institutions.append(
            schemas.InstitutionOut(
                id=institution_id,
                name=names[0],
                canonical_name=names[0],
                aliases=names[1:],
                external_ids=[
                    schemas.ExternalIdentifier(
                        scheme="ror", value=reference.source_record_id
                    )
                ],
                country_id=country_id,
                city=" / ".join(cities)
                if cities
                else "City not available in source evidence",
                field_ids=sorted(institution_fields[institution_id]),
                location=location,
                provenance=_provenance(reference, version, scope),
            )
        )
    for researcher_id, observed_names in sorted(researcher_names.items()):
        names = sorted(observed_names)
        external_ids = researcher_external_ids[researcher_id]
        orcids = {value for scheme, value in external_ids if scheme == "orcid"}
        if len(orcids) > 1:
            omitted["researcher_with_conflicting_cross_source_orcid"] += 1
        entities.researchers.append(
            schemas.ResearcherOut(
                id=researcher_id,
                name=names[0],
                canonical_name=names[0],
                aliases=names[1:],
                external_ids=[
                    schemas.ExternalIdentifier(scheme=scheme, value=value)
                    for scheme, value in sorted(external_ids)
                    if scheme != "orcid" or len(orcids) == 1
                ],
                field_ids=sorted(researcher_fields[researcher_id]),
                provenance=_provenance(
                    min(researcher_references[researcher_id], key=canonical_digest),
                    version,
                    scope,
                ),
            )
        )
    entities.authorships = [authorships[key] for key in sorted(authorships)]
    entities.affiliations = [affiliations[key] for key in sorted(affiliations)]
    entities.external_resources = _resources(entities)
    if len({snapshot.id for snapshot in source_snapshots}) != len(
        source_snapshots
    ) or any(
        item.provenance.status == "synthetic"
        or item.provenance.source_type == "synthetic-demo"
        for item in source_snapshots
    ):
        raise CertificationError("launch UI snapshot metadata is invalid")
    entities.source_snapshots = sorted(source_snapshots, key=lambda item: item.id)
    payload: dict[str, Any] = entities.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return LaunchEntitiesBuild(
        entities=entities,
        byte_length=len(serialized),
        entity_counts=tuple(
            sorted((key, len(value)) for key, value in payload.items())
        ),
        omitted_counts=tuple(sorted(omitted.items())),
        source_references=tuple(sorted(references, key=canonical_digest)),
    )
