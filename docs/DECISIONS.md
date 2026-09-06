# Atlas Physicus durable decisions

Last reviewed: 2026-09-06

These decisions constrain implementation and public communication. Add a dated superseding entry when a durable decision changes; do not silently rewrite project history.

Earlier entries retain the historical name Physics Atlas; their scientific and
architectural constraints continue to apply to Atlas Physicus.

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
| PA-048 | From 2026-09-05, the nominal approximately 5 GB budget applies to all persistent Atlas Physica data combined, not PostgreSQL alone. | Count hot DB, warm/cold archives, required historical/citation state, provenance/restore metadata and retained backups/replicas/copies once each. Moving bytes is not total savings without a smaller recoverable representation. External-store capacity/cost is separate, not free or an implied budget increase. Distinguish ephemeral processing/peaks from retained history. Preserve PA-044's 25% contingency and 60% steady/80% peak headroom alongside actual per-volume constraints; unknown required costs withhold a future capacity approval. Existing volume-only reports remain historical evidence and cannot establish a total-storage PASS. No data deletion or policy relaxation follows from this budget rule. |

## Local artifact identity and authority — 2026-09-05

**PA-049:** Local certification artifact identity binds type, schema version and
original-content SHA-256 independently of storage location. A separately pinned,
versioned descriptor selects one exact authoritative representation. Historical
manifests remain immutable and resolve through an explicit compatibility adapter;
missing/corrupt selected authority fails closed without silent fallback. Verified
archive recovery does not grant scientific certification, production migration or
automatic original-retirement permission. The initial implementation is limited
to the corrected decision-ledger contract; see the
[resolver proof](validation/artifact-resolver-2026-09-05.md).

## Project-family naming — 2026-09-05

**PA-050:** Atlas Physicus is the canonical product name within **Tech Echo
Physica**, alongside Illuminatio Physica and Theatrum Physicum. This supersedes
the naming portion of PA-047. The primary GitHub repository and frontend package
are `atlas-physicus`; current source links use that identifier. Preserve historical
release records, scientific provenance/schema/artifact identifiers, installed
backend package/import/CLI names, service/database/volume/environment identifiers,
and production API URLs to avoid breaking operated integrations. The separate
Web deployment remains independently versioned and pins an exact source commit.
See the [deployment compatibility audit](production-deployment.md#naming-and-deployment-compatibility).

## Validation artifacts do not scale with the corpus — 2026-09-05

**PA-051:** Full-scale ingestion must not generate full-corpus paired, rollback,
recovery, restore, or comparison ledgers. These are bounded validation artifacts
only. Only necessary compact authoritative certification state may scale with
the corpus; expanded A/B scientific traces are not production per-paper state.
Validate each pipeline version against an explicitly bounded representative
sample, preserving its inputs/versions, exact hashes, equivalence/failure results
and required provenance. Do not subdivide a full corpus into repeated proof runs
to evade this boundary. Runtime refusal and operational sample/decision/byte caps
do not change scientific thresholds or confer activation/capacity approval.
Existing historical artifacts remain valid and retained; separately authorized
exact restoration of one authoritative archive is not new trace generation.
This also excludes full-corpus verbose provider comparisons and researcher
replay A/B traces. Necessary source/history state still counts toward PA-048;
the absence of comparison ledgers does not prove a compact production layout.
See the [storage contract](storage-architecture.md#validation-artifact-scaling-contract)
and [implementation audit](validation/validation-ledger-scaling-safety-2026-09-05.md).

## Reusable validation and cumulative retention — 2026-09-05

**PA-052:** Reuse the pinned `bounded-cross-track-validation-sample-v1`
(`5f520b2a…`, 1,000 source-scoped paper references) for pipeline-version proof.
Replacement requires a documented domain/evidence expansion; do not silently
resample, combine scientific denominators or shard the corpus into proof jobs.
Keep PA-051's per-trace limits and cap cumulative retained validation outputs at
**1 GiB**, optionally stricter, within PA-048's combined 5 GB budget. Count all
physical copies, archives, prior versions, metadata and REVIEW files. Classify
KEEP / COMPRESS-ARCHIVE / REGENERABLE / RETIRE_CANDIDATE / REVIEW without automatic
deletion or subtracting prospective savings. Before each new proof version, bind
a complete fresh inventory, sample, code/version, proof plan and byte reservation.

Only necessary compact authoritative paper-time affiliation state may scale with
production ingestion. Expanded affiliation validation/replay outputs must remain
bounded, sampled, ephemeral or archived, never default per-corpus ingestion output.
Historical schema/path dependencies remain valid: exact duplicate content alone
does not authorize retirement. This is an operational storage policy, not a
change to attribution, certification or activation thresholds. The new pilot
enforces admission; old standalone validation commands still require operator
admission, not a claimed universal filesystem quota. See the
[audit and sample pins](validation/affiliation-retention-2026-09-05.md).

## Historical affiliation archive authority — 2026-09-05

**PA-053:** Extend PA-049's existing logical artifact resolver to explicitly
versioned historical affiliation artifacts, not a second authority framework.
Identity includes artifact type, schema version and exact content SHA-256.
Multiple historical paths may bind one identical logical artifact only when each
immutable manifest/path/hash/size/row binding is verified independently.
An additive local authority index selects the retained representation; it does
not rewrite historical manifests, scientific provenance or attribution decisions.
Missing or invalid selected authority fails closed without inline fallback.

The [final bounded storage review](validation/final-storage-consolidation-2026-09-05.md)
does not extend this whitelist. A recoverable generic artifact reference is not
historical path authority for provider, researcher or other replay schemas.
Unsupported bindings remain NO-GO; do not invent acquisition metadata, increase
global payload limits or rewrite historical manifests to obtain retirement.

Retirement requires original-absent recovery, exact bytes, scientific-input and
provenance equivalence, current-reader compatibility, reviewed dependencies and
available restore scratch. Historical as-of scripts may use an isolated exactly
restored tree without changing their recorded inputs. Archive creation/adoption
is development/test-only. Existing PA-051/052 production and proof-budget limits
remain unchanged; local archive authority is not independent-backup durability,
scientific certification, production migration or Full Physics authorization.
See the [affiliation batch](validation/affiliation-archive-batch-2026-09-05.md).

## Evidence-derived automatic certification — 2026-09-05

**PA-054:** The owner explicitly removed mandatory human review for the
lightweight launch. A versioned deterministic assessment may certify evidence
when it reconstructs the decision from explicit source facts and the existing
scientific requirements. It must not invent a reviewer, replace an assessment
with an approval boolean, treat a name match as identity, or infer missing facts.
Human review remains optional for genuine ambiguity, not a prerequisite for
mechanically verifiable evidence. Legacy `needs_review` may still describe an
unresolved machine assessment; it does not create an obligation to hire a reviewer.

This supersedes only the mandatory-human portions of PA-037/038/040/046 and
related methodology prose. It does not supersede broad-versus-conditioned
acquisition semantics, authority requirements, formulas, numerical thresholds,
complete denominators, conservation, citation maturity/cutoff, or exact-five
activation. Historical decisions and digests remain unchanged. Unsupported
automatic paths fail closed; this decision is not itself a passed activation gate.

Metric dates have an explicit source-field basis: preprint submission, journal
online publication and print publication are distinct. Mixed provider
`earliest_date`, record update times, and invented days cannot establish exact
publication timing. Historical citation impact measured now is retrospective,
not a reconstruction of citations known in the historical year. Separate response
times may not be relabeled as one cutoff. Keep compact observed counts, source
references, population membership, actual acquisition time and rule versions;
no new provider mirror or verbose decision ledger is required.

Implementation and primary-source rationale:
[automatic certification](automatic-certification.md). All public metrics remain
withheld until the complete certified calculation and activation chain passes.

## Versioned citation measurement windows — 2026-09-05

**PA-055:** The owner explicitly authorized finite, versioned citation measurement
windows after reviewing the multi-response limitation. The opt-in policy is
`non-self-citation-measurement-window-v1`, with transport contract
`citation-measurement-window-v1`. This changes citation observation semantics,
not Metric System v1 formulas or numerical scientific thresholds.

Freeze exact paper/provider identities from independently certified canonical
source years **before** measuring citations. Prefer explicit-ID batches and
require every frozen measurable identity exactly once; unexpected, omitted,
duplicate or conflicting identities fail closed. Papers without supported
provider identities remain explicit missing evidence in the full scientific
coverage denominators. Neither a frozen ID list nor stable pagination totals
proves an atomic provider snapshot or certifies a canonical year.

Retain actual request/response times, interval start/end, source references,
counts, population membership and rule versions. A session is capped at 30
minutes as a versioned operational bound, **not** an empirically established
scientific tolerance or an assertion of negligible citation drift. Label the
result retrospective measurement; do not call it historical as-of evidence.
Keep measured compact counts because a later mutable provider query cannot
reproduce those past counts from checksums alone.

All compared cohorts and normalization peers must share the exact session,
frozen scientific population and policy. Point-cutoff and interval evidence
cannot mix. Existing 24-month maturity is checked at each actual response time;
50-paper reference, 30-peer normalization and all coverage gates remain intact.
Partial-year, missing, unresolved and zero distinctions are unchanged. Legacy
single-cutoff contracts and historical digests remain valid under their old
version. This authorization does not activate metrics or certify any live data.
See [the method](automatic-certification.md#versioned-measurement-window-pa-055)
and [bounded validation](validation/citation-measurement-window-2026-09-05.md).

## Explicitly limited five-metric launch — 2026-09-06

**PA-056:** The owner authorized the first scientifically certified field/year/
entity slice without requiring Full Physics completeness. The opt-in boundary
`certified-ontology-branch-release-v1` may publish an explicitly named existing
ontology branch, provided the exact Joint Gate and all five current metrics pass
on compatible certified evidence. This supersedes only the broad-Physics-only
public-launch restriction of PA-038/040 for this explicit scoped variant. The
existing broad-Physics/default activation path is unchanged.

The first bounded recipe is `nuclear-physics-launch-v1`: INSPIRE articles with
Theory-Nucl or Experiment-Nucl evidence and exact `preprint_date` calendar years
2018–2023. Its fixed branch contains `nucl-th` and `nucl-ex`; it is not broad
Physics. A recipe or reconciled retrieval is not a certified complete year or
an atomic provider snapshot. Public activation still requires certified source
years, populations, comparable citation evidence, normalization and exact-five
observations sharing the same branch/entity/period. Unsupported fields, entities
and periods remain missing; favorable results from incompatible scopes cannot
be assembled into one passing system.

Branch Diversity uses the entire existing descendant leaf catalog. For branch
mass `B = Σ descendant field weights`, its within-branch shares are `w/B`;
effective contributions remain `(entity share × B) × (w/B) = entity share × w`.
Outside-branch and unmapped mass is retained, not reassigned. This is the existing
normalized Shannon metric on a declared branch, not a new formula, invented leaf
subfields or an average of leaf Diversity values. Historical Momentum remains
backward-looking: six certified years 2018–2023 can support terminal 2023, not
six fabricated Momentum observations. All numerical thresholds remain unchanged.

## Paper-native ROR affiliation cross-check — 2026-09-06

**PA-057:** `paper-native-ror-affiliation-crosscheck-v1` is a dedicated automatic
adapter under PA-054/046, not permission for generic name-only institution
matching. It binds an exact dated INSPIRE paper, author/raw-affiliation slot,
original text, official ROR affiliation request, response checksum and actual
request/response times. Trusted acquisition must establish provider origin;
an official-looking URL or a checksum alone does not authenticate evidence.

Admission requires one official `chosen: true` candidate, a whole institutional
label/alias match excluding acronym-only matches, and mandatory exact country
corroboration. A supplied city must also agree; a country-only source does not
invent a city. Only explicitly recognized simple subunit/address clauses may
remain. Multiple organizations, contradictory or unclassified geographic text,
unknown prefixes, inactive identities, unsupported parent rollups and historical
predecessor/successor ambiguity remain unresolved. Current employment or a
homepage never replaces paper-time affiliation, and no reviewer is fabricated.

The existing ROR lifecycle/parent validator remains authoritative. The resulting
match records this distinct cross-check method, not a claim that the original
paper directly supplied a ROR ID. ROR choice or numeric score alone is insufficient;
unresolved mass remains in the unchanged coverage denominator. Bounded positive
checks are not population-wide precision, 95% canonical coverage or activation.
See [method and limits](automatic-certification.md#paper-native-ror-cross-check-pa-057)
and [the bounded observations](validation/minimum-launch-integration-2026-09-06.md).

## Exact ROR identity versus parent aggregation — 2026-09-06

**PA-058:** The bounded launch may opt into retaining an exact active ROR
organization as the canonical institution, without interpreting every ROR parent
relationship as a request to aggregate into that parent. ROR describes organizations
with their own ROR IDs as independently identifiable, while ordinary internal
departments generally do not receive separate IDs. A parent edge alone therefore
does not invalidate an otherwise supported direct identity.

This is a narrow identity/granularity correction under the owner's minimum-needed
launch authorization. The existing resolver's parent-rollup behavior remains the
legacy default. The opt-in path must retain the exact selected ROR ID and all parent
references as provenance; it must not substitute, invent or automatically credit a
parent. Missing/ambiguous ROR links, conflicting identifiers, inactive identities
and unresolved historical lifecycle evidence remain withheld. Paper-time affiliation,
fractional attribution and all metric formulas/thresholds are unchanged; the same
paper must not be credited again through an automatic parent aggregation.

The versioned dataset must disclose the retained entity granularity. A separate
rollup requires an explicit supported policy and authority evidence, not this
identity option. Coverage must be remeasured after validation; the pre-fix sample
is not evidence that the corrected path passes the 95% gate.
[ROR registry scope](https://ror.org/registry/),
[ROR organizational scope guidance](https://ror.org/blog/2026-06-24-three-tips-for-requesting-ror-id/).

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
