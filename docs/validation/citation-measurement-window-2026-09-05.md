# Citation measurement-window validation — 2026-09-05

Baseline: source `b7d532ab91dbf50d17663c61940230ed2e63aaf7`;
[baseline CI 33968046386](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33968046386)
passed. Web remains `63fc454`, with green Pages deployment and unchanged source
pin `21bfcdb8`. The owner explicitly authorized PA-055 after the preceding
single-response limitation was reported. This report supersedes that *current*
limitation without rewriting the earlier validation receipt.

## Implemented method

- Freeze exact source/provider identities from independently certified source
  years before measuring citations. Unsupported provider identities remain
  missing in scientific denominators; a query result does not certify itself.
- Retain compact record facts and exact requested/received times. Prefer explicit
  ID batches and require exact complete frozen membership. Missing, duplicate,
  unexpected, conflicting or drifting records fail closed.
- Use `citation-measurement-window-v1` and
  `non-self-citation-measurement-window-v1`. Maximum session duration is 30 minutes
  as an operational bound—not a validated drift tolerance, simultaneity claim,
  provider snapshot, or historical as-of record.
- Bind three-year Impact windows to the same frozen canonical projection digests.
  Pre-measurement source-year authority and later citation-coverage evaluation
  have distinct certificates/times; changing an evaluation horizon does not
  rewrite when source evidence was acquired.
- Reuse existing non-self citation, per-observation 24-month maturity, ≥50-paper
  reference cohorts and MNCS/PP(top 10%) arithmetic. Retain missing versus zero.
- Isolate normalization and domain aggregation by exact measurement session and
  interval. Session presentation exposes no singular citation cutoff; the
  calculation retains its separately identified dataset evaluation horizon.
- Preserve old single-cutoff contracts, historical hashes and the exact-five
  activation gate. No public metric is enabled by a rule-name string alone.

Method and primary sources: [automatic certification](../automatic-certification.md#versioned-measurement-window-pa-055).

## Scope and limits

All validation uses bounded explicit fixtures, not a scientific corpus or new
provider acquisition. No Railway write, production migration, raw mirror,
historical replay, release-tag movement, data cleanup or Full Physics load.
No new live count/coverage gain is claimed. The last successful live health
receipt remains 13:06 UTC in the preceding report; failed local permission-check
timeouts do not indicate provider or production failure.

This completes one authorized citation semantic boundary, not the launch. Real
complete-year authority, source-bound date/identity admission, sufficiently
covered real populations, exact-five validation, and the compact v1 dataset
producer still remain. Counts observed now cannot reproduce citations known in
past years. Compact observed values and provenance must accompany any future
published calculation; hashes alone cannot recover mutable past values.

## Validation and cleanup

- **304 focused backend tests pass**: source-bound session integration, capture
  integrity, normalization/aggregation isolation, automatic and legacy evidence,
  all five existing metrics, attribution/fields, Joint/publication gates, API,
  identity, connectors and reference compatibility. The existing Starlette/httpx
  deprecation warning remains non-blocking; no dependency upgrade was made.
- The main integration fixture has 150 synthetic papers, 50 in each of 2020–2022,
  two exact-ID batches spanning UTC midnight, three certified cohorts and a later
  evaluation horizon. It reproduces MNCS **1.0** and PP(top 10%) **0.1**, not live
  scientific scores. Nine cases include insufficient/missing evidence, mutation,
  stale horizons and old-policy rejection. No scientific validator was bypassed.
- Separate tests reject cross-session normalization/aggregation, omitted/duplicate
  identities, invalid request chains/timestamps and oversized responses before
  parsing. Two 15-peer sessions cannot pool to meet the existing 30-peer minimum.
- Full backend lint and formatting pass (**160 files**); strict typing passes
  (**91 source files**); whitespace and **103 local documentation links** pass.
  Full remote CI is checked after the source commit is pushed; this local receipt
  does not by itself assert a remote run completed.

The same explicit scratch location from the earlier phase was re-created only
for this approved follow-up: `/private/tmp/atlas-auto-certification.IhRawZ`.
All fixture databases, test outputs and tool caches stayed there; bytecode and
pytest cache writes were disabled. No raw provider payload or generated Atlas
dataset was retained. Final/highest sampled temporary size was **73,489,482 bytes**
(80 files), well below 2 GB; this is a sampled retained-size measurement, not a
continuous instantaneous peak. All those bytes and the directory were removed
after the final passing checks. Together with the earlier phase's cleanup,
**128,923,125 temporary bytes** were removed across the two separate lifetimes.
No legacy evidence was touched. Only source, tests and concise docs persist.

**LOCAL BUILD CLEANUP = PASS; unapproved local scientific/build leftovers = 0.**
