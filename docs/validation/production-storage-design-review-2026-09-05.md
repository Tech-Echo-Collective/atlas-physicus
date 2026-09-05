# Atlas Physica — production storage design and total-budget review

2026-09-05; source `d4859c5` on `main`. **Design review only: no production
DDL, payload migration/deletion, acquisition, broad replay, scientific-policy
change, metric activation or release-tag change.** Production code is unchanged.

## Decisions and budget boundary

- **Migration Readiness: NO-GO for production execution.** A minimal additive
  plan is defined below, but the production-compatible adapter, durable archive,
  independent operational restore and peak-budget evidence are not implemented
  or approved. Local archive-only recovery is not production migration approval.
- **Total Storage Budget Gate: FAIL for the currently retained inventory** under
  the user's combined nominal **5,000,000,000-byte** budget. Local retained
  evidence alone is 16.248 GB, before production or this review's extra outputs.
  A future representative final-layout assessment remains **WITHHELD**, not PASS.
- The existing scientific Joint Gate remains withheld. The earlier software
  `storage-budget-gate-v1` assessments were volume-oriented and remain historical
  evidence; their generic projected-byte fields and `cold_payloads_externalized`
  flag do not independently prove a complete cross-store inventory. No existing
  gate input, scientific formula or threshold was changed in this review.

PA-048 makes the accounting boundary explicit:

```text
total persistent = hot PostgreSQL + cold/warm archive
                 + required history, provenance and restore metadata
                 + retained backups/replicas/other persistent copies
```

Do not add a category twice when its bytes already sit in another term. External
storage is not free capacity: a separately purchased store's capacity/cost must
be disclosed, and still falls inside this combined budget unless the user changes
it. Ephemeral processing is a separate peak resource, not a hidden archive.
Retain the existing 25% estimate contingency, 60% steady-state and 80% peak limits:
nominal **3.0 GB steady / 4.0 GB peak**, after contingency. Actual per-volume
limits also apply; the previously measured Railway volume is 4,685,873,152 bytes,
not 5 GiB. Unknown required bytes cannot be replaced by zero or by contingency.

## Minimum production reader/schema plan — not implemented

Reuse `SourceSnapshot`, `RawEntityRecord`, their existing foreign keys, IDs,
provenance and indexes. Keep canonical/normalized attributes hot. Initial scope
is one already-committed snapshot with exact raw-row membership, not new ingestion.

| Existing table | Proposed additive fields | Reused state / constraints |
| --- | --- | --- |
| `source_snapshots` | `payload_mode`, default `inline`; nullable versioned `payload_descriptor` JSONB | Existing `storage_reference` remains the stable `database://source_snapshots/{id}` provenance URI. Descriptor binds archive reference, compressed and decoded hash/size, representation, snapshot/source/scope and legacy checksum. |
| `raw_entity_records` | Same mode and nullable descriptor fields | Existing snapshot FK anchors the shared archive; descriptor supplies exact page/record/author locator version and fragment hash/size, not a full archive descriptor duplicated for every author. |

No new table or index is required for this bounded proposal. Do not add a GIN
index or duplicate provider/record/snapshot indexes. Keep both `raw_payload`
columns **NOT NULL** for the additive pilot. Validate known modes and descriptor
shape/version; reference selection requires a complete valid descriptor. Inline
requires the original array/object, never a fabricated empty sentinel. Bounded
DDL must use short lock timeouts and be rehearsed on an isolated schema first;
constraint validation/locks are operational work, not presumed free.

Expected overhead is positive: a mode plus a descriptor per selected row and
snapshot, plus archive bytes and restore metadata. **Exact physical overhead is
unmeasured for this schema.** The earlier eight-page catalog occupied 65,536 hot
bytes including 16,384 index bytes, but that was a different measured layout.
It is not an overhead prediction for these fields. Measure heap/TOAST/index,
archive allocation, metadata and WAL/duplicate-copy peaks before approval.
Keeping inline plus archive during rollout saves no storage.

### Representation and one shared scientific path

Production snapshots currently contain JSONB page wrappers or record objects;
INSPIRE bodies are already parsed JSON, while arXiv wrapper bodies retain XML
text. A migration must preserve **stored JSON semantics and legacy identities**,
not claim to recover discarded original INSPIRE wire formatting. PostgreSQL
JSONB does not preserve whitespace, object-key order or duplicate keys;
SQL NULL also differs from JSON null. See the
[PostgreSQL JSON documentation](https://www.postgresql.org/docs/18/datatype-json.html).

Archive a deterministic, distinctly versioned **legacy-JSON snapshot envelope**
once, with exact ordered fragment locators. Preserve existing source-fragment
hashes (`ensure_ascii=True`) separately from scoped snapshot hashes
(`ensure_ascii=False`, `{acquisitionScope,payload}`), decoded-envelope hashes and
compressed-artifact hashes. Never replace source IDs/checksums with archive IDs.
Do not invent HTTP capture/status metadata to fit the staging wire-byte envelope.
Keep a row inline if its exact fragment cannot be rederived using the pinned
adapter. Existing 16 MiB per-payload bounds remain: choose a fitting batch or
stop for a separately reviewed split plan, not an unbounded decompression path.

Both modes return the same source representation to the **existing** provider
parser, normalization and canonicalization. Recovery/certification equivalence
uses the existing offline certifier. The production worker does not currently
run that certification stage and retains `NoFormulaMetricRecalculator`; this
storage plan does not add a live scientific pipeline or activate observations.

### Selection, checks and checkpoints

1. Default/legacy rows select inline. A shadow reference does not win merely
   because it exists. Explicit reference mode selects only reference recovery;
   failure never falls back to inline, provider fetching, `{}`, `[]` or zero.
2. Verify descriptor version/binding, compressed hash/size, bounded decoding,
   decoded hash/size, legacy scoped hash, source/locator and exact fragment hash.
   Verify the whole bounded input before admitting scientific output. Missing,
   corrupt, unavailable or partial storage is an operational **blocked** error,
   not a new missing-evidence record or successful certification.
3. Immutable archive write and independent read-back precede a compare-and-swap
   SQL selection transaction. A failure preserves successful canonical state;
   an orphan archive remains unselected and counts until reviewed cleanup.
4. Migrating already-ingested storage must not advance provider cursors, rewrite
   dataset/update lineage or reapply canonical relationships. Future ingestion
   integration needs checks before canonical/update success and cursor advance.
   In particular, the current duplicate-snapshot shortcut in `updates/engine.py`
   advances the cursor without reading payloads; it must verify a reference
   before it can safely support reference-only state. This is a future integration
   requirement, not a demonstrated current inline-path bug.
5. Failure bookkeeping may retain a retry checkpoint, never falsely mark the
   next page completed. On connection loss during commit, reconnect and reconcile
   immutable snapshot/update identity and cursor: do not assume rollback or
   blindly repeat successful writes. Prior testing covered pre-commit interruption,
   not uncertain commit/network loss.
6. Rollback explicitly selects verified retained inline JSON in one transaction,
   preserves archive references/audit history, and rechecks hashes and outcomes
   with the archive unavailable. Old application versions remain compatible only
   while original inline columns remain populated. Later retirement would require
   separately approved nullability, exact inline restoration and compatibility
   checks; it is not part of the additive pilot.

## Independent archive-only recovery performed

The same existing January 13–19, 2020 batch was used: **635 occurrences / 474
papers**, with no acquisition. A fresh local kit copied only **449 cold objects
(2,506,196 bytes)** plus the **549,343-byte reference catalog**: **3,055,539 bytes**.

A separate process ran under an OS sandbox denying the **entire original evidence
tree** (raw sources, prior restorations, archives/catalogs and expected reports),
local PostgreSQL files, all network access and repository writes. Four negative
controls required permission-denied results before recovery. The process then
recovered payloads, verified manifests, and called the unchanged parser,
normalizer, canonicalizer and certifier. Only after it exited did a separate
process compare its hashes to the retained baseline report.

Result at `02:28:42Z`: **local archive-only dependency proof PASS**. All ten
scientific artifact hashes, full manifest hash and normalization digest match;
9,999 decisions retain their reasons/versions and states (2,305 certified,
1,686 needs_review, 6,007 insufficient_evidence, one conflicted). All 1,033 unique
provenance references recover; no lost links. Attribution/field ledgers,
missing-vs-zero semantics and certified-only input behavior remain unchanged.
Public/new metric observations remain zero. Existing focused fixtures additionally
cover withheld decisions, corrupt archives and invalid calculator admission.

This is **not** independent-host/account backup durability or production JSONB/
ORM restore. Those proofs must restore a copied archive **and** necessary hot
metadata, catalogs, authority/review/citation history and pinned code without
original DB/archive access, then verify the same outcomes. Operator ownership,
retention, credentials/keys, backup completeness and failure recovery remain open.

The new private workspace holds 39,270,041 logical / 41,754,624 allocated bytes:
kit plus 9,674,244 recovered source bytes, 26,526,025 regenerated scientific bytes
and proof files. These are extra processing/redundant copies, not savings.
Small proof scripts/profile/reports are also retained externally for audit;
the full kit was not duplicated into the repository or deployed anywhere.

## Total persistent accounting for the measured pilot

Decimal MB/GB throughout. Native PostgreSQL sizes include heap, TOAST, indexes
and allocation overhead. Archive/file columns are exact logical file bytes;
filesystem/object-store allocation and replicated copies must be added for a
physical deployment budget. This is a composed, one-copy evidence envelope,
**not a measured full production schema or actual reclaimed space**.

| 474-paper component | Inline bytes | Reference-layout bytes |
| --- | ---: | ---: |
| Raw/snapshot hot DB, including indexes/catalog | 14,155,776 | 6,373,376 |
| Exact original source/authority/manifests, or their recoverable cold encoding | 9,674,244 | 2,506,196 |
| Ten retained scientific output artifacts, including citation/decision history | 26,520,457 | 26,520,457 |
| Reference catalog, certification manifest and retained proof metadata | 590,165 | 590,165 |
| **Total persistent evidence envelope** | **50,940,642** | **35,990,194** |

Modeled total reduction: **14,950,448 bytes / 29.35%**. DB-only reduction:
**7,782,400 bytes / 54.98%**. The remaining 7,168,048 bytes saved come from smaller
exact source encoding, not free external storage. All source bytes are counted
in the inline baseline because JSONB alone cannot preserve the wire-byte
manifest guarantee. Both sides retain the same scientific output and proof set.

An allocation-sensitive local comparison adds the same native DB sizes to file
allocation: originals 10,792,960 bytes versus cold objects 3,829,760 bytes;
scientific artifacts 26,542,080 bytes and five metadata/proof files 606,208 bytes
on both sides. Its subtotal is **52,097,024 → 37,351,424 bytes (28.30% less)**.
Directory blocks, extra backups/replicas and cloud allocation are excluded;
these figures do not measure exclusive APFS extents or cloud billing.

The narrower raw/snapshot-only comparison is 14,155,776 DB bytes versus
6,373,376 DB + 1,922,804 native eight-page archive = **8,296,180 bytes**, a
**41.39% component reduction**. It omits other scientific persistence and is
not a capacity estimate. Do not add that archive again to the full 2,506,196-byte
449-file set: they represent the same provider inputs with slightly different
envelope metadata.

The earlier compact certification proposal measured 3,072,000 hot bytes plus
1,056,945 cold bytes. It preserves decision semantics but reorders the original
JSONL, so its archive does not directly reproduce the original artifact hash.
It is **not** substituted for the original decision stream or added to the
current undeployed certification schema here. A proven ordering/manifest restore
contract is required before using it to retire that original artifact.

## Retained inventory and persistence classification

Read-only file metadata inventory (no broad content replay), excluding this
review's new output directory and private workspace:

| Local evidence category | Files | Logical bytes |
| --- | ---: | ---: |
| Condensed Matter raw history | 1,455 | 2,762,821,076 |
| Condensed Matter certification histories | 8 | 6,874,716,074 |
| Condensed Matter replay histories | 20 | 6,362,201,567 |
| Paired-batch histories | 1,085 | 84,374,905 |
| Previous storage/proof/restore copies | 2,780 | 163,583,111 |
| **Retained local evidence total** | **5,348** | **16,247,696,733** |

File allocation totals 16,269,930,496 bytes; directory-inclusive `du` reports
16,269,942,784. APFS shared extents are not measured, so this is not a claim
about exclusive disk blocks or cloud billing. No hypothetical deduplication is
credited. The prior Railway volume used 482,541,568 bytes separately; it is
healthy, not full. This local history plus production cannot be described as
fitting a combined 5 GB budget. New proof copies only increase retained usage.

| Category | Conservative treatment |
| --- | --- |
| Canonical entities, exact attribution/field shares, current identity/certification/review state, necessary metrics and cursors | **Must persist**, compact hot representations permitted with exact linkage and behavior. |
| Historical raw captures, authority responses, citation cutoffs/counts, affiliation/identity supersession and authenticated review decisions | **Must persist** as versioned evidence. Current provider responses cannot reconstruct earlier truth. Lossless compression/dedup is allowed only with exact recovery and retained occurrence metadata. |
| Source/review/restore manifests, checksums, locators, parser/code/dependency versions, backup inventories and required keys/configuration | **Must persist**; include metadata/backups/replicas in the budget, never assume Git alone preserves scientific inputs. |
| Repeated expanded provenance, snapshot copies and detailed certification traces | **Can be compacted**, not discarded: dictionary/shared-body/archival representations require exact semantic and original-manifest recovery proof. |
| Search projections and deterministic replay outputs | **Can be reconstructed safely only conditionally**: pinned code, immutable complete inputs, decisions and exact hash checks must suffice. Existing output histories stay counted until that retention decision is reviewed. |
| Temporary downloads, decompression files, test DBs and verified duplicate restore working trees | **Ephemeral candidates** after successful processing/proof retention. Report peak space separately; merely being stored locally does not make history ephemeral. |

No historical file was deleted, relabeled as disposable by default, or assumed
free. Repeated directories are candidates for audited compaction/dedup, not
evidence that any particular copy can already be removed.

## Capacity scenarios — measured components, not corpus-size predictions

The complete final schema is unmeasured. To avoid treating the small raw table
as the entire Atlas, use a transparent **hybrid retained-production-mix scenario**:

```text
hot(N)   = N × (141,680,640 / 823 + 6,373,376 / 474)
cold(N)  = N × 2,506,196 / 474
other(N) = 185,466,880 + N × 27,110,622 / 474
modeled total = hot + cold + other
planning estimate = 1.25 × modeled total
```

141,680,640 bytes are all prior production public relations except the two raw
relations; 185,466,880 is measured non-public volume use. `other` retains the
ten artifacts and proof set once, including current citation/decision evidence.
No hypothetical compact-certification saving is applied. The 474/823-paper
ratios have different author/provider/history mixes and PostgreSQL platforms.

| Papers (scenario only) | Hot DB GB | Cold inputs GB | Other persistent GB | Modeled total GB | With 25% contingency GB |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 1.856 | 0.053 | 0.757 | 2.666 | 3.333 |
| 50,000 | 9.280 | 0.264 | 3.045 | 12.589 | 15.737 |
| 100,000 | 18.560 | 0.529 | 5.905 | 24.993 | 31.242 |
| 250,000 | 46.399 | 1.322 | 14.484 | 62.205 | 77.757 |

These are modeled known-component totals **plus unmeasured required costs**:
future citation/history generations, eligible review/metric state, durable backup
copies, archive replication/allocation, final descriptor overhead and WAL/rewrite
peaks. Those costs are not zero and are not proven covered by contingency. The
existing 16.248 GB inventory is reported separately rather than silently erased
or added to a different hypothetical paper population. These are not additional
paper-capacity allowances. Even the 10k estimate exceeds the nominal 3 GB steady
limit; larger cases exceed the entire budget. No safe capacity is certified.

## One-batch production pilot plan — DO NOT execute yet

1. **Select:** one small already-successful production snapshot, exact raw IDs,
   supported provider/locator version, all envelopes within existing size bounds.
   Record current source/update/cursor and known null/missing semantics.
2. **Back up:** verified snapshot/raw payloads plus necessary canonical, authority,
   review, citation and lineage state; record IDs/hashes/code versions and budget
   all backup/rollback copies. Abort unless independent restore and peak space fit.
3. **Archive:** create immutable bounded legacy-JSON envelopes with exact ordered
   locators and acquisition binding; no reacquisition or guessed wire metadata.
4. **Verify:** read back from the intended archive boundary; check compressed,
   decoded, scoped-snapshot and every fragment hash/size/source.
5. **Write references:** deploy/rehearse additive columns and dual readers first;
   retain inline NOT NULL. Use compare-and-swap transactions to install references
   without changing provider cursors, dataset versions or canonical relationships.
6. **Dual-read:** compare explicit inline and reference results; exercise normal
   API/provenance reads and unchanged legacy clients, with no silent fallback.
7. **Scientific equivalence:** feed both representations through the same pinned
   existing offline scientific pipeline; compare artifacts, decisions/reasons,
   provenance, conservation, missing-vs-zero and calculator eligibility.
8. **Independent restore:** restore archive plus compact DB/catalog/history backup
   on an isolated target unable to access original inline or archive paths.
   Require operator-owned backup/durability evidence, not just local file copies.
9. **Inject failures in isolation:** missing/corrupt/invalid/unavailable/partial
   archives; late batch failure; concurrent state change; pre-commit interruption;
   restart/retry; idempotent shortcut; uncertain commit. Reconcile unknown outcomes.
10. **Roll back:** atomically select checksum-verified retained inline data, keeping
    references/history. Prove it works without archive access or reacquisition.
11. **Post-rollback:** compare scientific hashes, row membership, dataset/update/
    cursor lineage, API behavior and health; measure total retained and peak bytes.
12. **Before any deletion:** separately reviewed authority, verified complete
    independent restore, historical retention and legal/provider requirements,
    exact inline rehydration and old-version safety, explicit SQL null semantics,
    passing total/per-volume budgets and measured reclamation/WAL plan. A nullable
    column or successful read alone is not deletion permission. No `VACUUM FULL`,
    broad rewrite or production retirement is authorized by this review.

**Smallest next action:** review a lossless compaction/retention plan for the
existing large history (start with one preserved artifact and prove exact original
hash restoration), without deleting originals. Then rehearse the proposed
production representation in isolation and measure its full archive/backup peak.
Do not proceed directly to production payload migration.

## Validation, evidence and production

85 focused existing storage/recovery/dual-read/rollback/certification/budget tests
pass (1.02s). The independent archive-only test above is additional. No application,
schema, metric or deployment code changed; no frontend rebuild is required locally.
Baseline source [CI 33938302268](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33938302268)
is green, including PostgreSQL/API/worker/container checks. The documentation
commit will run the same CI; final publication status is reported with the task.

Read-only production health at `02:26:03Z`: API/database healthy, both providers
healthy with zero failure streaks, recalculation idle, 440 unresolved identities,
the previously diagnosed single DOI 404 and **zero public metric observations**.
The worker's successful update/cursor values are unchanged. No production DB
connection or migration was needed for this review; no release tag was changed.

Retained evidence under `physics-atlas-evidence/production-storage-review-2026-09-05/`:

| File | SHA-256 |
| --- | --- |
| `total-storage-accounting.json` | `6709527f726b4185cb20525766b41ba7a87fc2d4d9f4b5bd6b77946f535207a6` |
| `archive-only-proof/archive-only-report.json` | `c17359a82299a57a9608ac23abae09e351003bcc7283d365e611f0cabd77da90` |
| `archive-only-proof/comparison.json` | `808f63cf434ccd61e20d9ee8d2ce593e4efb2bf78650b0f404a1f218bbabd8ce` |
| `archive-only-proof/kit-accounting.json` | `48fb8c36b65524912ec6b6a26ee1d34128f06f0a1e07d55300b23fe21954e13d` |
| `archive-only-proof/verify_archive_only.py` | `4c4e5b0d789a3abf42b5695aa3d16b899cb48cc6159d8106c4ac1cd41c3addfe` |
| `archive-only-proof/recovery.sb` | `357ffa15131a6765d9c468fc543b77916a8292956ce55a995da4ac2293d4eb52` |

The host-specific validator/profile are external audit material, not production
code. Reproduction must prepare a fresh temporary kit, deny original evidence/
DB/network reads, restore there, and compare only afterward. Prior measurement
inputs and immutable batch IDs remain in the linked
[payload](payload-reference-recovery-2026-09-05.md),
[storage](storage-amplification-2026-09-05.md), and
[staging](staging-dual-read-2026-09-05.md) reports; they are not silently rewritten.
