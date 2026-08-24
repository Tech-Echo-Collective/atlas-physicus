# Physics Atlas architecture

## Purpose

Physics Atlas is an interactive atlas of the global physics research ecosystem. Its primary interface is a map that lets users move from the world level through research fields, countries, institutions, and researchers.

Physics Atlas is a visualization and knowledge-exploration system. It is not a ranking system, prediction system, recommendation engine, or replacement for scientific literature services.

## Alpha architecture

The Phase 1 prototype is a static client application:

```text
Synthetic JSON dataset
        ↓
Zod runtime validation
        ↓
StaticAtlasRepository
        ↓
React application
        ↓
MapLibre world map and exploration panels
```

Technology choices:

- React for component-based interface construction;
- TypeScript for explicit domain and component contracts;
- Vite for development and static production builds;
- MapLibre GL JS for open-source WebGL map rendering;
- Zod for validating data at the application boundary;
- Vitest for focused domain and repository tests.

The prototype uses local geographic data from the `world-atlas` package. It does not require a map API key or remote tile service.

## Module boundaries

### Domain

`src/domain` contains the stable product vocabulary and validation rules. It does not depend on React, MapLibre, or a backend transport.

### Data access

`src/data` implements the `AtlasRepository` interface. The current `StaticAtlasRepository` validates and serves local JSON. UI components do not import the raw JSON directly.

### Presentation

`src/components/atlas` contains the exploration interface. It receives typed domain values and does not calculate scientific metrics.

The map only converts a provided normalized prototype value into a fixed visual color scale. It does not interpret scientific quality or create rankings.

## Future architecture

The intended long-term system is:

```text
External scientific APIs
        ↓
Data acquisition pipeline
        ↓
Cleaning and entity matching
        ↓
Knowledge graph database
        ↓
Metric engine
        ↓
Backend API
        ↓
Frontend repository adapter
        ↓
Visualization interface
```

Potential scientific sources include OpenAlex, arXiv, INSPIRE, and Crossref. None are connected in Phase 1.

The future API adapter should implement the same repository contract used by the static prototype. A graph database is a possible future storage component, not an alpha dependency. Its adoption should follow demonstrated graph-query requirements rather than precede them.

## Architectural constraints

- Scientific methodology remains outside presentation components.
- Data entering the frontend is validated at a boundary.
- Missing observations are distinct from zero-valued observations.
- Demo data is always identified as synthetic.
- Metric provenance and period travel with every observation.
- Backend, persistence, authentication, and external ingestion remain out of Phase 1.
