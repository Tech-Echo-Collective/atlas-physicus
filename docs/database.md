# Database and migrations

## Choice and scope

PostgreSQL is the canonical v3.0.5-alpha store. The present queries are relational, temporal, provenance-heavy, and filter by entity, field, country, institution, year, and source. A graph database would add operational complexity without a demonstrated query need, so graph relationships use constrained tables and joins.

SQLAlchemy models define the application persistence layer; Alembic owns schema evolution. JSON/JSONB retains provider payloads, provenance, identifier lists, and other source-varying metadata, while stable identifiers, important relationships, temporal bounds, and query dimensions remain typed columns and foreign keys.

## Schema groups

| Group | Tables/models |
| --- | --- |
| Atlas vocabulary | `ScienceDomain`, `ResearchField`, `Country`, `GeographicView`, `DatasetState` |
| Canonical entities | `Institution`, `ResearchGroup`, `Researcher`, `Paper`, `AuthorityIdentifier`, `EntitySearchTerm` |
| Graph relationships | `PaperField`, `Authorship`, `Affiliation`, `Citation` |
| Metrics and history | `MetricDefinition`, `MetricObservation`, `HistoricalEvent` |
| Resource enrichment | `ExternalResource`, `ResourceCheck` |
| Source evidence | `SourceSnapshot`, `RawEntityRecord` |
| Identity audit | `IdentityResolution`, `IdentityReview` |
| Update operations | `SourceCursor`, `DatasetUpdate`, `UpdateRun` |

Canonical IDs are stable Atlas identifiers; source IDs belong in authority/evidence records. `Affiliation` carries start/end dates and optional research-group membership. It is never replaced by a single `Researcher.institution_id`. URLs remain `ExternalResource` rows rather than entity properties.

`EntitySearchTerm` is a derived canonical index for preferred names, aliases, historical names, abbreviations/token variants, and authority identifiers. It is refreshed when supported canonical evidence changes. Unresolved raw records are never indexed as canonical results.

Metric observations retain entity scope, optional domain/field, period, definition/version fields, value, source, and calculation provenance. The schema preserves a missing observation as no row; zero is a valid measured value only when explicitly written.

## Query and scale rules

The initial migration creates indexes and uniqueness constraints for authority lookups, canonical names, entity/country/field filters, temporal relationship traversal, paper identifiers, source records/checksums, update time/status, resources, and metric partitions. Collection endpoints add bounded pagination; the API does not expose database implementation details.

Global map queries should return country observations only. Country queries should scope institutions by geographic-view membership and active metric/year. Researchers, papers, resources, and relationships are lazy profile queries rather than a global bootstrap payload. Incremental updates plan only affected metric partitions instead of recalculating the full database per paper.

## Migrations

The first live-platform revision is under `backend/alembic/versions`. Apply migrations before starting the API or worker:

```bash
alembic -c backend/alembic.ini upgrade head
alembic -c backend/alembic.ini current
```

Compose runs migration as a one-shot dependency. CI applies the same migration against PostgreSQL before API startup. SQLite may be useful for fast deterministic unit checks, but PostgreSQL is the supported deployment target and must validate every release migration.

Migration policy:

- never use application startup to silently create or rewrite production tables;
- take a verified backup before a destructive or long-running migration;
- prefer additive, backward-compatible changes and explicit data migrations;
- test upgrade and downgrade behavior where a downgrade is safe;
- never edit an already released migration to change its meaning;
- do not drop raw snapshots, prior metric observations, or identity evidence as part of routine updates.

The migration does not import the historical pilot automatically. `physics-atlas-seed` can load a checked-in validated dataset for development. The worker's empty-database bootstrap is narrower: it loads only Physics/field taxonomy, ISO countries, geographic views, and metric definitions before creating a new `live-api` dataset through ingestion. It never copies demonstration entities or observations. This separation prevents a live worker from writing into synthetic or preserved pilot data.

## Provenance and retention

`SourceSnapshot` and `RawEntityRecord` preserve source evidence. `IdentityResolution`, `DatasetUpdate`, and `UpdateRun` preserve the decisions and operations derived from it. Resource checks and metric observations are appendable histories. A correction creates a new version or decision; it does not silently erase the earlier chain.

Production retention must account for provider terms, personal-data minimization, storage cost, audit requirements, and backup recovery. Raw payload availability does not imply unrestricted redistribution. Secrets never belong in database seed files, migrations, JSON provenance, or committed compose configuration.

## Current limitations

- The schema is an alpha foundation and has not been benchmarked on a complete all-physics corpus.
- PostgreSQL full-text, geospatial extensions, table partitioning, materialized views, and external search services are not yet required or introduced.
- The derived search-term index is prefix-oriented and has not been benchmarked against a full all-physics corpus.
- There is no automated backup/restore service, replica, or hosted database in this repository.
- Tombstone, retraction, legal erasure, and long-term raw-payload retention policies need operational review before large-scale production ingestion.
