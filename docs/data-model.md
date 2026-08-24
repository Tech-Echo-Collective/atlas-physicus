# Data model

## Design goals

The initial model supports the alpha interaction while keeping entity relationships explicit enough for later migration to a relational or graph database.

The JSON dataset is normalized: countries do not embed duplicated institution or researcher records. Relationships use stable identifiers.

## Core entities

### ResearchField

Represents a physics classification used to filter the atlas.

| Property | Meaning |
| --- | --- |
| `id` | Stable field identifier, initially based on arXiv-style categories |
| `label` | Human-readable field name |
| `description` | Short scope description |

Initial fields are `hep-th`, `gr-qc`, `quant-ph`, and `cond-mat`.

### Country

Represents the geographic level used by the Phase 1 choropleth.

| Property | Meaning |
| --- | --- |
| `id` | Internal stable identifier |
| `isoAlpha3` | ISO three-letter country code |
| `isoNumeric` | ISO numeric code used to join world geometry |
| `name` | Display name |
| `region` | Broad geographic region |

### Institution

Represents a research institution located in one country.

| Property | Meaning |
| --- | --- |
| `id` | Internal stable identifier |
| `name` | Display name |
| `countryId` | Reference to `Country` |
| `city` | Display location |
| `fieldIds` | References to represented research fields |

### Researcher

Represents a researcher for later institution-to-researcher exploration.

| Property | Meaning |
| --- | --- |
| `id` | Internal stable identifier |
| `name` | Display name |
| `institutionId` | Reference to `Institution` |
| `fieldIds` | References to research fields |

### MetricObservation

Stores a metric value separately from entity identity and presentation.

| Property | Meaning |
| --- | --- |
| `id` | Stable observation identifier |
| `entityType` | Type of entity being observed |
| `entityId` | Reference to the observed entity |
| `fieldId` | Research-field context |
| `metricId` | Metric identity |
| `period` | Observation year in the alpha |
| `value` | Provided metric value |
| `provenance` | Origin classification |

Phase 1 accepts only `research_activity_score` with `synthetic-demo` provenance. This constraint prevents demo values from being mistaken for implemented scientific metrics.

## Relationships

The conceptual model includes:

```text
Researcher ── belongs to ──> Institution
Institution ── located in ──> Country
Researcher ── writes ──> Paper
Paper ── belongs to ──> ResearchField
Paper ── cites ──> Paper
```

Paper, authorship, citation, temporal affiliation, and research-group records are deferred until they are needed by a real data pipeline. They remain part of the approved long-term model.

## Validation

Zod schemas verify structure, identifier format, field references, institution-to-country references, researcher-to-institution references, metric period, and demo provenance when the repository loads the dataset.

The dataset fails closed if required relationships are invalid. Presentation components only receive a validated `AtlasDataset`.

## Demo-data policy

Country names are geographic references. Institution names, researcher names, and activity values in the alpha dataset are synthetic. They must not be presented as measurements, rankings, or claims about real organizations and people.
