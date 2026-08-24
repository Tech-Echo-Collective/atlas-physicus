# Physics Atlas architecture

## Purpose

Physics Atlas is an interactive atlas of the global physics research ecosystem. Its primary interface is a map that lets users move from the world level through research fields, countries, institutions, and researchers.

Physics Atlas is a visualization and knowledge-exploration system. It is not a ranking system, prediction system, recommendation engine, or replacement for scientific literature services.

## Alpha architecture

The Phase 2.3 prototype remains a static client application:

```text
Synthetic JSON dataset
        ↓
Zod runtime validation
        ↓
StaticAtlasRepository
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

The prototype uses local geographic data from the `world-atlas` package. It does not require a map API key or remote tile service. Historical activity observations and institution coordinates are part of the validated local fixture.

## Module boundaries

### Domain

`src/domain` contains the stable product vocabulary and validation rules. It does not depend on React, MapLibre, or a backend transport.

### Data access

`src/data` implements the `AtlasRepository` interface. The current `StaticAtlasRepository` validates local JSON once and exposes granular queries for domains, fields, countries, institutions, groups, researchers, papers, relationships, events, and observations. `loadAtlasDataset` assembles the current alpha snapshot through that interface; UI components never import raw JSON. A future `APIRepository` can implement the same contract without changing the atlas hierarchy.

Structured provenance is normalized at this boundary. Every validated entity and metric observation receives `source`, `sourceType`, `version`, `status`, and optional confidence/retrieval metadata. The fixture's legacy `synthetic-demo` shorthand is expanded into the explicit Phase 2.3 provenance object during validation.

### Navigation

`src/navigation` owns canonical URL creation and restoration. It maps shareable domain/field paths and country, institution, or researcher paths into the existing normalized hierarchy. Browser history remains the navigation source of truth after startup; back and forward events restore all dependent entity selections. URL resolution uses normalized relationships and geographic-view membership rather than duplicating scientific data inside routes.

### Presentation

`src/components/atlas` contains the exploration interface. `AtlasExplorer` coordinates repository data, URL state, search, and the optional guided path. `WorldMap` owns MapLibre lifecycle and geographic navigation, `GeographicGeometryLayer` joins packaged GeoJSON features to configured views and composes a dedicated country-mode canvas, `GeographicEntityMapping` resolves geometry and location membership, and `InstitutionLayer` converts already-provided institution observations into points. Dedicated institution, researcher, and field layers resolve normalized entity relationships without embedding records inside UI state.

The map only converts a provided normalized prototype value into fixed color and point-size scales. It does not interpret scientific quality, derive historical values, or create rankings.

Map information density follows the exploration hierarchy. World View enables only the global country choropleth. Country View disables every global country layer, renders only the configured country canvas with a neutral geographic fill, and enables the curated institution heat layer. Institution View retains that geographic context while the entity panel becomes the primary surface for groups, researchers, papers, and fields. `MapLayerHierarchy` defines and tests these layer transitions independently from MapLibre lifecycle code.

World-layer colors resolve through `GeographicView` membership rather than assuming a one-to-one relationship between a source polygon and a metric entity. The native geometry/location identifier is retained alongside the visualization metric identifier, keeping rendering decisions separate from scientific attribution.

Geographic geometry and scientific attribution are independent inputs. Map boundaries provide exploration context, while institution locations and future collaboration attribution follow institutional and affiliation metadata. The governing rules are documented in the [geographic representation policy](geography-policy.md).

## Phase 2.3 interaction architecture

```text
ScienceDomain (Physics)
        ├── domain observations ────────────────┐
        └── optional ResearchField              │
                    └── field observations ─────┤
                                                ↓
                                  MetricObservation.period
                                                ↓
country observations → world heatmap
        ↓ country selection
institution observations + location → institution points
        ↓ institution selection
InstitutionView
        ↓ research-group affiliation
ResearcherProfile

ResearchField → HistoricalEvent + Institution + Researcher + Paper
Paper ← Authorship → Researcher ← Affiliation → Institution / ResearchGroup

GeographicView → source geometry membership + institution-location membership

URL route ↔ AtlasNavigationState → existing hierarchy
Entity search → repository result → canonical route
Guided exploration → canonical state transitions (optional)
Entity / MetricObservation → DataProvenance
```

Time is represented by the existing `MetricObservation.period` field. This avoids introducing a parallel historical metric type and keeps the repository query boundary compatible with the Phase 1 model.

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

Potential scientific sources include OpenAlex, arXiv, INSPIRE, and Crossref. None are connected in Phase 2.3.

The future API adapter should implement the same repository contract used by the static prototype. A graph database is a possible future storage component, not an alpha dependency. Its adoption should follow demonstrated graph-query requirements rather than precede them.

## Architectural constraints

- Scientific methodology remains outside presentation components.
- Data entering the frontend is validated at a boundary.
- Missing observations are distinct from zero-valued observations.
- World, country, and institution views expose only the geographic layers appropriate to their scale.
- Demo data is always identified as synthetic.
- Structured provenance travels with every entity and metric observation.
- Geographic rendering does not determine exclusive ownership of scientific activity.
- Domain and field observations are separate validated inputs; the frontend does not aggregate one into the other.
- Global reset clears geographic/entity state and restores the minimum world camera without leaving fullscreen.
- URL state contains identifiers and exploration context only; scientific records remain in the repository layer.
- Backend, persistence, authentication, and external ingestion remain out of Phase 2.3.
