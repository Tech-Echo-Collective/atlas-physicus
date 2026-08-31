# Metric System v1 bounded `hep-th-v1` canonical replay

Date: 2026-08-31

Status: **staging replay complete; Joint Activation Gate withheld; production
unchanged**.

This report supersedes the raw-evidence estimates in the
[acquisition dry-run report](metric-system-v1-hep-th-2020-2025-dry-run.md) for
canonical-replay readiness. It does not activate a metric, certify a production
backfill, widen the corpus, or begin v3.1.

## Boundary and lineage

- Acquisition scope: exactly `hep-th-v1`, closed provider windows 2020–2025.
- Source manifest:
  `e3dba5492e0dee3fb0b359cd90acd9cc07991e83b89cb6f16c49b498c4e65536`.
- Replay bundle:
  `d125a0861df03c5e1e7e20202db06f7d2506e0e8e9fb3fca732e7208f4349d82`.
- Replay digest:
  `2ee93eb14319982d9eff1151a89c0d57bf63e9a50f0d3bda3f534b1083eea376`.
- Replay versions: `hep-th-v1-historical-replay-materialization-v1`,
  `canonical-paper-merge-policy-v1`, and
  `historical-paper-merge-plan-v1`.
- Institution-resolution manifest:
  `4e0f58bdc4d44836e013a2b311998858e4a1894bcecd06d617e2cfa5211ece38`.
- The replay read immutable staged files only. It used no database, production
  cursor, provider network, or production write. The separate exact-ID ROR
  acquisition was bounded to the 2,131 ROR targets already present in staged
  paper-time evidence; it did not search the ROR registry.
- All replay and institution artifact hashes, row counts, manifest self-hashes,
  and idempotent reruns passed.

## Canonical paper and relationship result

| Materialized artifact | Rows |
| --- | ---: |
| Source occurrences | 88,212 |
| Paper components | 47,726 |
| Citation observations | 43,439 |
| Field ledgers | 47,726 |
| Researcher appearances | 142,309 |
| Paper-time affiliation shares | 183,247 |
| Direct ROR authority anchors | 1,857 |
| Fractional attribution ledgers | 47,726 |

The merge planner placed all 88,212 occurrences into 47,726 paper components.
It grouped 80,957 provider records into 40,471 multi-record components: 40,469
cross-provider components and two conservative same-provider components. The
remaining 7,255 provider records are singletons. Of all components, 47,254 are
`matched` and 472 remain `needs_review`; no conflicted evidence was forced into
a canonical identity.

Every component has at least one valid normalized date fact: 249,815 valid
facts and zero invalid facts. This is **100% event-date evidence coverage**, not
a canonical publication-year certificate. Provider dates still represent
different events, so no canonical metric cohort date was selected.

Researcher appearances remain evidence rather than reviewed canonical people:
131,105 have unreviewed authority evidence, 11,143 have no authority identifier,
and 61 contain conflicting authority identifiers. Canonical researcher
materialization therefore remains zero.

## Affiliation and institution result

Fractional Attribution v1 evaluated 47,721 of 47,726 paper units. Five paper
units remain explicitly unmaterialized because their provider author
projections are non-unique. Among the evaluated mass:

- paper-time affiliation evidence mass: **42,601.726004 / 47,726 =
  89.263140%**;
- explicit no-affiliation-evidence mass: **5,119.273996**;
- evaluated conservation failures: **0**;
- relationship and affiliation-evidence mass conservation: **passed**.

Exact target-only ROR acquisition completed for 2,131 of 2,131 identifiers.
Canonical ROR evidence preserves 2,120 active, nine inactive, and two withdrawn
organizations, plus 676 parent, 35 predecessor, and 10 successor relationships.
Predecessor or successor relationships never become automatic statistical
rollups.

All 1,857 direct-ROR replay anchors resolve to canonical child metadata. This is
not the activation denominator. The result separates three coverage views:

| Institution evidence view | Paper mass | Coverage |
| --- | ---: | ---: |
| Any direct authority-linked evidence | 20,228.599731 | 42.384863% |
| Exact canonical child resolution | 20,026.649988 | 41.961719% |
| PA-035 activation-eligible parent/self rollup | 16,689.396051 | **34.969191%** |

The strict activation denominator is all 47,726 paper units. The remaining
31,036.603949 units are withheld. Quantified blockers are:

- no resolved child ROR: 27,492.400269 mass / 122,866 shares;
- missing parent authority metadata: 2,447.994659 / 7,604 shares;
- multiple parent RORs: 804.668188 / 3,032 shares;
- paper identity needing review: 201.949743 / 556 shares;
- inactive or withdrawn child lifecycle: 84.591090 / 224 shares;
- non-unique provider author projection: five paper units.

The parent decision is fail-closed: 1,448 anchors self-roll, 147 roll to one
exact active parent, 160 lack preserved parent metadata, 92 name multiple
parents, and 10 have an ineligible lifecycle state. Institution-resolution
mass conservation passed exactly.

## Field, citation, and historical readiness

- Reviewed field ledgers: **0 / 47,726 (0%)**. All ledgers remain unreviewed.
- Multi-field ledgers: **36,472 / 47,726 (76.419562%)**.
- Assigned field mass: **44,360.570996**.
- Explicit unmapped field mass: **3,365.429004 (7.051563%)**.
- Field-conservation failures: **0**; mapped plus unmapped mass equals 47,726.
- Raw/provider-reported non-self citation presence: **43,436 / 47,726
  (91.011189%)** at component level.
- Common-cutoff comparable citation observations: **0 (0%)**.
- Mature certified Impact cohorts: **0**.
- Raw acquisition-complete years: 2020–2025.
- Canonical metric-certified complete years: **none**.
- Momentum readiness: **false** for both 2020–2022 and 2023–2025.

The replay cutoff `2026-08-30T11:22:14.349248+00:00` is the acquisition
manifest completion upper bound. Individual source-page capture timestamps are
not available, so the replay does not claim simultaneous observation or
historical observable-at-cutoff citation cohorts. Raw counts remain preserved
but cannot enter production Impact.

## Joint Activation Gate

The exact gate was evaluated with current Metric System v1 algorithm versions,
successful algorithm/replay determinism, passing attribution and field-mass
conservation, the replay bundle checksum as `dataSourceVersion`, no asserted
broad-Diversity review artifact, and these activation coverages:

- paper-time affiliation: 89.263140% (minimum 90%);
- canonical institution: 34.969191% (minimum 95%);
- comparable citation: 0% (minimum 90%);
- reviewed field attribution: 0% (minimum 90%).

Result: **WITHHELD** for Activity, Impact, Connectivity, Diversity, and
Momentum together. The exact remaining gate reasons are:

1. `hep-th-v1` cannot validate broad-field Diversity;
2. the Diversity breadth-review evidence version is absent;
3. broad-field Diversity review has not passed;
4. affiliation coverage is below 90%;
5. canonical institution coverage is below 95%;
6. comparable citation coverage is below 90%;
7. reviewed field-attribution coverage is below 90%;
8. six-year canonical historical coverage is not validated;
9. citation age and common-cutoff handling are not validated;
10. metric-specific normalization is not validated;
11. reconstruction provenance is incomplete for canonical cohort and citation
    observation timing.

No activation manifest was prepared. Metric observations created by the replay:
**0**. Public eligibility: **false**.

## Concrete implementation corrections

The replay exposed and corrected bounded defects without changing scientific
definitions:

- arXiv normalization now retains author affiliation and journal-reference
  evidence needed by replay;
- INSPIRE normalization keeps raw and provider-reported non-self citation
  counts separate;
- INSPIRE author, institution, and BAI identifiers are normalized under their
  correct schemes and endpoint shapes;
- materialization no longer positionally zips unrelated multi-valued
  affiliation/ROR arrays or promotes a non-ROR name/INSPIRE identity as a
  canonical institution;
- missing `affiliations` can correctly fall back to preserved
  `raw_affiliations`;
- placeholder author names no longer create false secondary paper merges, and
  BAI conflicts are counted only when evidence genuinely conflicts;
- conservation excludes the five explicitly unevaluable ledgers rather than
  reporting false mass failures;
- paper identities requiring review cannot contribute activation-eligible
  institution mass;
- ROR lifecycle, parent, predecessor, and successor evidence is preserved, and
  ambiguous/missing parent rollup fails closed;
- a reviewed activation is now bound to its exact acquisition scope and data
  source version, preventing a stale release from authorizing a newer dataset.

## Smallest next action

Do not repeat provider acquisition or widen to Full Physics. The next bounded
work is independent review: resolve enough of the 31,036.603949 withheld
institution mass, label field mappings, establish per-page or equivalent common
citation observation cutoffs and mature cohorts, select and review the
canonical cohort-date policy, then certify all six years. Broad-Physics evidence
is still separately required for Diversity. Until every requirement passes in
one reviewed manifest, all five public layers remain withheld.
