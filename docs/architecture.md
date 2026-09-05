# Atlas Physica architecture

## Purpose

Atlas Physica is an open-source scientific exploration system for visualizing the structure and evolution of physics research ecosystems. Atlas Physica is developed and maintained by Tech Echo Collective. Its map-first path remains:

```text
Physics domain → research field → year → world → country
    → institution → group → researcher / papers
```

It is not a university or researcher ranking system, prediction system, recommendation engine, or replacement for scholarly databases.

## v3.0.5-alpha architecture

v3.0.5 preserves the continuously updateable v3.0.4 platform and adds
scientific-validation and presentation gates without changing the deployed
topology:

```text
Official scientific APIs
        ↓
source connectors + checkpoints
        ↓
raw snapshots and records
        ↓
normalization + field mapping
        ↓
canonical identity resolution
        ↓
paper-time fractional attribution
        ↓
PostgreSQL canonical graph + immutable source lineage
        ↓
scientific evidence certification
        ↓
certified exact metric-eligible populations
        ↓
raw metrics → metric-specific normalization → 0–100 Atlas Scale
        ↓
exact-five Joint Activation Gate
        ↓
FastAPI read service
        ↓
APIRepository
        ↓
React + MapLibre Atlas
```

External-resource enrichment and bounded health monitoring run alongside the canonical graph and feed profile read models. See [live data architecture](live-data-architecture.md), [database](database.md), and [backend](backend.md).

Technology choices:

- React, TypeScript, Vite, MapLibre GL JS, and Zod for the frontend;
- PostgreSQL, SQLAlchemy, Alembic, FastAPI, and Pydantic for persistence and transport;
- a cron-compatible Python worker for incremental ingestion and resource checks;
- Vitest for frontend/domain tests and pytest with deterministic fixtures for backend/pipeline tests;
- Docker Compose for PostgreSQL, migration, API, and worker development.

The public GitHub Pages application uses the operated Railway API on normal
routes. The repository retains synthetic and historical pilot datasets only for
explicit fallback, testing, and reproducibility and contains no production
credentials.

## Data modes and isolation

| Mode | Runtime boundary |
| --- | --- |
| Synthetic demo | Validated, hand-authored local JSON; visualization/framework demonstration only |
| INSPIRE pilot | Preserved bounded INSPIRE snapshot and versioned derived export; real but incomplete metadata |
| Live API fixture | FastAPI/PostgreSQL using deterministic connector fixtures; integration and operational testing |
| Provider-backed live | FastAPI/PostgreSQL/worker using official APIs; truly live only when separately hosted and operated |

A data-source switch replaces the complete repository boundary. Observations and entities from two sources are never silently combined. The selected domain, field, year, and entity chain is preserved only where the destination contains compatible identifiers; incompatible descendants are cleared together with a consistent URL update.

## Module boundaries

### Domain and validation

`src/domain` defines the stable frontend vocabulary, Zod schemas, provenance, identity, temporal relationships, metrics, dataset metadata, and source kinds. It has no React, MapLibre, SQL, or provider dependencies.

Backend Pydantic schemas provide an explicitly transport-oriented contract. SQLAlchemy records are not returned directly, and the browser validates API responses again before using them.

### Repository and transport

`AtlasRepository` and `ScientificAtlasRepository` remain the application-facing query contracts. `StaticAtlasRepository` supplies synthetic and pilot data. `APIRepository` supplies server data through the same conceptual boundary, including cancellation, stale-response protection, pagination, caching, loading/error behavior, and deterministic dataset replacement.

Large collections are scoped. Global map requests need countries and country observations; country requests need the selected canvas, major institutions, and institution observations; papers, researchers, relationships, resources, and profiles are entity-scoped and paginated. The bounded `/api/knowledge-graph` route is diagnostic, not a browser bootstrap payload.

### Persistent storage

PostgreSQL stores canonical entities and typed relationships plus raw evidence, identity decisions, review items, resources, check history, metric observations, and update metadata. Important relationships and query dimensions remain relational; variable provider payloads and structured provenance use JSON/JSONB.

`Affiliation` is a dated profile relationship between researcher, institution,
and optional group. `PaperAffiliation` separately stores exact, versioned,
resolved or withheld publication-time shares, so a current profile cannot
rewrite historical attribution. No permanent researcher-to-institution field
is introduced. URLs remain `ExternalResource` records. Alembic migrations own
schema evolution; application startup does not silently create production
tables.

### Connectors and updates

`backend/src/physics_atlas_api/connectors` implements one common `SourceConnector` boundary. The current `hep-th-v1` acquisition scope filters INSPIRE to Theory-HEP and arXiv to `cat:hep-th`; ROR refreshes only explicitly configured known IDs and is skipped with no targets. Cursor scope/version keys prevent broader or changed provider queries from reusing an incompatible checkpoint. ORCID and Crossref intentionally support only targeted `fetch_record` enrichment for an already-known ORCID iD or DOI; they are not global polling sources. Connector code fetches and normalizes source syntax but does not resolve identities or calculate scientific metrics. Raw provider categories are preserved separately from the uncertainty-bearing Atlas field mapping.

The update engine processes a bounded batch from the last successful cursor, writes an immutable snapshot, resolves changed entities, updates the canonical graph, plans affected metric partitions, and records a new dataset version. Scheduled connectors hold a closed acquisition window while paging and persist page checkpoints; the high-water cursor advances only after the final page succeeds. Repeated content is idempotent, and ambiguous identity evidence enters a persistent review queue. See [data sources](data-sources.md) and the [update engine](update-engine.md).

### Identity and knowledge graph

The canonical resolver is identifier-led and ambiguity-gated:

```text
authority ID → canonical/alias/historical name → contextual evidence
    → gated fuzzy candidate → matched / needs_review / unresolved
```

Authority IDs include ROR for institutions, ORCID/INSPIRE for researchers, and DOI/arXiv/INSPIRE for papers. Search confidence remains distinct from resolution confidence. Raw/unresolved records never become canonical search or profile results.

Canonical nodes include domains, fields, countries, institutions, groups, researchers, papers, and resources. Authorship, temporal affiliation, paper-field classification, citations, location, and hosting remain normalized edges. PostgreSQL is used as a relational graph store; a separate graph database is not justified by current queries.

### Profiles, search, and resources

Profile services assemble institution, researcher, and group read models from canonical entities, time-scoped relationships, papers, fields, metrics, and external resources. FastAPI exposes equivalent scoped profile routes. Entity-aware search queries canonical names, aliases, historical names, abbreviations, and authority identifiers, returns matching evidence, and excludes unresolved raw records.

The resource monitor validates public HTTP(S) targets, uses bounded `HEAD`/minimal `GET`, retry/backoff, timeouts, and check caching, and records status history. It does not crawl sites or delete a resource after a temporary failure. See [resource enrichment](resource-enrichment.md).

### Metric Engine

`MetricRegistry`, calculator contracts, versioned `MetricObservation`, and
confirmed composite weighting remain the product boundary. Presentation code
never invents formulas. Provider updates create affected partition plans across
entity, field, country, institution, year, and metric; the production
`NoFormulaMetricRecalculator` intentionally writes no new scientific values
until the implemented exact-five framework passes scientific review and an
explicit release manifest authorizes publication.

The post-v3.0.5 foundation implements paper-time fractional Activity,
MNCS-based Impact, collaboration proportions, Shannon-evenness Diversity, and
field-relative rolling-window Momentum with metric-specific normalization and
reconstructable certification and normalization proofs. Metric calculators
reject raw provider presence and uncertified partitions. Experimental and
taxonomy-only definitions cannot
enter live API map requests, layers, or composites. A `MetricSystemRelease`
must publish all five exact compatible algorithms together. The current live
evidence fails that gate, so no layer is enabled.

Existing synthetic calculations and bounded pilot signals remain reproducible and source-separated. Missing observations remain missing, not zero. Every calculated value retains definition, algorithm, dataset, and calculation versions. See the [Metric Engine](metric-engine.md).

Large immutable provider pages and replay bundles belong behind verified
warm/cold artifact references; PostgreSQL remains the hot canonical/queryable
state. Full Physics loading requires both the reviewed scientific gate and the
independent storage-budget gate. See [evidence certification](evidence-certification.md)
and [storage architecture](storage-architecture.md).

### Presentation and navigation

`AtlasExplorer` coordinates repository choice and canonical URL state. `WorldMap` owns MapLibre lifecycle; geographic and institution layers consume already-prepared geometry and observations. The layer hierarchy remains:

- World: country heatmap only;
- Country: selected geographic canvas plus major institution heat/nodes;
- Institution: selected country context plus group, researcher, paper, field, metric, and resource details;
- Researcher: identity, affiliation history, papers, collaborators, metrics, and resources.

The global reset clears selected country/institution/researcher state and restores the minimum world camera. Browser back/forward restores the same hierarchy.

## Geographic geometry and attribution

Map geometry is exploration context; institution metadata and temporal affiliations determine scientific location/attribution. `GeographicView` can group multiple geometry components and location-country memberships without embedding geopolitical rules in research relationships.

Country geometry processing supports polygon/multipolygon components, islands, exclaves, and antimeridian crossings. Rings are unwrapped and split into local components before rendering and camera bounds are calculated from that local canvas. This prevents Russia's far-east geometry from drawing across the map, retains disconnected Kaliningrad, and uses the same general abstraction as the China/Taiwan view. It does not create fake polygons or alter contribution logic. See the [geography policy](geography-policy.md).

## Time, color, and missing data

The timeline presents a continuous interaction over discrete historical observations. The selected year appears above the track; sparse major labels adapt to width; pointer, touch, click, and keyboard input are supported. A year without data is missing. The UI performs no scientific interpolation unless a future method is explicitly defined and labeled.

The active heat scale remains violet → blue → cyan → green → yellow → orange → red. Missing values use a dark neutral treatment distinct from low activity. Institution cores and both decorative pulse rings inherit the same computed color; pulse timing and size are constant and encode no metric.

## Deployment and operational boundaries

`docker-compose.yml` starts PostgreSQL, migrates the schema, and runs the API and worker. `/api/health` reports service/database status. `/api/updates/status` reports source freshness/failure, unresolved review count, resource failures, and metric-recalculation state. Structured logs record HTTP and worker/update events without introducing a large monitoring platform.

Provider-backed production requires separately supplied HTTPS hosting, credentials where required, provider-policy configuration, CORS, backups, database isolation, rate protection, and operator monitoring. GitHub Pages cannot host FastAPI/PostgreSQL; it only hosts the frontend and static fallback.

## Architectural constraints

- Scientific methods remain outside presentation and provider connectors.
- Geographic rendering and scientific attribution remain separate.
- Raw source records, resolution decisions, and canonical entities remain distinct.
- Ambiguous evidence is reviewable and never silently merged.
- Temporal affiliations replace permanent ownership fields.
- External URLs remain typed, monitored resources rather than scraped truth.
- Source, identity, dataset, and metric provenance remain inspectable.
- A source update cannot silently erase raw evidence or historical metric versions.
- Synthetic, pilot, fixture-live, and provider-live modes remain explicitly labeled and isolated.
- The browser does not contact providers, load the entire graph, or calculate all metrics on request.
- No source or composite is presented as an authoritative scientific ranking.

## Current limitations

The source connectors and scheduler are not a complete all-physics corpus, the
identity confidence model is not calibrated against a representative reviewed
truth set, and the implemented v1 formulas have not passed representative
scientific validation or the Joint Activation Gate. The operated Railway
backend exists, but the repository does not supply a public adjudication UI or
automated backup service. Provider freshness, coverage, recovery, and metric
readiness must therefore be reported from current operating evidence, never
inferred from the existence of code.
