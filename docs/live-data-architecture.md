# Live data architecture

## Status vocabulary

Physics Atlas uses four deliberately distinct data modes:

| Mode | Meaning |
| --- | --- |
| Synthetic demo | Hand-authored local JSON used to demonstrate the interface and Metric Engine contracts. It is not scientific evidence. |
| Historical INSPIRE pilot | A preserved, bounded INSPIRE-HEP snapshot and reproducible derived export. It is real metadata but incomplete and selection-biased. |
| Live API fixture mode | The FastAPI/PostgreSQL path running against deterministic provider fixtures. It exercises ingestion and serving without contacting providers. |
| Provider-backed live mode | The same backend configured to call official provider APIs and refresh a deployed database on a schedule. It is only truly live when that backend, worker, and database are hosted and operating. |

The provider-backed architecture is operated through Railway and the public
GitHub Pages frontend uses `APIRepository` on normal routes. Synthetic and pilot
modes remain internal reproducibility and explicit fallback paths. The
repository contains no hosting credentials, and no mode silently combines
observations from another mode.

## Processing path

```text
INSPIRE / arXiv / ROR scheduled feeds
        ↓
source-specific connectors and checkpoints
        ↓
immutable source snapshot + raw entity records
        ↓
normalization + provider-category mapping
        ↓
identifier-led entity resolution
        ↓
canonical PostgreSQL entities, paper-time affiliations, and temporal relationships
        ↓
explicit evidence certification and affected metric-partition planning
        ↓
certified raw metrics → metric-specific normalization → Atlas Scale
        ↓
reviewed exact-five publication gate
        ↓
FastAPI read models
        ↓
APIRepository
        ↓
map-first React / MapLibre Atlas
```

Known ORCID iDs and DOIs can additionally pass through targeted ORCID/Crossref record enrichment; neither source is globally polled. External-resource enrichment is an adjacent path: canonical entity → typed resource → bounded verification history → profile read model.

The browser never contacts scientific providers directly. Provider syntax, credentials, rate limits, retries, and checkpoints stay behind connector interfaces. FastAPI does not expose SQLAlchemy models as a transport contract, and React does not contain identity-resolution or metric-calculation logic.

## Persistence and provenance

PostgreSQL stores canonical/queryable entities, normalized relationships,
compact provenance, update lineage, resolution decisions, review items,
resource checks, and versioned metric observations. The target hot tier also
includes compact certification/review state, but the current certification
bundles remain content-addressed external staging evidence until that schema is
designed, deployed, and load-tested. The current production schema still
retains provider response envelopes in `SourceSnapshot` and normalized row
evidence in `RawEntityRecord`; a verified future migration may move large
immutable payloads to warm/cold content-addressed storage while keeping their
references hot. A canonical update does not destroy the lineage that produced
an earlier decision.

Real-data records retain, where applicable:

- provider and source record ID;
- source snapshot and retrieval time;
- dataset and processing version;
- identity-resolution method, confidence, and status;
- metric definition, algorithm, calculation version, and calculation time.

Profile `Affiliation` is a temporal relationship, not a permanent researcher
property. `PaperAffiliation` separately preserves each publication-time slot,
exact fractional share, resolution state, and snapshot lineage; a current
profile cannot overwrite it. Missing bounds, relationships, or observations
remain unknown and are never converted to zero.

## Incremental operation

The connector boundary supports batch fetches, record fetches, normalization, and cursor state, but provider capabilities are explicit. The versioned `hep-th-v1` scope constrains INSPIRE to `subject:Theory-HEP` and arXiv to `cat:hep-th`; ROR refreshes only configured known IDs and is disabled without targets. ORCID and Crossref reject unscoped batch polling and expose targeted record retrieval only. The update engine records an `UpdateRun`, persists a content-addressed snapshot, applies changed normalized records, advances the source cursor only after success, and records a `DatasetUpdate` with affected entities and metric partitions.

An identical batch is an idempotent replay. A failed record prevents checkpoint advancement, so the batch can be retried. Canonical entities are not deleted merely because a provider temporarily omits a record. Ambiguous identity evidence enters a persistent review queue instead of being silently merged.

The scheduler uses daily checks for INSPIRE and arXiv and weekly refreshes for configured ROR targets. INSPIRE uses day-resolution provider windows; arXiv uses its Query API `submittedDate` stream and therefore discovers new submissions, not a provably complete stream of subsequent revisions. ROR checkpoints the bounded target list. An incomplete multi-page checkpoint is due immediately rather than waiting for the next cadence. Cursors are bound to the exact scope/policy version and fail closed on mismatch. ORCID and Crossref enrichment is explicitly triggered for known identifiers and has no global schedule. These are project defaults, not a promise of second-by-second realtime data. Actual freshness is bounded by provider availability, access terms, worker uptime, and successful resolution.

Scheduled connectors keep a fixed upper time bound across every page in a batch. Page state is persisted separately from the high-water cursor, so a partial failure resumes the same closed window and cannot silently skip records that appeared mid-run.

## Frontend repository boundary

The frontend supports `StaticAtlasRepository`, the preserved pilot repository, and `APIRepository`. A source change replaces the repository as one atomic dataset boundary:

1. load and validate destination metadata;
2. preserve domain, field, year, and entity selections that exist there;
3. clear only incompatible descendants;
4. commit the destination repository and URL state together;
5. discard stale or cancelled responses.

The current map remains visible during an unobtrusive load, and an error leaves the previous usable dataset active. This prevents blank-map transitions and cross-source metric mixing. Large API collections use bounded, paginated endpoints; map routes should request only the geography, institutions, and observations needed for the active view.

## Temporal and geographic frontend rules

The timeline is a visually continuous range control over discrete observations. It supports pointer, touch, and keyboard input, displays the selected year above the track, and labels only sparse major ticks. Selecting a year with no observation yields missing data; the UI does not interpolate a scientific value.

Geographic rendering remains separate from research attribution. Polygon rings that cross ±180° are unwrapped and split into local renderable components before country-mode fitting. This general processing preserves multipolygons, islands, and exclaves, prevents artificial world-spanning edges for Russia near the Bering Strait, and leaves Kaliningrad disconnected. It uses the same `GeographicView` membership model that supports the existing China/Taiwan canvas; it does not change scientific ownership or affiliation rules.

Institution cores and both decorative pulse rings inherit the active metric color. Pulse timing is constant and carries no scientific meaning.

## Deployment boundary

`docker-compose.yml` provides PostgreSQL, migration, FastAPI, and worker services for reproducible local or hosted operation. The public `Physics-Atlas-Web` build enables live mode with `VITE_ATLAS_API_URL`; when it is unset or unavailable, explicitly retained static fallback paths remain usable.

Deployment-ready means the code, migrations, container configuration, fixtures, and health/status interfaces are present. Truly live means the separately operated PostgreSQL database, API, and scheduled worker are reachable and current. Production claims must be reverified for each release.

The worker bootstraps only non-observational reference data when the database is empty: the Physics domain, broader field taxonomy, ISO country records, geographic views, and metric definitions. It does not copy synthetic institutions, people, papers, or metric observations into a live database. Deterministic fixture runs remain visibly synthetic throughout provenance and dataset status.

The production recalculator remains `NoFormulaMetricRecalculator`. The five v1
algorithms are testable scientific framework code, but no live observation is
readable unless one exact-five `MetricSystemRelease` is explicitly active and
records a passed Joint Activation Gate. The current release manifest is
`experimental-withheld`; partial activation is not supported.
