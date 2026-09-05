# Atlas Physica — bounded archive-promotion review

2026-09-05, starting current `main` / `05783c1`.
**ARCHIVE PROMOTION = FAIL; ORIGINAL RETIREMENT = NO-GO.**
This is a dependency/authority failure, not a corrupt-archive finding. Nothing
was deleted, compressed, replayed, promoted or migrated; Railway was not accessed.

## Exact artifact identity

All evidence paths below are relative to the existing `physics-atlas-evidence/`
root beside the source repository. Fresh SHA-256 and stable-file checks passed
for both originals and the gzip; manifest/proof file hashes also match.

| Artifact | Exact path | Bytes |
| --- | --- | ---: |
| Corrected original, actually covered by the archive | `cond-mat-validation-v1-2020-2025-v2-certification-corrected-final/certification/decisions/459c1f4065130cef61c3c098f4775994982bd08f2ecb2e7f313d076a8d48aa7f.jsonl` | 3,437,302,947 |
| Historical original, **not covered** by this archive | `cond-mat-validation-v1-2020-2025-v2-certification-retained-final/certification/decisions/8d9ba03a16bb5a6b8051af8f7974e44a7b96027f8b99a2c94858827182cf76ed.jsonl` | 3,437,391,298 |
| Verified gzip | `local-retention-review-2026-09-05/pilot/history-jsonl-v1/459c1f4065130cef61c3c098f4775994982bd08f2ecb2e7f313d076a8d48aa7f.jsonl.gz` | 282,831,800 |
| Archive manifest | `local-retention-review-2026-09-05/pilot/history-jsonl-v1/archive-manifest.json` | 2,928 |
| Existing equivalence proof | `local-retention-review-2026-09-05/pilot/history-jsonl-v1/pilot-result.json` | 3,357 |

Original SHA-256 values are their full filename stems. Gzip SHA-256 is
`9ed30287fb6ce9d93e2259ab753fd8488e66043f51a09f7ce2df6588d8664879`;
archive-manifest SHA-256 is
`29987afb414b768901366755b4ce1531b44621fd0aac54c77690017605b99e6d`;
proof SHA-256 is
`0e9c4a9e5fba26a73807a707b9f9d07a512b3b581bd231b83c9e59bd6f6f818c`.
The manifest explicitly binds corrected `459c1f40…`, not historical `8d9ba03a…`.
No matching archive/proof for the historical ledger was identified in the scoped
evidence inventory. Similar sizes do not establish interchangeable evidence.

## Dependency and authority check

- **A — current reproducibility contract:** corrected certification manifest
  `9c79eced71031e79f17827ba00825a9541d63f527aa7d4131940799b1711b0d3.json`
  under its bundle's `certification/manifests/` binds the exact uncompressed path,
  size, hash and 2,766,760 rows; it declares `artifact_available: true` and
  `summary_only: false`. The current scientific validation report cites this
  manifest as final evidence. The retained-file contract in
  `backend/src/physics_atlas_api/certification/staging.py:1213` and its test in
  `backend/tests/test_historical_replay_materialization.py:644` use that path.
  There is no verified archive-authority/path resolver replacing that contract.
  No API/worker dependency on these local ledgers was found; this is **not** a
  demonstrated production outage risk.
- **B — historical mentions:** inventory, pilot README, prior validation reports
  and cleanup receipts mention original/restored paths. Those mentions alone
  do not require retaining a working copy, and none was rewritten.
- **C — archive-satisfied recovery:** standalone `restore_archive()` in
  `backend/tools/compact_historical_artifact.py:296` can restore corrected bytes
  to an explicit new path without the original. Its versioned manifest records
  checksums, ordered decisions/states/reasons/versions and provenance summaries.
  Existing proofs establish recoverability, not an archive-backed authority
  lookup for the retained certification bundle.

The user's dependency-stop condition applies. **No fresh isolated restore was
started**, no temporary restore file exists, and no new scientific equivalence
claim is made. The prior exact-restore proof remains unchanged. Manual recovery
cannot be silently reclassified as a tested original-retirement contract.

## Storage and next action

At `03:38:24Z`: evidence **16,532,083,020 bytes / 5,367 files**, Atlas-only
workspace **1,878,177,901 bytes**, combined **18,410,260,921 bytes**. Subsequent
documentation adds only small workspace bytes. **Logical reclamation: 0**.
No before/after APFS reclamation measurement was taken because no deletion was
attempted; no physical savings are claimed. Both originals, archive, manifests,
proofs and all other evidence remain retained.

Smallest next action: separately review an additive checksum-bound archive
authority/path-resolution contract for the **corrected** ledger, preserving
historical manifests, then verify isolated recovery and provenance through that
contract before reconsidering retirement. Do not compress the separate historical
ledger or change scientific policy as part of that review.

This review changes documentation only; no application tests or CI rerun is
needed for the read-only dependency check. Current source `05783c1` passed
[CI 33942051823](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33942051823).
No release tag or deployment configuration changed.
