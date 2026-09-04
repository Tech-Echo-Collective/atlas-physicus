# Archived worklog: Metric System v1 through canonical replay

This archive compresses the detailed worklog from 2026-08-30 through the
2026-08-31 bounded canonical replay. Current operating facts belong in
[`PROJECT_STATE.md`](../PROJECT_STATE.md), durable policy in
[`DECISIONS.md`](../DECISIONS.md), and exact measurements in the linked
validation reports.

## Metric System v1 scientific foundation

- Commit `fe752f0` implemented Fractional Attribution v1, the Physics Field
  Ontology v1 and provider mappings, the exact five raw metrics and their
  dimension-specific normalization, field-balanced Physics aggregation,
  reconstructable provenance, reference-ecosystem checks, and the fail-closed
  Joint Activation Gate.
- Local validation passed 172 backend tests, 130 frontend tests, seven pipeline
  tests, strict Python/TypeScript checks, lint, build, and migration checks.
  GitHub Actions run
  [33300307090](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33300307090)
  passed. No live metric observation was created.

## Bounded activation diagnostic

- The production `hep-th-v1` snapshot contained 177 canonical papers, 475
  researchers, 501 authorships, zero canonical institutions/profile
  affiliations, and zero metric observations.
- The diagnostic corrected four measurement defects: paper-time coverage now
  uses `PaperAffiliation`, collaboration coverage is not inferred merely from
  authorship, researcher Connectivity does not require geographic attribution,
  and INSPIRE date normalization can use valid `earliest_date` evidence.
- Focused validation passed 64 tests, Ruff, and strict mypy. The gate remained
  withheld because canonical institutions, comparable citations, reviewed
  fields, historical years, and eligible cohorts were absent.

## 2020–2025 raw acquisition

- Commit `d3b5cc8` froze cross-provider affiliation precedence and per-paper
  field-mass conservation, then added the database-free resumable acquisition
  boundary.
- The staging run captured 43,439 INSPIRE and 44,773 arXiv occurrences across
  628 checksum-verified pages and 12 exact provider/year partitions. Manifest:
  `e3dba5492e0dee3fb0b359cd90acd9cc07991e83b89cb6f16c49b498c4e65536`.
- A provider interruption resumed from the exact arXiv checkpoint without
  refetching completed pages. The run created no canonical or production rows.
- Backend validation passed 209 tests; frontend validation passed 130 tests and
  seven pipeline tests. GitHub Actions run
  [33309487273](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33309487273)
  passed.

## Dedicated hostname preparation

- A short-lived preparation branch documented the intended
  `https://atlas.techecho.org/` migration and transition CORS origins. It did
  not claim DNS, Pages, certificate, redirect, or deployment completion.
- This operational side task did not change scientific scope or metric state.

## Canonical replay and authority projection

- Commit `b20e3d9` replayed the immutable acquisition into 47,726 paper
  components, 142,309 researcher appearances, 183,247 paper-time affiliation
  shares, 47,726 attribution/field ledgers, and 43,439 citation observations.
  Replay bundle:
  `d125a0861df03c5e1e7e20202db06f7d2506e0e8e9fb3fca732e7208f4349d82`.
- Exact-ID ROR acquisition covered 2,131 targets. The strict PA-035 projection
  resolved 16,689.396051 of 47,726 paper mass (34.969191%) and conserved all
  resolved and withheld mass. Affiliation evidence covered 89.263140%.
- Reviewed field coverage and comparable citation coverage remained zero; no
  canonical year or Momentum window was certified. All five metrics remained
  jointly withheld and metric observations remained zero.
- Full local validation passed 258 backend tests, 130 frontend tests, seven
  pipeline tests, strict type/lint/build/migration checks, and artifact
  checksum/conservation verification. GitHub Actions run
  [33368874387](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33368874387)
  passed.

Exact evidence remains in:

- [`metric-system-v1-hep-th-2020-2025-dry-run.md`](../validation/metric-system-v1-hep-th-2020-2025-dry-run.md)
- [`metric-system-v1-hep-th-2020-2025-canonical-replay.md`](../validation/metric-system-v1-hep-th-2020-2025-canonical-replay.md)

## Boundaries carried forward

- The public production scope remained `hep-th-v1`; staging evidence never
  altered production history or cursors.
- Provider agreement did not become human review, missing evidence did not
  become zero, and no field-conditioned trial activated public metrics.
- The external raw/replay payloads were not stored in Git or GitHub artifacts.
  Their committed reports and checksums preserve the historical result, but
  later row-level enrichment requires restoration of those payloads or a fresh,
  separately versioned paired capture.
