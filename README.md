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

## Archived — 12 September 2026

Active development has ended by the owner's decision (PA-066). The interactive
map and source remain available as a project archive. Data is frozen at the
**8 September 2026** capture; no further acquisition, expansion or scientific
certification is planned. [Archive status and preserved assets](docs/ARCHIVE.md).

## What it does

Atlas Physicus supports a continuous exploration path:

```text
Physics → research field → time → world → country → institution
→ research group → researcher / papers
```

The system connects geographic views to canonical research entities,
paper-time affiliations, source evidence, and versioned scientific methods.

## Preserved public snapshot

The final public explorer uses static files hosted on GitHub Pages, with 51
native arXiv physics categories and years 2018–2026. The bounded INSPIRE capture
contains 61,846 source records; 46,524 dated papers have supported attribution to
4,569 institutions in 135 countries/regions. Missing attribution remains explicit.

These are observations from up to 250 most-recent records per category/year,
not a representative sample or complete census. The data does not support
extrapolating the overall distribution of physics research. 2026 is partial;
older cohorts use citations observed at the September 8 capture. Five normalized
observed dimensions are preserved without claiming strict scientific certification.

The public map requires no Railway API or database. Historical live-platform
and unfinished certification work is retained in the source and
[September 8 project state](docs/archive/project-state-2026-09-08.md).

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

The preserved public path is:

```text
September 8 INSPIRE capture → supported attribution and observed metrics
  → immutable map/catalog/relationship files on GitHub Pages
  → static repository and browser worker → React / MapLibre explorer
```

The frontend uses React, TypeScript, Vite, MapLibre GL JS, and Zod. The historical
Python/FastAPI/SQLAlchemy/Alembic/PostgreSQL backend and scientific certification
framework remain in source for study and reproducibility. They are not required
to serve the public archive and are no longer an active deployment programme.

## Data and provenance

The public path is the frozen attributed dataset. Checked-in synthetic
fixtures and the bounded historical INSPIRE pilot remain available for tests
and reproducibility; they are never silently mixed with the public snapshot.

Raw provider categories remain separate from the versioned Atlas field
ontology. Required source evidence, mappings, identity decisions, attribution
shares, normalization parameters, and dataset lineage are retained—either as
queryable canonical state or content-addressed warm/cold artifacts—so derived
results can be reconstructed. Provider data remains subject to its own terms
and licensing.

The separate unfinished certification framework and its conditional observed
admission policies are documented in the
[historical automatic certification methodology](docs/automatic-certification.md).
They do not certify the frozen public dataset.

## Public access

- [Interactive archive](https://atlas.techecho.org/)
- [Source](https://github.com/Tech-Echo-Collective/atlas-physicus)
- [Archive status and retirement record](docs/ARCHIVE.md)

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

The project is archived; there is no active development or review commitment.
The source and license remain available for study and reuse.

Reuse should preserve the no-ranking/no-prediction boundary, explicit missing
data, provenance, dataset isolation and deterministic scientific methods.

## License and citation

Atlas Physicus is released under the [Apache License 2.0](LICENSE). Copyright
(c) 2026 Tech Echo Collective; attribution information is preserved in
[NOTICE](NOTICE).

If Atlas Physicus supports research or teaching, cite it using
[CITATION.cff](CITATION.cff).
