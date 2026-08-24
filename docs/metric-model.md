# Metric model

## Status

The Physics Atlas metric model has been defined conceptually but is not implemented in the alpha prototype. Phase 2.2 does not substitute an improvised scientific scoring system.

The final heatmap model is:

```text
H = Σ wiMi
```

where `Mi` represents a metric and `wi` represents its normalized weight. Custom weighting is a future feature.

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

Definitions, normalization methods, provenance rules, uncertainty treatment, and weights for these metrics require separate scientific methodology work. They are not inferred by the frontend.

## Alpha placeholder

Phase 2.2 continues to expose exactly one placeholder metric:

```text
research_activity_score
```

Its values are synthetic demo values on a fixed `0–100` display scale. They exist only to prove that selecting the Physics domain or a field and year updates country colors and institution points. Domain-level and field-level observations are separate hand-authored fixtures; the frontend does not calculate Physics activity by adding or averaging field values. Historical values are interface demonstrations, not reconstructed scientific history. The prototype neither derives these values from publications nor claims that they measure research quality, impact, capacity, or influence.

The Phase 2.2 presentation maps supplied values through a continuous reversed spectral scale: violet, blue, cyan, green, yellow, orange, and red. Countries, institution nodes, and the institution activity history use the same low-to-high convention; node size also reflects the supplied value. This is a visualization standard, not a new metric, scientific threshold, or ranking method. Missing observations remain visually separate from a value of zero.

## Replacement boundary

`MetricObservation` separates values from entities, domain-or-field scope, periods, and provenance. `AtlasRepository` separates consumers from the current JSON transport.

A future metric engine can emit validated observations through an API-backed repository adapter. The map can then render supplied observations without owning the scientific calculation.

The UI is responsible for:

- selecting a science domain or field and period;
- requesting observations;
- distinguishing missing observations from zero;
- mapping supplied values to a documented visual scale;
- communicating provenance and limitations.

The UI is not responsible for:

- calculating the final heatmap equation;
- selecting or optimizing weights;
- normalizing scientific datasets;
- ranking entities;
- predicting future performance;
- recommending research directions or researchers.
