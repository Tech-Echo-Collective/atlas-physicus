# Scientific Evidence Certification v1

Status: implemented as a staging-safe, fail-closed foundation

Policy version: `scientific-evidence-certification-v1`
Last reviewed: 2026-09-05

Metric System v1 formulas do not consume raw provider presence directly. The
required boundary is:

```text
Provider Evidence
  -> Normalize
  -> Canonicalize
  -> Evidence Certification
  -> Metric-Eligible Evidence
  -> Raw Metrics
  -> Metric-specific normalization
  -> Normalized Atlas Scale [0,100]
  -> Joint Activation Gate
  -> Heatmap
```

Certification is an overlay on immutable evidence. It does not rewrite a
provider row, resolve an ambiguity by optimism, or turn a downloaded partition
into a scientific result.

## States

Every decision is bound to one subject and evidence dimension with its input
digest, dataset/scope and policy versions, source references, and reason codes.
When a human review is part of the decision, reviewer identity and a
timezone-aware review timestamp are retained together.

| State | Meaning |
| --- | --- |
| `certified` | Eligible for the explicitly declared purpose under the exact rule and versions. |
| `needs_review` | Plausible evidence exists but a reviewed decision is required. |
| `withheld` | Known evidence is excluded by policy or scope, such as a partial calendar year. |
| `conflicted` | Incompatible evidence remains unresolved. |
| `insufficient_evidence` | A required fact is absent or cannot be verified. |

The independently evaluated dimensions are canonical paper identity,
publication/metric date, researcher identity, paper-time affiliation,
canonical institution, field classification, field-weight conservation,
citation observation, citation-cutoff compatibility, collaboration
relationships, and provenance completeness. One paper can be certified for
identity while its affiliation or citation evidence remains unresolved.

Certification decisions and manifests are content-addressed. A stale,
superseded, scope-incompatible, or digest-mismatched decision is not accepted
by the metric boundary. Exclusion reasons and unresolved denominator mass stay
in the certification report rather than being silently filtered by a formula.

## Institution decisions

Institution certification follows the existing ROR authority policy:

1. a valid direct ROR authority identifier whose exact authority registry is
   bound to the decision;
2. provider crosswalk, canonical/alias/historical-name, and contextual evidence
   generate authority-backed candidates; the generic resolver requires dated,
   explicit approval before promoting any of these candidates;
3. a subunit rollup only through one exact active canonical parent when the
   authority record explicitly marks the relation eligible for rollup, or a
   dated human review approves that exact parent;
4. context evidence may create a review candidate but not an automatic fuzzy
   match;
5. absent, multiple, inactive, predecessor/successor, or conflicting matches
   remain `needs_review`, `conflicted`, or `insufficient_evidence`.

The generic resolver automatically certifies direct ROR evidence only. A
unique name in a caller-supplied subset is not proof of global uniqueness, and
an arbitrary crosswalk is not an authority assertion. The paired adapter may
project a direct ROR identifier from the exact INSPIRE institution response
only after verifying its content-addressed enrichment lineage. It performs no
name search. The authority registry digest binds the records used; it does not
authenticate their origin or prove that a submitted registry is complete.

Paper-time affiliation, source name, subunit evidence, ROR identity,
provenance, confidence, and review state are retained separately. The resolver
does not guess to improve coverage.

## Field decisions

Raw arXiv, INSPIRE, Crossref, and other already-integrated provider labels,
roles, abstracts, and keywords remain separate evidence. A versioned Atlas
mapping can support review, but provider agreement is not itself a reviewed
classification. Disagreement is retained and may result in conserved
multi-field weights or an unresolved decision.

Each complete selected ledger must satisfy:

```text
sum(mapped Atlas-field weights) + explicit unmapped mass = 1
```

within the existing numerical tolerance. A paper counts as field-certified
only when the whole selected ledger has a reviewed decision. Certified mapped
and unmapped mass remains separate in the ledger artifact and may be reported,
so an incompletely mapped ledger cannot inflate coverage.

## Citation decisions

A certified citation observation binds the canonical paper, source and source
record, immutable snapshot/page checksum, provider-reported raw and non-self
counts, response observation timestamp, explicit cutoff semantics, publication
year, document type, field/year/age cohort, maturity result, policy versions,
and provenance digest.

A raw count never substitutes for a missing provider-reported non-self count.
Impact compares only compatible observations at one demonstrable common cutoff
with the existing minimum cohort and 24-month maturity rules. A legacy
manifest-completion upper bound without page response timestamps is not a
common-cutoff observation. No tolerance for multi-page response times has been
approved, so a multi-page cohort remains withheld unless the provider supplies
snapshot semantics or a future reviewed policy explicitly defines one.

## Certified source years and metric windows

A source year is certified only when all applicable conditions hold:

1. the year is closed (`year < cutoff.year`);
2. every declared provider partition completed without truncation or missing
   pages;
3. expected, observed, and unique record counts reconcile;
4. every retained provider page checksum verifies and every provider record is
   accounted for by the record-to-page occurrence inventory;
5. canonical paper identity, metric date/year, and provenance cover the full
   eligible universe with no unaccounted structural mass;
6. every selected paper-field ledger conserves one unit;
7. the existing Metric Validation Thresholds v1 are met against full eligible
   denominators: field 90%; paper-time affiliation 90% and canonical institution
   95% when geographic attribution is required; citation comparability 90% for
   Impact; relationship resolution 90% for Connectivity;
8. dataset, scope, attribution, ontology, mapping, citation, threshold, and
   certification versions are compatible.

Provider download completion alone does not certify a year. Entity and cohort
sample-size minimums remain metric readiness checks rather than being
misrepresented as source-year completeness.

Metric windows are derived from certified source years:

- Activity, Connectivity, and Diversity require `t-2...t`;
- Impact requires those three source years plus mature common-cutoff cohorts;
- Momentum requires `t-5...t`, with both adjacent three-year Activity windows
  independently eligible and version-compatible.

The source-year acquisition plan explicitly names all required provider
partitions. Typed paper projections bind canonical dates, every provider
occurrence, conserved field shares, entity shares, and unresolved mass. The
metric population then enumerates the exact entity/field universe for the
window, including exclusions and their mass. A calculator cannot substitute a
favorable subset or count an unlisted paper. Structural completeness and
scientific review are separate: exact enumeration does not establish that an
affiliation, identity, or field assignment is correct.

Impact coverage uses the actual mature members of certified compatible
common-cutoff cohorts. A paper with a citation count but without membership in
that exact cohort contributes no comparable citation mass. Diversity requires
a reviewed category-universe proof bound to the current ontology; callers
cannot choose an arbitrary smaller category set to improve evenness.

## Trust and review boundary

The typed certification contracts validate content, version compatibility,
denominators, and reconstruction. Acquisition plans, eligibility populations,
normalization populations, authority records, and review approvals are
operator-supplied attestations. A content digest proves that the supplied
content agrees with its referenced digest; it does not independently prove
provider completeness, institution identity, scientific review, or reviewer
authority. Reviewer identity and permission must be authenticated by the
operating review process. These contracts are not a security boundary against
code running with the same application privileges.

The official paired adapter additionally verifies retained provider bytes,
request/response endpoint and query, response timestamps, and its internal live
transport lineage. Injected transports remain fixture evidence. Broader
deployment still needs a reviewed acquisition plan and authority/reviewer
workflow; the local trial cannot supply those approvals by implication.

## Normalized Atlas Scale

Scientific raw values and units remain unchanged. A separate presentation
contract records the metric-specific normalization, exact comparison cohort,
cohort size and fitted parameters, cutoff where relevant, evidence manifest
digest, coverage/uncertainty flags, and missing reasons before exposing an
Atlas value in `[0,100]`.

Each fitted cohort must equal its dated, reviewed normalization-population
manifest and bind one reconstructable calculation proof per entity. Atlas
values and metadata reconstruct from those calculations. Physics-wide
aggregation consumes these certified field Atlas observations and a separate
reviewed field-population proof; it cannot bypass normalization by accepting
raw field results.

`100` means at or above the fitted upper position within the declared
comparison cohort; it does not mean perfect. `0` means the fitted lower
position or a measured minimum; it does not mean no research. Missing remains
missing and uses the neutral map treatment.

The existing five user-defined weights must still total 100%. Their composite
is an exploratory perspective, not an official score or ranking.

## Current bounded evidence

The January 2020 paired capture is a record-level proof and cannot certify a
complete calendar year or a Momentum window. Existing legacy hep-th and
Condensed Matter replay pages did not retain response timestamps, so their
citation observations cannot be retrospectively declared common-cutoff. The
current field ledgers remain unreviewed. These states are explicit failures of
required evidence, not zeros and not permission to relax Metric System v1.

Exact trial and replay results are recorded in the
[certification validation report](validation/scientific-evidence-certification-2026-09-05.md).
