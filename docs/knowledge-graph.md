# Scientific knowledge graph

## Purpose and status

Physics Atlas uses a canonical scientific knowledge graph to connect source evidence to institutions, researchers, papers, fields, affiliations, authorships, groups, places, metrics, and external resources. The graph exists to support transparent exploration; it is not a university or researcher ranking, recommendation engine, or claim that source coverage is complete.

v3.0.4-alpha adds a persistent PostgreSQL representation and FastAPI read layer alongside the preserved validated static and pilot graph. PostgreSQL is a relational graph store for the current query shapes. A separate graph database is not justified yet.

```text
official source record
    → immutable snapshot and raw record
    → normalization and field-mapping evidence
    → identifier-led identity resolution
    → canonical node or persistent review item
    → normalized graph relationships
    → profile/search/map read models
```

The repository supplies deployment-ready infrastructure, not a claim that the public GitHub Pages instance is connected to a hosted live graph.

## Canonical nodes

The canonical vocabulary includes:

- `ScienceDomain` and `ResearchField`;
- `Country` and `GeographicView`;
- `Institution` and `ResearchGroup`;
- `Researcher` and `Paper`;
- `MetricDefinition` and versioned `MetricObservation`;
- `HistoricalEvent` and `ExternalResource`.

Stable Atlas IDs are distinct from provider identifiers and display names. `AuthorityIdentifier` maps ROR, ORCID, INSPIRE, DOI, and arXiv identifiers to supported canonical entities. Renaming an institution or adding an authority ID therefore does not require changing routes or unrelated relationships.

`SourceSnapshot`, `RawEntityRecord`, `IdentityResolution`, and `IdentityReview` are evidence/audit records, not canonical graph nodes. Unresolved records remain outside canonical traversal, search, profiles, attribution, and metrics.

## Relationships

```text
Researcher <── Authorship ──> Paper ── PaperField ──> ResearchField
     │
     └── temporal Affiliation ──> Institution ── located in ──> Country
                              └──> ResearchGroup (optional)

Institution ── hosts ──> ResearchGroup
Paper ── Citation ──> Paper
Canonical entity ── has ──> ExternalResource
```

Relationships are normalized records rather than embedded copies. This permits multiple/concurrent affiliations, many authors, multiple field classifications, repeated external resources, and versioned observations without duplicating canonical entities.

Affiliation is time-dependent and keeps start/end bounds, source, confidence, and provenance. A researcher does not have one permanent institution field. An unknown date remains unknown. Paper metadata can support an affiliation observed for a publication, but it must not be inflated into an uninterrupted employment interval.

Authorship preserves author position; it does not express contribution share, employment, endorsement, or exclusive geographic ownership. Collaborative work can be attributed to every supported participating affiliation.

The live ingestion engine currently materializes papers, paper-field classifications, resources, and authorships only for authors carrying authority evidence such as an ORCID or INSPIRE author ID. Name-only authors become review evidence rather than silent canonical people. INSPIRE affiliation, reference, and citation structures are retained in the exact snapshot and raw-record evidence, but v3.0.4 does not yet promote them to canonical `Affiliation` or `Citation` edges. That promotion needs reviewed institution resolution plus temporal/conflict rules; the alpha does not infer missing edges.

## Geographic separation

Geographic rendering and scientific attribution are separate layers:

- institution coordinates and location metadata determine where an entity appears;
- `GeographicView` determines the geometry components and location memberships shown in a country canvas;
- temporal affiliation relationships determine research participation;
- metric observations remain scoped evidence and never rewrite geography.

This separation supports disconnected components, islands, antimeridian geometry, and the China/Taiwan exploration canvas without hard-coding geopolitical assumptions into research relationships. See the [geographic representation policy](geography-policy.md).

## Identity and provenance boundary

Resolution follows authority ID, canonical/alias/historical-name evidence, contextual evidence, and ambiguity-gated fuzzy candidates. Only a supported match or authority-backed creation enters the canonical graph. Conflicts become `needs_review` or `unresolved`; the persistent queue has no automated approval.

Every live evidence chain retains, where applicable:

- provider, record ID, snapshot, and retrieval time;
- normalization/field-mapping version and uncertainty;
- resolution method, confidence, version, and timestamp;
- dataset/update version;
- metric definition, algorithm, calculation version, and timestamp.

Deterministic connector fixtures traverse the same persistence path but remain labeled synthetic/demo in snapshots, raw records, canonical provenance, and dataset metadata. They are never evidence that a provider-backed graph is live.

## Repository and API boundary

`ScientificAtlasRepository` remains the application-facing conceptual contract. `StaticAtlasRepository` serves validated synthetic/pilot snapshots; `APIRepository` consumes typed FastAPI read models without exposing SQLAlchemy details to React.

The API provides canonical entity, relationship, profile, provenance, search, update-status, and bounded diagnostic graph routes. Map startup intentionally does not send the entire graph: it loads vocabulary and country observations, then fetches scoped institution nodes for the selected country. Institution and researcher profiles and relationships are loaded lazily and remain bounded/paginated.

`EntitySearchTerm` stores canonical names, aliases, historical names, token variants, and authority identifiers. It refreshes when supported canonical evidence changes. Search returns canonical entities with match evidence; identity confidence and query-match confidence remain separate technical signals.

## Incremental and non-destructive updates

INSPIRE, arXiv, and ROR scheduled connectors use closed acquisition windows with resumable page checkpoints. A batch records raw evidence before canonicalization, updates supported canonical nodes and edges, refreshes search terms/resources, plans affected metric partitions, and advances the high-water cursor only after the final page succeeds.

Canonical records are not deleted because a provider temporarily omits them. Replayed content is idempotent where possible, earlier snapshots and decisions remain auditable, and a source correction creates a new update chain instead of silently erasing history. ORCID and Crossref are targeted enrichers for known identifiers, not globally scheduled graph crawls.

## Metric boundary

Metrics are observations about a graph scope, not identity attributes or graph-edge weights. The update engine records affected entity/field/country/institution/year/metric partitions. The default live recalculator intentionally produces no new scientific values until reviewed formulas exist. Missing observations remain missing, and earlier versioned observations remain reproducible.

## Limitations

- The live graph has not been operated or benchmarked on a complete all-physics corpus.
- Provider coverage, affiliations, authority identifiers, citation edges, groups, dates, and coordinates are incomplete.
- Name-only paper authors remain review evidence until stronger identity support is available.
- Targeted ORCID/Crossref enrichment is not yet automatically orchestrated for every discovered identifier.
- No human review UI, merge/split workflow, hosted queue, or public production database is included.
- The bounded `/api/knowledge-graph` projection is diagnostic and not a general graph-query language.
- Graph connectivity reflects selected source evidence and can expose source bias; it is not proof of quality, causation, contribution magnitude, or institutional superiority.

Visible incompleteness is preferable to a richly connected graph built from unsupported merges.
