# Atlas Physica — single corrected-ledger retirement

2026-09-05, starting clean `main` / `d9aa5c7`.
**Retirement GO / COMPLETE**, after all seven user-required checks passed.
Only the corrected uncompressed ledger was removed. No other evidence, Railway,
provider, replay, compression, scientific policy, metric or release tag was touched.

## Exact target and retained authority

Paths here are relative to the existing `physics-atlas-evidence/` directory
beside the source repository. The only removed file was:

```text
cond-mat-validation-v1-2020-2025-v2-certification-corrected-final/certification/decisions/459c1f4065130cef61c3c098f4775994982bd08f2ecb2e7f313d076a8d48aa7f.jsonl
```

It contained **3,437,302,947 bytes / 2,766,760 decisions**; the full filename stem
is its freshly verified SHA-256. The authoritative retained representation is
the existing 282,831,800-byte gzip at:

```text
local-retention-review-2026-09-05/pilot/history-jsonl-v1/459c1f4065130cef61c3c098f4775994982bd08f2ecb2e7f313d076a8d48aa7f.jsonl.gz
```

Its SHA-256 remains
`9ed30287fb6ce9d93e2259ab753fd8488e66043f51a09f7ce2df6588d8664879`.
The unchanged descriptor at
`artifact-resolver-2026-09-05/corrected-ledger-authority.json` selects
`corrected-ledger-archive-v1` for logical artifact
`045b1244b310d7fd8d7a581eeb0b290b14401202e233c51f904a6e750d9ac4fc`.
The descriptor's unselected original entry is not probed or used as fallback;
the new retirement receipt records its absence without rewriting old metadata.

## Dependency and integrity recheck

- Independent read-only review covered repository callers and 3,047 scoped
  evidence metadata/script files. No active API, worker or scientific reader
  requires the corrected original. No open handles were reported.
- `certification/staging.py` publishes newly generated streams, not a reader
  requiring this old file. Its retained-path test reads generated temporary
  fixtures. Old inventories, validation reports and completed one-shot cleanup
  scripts are historical records and remain unchanged.
- The unchanged historical certification manifest `9c79eced…` self-checks and
  binds exact role/path/hash/size/rows. Existing resolver binding functions verify
  it against the pinned descriptor and archive manifest. Historical paths are
  checked lexically; archive-authoritative resolution does not open the original.
- Fresh full-file SHA-256 checks passed for the original and gzip; the descriptor,
  archive/certification manifests, authority record, both retained proofs and all
  three recovery-tool source pins match the prior [authority proof](artifact-resolver-2026-09-05.md).
- The retained `04:13:19Z` OS-denied-original restore proof remains valid. Its
  complete scientific summary equals the archive manifest and both sides of the
  original byte-comparison proof: 2,766,760 decisions; 388,038 certified,
  1,287,642 needs_review, 1,026,684 insufficient_evidence, 64,396 withheld and zero
  conflicted, with identical ordered reason/version/provenance digests.
- Scratch availability was **281,804,800,000 bytes** before deletion; the check
  required 3,437,302,947 bytes plus 256 MiB headroom. A future restore fits now;
  availability must still be checked when a future restore actually runs.

At `04:25:46Z`, only the freshly checked original was unlinked. A before/after
inventory confirms exactly one missing file, no other modified evidence files,
and unchanged metadata for the separate 3,437,391,298-byte historical ledger
`8d9ba03a…`. A fresh gzip hash plus descriptor/historical-manifest binding check
passes with the corrected original absent. No full restore or recalculation was
rerun: unchanged pins preserve the previously verified exact-recovery proof.
Scientific eligibility is unchanged; an audit ledger is not a certified metric
input, and this task creates no observations.

## Storage and retained proof

Logical reclamation: **3,437,302,947 bytes**, from one file only. The new read-only
checker and retirement receipt add 14,191 small audit bytes. Evidence now totals
**13,094,800,623 bytes / 5,372 files**. At `04:28:05Z`, Atlas-only workspace is
**1,878,390,963 bytes**, giving **14,973,191,586 bytes combined**. Workspace includes the
same explicitly scoped repositories, legacy prototype, social asset, stopped
private DB and prior restore workspace as the [local inventory](local-evidence-retention-2026-09-05.md),
plus the resolver kit's six small files / 11,963 bytes. Symlinks are not followed;
unrelated Tech Echo/user files and Railway are excluded. Documentation/Git/cache
bytes may change slightly after this snapshot.

Filesystem available space reported **281,804,800,000 → 285,081,600,000 bytes**,
an observed increase of **3,276,800,000 bytes**. This is a whole-volume observation,
not an exact APFS exclusive-block saving or a guarantee about snapshots/clones.
The difference from logical reclamation is not classified as extra cleanup.

New append-only local record:
`corrected-ledger-retirement-2026-09-05/retirement-receipt.json`, SHA-256
`9ba54d2d7a5b3230396111fb7b24c990b60b38b7c2bce5bff60f59c303669f96`.
Its read-only `verify_retirement.py --original-absent` companion rechecks pins,
archive integrity and binding without expansion; source SHA-256
`27976982fcbeef834dbff81ce8acc112a4f1ac45c0588d8caccdfe6b2006ecad`.
Recovery remains the existing resolver recipe in the authority report, not this
lightweight checker. Old authority/proof records retain their historical
`originals_retained` statements and are not rewritten.

The archive, descriptor, manifests/checksums, validation proofs, distinct historical
ledger and every other pre-existing evidence artifact remain retained. This is
same-host recoverability, not independent-backup durability. Total-storage and
scientific gates do not change. No next deletion or second compression is cleared.

## Repository validation

Application/resolver source, scientific inputs and deployment configuration are
unchanged. Starting `d9aa5c7` passed
[CI 33944202529](https://github.com/Tech-Echo-Collective/Physics-Atlas/actions/runs/33944202529).
33 focused resolver tests pass after retirement (0.07s). Whitespace checks and
61 local documentation links pass; independent dependency review is complete.
Only this report and current context require documentation updates; historical
validation reports remain untouched. No new application CI run is needed for
the local evidence removal; publication status is reported separately.
