# Metric Engine

## Status and purpose

Physics Atlas v3.0.5-alpha preserves the versioned Metric Engine and the
affected-partition recalculation boundary established in v3.0.4. The live
backend's default `NoFormulaMetricRecalculator` records required work and emits
no observations, preventing infrastructure completion from being mistaken for
scientific validation.

The post-v3.0.5 scientific-modeling work adds implemented v1 contracts,
metric-specific calculators and normalization, reconstructable observation
metadata, and an exact-five Joint Activation Gate. These are framework
completion, not validated live scores. The canonical algorithms are in the
[Metric System v1 specification](metrics-spec-v1.md), with the validation and
publication rules in [Metric System v1 validation](metric-validation.md).

The synthetic dataset remains demonstration data. The historical INSPIRE pilot uses real metadata but incomplete, selection-biased technical signals. Neither is a country, institution, group, or researcher ranking.

## Architecture

```text
MetricDefinition → MetricRegistry → MetricCalculator / Metric Engine
        ↓
versioned MetricObservation
        ↓
raw layer or explicitly confirmed user composite
        ↓
shared map spectrum

changed canonical records
        ↓
MetricRecomputationPlanner
        ↓
affected entity/field/country/institution/year/metric partitions
        ↓
jointly activated calculator (withheld) → new versioned observations
```

React and MapLibre select supplied observations but never derive scientific metrics. Provider connectors normalize metadata but never calculate metrics.

## Metric definition and taxonomy

Each `MetricDefinition` includes stable ID, name, category, description, interpretation, unit, definition version, required data, implementation status, and provenance.

The complete top-level vocabulary is:

| ID | Category | Interpretation | Alpha status |
| --- | --- | --- | --- |
| `research_activity_score` | Research Activity | Fractionally attributed observed output, not research quality | Implemented v1 framework; live withheld |
| `research_impact` | Research Impact | Field-, age-, and document-normalized citation attention, not scientific value | Implemented v1 framework; live withheld |
| `collaboration` | Collaboration / Connectivity | Entity-appropriate collaboration proportions and supported graph evidence | Implemented v1 framework; live withheld |
| `research_diversity` | Research Diversity | Normalized subfield-distribution evenness, not quality | Implemented v1 framework; live withheld |
| `momentum` | Research Momentum / Sustainability | Backward-looking field-relative evolution, not prediction | Implemented v1 framework; live withheld |
| `talent_ecosystem` | Talent Ecosystem | Researcher development, mobility, and early-career activity | Taxonomy only |
| `concentration_vulnerability` | Concentration / Vulnerability | Institutional/geographic concentration and dependency | Taxonomy only |

Taxonomy membership does not imply a formula, representative dataset, normalization method, or scientific endorsement. Talent Ecosystem and Concentration / Vulnerability are not part of the default composite.

## Metric observations and provenance

`MetricObservation` is separate from entity identity and visualization state. It includes entity type/ID, optional domain/field, metric ID, value, period, source, algorithm version, calculation version, and structured provenance. Real-data storage additionally supports dataset/source snapshot and calculation timestamps.

Supported entity types include science domains, research fields, countries, institutions, groups, and researchers. Missing is represented by no applicable observation, never by a fabricated zero. A source correction creates a new traceable calculation/dataset version rather than silently rewriting history.

## Repository and API flow

`MetricRegistry` resolves definitions independently from observations and distinguishes visualization-capable metrics from taxonomy-only entries. `MetricEngine` invokes registered calculators. Static synthetic and pilot repositories expose the same definition/observation contract as FastAPI's `/api/metrics` and paginated `/api/metric-observations` routes.

`APIRepository` validates those responses and scopes map queries by entity type, field/domain, metric, and year. Switching repositories replaces the complete metric source; synthetic and provider-backed observations cannot be silently mixed.

## Composite weighting

The approved composite remains:

```text
H = Σ wiMi
```

where `Mi` is a supplied observation and `wi` is a user-confirmed normalized percentage. Inputs must be numeric, nonnegative, and total exactly 100%. Invalid drafts do not change the confirmed map. The result is a user-defined exploration perspective, not an official ranking.

| Preset | Activity | Impact | Connectivity | Diversity | Momentum |
| --- | ---: | ---: | ---: | ---: | ---: |
| Balanced Scientific Ecosystem | 25% | 25% | 20% | 15% | 15% |
| Output & Influence Lens | 20% | 45% | 15% | 10% | 10% |
| Recent Evolution Lens | 20% | 20% | 20% | 20% | 20% |
| Global Network | 15% | 20% | 45% | 10% | 10% |

Composites create derived observations and never modify raw values or graph relationships. The INSPIRE pilot lacks Research Diversity, so its five-category composite remains disabled rather than filling the missing category with synthetic data.

## Historical pilot signals

The preserved bounded INSPIRE pilot supplies four simple sample-relative signals for entity-years with resolved participation:

| Metric | Pilot raw signal |
| --- | --- |
| Research Activity | sampled-paper participation count |
| Research Impact | `log1p` of fully attributed citation counts excluding self-citations where supplied |
| Collaboration / Connectivity | distinct co-participating entities |
| Research Momentum / Sustainability | relative change across adjacent three-year participation windows |

Each collaborative paper attributes participation to every resolved participating affiliation; it does not assign exclusive country ownership. Values are min-max scaled only within the sampled year/entity type. They are engineering pilot signals, not final formulas, contribution shares, or complete field measurements. See [pilot study](pilot-study.md).

## Incremental live recomputation

`MetricRecomputationPlanner` converts changed normalized records into a unique set of partitions containing entity, field, country, institution, period, and optional metric. The update run stores that set for audit and observability. This prevents the architecture from requiring a whole-Atlas rebuild whenever one paper changes.

A scientifically reviewed production recalculator must:

- read only the affected canonical data plus required comparison context;
- append observations with metric-definition, algorithm, calculation, dataset, and source versions;
- bind public reads to the published definition and current dataset lineage,
  selecting a latest calculation only when the partition has one unambiguous
  algorithm version;
- leave prior results reproducible;
- preserve missing values and uncertainty;
- report failures without advancing the source checkpoint as though calculation succeeded.

The production planning boundary remains intact while the five v1 algorithms
are implemented behind a withheld publication boundary. No provider metadata
is converted into a live score by an undocumented or unvalidated formula.

The v3.0.5 production evidence snapshot still emits no metric observations.
Activity, Impact, Connectivity, Diversity, and Momentum remain excluded from
live visualization and composite inputs until one active release manifest
passes the exact-five gate. Talent Ecosystem and Concentration/Vulnerability
remain taxonomy-only.

## Visualization contract

Raw and composite observations use the existing normalized `0–100` display contract where applicable. Synthetic values are demonstrative; pilot values are sample-relative. The shared spectrum is violet → blue → cyan → green → yellow → orange → red. Missing uses a dark neutral color separate from low.

Country fill, institution heat surface, institution core, halos, and both pulse rings use the same computed active metric color. Pulse timing, expansion, and opacity are fixed decorative behavior and encode no value, uncertainty, rank, or additional metric.

## Limitations and methodology gate

Provider-backed ingestion, PostgreSQL storage, and update scheduling do not make
the metrics scientifically validated. Representative coverage, data-bias
review, identity-error analysis, sampled affiliation and field-mapping review,
normalization robustness, uncertainty communication, and external scientific
review remain required before the complete system can be activated.
