# Scientific Attribution Policy

Status: **implemented scientific framework; experimental and withheld from live
metrics**.

Policy implementation: `fractional-attribution-v1`.

This policy defines how Physics Atlas connects a paper to researchers,
institutions, and countries. It is a conservative evidence-allocation policy,
not a claim about intellectual contribution, authorship importance, research
quality, or institutional ownership.

## Durable rules

1. Paper attribution is based primarily on affiliations asserted for that
   paper at publication time.
2. A current homepage, profile, or employment record never retroactively
   replaces a historical paper affiliation.
3. Persistent identifiers such as INSPIRE author IDs, ORCID, and ROR support
   identity resolution and cross-checking. An identifier is not contribution
   evidence.
4. Institution strings resolve to canonical institutions while the original
   department, laboratory, group, or other subunit label is retained where it
   is useful.
5. An ambiguous, unresolved, or absent affiliation remains explicit. Physics
   Atlas does not guess a canonical institution or country.
6. Missing evidence never silently becomes a measured zero.

Geographic rendering remains separate from research attribution. Country
attribution follows the location metadata of a resolved paper-time institution;
map geometry is not scientific evidence.

## Paper-time materialization

The materialized relationship is:

```text
Paper
  ↔ provider author slot
  ↔ resolved Researcher, when supported
  ↔ paper-time affiliation assertion
  ↔ canonical Institution and Country, when resolved
```

For every source paper revision, materialization retains enough evidence to
reconstruct the decision:

- source provider, source record, immutable snapshot, and dataset version;
- raw author name and author position;
- raw affiliation text and provider institution identifier, when supplied;
- preserved subunit label;
- author-identity and affiliation-resolution statuses;
- canonical researcher, institution, and country IDs only when supported;
- exact fractional numerator/denominator and decimal representation;
- attribution-policy and materialization versions;
- identity-resolution, contribution-statement, and source provenance.

Paper-time affiliation rows are distinct from current or interval-based profile
affiliations. Reprocessing a provider revision creates versioned materialized
evidence; a current-profile update cannot overwrite the historical assertion.

## Fractional Attribution v1

Let a paper have `N` provider author slots. In the absence of reliable numeric
contribution evidence, author `i` receives:

```text
a_i = 1 / N
```

Let `K_i` be the number of distinct effective paper-time affiliation assertions
for that author after exact duplicates and repeated assertions of the same
resolved canonical institution are collapsed. Each effective assertion receives:

```text
w_ij = 1 / (N × K_i)
```

If an author has no affiliation assertion, one explicit missing slot carries
the full author share. The attribution ledger therefore always satisfies:

```text
Σ allocated shares + Σ withheld shares = 1 paper
```

Only a resolved assertion contributes its share to an institution and its
location country. An unresolved, ambiguous, or missing assertion keeps its
share as withheld mass. The calculation never reallocates that mass to a
resolved affiliation, so partial evidence is not silently renormalized to look
complete.

For clarity, an assertion may be valid source evidence while its canonical
target remains unresolved. It participates in conservation but not in an
institution or country total.

### Aggregation

For institution `g` and country `c`:

```text
institution_weight(g) = Σ resolved w_ij whose institution is g
country_weight(c)     = Σ resolved w_ij whose institution location is c
```

The same paper can contribute to several institutions and countries, but its
combined resolved and withheld mass cannot exceed one. A known researcher keeps
the equal author share independently of how many affiliations are listed; an
unresolved researcher identity is not promoted to a canonical researcher.

The coverage value is:

```text
paper affiliation coverage = allocated paper mass / total paper mass
```

Complete evidence gives coverage `1`. Partial evidence gives a value below `1`;
it does not shrink the denominator.

## Contribution evidence

Author order and corresponding-author status do not alter v1 weights. Explicit
contribution statements, including CRediT-like statements, may be retained as
non-numeric provenance. They do not change the calculation until a separate,
scientifically justified and versioned weighting policy has been reviewed.

Equal author shares are a conservative counting convention. They are not an
assertion that all authors made identical intellectual contributions.

## Deterministic examples

| Case | Result |
| --- | --- |
| One author, one resolved affiliation | Institution and country receive `1` |
| `N` authors, one shared institution | Each author supplies `1/N`; institution total is `1` |
| Authors at different institutions | Each institution receives the sum of its authors' shares |
| One author, two resolved affiliations | Each affiliation receives half of that author's share |
| One resolved and one unresolved affiliation | Half of the author share is allocated; half remains withheld |
| Author with no affiliation | The entire author share remains withheld |
| Large collaboration | The same exact `1/N` rule applies; no author-order or consortium bonus is introduced |
| Duplicate source assertion for one canonical institution | Counted once for allocation while all source assertion IDs remain provenance |

Tests use exact rational arithmetic at the policy boundary and cover
conservation, partial coverage, multi-affiliation authors, unresolved evidence,
and large author lists. Persistence stores both exact fractions and a high
precision decimal representation.

## Institution identity and subunits

Institution resolution prefers supported authority identifiers and exact,
reviewed identity evidence. Departments, laboratories, institutes, and research
groups may be represented as labels or relationships beneath a canonical host
institution. They must not be discarded merely to make names match, and they
must not become duplicate host institutions without evidence.

A change of name, merger, split, or historical affiliation needs versioned
evidence. An ambiguous match stays unresolved and enters the review path rather
than being assigned to the most convenient current institution.

## Limitations

- Provider author and affiliation lists can be incomplete or internally
  inconsistent.
- Persistent IDs can be absent, stale, or incorrect.
- Institution history and subunit relationships are not complete.
- Country attribution depends on resolved institution-location evidence and is
  not political-boundary ownership.
- Fractional Attribution v1 allocates publication evidence; it does not measure
  contribution, impact, quality, prestige, or rank.

The policy is an implemented and testable foundation. It is not, by itself,
scientific validation of the five Metric System v1 layers. Activation remains
subject to the [joint validation gate](metric-validation.md).
