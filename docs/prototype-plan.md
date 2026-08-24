# Alpha prototype plan

## Objective

The first prototype demonstrates that a world-map exploration model can communicate the idea of a global physics research atlas to a professor and future contributors.

The product path is:

```text
World → Research field → Country → Institution → Researcher
```

## Phase 1 scope

Phase 1 includes:

- Physics Atlas identity and alpha status;
- interactive MapLibre world map;
- four research-field selections;
- local, schema-validated synthetic data;
- `research_activity_score` color updates;
- country selection and a basic information panel;
- explicit demo-data and non-ranking notices;
- responsive desktop and narrow-screen layouts;
- repository documentation and automated quality checks.

## Phase 1 exclusions

Phase 1 deliberately excludes:

- backend services;
- databases and knowledge-graph infrastructure;
- external scientific API integration;
- data cleaning and entity matching;
- final metric calculations;
- custom weighting controls;
- AI prediction or researcher recommendation;
- paper and citation exploration;
- authentication and persistent user state.

## Acceptance criteria

A user can:

1. open the website and recognize Physics Atlas;
2. see an interactive world map;
3. select `hep-th`, `gr-qc`, `quant-ph`, or `cond-mat`;
4. observe the map colors update from local demo observations;
5. click a highlighted country;
6. read its name, region, placeholder score, period, and demo entity counts;
7. understand that all displayed values are synthetic and are not rankings.

Engineering acceptance requires successful type checking, unit tests, linting, and a production build.

## Next validated slice

After Phase 1 is reviewed, the smallest sensible extension is deeper local-data navigation from country to institution and researcher. External data acquisition should begin only as a narrow feasibility study—one field, one period, and one source—after the interaction model is accepted.
