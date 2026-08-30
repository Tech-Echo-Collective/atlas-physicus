# Entity resolution

## Purpose and status

Physics Atlas resolves source records before treating them as people, institutions, or papers:

```text
RawEntityRecord → evidence and candidates → IdentityResolution
    → canonical entity OR IdentityReview / unresolved
```

v3.0.4-alpha persists each layer in PostgreSQL and applies the existing identifier-led resolver during incremental updates. Resolution answers which canonical entity a source record most likely describes. It does not evaluate science, infer contribution, or prove a real-world identity.

## Evidence layers

### Raw record

A raw record preserves provider, provider record ID, payload, checksum, source snapshot, retrieval/update time, and provenance. It is immutable evidence. Re-normalization or a new source revision creates new derived processing records rather than overwriting the captured input.

### Resolution decision

An `IdentityResolution` records entity type, raw record, candidate or matched canonical ID, status, method, evidence, confidence, resolver version, timestamp, and provenance. Only a matched result can reference a canonical entity for traversal.

`IdentityReview` stores ambiguity or insufficient evidence persistently. An unresolved item is not inserted into profiles, search, affiliation attribution, or metrics as if its identity were known.

### Canonical entity

A canonical entity has a stable Physics Atlas ID, preferred name, aliases/historical names where supported, authority identifiers, identity provenance, and confidence. Canonical does not mean eternally correct. A reviewed correction creates a traceable new decision while preserving the source evidence and earlier processing version.

## Resolution order

The common policy is:

1. exact compatible authority identifier;
2. exact canonical name;
3. exact alias or abbreviation;
4. exact historical name;
5. contextual evidence such as institution location, field, affiliation, or coauthor structure;
6. fuzzy-name candidate only when it clears both a threshold and an ambiguity margin;
7. `needs_review` or `unresolved` when evidence is insufficient or conflicting.

Preferred identifiers include:

- institution: ROR and other authoritative organization IDs;
- researcher: ORCID and INSPIRE author ID;
- paper: DOI, arXiv ID, and INSPIRE literature ID.

Authority evidence dominates only when the identifier is valid and belongs to a compatible entity type. Provider mistakes, deprecated IDs, or conflicting IDs remain reviewable. String similarity alone cannot silently merge researchers.

Resolution confidence describes the identity decision. Search confidence describes a user's query-to-canonical-result match. Neither is a scientific metric, quality score, or probability that every associated source fact is correct.

## Institutions

A canonical institution may contain official name, aliases, historical names, ROR/INSPIRE/Wikidata identifiers where sourced, and location metadata. ROR is the preferred organization authority when available, but stronger or conflicting evidence is not overwritten without provenance.

Identity is independent from map rendering. Institution coordinates determine research-location display; `GeographicView` determines the exploration canvas; temporal affiliations determine attribution. Resolving an institution never rewrites political geometry or assigns exclusive country ownership to collaborative work.

## Researchers

A canonical researcher can contain name variants and explicitly sourced ORCID or INSPIRE identifiers. Not every researcher has an ORCID, and absence is not evidence against an identity.

Person-name matching is especially risky because of initials, ordering, diacritics, transliteration, common names, and changing affiliations. An approximate name is therefore candidate evidence only. The live pipeline persists ambiguous people for review instead of promoting them to canonical search results.

## Papers

Paper identity is led by DOI, arXiv ID, or INSPIRE ID. Titles and author lists can support a candidate but are insufficient when strong identifiers conflict. Provider category mapping is a separate scientific-classification decision and does not determine paper identity.

Cross-provider records may contribute complementary metadata to one canonical paper only after identity evidence supports the merge. Source-specific payloads and provenance remain available after canonicalization.

## Temporal affiliations

```text
Researcher ── Affiliation ── Institution
                         └── ResearchGroup (optional)
```

Each affiliation carries start/end bounds, source, confidence, and provenance. Concurrent and historical affiliations can coexist. An unknown bound remains unknown, not “all time.” A newer affiliation cannot replace an older one.

Publication metadata often supports only the statement that an affiliation appeared on a paper at a point in time. Physics Atlas records that dated observation and does not inflate it into continuous employment. Historical profile and paper-attribution queries must evaluate the edge for the relevant period.

Metric attribution uses the separate `PaperAffiliation` materialization, which
binds every provider author slot to its raw paper-time affiliation assertion,
optional canonical institution/country, exact fractional share, and source
snapshot. Authority identifiers and unique reviewed exact names may resolve an
institution; ambiguous or unsupported strings stay withheld. A homepage or
current profile update can neither replace nor retroactively reinterpret that
materialization. See [Scientific Attribution](scientific-attribution.md).

Collaborative papers can appear in every institution profile with a supported author affiliation. This is participation attribution, not contribution share or exclusive country ownership.

## Incremental pipeline and review

For each changed source record, the update engine stores the raw evidence, normalizes syntax, runs the resolver version recorded on the update, and then either:

- updates or creates a supported canonical record;
- records a matched resolution to an existing entity;
- creates a `needs_review` item with candidates/evidence;
- records unresolved evidence without a canonical pointer.

The source cursor advances only after the complete batch succeeds. Replaying an identical snapshot is idempotent. A source temporarily omitting an entity never triggers silent canonical deletion.

`/api/identity-resolutions` exposes auditable decisions, and `/api/updates/status` reports the number of open review items. v3.0.4 has a persistent review queue but no reviewer UI, authentication, or automated approval policy.

v3.0.5 adds an aggregate `/api/identity-resolutions/summary` contract and the
deterministic validation framework documented in
[entity-resolution validation](entity-resolution-validation.md). Resolution
outcomes remain separate from `needs_review` workflow state. Precision, recall,
and confidence calibration are withheld until enough cases have independent
human labels.

Persisted evidence may include a typed missing/invalid-metadata reason. The API
preserves that reason rather than dropping it; public summaries expose only
aggregate counts. Future cross-provider re-resolution must append a versioned
superseding decision and must not overwrite older evidence.

## Search integration

Search indexes only canonical entities and supported identifiers/names. Results identify entity type, match method/value, query confidence, and available identity confidence. Aliases, abbreviations, historical names, ROR, ORCID, INSPIRE, DOI, and arXiv identifiers can be matched where present.

Adding a canonical name, alias, or external identifier through an update changes the canonical search evidence. Unresolved raw records are never exposed as canonical results, and selecting a search result never mutates identity data.

## Provenance requirements

Every automated decision must be reproducible from source snapshot/record, provider identifier, resolver/rule version, evidence, method, confidence, status, and processing time. Provider field mappings keep their own rule version and uncertainty; they are not identity evidence by default.

Historical pilot reports remain reproducible from checked-in snapshots. Live fixture results demonstrate the persistent flow only. A truly live deployment must publish current source/update status and must not imply that its resolver has complete or perfect coverage.

## Limitations

- Authority identifiers can be absent, wrong, duplicated, deprecated, or conflicting.
- Name/alias matching can produce false positives and false negatives.
- Historical names, affiliation dates, and cross-provider coverage are incomplete.
- Confidence is heuristic and not calibrated against a representative reviewed truth set.
- The alpha review queue has no operational adjudication UI or correction-approval workflow.
- Broader ingestion needs sampled expert review, reversible merge/split procedures, and explicit conflict policy.

Physics Atlas must prefer visible uncertainty and a reviewable raw record over an unsupported canonical merge.
