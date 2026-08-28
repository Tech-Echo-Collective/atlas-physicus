# Physics Atlas project state

Last reviewed: 2026-08-29

This file records the factual operating state of the project. Read it with [durable decisions](DECISIONS.md), the [roadmap](roadmap.md), and the [worklog](WORKLOG.md) before major work.

## Current release

- Current release: `v3.0.5-alpha`.
- Source branch: `main` in `Tech-Echo-Collective/Physics-Atlas`.
- The `v3.0.5-alpha` annotated tag identifies the stabilization and scientific-
  validation release commit. Existing `v3.0.4-alpha` remains unchanged at
  `09f5d855a3ef28d687f5f888f0227a8f911b69de`.
- The active milestone is **v3.0.5-alpha Stabilization & Scientific
  Validation**. v3.1 has not started.

## Implemented systems

### Frontend

- React, TypeScript, Vite, MapLibre GL JS, and Zod application.
- Map-first world → country → institution → researcher exploration.
- Domain, field, and continuous time navigation.
- Static synthetic repository, preserved historical INSPIRE-HEP pilot repository, and API-backed repository behind one repository boundary.
- Validated API responses, pagination, caching, cancellation, stale-response protection, scoped map/profile loading, and deep-link hydration.
- Explicit provenance and missing-data treatment; a missing metric is not converted to zero.
- Viewport-bounded desktop controls, independently scrollable field and
  institution lists, compact live-data language, and tablet timeline/card
  overlap protection.
- Compact live methodology/status inside the existing information control;
  map presentation remains primary.
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
- Candidate-v1 scientific contracts and deterministic normalization helpers for
  Activity, Impact, Connectivity, Diversity, and Momentum.
- Additive metric-observation reconstruction metadata: definition, algorithm,
  dataset and scope versions; raw value/unit; normalization method/parameters;
  input count; quality flags; and calculation partition/time.
- Current-version metric reads exclude stale definitions and dataset lineages,
  deterministically select only same-algorithm recalculations, and fail
  conflicting-algorithm partitions closed across map and profile endpoints.
- Database-backed scientific activation reports that fail closed and never
  create observations.
- Deterministic identity-review sampling, independently labeled validation
  reports, and an aggregate public identity-quality summary.
- Deterministic fixtures, PostgreSQL integration tests, and Docker Compose services for database, migration, API, and worker validation.

## Public deployment state

- The public entry point is the separate `Tech-Echo-Collective/Physics-Atlas-Web` GitHub Pages project.
- The public Pages application at <https://tech-echo-collective.github.io/Physics-Atlas-Web/> is built with `VITE_ATLAS_API_URL=https://physics-atlas-api-production.up.railway.app/api` and uses `APIRepository` on normal clean routes.
- The normal public source selector exposes only the live API. Synthetic framework and historical pilot repositories remain available only through explicit internal routes for tests, reproducibility, and first-load failure fallback.
- Data-source resolution, repository boundaries, dataset-kind validation, and scoped live merges prevent live/static record mixing.
- The production API currently publishes no reviewed metric observations. All
  five live candidate layers fail the v3.0.5 evidence gates and remain
  explicitly withheld. The public map stays neutral; missing data is not zero.

## Repository and CI health

- The `v3.0.5-alpha` release gate includes 123 frontend component/data tests,
  seven deterministic pipeline tests, 113 backend tests, strict TypeScript and
  mypy checks, ESLint/Ruff, production builds, a fresh migration plus drift
  check, deterministic fixture ingestion, local API/CORS contract checks, and
  zero npm audit findings. The tag is created only after the GitHub frontend,
  PostgreSQL backend, and container jobs pass on the release commit.
- `Physics-Atlas` main commit `45da545` passed GitHub Actions
  [run 33182035844](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33182035844): frontend verification, PostgreSQL-backed backend validation, and the Docker Compose job all succeeded.
- The preceding main failure was a stale CI assertion that expected scheduled ROR
  output even when no reviewed ROR IDs were configured. CI now verifies the
  intentional `hep-th-v1` INSPIRE/arXiv safe default and its scope versions.
- The preceding v3.0.4 public activation at `Physics-Atlas-Web` main commit
  `13f1d5b` passed and deployed through GitHub Pages
  [run 33186585196](https://github.com/Tech-Echo-Collective/Physics-Atlas-Web/actions/runs/33186585196). Its `atlas` submodule is pinned to validated Physics Atlas main commit `45da545`; the `v3.0.4-alpha` tag was not moved.
- The v3.0.5 public deployment updates that submodule to the release commit and
  retains `APIRepository` as the normal clean-route source; synthetic and pilot
  repositories remain isolated reproducibility/fallback modes.
- Both npm dependency audits reported zero vulnerabilities, and the installed
  backend environment reported no broken Python requirements. No broad
  dependency upgrade was justified.

## Backend deployment state

- The production Railway API is operating at <https://physics-atlas-api-production.up.railway.app/api>. Before the v3.0.5 deployment it reported a healthy database and API version `3.0.4-alpha`; the release gate requires the deployed version to advance and remain healthy.
- The live evidence observed on 2026-08-29 reported `datasetKind: live-api`,
  acquisition scope `hep-th-v1`, update sequence 3, dataset version
  `live-20260828T155141Z-004ec04c`, and a last successful update at
  2026-08-28 15:51:44 UTC. INSPIRE and arXiv reported healthy cursor state and
  idle metric recalculation.
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

## Scientific validation result and limitations

- The bounded production snapshot has 44 canonical papers, 82 researchers, and
  82 authorships, but zero canonical institutions, affiliations, citation
  edges, or metric observations. Canonical papers cover 2026 only.
- Identity resolution has 319 outcomes: 126 external-identifier matches, 193
  unresolved/open-review records, and zero ambiguous outcomes. The 60.50%
  unresolved rate combines missing-metadata quarantine and authority-absent
  abstention; it is not a precision/error measurement.
- No independently labeled live truth sample exists, so precision, recall, and
  confidence calibration remain withheld. Institution/ROR validation cannot be
  measured against the canonical graph until institution materialization exists.

- Raw INSPIRE affiliation, reference, and citation structures are preserved, but the scheduled materializer does not yet promote them into reviewed canonical affiliation and citation edges.
- Institution/country attribution therefore remains too incomplete for a useful live geographic research view.
- No scientifically reviewed live metric formulas are implemented. Affected partitions are recorded, but no live country or institution heat values are fabricated.
- The live frontend can correctly show a neutral missing-data map, but that is not yet a useful scientific activity heatmap.
- Resolver precision has not been calibrated against a representative reviewed truth set, and there is no public resolution-review interface. The deterministic sample/report framework is present for that next bounded review.
- arXiv acquisition tracks new submissions through `submittedDate`; it is not a complete subsequent-revision stream.
- ROR targets are operator-configured until reviewed affiliation evidence can
  drive them automatically, and there is no general historical backfill command.
- Retraction, tombstone, cross-provider conflict, large-backfill, and long-term provider-payload retention policies require review before wider operation.

## Immediate task after v3.0.5-alpha

Preserve the hosted source → PostgreSQL → FastAPI → `APIRepository` path and
keep `hep-th-v1` bounded. The next minimum scientific action is independent
identity review, followed by reviewed affiliation materialization:

1. export and independently label the deterministic bounded identity-validation
   manifest, including common names, authority conflicts, historical names,
   aliases, and correct abstentions;
2. implement an append-only, resolver-versioned supersession path for older raw
   records that gain stronger cross-provider evidence;
3. materialize and review sufficient canonical institution and paper-time
   affiliation evidence for geographic validation;
4. retain the candidate metric versions and re-run their exact gates only after
   those inputs and multi-year coverage exist;
5. collect durable backup/restore, restart, monitoring, rate-protection, and
   alerting evidence for the operated Railway services.

Do not begin v3.1, expand to all Physics, or activate a live heatmap merely to
fill the map. The next release scope must be chosen from evidence after this
bounded review.
