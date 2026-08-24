# Metric Engine

## Status and purpose

Physics Atlas v3.0.2-alpha retains the formal Metric Engine boundary and tests it with both the synthetic framework dataset and a bounded INSPIRE-HEP metadata pilot. The engine is an extensible, versioned framework for supplying observations to the atlas; it is not a claim that the included metric definitions or calculations are scientifically validated.

The synthetic source remains demonstration data. The pilot pipeline ingests 81 selected INSPIRE-HEP records, but its values are incomplete, selection-biased technical outputs. Neither source ranks countries, institutions, groups, or researchers.

## Architecture

```text
Scientific entity
        ↓
MetricDefinition
        ↓
MetricRegistry
        ↓
MetricCalculator / MetricEngine
        ↓
versioned MetricObservation
        ↓
raw layer or user weight configuration
        ↓
composite MetricObservation
        ↓
shared spectral visualization
```

Presentation components never derive scientific metrics. They select already-calculated observations, choose an entity/domain/field/period scope, and pass values to the map.

## MetricDefinition

A `MetricDefinition` is a discoverable description of a metric:

| Property | Meaning |
| --- | --- |
| `id` | Stable metric identifier |
| `name` | Human-readable label |
| `category` | Registry grouping |
| `description` | Intended interpretation and limitation |
| `interpretation` | Plain-language guidance for reading the category |
| `unit` | Display unit |
| `version` | Definition version |
| `requiredData` | Inputs expected by a future validated calculator |
| `implementationStatus` | Synthetic visualization layer, pilot-calculated signal, or taxonomy-only definition |
| `provenance` | Source and status of the definition |

## Complete metric taxonomy

The registry establishes seven top-level categories as the long-term Metric Engine vocabulary:

| ID | Category | Interpretation | Alpha status |
| --- | --- | --- | --- |
| `research_activity_score` | Research Activity | Intensity and continuity of research activity within a selected scope, not research quality | Synthetic layer; pilot calculated |
| `research_impact` | Research Impact | Future exploration of how research is received or used, not an institutional-quality ranking | Synthetic layer; pilot calculated |
| `collaboration` | Collaboration | Future exploration of scientific relationships across researchers and institutions | Synthetic layer; pilot calculated |
| `research_diversity` | Research Diversity | Future exploration of subfield diversity, topic diversity, and research breadth | Synthetic layer; pilot taxonomy only |
| `momentum` | Research Momentum | Future exploration of change over time, not prediction | Synthetic layer; pilot calculated |
| `talent_ecosystem` | Talent Ecosystem | Future exploration of researcher growth, career mobility, and early-career activity | Taxonomy only |
| `concentration_vulnerability` | Concentration / Vulnerability | Future exploration of institutional or geographic concentration and ecosystem dependency | Taxonomy only |

Taxonomy membership does not imply an implemented formula, representative dataset, validated normalization method, or scientific endorsement. Talent Ecosystem and Concentration / Vulnerability deliberately have no calculator or observations in v3.0.2-alpha. Research Diversity also remains taxonomy-only in the real-data pilot.

Research Activity comes from the original hand-authored fixture. Research Impact, Collaboration / Connectivity, Research Diversity, and Research Momentum / Sustainability are deterministic synthetic transformations used only to demonstrate calculation, selection, versioning, and weighting. They are not final metrics.

## MetricObservation

`MetricObservation` separates a calculated value from entity records and visualization state. It includes entity type and identifier, optional science-domain or field scope, metric identifier, value, period, source, algorithm version, calculation version, and structured provenance.

Supported entity types include science domains, research fields, countries, institutions, research groups, and researchers. Both current sources supply map observations only for countries and institutions; the wider entity type supports later calculators without changing the model. Every pilot observation additionally supplies a calculation timestamp.

## Registry and calculation flow

`MetricRegistry` lists the complete taxonomy, resolves a definition by ID, filters definitions by category, and separates visualization-capable definitions from taxonomy-only definitions. `MetricEngine` associates calculated visualization definitions with a `MetricCalculator` and returns observations without exposing calculation logic to React or MapLibre.

`StaticAtlasRepository` validates a local dataset, constructs the registry, validates calculated observations, and exposes query methods. The synthetic repository runs its deterministic demonstration calculators. The pilot repository receives already-calculated, versioned observations from the development pipeline. A future `APIRepository` can return the same definitions and observations from a service without changing visualization components.

## Weighting framework

The custom profile implements the approved composite structure:

```text
H = Σ wiMi
```

where `Mi` is a supplied raw metric observation and `wi` is a user-selected normalized weight. Weights use direct numeric percentage entry, must be nonnegative, and must total exactly 100%. Editing one value does not silently change another. The interface reports invalid values or totals and only generates a composite after the user explicitly confirms a valid profile.

The four demonstration presets are:

| Preset | Activity | Impact | Collaboration | Diversity | Momentum |
| --- | ---: | ---: | ---: | ---: | ---: |
| Balanced | 25% | 25% | 20% | 15% | 15% |
| Research Excellence | 20% | 45% | 15% | 10% | 10% |
| Frontier Growth | 20% | 20% | 20% | 20% | 20% |
| Global Network | 15% | 20% | 45% | 10% | 10% |

Composite calculation creates new derived observations and never modifies raw observations or `MetricDefinition` records. The result is labelled as a user-defined synthetic composite profile. It is not an official ranking, an objective statement of superiority, or a scientifically privileged set of weights.

The presets require all five synthetic visualization metrics. The INSPIRE-HEP pilot does not calculate Research Diversity, so custom composite generation is disabled for that source rather than inserting a synthetic value into a real-metadata view.

## INSPIRE-HEP pilot calculations

The bounded pilot emits four observations for an entity-year only when that country or institution has resolved sampled-paper participation. It produces 1,060 observations across 107 country-years and 158 institution-years. Each value is min-max scaled among active entities within its year and entity type after calculating one of these raw signals:

| Metric | Pilot raw signal | Algorithm version |
| --- | --- | --- |
| Research Activity | Sampled-paper participation count | `pilot-activity-full-participation-minmax-v1` |
| Research Impact | `log1p` of the entity-year sum of fully attributed citations without self-citations | `pilot-impact-log-citations-minmax-v1` |
| Collaboration / Connectivity | Distinct co-participating entity count | `pilot-connectivity-unique-partners-minmax-v1` |
| Research Momentum / Sustainability | Relative change between adjacent three-year participation windows | `pilot-momentum-rolling-participation-minmax-v1` |

Every collaborative paper fully attributes participation to each resolved institution and country. Missing sampled participation remains missing rather than being encoded as a measured zero. These are deliberately simple pilot calculations used to test the framework; they are not final formulas and do not evaluate quality, contribution share, importance, or future performance. Exact scope, formulas, source citations, resolution results, and uncertainty are recorded in the [pilot-study documentation](pilot-study.md).

## Visualization contract

Raw and composite observations use one normalized `0–100` display range. For synthetic layers this is a demonstration range; for pilot layers it is a within-year, within-entity-type sample-relative index. Country fills, institution heat surfaces, institution cores, halos, and pulse rings share the violet → blue → cyan → green → yellow → orange → red language. Institution pulse speed, expansion, and opacity are constant and carry no metric information.

Missing data remains separate from a zero-valued observation. Map layers consume the generic `metricValue` feature property rather than a metric-specific score field.

## Reproducibility and future integration

Every observation records `source`, `algorithmVersion`, `calculationVersion`, `period`, and structured provenance. These fields provide an explicit replacement boundary for future methodology work; they do not by themselves establish validity.

The v3.0.2 pilot preserves its raw INSPIRE snapshot and reports identity resolution, metric output counts, source versions, algorithms, and calculation time. `npm run pipeline:rebuild` reconstructs derived artifacts from that snapshot; `npm run pipeline:ingest` deliberately creates a new, potentially different source snapshot.

Representative real-data integration still requires broader acquisition, source-policy review, multi-source entity resolution, historical-affiliation handling, uncertainty methods, scientific review, and versioned methodology. A validated calculator can be registered behind the current interface, or an API can supply compatible outputs. The current browser remains a static client and makes no runtime scientific-API request.
