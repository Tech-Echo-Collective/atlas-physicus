# Physics Atlas recent worklog

Keep this file to recent active milestones. Completed older detail is archived
in [`archive/`](archive/), while [`HISTORY_SUMMARY.md`](HISTORY_SUMMARY.md)
provides the compact cross-release chronology. Durable policy belongs in
[`DECISIONS.md`](DECISIONS.md), current facts in
[`PROJECT_STATE.md`](PROJECT_STATE.md), and exact measurements in validation
reports.

## 2026-09-05 — One-batch payload-reference recovery pilot

- Reused only the existing paired week: eight provider pages, 635 occurrences,
  474 canonical papers and retained exact-authority enrichment. No acquisition,
  broad replay, production migration/write, tag change or metric activation.
- Added a bounded local payload envelope/reference with separate original and
  compressed hashes, exact acquisition metadata and fail-closed recovery.
  All 449 source/authority/manifest files restore exactly; unchanged parsers,
  canonicalization and certification reproduce the original manifest and all
  ten artifacts, including 9,999 decisions. All 1,033 provenance links resolve;
  certification states, conservation, missing semantics and eligibility remain
  unchanged, with zero certified years/windows or metric observations created.
- Native local PostgreSQL compares a staging current-layout replica—not
  exported production rows—with 3,179 raw rows/four snapshots. All hot metadata
  and indexes remain; shared page references reduce the raw/snapshot component
  from 14.156 to 6.373 MB, 54.98%. Conditional production savings are not measured
  reclamation or Full Physics capacity. Both gates remain withheld; the next
  action is bounded additive dual-read/independent-restore integration, not
  production payload retirement. Exact figures, artifact hashes, migration and
  rollback requirements are in the [pilot report](validation/payload-reference-recovery-2026-09-05.md).
- All 123 focused tests pass (2.82s); Ruff passes 11 changed/storage files and
  strict mypy passes 79 source files. Native SQL-to-cold recovery independently
  verifies all 3,179 paper/author-fragment locators. At `01:34:34Z`, production
  API/database/providers remain healthy with zero provider failure streaks and
  zero public observations; one existing resource-check failure remains.
  Pilot commit `7c1f34c` is pushed and passed
  [CI 33936700018](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33936700018),
  including frontend, backend/PostgreSQL and containerized API/worker checks.
  The private benchmark server is stopped; production inline data is unchanged.

## 2026-09-05 — Bounded storage amplification investigation

- Read-only PostgreSQL-native accounting separates heap, auxiliary forks,
  TOAST and indexes. Raw payload duplication, search/authority fan-out and
  repeated affiliation/field provenance dominate; current hot attributes and
  historical audit payloads must not be treated as interchangeable.
- Reused only the existing 474-paper/9,999-decision sample in private local
  PostgreSQL. Complete SQL/archive recovery preserves decisions and the typed
  calculator boundary; compact certification uses 3.072 MB versus hypothetical
  expanded 18.563 MB, including dictionaries and indexes. This is an 83.45%
  component saving, not measured production compaction.
- Current-state-plus-compact-certification capacity remains insufficient for
  10k papers with required headroom. The illustrative steady ceiling is 5,616
  total papers, not approved safe capacity; both gates remain withheld.
  No acquisition, broad replay, production migration, history deletion, metric
  activation or tag change occurred. Exact bytes, hashes, limitations and the
  additive dual-read pilot plan are in the
  [storage report](validation/storage-amplification-2026-09-05.md).
- Exact SQL/archive recovery plus 1,033 unique provenance links pass with zero
  unresolved references and 447 local manifest files verified. All 398 backend
  tests pass (9.28s), strict mypy passes 78 source files, and Ruff format/lint
  passes 119 files including tools; one existing dependency warning remains.
  At `00:56:21Z`, production API/database/providers remain healthy with zero
  provider failure streaks; one resource-check failure remains. No frontend
  change was made. Implementation/result commit `c88f9b9` is pushed and passed
  [CI 33935510006](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33935510006),
  including frontend checks/build, backend PostgreSQL migrations/ingestion/API,
  and containerized API/worker checks. The isolated benchmark server is stopped.

## 2026-09-05 — Scientific certification, paired evidence, and capacity

- Implemented explicit certification states, per-kind formula-input binding,
  exact reviewed eligibility and normalization populations, citation cohorts,
  complete-year/window proofs, and the separate 0–100 Atlas Scale. Raw Metric
  System v1 formulas and thresholds are unchanged. Typed content attestations
  do not replace authenticated scientific/operator review (PA-046).
- Captured the closed week 2020-01-13–19 through official INSPIRE/arXiv paths
  for hep-th and Condensed Matter: 635 occurrences, 474 canonical components,
  14 shared components, and 9,999 retained decisions. Direct authority
  enrichment reaches 219 ROR records. Record-level certification is nonzero,
  but reviewed dates/identities/fields, metric-eligible citation cohorts,
  certified years/windows, and generated observations remain zero. Exact
  manifests and results are in the
  [certification report](validation/scientific-evidence-certification-2026-09-05.md).
- Preserved the removed-row hep-th baseline without claiming a new replay
  improvement. Offline Condensed Matter rematerialization corrects 1,667
  wrong-scope authority anchors while preserving seven other artifact hashes.
  The retained 2,766,760-decision certification stream still has zero eligible
  affiliation/institution/field/date/researcher/citation coverage; legacy
  fractional affiliation presence remains 25.407165%. Both exact paired Joint
  Gate executions return withheld; the diagnostic and all paired artifacts
  independently reproduce byte-for-byte.
- The read-only PostgreSQL audit found 306.5 MB database size on a 4.364 GiB
  volume, 499.1 MB used, and 52.35% of public relations occupied by duplicated
  raw evidence. Added a local content-addressed artifact-store abstraction and
  a separate Storage Budget Gate; measured sample, target population, final
  schema, and isolated restore requirements keep the gate withheld. See
  [storage sizing](validation/storage-sizing-2026-09-04.md).
- Frontend typecheck/lint, 130 Vitest tests, seven pipeline tests, and build
  pass. Backend Ruff format/lint, strict mypy, and 376 pytest tests pass with
  one existing dependency deprecation warning. Result commit `be5e304` is pushed
  to `main`; [CI 33932839622](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33932839622)
  passed frontend, backend/PostgreSQL, and container API/worker jobs. Read-only
  production checks on September 5 confirm healthy API/database/providers,
  expected Atlas CORS, and zero public observations. No production data,
  cursor, release tag, or Full Physics scope was changed.
- After the push, Railway health remained `ok` at `2026-09-05T00:24:27Z`,
  and the public metric endpoint still returned zero observations.

## 2026-09-04 — Bounded dual-field Metric System v1 validation

- **Scope:** Reuse the preserved 2020–2025 `hep-th-v1` replay as a theory-heavy
  stress test and run an isolated six-year Condensed Matter trial as the primary
  full-five-metric validation field. Do not write production history, begin
  Full Physics loading or v3.1, or partially activate metrics.
- **`hep-th-v1`:** The historical replay remains at 89.263140% paper-time
  affiliation coverage and 34.969191% activation-eligible institution
  coverage, with zero comparable common-cutoff citations, reviewed field
  ledgers, or certified years. Its removed external row artifacts prevent an
  honest same-capture enrichment, so the committed baseline is preserved and
  no improvement delta is claimed. Exact target-only institution/ROR and
  affiliation-enrichment tooling was added for a future fresh paired capture.
- **Integrity fixes:** Specialty scopes now remain field-conditioned despite a
  contradictory caller label; equal-rank resume evidence fails closed on
  content conflict; an empty institution target is a valid no-op; and every
  supplemental INSPIRE institution crosswalk is rederived from its
  checksum-bound raw snapshot before ROR identity is accepted.
- **Condensed Matter evidence:** The staging-only run preserved 160,294 source
  records in 30 complete partitions and replayed 129,464 paper components. Its
  source manifest is `484880ef2fd03163b393fff2a38a1901340550d5423da058c43f5210c9ed0384`;
  two complete replays reproduced bundle
  `26c51e77b696e2d4d3636074107f0751be9289b9e95f62f837abd8b106f8376f`
  and report
  `8d9b04e2616ee8450b7aef919f3dfded2bcb8004c9f4c031fb6aade96f3409cd`.
- **Coverage and conservation:** Paper-time affiliation is 25.407165%, short
  by 83,624.468289 paper units. Canonical-institution coverage is not
  measurable. Reviewed field attribution and common-cutoff citations are both
  0 / 129,464, each short by 116,518 components. All affiliation, attribution,
  and field-weight conservation checks pass; canonical years are 0 / 6 and
  ready Momentum windows are 0 / 2.
- **Readiness:** Activity, Impact, Connectivity, Diversity, and Momentum are
  all withheld. The comparison-only Joint Gate does not combine denominators
  and remains field-conditioned, without broad-Physics Diversity review,
  mature Impact cohorts, eligible normalization cohorts, or complete
  reconstruction provenance. Metric observations remain zero and Full Physics
  loading is not authorized. See the
  [Condensed Matter report](validation/metric-system-v1-cond-mat-2020-2025-validation.md)
  and [dual-track gate report](validation/metric-system-v1-dual-track-joint-activation.md).
- **Run fixes:** Exact quarterly arXiv partitions avoid the provider's 10,000
  offset boundary, and indexed merge evidence reduced the full replay to about
  three minutes while preserving every output byte. The integrity fixes above
  remain fail-closed and do not change metric science.
- **Production and validation:** Railway remains healthy and production stays
  `hep-th-v1`-only with zero public metric observations. Backend Ruff, strict
  mypy, and 284 pytest tests pass with one dependency deprecation warning;
  frontend TypeScript, lint, 130 Vitest tests, seven pipeline tests, and the
  production build pass with the existing non-blocking chunk-size warning.
- **Provenance and next action:** Result commit `5e3ba1f` is on `main` and
  GitHub Actions run
  [33884017132](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33884017132)
  passed its frontend, backend/PostgreSQL, and containerized API/worker jobs.
  A post-push read-only production check remained healthy with expected CORS,
  healthy provider cursors, and zero public metric observations. Existing
  release tags are unchanged. Next, scope only the reviewed institution,
  field, citation, cohort-date, and historical-certification evidence needed
  by the existing gate.

Older detail is preserved in:

- [`archive/worklog-through-v3.0.5-release.md`](archive/worklog-through-v3.0.5-release.md)
- [`archive/worklog-metric-system-v1-through-canonical-replay.md`](archive/worklog-metric-system-v1-through-canonical-replay.md)
