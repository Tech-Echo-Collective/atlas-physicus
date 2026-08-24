# Entity resolution

## Purpose and status

Physics Atlas resolves source records before treating them as people or institutions. v3.0.3-alpha establishes the first-class identity contract needed by the static atlas and future data services:

```text
Raw source entity
        ↓
resolution evidence and candidates
        ↓
resolved identity decision
        ↓
canonical scientific entity
```

This boundary answers “which known entity does this source record describe?” It does not judge scientific work, infer contribution, or guarantee real-world identity. Entity resolution is probabilistic data integration, not proof. A low-confidence or ambiguous record remains explicit instead of being silently merged into a canonical entity.

## Identity layers

### Raw entity

A raw entity is the source-specific representation preserved with its original source record. It may contain a spelling variant, abbreviation, historical name, source identifier, or incomplete affiliation. Raw records are immutable evidence: normalization and reprocessing produce new derived records rather than overwriting the captured source.

### Resolved identity

A resolved identity records the decision between one raw entity and a candidate canonical entity. The decision carries:

- entity type;
- raw record and source identifiers;
- candidate canonical identifiers in evidence, when available;
- a canonical entity pointer only when status is `matched`;
- resolution status;
- method and evidence;
- confidence from `0` to `1`;
- provenance and processing version;
- resolution timestamp.

Unresolved records remain addressable. They are not inserted into profiles, searches, relationships, or metric attribution as though their identity were known.

### Canonical entity

A canonical entity has a stable Physics Atlas identifier and a preferred display name. It retains aliases, historical names where applicable, authoritative external identifiers, structured provenance, and the best available identity confidence. Canonical records are the nodes exposed through profiles, search results, and graph relationships.

Canonical does not mean eternally correct. A later source snapshot or reviewed rule can create a new version of the derived identity layer while preserving the evidence and prior processing record.

## Resolution strategy

Resolution is identifier-led and evidence-aware. The intended order is:

1. exact authoritative external identifier;
2. exact canonical name;
3. exact recorded alias, including a supplied abbreviation;
4. exact recorded historical name;
5. fuzzy name comparison;
6. explicit ambiguous or unresolved result when evidence is insufficient or conflicting.

The current `CanonicalIdentityResolver` uses authority identifiers and canonical name records before its name-similarity fallback. The fallback is thresholded and must clear an ambiguity margin over the next candidate. Future contextual resolvers can add location for institutions and affiliation, field, or coauthor evidence for researchers. String similarity alone must not create an unqualified high-confidence match.

Confidence communicates the strength of the identity decision only. It is not a metric, rank, probability of research quality, or guarantee that every source fact associated with the identity is correct.

The schema reserves `manual-review` as a resolution method so a future reviewed correction can retain the same evidence contract. v3.0.3-alpha has no human-review UI and does not present automated ambiguity as manual verification.

## Institution resolution

A canonical institution identity can contain:

- stable Physics Atlas institution ID;
- official name;
- aliases and abbreviations;
- historical names;
- external identifiers such as ROR, INSPIRE, or Wikidata when available;
- location metadata;
- provenance and confidence.

For example, “Caltech,” “California Inst. of Technology,” and “CIT” can resolve to the same canonical institution when identifier and contextual evidence support that decision. The source labels remain available as aliases or raw evidence.

Institution identity is separate from geographic rendering. Resolving a name does not rewrite map geometry, research attribution, or affiliation history. An institution without renderable coordinates can remain a valid canonical and attribution entity.

## Researcher resolution

A canonical researcher identity can contain:

- stable Physics Atlas researcher ID;
- canonical display name and name variants;
- external identifiers such as ORCID or an INSPIRE author identifier;
- associated research fields;
- provenance and confidence.

Affiliations are not embedded as one permanent institution field. They are traversed through dated `Affiliation` relationships. This allows one person to move between institutions, hold concurrent affiliations, or have gaps in the known record without changing their identity.

Name-only matches are especially unsafe for people. Initials, ordering, diacritics, transliteration, common names, and changing affiliations can produce collisions. A fuzzy match such as “E. Witten” is therefore a candidate signal, not sufficient evidence by itself.

## Temporal affiliations

The relationship model is:

```text
Researcher ── Affiliation ── Institution
                         └── Research group (optional)
```

Each affiliation carries temporal bounds, source provenance, and confidence. An open end represents an affiliation still current or a source that supplied no end. A missing bound means unknown, not all time.

The INSPIRE pilot usually has evidence that an affiliation appeared on a publication, not a verified employment interval. It therefore records a dated affiliation observation at the paper date. That point-in-time assertion must not be expanded into continuous employment before or after the observation.

Queries must respect affiliation time when deriving historical relationships. The current `ProfileService` checks affiliation validity against a paper’s year and exposes a researcher’s full ordered affiliation history. Historical movement is preserved as multiple relationship records; a newer affiliation must not destructively replace an older one. Scientific collaboration and country attribution follow affiliations supported for the relevant period rather than a person’s current profile location.

## Search integration

Entity-aware search resolves the user’s text against canonical names, aliases, historical names, abbreviations, and stable external identifiers. Its flow is:

```text
User query
        ↓
normalized candidate retrieval
        ↓
identity-aware scoring
        ↓
canonical entity result
        ↓
canonical Atlas profile route
```

Results identify the canonical entity, entity type, matched text or reason, and confidence where appropriate. Search confidence describes the query-to-entity match; it is distinct from the underlying entity-resolution confidence. Search does not create new identities or mutate canonical records.

## Provenance, versioning, and review

Every automated decision must remain reproducible from:

- the preserved source snapshot;
- source and external identifiers;
- resolver and rule version;
- evidence and match method;
- confidence and status;
- calculation or resolution time.

Incremental ingestion appends a new raw snapshot and derives a new versioned resolution result. Reprocessing can improve canonical mappings without deleting the input or silently rewriting past output. Conflicting identifiers, ambiguous candidates, and missing evidence should be surfaced for future review queues rather than forced into the graph.

Snapshot-specific counts and methods are stored in `pipeline/data/reports/entity-resolution.json`. The checked-in pilot happens to report no unresolved affiliation mentions, but that is a property of its 81 selected records and authoritative INSPIRE references—not evidence of perfect resolver accuracy or an expected result for broader ingestion.

## Limitations

- v3.0.3-alpha provides an identity and search foundation, not comprehensive multi-source reconciliation.
- External identifiers can be absent, duplicated, mistyped, deprecated, or linked incorrectly by a source.
- Alias and fuzzy matching can produce false positives and false negatives.
- Historical names and affiliation dates are incomplete in many scientific metadata sources.
- Confidence is heuristic and is not yet statistically calibrated against a reviewed truth set.
- No automated resolver can claim perfect identity matching. High-impact ambiguous merges require human review and reversible corrections.
- Unresolved records are intentionally excluded from canonical traversal unless a consumer explicitly requests unresolved evidence.

These limitations are design constraints. Physics Atlas must prefer a visible unresolved record over a confident-looking but unsupported merge.
