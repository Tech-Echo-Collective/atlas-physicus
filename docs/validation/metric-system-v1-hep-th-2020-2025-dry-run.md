# Metric System v1 bounded `hep-th-v1` 2020–2025 dry run

Date: 2026-08-30

Status: **raw acquisition complete; canonical materialization stopped; Joint
Activation Gate withheld**.

This report records a staging-only trial. It is not a metric release, ranking,
production backfill, or claim of complete publication-year coverage.

## Safety boundary

- Scope: exactly `hep-th-v1`, calendar acquisition windows 2020–2025.
- Providers: official INSPIRE and arXiv endpoints.
- INSPIRE query boundary: article records whose INSPIRE earliest-record date
  (`de`) falls in the selected year.
- arXiv query boundary: `cat:hep-th` records whose submission date falls in the
  selected year.
- Output: immutable content-addressed provider pages outside the repository.
- Database, canonical entity, production cursor, metric, and public-layer
  writes: none.

The INSPIRE query-version label was found to say `publication-year-v1` even
though the exact query uses `de`. The source label is corrected to
`earliest-record-date-v1`. The completed artifact retains the pre-correction
label, but its exact query string, query checksum, endpoint, page checksums, and
provider totals remain recorded. The loader accepts only this exact legacy
label when every other partition identity field and checksum matches, then
normalizes it in memory to the corrected label. It must not be interpreted as
a certified publication-year cohort.

## Acquisition result

| Year | INSPIRE records | arXiv records |
| --- | ---: | ---: |
| 2020 | 6,881 | 7,213 |
| 2021 | 6,508 | 7,127 |
| 2022 | 6,735 | 7,167 |
| 2023 | 7,165 | 7,309 |
| 2024 | 7,595 | 7,790 |
| 2025 | 8,555 | 8,167 |
| **Total** | **43,439** | **44,773** |

- Provider occurrences: **88,212**.
- Verified content-addressed pages: **628**.
- Provider/year partitions complete: **12 of 12**.
- Within-partition duplicate source occurrences: **0**.
- Final manifest checksum:
  `e3dba5492e0dee3fb0b359cd90acd9cc07991e83b89cb6f16c49b498c4e65536`.
- Read-only evidence-analysis report checksum:
  `9ea90c592c69c91a55195f7fee5dd2fa34f20d2fd8f7722da6139703a9016864`.
- Page checksum, manifest checksum, page-count, partition-count, and parse
  failures: **0**.

The first run stopped safely after a transient arXiv failure at 2025 offset
4,600. Failed manifest
`58f1607aef0219e7e8811d14edc1e2efc4c6e63dba16c6564bb9438f86b37600`
recorded the checkpoint. The finalized loader verified and skipped all eleven
complete partitions, persisted their partition states, and fetched only the
remaining 2025 arXiv pages. The successful manifest reused 592 previously
verified pages and added 36.

## Raw evidence diagnostic

Identifier union by arXiv, DOI, and INSPIRE identifiers produced **47,726 raw
paper candidates**: 40,469 cross-provider components, 4,290 arXiv-only, and
2,967 INSPIRE-only. These are candidate components, not reviewed canonical
paper identities. Fourteen components contain a same-provider collision and
remain unresolved.

| Evidence | Raw diagnostic | Activation evidence |
| --- | ---: | ---: |
| Author slots | 142,310 | not materialized |
| Slots with paper-time affiliation evidence | 129,236 (90.813%) | not certified |
| Fractional paper mass with affiliation evidence | 42,604.726 / 47,726 (89.269%) | below 90% |
| Fractional mass with a structured institution reference | 40,720.127 / 47,726 (85.321%) | not canonical |
| Canonical resolved institution mass | 0 | 0% |
| Slots with a provider person anchor | 131,175 (92.176%) | not identity-reviewed |
| Raw non-self citation-count presence | 43,436 / 47,726 (91.011%) | 0% comparable |
| Raw provider-category mapping coverage | 90.509% | 0% reviewed |
| Metric-certified complete years | 0 | 0 of 6 |

Unresolved or missing raw boundaries include:

- 13,074 author slots without paper-time affiliation evidence;
- 4,951 slots with an affiliation string but no structured institution
  reference;
- 11,135 author slots without a provider person anchor;
- seven paper candidates without an author slot;
- 4,224 unique structured INSPIRE institution references with no reviewed
  canonical institution projection;
- 58,087 unique textual affiliation values requiring resolution/review.

The equal-author raw diagnostic conserves exactly one paper unit for all 47,719
candidates that contain authors. Raw affiliation evidence plus explicit
missing mass also has zero conservation failures. No authorship, affiliation,
researcher, or institution was materialized by this diagnostic.

## Field conservation

The selected raw candidate ledgers use:

- ontology `physics-field-ontology-v1`;
- mapping `provider-field-mapping-v1`;
- weighting `provider-evidence-conservation-v2`;
- reconciliation `cross-provider-field-reconciliation-v1`.

Across 47,726 candidate ledgers:

- assigned field mass: **44,360.571**;
- explicit unmapped mass: **3,365.429**;
- assigned plus unmapped mass: **47,726**;
- conservation violations: **0**.

This is a deterministic raw-ledger check. Reviewed field-attribution coverage
is still zero, and the `hep-th-v1` conditioned acquisition cannot by itself
validate the broad-field taxonomy required by Diversity.

## Date, Impact, and Momentum readiness

Connector candidates contain day precision for 47,253 papers, month precision
for 106, and year precision for 367. There are 18,751 publication-year versus
selected-date-year mismatches and 3,369 selected candidates whose normalized
publication year falls outside 2020–2025. A reviewed cross-provider title,
publication-date, precision, and document-type merge policy is therefore
required before a metric year can be certified.

Raw field/year/document grouping yields 232 Impact cohort candidates. Their raw
sizes range from 1 to 9,266 papers (median 67); 122 have at least 50 papers.
**Zero** cohorts are comparable or certified: the database has no timestamped
exact 24-month, common-cutoff, non-self-citation observation lineage for this
trial.

The raw `hep-th` weight mass is 9,859.480 for 2020–2022 and 12,951.465 for
2023–2025, above the count floor for both Momentum windows. Momentum readiness
is still false because no year is metric-certified, paper-time affiliations
are not materialized, same-field peer cohorts are not certified, and the
bibliographic year boundary is unresolved.

## Materialization stop condition

Canonical backfill stopped after acquisition because proceeding would require
durable policy or authority decisions that are not currently approved:

1. canonical title, publication-date/precision, and document-type precedence
   remains provider-order dependent;
2. the institution resolver promotes reviewed ROR authority, while this corpus
   primarily exposes INSPIRE institution references; no reviewed INSPIRE ↔ ROR
   authority/crosswalk and promotion policy exists;
3. no approved acquire-first replay adapter imports immutable staged pages into
   canonical materialization without coupling provider acquisition and writes;
4. citation persistence does not represent timestamped non-self counts at a
   common exact cutoff;
5. provider field evidence has not been independently reviewed;
6. raw provider completion is not a persisted metric-year certificate.

Per project policy, these contradictions were not resolved by guessing.

## Joint Activation Gate result

The exact-five gate returns **WITHHELD**. Its quantitative and validation
blockers are:

- fractional affiliation evidence is below 90%; even before canonical
  resolution, another **348.674 paper-equivalent units** are required;
- canonical institution coverage is 0% against 95%; at least **45,339.7
  paper-equivalent units** must resolve canonically. Structured raw references
  currently cover at most 40,720.127, a **4,619.573-unit** gap before review;
- comparable citation coverage is 0% against 90%; at least **42,953.4 eligible
  paper-equivalent units** need common-cutoff evidence;
- reviewed field coverage is 0% against 90%; at least **42,953.4 units** need
  reviewed attribution, and a broader reviewed corpus is still required for
  Diversity;
- metric-certified complete years are 0 of 6;
- fractional attribution, selected-ledger conservation, normalization,
  citation maturity, full reconstruction provenance, and system-level replay
  have not been reviewed on a canonical materialization.

Metric-specific result:

- **Activity:** withheld; no canonical institution attribution, three certified
  years, or eligible peer normalization cohort.
- **Impact:** withheld; 0 certified comparable cohorts and no exact cutoff.
- **Connectivity:** withheld; no canonical paper-time institution graph.
- **Diversity:** withheld; 0 reviewed field coverage, and `hep-th-v1` is not a
  reviewed broad-field taxonomy.
- **Momentum:** withheld; 0 certified years despite sufficient raw window mass.

All five remain jointly withheld. No activation manifest or live-calculated
observation was created.

## Smallest safe next action

Do not repeat or broaden acquisition yet. First review and record the
bibliographic merge/cohort policy and the INSPIRE-institution authority and ROR
crosswalk policy. Then implement a staging-only import/replay adapter and test
it on a bounded reviewed sample from these immutable pages. Independently label
affiliation, institution, identity, and field evidence before attempting a
canonical six-year replay. `hep-th-v1` alone cannot clear the existing
Diversity gate.

## Production verification

After the staging trial, the Railway API remained healthy at runtime
`3.0.5-alpha`, dataset `live-20260829T185718Z-23637742`, update sequence 9. Both
provider cursors remained healthy, metric recalculation remained idle, and the
public metric endpoint still returned **zero observations**.
