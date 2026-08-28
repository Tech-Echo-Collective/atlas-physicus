# Physics Atlas project state

Last reviewed: 2026-08-28

This file records the factual operating state of the project. Read it with [durable decisions](DECISIONS.md), the [roadmap](roadmap.md), and the [worklog](WORKLOG.md) before major work.

## Current release

- Current release: `v3.0.4-alpha`.
- Source branch: `main` in `Tech-Echo-Collective/Physics-Atlas`.
- The annotated release tag resolves to commit `09f5d855a3ef28d687f5f888f0227a8f911b69de`.
- The live-data platform implementation landed in `55c50b3`; `09f5d85` contains the release CI readiness correction.
- Production-activation hardening and the persistent context foundation landed in follow-up commit `b96aec8`; the release tag was not moved.
- CI and Railway activation compatibility were corrected in follow-up commit
  `ca4fe97`; the release tag remains on `09f5d85`.
- CI health and Railway readiness were recorded in follow-up commit `45da545`;
  the release tag remains on `09f5d85`.
- The active milestone is **v3.0.4 Production Activation**. v3.0.5 has not started.

## Implemented systems

### Frontend

- React, TypeScript, Vite, MapLibre GL JS, and Zod application.
- Map-first world → country → institution → researcher exploration.
- Domain, field, and continuous time navigation.
- Static synthetic repository, preserved historical INSPIRE-HEP pilot repository, and API-backed repository behind one repository boundary.
- Validated API responses, pagination, caching, cancellation, stale-response protection, scoped map/profile loading, and deep-link hydration.
- Explicit provenance and missing-data treatment; a missing metric is not converted to zero.
- Multipolygon, disconnected-territory, and antimeridian rendering, including the established China geographic-view behavior and Russia/Kaliningrad handling.

### Backend and data platform

- FastAPI read service with typed, paginated Atlas, profile, provenance, search, update-status, and health endpoints.
- PostgreSQL persistence through SQLAlchemy and Alembic.
- Canonical entities and temporal relationships, raw provider evidence, source snapshots, authority identifiers, resolution/review records, dataset updates, cursors, resources, and metric observations.
- Incremental, auditable, idempotent update engine with closed-window checkpoints and PostgreSQL advisory locking.
- Versioned `hep-th-v1` scheduled acquisition: INSPIRE `subject:Theory-HEP`,
  arXiv `cat:hep-th`, and direct ROR refreshes only for configured known IDs.
- Targeted record lookup implementations for known ORCID iDs and DOIs through ORCID and Crossref.
- External-resource enrichment and bounded resource-health monitoring.
- Scope-bound provider cursors, snapshots, and dataset provenance that fail closed
  rather than reusing or mixing a broader acquisition scope.
- Bounded provider HTTP retries, rate-limit handling, per-provider origin
  isolation, strict response envelopes, and conservative authority-conflict review.
- Affected metric-partition planning with `NoFormulaMetricRecalculator`; no unreviewed scientific scores are written.
- Deterministic fixtures, PostgreSQL integration tests, and Docker Compose services for database, migration, API, and worker validation.

## Public deployment state

- The public entry point is the separate `Tech-Echo-Collective/Physics-Atlas-Web` GitHub Pages project.
- The public Pages application at <https://tech-echo-collective.github.io/Physics-Atlas-Web/> is built with `VITE_ATLAS_API_URL=https://physics-atlas-api-production.up.railway.app/api` and uses `APIRepository` on normal clean routes.
- The normal public source selector exposes only the live API. Synthetic framework and historical pilot repositories remain available only through explicit internal routes for tests, reproducibility, and first-load failure fallback.
- Data-source resolution, repository boundaries, dataset-kind validation, and scoped live merges prevent live/static record mixing.
- The production API currently publishes no reviewed metric observations. The public map therefore remains explicitly neutral and does not display an unvalidated scientific score; missing data is not treated as zero.

## Repository and CI health

- `Physics-Atlas` main commit `45da545` passed GitHub Actions
  [run 33182035844](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33182035844): frontend verification, PostgreSQL-backed backend validation, and the Docker Compose job all succeeded.
- The preceding main failure was a stale CI assertion that expected scheduled ROR
  output even when no reviewed ROR IDs were configured. CI now verifies the
  intentional `hep-th-v1` INSPIRE/arXiv safe default and its scope versions.
- `Physics-Atlas-Web` main commit `13f1d5b` passed and deployed through GitHub Pages
  [run 33186585196](https://github.com/Tech-Echo-Collective/Physics-Atlas-Web/actions/runs/33186585196). Its `atlas` submodule is pinned to validated Physics Atlas main commit `45da545`; the `v3.0.4-alpha` tag was not moved.
- Both npm dependency audits reported zero vulnerabilities, and the installed
  backend environment reported no broken Python requirements. No broad
  dependency upgrade was justified.

## Backend deployment state

- The production Railway API is operating at <https://physics-atlas-api-production.up.railway.app/api> with a healthy database and API version `3.0.4-alpha`.
- The live dataset reports `datasetKind: live-api`, acquisition scope `hep-th-v1`, and update sequence 2. Update status reports a successful 2026-08-28 run with healthy INSPIRE and arXiv connectors and idle metric recalculation.
- CORS admits the exact GitHub Pages origin for GET and preflight requests. The deployed Pages bundle contains the configured HTTPS API endpoint.
- `compose.production.yml`, Caddy configuration, a production environment
  template, and an operator runbook now configure PostgreSQL, migrations,
  FastAPI, the bounded worker, and automatic HTTPS for a single authorized host.
- The API now consumes Railway's standard `DATABASE_URL` and `PORT`, normalizes
  generic PostgreSQL URLs to the installed psycopg 3 driver, and refuses to
  start in production fixture mode. The runbook records the required Dockerfile
  path, API migration/health gate, and separately sequenced worker service.
- The production definition fixes `hep-th-v1`, disables fixtures, admits only the
  exact GitHub Pages origin, keeps PostgreSQL/FastAPI unpublished, and leaves
  credentials in an ignored operator environment file.
- Railway provisioning, managed PostgreSQL, API, and bounded worker activation are complete. Secret values remain outside the repository.
- Off-host backup/restore evidence, rate protection, longer-running monitoring,
  alerting, and operational rehearsal remain operator responsibilities and have
  not been verified from this repository context.

## Data-source state

All retained modes remain isolated:

- **Synthetic framework:** hand-authored UI and architecture test data.
- **Historical INSPIRE-HEP pilot:** bounded, reproducible provider metadata retained for methodology and regression work.
- **Live API fixture mode:** deterministic connector fixtures exercising the complete database/API path in development and CI.
- **Provider-backed live mode:** deployed through Railway and used by the public Pages application as the normal data path.

The implemented provider-backed path is bounded to the requested activation
corpus:

- `hep-th-v1` is the only accepted acquisition policy.
- INSPIRE requests `subject:Theory-HEP`; arXiv requests `cat:hep-th`.
- ROR never scans the registry. It refreshes only configured, normalized known
  IDs and is skipped when the target list is empty.
- ORCID and Crossref remain targeted lookups. Crossref was smoke-tested with a
  DOI already discovered in the bounded corpus; no known ORCID was present, so
  ORCID was correctly not queried.
- A scope mismatch in the provider cursor or live dataset fails before provider
  I/O. Synthetic, fixture, pilot, and provider-backed records remain isolated.

An isolated local provider smoke run covered the closed historical window
2025-01-01 through 2025-01-02. It persisted four real INSPIRE/arXiv source
snapshots, 22 raw records, and seven canonical papers in a temporary database;
the arXiv window completed and the deliberately one-record INSPIRE pagination
checkpoint remained resumable. Fresh worker processes resumed both provider
checkpoints, FastAPI served the persisted records before and after restart, and
a three-resource monitoring pass completed. This is staging evidence, not a
production update or public dataset.

## Known limitations blocking a useful live Atlas

- Raw INSPIRE affiliation, reference, and citation structures are preserved, but the scheduled materializer does not yet promote them into reviewed canonical affiliation and citation edges.
- Institution/country attribution therefore remains too incomplete for a useful live geographic research view.
- No scientifically reviewed live metric formulas are implemented. Affected partitions are recorded, but no live country or institution heat values are fabricated.
- The live frontend can correctly show a neutral missing-data map, but that is not yet a useful scientific activity heatmap.
- Resolver precision has not been calibrated against a representative reviewed truth set, and there is no public resolution-review interface.
- arXiv acquisition tracks new submissions through `submittedDate`; it is not a complete subsequent-revision stream.
- ROR targets are operator-configured until reviewed affiliation evidence can
  drive them automatically, and there is no general historical backfill command.
- Retraction, tombstone, cross-provider conflict, large-backfill, and long-term provider-payload retention policies require review before wider operation.

## Immediate task: v3.0.4 Production Activation

The hosted source → PostgreSQL → FastAPI → `APIRepository` path is now active without redesigning the architecture or starting v3.0.5. Remaining activation work is operational and scientific validation:

1. collect durable backup/restore, restart, monitoring, rate-protection, and alerting evidence for the operated Railway services;
2. observe bounded `hep-th-v1` updates long enough to assess provider and resolver behavior without broadening scope;
3. materialize and review sufficient canonical affiliation evidence for meaningful country and institution exploration;
4. review and version scientific metric methods before publishing any live heat values;
5. retain explicit static and pilot routes for reproducibility while keeping them outside the normal public selector.

The public transport and frontend activation gates are complete. Do not claim the broader production milestone scientifically complete until the geographic view has sufficient reviewed affiliation and metric data to be meaningful.
