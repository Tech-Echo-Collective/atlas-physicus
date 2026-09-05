# Metric model

## Status

The approved Physics Atlas metric families remain the long-term conceptual
model. The post-v3.0.5 scientific-modeling work implements the exact five
Metric System v1 algorithms behind a withheld Joint Activation Gate. Synthetic
transformations and historical pilot signals remain isolated for interface and
reproducibility tests; neither is scientific validation.

The final heatmap model is:

```text
H = Σ wiMi
```

where `Mi` represents a supplied metric observation and `wi` represents a normalized weight. The synthetic source demonstrates this equation with user-selected weights; it does not establish final metrics, normalization, or authoritative weights.

## Approved metric families

### Researcher

- Research Output
- Research Impact
- Research Network
- Research Breadth
- Research Evolution

### Field

- Field Activity
- Field Impact
- Field Growth
- Field Connectivity
- Field Stability/Vulnerability
- Historical Evolution

### Institution

- Research Activity
- Research Impact
- Research Diversity
- Research Network
- Historical Contribution

### Geographic

- Research Capacity
- Research Influence
- Global Connectivity
- Research Diversity

These long-term family names do not imply that every future family member has
a formula. Metric System v1 separately defines exactly five versioned methods,
with certified scientific inputs, preserved raw values, and a presentation-only
Atlas Scale. Future family members still require separate methodology work;
none is inferred by the frontend.

## Alpha metric layers

The synthetic v3.0.2-alpha source registers five visualization layers:

- `research_activity_score` — Research Activity;
- `research_impact` — Research Impact;
- `collaboration` — Collaboration / Connectivity;
- `research_diversity` — Research Diversity;
- `momentum` — Research Momentum / Sustainability.

The registry also reserves Talent Ecosystem and Concentration / Vulnerability as taxonomy-only definitions. They establish future vocabulary and carry no observations or calculation logic in this release.

All values use a fixed synthetic `0–100` display scale. The Research Activity fixtures are hand-authored demonstration values; the other layers are deterministic transformations created by the alpha calculator solely to exercise registry, versioning, selection, and weighting behavior. They are not derived from publications and do not measure research quality, impact, capacity, influence, collaboration, or growth.

The presentation maps supplied values through a continuous spectral scale: violet, blue, cyan, green, yellow, orange, and red. Countries, institution heat surfaces, node cores, pulse rings, and metric histories use the same low-to-high convention; node size also reflects the supplied value. Pulse timing and expansion are constant visual emphasis and encode no metric. The scale is a visualization standard, not a scientific threshold or ranking method. Missing observations remain visually separate from zero.

The active metric layer changes with map scale. World View applies the scale only to countries. Country View removes that choropleth, uses a neutral geographic canvas, and applies the scale only to institution nodes. This presentation change does not recalculate or transfer observations.

## Custom weighting

The user-defined composite profile applies `H = Σ wiMi` without modifying its raw observations. Weights:

- total exactly 100%;
- accept nonnegative direct numeric percentages;
- default to 25% Activity, 25% Impact, 20% Collaboration, 15% Research Diversity, and 15% Research Momentum;
- do not generate a composite until the user explicitly confirms a valid total.

The result is labelled as a user-defined synthetic composite. It is not an official ranking, an objective ordering, or scientific truth.

The interface provides four named exploration presets: Balanced Scientific
Ecosystem, Output & Influence Lens, Recent Evolution Lens, and Global Network.
Preset names describe user-selected emphasis only; they do not endorse a
methodology or produce authoritative scores. The real-metadata pilot has no
Diversity calculation, so the five-metric composite remains unavailable for
that source rather than mixing real and synthetic observations.

## INSPIRE-HEP pilot layers

The bounded pilot calculates four sample-relative signals for countries and institutions:

- `research_activity_score` — sampled-paper participation count;
- `research_impact` — `log(1 + x)`, where `x` is the entity-year sum of fully attributed citation counts without self-citations;
- `collaboration` — Collaboration / Connectivity, using a distinct co-participating entity count;
- `momentum` — Research Momentum / Sustainability, using relative participation change between adjacent three-year windows.

Each signal is independently min-max scaled among entities with sampled participation within one year and one entity type. An entity-year without sampled participation has no observation rather than a measured zero. The pilot produces no Research Diversity, Talent Ecosystem, or Concentration / Vulnerability observations. These simple calculations test acquisition-to-visualization plumbing; they do not instantiate the final approved metric families or support cross-year, cross-entity-type, or scientific-quality comparison. See the [pilot study](pilot-study.md) for source scope, algorithms, provenance, resolution results, and limitations.

## Replacement boundary

`MetricDefinition` documents a metric's stable ID, category, description, interpretation, unit, version, required data, implementation status, and provenance. `MetricObservation` separates a calculated value from entity, domain-or-field scope, period, source, algorithm version, calculation version, and provenance. `MetricRegistry`, `MetricCalculator`, and `MetricEngine` keep methodology outside React and MapLibre. `AtlasRepository` separates consumers from the current JSON transport.

The implemented v1 calculators can replace synthetic or pilot values only
after the complete system passes reviewed activation and a production
recalculator is explicitly configured. The map continues to render supplied
observations without owning the scientific calculation. See the
[canonical v1 specification](metrics-spec-v1.md), [evidence-certification
boundary](evidence-certification.md), and [Atlas Scale rules](normalization.md).

The UI is responsible for:

- selecting a science domain or field and period;
- selecting and requesting calculated observations;
- collecting a valid user-defined weight profile;
- distinguishing missing observations from zero;
- mapping supplied values to a documented visual scale;
- communicating provenance and limitations.

The UI is not responsible for:

- implementing scientific metric formulas;
- selecting, optimizing, or endorsing weights;
- normalizing scientific datasets;
- ranking entities;
- predicting future performance;
- recommending research directions or researchers.
