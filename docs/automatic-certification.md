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
| Citation population | All records from one exact, complete INSPIRE query response; up to 1,000 records/six query years; exact count/cutoff/membership | Pagination without a shared snapshot; completeness of a different canonical publication-year population |
| Acquisition plan | Reconstruct supported scope/year partitions from existing registry | Successful acquisition, canonical-year completeness or missing date/identity facts |
| Metric population | Derive all entity×field projections from an already certified window, including excluded/unresolved mass | A source window that has not passed its structural and coverage checks |
| Category universe | Derive all applicable leaves from the frozen Physics ontology | Unspecified subfields below a leaf or a caller-selected favorable subset |
| Normalization population | Bind every represented peer and its reconstructable calculation to the same certified window | The required eligible peer count, or a valid raw value for a sparse peer |

These are typed adapters at existing boundaries, not a replacement certification
framework. Validators rerun derivation; fabricated review names/flags, missing
members, changed source facts, versions, dates or calculations fail closed.
Legacy reviewed records remain readable with their original content hashes.
Record-level date/researcher assessments are not yet sufficient to admit an
entire production metric partition. The production worker and Joint Activation
publisher are not switched by these adapters.

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

For a larger population, a bounded measurement-session policy could preserve
actual response timestamps and temporal uncertainty. That policy is **not
implemented**: no arbitrary timing tolerance or “as-of” provider snapshot has
been invented. The inspected official contract did not document a historical
snapshot token; that is not evidence that none can exist.

## Remaining launch requirements

- Complete certified metric-year windows: three years for Activity/Impact/
  Connectivity/Diversity; six for backward-looking Momentum.
- Existing 90% affiliation, 95% canonical institution, 90% field and 90%
  comparable citation coverage against full relevant denominators.
- At least 50 papers in each mature Impact reference cohort; at least 30
  eligible peers for Activity/Impact/Momentum normalization.
- The existing Physics-domain aggregation fixes 16 ontology leaves and 90%
  field coverage (at least 15 leaves). A narrow field slice must not be relabeled
  as global Physics; unsupported domain cells remain neutral.
- Complete transport-bound automatic date/researcher admission, eligible real
  populations, exact-five activation evidence and the v1 production export adapter.
  `NoFormulaMetricRecalculator` still writes no live scores; the pilot exporter
  must not be relabeled as a v1 scientific dataset.

Passing adapter tests does not satisfy these data requirements. No public metric
activation, fabricated historical observation, broad load or v3.1 follows from
this change. Public API failure must show unavailable/neutral, never substitute
synthetic observations. Temporary work stays in one <2 GB directory and is
removed after validation; no legacy evidence is a prerequisite for this work.
