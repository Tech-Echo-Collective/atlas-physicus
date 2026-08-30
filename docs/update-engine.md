# Incremental update engine

## Purpose

The v3.0.4-alpha worker updates changed source records without rebuilding the entire Atlas. It keeps provider-specific acquisition behind `SourceConnector` and keeps metric formulas behind `MetricRecalculationContract`.

```text
source cursor
    → bounded changed-record batch
    → immutable source snapshot
    → normalization
    → authority-gated identity resolution
    → canonical upsert or review item
    → paper-time affiliation and field-assignment materialization
    → affected metric partitions
    → dataset version and status
```

Synthetic and historical pilot datasets are protected from live ingestion. The engine refuses to write a provider batch when `DatasetState.dataset_kind` is not `live-api`.

## Transaction and audit model

Each attempt creates an `UpdateRun` containing source, timestamps, cursor before/after, fetched/added/changed/unresolved/failed counts, affected entities, affected metric partitions, status, and error details. A successful batch also creates:

- a content-addressed `SourceSnapshot` with the exact provider page envelope and parent snapshot;
- source-specific `RawEntityRecord` rows;
- versioned `IdentityResolution` decisions and `IdentityReview` items when needed;
- a `DatasetUpdate` describing derived changes and processing versions;
- an updated `DatasetState` and `SourceCursor`.

The source high-water cursor advances only after the complete closed window succeeds. A separate persisted checkpoint keeps the window's upper bound and current page/offset. Each cursor also stores a versioned acquisition-scope key, and the live `DatasetState` stores the shared corpus scope. If the configured provider filter or ROR target set differs from the stored key, or the existing live dataset is unmarked/different, ingestion fails before provider I/O; resetting a cursor cannot silently append bounded records to an older broad corpus. Snapshot content identity includes the scope as well as the provider payload. If a later page fails, the next worker cycle resumes that page immediately; it does not wait for the normal cadence or move the cursor beyond unseen records. One malformed record fails the batch and leaves the checkpoint available for retry. Provider omission does not delete a canonical record. An identical same-scope content checksum reuses the snapshot and completes as an idempotent replay.

## Identity and graph changes

Normalization never merges entities. The engine first checks compatible
authority identifiers, then canonical/alias evidence, and otherwise records
unresolved or ambiguous evidence for review. Only matched or explicitly created
canonical records enter the graph. Every provider paper author slot now enters
the exact Fractional Attribution v1 ledger. Paper-time institutions resolve
only from supported authority identifiers or a unique reviewed exact name;
unresolved, ambiguous, and absent affiliation mass remains withheld. Each new
snapshot supersedes the current materialization without deleting earlier
evidence. Separate profile affiliations remain dated relationship rows and
cannot overwrite it. Provider reference and citation structures remain raw
evidence until their own reviewed canonicalization rules pass.

The alpha stores the persistent review queue but does not provide a review UI or automatic approval. Corrections should be reversible and must preserve prior source and resolution provenance.

## Incremental metric boundary

Changed records produce partitions across the relevant dimensions:

```text
entity type + entity + field + country + institution + period + metric
```

`MetricRecomputationPlanner` records only affected partitions. Five v1
calculators now exist as deterministic scientific framework code, but
`NoFormulaMetricRecalculator` remains the production implementation and writes
no values. A future explicitly activated recalculator may append observations
only after the exact-five Joint Activation Gate passes and must retain all
definition, algorithm, normalization, attribution, ontology, mapping, threshold,
dataset, and calculation lineage. Historical observations must not be silently
overwritten, and missing remains missing rather than zero.

## Scheduling

The worker wakes on `PHYSICS_ATLAS_WORKER_POLL_SECONDS` and asks `UpdateScheduler` which sources are due. Defaults are:

| Source | Cadence |
| --- | --- |
| INSPIRE | daily, `subject:Theory-HEP` under `hep-th-v1` |
| arXiv | daily, `cat:hep-th` under `hep-th-v1` |
| ROR | weekly when explicit target IDs are configured |

`PHYSICS_ATLAS_ACQUISITION_SCOPE` currently accepts only `hep-th-v1`. ROR uses the comma-separated `PHYSICS_ATLAS_ROR_RECORD_IDS` allowlist and makes one record request per configured ID; it does not use a modified-record registry scan. With no IDs, the ROR connector is disabled and the worker makes no ROR request. A changed target list produces a different cursor scope and therefore requires an explicit cursor decision.

ORCID and Crossref are not scheduler sources. Their connectors accept only targeted `fetch_record` requests for an already-known ORCID iD or DOI and reject global `fetch_new_records` calls. A future enrichment job may invoke those bounded lookups from resolved canonical evidence without turning either provider into an unscoped crawl.

A PostgreSQL advisory lock prevents concurrent workers from processing the same schedule. Provider connectors also set request pacing and bounded batch sizes. These defaults can be operated by the compose worker or a cron-compatible one-shot command; they do not claim second-by-second realtime updates.

Useful worker forms from the backend environment are:

```bash
physics-atlas-worker --once --source inspire
physics-atlas-worker --once --source all --check-resources
physics-atlas-worker --check-resources
```

## Bounded historical raw acquisition

`physics-atlas-backfill` is a staging-only acquisition boundary for the fixed
`hep-th-v1`, 2020--2025 trial. It has no database, canonical-entity, source-
cursor, or metric imports. Preview is network-free; provider access and output
require the explicit `--execute` flag:

```bash
physics-atlas-backfill plan --output /external/staging/path --execute
physics-atlas-backfill acquire --output /external/staging/path --execute
```

The output path must be outside the repository. Each provider/year partition
records the exact query and version, expected provider total, unique record
count, page checksums, terminal status, and resumable checkpoint. A partition
is raw-acquisition-complete only when it reaches its terminal page with no
duplicates and its unique count equals the provider total. This is not a
complete-year metric certificate and it performs no canonical materialization.
INSPIRE partitions use its earliest-record date (`de`); arXiv partitions use
submission date. Neither is silently relabeled as a normalized publication-year
cohort.

Fixture mode is the default. Provider-backed operation requires an explicitly prepared `live-api` dataset state, provider-policy review, credentials where required, and an operated database.

On an empty database the worker seeds only reference vocabulary: Physics, the broader field taxonomy, ISO countries, geographic views, and metric definitions. It does not copy demonstration institutions, researchers, papers, relationships, or metric observations. Fixture ingestion labels snapshots, raw records, entity provenance, and dataset metadata as deterministic synthetic fixtures, even though it exercises the same API/database path.

## Failure recovery and observability

Updates are resumable from the stored cursor. Consecutive failures mark source health as degraded without erasing the last successful time. Structured logs include event, source, run ID, and record counts. `/api/updates/status` exposes:

- last successful and failed update;
- per-source attempt, success, cursor, scope version, and failure count;
- unresolved review count;
- resource-check failure count;
- metric-recalculation state.

This is lightweight operational visibility, not a full monitoring platform. Operators should alert on repeated failures, growing review queues, old source success times, migration errors, and resource-check backlogs.

## Current limitations

- There is no hosted queue, distributed lock service, or administrative review interface.
- The default production calculator records partitions but intentionally does not execute the implemented, still-withheld v1 formulas.
- Closed-window cursors are validated for bounded paging but still need long-running provider-scale and schema-change testing.
- There is no approved historical canonical-materialization/import command.
  The raw acquisition tool deliberately stops before identity resolution,
  institution promotion, citation cohorts, or database writes. Deletion/
  tombstone policy, retractions, and unresolved cross-provider bibliographic
  conflicts still require reviewed rules.
- ROR target IDs are operator-configured rather than automatically derived from reviewed affiliation evidence.
- Targeted ORCID/Crossref enrichment is not yet orchestrated automatically from every newly discovered identifier.
- arXiv scheduled acquisition is a `submittedDate` new-submission stream; complete revision discovery requires a future reviewed provider strategy.
- Paper-time INSPIRE affiliations can now materialize conservatively when exact institution evidence exists; unresolved affiliations, references, and citation structures remain evidence rather than guessed edges.
- A successful fixture run demonstrates deterministic behavior, not live provider completeness.
