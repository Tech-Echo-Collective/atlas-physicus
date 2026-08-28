# Physics Atlas roadmap

The roadmap records engineering direction, not promised dates. Each milestone must preserve the map-first exploration path and the rule that Physics Atlas is not a ranking, recommendation, or prediction system.

## Completed alpha foundations

| Release | Foundation |
| --- | --- |
| v1.0-alpha | React/TypeScript/Vite atlas, MapLibre world view, synthetic activity layer, country exploration, domain model, and documentation |
| v2.1-alpha | Temporal geographic exploration, country-only canvas, institution nodes, and geographic representation policy |
| v2.2-alpha | Research-entity exploration, domain/field heatmaps, global reset, and generalized China/Taiwan geographic-view membership |
| v2.3-alpha | Map information hierarchy, profiles and relationships, institution heat/pulse interaction, and public static deployment foundation |
| v3.0.1-alpha | Versioned Metric Engine vocabulary, registry, calculation boundary, and transparent composite weighting |
| v3.0.2-alpha | Bounded INSPIRE-HEP pilot, reproducible real-metadata snapshot, source separation, and uncertainty reporting |
| v3.0.3-alpha | Canonical identity, entity-aware search, temporal knowledge graph, profiles, resources, and append-only update lineage |

## v3.0.4-alpha — continuously updateable platform foundation

This release adds:

- PostgreSQL models and Alembic migrations;
- a typed, paginated FastAPI read service and frontend `APIRepository`;
- scheduled official-API connectors for INSPIRE, arXiv, and ROR, plus targeted ORCID and Crossref record enrichers;
- cursor-based, auditable, idempotent incremental updates with deterministic fixtures;
- persistent ambiguity review, source/update status, and affected metric-partition planning;
- external-resource enrichment and safe bounded health monitoring;
- broader Physics field-mapping rules with preserved uncertainty;
- Russia/multipolygon/antimeridian rendering fixes;
- a continuous accessible timeline, source-switch race protection, and pulse-color inheritance;
- reproducible PostgreSQL/API/worker development through Docker Compose;
- a direct Physics Atlas entry on the Tech Echo Collective website.

The release is deployment-ready, not automatically publicly live. The GitHub Pages Atlas retains synthetic and historical pilot fallbacks. Provider-backed mode becomes truly live only when an HTTPS backend, PostgreSQL database, worker, credentials, policy configuration, backups, and monitoring are operated.

## Current milestone — v3.0.4 Production Activation

Status: **in progress**. This is an operational follow-through on v3.0.4-alpha, not v3.0.5 and not a new product-feature phase.

The goal is to operate the existing path with a bounded `hep-th` corpus:

```text
INSPIRE / arXiv → normalization → entity resolution → PostgreSQL
    → FastAPI → APIRepository → public Atlas
```

The production activation is not complete. No hosting target, production credentials, public API URL, managed database, or provider-backed worker is currently recorded. The public GitHub Pages application remains static/pilot.

Scheduled acquisition is now bounded deliberately. The versioned `hep-th-v1`
policy requests INSPIRE Theory-HEP and arXiv `cat:hep-th`; ROR is target-only
and disabled without configured known IDs. Cursor, snapshot, and dataset scope
markers prevent legacy broad state from being reused silently. ORCID and
Crossref remain known-ID-only enrichers.

An isolated temporary-database smoke run verified real bounded INSPIRE/arXiv
records, checkpoint continuation in fresh worker processes, targeted Crossref,
resource monitoring, migrations, FastAPI health/reads, and API restart. This
does not satisfy the production gate: it used SQLite rather than an operated
PostgreSQL host, and no public HTTPS API or public `APIRepository` connection
exists.

Activation also requires enough reviewed canonical affiliation and metric data to support a useful geographic view. Until then, missing live map observations remain neutral rather than becoming zero or an unvalidated score.

Completion gates are:

1. authorized HTTPS hosting, production PostgreSQL, secrets, CORS, backups, rate protection, logs, and operational monitoring;
2. bounded provider-backed ingestion with explicit provenance and no fixture/synthetic/pilot mixing;
3. checkpoint, restart, timeout, rate-limit, duplicate, partial-update, and malformed-record recovery tests in the operated environment;
4. healthy public API and current update status;
5. verified public frontend use of `APIRepository`, including deep links and map/navigation regressions;
6. removal of the development dataset selector from the normal public experience only after live stability is demonstrated.

## Next validation gates

Before broad live ingestion, the project should validate:

1. provider terms, attribution, and retention policy under the intended hosting jurisdiction;
2. representative multi-field sampling and provider-category mapping against expert review;
3. researcher/institution identity precision, ambiguity thresholds, and a reversible review workflow;
4. historical affiliation, retraction, tombstone, and source-conflict policies;
5. scientifically reviewed formulas, normalization, uncertainty, and version migration for any live metrics;
6. scoped API performance on realistic country/profile workloads;
7. backup/restore, deployment security, rate protection, uptime, and operator runbooks;
8. accessible public methodology and provenance displays.

## Deferred by design

The roadmap does not currently commit to a graph database, Kubernetes, authentication, full-text paper archive, recommendation engine, prediction model, automatic researcher ranking, or universal live-data coverage. Those additions require a demonstrated scientific or operational need.

The next minimum action is to select an authorized hosting target and operate
the reviewed bounded stack with PostgreSQL, HTTPS, backups, and monitoring.
Only after hosted API and frontend verification should the Pages build switch
to `APIRepository`. Large backfills should wait for that operating evidence.
