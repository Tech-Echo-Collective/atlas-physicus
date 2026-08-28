# Profile system

## Purpose

Profiles are bounded read models assembled from canonical entities and supported graph relationships. They do not copy papers, affiliations, resources, or metrics into an identity record.

```text
canonical entity
    + time-scoped relationships
    + external resources and health state
    + versioned metric observations
    + provenance
    → profile read model
```

Profiles do not resolve identities, calculate scientific metrics, rank entities, or recommend researchers. They expose the selected dataset's supported evidence and keep gaps visible.

## Data modes and transport

The same conceptual profile contract is available through:

- `ProfileService` and `StaticAtlasRepository` for validated synthetic and historical pilot snapshots;
- FastAPI `/api/profiles/institutions/{id}`, `/api/profiles/researchers/{id}`, and `/api/profiles/groups/{id}` for PostgreSQL canonical data;
- frontend `APIRepository`, which validates responses and loads selected profiles lazily.

Switching source replaces the repository boundary. A profile never silently combines synthetic, pilot, fixture, and provider-backed records. Fixture-backed API profiles retain explicit synthetic/demo provenance.

## Aggregation rules

Profile assembly must:

- begin from one canonical entity ID;
- traverse only canonical, validated relationships;
- respect affiliation dates when connecting a paper to an institution/group;
- expose ordered current and historical affiliations rather than one permanent institution;
- retrieve typed links through `ExternalResource` and preserve their check/provenance state;
- retrieve metrics through the Metric Engine/repository boundary;
- preserve source, update, resolution, and calculation provenance;
- omit or label unresolved evidence rather than attaching it by guess;
- keep missing relationships missing;
- bound or paginate large collections.

## Institution profile

An institution profile can provide canonical/alias/historical names, authority identifiers, location, resources, hosted groups, time-scoped researchers, connected fields and papers, supplied metric observations, and provenance.

“Connected” is not exclusive ownership. A collaborative paper can appear for every institution with a supported participating affiliation. A node's inclusion or metric display is not an institutional ranking.

## Researcher profile

A researcher profile can provide canonical name variants, supported identifiers/resources, ordered affiliation history, fields, authored papers, collaborators derived from shared authorship, supplied observations, and provenance.

An ORCID or INSPIRE link appears only when explicitly supported. Not having an ORCID is not negative evidence. A collaboration edge records shared work in the selected source; it is not contribution allocation, endorsement, or recommendation.

## Research-group profile

A group profile can provide its host institution, fields, resources, dated members, and connected papers. Group membership is relationship data, not an embedded permanent list. Live group coverage depends on source evidence and may be sparse.

## External resources

Profiles request resources by canonical entity and type. Active verified authority links can be preferred for display while older/failing resources and check history remain auditable. Reachability does not verify ownership or scientific accuracy, and linked page content is not copied into the profile as scientific truth.

The resource monitor uses an operator host allowlist, public-address validation, bounded `HEAD` or one-byte range `GET`, retries/backoff, timeouts, and cached check history. Temporary failures do not delete a link or revoke earlier provenance.

## Search to profile

Canonical search indexes supported names, aliases, historical names, token variants, abbreviations, authority IDs, paper titles, DOI, arXiv IDs, and INSPIRE IDs. A result reports matching evidence and resolves to one canonical entity. Institution, group, and researcher results open their canonical Atlas context. Because v3.0.4 has no dedicated paper route, a paper result loads the canonical paper and authorships, then opens the first resolved author affiliation context; when none exists, the UI states that no navigable context is available. Selecting a result never changes identity data.

Search confidence measures query matching; identity confidence records a resolution decision. Neither measures scientific quality. Unresolved raw records never appear as canonical profile destinations.

## Frontend behavior

The Atlas stays map-first:

1. global startup loads only map vocabulary/country observations;
2. country entry loads bounded major-institution nodes;
3. institution selection lazily requests its profile and scoped authorships;
4. researcher selection lazily requests the researcher profile and authorships;
5. paper search selection lazily requests one paper and its bounded authorships instead of loading the publication graph globally.

The UI preserves source context, loading/error state, and compatible URL selection. A stale request cannot replace a newer source/entity selection.

## Limitations

- Profile completeness is bounded by the selected dataset and resolution coverage.
- Scheduled ingestion currently covers INSPIRE, arXiv, and ROR; ORCID/Crossref are record-scoped enrichers.
- Live paper authors without authority identifiers remain review evidence and are not silently promoted to profiles.
- Historical affiliations, groups, citations, coordinates, and resources are often incomplete.
- The alpha has no user-editable claims, authenticated correction flow, or human identity/resource-review UI.
- Collection endpoints are paginated. Alpha profile payloads use fixed upper bounds (affiliations/entities 500, papers 200, metrics 500, resources 100), so a profile response is not guaranteed to be an exhaustive scholarly bibliography.
- No public production backend is supplied, so GitHub Pages uses the static/pilot fallback unless separately configured.

A concise, traceable profile is preferable to a complete-looking profile built from silent inference.
