# Physics Atlas worklog

Append one concise entry after every substantial implementation, deployment, or release task. Record facts rather than intentions, cite the relevant commit or explicitly state that work is uncommitted, list validation actually run, preserve unresolved issues, and end with one immediate next action. Do not rewrite earlier entries merely to make later work appear complete.

## 2026-08-28 20:30 +08 — v3.0.4-alpha platform release

- **Task:** Release the continuously updateable platform foundation.
- **Relevant commits:** `55c50b3` (platform implementation) and `09f5d85` (container API readiness correction); annotated tag `v3.0.4-alpha` resolves to `09f5d85`.
- **Completed:** PostgreSQL/Alembic persistence, FastAPI read service, connector and update foundations, identity/provenance/resource infrastructure, `APIRepository`, continuous timeline, geographic rendering fixes, Docker Compose, and release documentation.
- **Validation:** Frontend type checking, lint, tests, and production build; backend Ruff, strict mypy, pytest, migrations, PostgreSQL/API fixture ingestion, and container workflow passed for the release.
- **Unresolved:** No public backend, production API URL, hosting target, credentials, or provider-backed worker. The public Pages application remains static/pilot. Final live metrics and complete affiliation materialization are absent.
- **Immediate next action:** Operate a bounded staging deployment before connecting the public frontend.

## 2026-08-28 21:13 +08 — Production-activation context foundation

- **Task:** Establish durable repository context before v3.0.4 Production Activation.
- **Relevant commit:** Uncommitted documentation work based on released commit `09f5d85`.
- **Completed:** Added repository agent instructions, factual project state, durable decision log, worklog, and explicit production-activation roadmap status; documented the public static/pilot state and current activation blockers.
- **Validation:** Documentation paths and repository history were inspected, and `git diff --check` passed. No runtime code changed.
- **Unresolved:** Hosting target and credentials are absent. Scheduled acquisition is not `hep-th` bounded, ROR is not corpus-targeted, targeted ORCID/Crossref lookup is not orchestrated, canonical affiliations are incomplete, and reviewed live map metrics do not exist.
- **Immediate next action:** Choose an authorized hosting target and define the bounded ingestion configuration before any production deployment or public frontend switch.

## 2026-08-28 21:34 +08 — Bounded activation hardening and live smoke

- **Task:** Prepare the existing v3.0.4 architecture for a safe, bounded production activation and test the real provider path without claiming a deployment.
- **Relevant commit:** `b96aec8533bc1e8c3e7e84ff7a931adf7afa5605`.
- **Completed:** Added `hep-th-v1` INSPIRE/arXiv policy, target-only ROR, scope-bound cursors/snapshots/datasets, exact failed-page replay, provider pacing/lifecycle and pagination hardening, paper-replay safeguards, partial-reference repair, truthful API health/scope status, production Compose/Caddy/environment/runbook configuration, and persistent repository context. In an isolated temporary database, ingested real bounded INSPIRE/arXiv records, resumed checkpoints in fresh workers, served FastAPI across restart, performed one known-DOI Crossref lookup, and checked three resources. No live metric observations were written.
- **Validation:** Frontend type check, lint, 108 tests, and production build passed. Backend Ruff format/lint, strict mypy, 82 tests, fresh migrations, migration drift check, FastAPI startup/health/reads/restart, worker checkpoint resume, bounded provider requests, scope/provenance isolation, and structural production-Compose checks passed. A final code/config audit found no P1/P2 blocker. The installed test stack emitted one Starlette/httpx deprecation warning; the frontend build retained its existing large pilot-data chunk warning.
- **Unresolved:** No authorized host, DNS name, production PostgreSQL, credentials, off-host backup target, public API URL, or operated worker exists. Docker/Caddy/PostgreSQL binaries are unavailable locally, so containers, PostgreSQL restart/concurrency, Caddy TLS, backup/restore, and hosted browser CORS were not exercised. Browser UI automation was blocked by the environment's admin policy. Canonical affiliations, reviewed live metrics, automatic ROR/ORCID/Crossref orchestration, and general historical backfill remain incomplete. Pages therefore remains static/pilot and still exposes its development dataset selector.
- **Immediate next action:** Supply an authorized production host/provider, API domain/DNS control, ACME contact, database credentials, backup/monitoring arrangements, Crossref contact, and reviewed ROR IDs; then deploy and verify the stack before changing `Physics-Atlas-Web`.

## 2026-08-28 22:47 +08 — GitHub/CI health and Railway readiness pass

- **Task:** Audit both GitHub repositories before Railway production activation and repair only reproducible release-health blockers.
- **Relevant commit:** `ca4fe97a9d520ca78a20b57145e4e6c6b129da3c`; `v3.0.4-alpha` remains unchanged at `09f5d855a3ef28d687f5f888f0227a8f911b69de`.
- **Completed:** Corrected the stale CI expectation for the targetless-ROR safe default, moved workflow actions to their current Node 24-compatible major lines, accepted Railway `DATABASE_URL` and `PORT`, normalized generic PostgreSQL schemes to psycopg 3, made the image use the validated API entrypoint, rejected fixture mode in production, added focused configuration tests, and documented the exact Railway API/worker activation profile. Audited `Physics-Atlas-Web`; no change was necessary.
- **Validation:** Physics Atlas frontend type check, lint, 108 tests, and production build passed; backend Ruff format/lint, strict mypy, 94 tests, fresh migrations, migration drift check, deterministic worker update, API health/status, non-default Railway port, and PostgreSQL URL compatibility passed. Physics Atlas Web type check, lint, five deployment tests, production build, and submodule integrity passed. Both npm audits reported zero vulnerabilities; Python `pip check` reported no broken requirements. Main GitHub Actions run [33181797118](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33181797118) passed `verify`, `backend`, and `containers`; Web Pages run [33172110570](https://github.com/Tech-Echo-Collective/Physics-Atlas-Web/actions/runs/33172110570) was green.
- **Unresolved:** No Railway project, managed database, production credentials, hostname, or operated worker is present yet. The worker must remain manually sequenced after the API-owned Alembic/health gate. The existing pilot bundle-size and third-party Starlette/httpx test deprecation warnings are non-blocking; Python dependencies are bounded but not frozen in a lock file. Scientific live-data limitations remain unchanged.
- **Immediate next action:** Provision the Railway PostgreSQL, API, and worker services from `main` using `docs/production-deployment.md`, verify the bounded backend privately, and connect Pages only after the activation gate passes.
