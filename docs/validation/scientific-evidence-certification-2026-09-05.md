# Scientific Evidence Certification validation — 2026-09-05

Status: **staging foundation implemented; all five public metrics WITHHELD;
Full Physics loading not authorized**.

This report separates record-level certification from metric eligibility.
It does not revise Metric System v1, historical release tags, or production
`hep-th-v1` history. The exact policies are in
[evidence certification](../evidence-certification.md),
[metric validation](../metric-validation.md), and
[storage architecture](../storage-architecture.md).

## Implemented boundary

Canonical provider evidence now receives explicit `certified`, `needs_review`,
`withheld`, `conflicted`, or `insufficient_evidence` decisions. Decisions bind
source references, dataset/scope and rule versions, evidence-value digests,
reasons, and review metadata when applicable. Calculation requires a
reconstructable certified partition, exact reviewed eligibility population,
complete metric window, and full coverage denominator. Excluded mass remains
explicit.

Institution, field, citation, source-year, metric-window, normalization, and
Physics field-population contracts are independently testable. Content-bound
review records are operational attestations: their hashes do not authenticate
the reviewer or prove the scientific accuracy/completeness of submitted
evidence. The live worker still uses `NoFormulaMetricRecalculator`.

## Fresh paired capture

The trial covers the closed UTC week **2020-01-13 through 2020-01-19**.
INSPIRE uses its exact earliest-record-date query; arXiv uses submission date.
Those provider query dates are preserved and are not silently selected as a
canonical metric date. Capture completed on
`2026-09-04T16:06:29.293740Z`.

| Track | INSPIRE occurrences | arXiv occurrences | Canonical components |
| --- | ---: | ---: | ---: |
| hep-th | 88 | 103 | 108 |
| Condensed Matter | 82 | 362 | 380 |

All four bounded provider partitions completed, with zero duplicate records
within partitions. There are **635 provider occurrences and 474 unique
canonical components**. Fourteen components occur in both specialty tracks;
the scope denominators must not be summed as a new independent corpus.

The exact identifier enrichment retained 220 INSPIRE institution responses
and 219 unique ROR authority records. No registry/name search was performed.
The final projection preserves 2,101 researcher appearances, 2,290
affiliation-share rows, 474 field ledgers, 170 citation observations, and 9,999
certification decisions.

The raw and enrichment manifests verify the internal live transport, exact
approved endpoints/queries, response timestamps, and stored response bytes.
Certification itself is an offline file operation with no database, cursor,
network, or public-activation access. Injected transports cannot claim an
official capture.

### Artifact provenance

These are SHA-256 content addresses, retained externally beneath the sibling
`physics-atlas-evidence/` directory. Git retains the contracts and this summary;
it does not contain provider payloads.

| Artifact | SHA-256 |
| --- | --- |
| Official raw manifest | `b715c6f2d81013c4ea1bea632edbfb75ab25fa8d3874df2d4326cc2b532e3322` |
| Raw evidence set | `151d1284b1e9fac791df27c141f0126e660b5ff5bb96b56de7500aee8bd3a495` |
| Official enrichment manifest | `8880eaf2afd3c6c32fc46f923d56bb6b6626318af8415653d5756d9c15ee539d` |
| Enrichment evidence set | `ff5d0a36c6f842616afa5b24eb2e54f4f45a10d2de80bb80828d3ae06cd9dda3` |
| Final certification manifest | `e7b99d22e632a30e5b949f4a0165873ecd665b06411984ba3d8a478875bb2729` |
| Final report file | `1196d5e1ebe6556c588489f614be8d074edb193f50d04d79524ea4cb5818d6f4` |
| Retained decision stream | `b21157332f997ad41bc251ff3a317faba6281892ec21d3e35d49905890ba63fb` |

The final certification directory is
`paired-certification-2020w03-v2-certified-official-final`.
An independent offline repeat reproduced the manifest and all ten artifacts
byte-for-byte, including all 9,999 decisions, without another provider request.
`physics-paired-trial-certification-manifest-v2` and
`paired-certification-projection-v2` explicitly supersede the earlier v1
certification semantics. Prior exploratory/fixture outputs and the incomplete
network attempt are not the final result.

## Certification coverage

Affiliation, institution, and researcher coverage use conserved fractional
paper mass; identity, dates, fields, citation observations, and provenance use
one unit per canonical component. Scope membership does not imply a reviewed
field assignment. Percentages below describe only this seven-day capture and
are **not** improvements or regressions against the six-year baseline.

| Evidence | hep-th (108 papers) | Condensed Matter (380 papers) |
| --- | ---: | ---: |
| Canonical paper identity | 107/108; 99.074074% | 380/380; 100% |
| Canonical metric date | 0%; all need review | 0%; all need review |
| Researcher identity | 0% | 0% |
| Paper-time affiliation | 91 units; 84.259259% | 82.440476 units; 21.694862% |
| Canonical institution | 31.933333 units; 29.567901% | 9.85 units; 2.592105% |
| Reviewed field classification | 0% | 0% |
| Field-weight conservation | 100% | 100% |
| Certified citation observation/cutoff mechanics | 20/108; 18.518519% | 13/380; 3.421053% |
| Metric-eligible comparable citations | 0% | 0% |
| Retained provenance completeness | 100% | 100% |

The combined unique-paper ledger conserves 474 paper units: each paper's
attribution mass has minimum and maximum one, with zero violations. Affiliation
decisions, institution decisions, researcher appearances, and field ledgers
retain their complete denominators; missing or unresolved mass is not
redistributed.

### Institution and identity outcomes

Direct ROR evidence can certify against the bound authority records. Generic
name, crosswalk, and contextual candidates require explicit dated review;
subunit rollup requires one eligible active parent or a reviewed exact parent
decision. The paired adapter obtains direct ROR assertions only from verified
exact INSPIRE institution records or paper evidence.

| Unresolved dimension | hep-th | Condensed Matter |
| --- | ---: | ---: |
| Paper identity conflicts | 1 component | 0 |
| Researcher appearances needing review | 215 | 331 |
| Researcher appearances lacking evidence | 41 | 1,544 |
| Missing affiliation shares | 35; 17 paper units | 1,525; 297.559524 units |
| Institution shares needing review | 163; 47.184722 units | 78; 14.05 units |
| Institution shares lacking evidence | 74; 28.881944 units | 1,910; 356.1 units |

No affiliation or canonical-institution conflict was observed in this final
trial. Tests separately cover conflicts, asymmetric identifier enrichment,
empty affiliation objects, and unsupported parent rollup.

At the existing coverage thresholds, this week alone is short by 6.2 hep-th
and 259.559524 Condensed Matter paper units for 90% affiliation coverage, and
70.666667 and 351.15 units respectively for 95% institution coverage. These
are local diagnostic deficits, not permission to fill missing mass or a
minimum sufficient backfill for activation.

### Fields, citation cohorts, and historical years

All 474 selected field ledgers conserve mapped plus explicit unmapped mass to
one, with zero violations. Explicit unmapped mass is `8909/105`
(84.847619 paper-equivalents), including 16 entirely unmapped papers. All
ledgers remain `needs_review`. The immutable v1 mapping catalog has no exact
INSPIRE `Condensed Matter` rule, and no replacement rule or reviewer approval
was invented.

Three provider-local citation cohort candidates contain 20 hep-th papers,
12 Condensed Matter papers, and one math-ph paper. Their cutoff timestamps are
the retained INSPIRE response times: `2026-09-04T16:05:51.942606Z` for hep-th
and `2026-09-04T16:06:15.996222Z` for the other two. Every candidate is below
the 50-paper minimum and lacks a reviewed exact eligible population.
**Certified cohorts: zero; activation-eligible cohorts: zero.** A certified
observation is therefore not reported as comparable Impact coverage.

The trial has **zero certified calendar years, zero certified metric windows,
and zero observations created**. A seven-day provider query cannot satisfy
three-year Activity/Impact/Connectivity/Diversity or six-year Momentum
requirements. Canonical metric-date and researcher/field review are also
missing.

## Existing staging replays

The 47,726-paper hep-th baseline cannot be recomputed because its original
external row artifacts were removed before this task. Its recorded
89.263140% affiliation and 34.969191% institution coverage are preserved;
no same-capture improvement is claimed. The fresh week is a separately
versioned evidence set.

The retained Condensed Matter source was replayed offline into a new immutable
bundle after fixing a concrete provenance bug: 1,667 institution authority
anchors had incorrectly retained the hep-th scope label. The corrected bundle
labels them with their actual Condensed Matter scope. All seven other raw and
projection artifact hashes are unchanged; no scientific coverage gain is
claimed. The original bundle and its conflicted certification diagnosis remain
preserved.

| Corrected Condensed Matter artifact | SHA-256 |
| --- | --- |
| Source manifest (unchanged) | `484880ef2fd03163b393fff2a38a1901340550d5423da058c43f5210c9ed0384` |
| Corrected replay manifest | `e0ef6636423db6db8ba78d92ab764e1d88be09907acc9b7e87733d2d65cf1b07` |
| Corrected replay report | `7b57c6b184f2a84f9960505528e1bcd4f97fc452725a6848ef27e8e102828137` |
| Corrected authority anchors | `dfebd6a884824338364232d4871839b070555f0d94615740be9be66e7d9cb21c` |
| Final retained certification manifest | `9c79eced71031e79f17827ba00825a9541d63f527aa7d4131940799b1711b0d3` |
| Final certification report | `ea1f019187f03c927da8b1de71e7c732aaad0fc1a7eac80568dda103d3636899` |
| Final retained decision stream | `459c1f4065130cef61c3c098f4775994982bd08f2ecb2e7f313d076a8d48aa7f` |

The final retained certification verifies nine input artifacts and records
2,766,760 decisions in a 3,437,302,947-byte content-addressed stream. Its evidence
remains 129,464 canonical components and 25.407165% legacy fractional affiliation
presence, with zero measured allocated institution mass. Full attribution
accounting retains 129,416 withheld paper units and 48 explicitly
unmaterialized units. All conservation checks pass without assigning those
48 units to a guessed author projection. Field ledgers preserve
103,525.748740 mapped plus 25,938.251260 unmapped units. Legacy pages lack
response-time citation lineage, fields/dates/identities remain unreviewed, and
no metric year/window or observation is created. New certification decision
ratios use record counts and must not be compared directly with the historical
fractional affiliation percentage.

| Strict record certification | Final result |
| --- | --- |
| Canonical paper identity | 129,110 certified; 354 need review; 99.726565% |
| Paper-time affiliation | 0% certified; 190,085 need review; 510,576 insufficient |
| Canonical institution | 0% certified; 702,328 decisions need review |
| Researcher identity | 0% certified; 135,947 need review; 516,108 insufficient |
| Canonical dates / reviewed fields | 0%; 129,464 need review in each dimension |
| Citation observation / cutoff | 0%; 32,198 withheld in each dimension |
| Field conservation / provenance | 100%; 129,464 certified in each dimension |

The scope fix changes the 1,667 authority anchors from `conflicted` to
`needs_review`; it does not certify their unresolved authority metadata. The
strict overlay cannot promote legacy affiliation presence to certification,
so its 0% result is deliberately distinct from the preserved 25.407165%
presence baseline. **New activation-grade coverage gain: none.**

Decision retention is optional in the replay tool and streams with bounded
memory. This final run retains the decisions; it is not a summary-only run.
The artifacts remain local external evidence, with no production database or
cursor access.

## Atlas Scale and gate result

`normalized-atlas-scale-v1` preserves the unchanged raw formula output and
unit, metric normalization version, fitted parameters, exact reviewed
field/time/entity population, cutoff, certification digest, coverage, and
missing reasons. The observation reconstructs from certified calculations;
Physics aggregation consumes certified normalized field observations. The
five-weight exploratory composite remains unchanged.

The exact existing `assess_joint_metric_activation` evaluator was run
independently for both final paired scopes with their measured coverage and
zero activation-eligible comparable citations. Both return **WITHHELD** for
all five metrics. Denominators are not pooled. Its diagnostic artifact is
`paired-certification-2020w03-v2-joint-readiness-official/joint-gate-diagnostic.json`,
file SHA-256 `00ea255efaa85298495557447f4ed5ef84c1be2483a89681e931879ef692da29`,
canonical result digest
`da1a8dfef9c4c1bbe0e5a0da3bb81f90037616d0d8098ef3620f1f3778e8141e`.
Repeating against the independently reproduced paired artifacts gives the
same diagnostic bytes.

The evaluator reports the same eleven blockers for both scopes: the boundary
is not broad Physics; the Diversity breadth-review version is absent; broad
Diversity review has not passed; affiliation is below 90%; institutions below
95%; comparable citations below 90%; reviewed fields below 90%; six-year
history is unvalidated; citation maturity/common cutoff is unvalidated;
normalization validation is absent; and system-level metric reproduction has
not passed. Algorithm regression tests and paired artifact reproduction pass,
but neither supplies live metric-system reproduction. No activation manifest
or live metric observations were created.

## Storage result

The read-only production audit measured a **306,534,079-byte database** on a
**4,685,873,152-byte volume**, with **499,077,120 bytes used**. Public tables
occupy 241,106,944 bytes and indexes 55,730,176 bytes. The two raw-evidence
relations account for 155,394,048 bytes, 52.35% of public-relation storage.

The observed full-database ratio is **3.725 decimal GB per 10,000 papers**;
excluding raw relations gives a **1.719 GB lower-bound proxy**. Both ratios
include fixed effects and are not a validated marginal cost. Illustrative
250,000/500,000/1,000,000-paper scenarios are 93.307/186.422/372.652 GB at the
current layout, or 43.168/86.134/172.065 GB with raw relations excluded, before
the required 25% contingency. These are capacity scenarios, not corpus-size
claims.

The Storage Budget Gate is **WITHHELD**: the 823-paper live sample is below
10,000, the final hot citation/certification/metric shape is unmeasured, no
reviewed exact Full Physics target exists, and isolated backup/restore
evidence is incomplete. The measured ceilings are 2,811,523,891 bytes steady
and 3,748,698,521 bytes peak. Raw externalization is necessary but insufficient
for every evaluated field-scale scenario. Exact breakdown and caveats are in
[storage sizing](storage-sizing-2026-09-04.md).

The local artifact-store abstraction and typed gate are implemented. No
object-store deployment, production schema migration, evidence deletion, plan
upgrade, or Full Physics load occurred. This storage gate applies to Full
Physics loading, not normal bounded map/API reads.

## Concrete integrity fixes

- Empty affiliation objects no longer count as historical evidence. Provider
  precedence retains usable assertions, and typed shared identifier namespaces
  expose conflicts instead of resolving them by processing order.
- Direct affiliation ROR and author-level authority assertions must agree;
  unaligned multiple-author identifiers cannot become a guessed institution.
  Generic name and crosswalk candidates need review, and authority rollup
  requires explicit eligibility.
- Historical replay authority anchors now inherit the actual replay scope.
  Replaying retained Condensed Matter bytes corrects 1,667 mislabeled anchors
  without changing the seven other evidence artifacts or scientific totals.
- Official capture status requires internal transport lineage and exact
  endpoint/query verification. Injected data and stale certification semantics
  cannot be relabeled as current official evidence.
- Metric certificates bind per-kind formula values, exact source-window
  populations, exclusions, and coverage mass. Impact comparability is derived
  from mature certified cohort membership. Diversity and normalization require
  reviewed exact universes; Atlas values and Physics aggregation reconstruct
  from certified inputs.
- The Full Load gate verifies typed measurement, projection, exact target,
  and isolated-restore records. A target below the sample or projection below
  the deterministic floor cannot produce authorization.

## Validation and remaining action

Frontend type checking, lint, 130 Vitest tests, seven pipeline tests, and the
production build pass; the existing chunk-size warning remains non-blocking.
Backend Ruff format/lint, strict mypy, and all 376 pytest tests pass with one
existing Starlette/httpx deprecation warning. Post-push CI verification is
pending. The unchanged source
baseline `3ab1456` has green CI run
[33884328992](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33884328992).
This report does not claim a successful new commit or CI run in advance.

Read-only production verification at `2026-09-05T00:14:15Z` found runtime
`3.0.5-alpha` and database health `ok`, both providers healthy with zero
consecutive failures, metric recalculation idle, 440 unresolved entities, and
two existing resource-check failures. At `00:16:29Z`, the public metric API
returned total zero and allowed the exact `https://atlas.techecho.org` CORS
origin. Storage figures remain the separately timestamped September 4 audit.
The public Atlas root returned HTTP 200 at `2026-09-05T00:16:50Z`.

The next scientific action is reviewed evidence work: canonical date selection,
researcher identities, exact field mapping/review, unresolved institution
targets/rollups, and a reproducible sufficiently sized common-cutoff citation
population. Complete-year certification must follow that work. The separate
operational action is a representative final-schema staging measurement and
reviewed isolated restore, before any larger production load is considered.
