# Scientific data sources

## Source policy

Physics Atlas prefers official APIs, stores source provenance, and separates provider metadata from canonical interpretation. A source record is evidence to resolve, not permission to copy all provider content or proof that an entity match is correct. Code is licensed under the repository license; upstream data and linked content retain their own terms.

Production operators must review current provider documentation before enabling ingestion because API terms, schemas, and limits can change.

## Implemented connectors

| Provider | Official interface | Atlas use | Default cadence and request policy | Reuse and attribution notes |
| --- | --- | --- | --- | --- |
| INSPIRE-HEP | [INSPIRE REST API](https://github.com/inspirehep/rest-api-doc) | HEP literature, authors, affiliations, identifiers, citations when supplied | `hep-th-v1`: daily `subject:Theory-HEP` incremental modified-date query with provider-native `YYYY-MM-DD` bounds; bounded batches; connector minimum interval 1 s | Public INSPIRE metadata is generally intended for reuse and much is CC0, but restricted fields and linked content require their own review. Retain INSPIRE provenance and do not harvest personal contact data. |
| arXiv | [API documentation](https://info.arxiv.org/help/api/index.html), [user manual](https://info.arxiv.org/help/api/user-manual.html), and [terms](https://info.arxiv.org/help/api/tou.html) | `hep-th` preprints, raw categories, identifiers, authors, abstracts | `hep-th-v1`: daily `cat:hep-th` new-submission query using minute-resolution `submittedDate`; at least 3 s between requests; batches capped at 100 | Identify arXiv as the source and link to records. Metadata access does not transfer copyright in papers or abstracts; redistribution must follow arXiv terms and author rights. The Query API stream is not represented as complete revision coverage. |
| ROR | [REST API](https://ror.readme.io/docs/rest-api), [API versions](https://ror.readme.io/docs/api-versions), and [schema 2.1](https://ror.readme.io/docs/schema-v2-1) | Preferred organization IDs, canonical names, aliases, location, external IDs, authoritative websites | Weekly direct-record refresh only for configured, already-known ROR IDs; no registry-wide search; disabled with no targets | ROR data is released under CC0; attribution remains good scientific practice. See the [ROR terms](https://ror.org/about/terms/). |
| ORCID | [Public API terms](https://info.orcid.org/public-client-terms-of-service/) | Authority identifier and explicit researcher-profile enrichment | Targeted `fetch_record` only after an ORCID iD is already known; access token required outside fixture mode; no global or scheduled people polling | Display ORCID iDs according to ORCID guidance. Do not infer an ORCID, copy private data, or treat absence as evidence. Respect visibility and public-client terms. |
| Crossref | [REST API documentation](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) and [API tips](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-and-tricks/) | DOI, publication metadata, type, subjects, and landing-page links | Targeted `fetch_record` only after a physics source supplies a DOI; no unscoped scheduled works crawl; configure `mailto` for polite requests | Many bibliographic facts are reusable, but deposited abstracts or other fields may retain copyright. Preserve Crossref/DOI provenance and redistribute only fields whose rights permit it. |

Deterministic response fixtures for all five connectors are included in `backend/fixtures`. The standard automated test suite uses them without depending on provider uptime. End-to-end scheduled fixture ingestion covers INSPIRE and arXiv, plus ROR when the fixture's known ID is configured; ORCID and Crossref fixtures exercise record-scoped normalization and enrichment. Fixture snapshots, raw records, canonical provenance, and dataset metadata are labeled synthetic/demo and must never be presented as official provider-backed live data.

## Normalization boundary

All connectors emit a common `SourceRecord` and `NormalizedRecord` contract. Normalization can standardize IDs, dates, names, and provider syntax, but it does not choose a canonical identity. Each fetched JSON or Atom page is retained as an exact provider envelope in `SourceSnapshot`; normalized record evidence remains separately available in `RawEntityRecord`.

Authority identifiers dominate only when valid:

- institutions: ROR and other authoritative organization IDs;
- researchers: ORCID and INSPIRE author IDs;
- papers: DOI, arXiv ID, and INSPIRE literature ID.

Similar names alone do not justify a researcher merge. Conflicts and close candidates become `needs_review` or `unresolved` evidence.

### Canonical paper merge and bibliographic evidence

Paper occurrences join first on exact normalized strong identifiers, with the
canonical key selected in this order: DOI, arXiv ID, INSPIRE ID. Every provider
occurrence, raw value, snapshot, and source lineage remains attached after a
merge. A component containing incompatible values for one strong-identifier
scheme is not silently collapsed.

When no strong identifier links two occurrences, automatic replay is limited
by `canonical-paper-merge-policy-v1`: exact normalized title, an identical nonempty
normalized author set, the same nonempty year, and identical nonempty journal
evidence. Title alone, fuzzy similarity, or a partially matching author list
never triggers an automatic merge. Insufficient or conflicting candidates are
retained for review.

Provider dates describe different events. arXiv submission, INSPIRE earliest
record or preprint date, and formal journal publication evidence are therefore
normalized with explicit event kind and precision. They remain separate until
a reviewed cohort-date selection policy applies; processing order never chooses
the metric year.

### Institution authority

ROR supplies canonical institution identity and metadata. INSPIRE institution
IDs and raw affiliation names remain cross-reference evidence. A direct ROR
identifier can anchor an identity, but country, location, parent, and canonical
name are not claimed complete until the corresponding ROR record is preserved.
Subunits remain paper-time labels and can roll up only through a versioned,
supported parent relationship.

Historical exact-ID ROR evidence preserves the organization lifecycle state and
parent, predecessor, and successor relationships from the source snapshot.
Only one exact active parent can support an automatic statistical rollup.
Missing or multiple parents, inactive/withdrawn children, and predecessor or
successor links remain explicit and withheld rather than being guessed.

## Physics field mapping

Provider categories are retained verbatim and pass through the versioned
`provider-field-mapping-v1` catalog before becoming Atlas assignments. They are
source classification evidence, not equivalent to the
`physics-field-ontology-v1` vocabulary. Every result retains the raw category,
provider taxonomy, primary/secondary role, exact rule or explicit unmapped
status, Atlas targets, equal-share policy version, uncalibrated confidence, and
uncertainty note.

The foundation supports at least:

- High Energy Theory (`hep-th`);
- High Energy Phenomenology (`hep-ph`);
- High Energy Experiment (`hep-ex`);
- Lattice High Energy Physics (`hep-lat`);
- General Relativity / Quantum Cosmology (`gr-qc`);
- Quantum Information (`quant-ph`);
- Astrophysics (`astro-ph`);
- Condensed Matter (`cond-mat`);
- Atomic / Molecular / Optical Physics (`amo`);
- Nuclear Theory and Experiment (`nucl-th`, `nucl-ex`);
- Plasma Physics (`plasma`);
- Biophysics (`biophysics`);
- Mathematical Physics (`math-ph`).

One provider category can map to multiple Atlas fields, and some categories
remain unmapped. Under `provider-evidence-conservation-v2`, unmapped evidence
retains explicit mass and the remaining mapped mass is divided equally across
the unique supported Atlas fields. `cross-provider-field-reconciliation-v1`
creates one selected paper ledger, so a second provider cannot give the paper
another unit of field contribution. Primary/secondary status remains
provenance and does not silently alter the share. For example, a broad Crossref
subject or an arXiv cross-list is not evidence of one exclusive field. Mapping
uncertainty must survive ingestion rather than being collapsed into a confident
label. See [Physics Field Ontology v1](field-ontology.md).

## Freshness and limitations

Physics Atlas describes provider-backed operation as continuously refreshed or near-real-time metadata, never as realtime scientific truth. The effective update time is visible through `/api/updates/status` and depends on provider publication cadence, service limits, worker uptime, retries, and identity review.

INSPIRE pagination uses closed, inclusive `YYYY-MM-DD` windows. arXiv uses closed, minute-resolution `submittedDate` windows for new submissions. ROR checkpoints progress through the explicit configured target list. A persisted page checkpoint is resumed immediately after interruption, and the source high-water cursor moves to `until` only after the last page succeeds. Inclusive boundary replays are made safe by scope-aware content-addressed snapshots and identifier-led upserts. Cursor scope/version metadata and the dataset-level corpus marker prevent checkpoints or existing broad records from being silently reused by a different acquisition policy.

The connectors are a production-oriented foundation, not a complete global corpus. In particular, the arXiv Query API `submittedDate` path does not guarantee complete discovery of later revisions; a reviewed OAI-PMH or equivalent revision strategy remains future work. Coverage bias, missing affiliations, incomplete identifiers, missing publication dates, corrections, retractions, duplicate records, and delayed deposits remain possible. New papers without an explicit publication year are retained as unresolved raw evidence rather than assigned the ingestion year. INSPIRE affiliation, reference, and citation structures remain preserved in raw evidence; only relationships supported by the current authority-gated materializer become canonical graph edges. No provider supplies a scientifically validated Physics Atlas metric by itself.
