# Physics Atlas project state

Last reviewed: 2026-08-31

This file records the factual operating state of the project. Read it with [durable decisions](DECISIONS.md), the [roadmap](roadmap.md), and the [worklog](WORKLOG.md) before major work.

## Current release

- Current release: `v3.0.5-alpha`.
- Source branch: `main` in `Tech-Echo-Collective/Physics-Atlas`.
- The `v3.0.5-alpha` annotated tag identifies the stabilization and scientific-
  validation release commit. Existing `v3.0.4-alpha` remains unchanged at
  `09f5d855a3ef28d687f5f888f0227a8f911b69de`.
- The active source phase is the post-v3.0.5 scientific-modeling foundation
  within **Stabilization & Scientific Validation**. It adds Metric System v1
  implementation and attribution infrastructure without changing the released
  tag, widening the live corpus, or beginning v3.1.

## Implemented systems

### Frontend

- React, TypeScript, Vite, MapLibre GL JS, and Zod application.
- Map-first world → country → institution → researcher exploration.
- Domain, field, and continuous time navigation.
- Static synthetic repository, preserved historical INSPIRE-HEP pilot repository, and API-backed repository behind one repository boundary.
- Validated API responses, pagination, caching, cancellation, stale-response protection, scoped map/profile loading, and deep-link hydration.
- Explicit provenance and missing-data treatment; a missing metric is not converted to zero.
- Viewport-bounded desktop controls, independently scrollable field and
  institution lists, compact live-data language, and tablet timeline/card
  overlap protection.
- Compact live methodology/status inside the existing information control;
  map presentation remains primary.
- Multipolygon, disconnected-territory, and antimeridian rendering, including the established China geographic-view behavior and Russia/Kaliningrad handling.

### Backend and data platform

- FastAPI read service with typed, paginated Atlas, profile, provenance, search, update-status, and health endpoints.
- PostgreSQL persistence through SQLAlchemy and Alembic.
- Canonical entities and temporal relationships, raw provider evidence, source snapshots, authority identifiers, resolution/review records, dataset updates, cursors, resources, metric observations, paper-time attribution projections, and joint metric-system release manifests.
- Incremental, auditable, idempotent update engine with closed-window checkpoints and PostgreSQL advisory locking.
- Versioned `hep-th-v1` scheduled acquisition: INSPIRE `subject:Theory-HEP`,
  arXiv `cat:hep-th`, and direct ROR refreshes only for configured known IDs.
- Targeted record lookup implementations for known ORCID iDs and DOIs through ORCID and Crossref.
- External-resource enrichment and bounded resource-health monitoring.
- Scope-bound provider cursors, snapshots, and dataset provenance that fail closed
  rather than reusing or mixing a broader acquisition scope.
- Bounded provider HTTP retries, rate-limit handling, per-provider origin
  isolation, strict response envelopes, and conservative authority-conflict review.
- Affected metric-partition planning still uses `NoFormulaMetricRecalculator`;
  no unreviewed scientific scores are written by the production worker.
- Paper-time affiliation materialization with exact Fractional Attribution v1
  conservation, explicit unresolved/ambiguous/missing mass, preserved subunit
  and contribution-statement provenance, versioned supersession, and explicit
  paper-native/INSPIRE → arXiv precedence. Undated ORCID and current-profile
  evidence cannot become a historical projection, unresolved cross-provider
  target conflicts remain withheld regardless of provider tier, and partial
  evidence cannot erase stronger author-slot evidence.
- The versioned Physics Field Ontology v1 and separate INSPIRE/arXiv provider
  mapping layer, including raw-category and primary/secondary-role preservation,
  explicit unmapped evidence, one conserved cross-provider selected ledger, and
  equal mapped-field shares when no reviewed unequal policy exists.
- Deterministic raw calculators and metric-specific normalization for exactly
  Activity, Impact, Connectivity, Diversity, and Momentum, plus field-balanced,
  coverage-aware Physics aggregation.
- Versioned Metric Validation Thresholds v1 and a fail-closed exact-five Joint
  Activation Gate. It now requires the exact field-weighting and reconciliation
  versions plus an explicit conservation pass; a legacy generic `jointGatePassed`
  flag cannot publish observations. The implementation is testable scientific
  infrastructure, not evidence that the live system is scientifically validated.
- Additive metric-observation reconstruction metadata: definition, algorithm,
  dataset and scope versions; raw value/unit; normalization method/parameters;
  input count; quality flags; and calculation partition/time.
- Current-version metric reads exclude stale definitions and dataset lineages,
  deterministically select only same-algorithm recalculations, and fail
  conflicting-algorithm partitions closed across map and profile endpoints.
- Database-backed scientific activation reports and a joint release manifest
  that fail closed, reject partial metric publication, and never create
  observations by themselves.
- Deterministic identity-review sampling, independently labeled validation
  reports, and an aggregate public identity-quality summary.
- Deterministic fixtures, PostgreSQL integration tests, and Docker Compose services for database, migration, API, and worker validation.
- A staging-only `physics-atlas-backfill` boundary can acquire the fixed
  `hep-th-v1`, 2020–2025 INSPIRE/arXiv raw trial into immutable external pages
  with exact totals, checksums, and verified resume state. It imports no
  database or canonical materialization code.

## Public deployment state

- The public entry point is the separate
  `Tech-Echo-Collective/Physics-Atlas-Web` GitHub Pages project. Its canonical
  target URL is <https://atlas.techecho.org/>.
- The deployed application is built with
  `VITE_ATLAS_API_URL=https://physics-atlas-api-production.up.railway.app/api`
  and uses `APIRepository` on normal clean routes. The previous inherited Pages
  path, <https://techecho.org/Physics-Atlas-Web/>, remains a migration origin
  until the separate DNS, Pages custom-domain, certificate, and redirect
  cutover is completed and verified; this source change does not claim that
  cutover has occurred.
- The normal public source selector exposes only the live API. Synthetic framework and historical pilot repositories remain available only through explicit internal routes for tests, reproducibility, and first-load failure fallback.
- Data-source resolution, repository boundaries, dataset-kind validation, and scoped live merges prevent live/static record mixing.
- The production API currently publishes no reviewed metric observations. All
  five live layers fail the joint evidence gate and remain
  explicitly withheld. The public map stays neutral; missing data is not zero.
- The post-v3.0.5 source foundation does not itself claim a production schema
  migration, historical materialization, backfill, worker recalculation, or
  public deployment. The operated v3.0.5 baseline remains the live reference
  until those steps are separately validated.

## Repository and CI health

- The `v3.0.5-alpha` release gate includes 123 frontend component/data tests,
  seven deterministic pipeline tests, 113 backend tests, strict TypeScript and
  mypy checks, ESLint/Ruff, production builds, a fresh migration plus drift
  check, deterministic fixture ingestion, local API/CORS contract checks, and
  zero npm audit findings. The tag is created only after the GitHub frontend,
  PostgreSQL backend, and container jobs pass on the release commit.
- The v3.0.5 implementation commit `ba44c7e` passed GitHub Actions
  [run 33191858046](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33191858046): frontend verification, PostgreSQL-backed backend validation and migration drift checks, deterministic ingestion/API checks, and the Docker Compose job all succeeded.
- The preceding main failure was a stale CI assertion that expected scheduled ROR
  output even when no reviewed ROR IDs were configured. CI now verifies the
  intentional `hep-th-v1` INSPIRE/arXiv safe default and its scope versions.
- The preceding v3.0.4 public activation at `Physics-Atlas-Web` main commit
  `13f1d5b` passed and deployed through GitHub Pages
  [run 33186585196](https://github.com/Tech-Echo-Collective/Physics-Atlas-Web/actions/runs/33186585196). Its `atlas` submodule is pinned to validated Physics Atlas main commit `45da545`; the `v3.0.4-alpha` tag was not moved.
- The v3.0.5 public deployment updates that submodule to the release commit and
  retains `APIRepository` as the normal clean-route source; synthetic and pilot
  repositories remain isolated reproducibility/fallback modes.
- Both npm dependency audits reported zero vulnerabilities, and the installed
  backend environment reported no broken Python requirements. No broad
  dependency upgrade was justified.

The post-v3.0.5 Metric System v1 implementation completed its local validation
gate on 2026-08-30: frontend type checking, lint, 130 Vitest tests across 24
files, seven deterministic pipeline tests, and the production build passed;
backend Ruff, strict mypy across 48 source files, and 172 pytest tests passed;
Alembic upgrade, drift check, head verification, and upgrade/downgrade coverage
passed. A fresh deterministic fixture worker database produced one canonical
paper, two paper-time affiliation rows, zero metric observations, and one
withheld joint release, as intended.

After that full run, a URL-state regression was corrected so an absent `year`
parameter remains absent and the repository dataset period is used instead of
coercing the missing value to year `0`; a regression test records the case. The
complete frontend validation rerun then passed. Docker is not available in this
local environment, so GitHub Actions remains the final PostgreSQL/container
validation gate. The implementation is recorded in commit `fe752f0`; its
GitHub Actions validation passed in [run 33300307090](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33300307090), including the PostgreSQL and container jobs.

## Backend deployment state

- The production Railway API is operating at <https://physics-atlas-api-production.up.railway.app/api> with a healthy database and runtime version `3.0.5-alpha`.
- The production evidence verified on 2026-08-30 reported `datasetKind:
  live-api`, acquisition scope `hep-th-v1`, period `2026`, update sequence 9,
  dataset version `live-20260829T185718Z-23637742`, and a last successful
  update at 2026-08-29 18:57:20 UTC. INSPIRE and arXiv reported healthy cursor
  state, zero consecutive failures, and idle metric recalculation. The
  persisted additive dataset schema identifier remains `3.0.4-alpha`; the
  runtime and newly emitted provenance are v3.0.5.
- Earlier representative v3.0.5 warm API reads returned HTTP 200 in
  0.19--0.27 seconds. The bounded responses ranged from 43 bytes for an empty
  metric page to 10,135 bytes for the seven-definition metric registry; these
  timings were not remeasured in the 2026-08-30 production snapshot.
- The transition CORS contract admits the exact legacy GitHub Pages origin,
  the inherited `techecho.org` origin, and `https://atlas.techecho.org` for GET
  and preflight requests, while denying an untrusted origin. The deployed Pages
  bundle contains the configured
  HTTPS API endpoint. The public Pages root returns HTTP 200; direct deep-link
  transport returns GitHub Pages HTTP 404 with the expected SPA fallback shell,
  which the client uses to restore the route.
- `compose.production.yml`, Caddy configuration, a production environment
  template, and an operator runbook now configure PostgreSQL, migrations,
  FastAPI, the bounded worker, and automatic HTTPS for a single authorized host.
- The API now consumes Railway's standard `DATABASE_URL` and `PORT`, normalizes
  generic PostgreSQL URLs to the installed psycopg 3 driver, and refuses to
  start in production fixture mode. The runbook records the required Dockerfile
  path, API migration/health gate, and separately sequenced worker service.
- The production definition fixes `hep-th-v1`, disables fixtures, admits only
  the three exact transition origins, keeps PostgreSQL/FastAPI unpublished, and
  leaves credentials in an ignored operator environment file.
- Railway provisioning, managed PostgreSQL, API, and bounded worker activation are complete. Secret values remain outside the repository.
- Off-host backup/restore evidence, rate protection, longer-running monitoring,
  alerting, and operational rehearsal remain operator responsibilities and have
  not been verified from this repository context.

## Data-source state

All retained modes remain isolated:

- **Synthetic framework:** hand-authored UI and architecture test data.
- **Historical INSPIRE-HEP pilot:** bounded, reproducible provider metadata retained for methodology and regression work.
- **Live API fixture mode:** deterministic connector fixtures exercising the complete database/API path in development and CI.
- **Provider-backed live mode:** deployed through Railway and used by the public Pages application as the normal data path.

The implemented provider-backed path is bounded to the requested activation
corpus:

- `hep-th-v1` is the only accepted acquisition policy.
- INSPIRE requests `subject:Theory-HEP`; arXiv requests `cat:hep-th`.
- ROR never scans the registry. It refreshes only configured, normalized known
  IDs and is skipped when the target list is empty.
- ORCID and Crossref remain targeted lookups. Crossref was smoke-tested with a
  DOI already discovered in the bounded corpus; no known ORCID was present, so
  ORCID was correctly not queried.
- A scope mismatch in the provider cursor or live dataset fails before provider
  I/O. Synthetic, fixture, pilot, and provider-backed records remain isolated.

An isolated local provider smoke run covered the closed historical window
2025-01-01 through 2025-01-02. It persisted four real INSPIRE/arXiv source
snapshots, 22 raw records, and seven canonical papers in a temporary database;
the arXiv window completed and the deliberately one-record INSPIRE pagination
checkpoint remained resumable. Fresh worker processes resumed both provider
checkpoints, FastAPI served the persisted records before and after restart, and
a three-resource monitoring pass completed. This is staging evidence, not a
production update or public dataset.

A separate staging-only 2020–2025 `hep-th-v1` raw trial completed on 2026-08-30:
43,439 INSPIRE plus 44,773 arXiv occurrences across 628 verified pages and 12
exact provider/year partitions. Final manifest checksum is
`e3dba5492e0dee3fb0b359cd90acd9cc07991e83b89cb6f16c49b498c4e65536`.
The first run failed safely at arXiv 2025 offset 4,600; the finalized loader
verified/skipped all completed pages and resumed only the unfinished partition.
This established raw provider-record completeness, not normalized
publication-year completeness, canonical materialization, or metric-year
certification. Full evidence is recorded in the
[bounded dry-run report](validation/metric-system-v1-hep-th-2020-2025-dry-run.md).

## Scientific validation result and limitations

### Metric System v1 source foundation

- The canonical scientific-attribution policy is implemented as
  `fractional-attribution-v1`: each paper carries total mass one, author shares
  are equal by default, multi-affiliation author shares are divided equally,
  and unresolved mass remains withheld rather than being redistributed.
- `physics-field-ontology-v1` supplies a broad, versioned Physics hierarchy.
  `provider-field-mapping-v1` keeps INSPIRE/arXiv taxonomy evidence separate,
  preserves raw categories and roles, and does not invent unmapped membership.
- The five versioned Metric System v1 algorithms now implement fractional
  Activity, cohort-normalized Impact with PP(top 10%) evidence, collaboration
  proportions, normalized Shannon Diversity, and backward-looking
  field-relative Momentum. Raw inputs and fitted normalization provenance are
  preserved for reconstruction.
- Physics-wide results are derived only after field-specific calculation and
  normalization, using `physics-field-balanced-coverage-aware-v1`; raw counts
  are never pooled across fields.
- `metric-validation-thresholds-v1` and the exact-five activation manifest keep
  every live layer jointly withheld until attribution, ontology/mapping,
  history, citation maturity, coverage, normalization, and deterministic
  reproduction evidence all pass review.
- Reference seeding preserves an exact reviewed activation but never creates
  one. Public reads also require the complete exact-five live definition set;
  a partial or internally inconsistent activation returns no observations.
- The user composite remains an explicitly confirmed exploratory perspective
  over exactly the five dimensions. It is not an official score or ranking.
- A linked Paper ↔ Researcher ↔ paper-time Affiliation ↔ Institution reference
  validation framework is present. Named research ecosystems are sanity-check
  anchors only and cannot impose a preferred ordering.

Canonical specifications are [Scientific Attribution](scientific-attribution.md),
[Field Ontology](field-ontology.md), [Metric System v1](metrics-spec-v1.md), and
[Metric Validation](metric-validation.md).

### Current operated evidence

- The bounded production snapshot verified on 2026-08-30 has 177 canonical
  papers, 475 researchers, 501 authorships, nine source snapshots, and nine
  dataset updates. It still has zero canonical institutions, zero profile
  affiliations, and zero metric observations. Historical-window completeness
  has not been established.
- Identity resolution has 1,383 outcomes: 1,028 matched, 355 unresolved and
  open for review, and zero ambiguous. Researcher outcomes total 780 (754
  matched and 26 unresolved); paper outcomes total 603 (274 matched and 329
  unresolved); institution outcomes remain zero. These counts describe
  workflow and evidence coverage, not precision, error rate, or scientific
  validity.
- A bounded Metric System v1 activation diagnostic on 2026-08-30 found 603
  incremental raw paper occurrences and 177 canonical papers. Raw records
  contain 1,643 author slots, of which 1,499 (91.236%) carry at least one of
  2,021 affiliation assertions, but there are still zero canonical institutions
  and therefore zero allocatable canonical institution mass. All 177 matched
  canonical papers have at least one finite raw citation count and a provider-
  derived field label; neither result is reviewed activation evidence. The
  reviewed field-attribution numerator and the set of certified complete years
  are both zero.
- The subsequent external raw trial produced 47,726 identifier-linked paper
  candidates from 88,212 provider occurrences. Raw fractional affiliation-
  evidence mass is 89.269%, structured-institution-reference mass is 85.321%,
  raw non-self-citation-count presence is 91.011%, raw provider-category
  mapping coverage is 90.509%, and reviewed field coverage remains zero. No
  canonical institution, citation-comparability, or complete-year certificate
  was created.
- Raw selected field ledgers conserved 44,360.571 mapped units plus 3,365.429
  explicit unmapped units across 47,726 candidates with zero violations. This
  is not the reviewed canonical conservation proof required by activation.
- Raw Momentum window mass is sufficient by count (9,859.480 for 2020–2022;
  12,951.465 for 2023–2025), but readiness remains false. The trial found
  18,751 publication-year/date-year mismatches and 3,369 candidates outside
  publication years 2020–2025, so no metric year can be certified without a
  reviewed bibliographic merge/cohort policy.
- The same diagnostic corrected four bounded implementation defects: live
  validation now measures current `PaperAffiliation` mass rather than profile
  `Affiliation` rows, does not treat "paper has an author" as collaboration
  relationship coverage, and does not require geographic attribution for a
  researcher-only Connectivity partition. INSPIRE normalization also now uses
  a valid `earliest_date` when journal-year metadata is absent. No production
  records were reprocessed and no metric was activated.
- No independently labeled live truth sample exists, so precision, recall, and
  confidence calibration remain withheld. Institution/ROR validation cannot be
  measured against the operated canonical graph until reviewed production
  institution materialization exists.

- Raw INSPIRE affiliation, reference, and citation structures are preserved.
  The new source materializer can create versioned paper-time affiliation
  projections conservatively, but no production migration, reviewed backfill,
  or sufficient canonical affiliation/citation coverage has yet been
  demonstrated.
- Institution/country attribution therefore remains too incomplete for a useful live geographic research view.
- The five formulas are implemented and deterministic, but they have not passed
  representative scientific review or the Joint Activation Gate. Affected
  partitions are recorded, but no live country or institution heat values are
  fabricated.
- The live frontend can correctly show a neutral missing-data map, but that is not yet a useful scientific activity heatmap.
- Resolver precision has not been calibrated against a representative reviewed truth set, and there is no public resolution-review interface. The deterministic sample/report framework is present for that next bounded review.
- arXiv acquisition tracks new submissions through `submittedDate`; it is not a complete subsequent-revision stream.
- ROR targets are operator-configured until reviewed affiliation evidence can
  drive them automatically. The staging raw-acquisition command deliberately
  stops before the still-unapproved canonical historical import/replay path.
- Retraction, tombstone, cross-provider conflict, large-backfill, and long-term provider-payload retention policies require review before wider operation.

## Immediate task after the bounded historical dry run

Preserve the hosted source → PostgreSQL → FastAPI → `APIRepository` path and
keep `hep-th-v1` bounded. The next minimum action is to review the policy and
authority blockers exposed by the completed raw trial, without activating it:

1. approve a cross-provider canonical title, publication-date/precision,
   document-type, and metric-year cohort policy;
2. approve an INSPIRE-institution authority and ROR crosswalk/promotion policy,
   then independently review a bounded institution/affiliation sample;
3. implement a staging-only acquire-first import/replay adapter and verify that
   it preserves immutable source lineage before any production write;
4. add timestamped non-self citation observations at a common cutoff and review
   provider field evidence; `hep-th-v1` alone cannot validate Diversity;
5. certify all six years and exact partitions, then rerun linked ecosystem,
   normalization, Impact cohort, Momentum, and joint-gate validation;
6. create a reviewed activation manifest only if all five dimensions pass
   together, and continue collecting operated backup/restart/monitoring evidence.

Do not begin v3.1, expand to all Physics, or activate a live heatmap merely to
fill the map. Cross-provider affiliation precedence and field conservation are
now frozen; the remaining bibliographic, institution-authority, citation-cutoff,
and import/replay decisions must be reviewed before a canonical historical
write. The next release scope must be chosen from that evidence.
