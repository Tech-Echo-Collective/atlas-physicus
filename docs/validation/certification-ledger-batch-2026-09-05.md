# Atlas Physica — bounded certification-ledger archive batch

2026-09-05. Starting `main` commit `5760524` was revalidated, pushed before this
batch and passed [CI 33945043808](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33945043808).
**Nine candidates; one retired; eight retained.** No shared archive/resolver
defect, new archive format, scientific policy change, acquisition, Railway access,
scientific replay, other-class processing or metric activation occurred.

## Candidate boundary and matrix

Discovery preceded ledger mutation. It found nine physical decision-JSONL files
with four distinct content hashes: eight in `physics-atlas-evidence/`, and one in
the previously scoped `/private/tmp/atlas-physica-archive-only.KpQrZU` recovery
workspace. All have explicit certification-manifest entries and decision rows;
the corrected `459c1f40…` original was already absent and excluded. Repository
fixtures, DB tables, non-decision artifacts and unrelated temp directories were
excluded. No candidate already had a matching archive.

Sizes below are decimal MB. **FAIL\*** means the existing required contract
cannot admit this artifact: archive creation rejects before writing output and
restore is blocked, not an observed corrupt archive or failed decompression.

| Artifact | Original MB | Archive MB | Archive | Restore | Authority | Dependencies | Retirement | Reclaimed MB | Blocker |
| --- | ---: | ---: | --- | --- | --- | --- | --- | ---: | --- |
| L01 Historical Condensed Matter `8d9ba03a…` | 3,437.391 | 282.717 | PASS | PASS | PASS | PASS | GO | 3,437.391 | None |
| L02 Paired v1 `03a711d5…` | 10.830 | — | FAIL* | FAIL* | FAIL | FAIL | NO-GO | 0 | Paired v1 contract/path |
| L03 Paired v1 `845cf978…` | 12.069 | — | FAIL* | FAIL* | FAIL | FAIL | NO-GO | 0 | Paired v1 contract/path |
| L04 Paired v2 canonical `b2115733…` | 12.233 | — | FAIL* | FAIL* | FAIL | FAIL | NO-GO | 0 | Paired v2 contract/path |
| L05 Payload-recovery `b2115733…` | 12.233 | — | FAIL* | FAIL* | FAIL | FAIL | NO-GO | 0 | Paired v2 contract/path |
| L06 Dual-read inline `b2115733…` | 12.233 | — | FAIL* | FAIL* | FAIL | FAIL | NO-GO | 0 | Paired v2 contract/path |
| L07 Dual-read reference `b2115733…` | 12.233 | — | FAIL* | FAIL* | FAIL | FAIL | NO-GO | 0 | Paired v2 contract/path |
| L08 Dual-read rollback `b2115733…` | 12.233 | — | FAIL* | FAIL* | FAIL | FAIL | NO-GO | 0 | Paired v2 contract/path |
| L09 Earlier isolated restore `b2115733…` | 12.233 | — | FAIL* | FAIL* | FAIL | FAIL | NO-GO | 0 | Paired v2 contract/path |

Full paths, content hashes, versions, logical IDs, sizes, decision counts and
exact historical-manifest bindings are retained in
`physics-atlas-evidence/certification-ledger-batch-2026-09-05/candidates.json`.
Every paired ledger contains 9,999 decisions. L01 has 2,766,760 decisions.

L02/L03 use `physics-paired-trial-certification-manifest-v1`; L04–L09 use v2.
Their own file/self-checksums and row/byte counts pass. However, they bind role
`decisions`, paths `artifacts/decisions/…` and `manifest_checksum`, not the
existing resolver's historical role/path/schema. The current paired verifier
in `paired_trial_certification.py` reads those artifact paths directly. Duplicate
bytes do not replace this absent authority adapter. All eight tests independently
reject before archive publication; their originals/manifests remain unchanged.
There is no fabricated historical manifest, partial fallback or weakened gate.

## L01 archive, isolated proof and retirement

The only pre-existing original removed was, relative to the evidence root:

```text
cond-mat-validation-v1-2020-2025-v2-certification-retained-final/certification/decisions/8d9ba03a16bb5a6b8051af8f7974e44a7b96027f8b99a2c94858827182cf76ed.jsonl
```

Historical manifest `b91eac93…` retains its original bytes and binding. Logical
identity is `005e861c3a44495e38436a3c744c946e25c17b8906e4d1b874c973559fdff392`.
The unchanged `lossless-historical-jsonl-archive-v1` helper created a deterministic
gzip in `certification-ledger-batch-2026-09-05/L01/archive/`. The unchanged
`historical-artifact-descriptor-v1` descriptor at `L01/artifact-descriptor.json`
selects `historical-ledger-archive-v1`; `L01/authority-record.json` binds its proof.

Initial compression took 46.36 seconds and direct byte-comparison restoration
33.55 seconds. The exact temporary restore was then removed after fresh checks.
An isolated kit at `/private/tmp/atlas-physica-ledger-batch.t9GgCk` copied only
the archive and pinned descriptor/manifests/proof metadata. OS controls denied
the real original evidence/archive, private DB and all network access. The
existing resolver/proof runner completed independent recovery at `04:45:23Z`:

- Exact **3,437,391,298 bytes / 2,766,760 decisions** and original SHA-256 match.
- States remain **388,038 certified; 1,285,975 needs_review; 1,026,684
  insufficient_evidence; 64,396 withheld; 1,667 conflicted**. Historical conflicts
  were not replaced by the corrected ledger's decisions.
- All ordered identity, reason/status/version and provenance digests match;
  5,365,415 evidence-reference occurrences and 2,378,722 reason entries remain.
- Full-byte equivalence preserves stored missing/null/zero and conservation
  information. No source conservation or external provider availability was
  recomputed. Audit JSON remains outside the unchanged certified-only calculator
  boundary; this is recovery, not new scientific eligibility.

Independent review plus fresh original/archive hashes, unchanged recovery-tool
pins, historical bindings, process-handle and scratch checks all passed. L01 was
retired at `04:48:07Z`. Inventory comparison found exactly one pre-existing file
removed and no other changed evidence files. Both archive authorities subsequently
pass lightweight integrity/binding checks with both originals absent. No extra
full restore was performed after retirement. All eight NO-GO ledgers and all nine
historical-manifest hashes were independently rechecked unchanged.

Historical records remain accurate as-of records. In particular, the old
single-corrected-ledger checker contains an explicit guard that `8d9ba03a…` was
untouched during that earlier task. That completed task-specific guard no longer
describes the current batch; it was not silently edited. Current lightweight
checks use `certification-ledger-batch-2026-09-05/verify_authorities.py
--originals-absent`. This only calls existing admission/integrity checks; actual
recovery still uses the public `resolve_historical_artifact` context manager,
not this audit script or a transparent filesystem interceptor.

## Storage accounting

| Measure | Bytes |
| --- | ---: |
| Nine original file occurrences examined | 3,533,688,096 |
| One original actually archived and retired | 3,437,391,298 |
| Eight retained expanded candidates | 96,296,798 |
| New archive retained | 282,717,390 |
| Net representation reduction before audit metadata | 3,154,673,908 |
| New evidence audit/descriptor/proof metadata | 61,080 |
| Net evidence-root reduction | 3,154,612,828 |
| New evidence footprint, 5,385 files | 9,940,187,795 |
| Scoped Atlas-only workspace at `04:49:12Z` | 1,878,437,276 |
| Combined scoped footprint | 11,818,625,071 |

L01 compression is **12.1584:1**. The old corrected archive is still retained but
not counted again as a newly created batch archive. The workspace boundary is
the prior [local inventory](local-evidence-retention-2026-09-05.md), plus the two
named resolver kits (11,963 and 11,868 retained metadata bytes). Symlinks are not
followed, and unrelated user files/Railway are excluded. Subsequent documentation,
Git and test-cache bytes may change workspace totals slightly.

Temporary data peak was **3,720,108,688 bytes**: one expanded file plus the
isolated archive copy. Counting the new retained archive as well gives
**4,002,826,078 additional peak bytes**, plus metadata, above the pre-run footprint.
The direct-comparison and independent expanded copies were sequential, not
simultaneous. Both expanded copies and the new isolated archive duplicate were
removed only after verification; those new temporary bytes are **not** included
in reclaimed pre-existing storage. The other eight candidates required zero
expanded/archive scratch because their contracts reject before writing.

Before final retirement, filesystem available space was 284,672,000,000 bytes,
well above the 3,705,826,754-byte future-restore requirement including 256 MiB
headroom. It rose to 288,358,400,000 during original/temporary-duplicate removal.
This whole-volume observation is not exclusive APFS reclamation. No ratio is
extrapolated to provider captures, affiliation/researcher evidence or other classes.

## Validation, pins and next boundary

65 focused existing resolver/archive/certification tests pass before and after
retirement (post-run 0.81s). Independent pre/post-retirement review, whitespace,
64 local documentation links and nine documented evidence pins pass. The
only audit issue was JSON handoff rounding numeric nanosecond timestamps: a guard
stopped before deletion; fresh hashes/inodes were reverified and exact timestamps
retained as decimal strings in `exact-identities.json`. Nine JSON round-trip checks
pass. Initial inventory metadata remains unchanged. No shared archive, checksum,
restore or resolver source was modified, and no production code changed.

All following files are below the batch evidence directory:

| Retained file | SHA-256 |
| --- | --- |
| `candidates.json` | `7cd26796343ee70d72d4c9f4c179ae2a3a0bc961003468eda5be46d96d25e97f` |
| `exact-identities.json` | `036d0aa995f90410a6f415277670dd481af56b5f28a7c0000e650b3216c08b21` |
| `batch-result.json` | `03a0e7d97de3ee0f03059a38238fb3315c17422c282906368b0152d7b0f2c085` |
| `L01/archive/8d9ba03a16bb5a6b8051af8f7974e44a7b96027f8b99a2c94858827182cf76ed.jsonl.gz` | `2083a78ca1b0db5e5e8cc31d3a7e59dfb45c602b44cb29b8bbf38142857bb7a1` |
| `L01/archive/archive-manifest.json` | `88e70bb57a75c8f10e6aa298c05029b1a2cb29125edfc778e4964fb32735104e` |
| `L01/artifact-descriptor.json` | `86442881101e81336306bd1de5de2d05d5d2530b5a45e3ba38bcc92d20aab45c` |
| `L01/resolver-proof.json` | `5568756e7d6257ac4e8db155d02a89cedb889105246b2fe3d93f6db005a737c7` |
| `L01/authority-record.json` | `0cfaa44cca8194c335ec9a9aa01731a8904b45e6f07dd7c96232492b4af1ca3a` |
| `L01/retirement-receipt.json` | `a824e85b17260432bfe9510049878e643b97a5a71a1427dcc7473328ad2c8bd2` |

Historical certification-manifest SHA-256 remains
`17353306ba2a164b790b8e2fcbb59874f196abdf534d88038b8ca70bf92d722a`;
recovery source pins remain those in the [resolver report](artifact-resolver-2026-09-05.md).

NO-GO group: eight unsupported paired v1/v2 manifest/path contracts, which need
a separately reviewed compatibility decision, not a quick destructive retry.
The next highest-value **class to review**, not process here, is affiliation
evidence: the prior inventory measured 2,267,637,717 bytes, including two exact
1,128,564,601-byte replay copies. Those paths remain required; no deletion or
compression savings are assumed. This batch stops here. Same-host recovery is
not independent-host backup durability; the combined 5 GB budget still fails,
and scientific activation, Full Physics loading and v3.1 remain unauthorized.
