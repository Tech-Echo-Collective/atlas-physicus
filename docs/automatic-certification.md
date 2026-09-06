# Evidence-derived automatic certification

Policy: PA-054, 2026-09-05. Mandatory human review is removed, not scientific
verification. No single method is universally “most scientific”; the implemented
choice is a conservative, reproducible assessment with explicit evidence limits.
Metric System v1 formulas, thresholds and historical decision hashes are unchanged.

## Implemented boundaries

| Boundary | Automatic evidence | Still not proved by that evidence |
| --- | --- | --- |
| Field | Reconstruct the selected, versioned provider ledger; exact leaf mappings and conserved mass | An unmapped label or broad branch is not an invented leaf; scope is not broad Physics merely because mapping succeeded |
| Date | Explicit provider/source field; same-basis dates reconciled with precision retained | Mixed `earliest_date`, ingestion/update time, unknown day, or a preprint date relabeled as journal publication |
| Researcher | Paper-native INSPIRE-author/valid ORCID identifiers; conflicting IDs rejected | Name-only global identity, career history, or paper-time affiliation |
| Institution | Exact provider-to-ROR authority linkage, or the strict source-bound PA-057 affiliation cross-check | A suggested ROR ID/name without corroboration, current employment substituted for paper-time evidence, or guessed lifecycle/parent resolution |
| Citation population | Complete single response, or PA-055 measured batches bound to independently certified frozen membership | An atomic provider snapshot, historical as-of counts, or canonical-year completeness derived merely from pagination |
| Acquisition plan | Reconstruct supported scope/year partitions from existing registry | Successful acquisition, canonical-year completeness or missing date/identity facts |
| Metric population | Derive all entity×field projections from an already certified window, including excluded/unresolved mass | A source window that has not passed its structural and coverage checks |
| Category universe | Derive all applicable leaves from the frozen Physics ontology | Unspecified subfields below a leaf or a caller-selected favorable subset |
| Normalization population | Bind every represented peer and its reconstructable calculation to the same certified window | The required eligible peer count, or a valid raw value for a sparse peer |

These are typed adapters at existing boundaries, not a replacement certification
framework. Validators rerun derivation; fabricated review names/flags, missing
members, changed source facts, versions, dates or calculations fail closed.
Legacy reviewed records remain readable with their original content hashes.
Typed date/researcher decisions now bind the consumed paper projection back to
its exact source occurrence and declared date basis. They remain individual
evidence decisions, not certification of an entire production metric partition.
The production worker and Joint Activation publisher are not switched by these
adapters.

## Source-bound paper facts

`source-bound-paper-facts-v1` extracts compact date and identity facts from the
existing parsed `SourceRecord`, verifying provider, record ID, snapshot and
content checksum. `declared-date-basis-assessment-v1` uses the selected exact
source field; the bounded launch explicitly uses INSPIRE `preprint_date`, not
`earliest_date` or a journal-date substitution. Date decisions must bind every
source-year occurrence and the same basis across the metric window.

`paper-native-identifier-assessment-v1` retains the complete author-position
inventory and exact native INSPIRE author identifiers, with valid co-asserted
ORCIDs as evidence rather than name-based merges. Repeated native identities
across positions, conflicting identifiers within an appearance, or one ORCID
asserted for different native identities fail closed. The consumed researcher
inventory must reconstruct from these facts; a caller-provided successful state
or copied rule string is insufficient. Unknown or conflicted people are not
merged to make coverage pass.

## Partial field evidence: conservation is not completeness

PA-033 already permits `Σ mapped weights + explicit unmapped mass = 1`.
A conserved partial ledger can prove its accounting and support its positive
known leaf contributions without certifying the unknown remainder. Its metric
population retains the existing conservative denominator:

```text
known contribution = entity share × known field weight
possible contribution = (entity share + unresolved entity mass)
                      × (known field weight + unmapped field mass)
```

The narrow integration separates source-year structural conservation, a
particular known-field projection, and field coverage. The projection adapter
`conserved-known-field-projection-v1` must not turn a partial paper into a full
unit of certified field evidence. Coverage must reconstruct its known/unmapped
mass against the complete declared denominator and retain the existing 90%
minimum. The older whole-paper binary coverage path and historical hashes stay
unchanged. Unknown labels remain unmapped; this change adds no ontology labels,
provider mapping rules or inference from embedded cross-provider metadata.

This completion is under focused integration validation; the measured 250-record
example in the [bounded report](validation/minimum-launch-integration-2026-09-06.md)
is not a certified year or a passed activation gate.

## Paper-native ROR cross-check (PA-057)

`paper-native-ror-affiliation-crosscheck-v1` consumes an exact paper/author/raw-
affiliation slot and the official ROR affiliation response. The request must
encode that exact text; response bytes, snapshot, checksum, HTTP status and real
timestamps are bound before matching. The adapter performs no network access or
payload persistence. Trusted acquisition supplies provider origin.

Admission requires all of the following:

- One `chosen: true` candidate, active and compatible with existing ROR lifecycle
  and parent rules. Numeric match score is not a scientific threshold.
- A whole institutional label/alias clause, excluding acronym-only matches;
  no fuzzy matching, transliteration or guessed abbreviations.
- Exact country corroboration, plus exact city agreement when a city is supplied.
  Bare institution names remain unresolved; country-only evidence invents no city.
- No competing organization or unexplained address/subunit content. A small
  full-match subunit grammar may accept “Department of Physics”; an open prefix
  such as “Department of Physics at Other University” is not sufficient.
- No inactive, post-paper establishment, predecessor/successor or unsupported
  parent inference. The existing institution validator remains in control.

Output retains compact source/response references, observed matching facts,
reason/state and a distinct method/version; it does not claim the paper itself
asserted a ROR identifier. Neither current profile affiliation nor invented human
approval is used. Unresolved cases retain their attribution mass. Responses are
bounded to 8 MiB/100 candidates; complex legitimate affiliations can be withheld
by this intentionally conservative parser.

ROR recommends `chosen` for automatic matching but warns that results can be
incorrect. This adapter adds the explicit corroboration above instead of treating
a suggestion as identity. [ROR affiliation API](https://ror.readme.io/docs/api-affiliation),
[ROR matching guidance](https://ror.readme.io/docs/matching).

### Exact identity is not an implicit parent rollup (PA-058)

The bounded launch has an opt-in exact-ROR granularity path. A reliably
identified active organization with its own ROR ID can retain that identity even
when ROR records a parent relationship. Parent edges remain provenance; they do
not automatically substitute a parent ID, duplicate paper attribution or confer
parent-level metric credit. The legacy rollup behavior remains unchanged unless
the caller explicitly selects this versioned path. Unsupported identity, lifecycle
and historical evidence still fail closed.

This separates direct identity from a requested aggregation operation. It does
not recognize arbitrary departments as independent organizations or relax ROR
authority requirements. The dataset must disclose its institution granularity;
any later parent aggregation needs its own supported policy/evidence. Focused
regressions pass; the same 250-paper remeasurement increased canonical mass from
49.139% to 67.354%, still below 95%. This is not whole-year coverage or activation.
See the [timestamped measurements](validation/minimum-launch-integration-2026-09-06.md).
[ROR registry scope](https://ror.org/registry/),
[ROR scope guidance](https://ror.org/blog/2026-06-24-three-tips-for-requesting-ror-id/).

## Dates and historical meaning

arXiv documents `published` as the first version's submission/processing time
and `updated` as the latest revision; neither is a journal-publication assertion.
The adapter keeps that distinct basis. [arXiv API manual](https://info.arxiv.org/help/api/user-manual.html).

An exact same-basis date can support the declared metric time axis. A year/month
retains an interval; the code does not invent January 1 or a first day of month.
Choosing the minimum across preprint and journal dates is not a date policy.
The citation adapter no longer uses the existing normalizer's mixed
`earliest_date` as proof of an exact date. Existing source records are not rewritten.

Current citation counts can describe “2020–2022 publications, measured at the
declared 2026 cutoff.” They cannot describe citations known in 2022 without
historical evidence. Separate publication periods and later citation cutoffs
are established bibliometric practice; equal citation age improves comparisons
over time. [CWTS indicators](https://traditional.leidenranking.com/information/indicators).

## Citation comparability

INSPIRE documents raw and non-self counts and bounded search responses. Use the
provider-reported non-self count, not raw count substitution. A small in-memory
capability check returned both fields; that is not a certified cohort.
[INSPIRE REST API](https://github.com/inspirehep/rest-api-doc),
[provider citation methodology](https://help.inspirehep.net/knowledge-base/citation-metrics/).

The implemented path derives every annual cohort from the **same complete
response**, so it does not fake cross-request simultaneity. It retains compact
irrecoverable citation facts and response/record hashes, not a raw payload mirror.
The ≥50-reference-paper and 24-month maturity rules remain. The whole query must
fit the bound; truncating an over-limit response or dropping unknown membership
to make it fit is rejected. A complete provider earliest-date query does not
certify a canonical journal-publication population.

### Versioned measurement window (PA-055)

The owner subsequently authorized an opt-in alternative to the single-response
path. `non-self-citation-measurement-window-v1` preserves the real measurement
interval and every batch's request/response times. It does not weaken the old
contract by assigning different responses one fabricated cutoff.

1. Independently certify canonical source years; freeze exact INSPIRE-to-paper
   identities before requesting citation counts. Keep unsupported identities in
   the scientific denominator as missing, not silently removed or zero.
2. Request bounded exact-ID batches; verify exact membership, no duplicate or
   missing records, unchanged date/field facts and actual monotonic timestamps.
   A transport-level pagination mode also exists, but cannot supply its own
   canonical population authority. Stable totals and successful page traversal
   alone never establish a snapshot.
3. Bind annual field/document cohorts to that same session and frozen scientific
   population. Check maturity at each actual observation time and retain the
   unchanged 50-paper reference and 30-peer normalization minima.
4. Retain compact counts, membership, response hashes, exact time interval and
   source/policy versions. Those observed counts—not a promise to re-query a
   mutable service—support later exact formula reproduction. Checksums alone
   cannot reconstruct discarded raw provider bytes.
5. Keep distinct sessions out of the same normalization or domain aggregation.
   Report an interval, never a singular citation cutoff, for this variant.

The 30-minute maximum is an operational session bound, **not** a scientifically
calibrated drift tolerance or simultaneity claim. A long, changed, interrupted or
incomplete session fails closed; silently extending the bound is not allowed.
The result means “publications from the stated years, citations measured during
this later interval.” It does not mean citations known in those historical years.

INSPIRE documents record-ID queries and bounded responses, supporting exact-ID
batching. [Official API contract](https://github.com/inspirehep/rest-api-doc).
Recording activity start/end separately follows standard provenance semantics.
[W3C PROV](https://www.w3.org/TR/prov-dm/).
Mutable pagination can change membership between requests; this is why captured
membership is checked against an independently frozen inventory rather than
equated with a provider snapshot.
[OAI-PMH protocol](https://www.openarchives.org/OAI/2.0/openarchivesprotocol.2003-02-21.htm).
The inspected INSPIRE contract did not document a historical snapshot token;
that is not evidence that none can exist.

## Remaining launch requirements

The existing per-entity coverage denominator is a worst-case possible-mass
bound: unresolved global entity mass can belong to each candidate entity. It is
not the same quantity as measured source-wide coverage. The new fractional
source-year adapter does not alter this old rule or silently remove unknowns.
Separating observed evidence coverage from retained uncertainty bounds is a
pending policy question, not an authorized or implemented gate change.

- Complete certified metric-year windows: three years for Activity/Impact/
  Connectivity/Diversity; six for backward-looking Momentum.
- Existing 90% affiliation, 95% canonical institution, 90% field and 90%
  comparable citation coverage against full relevant denominators.
- At least 50 papers in each mature Impact reference cohort; at least 30
  eligible peers for Activity/Impact/Momentum normalization.
- The existing Physics-domain aggregation fixes 16 ontology leaves and 90%
  field coverage (at least 15 leaves). A narrow field slice must not be relabeled
  as global Physics; unsupported domain cells remain neutral.
- Under PA-056, the opt-in `certified-ontology-branch-release-v1` may release a
  genuinely certified branch/entity/period with all five metrics together; it
  does not claim broad Physics or invent categories below a leaf. The bounded
  2018–2023 recipe can first support Momentum in terminal 2023. Other periods
  remain missing unless their own complete windows exist.
- Eligible real populations, exact-five activation evidence and validated compact
  export/deployment remain necessary after individual automatic admission.
  `NoFormulaMetricRecalculator` still writes no live scores; the pilot exporter
  must not be relabeled as a v1 scientific dataset.

Passing adapter tests does not satisfy these data requirements. No public metric
activation, fabricated historical observation, broad load or v3.1 follows from
this change. Public API failure must show unavailable/neutral, never substitute
synthetic observations. Temporary work stays in one <2 GB directory and is
removed after validation; no legacy evidence is a prerequisite for this work.
