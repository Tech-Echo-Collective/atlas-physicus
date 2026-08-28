# FastAPI backend

## Status

`backend/` is the v3.0.4-alpha read-oriented data service and update worker. It is designed for PostgreSQL and provides migrations, typed API schemas, provider connectors, deterministic fixtures, structured logging, and health/update status.

The backend is deployment-ready infrastructure. A local fixture deployment is not a public live service, and the repository does not contain production credentials or hosting. `PHYSICS_ATLAS_FIXTURE_MODE=true` is the safe default.

## Local container workflow

Requirements: Docker with Compose and a current Node.js installation for the frontend.

```bash
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL, runs Alembic to `head`, starts FastAPI on `http://localhost:8000`, and starts the worker. For a local Atlas frontend:

```bash
npm install
VITE_ATLAS_API_URL=http://localhost:8000/api npm run dev
```

Verify the backend with `GET http://localhost:8000/api/health`. Stop with `docker compose down`; add `--volumes` only when intentionally discarding the local database.

For a direct Python workflow, use Python 3.12+, install `backend[dev]`, set `PHYSICS_ATLAS_DATABASE_URL`, run `alembic -c backend/alembic.ini upgrade head`, then run `physics-atlas-api`. The container remains the reference path because it fixes the PostgreSQL and Python environment.

## Configuration

All settings use the `PHYSICS_ATLAS_` prefix. Important variables are:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `FIXTURE_MODE` | Use deterministic connector fixtures when true |
| `FIXTURE_DIRECTORY` | Optional installed path containing deterministic connector fixtures |
| `REFERENCE_DATA_PATH` | Optional installed path to the non-observational Atlas reference JSON |
| `ACQUISITION_SCOPE` | Versioned scheduled-ingestion policy; currently only `hep-th-v1` is supported |
| `ROR_RECORD_IDS` | Comma-separated, already-known ROR IDs to enrich; an empty value disables scheduled ROR requests |
| `WORKER_POLL_SECONDS` | Scheduler wake interval, not provider cadence |
| `RESOURCE_CHECK_MAX_PER_RUN` | Bound link checks per worker cycle |
| `RESOURCE_CHECK_ALLOWED_HOSTS` | Operator allowlist for bounded resource-health requests |
| `CROSSREF_MAILTO` | Identifies targeted Crossref requests to the polite pool |
| `ORCID_ACCESS_TOKEN` | Bearer token used for targeted ORCID record retrieval outside fixture mode |
| `ORCID_CLIENT_ID` / `ORCID_CLIENT_SECRET` | Optional operator-side credential metadata; the service does not exchange these for a token |

Never commit a populated `.env`, database password, provider token, or private client credential. Production CORS must name the deployed Atlas origin rather than using a wildcard.

## API surface

The configured prefix is `/api`. FastAPI validates query inputs and returns structured validation errors. Large collections are paginated and bounded by configured default/maximum sizes.

| Area | Routes |
| --- | --- |
| Service | `/health`, `/dataset`, `/updates/status` |
| Atlas vocabulary | `/domains`, `/fields`, `/countries`, `/countries/{id}`, `/geographic-views` |
| Map data | `/map/institutions` (country/domain/field/metric/year scoped and bounded) |
| Entities | `/institutions`, `/institutions/{id}`, `/groups`, `/researchers`, `/researchers/{id}`, `/papers`, `/papers/{id}` |
| Relationships | `/affiliations`, `/authorships` (including `paper_id` or `researcher_id` scope), `/historical-events` |
| Metrics | `/metrics`, `/metrics/{id}`, `/metric-observations` |
| Discovery | `/search`, `/knowledge-graph` (bounded diagnostic projection) |
| Profiles | `/profiles/institutions/{id}`, `/profiles/researchers/{id}`, `/profiles/groups/{id}` |
| Evidence | `/external-resources`, `/source-snapshots`, `/dataset-updates`, `/raw-entity-records`, `/identity-resolutions`, `/provenance/{type}/{id}` |

The knowledge-graph projection has a hard node bound and is not the normal map payload. Global bootstrap loads map vocabulary and country observations only; `/map/institutions` supplies major nodes for the selected country, and profile routes lazily load one canonical entity plus bounded relationships. The browser does not load every paper or researcher at startup. Canonical search uses the incrementally maintained `EntitySearchTerm` index rather than scanning all entities in application memory. It can return canonical papers from supported titles, DOI, arXiv, or INSPIRE identifiers; paper selection then loads `/papers/{id}` and paper-scoped authorships on demand.

## Frontend integration

`APIRepository` implements the same conceptual read contract as the static and pilot repositories. It validates responses with the frontend schemas, uses pagination, caches stable requests where appropriate, supports cancellation, and prevents a stale source response from replacing a newer selection.

Live mode appears only when `VITE_ATLAS_API_URL` is configured. A source switch preserves compatible domain/field/year/entity state and resets incompatible descendants. Until a destination dataset is validated, the current repository remains active. Synthetic, pilot, and API observations are never silently merged.

GitHub Pages can continue serving the static/pilot frontend with no backend URL. A true public live mode additionally requires a hosted HTTPS API, operated PostgreSQL database and worker, allowed CORS origin, migrations, backups, and provider-compliant configuration.

## Operations and validation

The service logs request IDs, request paths/status/duration, update events, sources, run IDs, and record counts as structured records. `/api/health` checks database connectivity and returns HTTP 503 with a structured degraded body when the database is unavailable. `/api/updates/status` reports freshness, each cursor's scope version, source failures, review backlog, resource failures, and metric-recalculation state. Dataset and evidence provenance expose the acquisition scope when one is present.

Repository validation covers Ruff, strict mypy, pytest fixtures, API routes, migrations, connector normalization, update idempotency/failure behavior, and resource checks. Standard tests do not call live providers.

The scheduler operates INSPIRE and arXiv within the configured acquisition scope. `hep-th-v1` maps to INSPIRE `subject:Theory-HEP` and arXiv `cat:hep-th`. ROR never scans the registry: it refreshes only `ROR_RECORD_IDS`, and is skipped when that list is empty. ORCID and Crossref remain targeted record enrichers and are not exposed as `--source` worker choices. The initial reference bootstrap contains taxonomy/geography/metric definitions but no synthetic scientific entities or observations.

Every provider cursor stores the exact scope and connector-policy version that created it. `DatasetState` separately records the shared corpus scope. A migrated legacy cursor, a live dataset without a scope marker, or a cursor/dataset from a different scope fails closed before provider I/O; an operator must deliberately replace or migrate it after preserving required evidence. Changing only the configuration does not reinterpret an older broad corpus as `hep-th`.

The API is public and read-oriented. It has bounded query parameters, GET/OPTIONS-only CORS, URL validation for the resource monitor, provider timeouts, and no authentication because v3.0.4 does not expose write endpoints. Production deployments still require ordinary network controls, TLS, database isolation, rate protection, backups, and log retention.
