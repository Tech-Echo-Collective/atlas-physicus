# Automatic certification validation — 2026-09-05

Baseline: source `4cdf667`, Web `bf39f192`. Scope: explicit owner authorization
to remove mandatory human review and resolve remaining launch blockers without
relaxing scientific standards. PA-054 records the change; the earlier launch
NO-GO remains an accurate historical report, not the current review requirement.

## Delivered

- Versioned evidence-derived field, explicit date-basis and paper-native identity
  assessments. Unsupported/partial/conflicting evidence remains explicit.
- Typed field decisions are bound to their exact consumed values and admitted
  by existing coverage/source-year/metric boundaries. An Activity fixture using
  automatic field decisions still produces raw value 30; altered shares fail.
- Exact fixed acquisition-plan derivation, complete metric-window population
  derivation and frozen ontology category enumeration; no fake reviewers.
- Single-response citation receipts preserve compact source identity, hashes,
  explicit date basis, counts, population membership and actual measurement time.
  The existing mixed-earliest-date and default-document-type conveniences are
  not accepted as scientific facts. This changes the new adapter, not old source
  records. One complete response may cover up to six years/1,000 records; separate
  responses never acquire a fabricated common cutoff.
- Automatic normalization includes every represented peer from the same certified
  source window, including missing raw results. The 30-eligible-peer rule remains.
- Web `63fc454eddcbe326c4b51217f8e6fa709a1d6bf8` removes automatic public fixture
  fallback and repairs a root TypeScript command that checked an empty reference
  project rather than both child projects. The source submodule remains `21bfcdb8`.

No threshold, metric formula, attribution, ontology weights, release tag,
production acquisition scope or legacy evidence was changed. New evidence
variants preserve existing manual contracts and historical serialized hashes.
These tests use explicit fixtures; they do not create live scientific scores.

## Primary-source and bounded live checks

Method choices and references are in [automatic certification](../automatic-certification.md).
One in-memory INSPIRE capability check on record `451647` observed raw 22,528 /
non-self 22,471 counts. This is API capability evidence, not an activation cohort.

At **13:03:19 UTC**, an independent `size=1`, ID-only query returned:

```text
document_type:article and subject:"Condensed Matter"
and date >= 2020-01-01 and date <= 2022-12-31
total = 16,815; next page present; response bytes = 2,496
```

No other pages from that query were fetched or retained. This proves the declared
query exceeds the single-response bound, not the number of certified papers.
No historical replay or provider mirror was created.

At **13:06 UTC**: API and database `ok`; INSPIRE/arXiv healthy with zero consecutive
failures; public-origin CORS correct; exposed metric observations **0**. Public
root HTTP 200 and deep Physics/year route app HTML HTTP 404 match the existing
Pages fallback. Browser execution of the full exploration flow was not repeated;
do not label real five-layer/timeline/composite regression passed.

## Validation

- **254 focused backend tests passed**: new automatic contracts, exact admission,
  populations, normalization, five existing metrics, Joint Gate/publication gate,
  fields, attribution, identity, connectors, API and reference-seed compatibility.
- Full backend Ruff lint/format: **150 files pass**. Strict mypy: **89 source files
  pass**. One existing Starlette/httpx deprecation warning is non-blocking; no
  unrelated dependency upgrade was made.
- Web: both TypeScript projects, lint, **16 tests**, production API build pass.
  [Pages build/deployment 33967823884](https://github.com/Tech-Echo-Collective/Physics-Atlas-Web/actions/runs/33967823884)
  completed successfully for `63fc454`. No source pin or domain migration.
- Source CI is checked separately after the validated source commit is pushed;
  local test success is not described as remote CI success in this receipt.

## Remaining blockers — no launch claimed

Mandatory human review is no longer policy. The following are **not** supplied
by a new rule name or passing fixture tests:

1. Complete transport-bound date/researcher **calculator admission**, complete
   canonical source years and sufficiently covered real populations. Current
   date/researcher assessments remain record-level only.
2. Real comparable Impact populations. The inspected three-year query needs
   more than 1,000 records; exact common-cutoff evidence requires an actual
   provider snapshot or a separately explicit measurement-session policy.
   Current counts cannot reconstruct citations known at an earlier date.
3. The unchanged ≥50 reference-paper and ≥30 eligible-normalization-peer minima,
   three-year metric/six-year Momentum windows, and existing coverage thresholds.
4. Broad Physics Diversity and domain aggregation cannot be manufactured from
   a specialty slice. The current domain aggregate requires ≥15/16 eligible leaf
   observations. Automatic leaf-internal Diversity lacks a frozen subfield catalog;
   no category denominator is silently reduced.
5. A producer that derives exact-five activation evidence and exports the complete
   compact v1 dataset with current profile/search relationships. Production remains
   `NoFormulaMetricRecalculator`; the historical pilot exporter is not repurposed.

All five public observations remain zero. No five-layer, historical timeline or
user-composite scientific activation success is claimed. Full Physics load and
v3.1 remain out of scope; legacy storage is not a launch dependency.

## Local cleanup

All task-created test/build/cache files used one directory:
`/private/tmp/atlas-auto-certification.IhRawZ`. No raw provider response or Atlas
dataset was saved locally. Bytecode and pytest cache writes were disabled;
Vite output/cache, mypy/Ruff, Node compile cache and test databases were isolated.

Highest observed retained temporary total: **55,433,643 bytes** (59 files), below
2 GB; this is a sampled retained-size measurement, not a continuously measured
instantaneous high-water mark. All **55,433,643 bytes** and the directory were
removed after validation. The original legacy evidence was not read, expanded,
reorganized or deleted. No unapproved task-created scientific/build leftovers
remain. Source, tests and concise documentation are the only persistent additions.

**LOCAL BUILD CLEANUP = PASS.**
