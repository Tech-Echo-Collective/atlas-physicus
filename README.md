# Physics Atlas

Physics Atlas is an open-source scientific exploration system from [Tech Echo Collective](https://github.com/Tech-Echo-Collective). It visualizes the structure and evolution of physics research ecosystems through a map-first interface.

Physics Atlas is not a university or researcher ranking, a recommendation or prediction engine, or a replacement for scholarly databases such as arXiv and INSPIRE.

[Explore the public Physics Atlas](https://tech-echo-collective.github.io/Physics-Atlas-Web/) · [View the source repository](https://github.com/Tech-Echo-Collective/Physics-Atlas)

## v3.0.5-alpha

This release stabilizes the operated v3.0.4 platform and adds a reviewable
scientific-validation boundary. It preserves the bounded live architecture:

```text
Scientific sources → raw snapshots → normalization → entity resolution
→ canonical graph in PostgreSQL → incremental metric partitions
→ FastAPI → repository adapter → Atlas frontend
```

Highlights include:

- viewport-bounded map controls with an independently scrollable field list,
  compact live-data language, and responsive overlap protection;
- explicit candidate-v1 scientific contracts for Activity, Impact,
  Connectivity, Diversity, and Momentum, with metric-specific minimums and
  limitations;
- reconstructable normalization metadata and strict activation gates that keep
  every insufficient live metric layer neutral;
- deterministic identity-review sampling, validation-report contracts, and a
  compact aggregate identity-quality API;
- a corrected strict identity-evidence response contract for persisted
  missing-metadata reasons;
- a compact public status/methodology surface for live scope, source health,
  update freshness, identity review, metric versions, and dataset version;

- PostgreSQL canonical storage with Alembic migrations, temporal affiliations, immutable raw snapshots, provenance, identity-review records, update cursors, and resource-check history;
- a typed, paginated FastAPI read service behind the existing repository boundary;
- scheduled incremental connectors for INSPIRE-HEP, arXiv, and ROR, plus targeted ORCID and Crossref record-lookup connectors, with official provider APIs used only by the backend;
- resumable, idempotent incremental-update orchestration and affected-partition planning without inventing scientific metric formulas;
- authority-led identity resolution that never silently merges ambiguous records;
- canonical entity search across supported names and authority identifiers, including paper titles, DOI, arXiv, and INSPIRE identifiers;
- external-resource enrichment and bounded, SSRF-aware link monitoring;
- resumable worker cadences for INSPIRE, arXiv, and ROR that respect provider limits and expose health and last-update status;
- a frontend `APIRepository` with validated responses, cancellation, caching, source-transition reconciliation, and no silent mixing of datasets;
- a continuous, accessible timeline that keeps missing observations missing and does not interpolate scientific values;
- general antimeridian-safe polygon processing for Russia, disconnected territories, islands, and exclaves while preserving the geographic-view abstraction;
- institution pulse rings that inherit the exact node heat color and remain decorative;
- broader Physics taxonomy mappings without equating provider categories to Atlas fields.

The exploration hierarchy remains:

```text
Physics → research field → time → world → country → institution
→ research group → researcher / papers
```

## Data modes

- **Synthetic framework:** checked-in demonstration data for UI and metric-framework testing.
- **INSPIRE-HEP pilot:** a bounded, reproducible historical export; its calculated signals are incomplete engineering outputs, not validated scientific metrics.
- **Live API:** the normal public data path through the operated Railway
  FastAPI/PostgreSQL service. Local development and automated tests use
  deterministic fixtures by default, and fixture provenance remains explicitly
  synthetic. The current live metric layers are intentionally withheld because
  their scientific activation gates have not passed.

These modes are separate datasets. Synthetic and provider-derived observations
are never silently combined. The public GitHub Pages build configures
`VITE_ATLAS_API_URL` and exposes only the integrated live source in the normal
experience; static modes remain internal reproducibility and explicit fallback
paths.

## Technology

Frontend: React, TypeScript, Vite, MapLibre GL JS, Zod, Vitest.

Backend: Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, HTTPX.

## Frontend development

Requirements: Node.js 22.13 or newer and npm.

```bash
npm install
npm run dev
```

Validation:

```bash
npm run typecheck
npm run lint
npm test
npm run build
```

The checked-in pilot remains reproducible with `npm run pipeline:rebuild`; new bounded acquisition is an explicit operation through `npm run pipeline:ingest`.

## Backend and database

Copy `.env.example` to `.env`, retain fixture mode for a deterministic local run, then start PostgreSQL, migration, API, and worker services:

```bash
docker compose up --build
```

The API is served at `http://localhost:8000/api`; health and update state are available at `/api/health` and `/api/updates/status`. Configure the frontend with `VITE_ATLAS_API_URL=http://localhost:8000/api` to expose Live API mode.

Without Docker, backend checks can be run from `backend/` after installing `.[dev]`:

```bash
python -m ruff check src tests alembic
python -m mypy src
python -m pytest
python -m alembic upgrade head
```

Provider-backed operation requires explicit configuration and compliance with each provider's terms. No secrets or production credentials are included.

The scheduled worker uses the versioned `hep-th-v1` scope: INSPIRE
`subject:Theory-HEP`, arXiv `cat:hep-th`, and direct ROR refreshes only for
explicitly configured known IDs. ROR is skipped when no targets are configured.
ORCID and Crossref provide deliberately record-scoped lookup connectors for an
already-known ORCID iD or DOI; v3.0.5 does not use them as global
people/publication crawls. Persisted provider cursors are scope/version bound,
so an older broad cursor fails closed instead of being reused.

## Structure

```text
src/                 Map-first frontend and repository adapters
backend/             FastAPI, PostgreSQL models, connectors, worker, tests
pipeline/            Reproducible bounded INSPIRE pilot pipeline
docs/                Architecture, methods, provenance, and operations
docker-compose.yml   Local PostgreSQL/API/worker environment
```

## Documentation

- [Current project state](docs/PROJECT_STATE.md)
- [Durable decisions](docs/DECISIONS.md)
- [Worklog](docs/WORKLOG.md)
- [Architecture](docs/architecture.md)
- [Live-data architecture](docs/live-data-architecture.md)
- [Backend API](docs/backend.md)
- [Production deployment runbook](docs/production-deployment.md)
- [Database](docs/database.md)
- [Data sources and compliance](docs/data-sources.md)
- [Update engine](docs/update-engine.md)
- [Resource enrichment](docs/resource-enrichment.md)
- [Entity resolution](docs/entity-resolution.md)
- [Knowledge graph](docs/knowledge-graph.md)
- [Metric engine](docs/metric-engine.md)
- [Candidate scientific metric methodology](docs/metric-methodology-v1.md)
- [Metric normalization](docs/normalization.md)
- [Entity-resolution validation](docs/entity-resolution-validation.md)
- [Data quality and public status](docs/data-quality-status.md)
- [v3.0.5 live validation snapshot](docs/validation/v3.0.5-hep-th-live.md)
- [Geographic representation policy](docs/geography-policy.md)
- [Roadmap](docs/roadmap.md)

## Open source

Physics Atlas is released under the [Apache License 2.0](LICENSE). Copyright (c) 2026 Tech Echo Collective; attribution information is preserved in [NOTICE](NOTICE). Provider data remains subject to its own terms and licensing, documented separately from the code license.

If Physics Atlas supports research or teaching, use the machine-readable [citation metadata](CITATION.cff).
