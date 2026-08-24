# Metric model

## Status

The Physics Atlas metric model has been defined conceptually but is not implemented in the alpha prototype. Phase 1 must not substitute an improvised scientific scoring system.

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

Phase 1 exposes one placeholder metric:

```text
research_activity_score
```

Its values are synthetic demo values on a fixed `0–100` display scale. They exist only to prove that selecting a field updates the map. The prototype neither derives these values from publications nor claims that they measure research quality, impact, capacity, or influence.

## Replacement boundary

`MetricObservation` separates values from entities, fields, periods, and provenance. `AtlasRepository` separates consumers from the current JSON transport.

A future metric engine can emit validated observations through an API-backed repository adapter. The map can then render supplied observations without owning the scientific calculation.

The UI is responsible for:

- selecting a field and period;
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
