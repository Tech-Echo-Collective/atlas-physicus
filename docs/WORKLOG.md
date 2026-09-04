# Physics Atlas recent worklog

Keep this file to recent active milestones. Completed older detail is archived
in [`archive/`](archive/), while [`HISTORY_SUMMARY.md`](HISTORY_SUMMARY.md)
provides the compact cross-release chronology. Durable policy belongs in
[`DECISIONS.md`](DECISIONS.md), current facts in
[`PROJECT_STATE.md`](PROJECT_STATE.md), and exact measurements in validation
reports.

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
