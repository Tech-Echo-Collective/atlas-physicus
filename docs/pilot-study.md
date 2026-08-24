# INSPIRE-HEP pilot study

## Purpose and status

Physics Atlas v3.0.2-alpha adds a deliberately bounded real-metadata pilot to test acquisition, normalization, entity resolution, metric calculation, provenance, export, and frontend repository integration. It does not establish a scientific methodology or support comparisons of research quality.

The pilot is incomplete and selection-biased by design. Its map values must not be used as rankings, evaluations, policy evidence, or scientific conclusions.

## Bounded scope

| Dimension | Pilot boundary |
| --- | --- |
| Science domain | Physics |
| Research field | Primary-category `hep-th` records only |
| Period | 2000–2026 inclusive |
| Sample | Three most-recent matching records per year |
| Literature records | 81 |
| Matching records reported across the 27 yearly queries at retrieval | 94,491 |
| 2026 status | Year-to-date at the retrieval timestamp |
| Runtime data source | Versioned local export; the browser does not call INSPIRE |

The acquisition query for each year is equivalent to `primarch:hep-th and de:YYYY`, sorted by most recent, with a response size of three. At the captured retrieval time, the totals reported by the 27 yearly queries summed to 94,491 matching records; the pilot selected 81 of them. The reported total is specific to this source snapshot and may change as INSPIRE metadata is maintained. This is a deterministic engineering sample, not a representative sample of high-energy theory. The 2026 slice is necessarily incomplete because it was retrieved before the end of the calendar year.

## Source, use, and citation

Literature, author-affiliation, citation-count, and institution metadata come from the [INSPIRE-HEP REST API](https://github.com/inspirehep/rest-api-doc). Query construction follows the official [INSPIRE paper-search guidance](https://help.inspirehep.net/knowledge-base/inspire-paper-search/) and [search-term reference](https://help.inspirehep.net/knowledge-base/full-listing-of-search-terms/). Field interpretation follows the published [INSPIRE HEP schema](https://inspire-schemas.readthedocs.io/en/latest/schemas/hep.html).

Use and redistribution of source metadata remain subject to the [INSPIRE Terms of Use](https://help.inspirehep.net/knowledge-base/terms-of-use/). The pilot intentionally excludes email addresses and abstract text from its normalized frontend export. The INSPIRE API itself can be cited using its [Zenodo software record](https://doi.org/10.5281/zenodo.5788550).

The captured source snapshot identifies:

- source: `INSPIRE-HEP REST API`;
- source-documentation reference: `INSPIRE REST API documentation accessed 2026-08-24`;
- pipeline version: `v3.0.2-alpha-pilot.1`;
- exact retrieval timestamp and source version in the raw snapshot;
- exact yearly request URL and total matching-record count for every year.

## Pipeline and raw preservation

```text
INSPIRE-HEP literature and institution records
        ↓
pipeline/ingestion
        ↓
preserved raw response snapshot
        ↓
pipeline/normalization
        ↓
pipeline/entity_resolution
        ↓
pipeline/metrics
        ↓
pipeline/export/hep-th-pilot.json
        ↓
StaticAtlasRepository → AtlasRepository → existing atlas UI
```

The raw source response is preserved at `pipeline/data/raw/inspire-hep-hep-th-2000-2026.json`. It contains the requested source fields and the returned INSPIRE records without replacing them with normalized values. Derived artifacts are written separately:

- normalized entities and relationships: `pipeline/data/processed/normalized-hep-th-pilot.json`;
- identity-resolution report: `pipeline/data/reports/entity-resolution.json`;
- metric summary: `pipeline/data/reports/metric-summary.json`;
- validated frontend snapshot: `pipeline/export/hep-th-pilot.json`.

`npm run pipeline:ingest` acquires a new source snapshot. `npm run pipeline:rebuild` reconstructs the normalized data, metrics, reports, and frontend export from the preserved snapshot without another network request. A new acquisition can change results because INSPIRE metadata and citation counts are maintained over time.

## Normalization

The pilot normalizes source records into the existing Physics Atlas entities and joins:

- `Paper`, using the INSPIRE control number as the stable source identifier and retaining DOI and arXiv identifiers when present;
- `Researcher`, keyed by the INSPIRE author-record identifier for this snapshot;
- `Institution`, keyed by the INSPIRE institution-record identifier;
- `Country`, derived from the institution record's address country code and mapped to ISO alpha-3 and numeric codes;
- `Affiliation`, joining a normalized researcher and institution over the years observed in the sample;
- `Authorship`, preserving the paper, researcher, and author position;
- `ResearchField`, fixed to the pilot's primary `hep-th` scope.

Every participating institution and country receives full participation attribution for a paper. A collaborative paper is therefore not assigned to one exclusive institution or country. This follows the repository's separation between geographic rendering and affiliation-based research attribution.

## Entity-resolution results

| Result | Count or value |
| --- | ---: |
| Literature records | 81 |
| Countries | 35 |
| Institution source records / normalized institutions | 143 / 143 |
| Institutions with renderable coordinates | 126 |
| Institutions retained for attribution without coordinates | 17 |
| Unique normalized researchers | 178 |
| Author appearances | 187 |
| Author appearances resolved through INSPIRE author-record IDs | 187 |
| Affiliation mentions | 234 |
| Resolved affiliation mentions | 234 |
| Unresolved affiliation mentions | 0 |
| Mean researcher-identity confidence | 0.99 |

All author appearances in this particular snapshot resolve through an INSPIRE author-record identifier; the configured BAI and normalized-name-plus-affiliation fallbacks were not needed. The 100% affiliation-resolution rate describes only these 81 sampled records. It is not an expected rate for broader INSPIRE data and does not prove that source identities or affiliations are error-free.

Resolution provenance is retained on normalized records. Institution location uses the address metadata returned by the current INSPIRE institution record, which may not represent a historical address for every publication year. Seventeen normalized institutions have no usable coordinates: they remain valid affiliation and metric-attribution entities but cannot render as geographic nodes. This is an explicit separation between scientific attribution and available map geometry.

## Pilot metrics

The pipeline produces 1,060 observations: four metrics for each of 107 sampled country-years and 158 sampled institution-years. The full entity registry contains 35 countries and 143 institutions, but an observation is emitted only when the entity has resolved sampled-paper participation in that year. Each observation records its source, field, period, algorithm version, calculation version, calculation timestamp, and derived-data provenance.

The four calculated signals are:

| Metric | Raw pilot signal | Algorithm version |
| --- | --- | --- |
| Research Activity | Count of distinct sampled papers with at least one resolved affiliation to the entity in the year | `pilot-activity-full-participation-minmax-v1` |
| Research Impact | `log(1 + x)`, where `x` is the entity-year sum of fully attributed INSPIRE citation counts without self-citations | `pilot-impact-log-citations-minmax-v1` |
| Collaboration / Connectivity | Count of distinct peer institutions or countries co-participating in at least one sampled paper in the year | `pilot-connectivity-unique-partners-minmax-v1` |
| Research Momentum / Sustainability | `(recent − previous) / max(1, recent + previous)`, comparing adjacent three-year participation windows | `pilot-momentum-rolling-participation-minmax-v1` |

For visualization, each raw signal is min-max scaled to `0–100` independently among entities with sampled participation within each year and entity type. If all values in an active scope are equal, a nonzero scope receives `50`; a constant-zero scope would receive `0`. No observation is emitted when an entity has no resolved sampled-paper participation in a year: absence from this sample remains missing rather than being encoded as a measured zero. These are sample-relative display indices, not comparable scientific measurements across entity types, years, fields, or datasets.

Research Diversity, Talent Ecosystem, and Concentration / Vulnerability remain taxonomy definitions only. The pilot does not silently substitute synthetic values for them, and the five-metric composite profiles are therefore unavailable for the real-data pilot source.

## Frontend integration

The generated export is schema-validated and loaded through `StaticAtlasRepository`, which implements the same `AtlasRepository` contract as the synthetic framework dataset. A source selector swaps repository instances while preserving the existing exploration hierarchy and visualization architecture:

```text
Science domain → Research field → Year → World → Country → Institution
```

The browser consumes the local, versioned pilot export. It does not call INSPIRE at runtime, recalculate scientific signals in React, or combine pilot and synthetic observations. World View continues to show country observations; Country View continues to replace the country layer with institution nodes.

## Limitations and uncertainty

- Three most-recent records per year cannot represent the volume, impact, collaboration structure, or evolution of `hep-th`.
- Sorting by most recent is a sampling rule, not an importance criterion; it introduces temporal and curation bias.
- The pilot covers one field, one source, and 81 selected records against 94,491 matches reported by the snapshot's yearly queries.
- 2026 is year-to-date and must not be compared with complete years as if coverage were equal.
- INSPIRE metadata may be corrected after retrieval; citation counts are mutable, age-dependent, and limited by INSPIRE's citation graph.
- Citation metadata is not a measurement of scientific quality and differs across document age, type, and citation practice.
- Institution records provide current metadata and can misrepresent historical geography or affiliation naming.
- Only 126 of 143 normalized institutions have renderable coordinates; the remaining 17 still contribute to attribution and observations but cannot appear as map nodes.
- Full participation attribution intentionally counts collaborative papers for every resolved participant; it is not fractional contribution accounting.
- A successful identifier join shows technical resolution, not verified real-world identity, institutional membership, or contribution.
- Within-year min-max scaling is highly sensitive to the tiny sample and hides absolute magnitude.
- Missing sampled participation is not evidence that an entity had no real research activity.
- The pilot includes no uncertainty propagation, deduplication across external sources, topic model, scientific-review process, or validated metric formula.
- The result supports pipeline and interface testing only. It makes no ranking, performance, quality, policy, or scientific claim.

Broader ingestion, representative sampling, multi-source reconciliation, historical affiliation validation, uncertainty methods, and scientific methodology review require separate future work.
