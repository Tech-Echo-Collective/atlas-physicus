# Atlas Physica durable decisions

Last reviewed: 2026-09-05

These decisions constrain implementation and public communication. Add a dated superseding entry when a durable decision changes; do not silently rewrite project history.

Earlier entries retain the historical name Physics Atlas; their scientific and
architectural constraints continue to apply to Atlas Physica.

| ID | Decision | Consequence |
| --- | --- | --- |
| PA-001 | Physics Atlas is descriptive and exploratory, not predictive. | Do not add prediction claims, forecasting, or interfaces that imply future scientific performance. |
| PA-002 | Physics Atlas does not rank researchers, institutions, universities, countries, or fields. | Metrics, ordering, labels, and visual emphasis must not be presented as statements of scientific worth. |
| PA-003 | Physics Atlas does not provide personalized researcher or paper recommendations. | Discovery follows explicit atlas exploration and search, not behavioral profiling or recommendation scoring. |
| PA-004 | Metrics are reference and exploration tools, not judgments of scientific value. | Every implemented metric needs an explicit definition, interpretation, version, source, method, and limitation. Taxonomy categories alone do not imply formulas. |
| PA-005 | Missing data must never silently become zero. | Missing observations use a distinct neutral state. Interpolation or imputation requires a reviewed, documented method and visible labeling. |
| PA-006 | Provenance and uncertainty remain explicit. | Provider records, mappings, identity decisions, derived observations, and public status must preserve source and confidence information. Ambiguity enters review rather than being silently merged. |
| PA-007 | Map-first exploration is a core product principle. | Preserve the domain → field → time → world → country → institution → researcher path. Avoid flattening the experience into a ranking dashboard. |
| PA-008 | Geographic display and scientific attribution are separate layers. | Geometry defines an exploration canvas; institutional location metadata and temporal affiliations define scientific relationships. Multi-institution work is attributed to each supported affiliation rather than forced into single-country ownership. |
| PA-009 | Synthetic data is only for testing, development, and clearly labeled demonstration. | Synthetic entities and observations must never be represented as scientific evidence or silently inserted into provider-backed datasets. |
| PA-010 | Historical pilot datasets are retained for reproducibility. | Keep the bounded INSPIRE pilot, its provenance, and deterministic rebuild path even after live activation. It does not become the live corpus. |
| PA-011 | Synthetic, pilot, fixture-live, and provider-backed live datasets must not be silently mixed. | A source change replaces the repository boundary. Stored dataset provenance includes fixture/live identity, and mismatched writes fail. |
| PA-012 | The final normal public experience uses one integrated live dataset without requiring ordinary users to choose providers or development datasets. | Provider selection remains an operator concern. Remove the public source selector only after the integrated backend is operational and verified; preserve static repositories for offline and regression use. |
| PA-013 | Unvalidated live metric scores are not enabled. | The update engine may identify affected partitions, but it writes no scientific values until a reviewed calculator is supplied. A neutral map is preferable to a fabricated heatmap. |
| PA-014 | Identity resolution is authority-led, ambiguity-gated, and reversible. | Valid authority identifiers dominate; names and fuzzy evidence cannot silently merge ambiguous people or organizations. Preserve raw evidence and resolution history. |
| PA-015 | Affiliations are temporal relationships, not permanent ownership fields. | Researcher–institution and optional group relationships retain known time bounds and uncertainty. Provider affiliation evidence requires reviewed promotion rules. |
| PA-016 | PostgreSQL remains the current canonical relational graph store. | Do not introduce a separate graph database without demonstrated query or operational need. FastAPI exposes transport schemas, not raw ORM records. |
| PA-017 | Scientific providers are contacted only by backend connectors. | Browsers receive the integrated Atlas API contract and never hold provider secrets, rate-limit logic, or identity-resolution rules. |
| PA-018 | Production claims require operating evidence. | Deployment-ready code is not a live service. Verify HTTPS API reachability, CORS, database and worker health, update freshness, provenance, and frontend repository use before calling the Atlas live. |
| PA-019 | Acquisition scope is a versioned dataset boundary. | Provider filters belong in backend connector policy. Cursors, snapshots, and live-dataset provenance record that scope and fail closed on mismatch; changing configuration must not silently reinterpret or mix an older corpus. |
| PA-020 | A metric taxonomy entry, candidate method, and visualization-ready metric are distinct states. | Candidate definitions may be public methodology, but only observations that pass the documented input, cohort, sanity, and version gates may enter a live map or composite. |
| PA-021 | Normalized metric values must be reconstructable from preserved raw evidence and fitted parameters. | Retain the raw value/unit, exact cohort and transform, definition/algorithm/dataset versions, calculation time, scope, partition, input count, and quality flags; a method change emits a new version. |
| PA-022 | Identity quality is measured against independent review, not the resolver's own decisions. | Keep outcomes separate from review workflow, stratify deterministic samples, withhold precision/recall/calibration without enough labels, and append superseding decisions instead of rewriting history. |
| PA-023 | Public metric reads are bound to one current definition and immutable dataset lineage. | Exclude stale definition or dataset versions, choose the newest calculation only when the current rows agree on algorithm, and fail the partition closed when algorithms conflict. Apply the same rule to map and profile reads. |
| PA-024 | Scientific attribution is based primarily on paper-time affiliations. | Current homepages and profile affiliations cannot overwrite historical paper evidence. Preserve source snapshots, subunits, identity decisions, and versioned supersession; ambiguous, unresolved, or absent affiliations remain explicit. |
| PA-025 | Fractional Attribution v1 conserves one paper of evidence without claiming intellectual-contribution weights. | Divide equally among provider author slots and then among each author's effective paper-time affiliations unless a separately reviewed numeric policy exists. Keep unresolved mass withheld; author order and corresponding-author status do not alter the share. |
| PA-026 | Provider taxonomies remain separate from the versioned Atlas field ontology. | Preserve raw INSPIRE/arXiv categories and roles, map only through explicit versioned rules, allow multiple Atlas fields, and use equal unique-field shares when no reviewed unequal policy exists. Unmapped evidence stays unmapped. |
| PA-027 | Metric System v1 consists of exactly Activity, Impact, Connectivity, Diversity, and Momentum and activates only as one coherent system. | Reject partial production manifests. After global activation, an individual entity may still have a missing observation when its own evidence is insufficient; that absence does not disable the system or become zero. |
| PA-028 | Metric normalization is dimension-specific and Physics-wide aggregation occurs only after field-specific calculation and normalization. | Preserve raw values and fitted parameters. Do not pool raw publication or citation counts across fields; use an explicit versioned field-balanced, coverage-aware aggregation so large fields do not dominate by volume alone. |
| PA-029 | Metric Validation Thresholds v1 are versioned first-pass evidence gates, not scientific truth. | Count, coverage, maturity, complete-window, and cohort minimums can change only through a new documented configuration and review; passing them is necessary but not sufficient for activation. |
| PA-030 | The five-weight composite is a user-defined exploratory perspective, not an official score. | Require nonnegative weights totaling exactly 100% and explicit confirmation. Invalid drafts or missing components do not update the map, and no preset may be framed as a ranking or overall scientific value. |
| PA-031 | Reference research ecosystems are linked validation fixtures, not ranking ground truth. | Validate Paper ↔ Researcher ↔ paper-time Affiliation ↔ Institution relationships and reconstruction. Never tune metrics to force IAS, Princeton, Harvard, Caltech, UCSB/KITP, Stony Brook, Perimeter, or another anchor into a preferred order. |
| PA-032 | Paper-time affiliation evidence uses explicit cross-provider precedence: paper-native/INSPIRE evidence, then arXiv paper metadata, then dated ORCID affiliation as cross-checking evidence; current homepages are profile evidence only. | A lower-precedence or current-profile source cannot overwrite stronger historical paper-time evidence. Dated evidence may resolve a supported conflict; otherwise the affiliation remains unresolved. Physics Atlas never guesses. |
| PA-033 | Every materialized paper-field evidence ledger conserves exactly one unit: mapped canonical-field weights plus explicit unmapped mass. | Preserve provider primary/secondary evidence, apply a versioned configurable weighting policy only when justified, and otherwise divide mapped mass equally across unique mapped fields. A multi-field paper cannot contribute full weight to each field; unmapped mass is never silently reassigned. |
| PA-034 | The canonical public Physics Atlas frontend uses the dedicated `https://atlas.techecho.org/` hostname. | During migration, backend CORS may admit the legacy GitHub Pages origin and inherited `techecho.org` origin alongside the new hostname. Remove legacy origins only after DNS, Pages, HTTPS, redirects, and client-cache behavior are verified; changing this source repository alone is not evidence of a completed cutover. |
| PA-035 | ROR is the canonical institution authority; INSPIRE institution identifiers are cross-references, not replacement authorities. | Resolve an institution automatically only when reliable evidence reaches one ROR identity. Preserve historical subunits and source names. Eligible statistics self-roll or roll to one exact active canonical parent; missing/multiple parents, ineligible lifecycle states, and predecessor/successor relations remain withheld. An INSPIRE ID or name without a reliable ROR match remains unresolved rather than becoming a guessed institution. |
| PA-036 | Citation evidence is observed at an explicit reproducible UTC cutoff. | Record the cutoff, provider record, source snapshot, dataset/artifact checksum, raw count, and provider-reported non-self count. Use only evidence observable by that cutoff; never substitute a raw count for missing non-self evidence. A manifest-completion upper bound without source capture times is not a simultaneous observation. Impact cohorts compare compatible field, year, age, and document-type evidence and withhold immature or incomparable papers. |
| PA-037 | Field attribution review combines versioned multi-source evidence without forcing a single field. | Preserve arXiv, INSPIRE, and any already-integrated bibliographic or publisher evidence independently. Agreement can corroborate but does not itself constitute human review; conflicts may support conserved multi-field attribution or remain `needs_review`. Unmapped mass and source provenance stay explicit. |
| PA-038 | The bounded `hep-th-v1` corpus cannot validate production Diversity. | Diversity remains implemented but withheld until a reviewed broad-Physics evidence boundary exists. Because Metric System v1 activates jointly, this condition keeps Activity, Impact, Connectivity, Diversity, and Momentum jointly withheld for this trial even if another metric's evidence minimum passes. |
| PA-039 | Canonical paper identity uses strong identifiers in the order DOI, arXiv ID, then INSPIRE ID. | Exact normalized strong identifiers may join source occurrences while retaining every source lineage record. Without a shared strong identifier, an automatic merge requires the versioned conservative combination of normalized title, author overlap, year, and journal evidence; title alone never merges papers. Conflicting or insufficient evidence remains `needs_review`. |
| PA-040 | Joint Activation evidence explicitly classifies its acquisition boundary as `field-conditioned` or `broad-physics`. | Public Metric System v1 activation requires a reviewed `broad-physics` boundary and fails closed when the classification is absent or narrower. A named specialty field, or an unreviewed union of specialty trials, remains field-conditioned regardless of favorable coverage or metric results; such trials may validate methods but cannot by themselves activate public metrics. |
| PA-041 | Scientific evidence certification is an explicit, versioned boundary between canonicalization and metric calculation. | Raw provider presence, a mapped label, a resolved identifier, or a completed download never automatically becomes metric-eligible evidence. Calculators accept only a checksum-bound certified projection, while `needs_review`, `withheld`, `conflicted`, and `insufficient_evidence` remain explicit with their denominator mass and provenance. |
| PA-042 | The Normalized Atlas Scale is a separate 0–100 presentation layer over preserved scientific raw metrics. | Keep each raw value and unit, metric-specific normalization and fitted parameters, exact field/time/entity cohort, cutoff, certification digest, coverage, uncertainty, and missing reasons. `100` is a cohort-relative fitted upper position, not perfection; `0` is not proof of no research; missing never becomes zero. The five-weight composite remains user-defined and exploratory. |
| PA-043 | PostgreSQL stores canonical and queryable scientific state, not every immutable provider payload. | Keep canonical entities, relationships, compact citation/certification/review/metric state, cursors, and provenance references hot. Put raw pages, large snapshots, backfill bundles, and replay archives behind checksum-verifiable warm/cold artifact references. Do not delete existing production evidence until a verified migration and restore path exists. |
| PA-044 | Full Physics loading requires both the Scientific Evidence / Joint Metric Gate and `storage-budget-gate-v1`. | The storage gate uses measured physical capacity and a representative final-schema load bound to an exact target-population manifest. The target cannot be smaller than the sample, the projection cannot fall below the versioned deterministic estimate, and audit, projection, population, and typed isolated-restore attestations must be content-addressed and verified. Withhold when the contingency-adjusted steady state exceeds 60% of capacity or peak exceeds 80%. A failed gate first prompts hot-state reduction and cold externalization, not an automatic plan upgrade. Artifact integrity preserves the reviewed attestation; it is not proof that the underlying physical operation occurred. |
| PA-045 | An endpoint URL alone cannot make captured provider evidence “official.” | An official capture or enrichment manifest requires the internal live lineage-aware transport, exact approved endpoint, response status/timestamps, and checksum-bound stored bytes. Any injected transport remains fixture evidence even when configured with an official-looking URL. Changing certification semantics creates a new manifest/generator version; older outputs are explicitly superseded, never silently relabeled. |
| PA-046 | Certification integrity and scientific authority are separate trust requirements. | Typed content-addressed acquisition, population, authority, and review records bind exact inputs and reconstruction; they do not authenticate a reviewer or prove scientific completeness. The operating review process must authenticate approvals. The generic institution resolver automatically certifies direct ROR only; name, crosswalk, and context candidates require dated explicit review unless a dedicated adapter has verified the original authority-bearing provider response. Exact population membership cannot substitute for semantic review. |
| PA-047 | From 2026-09-05, Atlas Physica is the canonical public/product name, formerly Physics Atlas. Atlas Physica is developed and maintained by Tech Echo Collective. | Update current product text and display metadata without changing scientific semantics. Preserve historical release names/records, GitHub repositories, package/import/schema IDs, Railway services/databases, environment variables, deployment URLs/domains, serialized provenance, and existing release tags. Any technical rename requires separate authorization and compatibility review. |

## Current activation decision

The v3.0.4 production activation begins with the implemented `hep-th-v1`
corpus policy. INSPIRE-HEP and arXiv supply literature evidence; ROR refreshes
only reviewed, explicitly configured institution IDs; ORCID and Crossref are
queried only for already-known identifiers. The boundary is enforced in backend
connector, cursor, snapshot, and dataset policy rather than by presentation-layer
filtering.

Existing default cadence remains INSPIRE daily, arXiv daily, ROR weekly, with the worker checking due work hourly unless measured provider or operational evidence justifies a change.

## Initial v3.0.5 release scientific activation decision

At the initial v3.0.5 release, the five accepted base metrics had experimental
candidate-v1 contracts, but the then-observed `hep-th-v1` live dataset lacked
canonical institutions, affiliations, citation edges, geographic cohorts, and
multi-year canonical history. All five live layers were withheld. The later
September 4 audit records 15,838 paper-time affiliation shares but still zero
profile affiliation rows and canonical institutions; current factual counts
belong in `PROJECT_STATE.md` and the timestamped validation reports.
This remains an activation
result, not a redesign of the composite weighting model; synthetic and pilot
values remain confined to their isolated modes. A corpus-wide readiness count
cannot activate a layer: the exact entity type, field/domain, period, dataset
version, acquisition scope, update sequence, per-entity minimums, cohort, and
missing-data checks must be independently certified.

## Post-v3.0.5 Metric System v1 decision

The repository may implement and deterministically test all five metric
algorithms without publishing live observations. The scientific system is
versioned by `physics-atlas-metric-system-v1` and depends on
`fractional-attribution-v1`, `physics-field-ontology-v1`,
`provider-field-mapping-v1`, and `metric-validation-thresholds-v1`.

The system-wide activation manifest must name exactly the five accepted
definitions, matching algorithm/normalization/data versions, validated
attribution and field mapping, sufficient coverage and history, and passing
reproduction evidence. It fails closed if any required evidence is missing or
incompatible. Passing code tests does not itself satisfy scientific review, and
the current `hep-th-v1` production evidence does not pass this gate. All five
live layers therefore remain jointly withheld; no source-level implementation
change authorizes a production migration, backfill, recalculation, or public
activation by itself.
