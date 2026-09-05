# Atlas Physica — verified local proof-copy cleanup

2026-09-05; starting `main` commit `0944968`. User-approved local unlink only.
No Railway access, acquisition, replay, compression experiment, scientific-policy
change, metric activation, production migration, or release-tag change.
All sizes below are decimal logical bytes, not measured exclusive APFS extents.

## Verified restore output

Removed only `local-retention-review-2026-09-05/pilot/history-jsonl-v1/verified-restored-original.jsonl`
under the existing `physics-atlas-evidence/` root: **3,437,302,947 bytes**.
Fresh original/restored hashes and hash-only decoding of the existing gzip agree:
`459c1f4065130cef61c3c098f4775994982bd08f2ecb2e7f313d076a8d48aa7f`.
The source and target are distinct regular files; stable identity/size/time checks
were repeated immediately before unlinking.

Retained unchanged:

- Corrected original ledger in `cond-mat-validation-v1-2020-2025-v2-certification-corrected-final/certification/decisions/`, named by that SHA-256.
- 282,831,800-byte gzip: SHA-256 `9ed30287fb6ce9d93e2259ab753fd8488e66043f51a09f7ce2df6588d8664879`.
- `archive-manifest.json`: file SHA-256 `29987afb414b768901366755b4ce1531b44621fd0aac54c77690017605b99e6d`.
- `pilot-result.json`: file SHA-256 `0e9c4a9e5fba26a73807a707b9f9d07a512b3b581bd231b83c9e59bd6f6f818c`.
- Restore instructions and certification manifest `9c79eced…`: file SHA-256 `dae7133e9caa4246d072cebac09ed2bb53063e3eb3f44e51e9d2cd44a1366995`.

The certification manifest binds the original ledger, not the test restore.
The only relevant proof reference to the removed output is the historical
`recovery.restored_path` receipt, not a scientific input dependency. Keep that
receipt unchanged: this report records the later authorized removal. Exact bytes
can be restored again from the retained archive. The prior 2,766,760-decision
scientific equality proof is retained, not rerun or recertified in this task.

## Older proof copies: 152,976,812 bytes reviewed

Removed **eight files / 8,175,736 bytes** only, beneath
`payload-reference-2026-09-05/postgres-v2/sql-restored-raw/pages/`.
Each is a fresh SHA-256/size match to its retained original under
`paired-certification-2020w03-v2-raw-official/pages/`. Their benchmark writer
creates read-back scratch output, not source/certification inputs. No copied
manifest lives in the removed subtree; source manifest, catalog, cold artifacts
and measurement remain outside it. All eight hashes, exact paths and recoverable
twins are individually recorded in the cleanup plan and deletion receipt.

| Scratch page (hash prefix) | Bytes | Retained evidence / removal reason |
| --- | ---: | --- |
| Condensed Matter arXiv `2f9e111f…` | 234,297 | Exact source twin; redundant SQL read-back output |
| Condensed Matter arXiv `3df9a373…` | 143,963 | Exact source twin; redundant SQL read-back output |
| Condensed Matter arXiv `4212bbc7…` | 223,641 | Exact source twin; redundant SQL read-back output |
| Condensed Matter arXiv `8515e456…` | 221,073 | Exact source twin; redundant SQL read-back output |
| Condensed Matter INSPIRE `4807ec08…` | 3,160,464 | Exact source twin; redundant SQL read-back output |
| hep-th arXiv `2352efa1…` | 6,646 | Exact source twin; redundant SQL read-back output |
| hep-th arXiv `7add2861…` | 199,018 | Exact source twin; redundant SQL read-back output |
| hep-th INSPIRE `6d9f4f8e…` | 3,986,634 | Exact source twin; redundant SQL read-back output |

Recovery needs only copying the named retained twin to its recorded scratch path
and verifying size/hash; no provider access or scientific processing is needed.
The parent independently rechecked all target/twin hashes and source bindings,
symlink absence, separate inodes, exact eight-file membership and stable stats.
The open-file check reported no users; deletion used only explicit approved paths.

Kept **1,840 files / 144,801,076 bytes**: the older `recovery-v1/restored/`
(9,674,244), `recovery-v1/recovered-certification/` (26,526,025), and the three
staging `inline/`, `reference/`, `rollback/` trees (36,200,269 each). Historical
copied manifests bind relative child paths. No relocation/recovery contract
permits deleting those children. All other replay copies, source captures,
original ledgers, private workspaces, caches and the 456-byte interrupted-write
fixture remain untouched. No historical manifest was edited to permit removal.

## Post-cleanup accounting

Metadata-only snapshots at `03:27:35–03:27:55Z` use exactly the prior review's
Atlas-only scope, with symlinks excluded and no unrelated user files counted.

| Scope | Logical bytes |
| --- | ---: |
| Evidence, archives and audit records: 5,367 files | 16,532,083,020 |
| Atlas repositories/dependencies, old prototype, named asset and two recorded private workspaces | 1,878,134,488 |
| **Combined scoped local usage** | **18,410,217,508** |
| **Gross removal: nine approved files** | **3,445,478,683** |

Evidence shrank from this task's 19,977,536,426-byte pre-deletion snapshot by
3,445,453,406 bytes net: the difference from gross removal is 25,277 bytes of
new cleanup tooling/receipts. The final evidence total includes all 32,145 bytes
of this task's audit directory. Later documentation/Git metadata can increment
workspace bytes slightly. Remaining evidence file allocation is 16,557,260,800
bytes; exclusive physical free-space gain was not isolated on APFS.

| Remaining evidence classification | Files | Bytes |
| --- | ---: | ---: |
| KEEP: prior protected metadata plus retained archive/audit outputs | 554 | 300,659,353 |
| COMPRESS: required unique expanded evidence, no removal permission | 2,261 | 12,903,185,415 |
| REVIEW: path-bound duplicates and untouched fault fixture; retain pending review | 2,552 | 3,328,238,252 |

Classes partition current evidence exactly; the additional workspace is KEEP/
REVIEW and was not cleared for deletion. No further unlink is approved by this
task. The combined nominal 5 GB budget still **FAILS**; production migration and
metric activation remain unauthorized/withheld as before.

## Single next candidate — not executed

The unique historical certification decision ledger `8d9ba03a16bb5a6b8051af8f7974e44a7b96027f8b99a2c94858827182cf76ed.jsonl`
in the retained-final certification directory is **3,437,391,298 bytes**.
It is the largest uncompressed unique artifact in the same class as the proven
corrected-ledger archive. Its historical decisions are scientifically important
and differ from the corrected ledger. A separately authorized lossless pilot
could use the established manifest/hash/byte-restore contract while keeping the
original. Its compression ratio is not measured; no new savings are claimed.

## Evidence and repository checks

Local audit directory: `physics-atlas-evidence/verified-local-cleanup-2026-09-05/`.
It retains `restore-copy-precheck.json`, `restore-copy-deletion.json`,
`proof-copy-cleanup-plan.json`, `proof-copy-deletion.json` and the two narrow
verification/deletion scripts. Plan SHA-256:
`9a4e02530ef8c8d26f927d94992c4017eca5847a554e851ade65c31ebd9b5014`.
These audit files are not published scientific datasets or automatic cleanup tools.
Prior [retention report](local-evidence-retention-2026-09-05.md) and manifests
remain historical records; this report supplies current deletion status.

Independent read-only audits confirm exactly nine approved paths absent, all
eight source twins present, all 26 inventoried historical manifests hash-unchanged,
all 1,840 protected older proof files retained, and reconciled accounting.
Documentation-only repository changes pass whitespace and 52 local-link checks.
Baseline `0944968` passed [CI 33940584417](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33940584417).
No application tests/replay are needed locally for these documentation changes;
publication uses the existing CI. Railway was deliberately not contacted, so
this task makes no new production-health claim.
