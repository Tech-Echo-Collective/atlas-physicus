# Physics Atlas

Physics Atlas is an open-source project by [Tech Echo Collective](https://github.com/Tech-Echo-Collective) for exploring the structure and evolution of the global physics research ecosystem through an interactive map.

The project is a visualization and knowledge-exploration platform. It is not a scientific ranking system, a prediction engine, a researcher recommendation service, or a replacement for arXiv and Google Scholar.

## Alpha prototype

Physics Atlas is currently an early alpha prototype. The first product slice demonstrates the interaction model:

```text
World map → Research field → Country → Institution → Researcher
```

Phase 1 currently provides:

- an interactive MapLibre world map;
- field selection for `hep-th`, `gr-qc`, `quant-ph`, and `cond-mat`;
- a synthetic `research_activity_score` visualization;
- country selection with basic institution and researcher counts;
- typed, schema-validated local demo data;
- an interface boundary that can later be backed by a real metric engine and API.

All values shown in the prototype are synthetic demonstration data. They do not measure research output, impact, quality, influence, or institutional performance.

## Technology

- React
- TypeScript
- Vite
- MapLibre GL JS
- Zod
- Vitest

The alpha has no backend, database, external scientific API connection, AI prediction, custom metric weighting, or final metric engine.

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
src/data/               Repository adapter and synthetic dataset
docs/                   Approved architecture and prototype documentation
```

The frontend depends on an `AtlasRepository` interface rather than on a transport mechanism. The current implementation reads local JSON; a future implementation can retrieve validated data from an API without coupling the map components to the backend.

## Documentation

- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md)
- [Metric model](docs/metric-model.md)
- [Prototype plan](docs/prototype-plan.md)

## Open source

Physics Atlas is released under the [MIT License](LICENSE). Contributions will be welcomed as the alpha architecture and data provenance process mature.
