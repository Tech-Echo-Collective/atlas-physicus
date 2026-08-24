# Data model

## Design goals

The initial model supports the alpha interaction while keeping entity relationships explicit enough for later migration to a relational or graph database.

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

Phase 2.3 contains only `Physics`. The array structure supports future domains, but no non-physics data is included.

### ResearchField

Represents a physics classification used to filter the atlas.

| Property | Meaning |
| --- | --- |
| `id` | Stable field identifier, initially based on arXiv-style categories |
| `label` | Human-readable field name |
| `description` | Short scope description |

Initial fields are `hep-th`, `gr-qc`, `quant-ph`, and `cond-mat`.

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
| `name` | Display name |
| `countryId` | Reference to `Country` |
| `city` | Display location |
| `fieldIds` | References to represented research fields |
| `location` | Optional longitude and latitude used by the map |

### Researcher

Represents a research person independently from affiliation records.

| Property | Meaning |
| --- | --- |
| `id` | Internal stable identifier |
| `name` | Display name |
| `fieldIds` | References to research fields |
| `externalLinks` | Optional validated homepage, personal site, arXiv, or GitHub references |

The optional legacy `institutionId` remains schema-compatible with Phase 2.1 data, but Phase 2.3 fixtures use normalized `Affiliation` records instead.

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
| `startYear`, `endYear` | Optional temporal bounds |
| `provenance` | Origin classification |

Affiliations are separate records so future metadata can represent multiple institutions and time ranges without duplicating researchers.

### Paper and Authorship

`Paper` is a normalized preparation record with a title, summary, year, fields, and provenance. Optional `doi`, `arxivId`, and generic `externalIdentifiers` prepare identifier matching without implementing paper pages, ingestion, citations, or recommendations. `Authorship` is a join record that connects one paper to one researcher and preserves author position.

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

Phase 2.3 normalizes the fixture's `synthetic-demo` shorthand into an explicit object with version `v2.3-alpha`. This is source transparency, not a scientific-quality score.

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
| `provenance` | Structured source metadata |

Each observation must identify either a science domain or a research field. Phase 2.3 still accepts only `research_activity_score` with structured `synthetic-demo` provenance. The Physics-domain fixtures are explicit visualization inputs rather than values calculated by summing the four fields. Multiple observations may share an entity and scope while carrying different year values in `period`. This constraint prevents demo values from being mistaken for implemented scientific metrics.

## Relationships

The conceptual model includes:

```text
Researcher <── Affiliation ──> Institution
                         └──> ResearchGroup
Institution ── located in ──> Country
GeographicView ── renders ──> Geometry / institution-location membership
Researcher <── Authorship ──> Paper
Paper ── belongs to ──> ResearchField
HistoricalEvent ── connects ──> ResearchField / Researcher / Institution
```

Phase 2.3 implements these relationships only as synthetic preparation records. Citation edges, researcher identity matching, affiliation disambiguation, and complete publication metadata remain deferred.

Country aggregation must be derived from affiliation relationships rather than by assigning a paper to one country. Geographic rendering remains separate from this attribution model, as defined by the [geographic representation policy](geography-policy.md).

## Validation

Zod schemas verify structure, identifier format, science-domain field references, geographic-view references, institution locations, field references, group-to-institution references, affiliation relationships, authorships, paper identifiers, event references, metric scope and period, and structured provenance when the repository loads the dataset.

The dataset fails closed if required relationships are invalid. Presentation components only receive a validated `AtlasDataset`.

## Demo-data policy

Country names are geographic references. Phase 2.3 also uses MIT, Caltech, and Princeton as recognizable institution-location examples. All researcher identities, group names, paper records, historical events, relationships, and activity values are synthetic. No displayed value or ordering is a measurement, ranking, or claim about any real organization or person.

The institution fixture is a deliberately small, curated set of major map nodes for interaction testing. Inclusion is dataset presentation metadata, not a calculated threshold, ranking, or claim about institutional importance.
