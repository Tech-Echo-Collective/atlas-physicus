# v3.0.4-alpha implementation plan

## Objective

v3.0.4-alpha turns the preserved static/pilot prototype into a continuously updateable platform foundation while keeping the public Atlas map-first and keeping the synthetic and INSPIRE pilot datasets reproducible.

```text
official source APIs
    → resumable source connectors
    → immutable snapshots/raw records
    → normalization and field mapping
    → identity resolution/review
    → PostgreSQL canonical graph
    → affected metric partitions
    → FastAPI and APIRepository
    → World → Country → Institution → Researcher exploration
```

Deployment-ready is not the same as publicly live. A truly live mode additionally requires an operated database, HTTPS API, scheduled worker, source-policy configuration, backups, and monitoring.

## Included scope

v3.0.4-alpha includes:

- PostgreSQL models for canonical entities, normalized relationships, metrics, raw evidence, identity review, resources/checks, update cursors/runs, and dataset state;
- Alembic migration and non-observational reference bootstrap;
- typed, bounded FastAPI queries, profiles, search, provenance, health, and update status;
- frontend `APIRepository` with validation, caching/cancellation, lazy profile/map loading, and source-transition reconciliation;
- scheduled closed-window incremental connectors for INSPIRE, arXiv, and ROR;
- targeted ORCID and Crossref record enrichment for already-known identifiers;
- deterministic provider fixtures whose provenance remains explicitly synthetic;
- idempotent/resumable update orchestration, persistent ambiguity review, search-index refresh, and affected metric-partition planning;
- resource enrichment and bounded, allowlisted link health monitoring;
- broader Physics field taxonomy and uncertainty-bearing provider mapping;
- Docker Compose for PostgreSQL, migrations, FastAPI, and the worker;
- Russia/multipolygon/antimeridian geometry repair, continuous accessible timeline, source-switch race handling, and pulse-color inheritance;
- explicit separation among synthetic demo, historical pilot, fixture API, and provider-backed live modes;
- a minimal Physics Atlas entry in the Tech Echo Collective website without duplicating the Atlas code.

## Deliberate exclusions

v3.0.4-alpha does not include:

- final scientific metric formulas, validated normalization, or uncertainty propagation;
- a public hosted backend, production credentials, managed database, backup service, or uptime claim;
- complete all-physics ingestion or historical backfill;
- global scheduled ORCID or Crossref crawling;
- automatic resolution of name-only researchers or ambiguous institutions;
- a reviewer UI, merge/split workflow, authentication, or write API;
- complete affiliations, groups, citations, resources, retractions, or tombstones;
- a graph database, Kubernetes, recommendation, ranking, or prediction system.

## Acceptance criteria

The frontend must pass type checking, lint, tests, and production build while preserving:

- global country heatmap, country institution nodes, and lazy profile navigation;
- synthetic/pilot isolation and API fallback behavior;
- continuous timeline selection with missing-not-zero semantics;
- Russia/antimeridian, Kaliningrad, China/Taiwan, reset, country isolation, and pulse-color regressions.

The backend must pass static validation, unit/integration tests, migrations, API startup, deterministic fixture ingestion/update, and resource-monitor tests. PostgreSQL/Compose behavior must be validated in an environment where Docker is available.

Release requires a clean commit, preserved prior tags, successful validation, a new `v3.0.4-alpha` tag without force movement, and a working pinned-submodule GitHub Pages fallback.

## Operational rules

- INSPIRE and arXiv default to daily checks; ROR defaults to weekly checks.
- Incomplete page checkpoints resume immediately inside the same closed window.
- ORCID and Crossref accept targeted known-ID lookups only and have no global cadence.
- Source omission never silently deletes a canonical entity.
- Fixture data remains synthetic through snapshots, canonical provenance, and dataset metadata.
- Metric partition planning does not write an observation without an explicitly registered, reviewed calculator.
- Missing data remains missing and is never converted to zero.
- External URLs remain references; monitoring never crawls or treats page content as scientific truth.

## Known limitations and next minimum action

The identity model is conservative but not calibrated against a representative truth set. Source coverage, field mapping, affiliation history, citations, resources, and search/profile completeness remain partial. Link validation cannot replace production egress controls. The API/search/database have not been benchmarked on a full corpus, and the public Pages deployment does not itself host FastAPI.

After release, the smallest responsible next step is a bounded staging deployment: operate PostgreSQL/API/worker, run fixture then limited provider-backed updates, measure resolver precision and scoped API performance, test backup/restore, and review provider/data-retention policy before any large backfill.
