# Scientific evidence storage architecture

Status: implemented foundation; production migration deferred

Policy version: `scientific-evidence-storage-policy-v1`
Last reviewed: 2026-09-05

Atlas Physicus keeps PostgreSQL for canonical, queryable scientific state. It
does not treat PostgreSQL as an archive for every immutable provider response.
This distinction is required for reproducibility and for safe operation within
the current Railway volume.

## Combined persistent budget

PA-048 fixes the nominal budget at approximately **5 GB total persistent Atlas
data**, including PostgreSQL, warm/cold artifacts, required snapshots/citation
history, provenance/restore metadata and retained backup/replica copies. An
external store has its own disclosed capacity/cost but is not free extra budget.
Report hot DB savings separately from true combined savings. Ephemeral processing
has a separate peak; existing retained history is not ephemeral by default.

The [production design/total-storage review](validation/production-storage-design-review-2026-09-05.md)
counts a 474-paper closed evidence envelope at 50.941 MB inline versus 35.990 MB
reference-layout total (29.35% less), not the 54.98% DB-only saving. Retained local
evidence already totals 16.248 GB before production, so the observed total-budget
result is **FAIL**. This is not a claim that Railway itself is full. The future
complete production-layout assessment remains **WITHHELD**; migration execution
is **NO-GO** until representation, independent operational restore and total peak
costs are verified. No production schema or payload was changed.

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
This is not a production dual reader: current NOT NULL payload columns, worker
transactions and cursor behavior are unchanged. Missing/corrupt references must
fail closed, never masquerade as empty JSON. Production integration and a durable
independent restore rehearsal remain separate from local artifact verification.

The [one-batch staging integration](validation/staging-dual-read-2026-09-05.md)
adds an explicit inline/reference selection adapter and a private PostgreSQL
source catalog. Both paths recover original bytes before calling the same
existing parser, normalization, canonicalization and certification. Selection
metadata binds acquisition identity to the payload hash/size; an archive write
and read-back must finish before transactional promotion and checkpoint advance.
An unavailable, missing, invalid or corrupt reference returns an operational
`blocked` error before scientific processing—not an empty evidence record, a
certification state, or a silent inline fallback. Deliberate rollback verifies
retained inline bytes and keeps the reference/provenance history without needing
the archive. This bounded rehearsal retains both representations and does not
prove production schema compatibility, archive durability, or storage capacity.

## Validation artifact scaling contract

PA-051: **Full-scale ingestion must not generate full-corpus paired, rollback,
recovery, restore, or comparison ledgers. These are bounded validation artifacts
only.** The ingestion worker has no verbose-validation sink or switch. Scientific
contract imports remain valid; executing installed offline paired/replay commands
in a configured production runtime is forbidden, before input reads/output writes.

Production-scaled certification may retain identity, evidence dimension, status,
reason code, rule/schema/data versions, compact provenance references, and required
cutoff/evidence metadata. Necessary history and unresolved/missing states remain
explicit. This is the target storage boundary, **not a newly deployed compact
certification schema**. NoFormulaMetricRecalculator and metric admission stay
unchanged; the current compact SQL/audit prototype is not production authority.

Full corpus → authoritative scientific processing only. A separately approved,
bounded representative sample → inline/reference, rollback/recovery and exact
restore/equivalence proofs for the pipeline version. Select and pin the sample
before the run; record acquisition/dataset and code versions, selection method,
strata/edge cases, input manifest and hashes, outcome/reason/provenance digests,
conservation/missing-value checks and failures. A convenient sample does not
establish scientific coverage or authorize Full Physics. There is no automatic
sampler and no truncation of certification input. Retain required proof metadata
and unique evidence once; temporary duplicates may be retired only after separate
verification/authorization. Existing historical manifests are never rewritten.

Enforced operational limits (not scientific thresholds):

- Paired certification retains the existing January 13–19, 2020 scope and maximum
  2,498 source occurrences. Fixed recovery/dual-read runners still accept only the
  checksum-pinned 635-occurrence / 474-component batch.
- Retained replay decisions require explicit `validation_max_papers` (CLI:
  `--retain-decisions --validation-max-papers N --output ...`), with `1 ≤ N ≤ 2,500`.
  Manifest paper/estimated-decision counts are checked before artifact verification.
  Actual artifact row/hash verification still follows; no sampling by omission.
- At most 100,000 decisions and 128 MiB of decision bytes per verbose trace.
  In-memory replay and its public writer are bounded too. Streaming retention
  checks actual bytes/count before writing; failure cleans its unpublished temporary
  stream. Paired generation checks its trace before publishing any artifact.
- Development/test execution only, using existing environment/.env settings.
  Summary-only offline replay remains available without retaining a decision
  ledger, but is not a production ingestion or equivalence step.

These limits bound individual proof traces, not all input memory. Do not schedule
a proof per production batch/paper, shard a full corpus into proof outputs, or
retain an expanding series of A/B copies. PA-052 now supplies the reviewed
per-version proof/retention budget below. Runtime settings
and static tests protect accidental reuse, not hostile code with application
privileges. Existing exact single-artifact archive restoration remains governed
by its separate pinned size/checksum/scratch contract; no archive tooling changes.

The [bounded audit](validation/validation-ledger-scaling-safety-2026-09-05.md)
records generator paths, focused tests and a deliberately pathological storage
scenario, not a Full Physics capacity estimate.

### Reusable sample and cumulative proof admission

PA-052 fixes `bounded-cross-track-validation-sample-v1` at 1,000 existing references
(474 official paired + 526 corrected replay), retaining separate source versions.
Sample ID, manifest checksum, selection strata and exact reuse proof are in the
[affiliation-retention report](validation/affiliation-retention-2026-09-05.md).
Future proof versions reuse it unless reviewed evidence/domain expansion requires
a documented replacement; the sample is not a pooled scientific dataset.

`storage/validation_retention.py` caps persistent proof outputs at **1 GiB**,
optionally tightened. All physical files, old versions, archives, copies and
metadata count, including REVIEW. Necessary base source/canonical bundles remain
under PA-048's total budget even when outside this narrower proof-output scope.
The typed inventory/admission binds sample/code/proof versions and a byte
reservation; fresh path/size preflight rejects unlisted managed files, missing
files, stale inventories, unsafe paths and existing output. Optional hash
verification is separate from metadata-only accounting.

The affiliation pilot uses that admission before input/output, bounds complete
selected paper groups and reserves stream/archive/manifest bytes before publishing.
Runs must be serialized; inventory all newly retained files before another version.
This is not an OS quota or automatic integration into every historical CLI:
operators must obtain admission before old standalone validation commands too.
No auto-delete/expiry, corpus sharding, science-policy relaxation or capacity PASS.

Expanded historical affiliation/replay writers are development/test only and
refuse production before IO. Normal production attribution continues through
`materialize_paper_time_affiliations` and authoritative ORM relationships. Only
necessary compact paper-time state, exact shares, unresolved status and provenance
may scale by default; verbose audit/replay artifacts remain bounded, sampled,
ephemeral or cold retained when justified. Existing compact certification/storage
prototypes are not deployed production authority.

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

These volume-oriented inputs are necessary but insufficient for PA-048. A new
approval must explicitly bind a deduplicated cross-store inventory and all
required persistent costs, including archives and backup/retention generations.
The nominal combined limits are 3 GB steady and 4 GB peak after the existing
25% contingency; actual individual-volume limits still apply. The current generic
projected-byte fields/flags do not themselves demonstrate this completeness.
This design review does not reinterpret older attestations or change gate code.

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

## Local historical affiliation authority

The existing historical resolver now lives in
`physics_atlas_api.storage.historical_authority`; the original tool import remains
compatible. Decision archive behavior is unchanged. The affiliation codec adds
exact gzip restoration for paired v1/v2 `affiliation-shares` and replay-v2
`paper-time-affiliation-shares`, without changing scientific parsers or evidence.

An explicit `artifact-authority.json` beside a historical bundle binds its exact
relative role/path/hash/size/rows to a pinned descriptor, storage root, pinned
manifest and **historical recorded manifest path**. Without an index the legacy
inline reader remains unchanged. With an index, absent/ambiguous/broken authority
is an error, not a fallback. Descriptor identity is type + schema version + exact
content SHA-256; multiple old paths require separate verified historical bindings.

The selected archive is verified and restored into one resolver-owned temporary
file; existing readers consume those bytes while retaining original provenance
paths. Context exit removes only that temporary file. The codec bounds one old
artifact to 4 GiB / one million rows and its archive to 192 MiB; these are restore
bounds, not permission to generate a large new validation corpus. Creation and
adoption refuse production runtime. Production worker call-boundary tests exclude
the archive tools and retain authoritative database affiliation state only.

For an immutable older script needing ordinary files, restore into an isolated
copy of the historical tree under the recorded **relative** artifact path. Supply
that tree through the script's existing root argument or its unchanged relative
layout. Never rewrite its manifest to point at compressed bytes. Exact source
checksums/row dimensions still verify the restored original representation.

`backend/tools/prove_affiliation_archive.py` accepts a pinned, self-contained
isolated plan/kit and emits only an aggregate receipt. Its OS-denial controls
must be installed externally; the runner refuses without them. This is local
historical authority, not a production payload migration or independent backup.
See [PA-053](DECISIONS.md#historical-affiliation-archive-authority--2026-09-05)
and the [measured batch](validation/affiliation-archive-batch-2026-09-05.md).

## Remaining local storage boundary

The [final consolidation review](validation/final-storage-consolidation-2026-09-05.md)
inventories the remaining provider, researcher and replay classes without
extending archive authority. Generic exact recovery is a representation proof,
not an automatically usable historical manifest binding. Current callers still
need the unsupported originals. In particular, 102 retained INSPIRE pages exceed
the 16 MiB payload envelope bound; some historical page manifests lack required
acquisition metadata. Both require separately reviewed compatibility work, not
silent truncation, fabricated timestamps or a blanket larger limit.

No full-corpus provider/researcher comparison output is permitted by PA-051/052.
Actual retained history and proof archives still count once toward PA-048, while
the cumulative proof budget is a cross-cutting limit, not an extra storage pool.
Future compact-component scenarios must include retained history and unknown
backup/citation/review costs; they are not final-schema capacity measurements.
