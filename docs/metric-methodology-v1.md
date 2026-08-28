# Candidate scientific metric methodology v1

Status: **experimental and withheld from the live Atlas**.

This document defines reviewable v1 candidates for the five accepted Physics
Atlas base metrics. A definition is not a validation result. No candidate may
become a public live layer until its inputs, cohort coverage, implementation,
and sanity checks pass the activation gate for the exact dataset version and
partition being shown.

All metrics are descriptive. They do not rank scientific quality, institutional
prestige, researcher worth, or future potential. Missing or insufficient data
produces no observation; it is never converted to zero.

## Shared scientific boundary

Every observation is partitioned by entity type and entity, field or science
domain, terminal year, acquisition scope, and immutable input dataset version.
Country and institution attribution may only follow reviewed paper-time
affiliations. Geographic display geometry is not attribution evidence.

Every persisted result must retain the metric-definition ID and version,
algorithm version, input dataset/update version, calculation timestamp,
acquisition scope, entity/field/year partition, raw value and unit,
normalization method and fitted parameters, input count, and quality flags. A
formula change creates a new metric version rather than rewriting the meaning
of an older result.

## Research Activity

- **Definition ID / version:** `research_activity_score` /
  `activity-output-participation-v1`.
- **Interpretation:** observed output participation in a defined field and
  acquisition scope; it is not research quality.
- **Formula:** let \(A_e\) be the number of distinct canonical papers attributed
  to entity \(e\) in the trailing three complete calendar years. The raw value
  is \(A_e\). The visualization transform is
  \(x_e=\log(1+A_e)\), followed by the stored robust cohort transform in
  [normalization](normalization.md).
- **Inputs:** canonical papers, reviewed field classification, and supported
  paper-time authorship or affiliation attribution.
- **Aggregation:** researcher, institution, country, field, or domain only when
  the relationship required for that level is present. Multi-institution work
  is attributed to every supported affiliation; it is not forced into one
  owner.
- **Window:** trailing three complete calendar years ending at the selected
  terminal year.
- **Normalization:** within the same entity type, field/domain, window,
  acquisition scope, and dataset version; `log1p` plus stored 5th/95th cohort
  quantiles.
- **Minimums:** complete three-year source coverage, at least three supported
  papers for the entity, at least 30 eligible peer entities, and distinct 5th
  and 95th quantiles.
- **Missing:** absent relationships, incomplete source windows, or failed
  minimums emit no observation.
- **High / low:** high means more observed output participation relative to the
  exact comparison cohort; low means less. Neither means better or worse
  science.
- **Limitations:** acquisition selection, authorship/affiliation coverage,
  database latency, field mapping, and the chosen window can all change the
  result.

## Research Impact

- **Definition ID / version:** `research_impact` /
  `impact-field-age-percentile-v1`.
- **Interpretation:** recorded citation attention relative to papers of similar
  field and age; it is not scientific value or quality.
- **Formula:** for every eligible paper, calculate the midrank percentile of
  `log1p(non-self citation count)` within the same reviewed field and
  publication-year cohort. The entity raw value is the arithmetic mean of its
  eligible paper percentiles; the 0–100 value is that mean expressed as a
  percentage.
- **Inputs:** canonical papers, explicit citation observations, reviewed field
  classes, publication dates, authorships, and enough identity evidence to
  apply a documented self-citation rule.
- **Aggregation:** supported papers attributed to the entity in the requested
  partition. Duplicate provider records do not create duplicate papers.
- **Window / age control:** a paper must be at least 24 months old. Cohorts use
  the same field and publication year; newer papers are never compared directly
  with mature papers.
- **Minimums:** at least five eligible papers per entity, at least 80% citation
  coverage for the entity, and at least 50 eligible papers in every cohort used.
- **Missing:** missing citations are missing, not zero. A failed cohort or
  coverage threshold emits no observation.
- **High / low:** high means greater recorded citation attention than same-age,
  same-field peers; low means less recorded attention in that evidence source.
- **Limitations:** citations are incomplete, delayed, field-dependent, and
  socially structured. The metric does not capture many forms of scientific
  contribution.

## Collaboration / Connectivity

- **Definition ID / version:** `collaboration` /
  `connectivity-distinct-partners-v1`.
- **Interpretation:** breadth of supported collaboration relationships; it is
  not prestige or contribution allocation.
- **Formula:** let \(C_e\) be the number of distinct supported neighbors during
  the trailing three complete years: coauthors for researchers,
  co-participating institutions for institutions, and co-participating
  countries for countries. Normalize `log1p(C_e)` with the stored robust cohort
  transform.
- **Inputs:** canonical papers and authorships plus reviewed temporal
  affiliations for institution/country levels.
- **Aggregation:** distinct relationships only. Repeated joint papers do not
  create new neighbors. No hidden centrality or prestige weighting is used.
- **Minimums:** at least three supported papers for the entity, at least 90%
  relationship-resolution coverage, at least 30 eligible cohort entities, and
  nondegenerate cohort quantiles.
- **Missing:** unsupported or unresolved links do not become absent
  relationships; insufficient coverage emits no observation.
- **High / low:** high means broader observed connection breadth in the exact
  cohort; low means narrower observed breadth. It does not mean stronger or
  better collaboration.
- **Limitations:** author-list conventions, consortium papers, name resolution,
  affiliation coverage, and acquisition scope affect the graph.

## Research Diversity

- **Definition ID / version:** `research_diversity` /
  `diversity-normalized-shannon-v1`.
- **Interpretation:** evenness of observed participation across a reviewed
  field/subfield taxonomy; high diversity is not automatically better.
- **Formula:** a paper assigned to \(k\) eligible categories contributes
  \(1/k\) to each. Let \(q_j\) be the resulting share in category \(j\), and
  let \(K\) be the number of eligible categories in the exact taxonomy scope.
  \(D_e=-\sum_j q_j\ln q_j/\ln K\), with score \(100D_e\).
- **Inputs:** canonical papers and a versioned, reviewed multi-category
  classification taxonomy.
- **Aggregation:** papers supported for the entity and period; fractional
  category contribution prevents multi-label papers from being counted more
  than once in total.
- **Window:** trailing three complete calendar years unless a future version
  explicitly defines another window.
- **Minimums:** at least two eligible taxonomy categories, at least ten papers
  per entity, and at least 90% classification coverage.
- **Missing:** unclassified papers remain unclassified. Failed taxonomy or
  coverage minimums emit no observation.
- **High / low:** high means more even observed breadth; low means concentration
  in fewer observed categories. Neither is a quality judgment.
- **Limitations:** results depend strongly on taxonomy resolution and provider
  categorization. A `hep-th`-conditioned corpus is not automatically a valid
  broad-Physics diversity sample.

## Research Momentum

- **Definition ID / version:** `momentum` /
  `momentum-symmetric-window-change-v1`.
- **Interpretation:** observed change between adjacent completed periods; it is
  not a forecast and does not prove sustainability. The broader product
  taxonomy retains sustainability as future methodological work; this v1
  candidate measures momentum only.
- **Formula:** let \(R\) be supported Activity output in years \(t-2\) through
  \(t\), and \(B\) output in years \(t-5\) through \(t-3\). The raw symmetric
  change is \((R-B)/(R+B)\); the visualization value is
  \(50(1+(R-B)/(R+B))\).
- **Inputs:** the same supported output relationships as Activity across six
  complete years.
- **Aggregation:** exact entity/field/scope partition; no extrapolation beyond
  the observed windows.
- **Minimums:** six complete calendar years and at least ten supported papers
  across both windows. When \(R+B=0\), no observation is emitted.
- **Missing:** an incomplete year, unsupported relationship, or failed minimum
  emits no observation.
- **High / low:** above 50 means more observed output in the recent window;
  below 50 means less; 50 means balanced windows.
- **Limitations:** short-term events, source coverage, organizational change,
  and small denominators can affect change. The metric must never be presented
  as prediction.

## Current activation result

The production evidence snapshot in
[v3.0.5 `hep-th-v1` validation](validation/v3.0.5-hep-th-live.md) fails the
required geographic, citation-age, relationship, taxonomy, and longitudinal
coverage gates. All five live candidates therefore remain experimental and
withheld. Synthetic and historical pilot observations remain available only in
their isolated reproducibility modes.
