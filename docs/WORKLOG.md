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
- **Relevant commit:** Uncommitted follow-up work based on released commit `09f5d85`; replace this line with the implementation commit after it is created.
- **Completed:** Added `hep-th-v1` INSPIRE/arXiv policy, target-only ROR, scope-bound cursors/snapshots/datasets, provider transport and paper-replay hardening, partial-reference repair, production Compose/Caddy/environment/runbook configuration, and persistent repository context. In an isolated temporary database, ingested real bounded INSPIRE/arXiv records, resumed checkpoints in fresh workers, served FastAPI across restart, performed one known-DOI Crossref lookup, and checked three resources. No live metric observations were written.
- **Validation:** Frontend type check, lint, 108 tests, and production build passed. Backend Ruff format/lint, strict mypy, 66 tests, fresh migrations, migration drift check, FastAPI startup/health/reads/restart, worker checkpoint resume, bounded provider requests, scope/provenance isolation, and structural production-Compose checks passed. The installed test stack emitted one Starlette/httpx deprecation warning; the frontend build retained its existing large pilot-data chunk warning.
- **Unresolved:** No authorized host, DNS name, production PostgreSQL, credentials, off-host backup target, public API URL, or operated worker exists. Docker/Caddy/PostgreSQL binaries are unavailable locally, so containers, PostgreSQL restart/concurrency, Caddy TLS, backup/restore, and hosted browser CORS were not exercised. Browser UI automation was blocked by the environment's admin policy. Canonical affiliations, reviewed live metrics, automatic ROR/ORCID/Crossref orchestration, and general historical backfill remain incomplete. Pages therefore remains static/pilot and still exposes its development dataset selector.
- **Immediate next action:** Supply an authorized production host/provider, API domain/DNS control, ACME contact, database credentials, backup/monitoring arrangements, Crossref contact, and reviewed ROR IDs; then deploy and verify the stack before changing `Physics-Atlas-Web`.
