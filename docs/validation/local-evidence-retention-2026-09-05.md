# Atlas Physica — bounded local evidence retention review

2026-09-05; starting `main` commit `32b3f4b`. Local inventory, exact-duplicate
review and one lossless historical-artifact pilot only. No scientific acquisition,
broad replay, Railway access, migration, scientific-policy change, metric
activation, release-tag change or deletion is authorized or performed here.

## Scope and measured baseline

All sizes are decimal bytes/MB/GB. At `02:48:17Z`, the explicit
`physics-atlas-evidence/` root contains **5,356 files / 16,247,746,809 bytes**.
The previous 16,247,696,733-byte inventory is confirmed: the difference is just
eight previous-review output files / 50,076 bytes. This task's new outputs are
excluded from that fixed baseline and accounted for separately below.

All evidence files were stream-hashed with SHA-256, with before/after and final
stat checks. All inputs were stable. File allocation is 16,270,000,128 bytes;
5,356 distinct inodes mean no pathname-level hard-link double count. APFS shared
extents/exclusive physical reclamation were not measured. Logical redundancy
is not a claim about immediately free filesystem blocks.

Percentages below use the previous **16,247,696,733-byte denominator** for direct
comparison. Directory and file-class views overlap and must not be added.

| Largest evidence directories | Files | Bytes | % |
| --- | ---: | ---: | ---: |
| Condensed Matter retained historical certification | 3 | 3,437,398,729 | 21.156 |
| Condensed Matter corrected certification | 3 | 3,437,310,297 | 21.156 |
| Condensed Matter corrected replay | 10 | 3,181,111,619 | 19.579 |
| Condensed Matter historical replay | 10 | 3,181,089,948 | 19.579 |
| Condensed Matter raw capture | 1,455 | 2,762,821,076 | 17.004 |
| Staging dual-read proofs/working copies | 1,832 | 111,163,472 | 0.684 |
| Payload recovery proofs/working copies | 939 | 51,338,174 | 0.316 |

| File class, all retained copies | Files | Bytes | % |
| --- | ---: | ---: | ---: |
| Certification decision ledgers | 9 | 6,958,757,999 | 42.829 |
| Provider page captures | 1,480 | 2,819,208,251 | 17.351 |
| Affiliation evidence | 8 | 2,267,637,717 | 13.957 |
| Researcher evidence | 9 | 1,467,739,702 | 9.034 |
| Canonical papers | 8 | 863,394,600 | 5.314 |
| Source occurrences | 8 | 833,496,688 | 5.130 |
| Field evidence | 8 | 669,195,022 | 4.119 |
| Attribution ledgers | 2 | 250,341,360 | 1.541 |
| Citation evidence | 16 | 82,263,710 | 0.506 |
| Existing cold artifacts | 916 | 9,957,789 | 0.061 |
| Authority evidence projections | 6 | 8,327,664 | 0.051 |
| Other JSON evidence/metadata | 2,848 | 7,809,087 | 0.048 |
| Other files | 4 | 6,308,661 | 0.039 |
| Manifests | 26 | 3,270,646 | 0.020 |
| Proof scripts/profiles | 5 | 35,198 | <0.001 |
| Accounting CSV artifacts | 3 | 2,715 | <0.001 |

The largest individual files are historical decision stream `8d9ba03a…`
(3,437,391,298 bytes), corrected stream `459c1f40…` (3,437,302,947), two
`36b3550d…` affiliation copies (1,128,564,601 each), and two `269c2efd…`
researcher copies (729,806,683 each). The inventory preserves every full path,
hash and size, including paper, occurrence, field and citation snapshots.

### Additional Atlas-only workspace, measured separately

Metadata-only inventory of explicitly named repositories and previously recorded
private workspaces totals **1,877,970,849 bytes**, beyond the evidence root:

| Workspace | Files | Bytes | % of prior evidence baseline |
| --- | ---: | ---: | ---: |
| Source repository, including dependencies/caches | 23,343 | 689,048,185 | 4.241 |
| Web repository and submodule | 5,880 | 206,338,377 | 1.270 |
| Legacy untracked prototype, not a source of truth | 27,425 | 789,908,771 | 4.862 |
| Atlas social-card asset | 1 | 1,419,050 | 0.009 |
| Previously stopped private PostgreSQL test workspace | 1,405 | 151,986,425 | 0.935 |
| Prior archive-only restore workspace | 915 | 39,270,041 | 0.242 |

Combined scoped baseline is **18,125,717,658 bytes**, not just 16.248 GB.
Other Tech Echo projects, synced `sources/`, user-wide caches/temp directories,
and Railway were not scanned. Symlinks were counted separately, not followed.
Installed dependencies account for 1,570,946,995 bytes; tool caches 54,760,750;
generated build/test outputs 13,344,708. Those are not scientific raw captures.
This metadata-only check does not prove environments unmodified/reinstallable or
workspaces inactive. Keep those facts separate from verified evidence hashes.

## Exact duplicates and reference safety

Actual SHA-256 plus size finds **925 groups / 3,485 file occurrences**.
Counting only `n−1` copies per group gives **3,336,424,222 redundant bytes
(20.535%)**. Bundle signatures additionally compare ordered relative member
paths/hashes/sizes; nested bundle counts overlap this file total and add no
further saving. Even a hypothetical single copy of every hash retains
**12,911,322,587 bytes**, before workspace and new outputs.

Seven equal replay artifacts contribute **3,177,938,879 bytes** of redundancy.
Historical bundle `26c51e77…` and corrected bundle `e0ef663…` both require their
own relative paths. Historical certification `b91eac…` and current certification
`9c79eced…` depend on those distinct bundles. Removing one path breaks historical
recovery; current root-containment checks reject cross-root symlink substitution.
No hard-link/path replacement contract was tested or implemented.

The two 3.437 GB decision streams have different hashes and scientific scope/
state histories: **they are not duplicates**. Paired v1/v2 evidence also retains
distinct authority/version history. Keep the older summary-only certification
record's `artifact_available:false` diagnosis; do not pretend its missing row
artifact can be reconstructed from the surviving report.

## Disjoint retention classification

Per-file classification covers the entire evidence baseline exactly once:

| Class | Files | Bytes | Meaning |
| --- | ---: | ---: | --- |
| KEEP | 535 | 8,147,406 | Manifests, proofs, catalogs, unique compressed archives and uncertain metadata. |
| COMPRESS | 2,261 | 12,903,185,415 | Required unique expanded evidence; input bytes, **not proven compression savings**. |
| REGENERABLE | 2,559 | 3,336,413,532 | Each has a named byte-identical retained representative; reconstructable by verified copying, but removal remains **REVIEW** until path/retention contracts hold. |
| DELETE_CANDIDATE | 1 | 456 | Explicit unpublished interrupted-write test artifact; no unique scientific evidence, but left intact. |

Duplicate metadata totaling 10,690 bytes is deliberately KEEP, not counted again
as REGENERABLE. Of REGENERABLE bytes, 152,976,812 are duplicated proof/restore
working trees worth reviewing first; 3,183,436,720 are other path-bound copies.
The classification includes explicit representative mappings, not an inference
that absence from a text search proves a file unused.

Outside that table, 54,760,750 bytes of known tool caches are cleanup candidates
after inactivity/ownership review. Remaining workspace bytes are KEEP/REVIEW;
no dependency reinstall, original private-DB retirement or build reproducibility
claim was tested. **Direct scientific unlink clearance and actual reclaimed
bytes are both zero.** Candidates and conditional savings are not permission.

## Compaction pilot and validation

One original file only:

```text
cond-mat-validation-v1-2020-2025-v2-certification-corrected-final/
  certification/decisions/459c1f4065130cef61c3c098f4775994982bd08f2ecb2e7f313d076a8d48aa7f.jsonl
```

It is bound by existing certification manifest `9c79eced…`. The local helper
`backend/tools/compact_historical_artifact.py` verifies that manifest's file and
self-checksums, exact artifact path/hash/size/row count, and unchanged source
identity. It streams one deterministic gzip (level 6, timestamp 0, no filename
header), then restores and directly compares every byte with the original.
Completed archive/manifest files are read-only and create-exclusive; this is
not a durable WORM/object-store or independent-backup guarantee.

| Pilot component | Logical bytes | Allocated bytes |
| --- | ---: | ---: |
| Original, retained unchanged | 3,437,302,947 | 3,437,305,856 |
| Compressed artifact | 282,831,800 | 285,741,056 |
| Archive manifest | 2,928 | 4,096 |
| Retained verification result | 3,357 | 4,096 |
| Restored test copy, also retained | 3,437,302,947 | 3,439,730,688 |

Archive plus manifest is **282,834,728 bytes**, a **12.15:1** compression ratio
and **91.7716% smaller representation**. Including the verification report gives
282,838,085 retained archive/proof bytes, an exact conditional saving of
**3,154,464,862 bytes** if the original representation can later be retired
safely. No such retirement occurred. Compression took 46.64 seconds; restoration
33.42 seconds. Including a 6,148-byte restore README, the five-file pilot adds
**3,720,147,180 logical / 3,725,488,128 allocated bytes** because the full restored
copy is still retained.

At `02:53:24Z`, original and restored SHA-256 are both
`459c1f4065130cef61c3c098f4775994982bd08f2ecb2e7f313d076a8d48aa7f`.
All **2,766,760 rows**, ordered identity/status/reason/version/provenance digests,
5,365,415 evidence-reference occurrences and 2,378,722 reasons match. States
remain 388,038 certified, 1,287,642 needs_review, 1,026,684 insufficient_evidence,
64,396 withheld and zero conflicted. Exact bytes preserve all conservation,
missing/null/zero and eligibility information already present in the ledger.

This is **unchanged stored scientific state**, not recertification, remeasurement
of source coverage, verification of every external evidence link or scientific
activation. No large replay/calculator run was performed. Small fixtures also
cover conflicted decisions, Unicode, CRLF, no final newline, future fields,
missing/null/zero distinctions, and archive recovery with original access denied.

Inputs are bounded to 4 GiB / three million rows / 16 MiB per line; compressed
input has a 4 GiB + 8 MiB ceiling, metadata a 1 MiB ceiling. Invalid bindings,
existing outputs, corrupted/truncated or changing archives, oversized input and
interrupted writes fail closed. Unverified partial files are not successful
artifacts and are never silently substituted for scientific evidence.

Restore from a copied archive directory, with this explicit pinned manifest hash
and a new output path (run from the source repository; no original needed):

```sh
backend/.venv/bin/python backend/tools/compact_historical_artifact.py restore \
  --manifest /path/to/history-jsonl-v1/archive-manifest.json \
  --manifest-sha256 29987afb414b768901366755b4ce1531b44621fd0aac54c77690017605b99e6d \
  --output /path/to/new-restored-decisions.jsonl
```

## Conservative post-cleanup scenarios — not executed

Apply measured savings only to the one verified file; do not extrapolate its
91.77% ratio across raw captures, other decision streams or all 16.248 GB.

| Conditional evidence-only representation | Bytes, before new review/instruction metadata |
| --- | ---: |
| Original baseline | 16,247,746,809 |
| Replace only the verified pilot original with archive + manifest + result | 13,093,281,947 |
| One copy per exact hash, no compression | 12,911,322,587 |
| Exact deduplication plus only the verified pilot replacement | 9,756,857,725 |

The pilot original is unique in the baseline, so these two hypothetical savings
do not overlap. The final scenario needs path-preserving recovery and separate
retention/deletion approval; it is **not presently safe to execute**. It still
exceeds the entire combined 5 GB budget before the 1.878 GB workspace, backups,
production or operational headroom. No new capacity approval follows.

New inventories/classifications/scripts and restore instructions add about
9.642 MB beyond the archive/manifest/result/restore files. Adding these retained
audit bytes puts the conditional 9.757 GB scenario at approximately **9.766 GB**,
not below 5 GB. The measured scoped
baseline plus retained trial outputs therefore occupies approximately **21.856
GB now**, not less than before. Temporary proof copies are explicitly visible,
not hidden as savings. Repository build/test cache churn is not an immutable
scientific accounting boundary.

## Retention proposal and next boundary

The [proposed retention policy](../local-evidence-retention.md) requires each
large job to report new persistent and peak temporary bytes, disjoint retention
classes, exact reconstruction evidence and path references. It distinguishes
canonical current, milestone, raw, replay, cache and superseded material; it
implements no automatic deletion or age-based expiry.

No original, historical bundle, raw capture, database workspace or duplicate
was removed. The smallest next cleanup is a separately approved removal of this
new **3.437 GB verified restored test copy**, keeping the original, archive and
small proof report; then review the **152.977 MB** older redundant proof/restore
copies. Those are not unique source evidence. Other duplicates need the stronger
historical path contract before retirement. A future cleanup must name exact
targets and retained replacements and verify hashes before and after.
Production migration remains NO-GO; this local work cannot authorize Full Physics
loading, metric activation or v3.1.

## Validation and evidence

97 focused local tests pass (12 new archive fixtures plus 85 existing storage/
recovery tests); changed-tool/test Ruff lint and formatting pass. A final stat
check of all 5,356 hashed baseline inputs finds no change after the pilot.
No production
application, schema or deployment configuration changed. Baseline `32b3f4b`
passed [CI 33939682265](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33939682265).
New-commit CI status is reported with publication. Railway was not contacted in
this local-only task; its last verified health remains in the prior report.

Complete evidence is retained outside Git under
`physics-atlas-evidence/local-retention-review-2026-09-05/`, including every
file/hash/representative mapping and the exact restore recipe:

| Evidence | SHA-256 |
| --- | --- |
| `inventory/summary.json` | `41ed0dfd945257887c863720674769f88d023948f4ad37c73b3b290946717d9f` |
| `retention-classification.json` | `a8e906aa11d6e719ea2736318373350d8dfb7b5be14f21948f96a92e1d0ade8f` |
| `workspace-inventory.json` | `b6fa1e5570469ea2eee7a3b5657666b5f042eade0702a9ac2b09443dc2c5de92` |
| Gzip archive, named with the full original SHA-256 | `9ed30287fb6ce9d93e2259ab753fd8488e66043f51a09f7ce2df6588d8664879` |
| `pilot/history-jsonl-v1/archive-manifest.json` | `29987afb414b768901366755b4ce1531b44621fd0aac54c77690017605b99e6d` |
| `pilot/history-jsonl-v1/pilot-result.json` | `0e9c4a9e5fba26a73807a707b9f9d07a512b3b581bd231b83c9e59bd6f6f818c` |
