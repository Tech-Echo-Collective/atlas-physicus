# Atlas Physicus — proposed local evidence retention policy

Draft, 2026-09-05. This is a review proposal, **not deletion authorization or an
automatic cleanup policy**. PA-048's combined persistent budget still applies.
Production storage, scientific methods and release tags are outside this policy.

## Retention classes

| Evidence class | Default treatment | Conditions for a smaller representation |
| --- | --- | --- |
| Canonical current evidence | **KEEP** | Preserve current manifests, exact populations, identity/review decisions, source linkage and calculator eligibility. A representation change must restore exact supported inputs and paths. |
| Milestone validation evidence | **KEEP / COMPRESS** | Retain result reports, code/version identifiers, manifests, hashes, inputs and unique historical decisions. Supersession does not make a different scientific result disposable. |
| Raw source evidence | **KEEP / COMPRESS** | Preserve original bytes, acquisition/source/cutoff metadata and occurrence lineage. Today's provider response is not a reconstruction of historical evidence. |
| Replay outputs | **COMPRESS**; **REGENERABLE** only with proof | Require retained complete inputs, pinned code/environment and successful exact output reconstruction. File equality alone does not authorize breaking an older manifest's relative paths. |
| Temporary/cache data | **DELETE_CANDIDATE** after verification | Establish ownership, inactivity and lack of unique evidence. Preserve small proof reports; check that a restore workspace is a redundant working copy, not the only backup. |
| Superseded artifacts | **KEEP / REVIEW** by default | Exact duplicates need a verified retained copy and usable path/restore mapping. Different hashes remain unique until a separate evidence review proves otherwise. |

`DELETE_CANDIDATE` means eligible for an explicit, target-specific cleanup review,
not permission to remove it. `REGENERABLE` means demonstrated reproducibility,
not merely that a script exists. Installed dependencies can be rebuild candidates,
but retain lock/environment records and investigate local modifications first.

## Exact duplicate and compaction requirements

- Inventory only explicitly owned Atlas roots. Do not traverse unrelated files,
  follow symlinks outside the boundary, or treat filenames as checksums.
- Verify content hash and size with stable input metadata; compare ordered
  relative paths and member hashes before calling entire bundles duplicates.
- Separate redundant logical bytes from actually reclaimable physical blocks.
  Hard links, filesystem clones, allocation and backup copies affect savings.
- Keep at least one verified representation of every unique required input and
  decision. Record every original logical path, linked manifest and occurrence.
- Use a versioned lossless format, exact original and compressed hashes/sizes,
  bounded streaming restore and a checksummed manifest. Preserve ordering,
  whitespace, null/missing/zero distinctions and original artifact identities.
- Validate recovery from the archive without relying on the original input.
  Where outputs are scientifically meaningful, compare their existing validation
  summaries as well as the full original-byte hash. Do not broaden replay scope.
- Retain originals during pilots. Replacement/deletion needs separate approval,
  verified restore instructions and path compatibility, a rollback plan and an
  accounting of all required copies. Do not silently rewrite historic manifests.
- A local read-only file is not a durable independent backup or an object-store
  immutability guarantee. Specify the required backup boundary separately.

## Required report for each future large job

Before a run, name its bounded inputs, output directory, estimated persistent
and peak temporary bytes, retention owner and verification/stop conditions.
After the run, record:

1. New persistent bytes and file count, including archives, manifests and backups.
2. New temporary bytes and peak working-space use, reported separately.
3. KEEP / COMPRESS / REGENERABLE / DELETE_CANDIDATE / REVIEW totals, with disjoint
   membership so a duplicate is not counted twice as a compression saving.
4. Input/output/version manifests and exact restore/reproduction checks.
5. Candidate-to-retained-copy or archive mappings, active references and reasons
   a path may or may not be removed.
6. Actual reclaimed bytes, if separately authorized; otherwise explicitly zero.

No age-based expiry, automatic deletion, bulk rewrite or scientific-policy
relaxation is proposed. Stop on missing provenance, unique unreviewed evidence,
changing inputs, unsafe restore paths or unverified archive integrity.
