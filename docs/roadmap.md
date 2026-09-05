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
| v3.0.4-alpha | Continuously updateable PostgreSQL/FastAPI platform, bounded provider connectors, public API repository, and production activation |

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

## Current milestone — v3.0.5-alpha Stabilization & Scientific Validation

Status: **released baseline; scientific certification/capacity foundation
validated; scientific and storage activation remain withheld**.
This milestone stabilizes the live v3.0.4 system; it does not
expand beyond the bounded Physics scope or redesign the production
architecture.

The operated path remains bounded to `hep-th-v1`:

```text
INSPIRE / arXiv → normalization → entity resolution → PostgreSQL
    → FastAPI → APIRepository → public Atlas
```

The Railway API is healthy at
<https://physics-atlas-api-production.up.railway.app/api>, bounded INSPIRE/arXiv
updates are persisted, and the GitHub Pages application uses `APIRepository` by
default. The normal public selector does not present synthetic or pilot
datasets.

Scheduled acquisition is now bounded deliberately. The versioned `hep-th-v1`
policy requests INSPIRE Theory-HEP and arXiv `cat:hep-th`; ROR is target-only
and disabled without configured known IDs. Cursor, snapshot, and dataset scope
markers prevent legacy broad state from being reused silently. ORCID and
Crossref remain known-ID-only enrichers.

The earlier isolated smoke evidence is now supplemented by an operated Railway deployment, exact-origin CORS, current update status, successful live API reads, a production Pages build, and root/deep-route fallback verification. Backup/restore, long-running monitoring, rate protection, and alerting still require durable operator evidence.

v3.0.5 adds candidate scientific contracts, metric-specific normalization,
reconstructable output metadata, explicit activation gates, identity-validation
sampling/reporting, aggregate public data status, and viewport stabilization.
The evidence snapshot fails every live metric gate, so the map remains neutral
rather than becoming zero or an unvalidated score.

### Post-v3.0.5 Metric System v1 foundation

The current source phase completes the deterministic, versioned scientific
framework without changing the released tag or activating public metrics:

- paper-time affiliation materialization and exact
  `fractional-attribution-v1`, including explicitly withheld unresolved mass;
- `physics-field-ontology-v1` and a separate versioned INSPIRE/arXiv mapping
  layer that preserves raw provider evidence and does not infer unsupported
  membership;
- raw calculators and metric-specific normalization for exactly Activity,
  Impact, Connectivity, Diversity, and Momentum;
- field-first, field-balanced, coverage-aware Physics aggregation;
- versioned first-pass evidence thresholds, reconstructable provenance, and an
  exact-five Joint Activation Gate;
- exact-five user composite validation and linked reference-ecosystem checks
  that do not impose a preferred ordering.

This is an implementation milestone, not scientific activation. The live
Railway/PostgreSQL dataset remains bounded to `hep-th-v1`; a source migration,
historical materialization, citation reconstruction, wider ingestion, and
public recalculation are not implied. All five live layers remain jointly
withheld.

The bounded `hep-th-v1` 2020–2025 acquisition and staging replay are complete:
88,212
official provider occurrences across 12 exact provider/year partitions were
preserved as 47,726 paper components with content-addressed relationship,
field, citation, attribution, and ROR-authority evidence outside the database.
The replay validates deterministic lineage and conservation, not production
readiness. It leaves zero metric-certified years, zero comparable citation
cohorts, zero reviewed field ledgers, and only 34.969191% activation-eligible
institution rollup mass. It does not authorize a production historical write,
metric activation, or wider acquisition.

Current bounded validation also includes an isolated 2020–2025 Condensed
Matter trial. It is a complementary full-five-metric method test, not a
production load. Its completed replay preserved 160,294 provider records as
129,464 paper components, but paper-time affiliation coverage is only
25.407165%; reviewed field and common-cutoff citation coverage are both zero;
canonical-institution coverage is not measurable; and certified canonical
years and ready Momentum windows remain zero. All five metrics are withheld.
Both specialty trials remain field-conditioned; neither their individual
results nor an unreviewed comparison can satisfy the PA-040 broad-Physics
activation boundary.

### Scientific Evidence Certification and storage sizing

The current source implements an explicit certification boundary, exact
reviewed eligibility/normalization populations, complete-year/window proofs,
and a separate 0–100 Atlas Scale over the unchanged five raw metrics. A small
official January 2020 paired capture demonstrates nonzero record-level
certification without certifying a year or activating metrics. Existing
Condensed Matter artifacts are replayed conservatively; missing hep-th row
artifacts cannot be reconstructed from Git. The
[certification report](validation/scientific-evidence-certification-2026-09-05.md)
is the canonical evidence record.

A read-only production PostgreSQL audit and hot/warm/cold artifact abstraction
establish the storage boundary. Full Physics loading requires **both** the
Joint Metric Gate and Storage Budget Gate. The present sample and capacity
projections do not pass the latter; no object-store deployment, production
payload migration, or wider load is implied. The bounded September 5
[storage investigation](validation/storage-amplification-2026-09-05.md) validates
compact decision storage, not production compaction or a safe larger capacity.
Next is a one-batch additive artifact-reference/dual-read and isolated-restore
pilot before any representative final-schema staging load is considered.

Remaining scientific and operational gates are:

1. durable backup/restore, restart, rate-protection, logging, monitoring, and alerting evidence in the operated environment;
2. longer observation of bounded provider ingestion and checkpoint recovery under production conditions;
3. reviewed canonical paper-time affiliation and institution coverage sufficient for useful country and institution exploration;
4. representative validation of the implemented formulas, field mapping,
   normalization, uncertainty, and version lineage before any live metric
   observations are published;
5. a single reviewed activation manifest demonstrating that all five metric
   dimensions pass together;
6. a reviewed exact target population and representative final-schema storage
   measurement/restore evidence passing the independent Storage Budget Gate
   before Full Physics loading.

## Gates before broader Physics coverage or v3.1

Before broad live ingestion, the project should validate:

1. provider terms, attribution, and retention policy under the intended hosting jurisdiction;
2. representative multi-field sampling and provider-category mapping against expert review;
3. researcher/institution identity precision, ambiguity thresholds, and a reversible review workflow;
4. historical affiliation, retraction, tombstone, and source-conflict policies;
5. scientific review, robustness, sensitivity, uncertainty, bias, and version-
   migration evidence for the implemented five-metric system;
6. scoped API performance on realistic country/profile workloads;
7. backup/restore, deployment security, rate protection, uptime, and operator runbooks;
8. accessible public methodology and provenance displays.

## Deferred by design

The roadmap does not currently commit to a graph database, Kubernetes, authentication, full-text paper archive, recommendation engine, prediction model, automatic researcher ranking, or universal live-data coverage. Those additions require a demonstrated scientific or operational need.

The certification foundation is committed as `be5e304` with green CI run
33932839622; this does not constitute scientific activation. The current minimum
scientific action is reviewed canonical dates, identities, institution
targets/rollups, field mappings, common-cutoff populations, and complete
historical certification. The Joint and Storage gates remain withheld.
Production history, Full Physics loading, v3.1, and live metric activation
remain gated.
