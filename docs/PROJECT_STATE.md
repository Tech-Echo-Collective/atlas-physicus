# Atlas Physica project state

Last reviewed: 2026-09-05

This is the canonical snapshot of the project's current operating and
scientific state. Read it with [durable decisions](DECISIONS.md), the
[roadmap](roadmap.md), the compact [history](HISTORY_SUMMARY.md), and the
recent [worklog](WORKLOG.md). Exact scientific measurements belong in the
linked validation reports rather than being repeated throughout the project
documentation.

## Release and scope

- Canonical public/product name: **Atlas Physica**, formerly Physics Atlas
  (PA-047, 2026-09-05). Atlas Physica is developed and maintained by Tech Echo
  Collective. Repository, package, schema, service, environment, provenance,
  URL/domain, and release identifiers remain unchanged.
- Current release: `v3.0.5-alpha`; the annotated tag remains at `b1974d2`.
- Source branch: `main` in `Tech-Echo-Collective/Physics-Atlas`.
- The active phase is post-release **Stabilization & Scientific Validation**
  for Metric System v1. It does not change the release tag, begin v3.1, or
  authorize a Full Physics load.
- Production acquisition remains `hep-th-v1`. Condensed Matter work is an
  isolated, staging-only validation scope; it is not a production source or a
  broad-Physics activation boundary.
- Public live observations for Activity, Impact, Connectivity, Diversity, and
  Momentum remain jointly withheld. Missing evidence is not displayed as
  zero, and no partial activation is allowed.

## Operated system

### Public Atlas

- React, TypeScript, Vite, MapLibre GL JS, and Zod implement the map-first
  Physics domain → field → time → world → country → institution → researcher
  exploration path.
- The normal public source is `APIRepository`. Synthetic fixtures and the
  historical pilot remain isolated internal sources for tests,
  reproducibility, and explicit fallback only.
- Repository and dataset-kind checks prevent live/static data mixing.
  Missing observations render as a neutral state.
- The public Pages project is
  `Tech-Echo-Collective/Physics-Atlas-Web`. Its configured backend is
  <https://physics-atlas-api-production.up.railway.app/api>.
- `https://atlas.techecho.org/` is the canonical target hostname. The legacy
  Pages/inherited origins remain in transition CORS until DNS, Pages custom
  domain, certificate, redirects, and client behavior are separately verified.

### Backend and evidence platform

- FastAPI, PostgreSQL, SQLAlchemy, and Alembic provide typed, paginated Atlas,
  profile, search, provenance, update-status, metric, and health APIs.
- Canonical entities, temporal relationships, raw provider records, immutable
  source snapshots, authority and review decisions, cursors, update lineage,
  paper-time attribution, and release manifests are persisted with explicit
  provenance.
- The update worker is bounded, resumable, idempotent, and scope-aware.
  INSPIRE and arXiv are the scheduled `hep-th-v1` sources; ROR, ORCID, and
  Crossref remain exact known-identifier enrichers rather than discovery
  crawlers.
- `NoFormulaMetricRecalculator` remains the production recalculation path. It
  plans affected partitions but does not fabricate or publish scientific
  scores.
- Staging-only acquisition and file replay can preserve content-addressed raw
  pages and deterministically materialize papers, authors, dates,
  affiliations, institutions, citations, field ledgers, attribution, and
  review status without touching production cursors or history.

## Production health

Read-only verification on 2026-09-05 at `02:00:44Z` found:

- runtime `3.0.5-alpha` and database health both healthy;
- INSPIRE and arXiv healthy with zero consecutive failures and September 4
  latest successes;
- metric recalculation idle;
- 440 unresolved entities remain recorded for review; the one resource-check
  failure is a DOI resolver HTTP 404, independently confirmed and unrelated to
  payload storage. No monitor fix or scientific-data correction is justified;
  see the [diagnosis](validation/staging-dual-read-2026-09-05.md#existing-resource-check-failure);
- zero public metric observations; expected `https://atlas.techecho.org`
  CORS was separately verified at `00:16:29Z`.

Railway production data, update history, and release tags have not been
modified by the current validation work. Backup/restore evidence, restart and
incident rehearsal, rate protection, longer-running monitoring, and alerting
remain operator responsibilities.

## Metric System v1

- The system consists of exactly Activity, Impact, Connectivity, Diversity,
  and Momentum.
- `fractional-attribution-v1` conserves one paper unit and leaves unresolved
  mass explicit. Paper-time evidence follows paper-native/INSPIRE → arXiv →
  dated ORCID precedence; current profiles cannot overwrite history.
- `physics-field-ontology-v1` and `provider-field-mapping-v1` preserve provider
  categories and roles. Each paper conserves exactly one unit across mapped
  field weights plus explicit unmapped mass.
- Raw calculators, dimension-specific normalization, and
  `physics-field-balanced-coverage-aware-v1` Physics aggregation are
  deterministic and reconstructable from versioned evidence.
- `metric-validation-thresholds-v1` and the exact-five Joint Activation Gate
  require sufficient attribution, reviewed mappings, comparable citations,
  certified history, eligible cohorts, normalization sanity, provenance, and
  deterministic reproduction.
- Joint evidence must identify its acquisition boundary. Public activation
  requires reviewed `broad-physics` evidence; `hep-th-v1`, the Condensed Matter
  trial, and an unreviewed union of specialty trials remain
  `field-conditioned` under PA-040.
- Passing implementation tests or a specialty-field sanity check is not
  scientific activation. A single-field `hep-th-v1` Diversity result cannot
  validate Physics-wide Diversity.

Canonical specifications are [Scientific Attribution](scientific-attribution.md),
[Field Ontology](field-ontology.md), [Metric System v1](metrics-spec-v1.md), and
[Metric Validation](metric-validation.md).

## Scientific certification and capacity foundation

The current source adds `scientific-evidence-certification-v1` between
canonicalization and metric calculation. It binds per-dimension decisions,
full coverage denominators, exact reviewed populations, source years, metric
windows, citation cohorts, and preserved formula inputs. Institution evidence
uses direct ROR or an explicit reviewed candidate; field/date/researcher
approvals are not inferred from provider presence. Typed content hashes prove
reconstruction, while reviewer authority and semantic completeness remain
responsibilities of the operating review process.

The fresh official paired capture covers only 2020-01-13–19: 635 provider
occurrences become 474 canonical components, with 14 shared across tracks.
Record-level affiliation, institution, citation-observation, identity,
conservation, and provenance decisions now have nonzero certified coverage.
However, reviewed dates, researcher identities, field ledgers, metric-eligible
citation cohorts, certified years, and metric windows remain zero. Exact
fractions, retained manifests, and replay limitations belong in the
[certification report](validation/scientific-evidence-certification-2026-09-05.md).
The small week's results must not be reported as six-year coverage gains.

The retained Condensed Matter source was replayed into a new immutable bundle
to correct 1,667 institution anchors mislabeled with the hep-th scope; all
seven other data artifact hashes are unchanged. The final overlay retains
2,766,760 decisions: paper identity is 99.726565% certified and conservation/
provenance 100%, but affiliation, institution, field, date, researcher, and
comparable-citation certification remain zero. The corrected anchors now need
review rather than being scope-conflicted. Legacy fractional affiliation
presence remains 25.407165%; this is not the strict certification measure.

`normalized-atlas-scale-v1` adds a separate 0–100 presentation proof for all
five unchanged raw metrics. It binds exact reviewed normalization populations,
fitted parameters, cutoff, coverage, and missing reasons. These certification
and Atlas artifacts are staging-only; production has no deployed certification
schema and still publishes zero live metric observations.

The September 5 read-only audit measured a 306.8 MB database and 482.5 MB volume
use on actual 4.364 GiB capacity. Raw snapshot/record relations occupy 52.31%
of public relations, but required normalized attributes/metadata are not cold.
A local 474-paper/9,999-decision PostgreSQL prototype preserves exact decisions
while reducing hypothetical expanded certification storage by 83.45%, from
391.626 to 64.810 MB per 10k papers; this is not a whole-database saving.
The retained-layout estimate supports only an illustrative 5,616 total-paper
steady ceiling, not certified capacity. The **Storage Budget Gate remains
WITHHELD**: representative final-state rows, target population, peak usage and
isolated restore are unvalidated. No production payload was migrated or deleted.
Full Physics still requires both gates. See the
[bounded storage investigation](validation/storage-amplification-2026-09-05.md)
and the historical [initial sizing](validation/storage-sizing-2026-09-04.md).

The subsequent one-batch [payload-reference recovery pilot](validation/payload-reference-recovery-2026-09-05.md)
restores all existing paired source/authority bytes and reproduces the unchanged
certification manifest and ten artifacts. A local current-layout replica retains
all hot metadata/indexes while reducing its raw/snapshot component from 14.156
to 6.373 MB (54.98%); sampled scaling is 298.645 to 134.459 MB per 10k papers,
not whole-Atlas storage or approved capacity. Production still stores inline
payloads. The subsequent [staging dual-read rehearsal](validation/staging-dual-read-2026-09-05.md)
integrates 449 original-byte catalog rows in a private PostgreSQL schema.
Inline, checksum-verified reference, and explicit rollback paths reproduce all
ten scientific artifacts and 9,999 decisions exactly. Seven fault injections
block before processing with rows/checkpoints unchanged. Both representations
are retained; this is not a production ORM migration or measured storage saving.
Durable independent restore and production-compatible reader/schema review
remain required before any inline retirement.

## Track A — `hep-th-v1` evidence

The immutable 2026-08-31 source and canonical-replay reports remain the source
of truth:

- source manifest `e3dba5492e0dee3fb0b359cd90acd9cc07991e83b89cb6f16c49b498c4e65536`;
- replay bundle `d125a0861df03c5e1e7e20202db06f7d2506e0e8e9fb3fca732e7208f4349d82`;
- institution-resolution manifest
  `4e0f58bdc4d44836e013a2b311998858e4a1894bcecd06d617e2cfa5211ece38`;
- 88,212 provider occurrences and 47,726 paper components;
- paper-time affiliation evidence: 42,601.726004 / 47,726 = 89.263140%;
- activation-eligible canonical institution mass: 16,689.396051 / 47,726 =
  34.969191%;
- common-cutoff comparable citations: 0 / 47,726;
- reviewed field ledgers: 0 / 47,726;
- certified canonical years: none; both Momentum windows unready;
- 472 paper components need merge review, 11,143 researcher appearances lack
  authority, 61 authority conflicts remain, and five author projections were
  not uniquely materialized;
- all measured attribution, institution, and field-mass conservation checks
  passed; metric observations created: zero.

The original external raw/replay payloads are no longer available, so those
row-level results cannot be enriched or recomputed from Git alone. A new run
must be a fresh, separately versioned paired capture rather than mixing current
provider data with the historical denominator. Validated staging tooling now
supports exact INSPIRE institution-to-ROR evidence and exact arXiv-ID
paper-affiliation enrichment while retaining precedence and conservation, but
no new evidence delta is claimed.

Against the unchanged thresholds, the historical replay remains short by at
least 351.673996 paper units of affiliation evidence and 28,650.303949 paper
units of activation-eligible institution evidence. Citation comparability and
reviewed field attribution each require at least 42,954 components, and six
canonical years, eligible Impact cohorts, and both Momentum windows still need
certification.

Exact evidence:

- [raw dry run](validation/metric-system-v1-hep-th-2020-2025-dry-run.md)
- [canonical replay](validation/metric-system-v1-hep-th-2020-2025-canonical-replay.md)
- [bounded improvement readiness](validation/metric-system-v1-hep-th-evidence-improvement-readiness.md)

## Track B — bounded Condensed Matter validation

The isolated, field-conditioned `cond-mat-validation-v1` trial completed its
staging-only 2020–2025 acquisition and deterministic replay without touching
production:

- 160,294 source records—32,198 INSPIRE and 128,096 arXiv—were preserved across
  30 complete provider partitions and replayed into 129,464 paper components;
- source manifest
  `484880ef2fd03163b393fff2a38a1901340550d5423da058c43f5210c9ed0384`,
  replay bundle
  `26c51e77b696e2d4d3636074107f0751be9289b9e95f62f837abd8b106f8376f`,
  and content-addressed report
  `8d9b04e2616ee8450b7aef919f3dfded2bcb8004c9f4c031fb6aade96f3409cd`
  reproduced exactly across two complete replays;
- paper-time affiliation coverage is 32,893.131711 / 129,464 = 25.407165%,
  short by 83,624.468289 paper units; 48 paper ledgers have non-unique author
  projections;
- canonical-institution coverage is not measurable, rather than zero: 34,541
  direct ROR alignments across 1,667 provider authority anchors were not
  promoted to canonical institutions;
- reviewed field attribution and common-cutoff comparable citations are each
  0 / 129,464, short by 116,518 components apiece; 55,228 field ledgers retain
  explicit unmapped mass;
- affiliation, attribution, and field-weight conservation all pass with zero
  failures; no missing or unresolved mass was reassigned;
- raw provider query windows are complete for all six years, but certified
  canonical metric years remain 0 / 6, mature Impact cohorts remain zero, and
  both Momentum windows remain unready;
- unresolved evidence includes 510,576 shares with no affiliation evidence,
  189,863 unresolved shares, 222 ambiguous shares, 516,108 researcher
  appearances without an authority identifier, 135,945 with unreviewed
  authority evidence, two with conflicting identifiers, and 354 paper
  components requiring identity review.

Activity, Impact, Connectivity, Diversity, and Momentum are all **withheld**.
No eligible normalization cohort was materialized, and no metric observation
was calculated or published. Exact evidence and limitations are in the
[Condensed Matter validation report](validation/metric-system-v1-cond-mat-2020-2025-validation.md).

## Joint activation state

The exact current Joint evaluator was independently rerun on each final paired
scope and returns **WITHHELD** for all five metrics, with eleven explicit
scientific blockers. Its diagnostic reproduces byte-for-byte. See the
[current certification report](validation/scientific-evidence-certification-2026-09-05.md)
for the exact inputs, output digest, and distinction between algorithm tests,
artifact reproduction, and missing metric-system reproduction.

The historical comparison-only exact-five assessment also remains **WITHHELD** for
Activity, Impact, Connectivity, Diversity, and Momentum. It keeps the two
specialty tracks separate—no denominators were averaged and no combined data
source was invented. Both tracks have 0% comparable-citation and reviewed-field
coverage, 0 / 6 certified canonical years, and 0 / 2 ready Momentum windows;
their distinct affiliation and institution deficits are recorded above.

The comparison remains field-conditioned, has no reviewed broad-Physics
Diversity evidence, no eligible normalization cohorts, and incomplete
reconstruction provenance. It therefore cannot satisfy PA-040 even if a
specialty-field internal check later passes. Public metric observations remain
zero, no activation manifest was prepared, and Full Physics loading is **not
authorized**. The exact gate input and output are preserved in the
[dual-track Joint Activation assessment](validation/metric-system-v1-dual-track-joint-activation.md).

## Repository validation state

- The staging dual-read/rollback proof passes 130 focused backend tests,
  focused Ruff lint/format and strict mypy (80 source files). Native private
  PostgreSQL recovery/certification equivalence and all seven injected failures
  pass. Current Atlas Physica frontend typecheck/lint, 132 Vitest tests, seven
  pipeline tests and production build pass. See the
  [staging report](validation/staging-dual-read-2026-09-05.md) for scope and
  proof limitations. Publication/CI results are recorded after pushing.
- The one-batch payload-reference pilot passes 123 focused tests (2.82s), Ruff
  over 11 changed/storage files, and strict mypy over 79 source files. Native
  PostgreSQL SQL-to-cold recovery verifies all 3,179 paper/author-fragment
  locators and unchanged hot metadata; independent restored sources reproduce
  all certification artifacts exactly. Commit `7c1f34c` is pushed and passed
  [CI 33936700018](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33936700018)
  (frontend, backend/PostgreSQL and containers). Exact measurements
  and limitations are in the [payload recovery report](validation/payload-reference-recovery-2026-09-05.md).
- The bounded storage investigation passes all 398 backend tests, strict mypy
  (78 source files), and Ruff format/lint (119 files, including tools). Native
  PostgreSQL SQL/archive recovery and bounded local provenance verification
  pass. Commit `c88f9b9` is pushed and passed
  [CI 33935510006](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33935510006)
  (frontend, backend/PostgreSQL and containers). No frontend code changed. Exact results and
  limits are in the [storage report](validation/storage-amplification-2026-09-05.md).
- Certification/capacity result commit `be5e304` is pushed to `main` and passed
  [CI 33932839622](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33932839622),
  including frontend, backend/PostgreSQL, and containerized API/worker checks.
  Frontend type checking, lint, 130 Vitest tests,
  seven pipeline tests, and production build pass. Backend Ruff format/lint,
  strict mypy, and all 376 pytest tests pass with one existing dependency
  deprecation warning and the existing non-blocking frontend chunk-size warning.
- The bounded dual-track result is commit `5e3ba1f`; it passed GitHub Actions
  run [33884017132](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33884017132),
  including frontend, backend/PostgreSQL, and containerized API/worker jobs.
- Post-push production checks confirm healthy service/database status, expected
  public-origin CORS, healthy INSPIRE/arXiv cursors, and zero public metric
  observations. Existing release tags remain unchanged.

## Immediate next action

Perform only reviewed evidence work for canonical dates, researcher identities, fields,
institution targets/rollups, common-cutoff cohort populations, and complete
historical windows. The smallest storage action is to review a one-batch
production-compatible schema/reader plan and durable archive retention plus
independent restore requirements, building on the completed private staging
dual-read/rollback proof. Keep production inline data until separately approved
archive write/read-back, transactional checkpoint, restore, and rollback checks
pass. A later representative final-schema measurement is still required. Both
gates remain withheld; Full Physics loading and v3.1 remain unauthorized.
