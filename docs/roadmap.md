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

The next minimum action after v3.0.4-alpha is an operated, bounded staging deployment with fixture and limited provider-backed updates, followed by measured resolver and API review. Large backfills should wait for that evidence.
