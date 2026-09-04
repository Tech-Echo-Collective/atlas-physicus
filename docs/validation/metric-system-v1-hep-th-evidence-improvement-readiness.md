# `hep-th-v1` evidence-improvement readiness

Date: 2026-09-04

Status: **staging implementation validated; evidence reacquisition not run;
Joint Activation Gate remains withheld; production unchanged**.

This note records the bounded implementation prepared to improve the existing
2020–2025 canonical replay. It does not claim a new evidence result. The
external `/private/tmp` replay and enrichment artifacts were removed before
this pass resumed, so no before/after delta can be reproduced from the working
tree alone.

## Durable baseline

The committed canonical-replay report remains the source of truth:

- source manifest:
  `e3dba5492e0dee3fb0b359cd90acd9cc07991e83b89cb6f16c49b498c4e65536`;
- replay bundle:
  `d125a0861df03c5e1e7e20202db06f7d2506e0e8e9fb3fca732e7208f4349d82`;
- institution-resolution manifest:
  `4e0f58bdc4d44836e013a2b311998858e4a1894bcecd06d617e2cfa5211ece38`;
- 47,726 paper components, 183,247 paper-time affiliation shares, 47,726
  attribution/field ledgers, and 43,439 citation observations;
- affiliation evidence: 42,601.726004 / 47,726 = 89.263140%;
- activation-eligible canonical institution rollup: 16,689.396051 / 47,726 =
  34.969191%;
- comparable common-cutoff citations: 0 / 47,726 = 0%;
- reviewed field ledgers: 0 / 47,726 = 0%;
- certified canonical metric years: none;
- metric observations created: 0.

Those values can be quoted and checked against the committed report. They
cannot be recalculated byte-for-byte without restoring the content-addressed
source, replay, ROR, and resolution artifacts referenced by the checksums.

Against the unchanged v1 thresholds, the historical baseline is short by at
least **351.673996 paper units** of affiliation evidence and **28,650.303949
paper units** of activation-eligible canonical-institution evidence. Citation
comparability and reviewed field attribution each require at least 42,954 of
47,726 components but remain at zero; all six canonical years, every mature
Impact reference cohort, and both three-year Momentum windows remain
uncertified. These are minimum threshold deltas, not evidence that the next
acquisition will recover them.

## Validated bounded implementation

Two external-staging-only evidence boundaries are prepared:

1. `hep-th-v1-historical-inspire-institution-targets-v1` acquires only exact
   INSPIRE institution recids already present on paper-time affiliation
   evidence. A complete acquisition can emit an exact explicit recid-to-ROR
   crosswalk and a target-only ROR manifest. Partial acquisitions cannot emit
   either canonical input.
2. `hep-th-v1-inspire-paper-affiliation-targets-v1` targets only existing,
   matched arXiv-only replay components with missing affiliation mass. Exact
   arXiv-ID INSPIRE results may recover paper-native affiliations only after a
   complete positional author-list check. No-hit, multiple-hit, nonexact-hit,
   and author conflicts remain explicit. All exactly aligned INSPIRE slots are
   retained. Matching arXiv assertions are classified as corroborated and
   superseded under provider precedence; irreconcilable differences remain
   unresolved. Existing multi-affiliation share identities and mass remain
   intact, and only formerly missing author slots count as recovered coverage.
   Conflict mass remains source evidence under the existing coverage contract,
   but is reported separately and withheld from canonical resolution; both
   evidence-presence and resolution-eligibility mass partitions conserve.

The ROR resolver now accepts a checksum-verified, non-overlapping sequence of
canonical authority bundles. This preserves existing direct-ROR resolutions
while adding exact crosswalk resolutions from a supplemental bundle. Direct
paper evidence retains precedence. Exact attribution mass and PA-035
parent/self rollup conservation remain fail-closed.

Institution, paper, and ROR acquisition checkpoints are written at a bounded
25-record cadence plus terminal/failure/paused boundaries. Existing
content-addressed resume states remain readable.

Focused validation passed:

- Ruff: pass;
- mypy: pass for all three affected staging modules;
- 64 focused ROR, institution-crosswalk, paper-enrichment, replay, and backfill
  tests: pass.

Tests cover partial-materialization rejection, exact target order, source and
record lineage, duplicate recid rejection, multi-bundle canonical union,
direct-evidence precedence, mass conservation, exact-query outcomes, and
non-mutation of existing affiliation evidence, including multi-affiliation
author slots and unresolved cross-provider conflicts. A byte-level
compatibility regression also verifies that the legacy single-canonical-bundle
path retains its prior v2 manifest, authority-resolution, and
affiliation-projection checksums; extended fields appear only for multi-bundle
or supplemental-crosswalk resolution.

A final independent integrity pass also made every crosswalk consumer rederive
the exact normalized ROR identifiers and resolution status from its referenced,
checksum-bound raw INSPIRE institution snapshot. A fully rehashed crosswalk
cannot substitute another valid ROR identity. Equal-progress manifest and
partition resume evidence now fails closed when its content differs, an empty
institution target materializes as a valid empty no-op, and both known
specialty scopes remain field-conditioned even if a caller supplies a
contradictory broad-Physics label.

## Evidence that requires restoration or reacquisition

No post-baseline count or coverage delta is claimed. The following require
restoring the original immutable staging tree or rerunning the bounded source
acquisition and canonical replay first:

- deriving the exact unresolved INSPIRE-institution target count and mass;
- acquiring and projecting explicit INSPIRE recid-to-ROR evidence;
- deriving the exact arXiv-only missing-affiliation target prefix and measuring
  recovered affiliation mass;
- acquiring any supplemental ROR child/parent authority records;
- producing a new content-addressed resolution manifest and after-coverage.

Common-cutoff citation cohorts require a separate reproducible acquisition
whose observation-time lineage satisfies the existing citation-cutoff policy.
The prior aggregate counts cannot be made comparable by relabeling their
manifest completion time. Field review and canonical-year certification also
remain review decisions, not safe automated enrichments.

Until those artifacts are restored or reacquired and the exact Joint
Activation Gate passes, Activity, Impact, Connectivity, Diversity, and
Momentum remain withheld together. No public metric activation or production
write is authorized by this implementation pass.

## Fresh paired-run plan

Any new measurement must be a fresh pair, not a continuation of or an
identical comparison with the 2026-08-31 replay. Provider records may have
changed since that capture.

Use an operator-approved durable external sibling staging root, never
`/private/tmp` or the repository, with this logical layout:

```text
<external-staging-root>/hep-th-v1-2020-2025-<capture-id>/
  source/
  replay/
  baseline-ror/
  inspire-institution-crosswalk/
  supplemental-ror/
  paper-affiliation-enrichment/
  paired-reports/
```

The `<capture-id>` must encode or be bound by manifest to the new UTC
acquisition start/completion timestamps. The paired report must record every
source, replay, target, acquisition, crosswalk, canonical authority,
resolution, and enrichment manifest checksum.

Run order after provider coordination:

1. acquire the same closed 2020–2025 `hep-th-v1` source scope into the durable
   root, preserving per-page/per-record capture times;
2. create one new immutable canonical replay and measure its own baseline;
3. resolve direct ROR anchors to produce the paired institution baseline;
4. derive exact INSPIRE-institution and exact arXiv-paper target manifests from
   that same replay;
5. finish the institution target before emitting its crosswalk/ROR target;
6. acquire/canonicalize the exact supplemental ROR children and required
   parents, then resolve the same replay with the baseline and supplemental
   canonical bundles together;
7. acquire a deterministic missing-affiliation target prefix and project it
   against the same replay without replacing existing evidence;
8. compare baseline and enriched numerators only within this new capture pair,
   rerun conservation and Joint Gate validation, and write a content-addressed
   paired report.

The final paired report should fill the following fields with exact fractions,
not rounded-only percentages:

| Evidence | Fresh baseline | Enriched | Delta |
| --- | ---: | ---: | ---: |
| Affiliation evidence mass / expected paper mass | pending | pending | pending |
| PA-035 activation-eligible institution mass / expected paper mass | pending | pending | pending |
| Unresolved affiliation share count and mass | pending | pending | pending |
| Unresolved institution share count and mass | pending | pending | pending |
| Comparable citation cohort count / eligible cohort | pending | pending | pending |
| Reviewed field ledgers / field ledgers | pending | pending | pending |
| Certified canonical years | pending | pending | pending |

The 2026-08-31 values remain a historical reference column only. They must not
serve as the baseline denominator for the fresh enrichment pair.
