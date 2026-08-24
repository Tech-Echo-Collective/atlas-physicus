# Physics Atlas architecture

## Purpose

Physics Atlas is an interactive atlas of the global physics research ecosystem. Its primary interface is a map that lets users move from the world level through research fields, countries, institutions, and researchers.

Physics Atlas is a visualization and knowledge-exploration system. It is not a ranking system, prediction system, recommendation engine, or replacement for scientific literature services.

## Alpha architecture

The v3.0.3-alpha prototype remains a static client application and adds canonical identity, graph-profile, entity-search, and incremental-update foundations to the optional development-time pilot pipeline:

```text
Synthetic JSON dataset ───────────────────────────────┐
                                                     │
INSPIRE-HEP REST API                                 │
        ↓                                            │
bounded acquisition → preserved raw snapshot         │
        ↓                                            │
normalization → identity resolution                  │
        ↓                                            │
canonical entities + temporal graph relationships   │
        ↓                                            │
profile enrichment → pilot metrics                  │
        ↓                                            │
versioned local pilot export + update manifest ──────┤
                                                     ↓
                                          Zod runtime validation
                                                     ↓
                                          StaticAtlasRepository
        ↓
MetricRegistry + MetricCalculator / MetricEngine
        ↓
query-oriented AtlasRepository interface
        ↓
React application + URL navigation state
        ↓
MapLibre geographic layers, timeline, and entity exploration layers
```

Technology choices:

- React for component-based interface construction;
- TypeScript for explicit domain and component contracts;
- Vite for development and static production builds;
- MapLibre GL JS for open-source WebGL map rendering;
- Zod for validating data at the application boundary;
- Vitest for focused domain and repository tests.

The prototype uses local geographic data from the `world-atlas` package. It does not require a map API key or remote tile service. Historical observations and synthetic institution coordinates remain part of the validated fixture. The second repository reads a checked-in, versioned INSPIRE-HEP pilot export; the browser never contacts INSPIRE at runtime.

## Module boundaries

### Domain

`src/domain` contains the stable product vocabulary and validation rules. It does not depend on React, MapLibre, or a backend transport.

### Data access

`src/data` retains the base `AtlasRepository` interface and adds `ScientificAtlasRepository` as its knowledge-graph read-side extension. `StaticAtlasRepository` implements the extended contract: it validates local JSON once and exposes granular queries for domains, fields, countries, institutions, groups, researchers, papers, relationships, events, metrics, raw identity evidence, resolution results, external resources, source/update lineage, graph projection, and profiles. Separate repository instances provide the synthetic framework dataset and the INSPIRE-HEP pilot export. `loadAtlasDataset` assembles either snapshot through the same boundary; visualization components never depend on source-specific records.

`ScientificAtlasRepository.ts` also defines deliberately small `AtlasApiTransport` and `CanonicalEntityPersistence` boundaries. They prepare a future FastAPI client or PostgreSQL adapter without providing a network client, database implementation, or backend in this alpha.

Structured provenance is normalized at this boundary. Every validated entity and metric observation receives `source`, `sourceType`, `version`, `status`, and optional confidence/retrieval metadata. Metric observations also identify their source, algorithm version, and calculation version.

### Identity and graph

`src/identity` contains the conservative `CanonicalIdentityResolver`. It consumes immutable `RawEntityRecord` inputs, tries authoritative external identifiers before exact canonical/alias/historical names, gates fuzzy candidates by threshold and ambiguity margin, and returns an auditable `IdentityResolution`. The statuses `matched`, `ambiguous`, and `unresolved` remain explicit; only a matched result can reference a canonical institution or researcher.

Canonical institutions and researchers hold stable Atlas identifiers, preferred names, aliases, historical names where applicable, external identifiers, provenance, and identity confidence. URLs are isolated in typed `ExternalResource` records. `Affiliation` is a time-dependent edge with optional start/end dates, source, and confidence. See [entity resolution](entity-resolution.md) and the [scientific knowledge graph](knowledge-graph.md).

`src/knowledge/KnowledgeGraph.ts` exposes `KnowledgeGraphService`, which projects the validated dataset into typed canonical nodes and edges. Every edge must reference an existing node. Raw records and resolution decisions remain outside the node set; an `identityResolutionBoundary` reports the matched, ambiguous, and unresolved raw IDs without promoting unresolved evidence into the graph.

### Profiles and search

`src/profiles` assembles read-only institution, researcher, and research-group profiles from canonical entities, resources, affiliations, authorships, papers, fields, collaborators, and existing metric observations. `ProfileService` filters paper-to-institution or group connections through the affiliation valid for the paper year. `ScientificAtlasRepository` exposes the same projections for transport-neutral consumers. The service does not copy profile data into entity records or calculate metrics.

`src/search` builds an `EntitySearchIndex` over canonical entities. It recognizes canonical names, aliases, historical names, abbreviations, stable identifiers, and fuzzy spelling variants, then returns entity type, match method, matched value, search confidence, and available identity confidence. Search maps a query to an existing canonical entity; it never resolves source records or mutates identity data.

### Metrics

`src/metrics` contains the metric registry, calculator contract, engine orchestration, synthetic alpha calculators, and composite-weighting framework. The registry resolves definitions independently from observations. The engine invokes calculators and returns versioned observations through the repository boundary. React can request or combine supplied layers but cannot contain scientific calculation logic.

The custom-weighting module accepts nonnegative numeric weights that total exactly 100% and emits derived composite observations only after explicit user confirmation. It leaves every raw observation unchanged. Four named demonstration presets provide transparent starting points. Because the real pilot does not calculate Research Diversity, its five-metric composite is disabled rather than filled with synthetic data. A future validated calculator or API can replace the pilot or synthetic implementation while preserving the domain and repository contracts.

### Pilot pipeline

`pipeline` contains development-time acquisition, normalization, entity-resolution, update, metric, and export modules. Acquisition makes bounded, year-sharded INSPIRE queries and preserves the raw responses. Normalization produces the existing Physics Atlas entities and relationship records. Entity resolution produces canonical identities, temporal affiliations, external resources, and reports that distinguish matched, ambiguous, and unresolved evidence with method, confidence, and provenance. Metric calculation emits already-calculated country and institution observations. Export produces a standalone dataset accepted by the normal schema and repository boundary.

`pipeline/updates` creates an append-only snapshot manifest, plans an explicit overlapping incremental query, merges newer source revisions by authoritative source key into a new snapshot object, and never mutates the base snapshot. `pipeline/reprocess.mjs` rebuilds any preserved raw snapshot into its own `data/versions/<snapshot-id>/` directory. This is an update foundation, not a scheduler, production synchronizer, or cloud deployment.

The pipeline is not bundled as browser application logic and is not a backend. Its scope and uncertainty are documented in the [pilot study](pilot-study.md).

### Navigation

`src/navigation` owns canonical URL creation and restoration. It maps shareable domain/field paths and country, institution, or researcher paths into the existing normalized hierarchy. Browser history remains the navigation source of truth after startup; back and forward events restore all dependent entity selections. URL resolution uses normalized relationships and geographic-view membership rather than duplicating scientific data inside routes.

### Presentation

`src/components/atlas` contains the exploration interface. `AtlasExplorer` coordinates repository data, URL state, search, and the optional guided path. `WorldMap` owns MapLibre lifecycle and geographic navigation, `GeographicGeometryLayer` joins packaged GeoJSON features to configured views and composes a dedicated country-mode canvas, `GeographicEntityMapping` resolves geometry and location membership, and `InstitutionLayer` converts already-provided institution observations into points. Dedicated institution, researcher, and field layers resolve normalized entity relationships without embedding records inside UI state.

The map only converts a provided normalized prototype value into fixed color and point-size scales. Its GeoJSON contract uses the generic `metricValue` property. It does not interpret scientific quality, derive historical values, or create rankings.

Map information density follows the exploration hierarchy. World View enables only the global country choropleth. Country View disables every global country layer, renders only the configured country canvas with a neutral geographic fill, and enables the curated institution heat layer. Institution View retains that geographic context while the entity panel becomes the primary surface for groups, researchers, papers, and fields. `MapLayerHierarchy` defines and tests these layer transitions independently from MapLibre lifecycle code.

World-layer colors resolve through `GeographicView` membership rather than assuming a one-to-one relationship between a source polygon and a metric entity. The native geometry/location identifier is retained alongside the visualization metric identifier, keeping rendering decisions separate from scientific attribution.

Geographic geometry and scientific attribution are independent inputs. Map boundaries provide exploration context, while institution locations and future collaboration attribution follow institutional and affiliation metadata. The governing rules are documented in the [geographic representation policy](geography-policy.md).

## v3.0.3 interaction architecture

```text
ScienceDomain (Physics)
        ├── domain observations ────────────────┐
        └── optional ResearchField              │
                    └── field observations ─────┤
                                                ↓
MetricDefinition → MetricRegistry → MetricEngine
                         ↓
             versioned MetricObservation
                         ↓
              raw layer or user-defined composite
                         ↓
                  period and entity scope
                                                ↓
country observations → world heatmap
        ↓ country selection
institution observations + location → institution points
        ↓ institution selection
InstitutionView
        ↓ research-group affiliation
ResearcherProfile

ResearchField → HistoricalEvent + Institution + Researcher + Paper
Paper ← Authorship → Researcher ← temporal Affiliation → Institution / ResearchGroup

RawEntityRecord → IdentityResolution → canonical Institution / Researcher
Canonical entity → typed ExternalResource
Canonical graph relationships → ProfileService → entity profile

GeographicView → source geometry membership + institution-location membership

URL route ↔ AtlasNavigationState → existing hierarchy
Entity-aware search → canonical entity + match evidence → canonical route
Guided exploration → canonical state transitions (optional)
Entity / MetricDefinition / MetricObservation → DataProvenance
```

Time is represented by the existing `MetricObservation.period` field. This avoids introducing a parallel historical metric type and keeps the repository query boundary compatible with the Phase 1 model. Switching sources swaps repository instances and resets incompatible field or entity state; it does not create a second visualization system.

## Future architecture

The intended long-term system is:

```text
External scientific APIs
        ↓
incremental data acquisition
        ↓
raw snapshot storage
        ↓
normalization + canonical identity resolution
        ↓
PostgreSQL knowledge-graph storage
        ↓
Metric engine
        ↓
FastAPI service
        ↓
Frontend repository adapter
        ↓
Visualization interface
```

The v3.0.3-alpha engineering pilot exercises the identity and graph path through local export with INSPIRE-HEP metadata. It provides validated canonical graph records and query services in memory, but no production database, continuous ingestion, multi-source reconciliation, backend API, or validated methodology. Potential later sources include OpenAlex, arXiv, INSPIRE, Crossref, ROR, and ORCID under their applicable access and licensing terms.

The future `APIRepository` should implement the same application contract used by the static prototype. PostgreSQL can store canonical nodes, typed joins, temporal affiliation bounds, resource records, provenance, and version lineage; FastAPI can expose versioned lookup, search, profile, relationship, and metric endpoints. These are prepared boundaries, not alpha runtime dependencies. Their adoption should follow demonstrated query and operational requirements rather than precede them.

## Architectural constraints

- Scientific methodology remains outside presentation components.
- Data entering the frontend is validated at a boundary.
- Missing observations are distinct from zero-valued observations.
- World, country, and institution views expose only the geographic layers appropriate to their scale.
- Synthetic data and real-metadata pilot data are explicitly distinguished.
- Structured provenance travels with every entity and metric observation.
- Raw source records remain distinct from resolution decisions and canonical entities.
- Ambiguous and unresolved records cannot silently reference a canonical entity.
- Search operates on canonical entities and reports match confidence; it does not mutate resolution state.
- Temporal affiliation edges replace permanent researcher-to-institution ownership.
- External URLs remain typed resource records rather than canonical identity fields.
- A newer snapshot or derived build cannot destructively replace preserved raw evidence.
- Geographic rendering does not determine exclusive ownership of scientific activity.
- Domain and field observations are separate validated inputs; the frontend does not aggregate one into the other.
- Every metric layer is registered and every observation identifies its algorithm and calculation version.
- User composites preserve raw observations and are explicitly non-authoritative.
- Global reset clears geographic/entity state and restores the minimum world camera without leaving fullscreen.
- URL state contains identifiers and exploration context only; scientific records remain in the repository layer.
- Browser-time external access, PostgreSQL/FastAPI deployment, scheduling, authentication, representative ingestion, and multi-source reconciliation remain out of v3.0.3-alpha.
