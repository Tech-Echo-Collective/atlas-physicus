# Profile system

## Purpose

Profiles are read models assembled from canonical entities and graph relationships. They give the Atlas a coherent entity view without copying papers, affiliations, resources, or metrics into the entity record itself.

```text
Canonical entity
        + time-scoped relationships
        + external resources
        + metric observations
        + provenance
        ↓
versioned profile read model
```

Profiles do not perform entity resolution, calculate scientific metrics, rank entities, or recommend researchers. They expose the best currently resolved evidence and keep gaps visible.

## Aggregation rules

Profile aggregation follows these rules:

- begin from one canonical entity ID;
- traverse only validated relationships that reference canonical IDs;
- use an affiliation valid for the paper year when deriving institution or group paper connections;
- expose the complete ordered affiliation history for a researcher instead of selecting one permanent institution;
- include historical affiliations separately from active affiliations;
- retrieve typed external resources through the resource layer;
- retrieve metric observations through the existing Metric Engine/repository boundary;
- preserve source and resolution provenance;
- omit or label unresolved evidence rather than silently attaching it;
- avoid interpreting a missing relationship as evidence that no relationship exists.

The same rules apply whether records come from the synthetic fixture, a versioned pilot export, or a future API-backed repository.

## Institution profile

An institution profile can aggregate:

- canonical official name, aliases, and historical names;
- location and geographic context;
- official and department websites;
- associated research groups;
- researchers connected by time-scoped affiliations;
- relevant research fields;
- papers connected through resolved authorships and affiliations;
- supplied metric observations and history;
- external identifiers, provenance, and identity confidence.

“Associated” does not mean exclusive ownership. A collaborative paper can appear in multiple institution profiles because each resolved participant receives affiliation-based attribution.

## Researcher profile

A researcher profile can aggregate:

- canonical name and name variants;
- ORCID, INSPIRE, arXiv, and homepage resources when available;
- historical and current affiliations with dates and confidence;
- research fields;
- papers connected through authorship;
- collaboration relationships derived from shared papers;
- supplied researcher metric observations when available;
- provenance and identity confidence.

The profile must not collapse affiliation history into one permanent institution. A collaboration edge means only that the selected data contains a supported shared-work relationship; it is not a recommendation, endorsement, or contribution assessment.

## Research-group profile

A research-group profile can aggregate:

- group name and canonical host institution;
- associated research field;
- official group website;
- members connected by time-scoped affiliations;
- papers connected through those resolved relationships;
- available provenance and source version.

Group membership is relationship data. It is not an embedded, permanent member list, and incomplete metadata must be disclosed rather than completed by assumption.

## External resources

Profiles request resources by canonical entity ID and resource type. They do not store arbitrary URLs on institution, researcher, or group objects. This supports multiple links of one type, historical links, independent verification status, and later link maintenance.

Resource display should prefer an authoritative identifier or official site when provenance supports it. Physics Atlas does not scrape linked pages as its primary data source and does not guarantee availability, ownership, completeness, or current content of external websites.

## Entity-aware search to profiles

Search is the entry point to a canonical profile:

```text
query text
        ↓
canonical/alias/identifier candidates
        ↓
scored entity-aware matches
        ↓
selected canonical entity ID
        ↓
Atlas route and profile aggregation
```

For example, an institution abbreviation can lead to the institution’s canonical profile, and a researcher name variant can lead to the canonical researcher profile when the resolution evidence is sufficient. Results identify entity type and confidence where appropriate so similarly named entities are not flattened into one answer.

Search matching and entity resolution are related but separate:

- entity resolution maps source records into the canonical graph during data processing;
- search matching maps a user query to an already-canonical entity at interaction time.

Selecting a search result never changes the canonical graph.

## Repository and future API contract

Profile composition belongs behind repository/query services, not inside visual components. `ProfileService` aggregates validated records in memory, and `ScientificAtlasRepository` exposes `getInstitutionProfile`, `getResearcherProfile`, and `getResearchGroupProfile`. Its `AtlasApiTransport` and `CanonicalEntityPersistence` seams allow a future PostgreSQL/FastAPI adapter to provide equivalent projections without redesigning the Atlas interface; no such backend is implemented in this alpha.

Future API responses should remain explicit about:

- canonical entity and profile version;
- requested temporal scope;
- included relationship types;
- unresolved or omitted evidence;
- provenance and source timestamps;
- pagination or truncation for large paper, member, and collaboration collections.

## Limitations

- Profiles are only as complete and current as the selected dataset version.
- Identity confidence and search confidence are not guarantees of identity.
- Current source records can lack historical affiliations, resource links, coordinates, papers, or group membership.
- Profile paper and collaboration coverage is incomplete in the bounded pilot.
- External links can move, expire, or contain information not verified by Physics Atlas.
- Aggregated metrics retain all limitations of their source observations and do not create rankings.
- The alpha has no user-editable profile claims, review workflow, account system, or live institutional verification.

A concise but incomplete profile is preferable to a richly populated profile built from silent guesses.
