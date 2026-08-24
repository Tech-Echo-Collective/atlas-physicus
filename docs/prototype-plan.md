# Alpha prototype plan

## Objective

Phase 2.2 extends the established geographic and temporal exploration model into a small research-community atlas. It connects where and when research activity appears with synthetic researchers, groups, papers, and historical context.

The product path is:

```text
Science domain
    → Optional research field
    → Time
    → World
    → Country
    → Institution
    → Research group
    → Researcher
```

Paper records remain a preparation layer rather than a separate destination.

## Phase 2.2 scope

Phase 2.2 includes:

- a continuous violet, blue, cyan, green, yellow, orange, and red activity scale;
- explicit Physics-domain and field-specific heatmap scopes;
- the existing country and institution geographic exploration;
- validated geographic-view membership for composite exploration canvases;
- a persistent global reset at country and institution depth;
- dedicated institution exploration with associated fields and synthetic activity history;
- research-group selection derived from normalized affiliations;
- researcher profiles with affiliation, fields, optional external links, paper connections, and event connections;
- field overviews with an introduction, demo milestones, representative institutions, researchers, and papers;
- normalized `ResearchGroup`, `Affiliation`, `Paper`, `Authorship`, and `HistoricalEvent` records;
- explicit non-ranking and incomplete-demo language throughout entity views;
- runtime relationship validation and focused automated tests.

## Phase 2.2 exclusions

Phase 2.2 deliberately excludes:

- backend services or databases;
- external scientific API integration;
- real researcher, group, paper, or event datasets;
- publication ingestion, citation graphs, and identity disambiguation;
- full paper pages;
- ranking, recommendation, evaluation, or admission prediction;
- final metric calculations and custom weighting;
- authentication and persistent user state.

## Acceptance criteria

A user can:

1. view overall Physics activity or select a field, then explore a year, country, and institution through the existing atlas path;
2. understand that the heat scale runs continuously from low violet to high red;
3. open a dedicated institution layer and see its associated fields and synthetic activity history;
4. move through an institution's research groups to affiliated researchers;
5. open a researcher profile and return clearly to the institution;
6. view optional external links and representative paper connections without ranking language;
7. open a field overview with synthetic milestones and connected entities;
8. understand that every research entity and historical record is incomplete synthetic demo content.
9. return from any map exploration depth to the minimum-zoom global atlas without leaving fullscreen.

Engineering acceptance requires successful type checking, unit tests, linting, and a production build.

## Known prototype limitations

- Historical metric values exist at four discrete years and are not scientifically reconstructed.
- Research groups, researchers, papers, authorships, and events are a deliberately small synthetic graph.
- Real institution names are location examples only; their surrounding entity records are fictional.
- Paper records have no dedicated page, citation network, identifier resolution, or source provenance beyond `synthetic-demo`.
- External links on synthetic profiles are interface examples rather than verified researcher metadata.
- Entity exploration is in-memory and URL state is not persistent or shareable.
- Geographic-view membership is a small manually maintained synthetic fixture, not a comprehensive boundary or location registry.
- Physics-domain activity values are explicit demo observations, not computed aggregates of field activity.

Phase 2.2 should be reviewed as an entity-navigation and normalization slice before any real metadata feasibility work begins.
