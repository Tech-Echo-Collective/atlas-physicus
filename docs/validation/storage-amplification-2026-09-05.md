# Bounded PostgreSQL amplification investigation — 2026-09-05

Status: **compact certification prototype validated; Storage Budget Gate
WITHHELD; no production migration or broader load authorized**.

This investigation reused the existing 474-paper paired certification sample.
It acquired no scientific data, ran no broad replay, changed no scientific
policy/threshold, and activated no metric. Production reads and an isolated
local PostgreSQL benchmark are separate measurements.

## Production byte accounting

Read-only Railway console measurements around `2026-09-05T00:48:30.305589Z`,
PostgreSQL 18.6, Debian x86_64. Separate bounded read-only transactions used
60-second statement and 2-second lock timeouts; this is not one atomic snapshot.
No production writes occurred.

| Measure | Bytes |
| --- | ---: |
| Database | 306,771,647 |
| Public tables, including TOAST | 241,270,784 |
| Public target-table indexes | 55,803,904 |
| Public relations total | 297,074,688 |
| Mounted volume capacity | 4,685,873,152 |
| Mounted volume used | 482,541,568 |
| Volume use outside public relations | 185,466,880 |

The table below contains exact counts and PostgreSQL-native physical bytes,
not estimated live-row counts. Heap is the main fork; auxiliary is FSM/VM/init;
TOAST includes its own indexes; index is the target table's indexes. Thus
`heap + auxiliary + TOAST + index = total` without double-counting. Approximate
bytes/row is total divided by rows, including indexes and allocation overhead.
Empty tables have allocated bytes but no meaningful bytes/row. Native function
semantics follow [PostgreSQL's size-function documentation](https://www.postgresql.org/docs/17/functions-admin.html#FUNCTIONS-ADMIN-DBSIZE).

| Relation | Rows | Heap | Auxiliary | TOAST | Index | Total | Bytes/row |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `raw_entity_records` | 15708 | 22274048 | 32768 | 68968448 | 3661824 | 94937088 | 6043.9 |
| `source_snapshots` | 27 | 24576 | 24576 | 60358656 | 49152 | 60456960 | 2239146.7 |
| `entity_search_terms` | 87078 | 17571840 | 32768 | 8192 | 27164672 | 44777472 | 514.2 |
| `paper_affiliations` | 15838 | 29605888 | 32768 | 24576 | 5103616 | 34766848 | 2195.2 |
| `authority_identifiers` | 22598 | 10264576 | 32768 | 8192 | 6676480 | 16982016 | 751.5 |
| `identity_resolutions` | 15708 | 9945088 | 32768 | 8192 | 4423680 | 14409728 | 917.3 |
| `authorships` | 9013 | 4374528 | 32768 | 8192 | 3129344 | 7544832 | 837.1 |
| `external_resources` | 5577 | 4055040 | 32768 | 8192 | 2080768 | 6176768 | 1107.5 |
| `researchers` | 8485 | 4923392 | 32768 | 8192 | 1073152 | 6037504 | 711.6 |
| `paper_fields` | 1627 | 3112960 | 32768 | 491520 | 286720 | 3923968 | 2411.8 |
| `papers` | 823 | 1720320 | 32768 | 1040384 | 229376 | 3022848 | 3673.0 |
| `resource_checks` | 6277 | 974848 | 32768 | 8192 | 1056768 | 2072576 | 330.2 |
| `identity_reviews` | 440 | 106496 | 24576 | 8192 | 180224 | 319488 | 726.1 |
| `update_runs` | 27 | 24576 | 24576 | 172032 | 49152 | 270336 | 10012.4 |
| `dataset_updates` | 27 | 24576 | 24576 | 90112 | 16384 | 155648 | 5764.7 |
| `metric_observations` | 0 | 0 | 0 | 8192 | 81920 | 90112 | — |
| `affiliations` | 0 | 0 | 0 | 8192 | 32768 | 40960 | — |
| `citations` | 0 | 0 | 0 | 8192 | 32768 | 40960 | — |
| `institutions` | 0 | 0 | 0 | 8192 | 24576 | 32768 | — |
| `source_cursors` | 2 | 8192 | 0 | 8192 | 16384 | 32768 | 16384.0 |

The 20 listed relations are the relevant large/state relations, not every
small ontology/configuration table included in the public total. Certification
decisions have **no deployed production table**. The historical replay and
3.437 GB expanded certification stream are external artifacts, not part of this
database. Zero citation rows does not mean zero observed citations: some raw
normalized records contain observation evidence, without certified comparable
cohorts. Profile affiliations and paper-time affiliation shares are separate.

Largest individual target indexes:

| Index | Bytes | Recorded scans |
| --- | ---: | ---: |
| `uq_entity_search_terms_entity_type` | 13,000,704 | 1,834 |
| `pk_entity_search_terms` | 8,192,000 | 0 |
| `ix_entity_search_term_lookup` | 3,424,256 | 3,389 |
| `pk_identity_resolutions` | 2,203,648 | 1,968 |
| `uq_raw_entity_records_source` | 1,941,504 | 0 |
| `pk_authority_identifiers` | 1,900,544 | 0 |
| `pk_paper_affiliations` | 1,777,664 | 1,964 |
| `ix_entity_search_terms_entity_id` | 1,687,552 | 0 |

Search indexes occupy 27.165 MB, 48.68% of all target-index bytes. A zero scan
counter is not removal evidence: primary/unique constraints enforce integrity,
and the statistics horizon/workload is not a representative query benchmark.
No index was removed.

## Amplification and Hot/Cold boundary

The two raw relations occupy **155.394 MB (52.31%)** of public relations.
`updates/engine.py` stores full provider pages in snapshots, then raw paper and
author occurrences with normalized attributes and provenance. Each author
appearance has a source record/resolution; snapshot-bound IDs preserve later
occurrences. Therefore 15,708 raw records are not 15,708 canonical papers.
Native counts show 1,770 INSPIRE paper occurrences for 929 distinct provider
record IDs and 13,786 researcher occurrences for 9,082 provider IDs; arXiv has
43/43 paper and 109/109 researcher occurrences/IDs. These are provider IDs,
not canonical identities. Of 15,838 affiliation shares, 10,612 are current and
5,226 (33.0%) superseded. History retention is measurable, not a bloat diagnosis.

Search stores whole names/identifiers plus token variants, repeating text and
string IDs across rows/indexes (`search_index.py`). Affiliation materialization
retains current and superseded snapshot-based shares with exact fractions,
decimal projections, versions, and evidence. Field reconciliation repeats a
full ledger on the paper and each field link. Authority IDs also appear in
canonical JSON and indexed authority rows. These are representation/history
costs, not permission to discard scientific evidence.

Stored-datum accounting highlights 127,219,997 bytes of snapshot/raw payloads,
12,415,542 of affiliation provenance, 5,069,604 of affiliation resolution
evidence, 6,057,010 of authority provenance, and 7,686,552 of raw normalized
attributes. **`pg_column_size` can measure compressed datums**; these numbers
are neither uncompressed JSON sizes nor independently recoverable physical
savings. They overlap table accounting. The older sizing report's “logical
bytes” terminology should be read with this correction.

| Consumer | Hot requirement | Cold/audit candidate |
| --- | --- | --- |
| Snapshots/raw records | IDs, source/time/version, checksums/references, required normalized evidence | Full raw payloads and superseded expanded evidence |
| Affiliations | Current exact shares, unresolved mass, status, entity and source links | Superseded full rows and detailed assertion traces |
| Identity/review state | Current matching/review result and compact provenance | Historical expanded decision traces |
| Papers/authorships/fields | Canonical entities, dates, links, conserved weights, evidence references | Duplicated full reconciliation ledgers |
| Search/authority | Indexed normal-query and identity-resolution projections | No wholesale externalization; profile duplication first |
| Citation/metric state | Necessary cutoff/history, current observations and proof references | Expanded reconstruction/debug archives |
| Updates/cursors | Current checkpoints and compact lineage | Expanded historical affected-entity/validation ledgers |
| Certification/replay | Current status/reason/version and verified proof references | Full decision/input/replay archives, already external today |

Entire raw relations are **not** cold: field reconciliation reads
`RawEntityRecord.attributes_json`; identity/readiness checks use attributes and
external IDs; provenance APIs require raw-record links. Whole-object ORM reads
also fetch payloads incidentally. Dual-read/recovery and compact live evidence
must exist before any externalization. Eliminating incidental payload reads
would improve I/O, not by itself reduce stored bytes.

## Small compact-state prototype

The private benchmark used PostgreSQL 17.11 on local arm64, not Railway, and
only the existing **9,999 decisions for 474 papers**. The scratch runtime was
installed for this benchmark, not registered as a background service. No scientific rules were
rerun. Expanded JSONB is a hypothetical baseline, not a deployed certification
schema. Both alternatives retain equivalent paper/subject lookup indexes.

Compact storage keeps queryable status, kind, reason, version, IDs, per-decision
digest and audit ordinal; shared text/reason dictionaries and batch metadata
are included. The complete original decision JSON, including provenance and
unknown fields, remains in one deterministic checksum-verified gzip archive.

| Measured component | Expanded | Compact |
| --- | ---: | ---: |
| Heap main bytes | 16,564,224 | 1,622,016 |
| Auxiliary + TOAST bytes | 32,768 | 81,920 |
| Index bytes | 1,966,080 | 1,368,064 |
| Total hot PostgreSQL bytes | 18,563,072 | 3,072,000 |
| Bytes per paper | 39,162.60 | 6,481.01 |
| Bytes per decision, all support tables included | 1,856.49 | 307.23 |
| Decimal MB per 10,000 papers, certification only | 391.626 | 64.810 |

This is **83.45% less hot certification-component storage**. Compact totals
include all four tables, 3,330 dictionary rows, 14 reason rows, batch metadata,
and every associated index. The cold archive is 1,056,945 bytes; source JSONL
is 12,233,044 bytes. Neither is silently counted as PostgreSQL hot savings.

SQL readback reconstructs the same batch and every original decision exactly.
Observed states remain 2,305 certified, 1 conflicted, 6,007 insufficient, and
1,686 needing review. Tests separately retain all five allowed states,
including withheld; absent/null/false/zero distinctions; exact field and
attribution mass; reasons, versions and provenance. Missing/corrupt archives
or modified hot projections fail closed. Hot rows or recovered ordinary JSON
cannot enter calculators directly; a reconstructed typed Activity certificate
retains its proof digest and calculation result. No certification was promoted.
A separate bounded local provenance check recovered 11,742 reference
occurrences/1,033 unique references with zero unresolved links. It verified
406 referenced files and all 447 retained manifest artifacts (9,209,331 bytes),
635 provider-record fragments, and 398 authority references without network
requests or replay. This proves local byte/link recovery—not scientific review,
object-store durability, or a production disaster-recovery rehearsal.

## Capacity estimate and gate

A complete compact canonical schema has **not** been measured. To avoid
claiming unjustified savings, this estimate retains every byte of current
public state—including raw payloads and necessary mixed attributes—and adds
the measured compact certification component. It is a conservative retained-
layout scenario, not a final compact-hot design or representative marginal cost.

```text
fixed = 482,541,568 - 297,074,688 = 185,466,880 bytes
per-paper = 297,074,688 / 823 + 3,072,000 / 474
          = 367,446.611686 bytes
steady estimate = 1.25 × (fixed + paper_count × per-paper)
```

Before/after certification choice changes the combined public-state ratio from
**4,001.282 to 3,674.466 MB per 10,000 papers**, before fixed overhead and the
25% contingency. It does not turn the measured 155.394 MB raw relations into
entirely disposable storage.

| Papers | Expanded-certification scenario, GB | Compact-certification scenario, GB |
| ---: | ---: | ---: |
| 10,000 | 5.233436 | 4.824916 |
| 100,000 | 50.247858 | 46.162660 |
| 250,000 | 125.271896 | 115.058900 |
| 500,000 | 250.311957 | 229.885966 |

All scenarios include fixed measured non-public use and 25% contingency.
Against actual 4,685,873,152-byte capacity, the 60% steady ceiling remains
2,811,523,891 bytes; the 80% peak ceiling remains 3,748,698,521 bytes. The
illustrative steady-only ceiling improves from **5,157 to 5,616 total papers**,
not additional papers. **No larger capacity is certified safe or approved.**
Future citation/canonical state, update-history growth, migration/WAL peaks,
corpus-dependent author/institution fan-out, and PostgreSQL 17/18/platform
differences remain unmeasured. No current calculation justifies a 56k-paper
Hobby capacity claim.

**Storage Budget Gate: WITHHELD.** The 474/823-paper samples are below the
10,000 representative-final-schema requirement; expected final evidence rows,
reviewed target population and isolated restore remain unvalidated. The shown
larger scenarios exceed current safe capacity. The independent Scientific
Joint Gate also remains withheld; public live metric observations remain zero.

## Smallest next action and evidence

Prepare an additive artifact-reference/dual-read pilot for one existing bounded
batch, with verified storage and isolated restore first. Retain all inline
production evidence. Future new-batch external writes must verify before the
database reference/cursor advances. Only after equivalence and restore checks
should a separately approved migration retire payloads; vacuum/reuse or a
controlled rewrite may be needed to reclaim physical space. Do not execute
millions of rewrites, broad replay, or whole-database schema changes for this
investigation. Measured certification savings are 326.816 MB/10k papers; raw
externalization savings remain unmeasured, not 155.394 MB by assumption.

Read-only accounting is reproducible from `storage/audit.py`; the private-socket,
exact-source-hash-limited benchmark is `backend/tools/benchmark_compact_storage.py`.
Evidence is retained beneath external `physics-atlas-evidence/storage-compact-2026-09-05/`:

| Artifact | SHA-256 |
| --- | --- |
| `production-summary.json` | `101125b2d526215a021fc1dd61b404636ca1dfafa85349d31fee6b44dda162ea` |
| `production-relations.csv` | `3e7f42cfffe5d339b69da6ada013dbc8c5a691b8cdf06b7321ce55837d49f551` |
| `production-indexes.csv` | `0fbd573a59f83d5c1b4cf464c8fb3f7c5084ad0839192eb84ee86220f638680e` |
| `production-stored-datums.csv` | `98a8198b31986bcc0fba04f93fa12a840499c8816347f5a6004a346d61a54a41` |
| `production-fanout.json` | `7e243fd0a637621bffee8f5ac4ce6d8986ea72cbca15031b194dc5133a619810` |
| `provenance-check.json` | `db80d35d27acc5404d0fe57aba4b6f9eda13f2d76d4fd96cdc07ab9c134f18ef` |
| `postgres-prototype-v1/measurement.json` | `a637eef189f23b1b1701aeb39b4d1b4d1065c85eadeb7e7d2e61de7e1f7c9e26` |
| Existing source decisions | `b21157332f997ad41bc251ff3a317faba6281892ec21d3e35d49905890ba63fb` |
| Compact cold archive | `84c61fd66d8cf4d0c8ce0b86a4ca6f9556a529d6ff584a5024ec59f5933ab0a2` |

Hashes can be checked with `shasum -a 256` against the named retained files;
the source remains the final paired capture documented in the
[certification report](scientific-evidence-certification-2026-09-05.md).
All 398 backend tests pass (9.28 seconds), including storage/scientific
regressions; strict mypy passes 78 source files and Ruff formatting/lint passes
119 files including benchmark tools. The existing Starlette/httpx deprecation
warning remains. At `2026-09-05T00:56:21.780483Z`, production API/database were
healthy; INSPIRE/arXiv had zero consecutive failures and September 4 latest
successes. One resource-check failure remains. Post-push CI is pending; no
frontend changes were made.
