# Atlas Physicus

Atlas Physicus is open scientific infrastructure for exploring the geographic,
temporal, and institutional structure of physics research ecosystems through a
map-first interface.

Part of Tech Echo Physica, a Tech Echo Collective project family for exploring physics through research mapping, knowledge structures, and interactive physical systems.

Atlas Physicus focuses on research mapping, alongside Illuminatio Physica for
knowledge structures and Theatrum Physicum for interactive physical systems.
The source repository is `atlas-physicus`. Historical names and release records
remain intact; deployed compatibility identifiers are documented in the
[deployment guide](docs/production-deployment.md#naming-and-deployment-compatibility).

It is not a ranking, recommendation, or prediction system, and it is not a
replacement for scholarly databases such as arXiv or INSPIRE.

[Open the public Atlas](https://atlas.techecho.org/)
· [View the source repository](https://github.com/Tech-Echo-Collective/atlas-physicus)

## What it does

Atlas Physicus supports a continuous exploration path:

```text
Physics → research field → time → world → country → institution
→ research group → researcher / papers
```

The system connects geographic views to canonical research entities,
paper-time affiliations, source evidence, and versioned scientific methods.

## Current live status

The public deployment uses the released `v3.0.5-alpha` architecture and a
bounded `hep-th-v1` provider scope through the production FastAPI/PostgreSQL
service. INSPIRE and arXiv supply literature evidence; ROR, ORCID, and Crossref
are used only through constrained identifier-led workflows.

The repository contains the deterministic Metric System v1 framework, explicit
evidence certification and a separate 0–100 Atlas Scale. Scientific validation
and the compact five-metric dataset launch remain incomplete. The
five live metric layers remain jointly withheld, so the
public map does not substitute zero or synthetic values for missing live
observations. Full Physics expansion and v3.1 have not started.

### Minimum remaining launch work

On September 8, 2026, the owner authorized separate validation of **observed
evidence coverage** and **unresolved attribution uncertainty** (PA-059).
The opt-in `observed-attribution-coverage-v1` adapter now measures completeness
conditional on actual conserved entity×field mass. Unknown attribution remains
in the complete source projections and exported possible-contribution bounds;
it is neither reassigned nor silently zeroed. These bounds are not statistical
confidence intervals or metric-score intervals and cannot be summed across
entities. Source-wide coverage still uses the full paper mass and the unchanged
90%/95% evidence gates. Old proof versions remain unchanged; normalization and
cross-field aggregation reject mixed coverage policies. This is an
admission-contract change, not a metric formula change or evidence that the
five-layer launch has passed.

Focused validation: 130 backend tests, 33 frontend compatibility tests, lint,
type checking and the production build pass. No new scientific data was acquired
or activated; all 36,456,719 bytes of isolated local test/build material were removed.

The latest bounded evidence still leaves these completion requirements:

- Resolve or explicitly withhold the seven identity-conflicted components among
  2,306 inspected 2018 nuclear-physics records without dropping their evidence.
- Improve and remeasure canonical institution evidence. The 250-paper sample
  reaches **67.354%**, below the unchanged **95%** threshold; this is not a
  whole-year or production-wide estimate.
- Establish six certified historical years for the candidate 2018–2023 window,
  mature comparable citation cohorts, and the required eligible normalization
  peers. Impact retains its 24-month maturity, 50-paper reference-cohort minimum
  and 90% citation coverage; Activity, Impact and Momentum retain their respective
  30-peer requirements.
- Generate real, co-located observations for all five dimensions, verify the
  preserved raw metrics and versioned 0–100 values, then publish the compact
  dataset and regression-test the timeline, composite and existing Atlas UX.

Use existing certification, calculators and frontend interfaces, with only
targeted evidence acquisition and necessary adapter fixes. Mandatory human review,
Full Physics completeness and legacy evidence-storage cleanup are **not** launch
prerequisites. Unsupported fields, entities and periods remain missing; no partial
metric activation is allowed. Current measurements and exact limitations are in
the [minimum launch integration report](docs/validation/minimum-launch-integration-2026-09-06.md);
implementation and deployment status belong in [project state](docs/PROJECT_STATE.md).

## Core principles

- Describe research ecosystems without ranking their scientific worth.
- Keep missing, unresolved, immature, and measured-zero evidence distinct.
- Preserve source, identity, mapping, method, and dataset provenance.
- Keep synthetic, pilot, fixture-live, and provider-backed live data isolated.
- Use the map as an exploration interface, not a prestige dashboard.
- Publish no metric layer before its scientific and production gates pass.

## Scientific attribution

Scientific attribution follows six durable rules:

1. Paper-time affiliations are the primary attribution evidence.
2. Current profiles never retroactively overwrite historical affiliations.
3. Persistent researcher identifiers support identity resolution and
   cross-checking; they do not determine contribution weight.
4. Institution names resolve to canonical entities while useful subunit labels
   are retained.
5. Ambiguous or unresolved affiliations remain unresolved rather than guessed.
6. Missing evidence never silently becomes zero.

Fractional Attribution v1 gives each paper a total mass of one, divides it
equally among authors, then equally among each author's valid paper-time
affiliations when no reviewed numeric contribution rule exists. Unresolved mass
is withheld rather than reassigned. Author order and corresponding-author
status do not change the weight. See the
[Scientific Attribution Policy](docs/scientific-attribution.md).

## Metric philosophy

Metric System v1 contains exactly five descriptive dimensions:

- Research Activity;
- Research Impact;
- Collaboration / Connectivity;
- Research Diversity;
- Research Momentum / Sustainability.

Calculations are field-specific before any coverage-aware Physics-wide
aggregation, and each dimension uses an appropriate documented normalization.
The five dimensions activate only as one coherent system. They do not measure
scientific value, quality, prestige, or future potential.

Users may define an explicitly confirmed five-weight exploratory composite whose
weights total 100%. It is not an official default or an “overall scientific
score.” Detailed formulas and limits belong in the
[Metric System v1 specification](docs/metrics-spec-v1.md) and
[validation protocol](docs/metric-validation.md).

## Architecture

The currently operated API-backed path is:

```text
INSPIRE / arXiv / reviewed identifier lookups
  → immutable source evidence and update lineage
  → normalization and conservative entity resolution
  → paper-time attribution and canonical field mapping
  → PostgreSQL canonical graph and compact provenance
  → explicit scientific evidence certification
  → exact eligible populations → certified raw metrics
  → metric-specific normalization → Atlas Scale
  → evidence-certified Joint Activation Gate
  → FastAPI → APIRepository → map-first React application
```

The frontend uses React, TypeScript, Vite, MapLibre GL JS, and Zod. The backend
uses Python, FastAPI, SQLAlchemy, Alembic, and PostgreSQL.

Full Physics loading additionally requires the independent Storage Budget
Gate. Normal public map/API reads continue on the bounded production dataset.

The first compact dataset launch reuses this scientific processing and publishes
only certified, versioned Atlas observations and necessary entity/provenance
metadata to the existing frontend. Raw provider and intermediate build material
is ephemeral, not a new permanent scholarly mirror. That dataset is not yet the
ordinary public source; implementation support does not imply deployment.

## Data and provenance

The normal public path is the integrated live API. Checked-in synthetic
fixtures and the bounded historical INSPIRE pilot remain available only for
tests, reproducibility, and explicit fallback; they are never silently mixed
with provider-backed live data.

Raw provider categories remain separate from the versioned Atlas field
ontology. Required source evidence, mappings, identity decisions, attribution
shares, normalization parameters, and dataset lineage are retained—either as
queryable canonical state or content-addressed warm/cold artifacts—so derived
results can be reconstructed. Provider data remains subject to its own terms
and licensing.

## Public access

- Atlas: <https://atlas.techecho.org/>
- Production API: <https://physics-atlas-api-production.up.railway.app/api>
- Source: <https://github.com/Tech-Echo-Collective/atlas-physicus>

The dedicated Atlas hostname replaces the inherited
`https://techecho.org/Physics-Atlas-Web/` Pages path. During DNS and Pages
propagation, that legacy path and the underlying
`https://tech-echo-collective.github.io/Physics-Atlas-Web/` origin may remain
reachable. The backend accepts all three browser origins for this bounded
transition; remove the legacy origins only after the new hostname and redirects
have been verified in production.

## Documentation

- [Project state](docs/PROJECT_STATE.md), [durable decisions](docs/DECISIONS.md),
  [roadmap](docs/roadmap.md), [history summary](docs/HISTORY_SUMMARY.md), and
  [recent worklog](docs/WORKLOG.md)
- [Architecture](docs/architecture.md) and
  [live-data architecture](docs/live-data-architecture.md)
- [Scientific Attribution Policy](docs/scientific-attribution.md)
- [Physics Field Ontology v1](docs/field-ontology.md)
- [Metric System v1 specification](docs/metrics-spec-v1.md)
- [Metric System v1 validation](docs/metric-validation.md)
- [Scientific evidence certification](docs/evidence-certification.md) and
  [hot/warm/cold storage architecture](docs/storage-architecture.md)
- [Entity resolution](docs/entity-resolution.md),
  [data sources](docs/data-sources.md), and
  [knowledge graph](docs/knowledge-graph.md)
- [Production deployment](docs/production-deployment.md)

## Contributing

Issues and focused pull requests are welcome. Changes should preserve the
no-ranking/no-prediction boundary, explicit missing-data semantics, provenance,
dataset isolation, deterministic tests, and the current bounded acquisition
scope. Read the project state and durable decisions before proposing
architecture or methodology changes.

## License and citation

Atlas Physicus is released under the [Apache License 2.0](LICENSE). Copyright
(c) 2026 Tech Echo Collective; attribution information is preserved in
[NOTICE](NOTICE).

If Atlas Physicus supports research or teaching, cite it using
[CITATION.cff](CITATION.cff).
