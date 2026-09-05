# Scientific evidence storage architecture

Status: implemented foundation; production migration deferred

Policy version: `scientific-evidence-storage-policy-v1`
Last reviewed: 2026-09-05

Physics Atlas keeps PostgreSQL for canonical, queryable scientific state. It
does not treat PostgreSQL as an archive for every immutable provider response.
This distinction is required for reproducibility and for safe operation within
the current Railway volume.

## Target tiers

### Hot — PostgreSQL target state

- canonical papers, researchers, institutions, fields, and geographic entities;
- typed authorship, paper-time affiliation, and other query relationships;
- compact cutoff-bound citation observations;
- current certification and review decisions;
- metric observations and their compact reconstruction metadata;
- source cursors, checkpoints, update lineage, and checksum-bearing provenance
  references.

### Warm — external, quickly retrievable evidence

- recent content-addressed certification inputs;
- review bundles and reviewed manifests;
- recent replay artifacts needed for reconstruction or investigation.

### Cold — external immutable archive

- original provider pages and large full snapshots;
- historical backfill bundles;
- replay and validation archives.

Warm and cold artifacts use immutable references containing a URI, SHA-256
digest, byte size, media type, compression, and tier. A reference is not valid
until its digest and size verify. Local filesystem storage is supported for
staging and tests; a production object-store adapter may be added without
changing scientific identities or metric contracts.

## Processing rule

```text
Provider
  -> bounded stream/read
  -> normalize
  -> canonicalize
  -> certify
  -> persist necessary canonical state and compact provenance references
  -> archive required raw evidence externally
  -> discard temporary processing data
```

An external write must complete and verify before a database transaction can
refer to it or advance a cursor. A missing, changed, or unverifiable artifact
fails closed. Fixture mode remains self-contained and may retain its small raw
payloads for deterministic tests.

Existing `SourceSnapshot.storage_reference` is the migration seam. The current
production schema still duplicates raw provider evidence at snapshot and
record level; no destructive production migration is part of this milestone.

The [bounded payload-reference pilot](validation/payload-reference-recovery-2026-09-05.md)
demonstrates exact original-byte recovery and unchanged parser/canonicalization/
certification outputs for one retained batch. Its SQL replica keeps required
normalized attributes, IDs, timestamps, provenance and indexes hot, sharing
checksum-bound page references across raw occurrences. Original payload hashes,
compressed archive hashes and legacy identity/snapshot checksums remain distinct.
This is not a deployed dual reader: current NOT NULL payload columns, worker
transactions and cursor behavior are unchanged. Missing/corrupt references must
fail closed, never masquerade as empty JSON. Production integration and a durable
independent restore rehearsal remain separate from local artifact verification.

## Storage Budget Gate v1

Full Physics loading requires both the existing Joint Metric Activation Gate
and `storage-budget-gate-v1` to pass. The storage gate uses measured volume
capacity rather than a plan label and requires:

1. a representative staging measurement of at least 10,000 canonical papers
   on the final schema after database statistics are refreshed, with measured
   sample bytes, fixed bytes, environment, and timestamp recorded;
2. all expected hot rows, including citation, certification, review, and metric
   state, included in the estimate;
3. a 25% estimation contingency;
4. projected steady-state usage at or below 60% of actual capacity;
5. projected peak usage, including WAL and the largest expected migration,
   index build, or rewrite working set, at or below 80% of capacity;
6. checksum-verifiable references for every externalized required artifact;
7. a demonstrated backup and restore path.

The projection is also bound to a content-addressed target-population manifest
(population ID, exact canonical-paper count, and digest of the paper-ID set).
The target cannot be smaller than the representative sample, and the claimed
steady-state projection cannot be lower than the deterministic
`final-schema-linear-lower-bound-v1` estimate derived from the measured sample
and fixed components. The backup/restore record retains the source backup ID
and digest, isolated target and environment, verification-check digest,
timezone-aware completion time, and reviewer identity.

These documents are reviewed operational attestations. Content addressing
proves that the reviewed bytes have not changed; it does not by itself prove
that a SQL measurement or physical restore occurred. Production authorization
therefore still depends on restricted operator review of the underlying audit,
population, and isolated-restore outputs. Reviewer identity and authority are
authenticated by the external operating process, not by the artifact format.
The current implementation is
fail-closed when any typed input or referenced artifact is missing.

Missing capacity, an unrepresentative measurement, or missing peak/steady-state
inputs produces `WITHHELD`, never an optimistic pass. The 60% limit retains
normal operating headroom; the 80% peak limit retains emergency headroom.

The measured 2026-09-04 production state and projections are recorded in the
[storage sizing report](validation/storage-sizing-2026-09-04.md).

This gate authorizes a larger Full Physics load. It is not required for ordinary
map/API reads or the currently bounded production updates, and it does not
replace the Joint Gate for public metric activation. The current implementation
provides typed gates and a local artifact-store adapter; it does not migrate
production payloads, deploy object storage, or certify a physical restore.
