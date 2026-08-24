# Alpha prototype plan

## Objective

v3.0.3-alpha turns the v3.0.2 bounded metric pilot into the first scientific knowledge-graph foundation. It introduces explicit source evidence, canonical identity, temporal affiliations, external resources, entity-aware search, profile aggregation, and non-destructive update lineage while retaining the existing Atlas frontend, `AtlasRepository`, Metric Engine, provenance, and visualization hierarchy.

The central processing order is:

```text
Scientific source
    → Preserved raw snapshot
    → Raw entity record
    → Identity resolution
    → Canonical entity and graph relationships
    → Profile enrichment
    → Metric Engine
    → AtlasRepository
    → Atlas visualization
```

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

Paper and historical-event records remain connection layers rather than new destinations.

## v3.0.3 scope

v3.0.3-alpha includes:

- the complete v3.0.2 metric pilot, numeric weighting profiles, source separation, and map hierarchy;
- immutable `RawEntityRecord`, auditable `IdentityResolution`, and canonical institution/researcher identity contracts;
- `matched`, `ambiguous`, and `unresolved` states with method, evidence, confidence, resolver version, timestamp, and provenance;
- identifier-first resolution, exact canonical/alias/historical-name matching, and an ambiguity-gated fuzzy fallback;
- canonical names, aliases, historical institution names, external identifiers, and identity confidence;
- time-dependent affiliations with start/end dates, source, confidence, and legacy-year compatibility;
- typed `ExternalResource` records for official websites, department/group pages, researcher homepages, ORCID, INSPIRE, arXiv, and DOI links;
- entity-aware canonical search across names, aliases, historical names, abbreviations, external identifiers, and spelling variations;
- search results with entity type, matched method/value, search confidence, and available identity confidence;
- read-only institution, researcher, and research-group profile projections over normalized graph relationships;
- `ScientificAtlasRepository` read methods plus interface-only `AtlasApiTransport` and `CanonicalEntityPersistence` seams;
- source-snapshot and dataset-update lineage in the validated domain model;
- an append-only pilot snapshot manifest, explicit incremental query planner, source-key merge into a new snapshot, and isolated versioned reprocessing;
- preparation boundaries for a future PostgreSQL store, FastAPI service, and `APIRepository` implementation;
- documentation of resolution, graph, profile, update, and uncertainty rules;
- focused schema, identity, search, profile, pipeline, metric, repository, and map-layer tests.

## v3.0.3 exclusions

v3.0.3-alpha deliberately excludes:

- a deployed PostgreSQL database, FastAPI backend, cloud service, scheduler, queue, authentication, or moderation system;
- browser-time scientific API access or automatic continuous ingestion;
- complete or representative INSPIRE coverage;
- automatic OpenAlex, Crossref, ROR, ORCID, institutional-site, or multi-source reconciliation;
- perfect researcher or institution matching, calibrated confidence, or a human resolution-review workflow;
- authoritative historical affiliation verification;
- website scraping as a primary source;
- new paper destinations, full-text search, citation-graph visualization, or recommendations;
- university rankings, researcher recommendations, prediction, evaluation, or admission prediction;
- validated scientific formulas, normalization, uncertainty propagation, or methodology;
- authoritative or optimized metric weights.

## Acceptance criteria

A user can:

1. continue exploring synthetic and INSPIRE pilot sources through the existing hierarchy;
2. search canonical institutions and researchers by supported canonical names, aliases, abbreviations, external identifiers, and reasonable spelling variants;
3. see match confidence and identity confidence as distinct technical signals where available;
4. navigate a selected search result to the existing canonical Atlas route;
5. continue exploring institution, group, researcher, paper, field, and metric connections without synthetic/pilot mixing;
6. inspect clear source, uncertainty, identity, and no-ranking communication.

The data system can:

1. keep raw source evidence separate from resolution decisions and canonical records;
2. reject invalid canonical references and silent unresolved merges at schema validation;
3. preserve concurrent and historical affiliations as dated edges;
4. aggregate institution, researcher, and group profiles without embedding copies in canonical entities;
5. plan an incremental refresh without modifying the base snapshot;
6. reprocess a preserved snapshot into an isolated version directory;
7. retain source, resolver, metric, and dataset version lineage.

Engineering acceptance requires successful type checking, unit and pipeline tests, linting, and a production build.

## Known prototype limitations

- The repository boundary is query-oriented, but the static alpha still validates and loads a local snapshot into memory.
- Canonical resolution is conservative but heuristic. Authority IDs and sources can be wrong, aliases can collide, and fuzzy matching can produce false positives or false negatives.
- Confidence values are not statistically calibrated and are not scientific metrics.
- An ambiguous or unresolved source record is intentionally kept outside canonical traversal; no review UI exists yet.
- Historical institution names, affiliation dates, group membership, resource links, coordinates, and paper coverage are incomplete.
- Profile paper and collaboration connections reflect only the selected dataset and source coverage.
- External resources can move or expire and are not continuously verified.
- The update planner and merge functions are development foundations; they do not poll sources, schedule jobs, promote snapshots automatically, or deploy infrastructure.
- The preserved pilot still contains only three records per year, and 2026 is year-to-date.
- The four pilot calculations remain sample-relative engineering signals, not scientific formulas or complete field measurements.
- Research Diversity, Talent Ecosystem, and Concentration / Vulnerability remain uncalculated for the pilot; real-data composite profiles remain disabled.
- Production hosting must provide a single-page-app fallback for direct `/atlas/*` requests.
- The selected metric and custom weights are session state and are not yet encoded in shareable URLs or persisted.
- Geographic-view membership remains a small validated fixture, not a comprehensive global registry.

Broader ingestion should proceed only after source policy, resolver behavior, ambiguity handling, historical affiliation rules, sampling bias, uncertainty communication, and scientific methodology have been reviewed. A visible unresolved entity is preferable to an unsupported canonical merge.
