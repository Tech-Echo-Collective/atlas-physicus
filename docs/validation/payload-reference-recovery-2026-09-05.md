# Bounded payload-reference recovery pilot — 2026-09-05

Status: **isolated recovery succeeds; production migration not performed;
Scientific Joint and Storage Budget gates remain WITHHELD**.

This reuses one existing batch only. No scientific acquisition, broad replay,
metric/policy/threshold change, activation, production write, release-tag change,
Full Physics load, or v3.1 work is included. This is a storage-representation
test, not a new scientific review or production capacity certification.

## Selected evidence and baseline

The retained official paired capture covers **2020-01-13–19**: 170 INSPIRE and
465 arXiv paper occurrences, 635 total, resolving to 474 canonical components.
It has four provider/scope partitions and eight original response pages. The
same retained exact-identifier enrichment supplies 439 authority response files;
no provider was contacted. Source and certification provenance remain in the
[certification report](scientific-evidence-certification-2026-09-05.md).

The PostgreSQL baseline is a **current-column/index-layout replica populated
from this staging batch, not exported production rows**. Four partition-level
snapshot wrappers and 3,179 deduplicated raw rows are materialized: 635 paper
rows and 2,544 author-fragment rows (INSPIRE 545; arXiv 1,999). These are provider
occurrences, not additional canonical researchers or papers. Snapshot IDs and
scope metadata belong to the staging replica, not existing production IDs.

| Retained payload representation | Bytes | Decimal MB |
| --- | ---: | ---: |
| Eight original provider response bodies | 8,175,736 | 8.176 |
| Parsed raw-record JSON, including author fragments | 8,639,692 | 8.640 |
| Four snapshot-wrapper JSON payloads | 8,203,342 | 8.203 |
| PostgreSQL stored raw-payload datums | 4,262,680 | 4.263 |
| PostgreSQL stored snapshot-payload datums | 3,392,601 | 3.393 |

These are different, overlapping representations. `pg_column_size` can measure
compressed datums; it is not independently reclaimable physical storage. The
record and snapshot copies repeat provider evidence. Required normalized
attributes repeat some content too, including complete author fragments in
`attributes.authors`, but remain hot in this experiment. Removing dedicated
payload columns does not remove every provider-origin byte from hot storage.

## Minimal reference representation

`storage/payloads.py` wraps **unaltered original bytes** with versioned acquisition
metadata in deterministic gzip. It records provider/page identity, acquisition
and snapshot IDs, scope/dataset version, original timestamp/status/media type,
original payload SHA-256/size, and a separate archive reference/SHA-256/size.
Read-after-write recovery must succeed before a reference is returned. Individual
payloads are capped at 16 MiB; compressed and expanded reads are bounded.

The SQL prototype retains every existing normalized attribute, external ID,
raw name, ingestion timestamp, provenance field, source identity and normal
index. A shared eight-row page catalog stores the artifact references. Raw rows
replace only `raw_payload` with a page key, exact parsed-fragment digest and
size; their existing source record ID locates the paper or author position.
Snapshots retain ordered page checksums instead of duplicate response bodies.
All catalog tables and indexes are charged to the measured hot total.

Legacy source-record and scoped-snapshot checksums are distinct from original
response and compressed-envelope hashes. None is substituted for another or
used to relabel source authority. A recovered reference is not a certificate.
Missing/corrupt bytes or changed metadata fail closed, never become `{}`, `[]`,
zero evidence, or newly certified evidence.

## Recovery and scientific regression

The isolated recovery path is:

```text
retained reference -> verified cold bytes -> original relative source paths
 -> unchanged INSPIRE/arXiv parser and normalization -> canonicalization
 -> unchanged scientific certification -> retained output comparison
```

All 449 files (eight pages, 439 authority responses and two manifests) recover
byte-for-byte. The original manifest identities and 635 parsed/normalized
occurrences are unchanged. Canonicalization produces the same 474 components.
The certification manifest and **all ten output artifacts are byte-identical**,
including 9,999 decisions, 2,290 affiliation shares, 474 field ledgers, 2,101
researcher appearances, 170 citation observations, authority rows and reasons.

Decision counts remain **2,305 certified; 1,686 needs_review; 6,007 insufficient;
1 conflicted**. This batch has no withheld decision; focused fixtures cover that
state and the others. Exact field/attribution fractions, unresolved mass,
institution decisions, paper identities, provenance and missing/null/zero
semantics are unchanged. All 11,742 provenance-link occurrences resolve through
1,033 unique references, including 635 paper and 398 authority references;
unresolved links: **zero**. Certified years/windows and metric observations
created remain **zero**. Existing certified-only calculator admission is unchanged.

SQL readback verifies the inline baseline, all hot metadata and reconstructed
snapshot wrappers. SQL references recover the exact original response bytes,
which are independently reparsed to verify all **3,179 paper/author-fragment
locators** and their source identities, sizes and checksums.
Byte identity is meaningful for the retained original files. A legacy JSONB
baseline does not preserve HTTP whitespace/key order; its comparison is exact
parsed-JSON/scientific equivalence, not a claim to recreate lost wire formatting.

## Native PostgreSQL storage result

Measured at `2026-09-05T01:33:27.225224Z` using PostgreSQL 17.11, arm64, 8 KiB
pages, in a private Unix socket/database/schema. Production runs PostgreSQL 18.6
on x86_64. No production
DDL or rows are touched. Values include allocation overhead, TOAST and indexes;
they are neither compressed-file sizes nor final whole-Atlas hot storage.

| Component | Inline bytes | Reference bytes |
| --- | ---: | ---: |
| Raw-record relation, including indexes | 10,526,720 | 6,242,304 |
| Snapshot relation, including indexes | 3,629,056 | 65,536 |
| Shared page catalog, including index | — | 65,536 |
| Heap main | 4,153,344 | 3,743,744 |
| Auxiliary + TOAST | 9,158,656 | 1,769,472 |
| Target-table indexes | 843,776 | 860,160 |
| **Total hot PostgreSQL bytes** | **14,155,776** | **6,373,376** |
| Hot bytes per provider paper occurrence, all tables | 22,292.56 | 10,036.81 |
| Hot bytes per canonical paper, all tables | 29,864.51 | 13,445.94 |
| **Hot decimal MB per 10,000 canonical papers** | **298.645** | **134.459** |

The sampled raw/snapshot component shrinks **54.98%**, saving 7.782 MB. Raw rows
alone shrink 40.70%; their required hot evidence prevents wholesale removal.
The index increase is 16,384 bytes for the page catalog. Per raw row, with shared
snapshot/catalog overhead included, the totals are 4,452.90 -> 2,004.84 bytes.

The native benchmark's eight cold page envelopes occupy **1,922,804 bytes**.
The independent recovery proof stores these pages in 1,922,886 bytes because
its bound envelope labels differ; the original 8,175,736 payload bytes are
identical. Including retained authority responses (537,545 bytes) and manifests
(45,765 bytes), that proof's full cold set is **2,506,196 bytes**. Cold storage is
reported separately, not hidden in hot savings. The 10k ratio is sample scaling
for these relations only, not a capacity claim or an instruction to load data.

### Conditional transfer to the previous production audit

The [prior audit](storage-amplification-2026-09-05.md) measured 94.937 MB of raw
records and 60.457 MB of snapshots. Applying the **separate measured retention
ratios**, charging all shared page-catalog cost to snapshots, gives:

| Component | Previously measured MB | Conditional retained MB | Conditional saving MB |
| --- | ---: | ---: | ---: |
| Raw records: `6,242,304 / 10,526,720` retained | 94.937 | 56.297 | 38.640 |
| Snapshots + catalog: `131,072 / 3,629,056` retained | 60.457 | 2.184 | 58.273 |
| Combined | 155.394 | 58.481 | 96.913 |

This is a conditional **96.9 MB potential reduction**, not measured production
reclamation. Provider/author mix, repeated updates, page sizes, compression,
index history and PostgreSQL versions differ. The production sample is mostly
INSPIRE; this batch has more arXiv. A physical migration can generate WAL and
retain dead space, so clearing values would not instantly free this volume.
No Full Physics capacity or passing Storage Budget Gate follows from these ratios.

## Smallest migration plan — not executed

Production migration is required to use reference-only rows; it is **not**
required to run this isolated pilot. Current payload columns remain NOT NULL
and the worker still writes inline data. The next authorization should cover
only an additive, one-existing-batch staging integration and restore rehearsal:

1. Add explicit reference/inline state and a dual reader, retaining every
   existing inline payload and all scientific metadata/index constraints.
2. Copy one checksum-bound batch into durable recoverable storage; verify
   archive, decoded body, page/fragment locators, legacy IDs and lineage.
3. Restore into an independent isolated destination. Compare exact payloads,
   parser/canonical/certification outputs; test missing, corrupt and mismatched
   references, API compatibility, idempotency and failed-write cursor behavior.
4. Verify an external write/read-back before committing its database reference
   or advancing a cursor. Until then, rollback selects retained inline values;
   orphan archives can remain unreferenced without losing scientific history.
5. Only a later separately reviewed migration may retire inline values in
   bounded batches. Before retirement, verify rollback restoration of exact
   JSON and plan WAL/headroom/physical reclamation; never use silent empty
   payloads as a missing-reference fallback.

This pilot does not deploy object storage, prove disaster recovery, change the
worker, relax scientific policy, or authorize a production-wide migration.

## Reproduction, validation and health

The fixed-manifest tools are `backend/tools/verify_payload_recovery.py` and
`backend/tools/benchmark_payload_references.py`. They reject another corpus or
network/production database target. Retained evidence is external under
`physics-atlas-evidence/payload-reference-2026-09-05/`; source payloads are not
committed to Git.

| Artifact | SHA-256 |
| --- | --- |
| `recovery-v1/recovery-report.json` | `56408b1b28aaecf27df3bd6c44cbe8b7816d85d7e9aad7440243f941c4380f17` |
| `recovery-v1/payload-catalog.json` | `9db5796a5eb652c442380aac74be3c5a070be345e96a8b93a94b0fa7c420a73c` |
| `postgres-v2/measurement.json` | `311800973fe8e78a80bcba6126ac76474ec33f8d12fed6c0817beba620d3977d` |
| `postgres-v2/payload-references.json` | `79a6a42ac275351a03a6b4fc1badf5b232af004d18569e01c9fc4f15261f9b69` |

Focused validation passes **123 tests in 2.82 seconds**, covering payload
integrity/recovery, parser/certification equivalence, provenance, conservation,
calculator eligibility and relevant backend behavior. Ruff passes the 11 checked
changed/storage files; strict mypy passes 79 source files. The private native
PostgreSQL measurement/readback is additional to those fixture tests. The local
benchmark server was stopped after verification; retained evidence is unchanged.

Read-only production verification at `2026-09-05T01:34:34.618824Z` confirms API
and database health, healthy INSPIRE/arXiv with zero consecutive failures, and
zero public metric observations. The existing one resource-check failure and
440 unresolved entities remain; neither is silently treated as a new pilot
regression. Pilot commit `7c1f34c` is pushed and passed
[CI 33936700018](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33936700018):
frontend lint/tests/build, backend/PostgreSQL tests/migrations/ingestion/API,
and containerized API/worker checks. No production compaction or metric
activation is inferred from local recovery.
