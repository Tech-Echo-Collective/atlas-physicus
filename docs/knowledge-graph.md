# Scientific knowledge graph

## Purpose and scope

Physics Atlas v3.0.3-alpha introduces a scientific knowledge-graph model above the existing repository and metric boundaries. The graph connects canonical entities and evidence-backed relationships so the application can answer questions such as:

- Which canonical institution does this source affiliation reference?
- Which institutions was a researcher affiliated with during a selected period?
- Which papers, fields, groups, and metrics connect to an institution?
- Which external resource belongs to a canonical entity?

The alpha graph is a validated static data model and query layer. It is not yet a graph database, live public API, complete scientific index, citation graph, ranking system, or recommendation engine.

## Processing architecture

```text
Scientific data sources
        ↓
append-only raw snapshots
        ↓
normalization into source records
        ↓
entity resolution
        ↓
canonical scientific entities
        ↓
profile enrichment and graph relationships
        ↓
Metric Engine
        ↓
AtlasRepository
        ↓
Atlas visualization
```

Identity precedes profile aggregation and metric attribution. Presentation components consume canonical records and already-resolved relationships; they do not decide whether two names represent the same person or institution.

## Nodes

`KnowledgeGraphService.build()` creates the following canonical node types:

- `ScienceDomain`;
- `ResearchField`;
- `Country`;
- `Institution`;
- `ResearchGroup`;
- `Researcher`;
- `Paper`;
- `ExternalResource`.

Stable internal identifiers are independent from display labels and source-system identifiers. Renaming an institution or adding an ORCID therefore does not require changing graph edges or routes.

Raw source records and identity-resolution decisions deliberately do not become graph nodes. The graph exposes an `identityResolutionBoundary` containing the raw-record IDs classified as matched, ambiguous, or unresolved, so evidence status remains inspectable without turning unresolved records into canonical entities. Historical events, metric definitions, and versioned metric observations remain validated Atlas records outside this alpha graph projection and continue through their established repository boundaries.

## Relationships

```text
Researcher <── Authorship ──> Paper ── classified as ──> ResearchField
     │
     └── Affiliation ──> Institution ── located in ──> Country
                    └──> ResearchGroup (optional)

Institution ── hosts ──> ResearchGroup
Canonical entity ── has ──> ExternalResource
```

The implemented graph edge vocabulary covers domain-to-field membership, institution location and field activity, group hosting and field activity, researcher field activity, temporal institution/group affiliation, authorship, paper classification, and resource ownership. Every edge references an existing canonical node or the graph build fails.

Relationships remain normalized records rather than embedded copies. This supports multiple affiliations, multiple authors, multiple external resources, and versioned observations without duplicating entities.

### Temporal relationships

Affiliation is time-dependent. Its start and end bounds, source, provenance, and confidence belong to the edge. A researcher does not have one permanent institution relationship. Concurrent and historical affiliations can coexist, and an unknown date remains unknown instead of being interpreted as permanent.

The current pilot derives point-in-time affiliation evidence from paper metadata. These dated observations support the paper connection but do not assert an employment interval between publications.

Authorship identifies a paper-person relationship and preserves author order. It does not establish employment, contribution share, or exclusive geographic ownership. Country and institution participation are derived from supported affiliation relationships under the project’s [geographic representation policy](geography-policy.md).

### External resources

URLs are represented as `ExternalResource` records rather than fields scattered across entity objects. Each record associates one canonical entity with a typed resource, label, URL, provenance, and optional source-specific identifiers or timestamps.

Supported resource vocabulary includes:

- official institution website;
- department website;
- research-group website;
- researcher homepage;
- ORCID;
- INSPIRE;
- arXiv;
- DOI.

This separation allows resources to be updated, deprecated, deduplicated, or verified without changing canonical identity. A link is supporting metadata, not evidence that every page statement has been verified by Physics Atlas.

## Graph invariants

- Only canonical entity IDs are used by profile, search-result, and metric relationships.
- Raw and unresolved source records are never silently presented as canonical entities.
- Every derived node or edge retains provenance and a source or processing version.
- Missing relationships remain missing; they are not inferred as negative facts.
- Geographic rendering and scientific attribution are separate graph concerns.
- Metric observations remain outside entity identity and keep their algorithm and calculation versions.
- User-defined metric composites never rewrite source observations or graph edges.

## Repository boundary

`AtlasRepository` remains the base application-facing boundary. `ScientificAtlasRepository` extends it with raw-evidence, identity-resolution, external-resource, snapshot/update, knowledge-graph, and profile queries. `StaticAtlasRepository` implements that extended contract for both validated synthetic and pilot snapshots.

The frontend asks for canonical entities and relationships; it does not depend on whether the implementation reads validated JSON or, in a future release, a service. `AtlasApiTransport` and `CanonicalEntityPersistence` name future transport and storage seams without implementing FastAPI or PostgreSQL. This preserves the existing World → Country → Institution → Researcher exploration architecture.

## Incremental and non-destructive updates

The update foundation treats each explicit acquisition as a versioned event:

```text
previous raw snapshots ───────────────┐
new source snapshot                   │
        ↓                             │
incremental normalization             │
        ↓                             │
identity re-resolution                │
        ↓                             │
versioned canonical graph build  ←────┘
        ↓
affected metric recalculation
        ↓
versioned export
```

Raw snapshots are append-only inputs. A new build writes a new manifest and derived output instead of destructively replacing prior evidence. `pipeline/data/manifests/inspire-hep-hep-th-snapshots.json` records the active snapshot, parent, source/version, timestamps, coverage, canonical content SHA-256 digest, record counts, processing versions, and output paths. The checked-in `incremental-update-plan.json` refreshes the overlapping 2025–2026 boundary and requires explicit ingestion; it does not run by itself.

`pipeline/reprocess.mjs` rebuilds a preserved raw snapshot beneath `pipeline/data/versions/<snapshot-id>/` without modifying the raw input. `pipeline/rebuild.mjs` refreshes the current compatibility outputs from the checked-in raw snapshot.

The alpha does not run a production scheduler or cloud service. Its update interfaces establish idempotent stages and version boundaries for later orchestration.

## Future PostgreSQL and FastAPI boundaries

A future PostgreSQL implementation can map canonical nodes to typed tables and relationship edges to join tables with temporal columns, provenance foreign keys, and version or validity ranges. JSON/JSONB can retain source payload references or less-stable external metadata, but canonical identifiers and important joins should remain relationally constrained.

A future FastAPI service can implement `AtlasRepository`-equivalent endpoints for:

- canonical entity lookup;
- entity-aware search;
- time-scoped affiliations and relationships;
- aggregated institution, group, and researcher profiles;
- metric definitions and observations;
- external-resource lookup;
- provenance and dataset-version inspection.

The API must return the same validated domain shapes or an explicitly versioned transport schema. Neither PostgreSQL nor FastAPI belongs inside React components, metric calculators, or resolution rules. Authentication, access policy, pagination, caching, migrations, background jobs, and operational monitoring remain future deployment work.

## Limitations

- The alpha graph is bounded by the synthetic fixture and the small INSPIRE-HEP pilot snapshot.
- It does not contain a complete citation, collaboration, topic, funding, or career graph.
- Identity and relationship confidence is not a measure of scientific quality.
- Some source entities, affiliations, dates, coordinates, and external resources are missing or unresolved.
- The graph does not infer exclusive country ownership for collaborative science.
- The current manifest contains one baseline snapshot; no production database, API, scheduler, queue, promotion/rollback UI, review interface, or continuous update service is deployed.
- The manifest digest hashes canonicalized JSON content, not the source file's exact bytes.
- Graph traversal can reveal source-data bias; a connected path is not proof of causation, endorsement, contribution magnitude, or institutional superiority.

The knowledge graph is infrastructure for transparent exploration. It must not be repurposed as a university ranking or researcher recommendation system.
