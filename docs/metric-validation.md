# Metric System v1 Validation

Status: **validation framework implemented; Metric System v1 remains
experimental and withheld from live visualization**.

Threshold configuration: `metric-validation-thresholds-v1`.

The thresholds below are first-pass evidence gates, not immutable scientific
truth. Changing a threshold requires a new configuration version and a recorded
validation decision. Passing a numeric minimum is necessary but not sufficient
for scientific activation.

## Certification boundary

All readiness inputs pass through `scientific-evidence-certification-v1`.
Canonicalization or provider presence alone is not eligibility. Each included
paper, relationship, field ledger, and citation observation is bound to a
checksum-verified decision; excluded and unresolved denominator mass remains
visible in the certification manifest. Metric calculators reject an
uncertified, stale, scope-incompatible, or digest-mismatched partition before
a formula executes. The exact states and complete-year rule are documented in
[Scientific Evidence Certification v1](evidence-certification.md).

## Global coverage thresholds

| Evidence | Minimum |
| --- | ---: |
| Paper-time affiliation coverage | 90% |
| Canonical institution coverage | 95% |
| Citation-observation coverage | 90% |
| Canonical field-attribution coverage | 90% |

Coverage denominators retain unresolved and missing eligible mass. The system
does not compute coverage only over successfully resolved records.

## Metric-specific minimums

| Dimension | Entity evidence minimum | Additional requirement |
| --- | --- | --- |
| Activity | 10 fractional papers; 5 distinct identifiable researchers | Three complete source years; eligible normalization cohort |
| Impact | 10 mature eligible papers | At least 24 months citation age; common cutoff; same-field/year/document cohorts; 90% citation coverage |
| Connectivity | 10 fractional papers; 5 identifiable researchers | Resolvable primary collaboration indicator and at least 90% relationship coverage |
| Diversity | 15 fractional papers | At least two eligible canonical categories and 90% field-attribution coverage |
| Momentum | 10 fractional papers in each adjacent three-year window | Six complete years; terminal year complete; compatible evidence versions; eligible same-field cohort |

The implementation also uses versioned normalization-cohort safeguards:

- Activity: at least 30 eligible peer entities;
- Impact: at least 50 papers per citation reference cohort and at least 30
  eligible peer entities for the display transform;
- Momentum: at least 30 eligible same-field peer entities;
- non-degenerate fitted cohort bounds or scale.

Impact citation evidence is bound to an explicit UTC observation cutoff and to
the exact provider record, source snapshot, dataset or artifact checksum, and
replay version. Raw and provider-reported non-self counts are preserved
separately. Primary Impact evidence excludes self citations; a missing non-self
count is withheld rather than replaced with the raw count. Only papers whose
evidence was observable by the common cutoff and whose field,
publication-year, age, and document-type cohort is comparable may enter a
reference cohort.

An acquisition-manifest completion timestamp is only an upper bound when
individual source-page capture times are unavailable. It must not be represented
as a simultaneous observation or used to reconstruct historical
observable-at-cutoff cohorts. Such evidence remains raw and incomparable until
the missing observation-time lineage is supplied.

`Sufficient resolvable collaboration edges` is not converted into an arbitrary
prestige or centrality threshold. In v1 it is operationalized through a known
entity-specific collaboration indicator, the publication and researcher
minimums, and at least 90% relationship-resolution coverage. Partner counts and
edges remain companion evidence. A future fixed edge-count requirement would
need an explicit threshold-version change and validation.

## Missing versus zero

The validation contract distinguishes:

- measured zero: valid evidence records a quantity of zero;
- missing: no observation exists for the required input;
- unresolved: evidence exists but cannot be assigned to a canonical entity;
- immature: evidence exists but the required time window has not elapsed;
- insufficient: evidence exists but a configured coverage, count, or cohort
  minimum fails.

Only the first can be used as numeric zero. The others generate a missing
observation with explicit reasons. A visualization must use its missing-data
treatment rather than the low end of the metric color scale.

## Joint Metric Activation Gate

The complete system can become eligible for reviewed activation only when a
single versioned activation manifest demonstrates all of the following:

1. exactly the five Metric System v1 algorithms are implemented;
2. each definition, algorithm, and normalization version matches its contract;
3. deterministic reproduction passes for every metric and for the system as a
   whole;
4. Fractional Attribution v1 materialization and conservation are validated;
5. a canonical Physics ontology and versioned INSPIRE and arXiv mappings are
   available, and every paper conserves one field-evidence unit across mapped
   canonical weights and explicit unmapped mass under
   `provider-evidence-conservation-v2` and
   `cross-provider-field-reconciliation-v1`;
6. global affiliation, canonical-institution, citation, and field-mapping
   coverage pass the configured thresholds;
7. six-year historical coverage and incomplete-year exclusion are validated;
8. citation maturity and common-cutoff handling are validated;
9. metric-specific normalization has passed numerical and cohort validation;
10. raw inputs, fitted parameters, versions, and calculation provenance are
    sufficient to reproduce every observation.
11. Diversity has been reviewed on an explicitly classified `broad-physics`
    evidence boundary; a named specialty field, or an unreviewed union of
    specialty trials, remains `field-conditioned` and cannot supply this proof.

Persisted activation evidence records the exact `acquisitionScope`, its
`acquisitionBoundaryKind` (`field-conditioned` or `broad-physics`), immutable
`dataSourceVersion`, and current `diversity-breadth-review-v1` proof. Public
reads require a reviewed `broad-physics` boundary and require the scope and
dataset version to match the current live dataset. A legacy, specialty-only,
stale-dataset, or manually asserted `jointGatePassed` flag without those current
proofs cannot expose or preserve live observations.

The gate fails closed:

```text
any required system evidence missing
→ Metric System v1 = experimental / withheld
```

There is no production state in which Activity alone is labeled validated while
the other four official dimensions remain unfinished. An eligible gate result
still requires an explicit reviewed activation decision; it does not publish
layers automatically.

The Joint Metric Activation Gate remains a scientific gate. Authorization to
begin a Full Physics load additionally requires the independent
[`storage-budget-gate-v1`](storage-architecture.md). Neither gate can override
the other, and passing storage capacity does not activate a metric.

The public repository read path independently verifies the exact five current
definition versions and `live-calculated` statuses together with the exact
active release manifest, including the current field-weighting and
cross-provider reconciliation versions and an explicit conservation pass. Four
live definitions plus one candidate or missing definition therefore returns no
live observations. Reference-data seeding may preserve a reviewed exact
activation, but it cannot create or promote one.

### System readiness versus entity availability

The gate is global. After the complete system has been validated and activated,
an individual entity may still lack one or more observations because its own
evidence fails a threshold. For example, an institution can have eligible
Activity and missing Impact because it has only six mature citation-eligible
papers. That entity-level absence does not deactivate the globally validated
system, and it must not be filled with zero.

## Current gate result

The algorithms and policy contracts now form an implemented test framework,
but the current public `hep-th-v1` production evidence is a bounded live slice,
not representative Full Physics validation data. It does not establish the
required historical affiliation, citation, field, institution, normalization,
or reference-ecosystem evidence across all five dimensions.

Therefore:

```text
Joint Activation Gate: WITHHELD
Live Activity layer:     WITHHELD
Live Impact layer:       WITHHELD
Live Connectivity layer: WITHHELD
Live Diversity layer:    WITHHELD
Live Momentum layer:     WITHHELD
```

The production worker's fail-closed behavior must continue emitting no live
metric observations until a complete, reviewed activation manifest passes.
Synthetic fixtures and historical pilot signals remain isolated demonstration
or reproducibility data, not substitutes for gate evidence.

## Deterministic validation suite

Standard tests use fixed local evidence and never depend on live provider
availability. They cover:

- paper-time affiliation materialization and version lineage;
- cross-provider affiliation precedence, including lower-precedence replay and
  unresolved cross-tier and equal-tier conflicts;
- exact one-paper conservation for single author, multiple authors,
  multi-institution work, multi-affiliation authors, large collaborations,
  unresolved affiliations, and partial coverage;
- ontology IDs, parents, cycles, aliases, provenance, and versioning;
- INSPIRE/arXiv raw-category preservation, primary/secondary roles, multi-field
  equal shares, cross-provider one-paper conservation, unmapped categories, and
  mapping versions;
- all five raw calculators and their companion evidence;
- each metric-specific normalization, including tied and degenerate cohorts;
- minimum count, maturity, complete-year, coverage, and cohort thresholds;
- measured-zero versus missing behavior;
- field-first, field-balanced Physics-wide aggregation without raw-count
  dominance;
- exact-five composite weights and explicit confirmation behavior;
- exact-five Joint Activation Gate behavior, including rejection of partial
  manifests;
- stable input digests and version/provenance reconstruction.

Passing these deterministic tests proves implementation consistency, not
scientific validity on a representative population.

## Reference ecosystem validation

Validation is performed on linked ecosystems, not isolated profiles:

```text
Paper
↔ Researcher
↔ paper-time Affiliation
↔ Institution
```

A reusable reference case records source evidence, expected identity and
affiliation constraints, field-mapping evidence, time bounds, and the exact
dataset/rule versions. Checks should detect:

- false researcher or institution merges and splits;
- paper-time affiliations overwritten by current profiles;
- unresolved evidence promoted without support;
- incorrect institution/subunit or country materialization;
- unreasonable or unreconstructable field assignment;
- attribution conservation failures;
- normalization cohorts with wrong fields, years, or entity types;
- missing historical or citation evidence hidden as zero.

IAS, Princeton, Harvard, Caltech, UCSB/KITP, Stony Brook, and Perimeter may be
used as well-documented sanity-check anchors. They are not ranking ground truth.
Reference validation must never demand a predetermined metric order or tune a
formula until those institutions appear in a preferred sequence.

Before live activation, reference cases need independently reviewed source
evidence, explicit expected relationship constraints, and reproducible failure
reports. The current framework establishes the shape of these checks; it does
not claim that the named ecosystems form a complete or representative truth
set.

## Scientific review still required

Before activation, Atlas Physica still needs representative acquisition
coverage, sampled expert review of field mappings and historical affiliations,
identity error analysis, citation-source bias analysis, robustness and
sensitivity studies, uncertainty communication, external methodological review,
and a documented release decision.

No validation result may be framed as an institutional ranking, researcher
recommendation, scientific-value judgment, or prediction.
