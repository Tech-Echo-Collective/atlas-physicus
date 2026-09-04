# Archived worklog: platform activation through v3.0.5 release

This archive compresses the detailed worklog entries from 2026-08-28 through
the `v3.0.5-alpha` release on 2026-08-29. Release tags and cited commits are the
provenance record; current operating facts belong in
[`PROJECT_STATE.md`](../PROJECT_STATE.md), and durable policy belongs in
[`DECISIONS.md`](../DECISIONS.md).

## v3.0.4 platform foundation

- `v3.0.4-alpha` was implemented in `55c50b3` and corrected for container API
  readiness in tagged commit `09f5d85`.
- The release established PostgreSQL/Alembic persistence, the FastAPI read
  service, provider/update and identity/provenance infrastructure,
  `APIRepository`, Docker Compose, and the continuously updateable platform
  boundary. It did not claim that a public backend was operating.
- Commit `b96aec8` then fixed the acquisition boundary at `hep-th-v1`, added
  target-only authority lookup, scope-bound cursors and datasets, bounded retry
  and replay behavior, and a production deployment profile. An isolated live
  provider smoke run demonstrated resumable INSPIRE/arXiv acquisition without
  publishing metric observations.
- Commit `ca4fe97` restored CI and Railway readiness by correcting the
  targetless-ROR expectation, updating workflow action runtimes, accepting
  Railway's database/port conventions, and adding focused configuration tests.
  GitHub Actions run
  [33181797118](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33181797118)
  passed frontend, PostgreSQL backend, migration, ingestion/API, and container
  jobs. `v3.0.4-alpha` was not moved.

## Public backend and frontend activation

- Railway PostgreSQL, API, and bounded worker operation was verified before the
  normal public frontend path changed. The source-side readiness record is
  `45da545`.
- `Tech-Echo-Collective/Physics-Atlas-Web` commit `13f1d5b` exposed the
  configured production API URL to the Pages build, pinned the Atlas source,
  made `APIRepository` the normal clean-route source, and removed synthetic and
  pilot choices from normal public navigation while retaining their isolated
  test/reproducibility paths.
- Pages run
  [33186585196](https://github.com/Tech-Echo-Collective/Physics-Atlas-Web/actions/runs/33186585196)
  passed. API health, root and deep-route fallback, exact-origin CORS, and zero
  public metric observations were verified. The public map intentionally
  remained neutral because no reviewed live metric layer existed.

## v3.0.5 stabilization and scientific-validation release

- Implementation commit `ba44c7e` stabilized the map controls and responsive
  layout, added candidate five-metric contracts and reconstructable output
  metadata, strengthened dataset/version read gates, and added identity-review
  sampling and public quality status.
- Tagged documentation commit `b1974d2` records `v3.0.5-alpha`. GitHub Actions
  run
  [33191858046](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33191858046)
  passed frontend, PostgreSQL migration/drift/ingestion/API, and container jobs.
- At release, Railway operated the bounded `hep-th-v1` path, but all five
  scientific metric layers remained experimental and jointly withheld.
  Canonical institution/affiliation evidence, citation cohorts, reviewed field
  mappings, six-year history, independent identity validation, and longer-term
  operational evidence were still incomplete.

## Historical constraints carried forward

- Existing release tags are immutable provenance and must not be moved.
- Synthetic, pilot, fixture-live, and provider-backed live datasets remain
  isolated.
- Missing evidence is not zero, and production status requires operated
  evidence rather than deployment-ready code.
- Public scientific metrics remain subject to the exact-five Joint Activation
  Gate; no historical milestone authorized partial activation.
