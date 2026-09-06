# Atlas Physicus project state

Last reviewed: 2026-09-06

This is the canonical snapshot of the project's current operating and
scientific state. Read it with [durable decisions](DECISIONS.md), the
[roadmap](roadmap.md), the compact [history](HISTORY_SUMMARY.md), and the
recent [worklog](WORKLOG.md). Exact scientific measurements belong in the
linked validation reports rather than being repeated throughout the project
documentation.

## Current task: minimum launch integration and actual evidence blockers

PA-054 removes mandatory human approval; PA-055 permits explicitly retrospective
citation measurement intervals. Neither removes unresolved source evidence or
scientific thresholds. PA-056 admits a declared, limited ontology branch with all
five metrics together, without relabeling it broad Physics. The bounded candidate
is the existing nuclear branch, exact preprint years 2018–2023, not Full Physics.

The working integration supplies source-bound date/identity admission, bounded
page receipts, conserved partial-field coverage, fractional affiliation coverage,
source-year proofs, branch aggregation/Diversity and a fail-closed compact dataset
export/loader. PA-057 adds strictly corroborated paper-native ROR matching;
PA-058 distinguishes exact ROR identity from optional parent aggregation. Explicit
erratum/addendum DOIs are preserved as related evidence, not primary identifiers.
Legacy policies, formulas, historical hashes and normal API behavior are unchanged.

**The five-metric launch remains incomplete.** A complete 2018 source traversal
retained all 2,306 records with exact dates and 93.404% known field mass. Following
the DOI-role repair, the identifier-only recheck has 2,299 matched components and
seven unresolved components, not a certified complete year. On the same 250-paper
authority sample, exact-ROR retention raises canonical institution coverage from
49.139% to 67.354%; paper-time affiliation presence is 96.359%. These are measured
sample results, not whole-year institution coverage. Six certified years, mature
comparable cohorts and real exact-five normalized observations are not established.

The current per-entity admission rule also includes the global unknown mass in
each entity's possible-coverage denominator. That intentional worst-case rule is
not silently replaced by the source-year fractional-coverage repair. Separating
observed coverage from retained uncertainty bounds requires a versioned policy
decision; it remains pending, not an implemented relaxation.

The API/database were healthy at 03:10:33 UTC on September 6, expected public-origin
CORS was present and public metric observations were zero. Web `63fc454`/source pin
`21bfcdb8` remain unchanged; no dataset variable or live metrics are enabled. Source
baseline `4e203c0` passed CI 33973186186. Implementation `a813d3e` is pushed;
CI 34008433748 exposed one offline import-boundary failure after 1,118 backend
passes. A narrow shared-pure-function extraction fixes the reproduced failure;
105 relevant cases and full lint/format/mypy (103 source files) pass. Follow-up CI
status is recorded in the recent worklog, not inferred from local validation.
The final local run passes 420 focused backend cases, 139 frontend cases and seven
pipeline cases, full lint/type checking and production build. Local cleanup is
PASS: all **151,511,633** cumulative temporary logical bytes were removed,
including the isolated CI diagnosis/recheck; no raw scientific or build artifacts
were retained by this task.
Exact acquisition bounds, measured denominators, fixes and remaining blockers:
[minimum integration report](validation/minimum-launch-integration-2026-09-06.md).

## Release and scope

- Canonical public/product name: **Atlas Physicus**, part of **Tech Echo
  Physica** (PA-050, superseding the naming portion of PA-047). The primary
  repository and frontend package are `atlas-physicus`. Historical records,
  deployed backend/package/CLI/environment/database identifiers, scientific
  provenance, production URLs and release tags remain unchanged. The current
  naming source changes do not by themselves prove a completed deployment; see
  the [compatibility audit](production-deployment.md#naming-and-deployment-compatibility).
- Current release: `v3.0.5-alpha`; the annotated tag remains at `b1974d2`.
- Source branch: `main` in `Tech-Echo-Collective/atlas-physicus`.
- The active phase is post-release **Stabilization & Scientific Validation**
  for Metric System v1. It does not change the release tag, begin v3.1, or
  authorize a Full Physics load.
- Production acquisition remains `hep-th-v1`. Condensed Matter work is an
  isolated, staging-only validation scope; it is not a production source or a
  broad-Physics activation boundary.
- Public live observations for Activity, Impact, Connectivity, Diversity, and
  Momentum remain jointly withheld. Missing evidence is not displayed as
  zero, and no partial activation is allowed.
- PA-048: the nominal **5 GB budget covers all persistent Atlas data combined**,
  including archives, history, metadata and retained copies—not PostgreSQL only.
  After the final bounded consolidation review, retained evidence/archive/audit files
  occupy 7.804 GB, plus approximately 1.879 GB of Atlas-only workspace: observed
  total-budget **FAIL**. Production migration execution is **NO-GO**; a future representative
  final-layout capacity assessment remains **WITHHELD**. No scientific history is lost
  or scientific policy weakened to fit the budget.

## Operated system

### Public Atlas

- React, TypeScript, Vite, MapLibre GL JS, and Zod implement the map-first
  Physics domain → field → time → world → country → institution → researcher
  exploration path.
- The normal public source is `APIRepository`. Synthetic fixtures and the
  historical pilot remain separate sources for tests and reproducibility.
  Web `63fc454` prevents automatic synthetic fallback on initial API failure or
  missing production configuration. Explicit internal fixture routes remain
  isolated for reproducibility; normal public failure stays unavailable/neutral.
- Repository and dataset-kind checks prevent live/static data mixing.
  Missing observations render as a neutral state.
- The public Pages project is
  `Tech-Echo-Collective/Physics-Atlas-Web`. Its configured backend is
  <https://physics-atlas-api-production.up.railway.app/api>.
- `https://atlas.techecho.org/` serves the public Atlas Physica instance.
  Existing Web domain/routing commits `f1e3be4`/`f4c4e21` were preserved, not
  changed by the rename. Root and direct Atlas route loading, HTTPS, current
  branding, Live API mode and public-origin CORS were verified on September 5.
  Legacy-origin retirement/redirect policy still requires separate review.
- Current Web commit `63fc454` preserves source pin `21bfcdb8` and passed
  [Pages build/deploy 33967823884](https://github.com/Tech-Echo-Collective/Physics-Atlas-Web/actions/runs/33967823884).
  Public page metadata displays Atlas Physicus; unvalidated observations remain
  absent. The new fail-closed wrapper does not deploy backend certification code
  or activate metrics through a submodule upgrade.

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

Read-only verification on 2026-09-05 at `02:26:03Z` found:

- runtime `3.0.5-alpha` and database health both healthy;
- INSPIRE and arXiv healthy with zero consecutive failures and September 4
  latest successes;
- metric recalculation idle;
- 440 unresolved entities remain recorded for review; the one resource-check
  failure is a DOI resolver HTTP 404, independently confirmed and unrelated to
  payload storage. No monitor fix or scientific-data correction is justified;
  see the [diagnosis](validation/staging-dual-read-2026-09-05.md#existing-resource-check-failure);
- zero public metric observations; expected `https://atlas.techecho.org`
  CORS and successful browser Live API reads were verified after publication.

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

The subsequent [production storage design review](validation/production-storage-design-review-2026-09-05.md)
defines an additive mode/descriptor on existing snapshot/raw rows, shared archive
locators and explicit fail-closed precedence; no production adapter/DDL was
implemented. It additionally proves same-host **archive-only dependency recovery**:
OS-denied original evidence, DB files and network; 449 recovered inputs reproduce
all ten artifacts and 9,999 decisions exactly. Independent-host archive durability,
production JSONB/ORM recovery, worker crash/uncertain-commit handling and total
retention/backup/WAL peaks remain unproven.

Counting exact source archives plus retained scientific artifacts/metadata changes
the 474-paper evidence envelope from **50.941 MB to 35.990 MB total**, a 29.35%
modeled total reduction versus 54.98% DB-only. This is not the proposed final
production schema or reclaimed disk. A metadata-only inventory found 5,348 local
evidence files / **16,247,696,733 logical bytes**, dominated by Condensed Matter
raw/replay/certification history; none was deleted or casually labeled temporary.
Known-component 10k-paper hybrid scaling reaches 3.333 GB with contingency,
already above the nominal 3 GB steady limit, before unmeasured required costs.
The total-budget FAIL does not mean the healthy Railway volume is full.

The [local retention investigation](validation/local-evidence-retention-2026-09-05.md)
confirms 5,356 retained evidence files / 16,247,746,809 bytes, plus 1.878 GB of
explicit Atlas-only repository/cache/private-test workspace. Exact hashes find
3.336 GB of redundant bytes, but 3.178 GB belong to distinct required replay
path sets; duplicate content is not deletion permission. Historical and corrected
3.437 GB certification ledgers differ and both retain unique scientific history.

One corrected ledger compresses losslessly to 282.832 MB. Exact original/restored
bytes, all 2,766,760 decisions and ordered provenance/reason/version summaries
match; no scientific replay or recertification occurred. The separately approved
[verified cleanup](validation/verified-local-cleanup-2026-09-05.md) removes only
the 3,437,302,947-byte restored test output and eight redundant SQL read-back
files / 8,175,736 bytes. Original ledgers, archive, manifests, proof and all source
twins remained at that cleanup milestone. Historical manifest paths require retaining the other 144,801,076
bytes of reviewed older proof copies; neither historical manifests nor scientific
evidence were rewritten.

That earlier cleanup removed **3,445,478,683 logical bytes**. Its historical snapshot was
**16,532,083,020 evidence bytes / 5,367 files**, plus **1,878,134,488 workspace
bytes**, approximately **18.410 GB combined**; subsequent documentation/Git
metadata can change the workspace slightly. APFS exclusive block reclamation is
not measured. The [retention policy](local-evidence-retention.md) remains a
proposal, not automatic deletion or production migration approval. Total-budget
FAIL remains; moving or deduplicating required evidence paths is not authorized.

The [archive-promotion review](validation/archive-promotion-review-2026-09-05.md)
initially returned **FAIL / retirement NO-GO** because no authority adapter existed.
The subsequent [bounded resolver proof](validation/artifact-resolver-2026-09-05.md)
now passes: PA-049's pinned logical identity/representation contract resolves the
unchanged historical manifest through archive authority, with original/DB/network
access OS-denied. Exact 3,437,302,947 bytes, all 2,766,760 decisions and complete
scientific/provenance summaries match. Resolver-owned expanded output and the
new isolated archive duplicate were removed; both real originals were retained
until the subsequent explicitly authorized single-artifact retirement.

The [single corrected-ledger retirement](validation/corrected-ledger-retirement-2026-09-05.md)
passed all seven fresh checks: **GO / COMPLETE**. Only corrected `459c1f40…`
was removed, reclaiming **3,437,302,947 logical bytes**. Its 282,831,800-byte
archive remains authoritative; descriptor, manifests/checksums and proofs remain
unchanged. Post-delete archive integrity and historical binding pass without
another full restore. Evidence was then **13,094,800,623 bytes**, approximately
**14.973 GB combined** with Atlas-only workspace. Observed filesystem free space
increased by 3,276,800,000 bytes, not an exclusive APFS block claim.
At that single-artifact milestone, historical `8d9ba03a…` remained intact and no
other evidence was removed. It is distinct from the corrected archive. This is opt-in local tooling,
not production integration or transparent replacement of every direct-path caller.
No scientific eligibility changed; independent durability and budget gates remain.

The subsequently authorized [certification-ledger batch](validation/certification-ledger-batch-2026-09-05.md)
examined nine remaining files / 3,533,688,096 bytes. Historical `8d9ba03a…` now
has its own exact, independently restored 282,717,390-byte archive; only its
3,437,391,298-byte expanded original was retired after all five gates passed.
Its 1,667 historical conflicts remain preserved. Eight paired ledgers totaling
96,296,798 bytes remain NO-GO because their manifest/path contracts are not
supported by the unchanged resolver. Both historical and corrected archive
authorities pass post-retirement checks; original manifests and old proof records
are unchanged. Evidence is **9,940,187,795 bytes**, approximately **11.819 GB
combined** with Atlas-only workspace. No other artifact class was processed.

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

- The [final storage consolidation review](validation/final-storage-consolidation-2026-09-05.md)
  inventories all remaining classes and proves exact recovery on two existing
  provider envelopes and four small researcher/history files. Every unsupported
  historical authority remains NO-GO; no original evidence is retired. Large
  provider-page limits/missing acquisition metadata and direct-path replay
  dependencies remain blockers. 387 focused tests pass; no production/scientific
  code changed. New proofs are bounded by one shared 16 MiB reservation, not a
  corpus-scaled output. New retained audit/probe bytes are 4,874,681; no original
  bytes were reclaimed. Proof retention is 954.114 MB, within 1 GiB; combined local
  footprint is 9.683 GB. Exact snapshot accounting is in the report.
- PA-052 pins 1,000 existing source-scoped paper references (474 paired + 526
  corrected Condensed Matter) and a 1 GiB cumulative proof-output budget within
  PA-048. Exact sample reuse/row recovery pass; retained proof scope was 949.239 MB
  after the affiliation batch, including archives, old versions, copies and metadata;
  the final review records subsequent bounded proof growth. New affiliation pilots
  enforce fresh admission; this is not a universal old-CLI/OS quota.
- The [affiliation archive batch](validation/affiliation-archive-batch-2026-09-05.md)
  extends the existing resolver and current affiliation readers (PA-053). All nine
  original paths, including both large replay twins, passed exact original-absent
  recovery and dependency gates and were retired. Three authoritative archives,
  ten historical manifest bindings and nine explicit indices retain exact content
  and provenance. Historical manifests remain unchanged; three small prior pilot
  inputs remain. Net logical savings are 2,156,281,258 bytes after archives/proofs/
  metadata; combined scoped footprint is 9,678,356,054 bytes at the recorded snapshot.
  432 focused tests, lint/format and strict typing pass; post-retirement authority
  checks and independent accounting pass. No provider/researcher processing,
  Railway access, broad replay, scientific-policy change or activation occurred.
  Production ingestion still excludes expanded validation twins. This does not
  establish independent backup durability, production migration or capacity approval.
- PA-051 now separates corpus-scaled authoritative certification from bounded
  validation traces. Installed paired/replay generators and recovery/dual-read
  runners refuse production runtime execution. Retained replay requires an
  explicit sample ≤2,500 papers; verbose traces are capped at 100,000 decisions
  and 128 MiB. Existing fixed paired/pilot scope checks remain. Summary-only
  offline replay retains no full decision ledger; no production sink was added.
- The [scaling-safety audit](validation/validation-ledger-scaling-safety-2026-09-05.md)
  covers production reachability, guard failure/cleanup and unchanged scientific
  outputs using fixtures only. Existing evidence, archived authorities and release
  tags remain untouched. No Railway access, new acquisition, corpus replay,
  other-class processing, migration or activation occurred. These guardrails
  do not pass the existing scientific/storage gates or establish larger capacity.

- The archive resolver passes 65 focused tests, changed-file Ruff format/lint,
  independent code review and the real original-absent exact-restore proof. Prior
  NO-GO documentation is retained as accurate history alongside the new result.
  No original ledger, historical manifest, scientific policy or release tag changed.
- The verified local cleanup changes documentation only. Nine removed paths
  have fresh checksum/retained-source checks and explicit receipts; original
  evidence, archive and historical manifest hashes are preserved. Baseline
  `0944968` passed [CI 33940584417](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33940584417).
  Documentation whitespace/link checks pass. No Railway access, scientific replay,
  new compression trial, application/schema change or tag change occurred.
- The local retention review adds only a bounded standalone archival helper,
  fixture tests and documentation. 97 focused tests and changed-file Ruff pass;
  the real one-file lossless restore passes. Baseline `32b3f4b` passed
  [CI 33939682265](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33939682265).
  Complete hashes, accounting and limitations are in the
  [local report](validation/local-evidence-retention-2026-09-05.md). Railway was
  not contacted in this local-only task; production code/schema remain unchanged.
- The production storage design review changes documentation only. 85 focused
  existing storage/budget/recovery tests pass (1.02s); OS-isolated archive-only
  recovery and the separate post-recovery hash comparison pass. Baseline source
  `d4859c5` passed [CI 33938302268](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33938302268).
  No new provider calls, production database connection, schema migration or
  frontend changes were needed. Exact evidence hashes and limits are in the
  [review](validation/production-storage-design-review-2026-09-05.md).
- The staging dual-read/rollback proof passes 130 focused backend tests,
  focused Ruff lint/format and strict mypy (80 source files). Native private
  PostgreSQL recovery/certification equivalence and all seven injected failures
  pass. Current Atlas Physica frontend typecheck/lint, 132 Vitest tests, seven
  pipeline tests and production build pass. See the
  [staging report](validation/staging-dual-read-2026-09-05.md) for scope and
  proof limitations. Source commit `1601b7e` is pushed and passed
  [CI 33937979974](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33937979974),
  including all 452 backend fixture tests, PostgreSQL migrations/API/worker
  and container checks. No production payload integration was enabled.
- The one-batch payload-reference pilot passes 123 focused tests (2.82s), Ruff
  over 11 changed/storage files, and strict mypy over 79 source files. Native
  PostgreSQL SQL-to-cold recovery verifies all 3,179 paper/author-fragment
  locators and unchanged hot metadata; independent restored sources reproduce
  all certification artifacts exactly. Commit `7c1f34c` is pushed and passed
  [CI 33936700018](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33936700018)
  (frontend, backend/PostgreSQL and containers). Exact measurements
  and limitations are in the [payload recovery report](validation/payload-reference-recovery-2026-09-05.md).
- The bounded storage investigation passes all 398 backend tests, strict mypy
  (78 source files), and Ruff format/lint (119 files, including tools). Native
  PostgreSQL SQL/archive recovery and bounded local provenance verification
  pass. Commit `c88f9b9` is pushed and passed
  [CI 33935510006](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33935510006)
  (frontend, backend/PostgreSQL and containers). No frontend code changed. Exact results and
  limits are in the [storage report](validation/storage-amplification-2026-09-05.md).
- Certification/capacity result commit `be5e304` is pushed to `main` and passed
  [CI 33932839622](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33932839622),
  including frontend, backend/PostgreSQL, and containerized API/worker checks.
  Frontend type checking, lint, 130 Vitest tests,
  seven pipeline tests, and production build pass. Backend Ruff format/lint,
  strict mypy, and all 376 pytest tests pass with one existing dependency
  deprecation warning and the existing non-blocking frontend chunk-size warning.
- The bounded dual-track result is commit `5e3ba1f`; it passed GitHub Actions
  run [33884017132](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33884017132),
  including frontend, backend/PostgreSQL, and containerized API/worker jobs.
- Post-push production checks confirm healthy service/database status, expected
  public-origin CORS, healthy INSPIRE/arXiv cursors, and zero public metric
  observations. Existing release tags remain unchanged.

## Immediate next action

Resolve the remaining source identity/authority evidence and the explicit
coverage-versus-uncertainty policy question before repeating a larger capture.
Then certify the bounded historical population and apply the measured-session,
five-metric and normalization gates. Admission/export adapters are implemented;
they do not substitute for real certified populations or end-to-end calculation.
Produce the compact dataset only from genuinely admitted calculations; no partial
activation. Do not repeat diagnostics or introduce a new architecture as a proxy
for these concrete evidence requirements.

The earlier storage review is historical context, **not the current next task**.
Legacy retained evidence is not a launch prerequisite; do not expand, reorganize,
delete or optimize it. Keep production healthy, existing tags unchanged, no Full
Physics load or v3.1. New temporary work belongs in one explicit directory under
2 GB and must be removed on success or failure.
