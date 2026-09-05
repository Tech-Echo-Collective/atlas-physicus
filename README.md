# Physics Atlas

Physics Atlas is open scientific infrastructure for exploring the geographic,
temporal, and institutional structure of physics research ecosystems through a
map-first interface.

It is not a ranking, recommendation, or prediction system, and it is not a
replacement for scholarly databases such as arXiv or INSPIRE.

[Open the public Atlas](https://atlas.techecho.org/)
· [View the source repository](https://github.com/Tech-Echo-Collective/Physics-Atlas)

## What it does

Physics Atlas supports a continuous exploration path:

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
evidence certification, a separate 0–100 Atlas Scale, and a measured storage
readiness gate. Representative scientific validation remains incomplete. The
five live metric layers remain jointly withheld, so the
public map does not substitute zero or synthetic values for missing live
observations. Full Physics expansion and v3.1 have not started.

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

```text
INSPIRE / arXiv / reviewed identifier lookups
  → immutable source evidence and update lineage
  → normalization and conservative entity resolution
  → paper-time attribution and canonical field mapping
  → PostgreSQL canonical graph and compact provenance
  → explicit scientific evidence certification
  → exact eligible populations → certified raw metrics
  → metric-specific normalization → Atlas Scale
  → reviewed Joint Activation Gate
  → FastAPI → APIRepository → map-first React application
```

The frontend uses React, TypeScript, Vite, MapLibre GL JS, and Zod. The backend
uses Python, FastAPI, SQLAlchemy, Alembic, and PostgreSQL.

Full Physics loading additionally requires the independent Storage Budget
Gate. Normal public map/API reads continue on the bounded production dataset.

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
- Source: <https://github.com/Tech-Echo-Collective/Physics-Atlas>

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

Physics Atlas is released under the [Apache License 2.0](LICENSE). Copyright
(c) 2026 Tech Echo Collective; attribution information is preserved in
[NOTICE](NOTICE).

If Physics Atlas supports research or teaching, cite it using
[CITATION.cff](CITATION.cff).
