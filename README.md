# Physics Atlas

Physics Atlas is an open-source project by [Tech Echo Collective](https://github.com/Tech-Echo-Collective) for exploring the structure and evolution of the global physics research ecosystem through an interactive map.

The project is a visualization and knowledge-exploration platform. It is not a scientific ranking system, a prediction engine, a researcher recommendation service, or a replacement for arXiv and Google Scholar.

## Alpha prototype

Physics Atlas is currently an early alpha prototype. Phase 2.3 strengthens the usability and data foundation of the normalized research-entity atlas:

```text
Science domain → Optional research field → Time → World → Country → Institution → Research group → Researcher
```

The current development state provides:

- a dark, interactive MapLibre scientific atlas with a full violet-to-red spectral activity scale;
- scale-aware map layers: World View shows only country activity, while Country View replaces it with a neutral country canvas and institution activity nodes;
- an overall Physics domain heatmap and field-specific heatmaps, designed for later domain expansion;
- field selection for `hep-th`, `gr-qc`, `quant-ph`, and `cond-mat`;
- a historical timeline with synthetic observations for 1900, 1950, 2000, and 2026;
- a synthetic country-level `research_activity_score` heatmap;
- world-to-country camera transitions and activity-scaled institution nodes;
- configurable geographic-view membership, keeping rendered geometry separate from institution and affiliation metadata;
- a compact map-native global reset above the zoom controls;
- URL-addressable domain, field, country, institution, and researcher views with browser back/forward restoration;
- lightweight search across existing atlas entities;
- an optional seven-step guided exploration path for first-time visitors;
- visible, structured data provenance with source, type, version, status, and optional confidence;
- dedicated institution exploration with historical activity, groups, researchers, and representative papers;
- synthetic researcher profiles with affiliations, fields, paper connections, and optional external links;
- field overviews with demo milestones and connected research entities;
- normalized research-group, affiliation, paper, authorship, and historical-event records;
- paper identifier preparation for DOI, arXiv, and other external identifier schemes;
- an immersive fullscreen mode;
- typed, schema-validated local demo data;
- an interface boundary that can later be backed by a real metric engine and API.

All metric values, researchers, groups, papers, events, and relationship records shown in the prototype are synthetic demonstration data. Real institution names are used only as recognizable location examples. The prototype does not measure research output, impact, quality, influence, or institutional performance.

## Technology

- React
- TypeScript
- Vite
- MapLibre GL JS
- Zod
- Vitest

The alpha has no backend, database, external scientific API connection, real research dataset, AI prediction, custom metric weighting, or final metric engine.

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

## Project structure

```text
src/components/atlas/   Map interface and exploration panels
src/domain/             Domain types and runtime schemas
src/data/               Query-oriented repository adapter and synthetic dataset
src/navigation/         URL parsing, canonical links, and hierarchy restoration
docs/                   Approved architecture and prototype documentation
```

The frontend depends on query-oriented `AtlasRepository` methods rather than on a transport mechanism. The current `StaticAtlasRepository` reads local JSON; a future `APIRepository` can retrieve validated data without changing the exploration components.

## Documentation

- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md)
- [Geographic representation policy](docs/geography-policy.md)
- [Metric model](docs/metric-model.md)
- [Prototype plan](docs/prototype-plan.md)

## Open source

Physics Atlas is released under the [Apache License 2.0](LICENSE). Copyright (c) 2026 Tech Echo Collective. Attribution information is preserved in [NOTICE](NOTICE).

If Physics Atlas supports research or teaching work, use the repository's machine-readable [citation metadata](CITATION.cff). Contributions will be welcomed as the alpha architecture and data provenance process mature.
