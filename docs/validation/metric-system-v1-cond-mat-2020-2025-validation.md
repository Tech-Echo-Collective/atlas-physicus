# Metric System v1 bounded `cond-mat-validation-v1` validation

Date: 2026-09-04

Status: **staging acquisition and deterministic replay complete; all five
metrics and the field-conditioned Joint Activation Gate withheld; production
unchanged**.

This is the bounded Condensed Matter validation requested for six closed
calendar windows, 2020–2025. It does not activate metrics, write a database,
change production, begin Full Physics loading, or begin v3.1.

## Boundary and immutable lineage

- Acquisition scope: `cond-mat-validation-v1`, classified
  `field-conditioned`.
- INSPIRE query boundary: exact `subject:"Condensed Matter"` article records,
  partitioned by provider earliest-record date for each year.
- arXiv query boundary: exact `cat:cond-mat.*`, partitioned into non-overlapping
  Q1–Q4 `submittedDate` windows for each year. The quarterly boundary replaces
  the rejected annual attempt whose 2020 total was 20,870 and whose provider
  stream failed at offset 10,000. Every observed quarterly total was below
  10,000; the maximum was 6,391.
- Source acquisition manifest version:
  `cond-mat-validation-v1-historical-raw-acquisition-manifest-v2`.
- Source manifest identity:
  `484880ef2fd03163b393fff2a38a1901340550d5423da058c43f5210c9ed0384`.
- Replay version:
  `cond-mat-validation-v1-historical-replay-materialization-v2`.
- Relationship projection version:
  `cond-mat-validation-v1-historical-relationship-projection-v2`.
- Merge-plan version: `historical-paper-merge-plan-v1`; merge-plan digest:
  `8a7ffbfe9910ae90d63ce82a38d0c2bb6b6348f16e37d5139ef776d83a4f849b`.
- Replay digest:
  `55d99317efe31ab549f59b909caacbbea78e6b313e9f2fc65e5d378b9971caf4`.
- Replay-bundle identity and field-conditioned `dataSourceVersion`:
  `26c51e77b696e2d4d3636074107f0751be9289b9e95f62f837abd8b106f8376f`.
- Content-addressed replay report:
  `8d9b04e2616ee8450b7aef919f3dfded2bcb8004c9f4c031fb6aade96f3409cd`.
- Cutoff upper bound: `2026-09-04T13:36:21.011160+00:00`.

The 2.6 GiB raw staging tree and 3.0 GiB replay tree remain in durable external
evidence storage, outside Git. Replay used no provider network, database,
source cursor, production service, or metric write.

## Raw acquisition result

| Provider | Window | Records | Pages |
| --- | ---: | ---: | ---: |
| INSPIRE | 2020 | 4,567 | 19 |
| INSPIRE | 2021 | 4,949 | 20 |
| INSPIRE | 2022 | 5,300 | 22 |
| INSPIRE | 2023 | 5,604 | 23 |
| INSPIRE | 2024 | 6,004 | 25 |
| INSPIRE | 2025 | 5,774 | 24 |
| arXiv | 2020 | 20,870 | 211 |
| arXiv | 2021 | 20,470 | 207 |
| arXiv | 2022 | 19,730 | 198 |
| arXiv | 2023 | 20,946 | 212 |
| arXiv | 2024 | 21,965 | 220 |
| arXiv | 2025 | 24,115 | 243 |
| **Total** | **2020–2025** | **160,294** | **1,424** |

INSPIRE contributed 32,198 records and arXiv 128,096. All 30 immutable
partitions—six annual INSPIRE and 24 quarterly arXiv partitions—are complete.
Every partition's unique-ID count equals its exact provider total, with zero
within-partition duplicates and zero count mismatches.

These are complete raw provider query windows. They are not canonical
publication-year certificates: provider date fields describe different events,
and the replay deliberately did not select a canonical cohort date.

## Canonical replay result

| Artifact | Rows | SHA-256 |
| --- | ---: | --- |
| Source occurrences | 160,294 | `0c76c187192ea8292822e0533d6cdb6caa1facab13592e551190914b16ed6dc9` |
| Paper components | 129,464 | `dc9224a2fc752f9c519834df94f572d454790ad55bf9103a884eff76773e146f` |
| Citation observations | 32,198 | `37ec3f0d7cf8ed1974d70f5e61a87e434c0a66e28b7a711c0c0b8462a9b5970a` |
| Field ledgers | 129,464 | `033e3c1d033c5d51e50d67f4afc6ab56aa6866694728f881a2a6fab45fdc60da` |
| Researcher appearances | 652,055 | `269c2efddc0c299e44a0c9cf24125cfb1133b92be321750e2e3916828c4c3768` |
| Paper-time affiliation shares | 700,661 | `36b3550df9af05c2bf2e14eb53fc37128e99fdbe11919f6f46d16b8391c29629` |
| Institution authority anchors | 1,667 | `4d4b0675bfe9f4805cb935e998c2fb5413c95ab55a1efea8756046b90972a1a3` |
| Fractional attribution ledgers | 129,464 | `2c2a5b7e7a9bf92d30513c0267203379c4bdd3812126af101621b781fb3aaf1e` |

The merge planner produced 129,110 `matched` and 354 `needs_review` paper
components. It formed 30,791 multi-record components: 30,746 cross-provider
and 45 conservative same-provider components. The other 98,673 components are
singletons. No conflicted identity was forced into a canonical paper.

Every component has valid normalized event-date evidence: **129,464 / 129,464
(100%)**, comprising 371,176 valid date facts and zero invalid facts. This is
event-date coverage only. Canonical publication/cohort dates selected: **0**.

## Attribution, affiliations, identities, and institutions

Fractional Attribution v1 expected 129,464 paper units and evaluated 129,416.
Forty-eight units remain explicitly unevaluable because their provider author
projection is non-unique. Exact mass accounting is:

- paper-time affiliation-evidence mass:
  `575138025696274847 / 17485049181600` = 32,893.131711 units;
- no-affiliation-evidence mass:
  `1687707099189670753 / 17485049181600` = 96,522.868289 units;
- unmaterialized mass: `48 / 1` units;
- expected mass: `129464 / 1` units;
- coverage over the full expected denominator:
  `575138025696274847 / 2263684407246662400` = **25.407165%**;
- minimum additional evidence mass to reach the 90% gate:
  `1462177940825721313 / 17485049181600` = **83,624.468289** units.

Affiliation and attribution conservation both pass with zero failures. No
scientific mass was reassigned from missing or unresolved evidence. All 129,416
evaluated units remain withheld from canonical allocation; the allocated mass
is `0 / 1`.

| Unresolved relationship evidence | Count |
| --- | ---: |
| Shares with no affiliation evidence | 510,576 |
| Shares with unresolved affiliation | 189,863 |
| Shares with ambiguous affiliation | 222 |
| Non-unique author projections | 48 paper ledgers |
| Researcher appearances with no authority identifier | 516,108 |
| Researcher appearances with unreviewed authority evidence | 135,945 |
| Researcher appearances with conflicting authority identifiers | 2 |
| Paper components requiring identity review | 354 |

The replay found 34,541 direct ROR alignments across 1,667 distinct provider
authority anchors. Those are source assertions, not canonical institutions.
The current canonical ROR replay boundary is explicitly `hep-th-v1`-only, so
it cannot consume this distinct Condensed Matter replay without a separately
versioned, reviewed staging generalization.

Accordingly, activation-eligible canonical-institution coverage is **not
measurable (`None`) over the known 129,464-paper denominator**, not zero. The
95% target would require at least 122,990.8 paper units, but the current
canonical numerator and gap cannot be claimed. Canonical institutions and
canonical researchers materialized by this replay are both zero; provider IDs
were never promoted as substitutes.

## Field, citation, history, and normalization evidence

- Reviewed field ledgers: **0 / 129,464 (0%)**; all 129,464 are unreviewed.
  Passing 90% requires at least 116,518 reviewed components, a deficit of
  **116,518**.
- Ledgers with explicit unmapped mass: **55,228 / 129,464 (42.658963%)**.
- Assigned field mass: **103,525.748740**; explicit unmapped field mass:
  **25,938.251260**. Their sum is one unit per paper across 129,464 ledgers.
- Multi-field ledgers: **57,763 / 129,464 (44.617036%)**.
- Field-conservation failures: **0**.
- The exact INSPIRE category `Condensed Matter` has no rule in
  `provider-field-mapping-v1`; its mass remains explicit rather than being
  silently reassigned. Adding a rule requires a reviewed mapping-version
  decision and is not treated as a bug fix.
- Raw citation observations: 32,198; canonical components with raw and
  provider-reported non-self evidence: **32,195 / 129,464 (24.867917%)**.
- Common-cutoff comparable citation evidence, using the activation denominator:
  **0 / 129,464 (0%)**. The replay's manifest-completion timestamp is only an
  upper bound and is not a simultaneous observation cutoff. Passing 90%
  requires at least 116,518 comparable components, a deficit of **116,518**.
- Mature certified Impact cohorts: **0**; minimum field/year/age/document-type
  cohort size is therefore unavailable.
- Raw acquisition-complete provider windows: **2020–2025 (6 / 6)**.
- Certified complete canonical metric years: **0 / 6**.
- Momentum window readiness: **false** for both 2020–2022 and 2023–2025.

No activation-eligible institution, country, researcher, field-review, or
citation cohort partition was materialized. Therefore trial-level
normalization cohorts, fitted parameters, degeneracy checks, and per-entity
sanity distributions are **not measurable**, rather than failed numeric
observations. The already tested normalization algorithms were not fitted to
ineligible evidence.

## Five-metric readiness

| Metric | Decision | Exact blockers in this trial |
| --- | --- | --- |
| Activity | **Withheld** | 0/6 canonical years certified; affiliation coverage 25.407165% < 90%; canonical institution coverage not measurable; no eligible entity normalization cohort. |
| Impact | **Withheld** | 0/129,464 common-cutoff comparable papers; zero mature cohorts; citation age/common cutoff not certified; affiliation evidence below threshold. |
| Connectivity | **Withheld** | Canonical researchers and institutions are not materialized; resolved relationship coverage is not measurable; affiliation evidence is below threshold; no three-year canonical window is certified. |
| Diversity | **Withheld** | 0/129,464 reviewed field ledgers; 55,228 ledgers retain unmapped mass; no broad-Physics breadth review; the acquisition boundary is field-conditioned. |
| Momentum | **Withheld** | Both canonical three-year windows are uncertified; stable canonical entity/affiliation history and eligible same-field normalization cohorts are unavailable. |

Sufficient raw record volume does not cure the missing reviewed evidence. No
metric formula or scientific threshold was changed, and no metric observation
was calculated or published.

## Field-conditioned Joint Activation Gate

The exact current gate was evaluated with the current five definitions and
algorithm versions, passing deterministic replay and conservation, the bundle
identity above as this field's `dataSourceVersion`, and no invented aggregate
across fields. Coverage inputs were affiliation 25.407165%, canonical
institution `None`, comparable citation 0%, and reviewed field attribution 0%.

Result: **WITHHELD** for Activity, Impact, Connectivity, Diversity, and
Momentum together. Exact gate reasons:

1. `cond-mat-validation-v1` cannot validate the broad-field Research Diversity
   boundary;
2. the acquisition boundary is not certified as broad Physics evidence;
3. the Diversity breadth-review version does not match the contract;
4. broad-field Research Diversity review has not passed;
5. paper-time affiliation coverage is below 90%;
6. the gate reports canonical institution coverage below 95%; the measured
   input is `None` because coverage is not measurable for this replay;
7. comparable citation coverage is below 90%;
8. reviewed field-attribution coverage is below 90%;
9. six-year closed-window canonical historical coverage is not validated;
10. citation-age and common-cutoff handling are not validated;
11. metric-specific normalization validation has not passed;
12. reconstruction provenance remains incomplete for canonical institutions,
    cohort dates, and citation observation timing.

This field-conditioned result is not averaged or unioned with `hep-th-v1` and
does not create a combined `dataSourceVersion`. Full Physics loading is **not
authorized** by this trial. Metric observations created: **0**.

## Concrete implementation fixes and deterministic proof

The bounded run exposed two implementation constraints and fixed them without
changing metric science:

1. The arXiv annual 2020 stream crossed the provider's 10,000-offset boundary.
   Condensed Matter acquisition now uses exact, non-overlapping quarterly
   partitions, versioned v2 state, 100-record pages, the existing three-second
   minimum interval, segment-specific resume state, strict segment/query
   checks, and a fail-closed `total < 10,000` assertion. Existing `hep-th-v1`
   paths and serialization remain unchanged.
2. Canonical merge planning rescanned every evidence edge for every component.
   Evidence is now indexed once to its final union-find root, preserving the
   exact per-component sort order. The prior full replay remained unfinished
   after 29 minutes; the corrected replay completed in **171.34 seconds**—more
   than 10.1 times faster than that unfinished lower bound. A second complete
   execute took **181.48 seconds** and verified every existing artifact byte.

Both complete replays produced identical source-manifest, merge-plan, replay,
bundle, report, and per-artifact checksums. The pinned legacy `hep-th-v1`
source, replay, and bundle checksum regression also passed, demonstrating that
the optimization did not change existing output bytes.

Focused validation passed:

- 113 historical acquisition, canonical replay, connector, and field-mapping
  tests;
- Ruff on the affected implementation and tests;
- mypy on the affected implementation;
- whitespace/diff integrity checks.

## Smallest evidence work still required

Do not start Full Physics loading from this result. The smallest defensible next
steps are separate reviewed evidence tasks: version a Condensed Matter-compatible
target-only ROR projection; review the existing field ledgers and decide a new
provider mapping version for currently unmapped exact categories; acquire
common-cutoff, source-timestamped non-self citation evidence and form mature
cohorts; select and review canonical cohort dates; then certify the six years
and both Momentum windows. A separately reviewed `broad-physics` acquisition is
still required for public Joint Activation.
