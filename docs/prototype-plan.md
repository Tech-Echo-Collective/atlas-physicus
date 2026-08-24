# Alpha prototype plan

## Objective

Phase 2.3 makes the established scientific atlas easier to navigate, share, understand, and later connect to real data sources. It is a usability and data-foundation pass, not an entity or metric expansion.

The product path remains:

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

Paper and historical-event records remain preparation and connection layers rather than separate destinations.

## Phase 2.3 scope

Phase 2.3 includes:

- one compact map-native control stack: global reset, zoom in, and zoom out;
- explicit world/country/institution layer visibility, with country aggregates replaced by institution activity after entering a country;
- canonical routes for domain, field, country, institution, and researcher views;
- browser back/forward restoration and shareable query context for field, year, and group;
- query-oriented `AtlasRepository` methods implemented by `StaticAtlasRepository`;
- structured provenance normalized across entities and metric observations;
- a small entity search that navigates to existing atlas views;
- an optional guided path through Physics, `hep-th`, 2026, the United States, MIT, a synthetic researcher, and a connected demo event;
- optional DOI, arXiv, and generic external identifiers on paper preparation records;
- focused schema, repository, navigation, and geographic regression tests.

## Phase 2.3 exclusions

Phase 2.3 deliberately excludes:

- backend services, databases, or authentication;
- OpenAlex, arXiv, INSPIRE, Crossref, or institutional-site connections;
- real scientific ingestion, source reconciliation, or identity matching;
- paper pages, full-text search, citation graphs, or recommendations;
- ranking, prediction, evaluation, or admission prediction;
- final metric calculations and custom weighting.

## Acceptance criteria

A user can:

1. reset the atlas from any exploration depth using the control directly above zoom;
2. see only country activity in World View and only the selected country plus institution activity in Country View;
3. copy a canonical URL for a domain, field, country, institution, or researcher and restore the same hierarchy;
4. use browser back and forward navigation without losing dependent state;
5. search existing domains, fields, countries, institutions, and synthetic researchers;
6. opt into a guided demonstration without blocking normal exploration;
7. inspect the synthetic dataset's explicit source, type, version, and status;
8. continue using every Phase 2.2 country, institution, researcher, field, timeline, fullscreen, and global-reset capability.

Engineering acceptance requires successful type checking, unit tests, linting, and a production build.

## Known prototype limitations

- The repository boundary is query-oriented, but the static alpha still assembles a small in-memory snapshot at startup.
- Production hosting must provide a single-page-app fallback for direct `/atlas/*` requests.
- Search covers only existing entity labels and identifiers; it is not scientific or paper full-text search.
- Provenance records are synthetic examples and do not verify scientific claims.
- Paper identifiers are preparation metadata only and are not resolved externally.
- Historical metric values exist at four discrete demo years and are not scientifically reconstructed.
- The guided path uses fixed synthetic entities solely to explain the atlas hierarchy.
- Geographic-view membership remains a small validated fixture, not a comprehensive global registry.

Phase 2.3 should be reviewed as the final alpha foundation before choosing a narrow Phase 3 data-source feasibility study.
