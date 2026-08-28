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

The release tag remains the architectural baseline. The follow-up Production Activation work now operates its HTTPS Railway API, managed PostgreSQL path, bounded worker, and public GitHub Pages `APIRepository` integration. Synthetic and historical pilot sources remain isolated internal reproducibility and fallback resources.

## Current milestone — v3.0.4 Production Activation

Status: **in progress**. This is an operational follow-through on v3.0.4-alpha, not v3.0.5 and not a new product-feature phase.

The goal is to operate the existing path with a bounded `hep-th` corpus:

```text
INSPIRE / arXiv → normalization → entity resolution → PostgreSQL
    → FastAPI → APIRepository → public Atlas
```

The transport and public frontend portions of Production Activation are complete. The Railway API is healthy at <https://physics-atlas-api-production.up.railway.app/api>, the bounded provider update reports healthy INSPIRE/arXiv status, and the GitHub Pages application uses `APIRepository` by default. The normal public selector no longer presents synthetic or pilot datasets.

Scheduled acquisition is now bounded deliberately. The versioned `hep-th-v1`
policy requests INSPIRE Theory-HEP and arXiv `cat:hep-th`; ROR is target-only
and disabled without configured known IDs. Cursor, snapshot, and dataset scope
markers prevent legacy broad state from being reused silently. ORCID and
Crossref remain known-ID-only enrichers.

The earlier isolated smoke evidence is now supplemented by an operated Railway deployment, exact-origin CORS, current update status, successful live API reads, a production Pages build, and root/deep-route fallback verification. Backup/restore, long-running monitoring, rate protection, and alerting still require durable operator evidence.

Activation also requires enough reviewed canonical affiliation and metric data to support a useful geographic view. Until then, missing live map observations remain neutral rather than becoming zero or an unvalidated score.

Remaining completion gates are:

1. durable backup/restore, restart, rate-protection, logging, monitoring, and alerting evidence in the operated environment;
2. longer observation of bounded provider ingestion and checkpoint recovery under production conditions;
3. reviewed canonical affiliation coverage sufficient for useful country and institution exploration;
4. scientifically reviewed formulas, normalization, uncertainty, and versioning before any live metric observations are published.

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

The next minimum action is to monitor the bounded operated path and record a tested backup/restore and restart procedure. Large backfills, new public metrics, and v3.0.5 work should wait for that operating evidence and scientific review.
