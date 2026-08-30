# Data model

## Design goals

The model supports the alpha interaction while keeping source evidence, canonical identity, temporal relationships, profiles, and metrics separate across validated frontend contracts and the v3.0.5 PostgreSQL/FastAPI implementation.

The JSON dataset is normalized: countries do not embed duplicated institution or researcher records. Relationships use stable identifiers.

## Core entities

### ScienceDomain

Groups research fields above the field level without changing their identifiers.

| Property | Meaning |
| --- | --- |
| `id` | Stable domain identifier |
| `label` | Human-readable domain name |
| `description` | Short exploration description |
| `fieldIds` | References to fields within the domain |

v3.0.5-alpha contains only `Physics`. The array structure supports future domains, but no non-physics data is included. The live reference bootstrap expands the Physics field vocabulary without adding non-physics observations.

### ResearchField

Represents a physics classification used to filter the atlas.

| Property | Meaning |
| --- | --- |
| `id` | Stable Atlas field identifier; provider category strings remain separate evidence |
| `label` | Human-readable field name |
| `description` | Short scope description |
| `parentFieldId` | Optional parent in the versioned Atlas hierarchy |
| `aliases` | Reviewed discovery labels, not provider-classification evidence |
| `ontologyVersion`, `nodeKind` | Exact ontology lineage and branch/field role |
| `isExplorable`, `displayOrder` | Navigation eligibility and deterministic ordering |

The local synthetic dataset still exercises a small subset. The reference
bootstrap now stores the broad [Physics Field Ontology v1](field-ontology.md),
while the live acquisition scope remains bounded to `hep-th-v1`.

### Country

Represents a geographic location entity and the direct ISO join for world geometry.

| Property | Meaning |
| --- | --- |
| `id` | Internal stable identifier |
| `isoAlpha3` | ISO three-letter country code |
| `isoNumeric` | ISO numeric code used to join world geometry |
| `name` | Display name |
| `region` | Broad geographic region |

### GeographicView

Defines membership in a country exploration canvas without changing location or attribution records.

| Property | Meaning |
| --- | --- |
| `id` | Stable view identifier |
| `countryId` | Country entity presented by the exploration view |
| `geometryIsoNumerics` | Source geometries rendered and fitted in the view |
| `locationCountryIds` | Location entities whose institutions appear in the view |
| `provenance` | Origin classification |

This mapping is consumed only by geographic navigation and institution visibility. It does not assign papers, researchers, or metrics to a different entity.

### Institution

Represents a research institution located in one country.

| Property | Meaning |
| --- | --- |
| `id` | Internal stable identifier |
| `canonicalName` | Preferred official display name |
| `aliases`, `historicalNames` | Resolved variants retained without changing identity |
| `externalIds` | Authority-issued identifiers such as INSPIRE or ROR when available |
| `identityConfidence` | Confidence in the canonical identity, not a metric |
| `name` | Deprecated alpha UI compatibility label |
| `countryId` | Reference to `Country` |
| `city` | Display location |
| `fieldIds` | References to represented research fields |
| `location` | Optional longitude and latitude used by the map |

### Researcher

Represents a research person independently from affiliation records.

| Property | Meaning |
| --- | --- |
| `id` | Internal stable identifier |
| `canonicalName` | Preferred display name |
| `aliases` | Name variants and initials supported by source evidence |
| `externalIds` | Authority-issued identifiers such as ORCID or INSPIRE |
| `identityConfidence` | Confidence in the canonical identity, not a metric |
| `name` | Deprecated alpha UI compatibility label |
| `fieldIds` | References to research fields |
| `externalLinks` | Deprecated compatibility field; URLs belong in `ExternalResource` |

The optional legacy `institutionId` remains schema-compatible with Phase 2.1 data, but current fixtures use normalized `Affiliation` records instead.

### ResearchGroup

Represents a named research community hosted by an institution.

| Property | Meaning |
| --- | --- |
| `id` | Internal stable identifier |
| `name` | Display name |
| `institutionId` | Reference to the host `Institution` |
| `description` | Short demo scope description |
| `fieldIds` | References to associated research fields |

Group membership is derived from affiliations rather than embedded researcher arrays.

### Affiliation

Connects a researcher to an institution and optionally a research group.

| Property | Meaning |
| --- | --- |
| `id` | Stable relationship identifier |
| `researcherId` | Reference to `Researcher` |
| `institutionId` | Reference to `Institution` |
| `researchGroupId` | Optional reference to a group at that institution |
| `startDate`, `endDate` | Optional ISO year, month, or date bounds; an omitted end is open-ended or unknown |
| `source` | Source assertion for the relationship |
| `confidence` | Confidence in the affiliation assertion |
| `provenance` | Origin classification |

Affiliations are separate records so metadata can represent multiple, concurrent, and historical institutions without duplicating researchers. Legacy `startYear` and `endYear` remain accepted for existing fixtures. A missing bound means unknown; it must not be interpreted as permanent employment.

### Paper and Authorship

`Paper` is a normalized record with a title, summary, year, fields, and provenance. Optional `doi`, `arxivId`, and generic `externalIdentifiers` preserve source identifiers; resolvable URLs belong in `ExternalResource`. Synthetic paper records remain interface preparation data. Pilot papers come from the bounded ingestion snapshot, retain an INSPIRE external identifier, and intentionally use a placeholder summary instead of source abstract text. `Authorship` is a join record that connects one paper to one researcher and preserves author position.

Papers do not embed researchers, institutions, or countries. Multi-institution collaboration is derived by traversing authorship and affiliation relationships.

### HistoricalEvent

Prepares field history and timeline connections.

| Property | Meaning |
| --- | --- |
| `id` | Stable event identifier |
| `title`, `summary` | Demo event description |
| `year` | Timeline year |
| `fieldId` | Reference to the connected field |
| `relatedResearcherIds` | Researcher references |
| `relatedInstitutionIds` | Institution references |
| `provenance` | Origin classification |

### ExternalIdentifier

Represents an authority-issued identifier as a scheme/value pair. Examples include ROR, ORCID, INSPIRE institution records, and INSPIRE author records. It does not carry a URL; resolvable links are separate resource records.

### RawEntityRecord

Preserves an immutable institution, researcher, or paper source input before resolution/canonicalization.

| Property | Meaning |
| --- | --- |
| `id` | Stable raw-record identifier |
| `entityType` | Institution, researcher, or paper |
| `sourceRecordId` | Identifier in the source system |
| `sourceSnapshotId` | Optional reference to the captured source snapshot |
| `rawName` | Unchanged source-facing name |
| `externalIds` | Source-supplied authority identifiers |
| `attributes` | Bounded source context used as evidence |
| `ingestedAt` | Ingestion timestamp |
| `provenance` | Source/version record |

`Affiliation` represents a profile or bounded temporal relationship. It is not
allowed to overwrite publication-time evidence.

### PaperAffiliation

Stores one resolved or explicitly withheld paper-time affiliation share. It
records paper, provider author slot, optional canonical researcher,
institution/country only when resolved, raw affiliation/subunit evidence,
source snapshot and dataset version, exact fraction numerators/denominators,
resolution statuses, contribution statements, and attribution/materialization
versions. Current rows may be superseded by a new source snapshot, but older
materializations remain auditable. See
[Scientific Attribution](scientific-attribution.md).

### IdentityResolution

Records an auditable decision between a raw record and a canonical entity.

| Property | Meaning |
| --- | --- |
| `rawEntityRecordId` | Evidence record being resolved |
| `status` | `matched`, `ambiguous`, or `unresolved` |
| `canonicalEntityId` | Present only for a matched identity |
| `method` | External ID, canonical name, alias, historical name, fuzzy name, or manual review |
| `confidence` | Identity-decision confidence from 0 to 1 |
| `evidence` | Input, canonical candidate, method, and score records |
| `resolverVersion`, `resolvedAt` | Reproducibility metadata |
| `provenance` | Derived-data provenance |

Runtime validation rejects a matched decision without a canonical entity or method, and rejects an ambiguous or unresolved decision that silently names a canonical entity. The full policy is documented in [entity resolution](entity-resolution.md).

### ExternalResource

Associates a canonical institution, research group, researcher, or paper with a typed URL.

| Property | Meaning |
| --- | --- |
| `entityType`, `entityId` | Canonical owner of the resource |
| `resourceType` | Official institution site, department site, group site, researcher homepage, ORCID, INSPIRE, arXiv, or DOI |
| `label`, `url` | Display label and validated URL |
| `externalId` | Optional associated authority identifier |
| `isPrimary` | Preferred resource within its type or context |
| `validFrom`, `validTo` | Optional resource-validity bounds |
| `lastVerifiedAt` | Optional verification timestamp |
| `provenance` | Source/version record |

The persistent API model additionally records `source`, `sourceRecordId`, `verified`, `verificationMethod`, `lastCheckedAt`, `httpStatus`, `redirectTarget`, `createdAt`, and `updatedAt`. `ResourceCheck` history retains individual reachability, redirect, timeout, and failure outcomes without deleting the resource or rewriting its original provenance.

URLs are deliberately outside canonical entity records so they can be versioned, deprecated, deduplicated, or verified independently.

### SourceSnapshot and DatasetUpdate

`SourceSnapshot` describes an immutable full or incremental source capture: source, version, capture time, record count, optional parent snapshot, checksum, storage reference, and provenance. `DatasetUpdate` describes a full, incremental, or reprocessing build with source snapshot IDs, previous/new dataset versions, resolver and metric versions, change counts, application time, and provenance.

Dataset metadata can identify its latest update time, source snapshots, and update sequence. PostgreSQL persists these records with `SourceCursor` and `UpdateRun`; the worker applies bounded schedules and resumable checkpoints without changing the frontend lineage contract.

### DataProvenance

Every validated entity, relationship, historical event, paper, and metric observation carries a structured provenance object.

| Property | Meaning |
| --- | --- |
| `source` | Human-readable source name |
| `sourceType` | Synthetic demo, external API, institutional source, or derived data |
| `version` | Source or dataset version |
| `status` | Synthetic, unverified, verified, or deprecated |
| `confidence` | Optional normalized confidence from 0 to 1 |
| `retrievedAt` | Optional retrieval timestamp |

v3.0.5-alpha normalizes the static fixture's `synthetic-demo` shorthand into an explicit object and preserves separate external-API or derived provenance on pilot records. Deterministic backend connector fixtures are also explicitly labeled synthetic/demo across snapshots, raw records, canonical entities, and dataset metadata. Pilot provenance includes the INSPIRE snapshot version and retrieval time; identity, affiliation, and search confidence describe different technical decisions and are never scientific-quality scores.

### MetricDefinition

Describes a discoverable metric independently from calculated values.

| Property | Meaning |
| --- | --- |
| `id` | Stable registry identifier |
| `name` | Human-readable layer name |
| `category` | Metric family or registry grouping |
| `description` | Intended interpretation and limitations |
| `interpretation` | Plain-language reading guidance |
| `unit` | Display unit |
| `version` | Definition version |
| `requiredData` | Inputs expected by a future calculator |
| `implementationStatus` | Synthetic demonstration, pilot-calculated, live-calculated, experimental-candidate, or taxonomy-only status |
| `provenance` | Structured origin metadata |

### MetricObservation

Stores a metric value separately from entity identity and presentation.

| Property | Meaning |
| --- | --- |
| `id` | Stable observation identifier |
| `entityType` | Type of entity being observed |
| `entityId` | Reference to the observed entity |
| `scienceDomainId` | Optional science-domain context |
| `fieldId` | Optional research-field context |
| `metricId` | Metric identity |
| `period` | Observation year in the alpha |
| `value` | Provided metric value |
| `source` | Source label for the calculated value |
| `metricDefinitionVersion` | Exact scientific definition used for interpretation |
| `algorithmVersion` | Calculator or methodology version |
| `calculationVersion` | Particular calculation/release version |
| `dataSourceVersion`, `acquisitionScope` | Immutable input dataset/update and bounded source scope |
| `rawValue`, `rawUnit` | Preserved pre-normalization observation |
| `normalizationMethod`, `normalizationParameters` | Versioned transform and fitted reconstruction record |
| `inputCount`, `qualityFlags` | Evidence amount and explicit calculation warnings |
| `calculatedAt` | Optional calculation timestamp for generated observations |
| `provenance` | Structured source metadata |

Each observation must identify either a science domain or a research field and reference a registered metric definition. Supported entity types now include science domains, research fields, countries, institutions, research groups, and researchers. The fixture currently provides country and institution map observations.

The synthetic source registers five visualization definitions: Research Activity, Research Impact, Collaboration / Connectivity, Research Diversity, and Research Momentum / Sustainability. The INSPIRE-HEP pilot calculates only Research Activity, Research Impact, Collaboration / Connectivity, and Research Momentum / Sustainability; its Diversity, Talent Ecosystem, and Concentration / Vulnerability definitions remain taxonomy-only. Multiple observations may share an entity and scope while carrying different metric IDs and periods. Neither the synthetic transformations nor the bounded pilot values are validated scientific measurements.

The live registry exposes the same five scientific categories as
`experimental-candidate` definitions. They are reviewable methodology but are
not visualization-ready and cannot enter live map requests or composites. The
current production dataset contains no live metric observations.

Public observation reads join every row to the currently published
`MetricDefinition.version` and the current dataset provenance version. Within
one exact entity/scope/period partition, a newer calculation is selected only
when all current rows use one algorithm version; conflicting algorithms fail
closed. Historical rows remain stored for audit but cannot compete with the
current map or profile value.

### MetricSystemRelease

Records the joint publication state for exactly the five Metric System v1
dimensions. The manifest binds metric and algorithm IDs to attribution,
ontology, mapping, and threshold versions plus validation evidence. Live API
reads fail closed unless one `active` manifest contains all five exact IDs and
records that the Joint Activation Gate passed; partial metric publication is
not a valid state.

## Preserved pilot canonical records

The preserved v3.0.3 pilot maps the 81-record INSPIRE-HEP snapshot through normalization and the canonical identity layer. INSPIRE control numbers identify papers; authority references and external identifiers supply the strongest researcher and institution evidence. Institution address country codes map to ISO country records. `Authorship` and temporal `Affiliation` joins retain participation relationships without embedding authors or institutions inside papers.

The resulting snapshot contains 35 countries, 143 institutions, 178 unique researchers, 187 authorships, and 234 resolved source affiliation mentions. Of the 143 institutions, 126 have coordinates and 17 remain attribution entities that cannot render as map nodes. Every normalized pilot record retains external or derived provenance. These counts describe only the three-record-per-year engineering sample documented in the [pilot study](pilot-study.md).

Pilot affiliations are dated source observations from paper metadata, not asserted employment intervals. They preserve when an affiliation was observed without assuming continuity between publications.

## Relationships

The conceptual model includes:

```text
RawEntityRecord ── IdentityResolution ──> canonical Institution / Researcher
Researcher <── temporal Affiliation ──> Institution
                                  └──> ResearchGroup
Institution ── located in ──> Country
GeographicView ── renders ──> Geometry / institution-location membership
Researcher <── Authorship ──> Paper
Paper ── belongs to ──> ResearchField
ExternalResource ── belongs to ──> Institution / ResearchGroup / Researcher / Paper
HistoricalEvent ── connects ──> ResearchField / Researcher / Institution
MetricDefinition ── identifies ──> MetricObservation ── observes ──> Entity
SourceSnapshot ── produces through DatasetUpdate ──> versioned AtlasDataset
```

The synthetic source implements these relationships as preparation records. The pilot exercises a narrow identifier-led resolution path using source record references and emits canonical identity, temporal affiliation, resource, snapshot, and update-lineage records. It does not provide general multi-source disambiguation, externally verified historical affiliations, citation edges, or complete publication metadata.

Country aggregation must be derived from affiliation relationships rather than by assigning a paper to one country. Geographic rendering remains separate from this attribution model, as defined by the [geographic representation policy](geography-policy.md).

## Profile read models

`ProfileService` creates transport-independent read models without adding embedded profile records to `AtlasDataset`:

- `InstitutionProfileData`: canonical institution, resources, groups, affiliations, researchers, connected papers, and institution metrics;
- `ResearcherProfileData`: canonical researcher, resources, fields, ordered affiliation history, papers, coauthor collaborators, and researcher metrics;
- `ResearchGroupProfileData`: group, host institution, resources, fields, affiliations, members, and connected papers.

Institution and group paper aggregation checks that an affiliation includes the paper year. These projections are convenient query results, not new sources of truth. See [profile system](profile-system.md).

`ScientificAtlasRepository` extends the existing `AtlasRepository` with queries for raw records, resolution results, external resources, source snapshots, dataset updates, the graph projection, and all three profile read models. `StaticAtlasRepository` provides the in-memory implementation, while `APIRepository` validates FastAPI responses and loads map/profile data lazily from PostgreSQL-backed read models.

## Validation

Zod schemas verify structure, identifier format, science-domain field references, geographic-view references, institution locations, canonical external identifiers, temporal bounds, group-to-institution references, affiliation relationships, external-resource ownership, raw-record/snapshot references, identity-resolution invariants, update lineage, authorships, paper identifiers, event references, metric scope and period, implementation status, calculation timestamp, and structured provenance when the repository loads either dataset.

The dataset fails closed if required relationships are invalid. Presentation components only receive a validated `AtlasDataset`.

## Data-source policy

In the synthetic source, country names are geographic references and real institution names are used only as recognizable location examples. Synthetic researcher identities, groups, papers, events, relationships, and metric values remain explicitly marked. No synthetic value or ordering is a measurement, ranking, or claim about a real organization or person.

The pilot source contains real INSPIRE metadata and clearly labels its outputs `inspire-hep-pilot` and `unverified`. It preserves raw evidence, canonical-resolution decisions, resources, source/calculation provenance, and snapshot lineage, but that transparency does not make its tiny, selection-biased sample representative, perfectly resolved, or scientifically valid. No confidence or pilot value should be read as quality, performance, contribution share, or rank.

The institution fixture is a deliberately small, curated set of major map nodes for interaction testing. Inclusion is dataset presentation metadata, not a calculated threshold, ranking, or claim about institutional importance.
