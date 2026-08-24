# Physics Atlas

Physics Atlas is an open-source project by [Tech Echo Collective](https://github.com/Tech-Echo-Collective) for exploring the structure and evolution of the global physics research ecosystem through an interactive map.

The project is a visualization and knowledge-exploration platform. It is not a scientific ranking system, a prediction engine, a researcher recommendation service, or a replacement for arXiv and Google Scholar.

## Alpha prototype

Physics Atlas is currently an early alpha prototype. v3.0.3-alpha adds a scientific knowledge-graph foundation to the bounded INSPIRE-HEP pilot while preserving the formal Metric Engine and repository boundaries:

```text
Science domain → Optional research field → Time → World → Country → Institution → Research group → Researcher
```

The current development state provides:

- a dark, interactive MapLibre scientific atlas with a full violet-to-red spectral metric scale;
- scale-aware map layers: World View shows only country metric values, while Country View replaces them with a neutral country canvas and institution metric nodes;
- an overall Physics domain heatmap and field-specific heatmaps, designed for later domain expansion;
- a data-source selector between the synthetic framework dataset and a versioned local INSPIRE-HEP pilot export;
- a first-class `raw entity → resolved identity → canonical entity` contract for institutions and researchers;
- identifier-led, confidence-bearing resolution that keeps matched, ambiguous, and unresolved source records distinct;
- canonical names, aliases, historical institution names, external identifiers, and auditable resolution evidence;
- time-dependent affiliation relationships with source and confidence instead of permanent researcher-to-institution ownership;
- typed external resources stored separately from canonical entities;
- read-only institution, researcher, and research-group profile aggregation over normalized graph relationships;
- field selection for `hep-th`, `gr-qc`, `quant-ph`, and `cond-mat` in the synthetic dataset, with the pilot deliberately limited to `hep-th`;
- a historical timeline with synthetic observations for 1900, 1950, 2000, and 2026;
- five selectable synthetic demonstration layers: Research Activity, Research Impact, Collaboration / Connectivity, Research Diversity, and Research Momentum / Sustainability;
- a seven-category long-term taxonomy that also reserves Talent Ecosystem and Concentration/Vulnerability without calculating them;
- a versioned metric registry, calculation interface, and query-oriented observation repository;
- direct numeric composite-weight entry, exact 100% validation, explicit confirmation, and four named demonstration presets;
- world-to-country camera transitions and metric-scaled institution nodes;
- configurable geographic-view membership, keeping rendered geometry separate from institution and affiliation metadata;
- a compact map-native global reset above the zoom controls;
- URL-addressable domain, field, country, institution, and researcher views with browser back/forward restoration;
- entity-aware search across canonical names, aliases, historical names, abbreviations, external identifiers, and spelling variations, with visible match confidence;
- an optional seven-step guided exploration path for first-time visitors;
- visible, structured data provenance with source, type, version, status, and optional confidence;
- dedicated institution exploration with metric history, groups, researchers, and representative papers;
- researcher profiles with affiliation history, fields, paper and collaboration connections, available external resources, and explicit data-source limitations;
- field overviews with demo milestones and connected research entities;
- normalized research-group, affiliation, paper, authorship, and historical-event records;
- paper identifier preparation for DOI, arXiv, and other external identifier schemes;
- an immersive fullscreen mode;
- typed, schema-validated local demo data;
- generic map features that accept any supplied metric observation through `metricValue`;
- a reproducible `ingestion → normalization → entity resolution → profile enrichment → metrics → export` pilot pipeline;
- append-only snapshot manifests, incremental-update planning, deterministic reprocessing, and isolated versioned outputs;
- a frontend integration that consumes both validated datasets through the same repository abstraction.

The synthetic source remains clearly identified demonstration data. The real-metadata pilot contains 81 INSPIRE-HEP literature records: the three most-recent primary-category `hep-th` matches for each year from 2000 through 2026. Its four calculated signals are incomplete, sample-relative engineering outputs, not validated scientific metrics. Neither source measures research quality or supports institutional, country, or researcher ranking.

## Technology

- React
- TypeScript
- Vite
- MapLibre GL JS
- Zod
- Vitest

The alpha has no deployed backend, database, scheduler, runtime scientific-API connection, AI prediction, ranking model, or final scientific methodology. The browser reads versioned local exports. INSPIRE-HEP is accessed only by the optional development pipeline, and the included calculations and weights remain framework or pilot-study mechanisms rather than scientific claims.

## Local development

Requirements:

- Node.js 22.13 or newer
- npm

```bash
npm install
npm run dev
```

Quality checks:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

Rebuild the checked-in pilot from its preserved raw snapshot:

```bash
npm run pipeline:rebuild
```

Acquire a fresh bounded snapshot from INSPIRE-HEP and regenerate the pilot artifacts:

```bash
npm run pipeline:ingest
```

Reprocess the preserved snapshot into an isolated version directory without changing the raw input:

```bash
node pipeline/reprocess.mjs pipeline/data/raw/inspire-hep-hep-th-2000-2026.json
```

A new acquisition can change the snapshot because source metadata and citation counts are maintained over time. The checked-in incremental plan is descriptive and requires explicit ingestion; no scheduler or live service runs in this alpha. See the [pilot-study documentation](docs/pilot-study.md) and [knowledge-graph update architecture](docs/knowledge-graph.md#incremental-and-non-destructive-updates) before interpreting or regenerating the data.

## Project structure

```text
src/components/atlas/   Map interface and exploration panels
src/domain/             Domain types and runtime schemas
src/data/               Query-oriented repository adapters and validated datasets
src/identity/           Canonical identity resolution
src/knowledge/          Typed canonical knowledge-graph projection
src/search/             Entity-aware canonical search index
src/profiles/           Read-only graph profile aggregation
src/metrics/            Metric definitions, registry, calculators, and composite framework
src/navigation/         URL parsing, canonical links, and hierarchy restoration
pipeline/               INSPIRE acquisition, resolution, versioned updates, metrics, and export
docs/                   Approved architecture and prototype documentation
```

The frontend depends on query-oriented repository methods rather than a transport mechanism. `ScientificAtlasRepository` extends the original `AtlasRepository` with canonical identity, resource, graph, update-lineage, and profile reads; the current `StaticAtlasRepository` implements it over local JSON. Future API and persistence seams are type contracts only and do not add a backend or database to this alpha.

## Documentation

- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md)
- [Entity resolution](docs/entity-resolution.md)
- [Geographic representation policy](docs/geography-policy.md)
- [Scientific knowledge graph](docs/knowledge-graph.md)
- [Metric engine](docs/metric-engine.md)
- [Metric model](docs/metric-model.md)
- [INSPIRE-HEP pilot study](docs/pilot-study.md)
- [Profile system](docs/profile-system.md)
- [Prototype plan](docs/prototype-plan.md)

## Open source

Physics Atlas is released under the [Apache License 2.0](LICENSE). Copyright (c) 2026 Tech Echo Collective. Attribution information is preserved in [NOTICE](NOTICE).

If Physics Atlas supports research or teaching work, use the repository's machine-readable [citation metadata](CITATION.cff). Contributions will be welcomed as the alpha architecture and data provenance process mature.
