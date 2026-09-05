# Physics Atlas history summary

This is the compact chronological entry point for project history. It records
milestone provenance and major architectural transitions without repeating the
current facts in [`PROJECT_STATE.md`](PROJECT_STATE.md), durable policy in
[`DECISIONS.md`](DECISIONS.md), or task evidence in validation reports.

## Alpha foundations

| Milestone | Provenance | Lasting result |
| --- | --- | --- |
| `v1.0-alpha` | tag at `5ca9fd6`, 2026-08-24 | React/TypeScript/Vite and MapLibre prototype; synthetic world activity, field selection, country exploration, domain models, and initial documentation. |
| `v2.1-alpha` | development milestone; no retained release tag | Temporal geography, country-only canvas, institution nodes, and the geographic-representation policy. |
| `v2.2-alpha` | corrected tag at `3fc193a`, 2026-08-24 | Research-entity exploration, domain/field heatmaps, global reset, and generalized geographic-view membership including the China/Taiwan canvas correction. |
| `v2.3-alpha` | tag at `bf6a51e`, 2026-08-24 | Map information hierarchy, institution interaction, profiles/relationships, and the first public static-deployment foundation. |
| `v3.0.1-alpha` | development milestone; no retained release tag | Versioned Metric Engine vocabulary, registry/calculation boundary, and transparent exploratory weighting. |
| `v3.0.2-alpha` | development milestone; no retained release tag | Bounded reproducible INSPIRE-HEP pilot, source separation, and explicit uncertainty/missing-data treatment. |
| `v3.0.3-alpha` | tag at `c3ce6c8`, 2026-08-24 | Canonical identity, temporal relational knowledge graph, entity-aware search, profiles/resources, and append-only update lineage. |

## Live platform and scientific validation

| Milestone | Provenance | Lasting result |
| --- | --- | --- |
| `v3.0.4-alpha` | tag at corrected commit `09f5d85`, 2026-08-28 | PostgreSQL/FastAPI platform, bounded connectors and update engine, API-backed frontend repository, migrations, fixtures, and deployable container stack. |
| Production activation | source `45da545`; Web `13f1d5b`, 2026-08-28 | Verified Railway PostgreSQL/API/worker and normal public `APIRepository` path; synthetic and pilot modes retained only as isolated internal sources. |
| `v3.0.5-alpha` | implementation `ba44c7e`; tag at `b1974d2`, 2026-08-29 | UI stabilization, candidate scientific contracts, reconstructable metrics, stricter lineage/read gates, identity-review framework, and explicit scientific withholding. |
| Metric System v1 foundation | `fe752f0`, 2026-08-30 | Fractional paper-time attribution, Physics ontology/provider mappings, exact five raw metrics and dimension-specific normalization, field-balanced aggregation, and fail-closed Joint Activation Gate. No live metric was activated. |
| Bounded activation diagnostic and acquisition | `0b6b08a`, `d3b5cc8`, 2026-08-30 | Corrected readiness measurement, froze cross-provider affiliation precedence and field-mass conservation, and acquired a resumable staging-only 2020–2025 `hep-th-v1` corpus. |
| Canonical replay and authority materialization | `b20e3d9`; CI record `f88385c`, 2026-08-31 | Deterministic file-only paper/author/affiliation/field/citation replay plus target-only ROR authority projection. The exact-five gate remained withheld and production history was untouched. |
| Bounded dual-field validation | `5e3ba1f`; CI run `33884017132`, 2026-09-04 | Preserved the `hep-th-v1` baseline and completed a reproducible 2020–2025 Condensed Matter replay. Both specialty tracks and the comparison-only exact-five gate remain withheld; Full Physics loading stays unauthorized. |
| Scientific certification and capacity foundation | `be5e304`, CI 33932839622 green, 2026-09-05 | Explicit certification, exact reviewed populations, separate Atlas Scale, small official paired capture, conservative replay, PostgreSQL audit, and independent Storage Budget Gate. Public metrics and Full Physics loading remain withheld. |

The detailed v3.0.4 activation and v3.0.5 release history is archived in
[`archive/worklog-through-v3.0.5-release.md`](archive/worklog-through-v3.0.5-release.md).
The Metric System v1 implementation, diagnostic, acquisition, and canonical
replay history is compressed in
[`archive/worklog-metric-system-v1-through-canonical-replay.md`](archive/worklog-metric-system-v1-through-canonical-replay.md).
Scientific replay evidence is retained in
[`validation/metric-system-v1-hep-th-2020-2025-dry-run.md`](validation/metric-system-v1-hep-th-2020-2025-dry-run.md)
and
[`validation/metric-system-v1-hep-th-2020-2025-canonical-replay.md`](validation/metric-system-v1-hep-th-2020-2025-canonical-replay.md).

## Durable boundaries established over time

- Physics Atlas is descriptive, map-first scientific infrastructure—not a
  ranking, prediction, or recommendation system.
- Geographic display is separate from affiliation-based scientific
  attribution.
- Missing, unresolved, immature, and measured-zero evidence remain distinct;
  every dataset and derived result preserves provenance.
- PostgreSQL is the current canonical relational graph store; a separate graph
  database remains deferred until a demonstrated need exists.
- Acquisition is versioned and bounded. Browser clients never contact
  scientific providers directly, and dataset modes are never silently mixed.
- Metric System v1 consists of Activity, Impact, Connectivity, Diversity, and
  Momentum. It activates only through one reviewed exact-five manifest.
- Certification binds evidence and exact populations without replacing
  scientific review. Full Physics loading also requires measured storage and
  reviewed restore evidence; content-addressed warm/cold artifacts preserve
  raw lineage without making PostgreSQL the permanent payload archive.

The authoritative wording and consequences of these boundaries are in
[`DECISIONS.md`](DECISIONS.md); this summary is not a substitute for that log.

## Open historical gates

- Complete, reviewed, representative evidence remains required for
  paper-time affiliations, canonical institutions, fields, citation cohorts,
  normalization, and historical windows before public metrics can activate.
- A theory-heavy `hep-th-v1` corpus cannot by itself validate Physics-wide
  Diversity; broader-field validation remains gated and must not be inferred
  from a subfield sanity check.
- Backup/restore, restart rehearsal, rate protection, monitoring, alerting, and
  long-running production observation remain operator evidence requirements.
- Full Physics acquisition remains gated by both the exact-five scientific
  gate and independent Storage Budget Gate. v3.1 remains deferred.

## Normal context-reading path

Future work should normally read, in order:

1. repository `AGENTS.md`;
2. [`PROJECT_STATE.md`](PROJECT_STATE.md);
3. [`DECISIONS.md`](DECISIONS.md);
4. [`roadmap.md`](roadmap.md);
5. this history summary;
6. the recent [`WORKLOG.md`](WORKLOG.md);
7. only the methodology or validation documents relevant to the task.
