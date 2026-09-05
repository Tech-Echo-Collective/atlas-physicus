# Metric normalization

Normalization makes a supported raw observation legible on the existing
0–100 heat scale. It does not create evidence, repair missing inputs, or make
unlike scientific contexts interchangeable.

The public presentation contract is versioned as
`normalized-atlas-scale-v1`. It is downstream of
`scientific-evidence-certification-v1`: no transform can promote uncertified
provider evidence into a metric observation.

## Rules

1. Preserve the raw observation and raw unit.
2. Fit parameters only within an explicit cohort: metric version, entity type,
   field/domain, time window, acquisition scope, and input dataset version.
3. Store the transform name, exact cohort proof, fitted parameters, and cohort
   size with the deterministic normalized result. When that result is later
   materialized as a `MetricObservation`, record the materialization timestamp
   separately; wall-clock time is not a scientific transform input.
4. Emit no observation when inputs or cohort minimums fail. Missing is not zero.
5. Never reuse parameters across dataset modes or silently refit an older
   calculation version.
6. Keep metric-specific transforms. A single global min/max rule is not
   scientifically defensible for every distribution.
7. Bind the Atlas value to the evidence-certification manifest, exact cutoff
   where relevant, and coverage/uncertainty flags used by the calculation.
8. Require the exact entity set and one calculation proof per entity to match
   the dated, reviewed normalization-population manifest. Reconstruct the
   normalized value and presentation metadata from those proofs. A digest
   validates the submitted population, while the review process remains
   responsible for its scientific completeness and reviewer authority.

`100` means at or above the fitted upper position in the declared comparison
cohort; it does not mean perfect or best. `0` means the fitted lower position
or a measured minimum; it does not mean no research. Missing evidence remains
missing and uses the neutral visualization state.

## Research Activity

Research Activity uses a two-stage transform:

\[
x_e=\log(1+r_e)
\]

where \(r_e\) is the nonnegative raw count. For an eligible cohort, store the
linear-interpolated 5th and 95th quantiles \(Q_{.05}\) and \(Q_{.95}\), then:

\[
s_e=100\operatorname{clip}\left(
\frac{x_e-Q_{.05}}{Q_{.95}-Q_{.05}},0,1\right).
\]

The stored quantiles limit the visual effect of one extreme outlier. A cohort
smaller than the metric contract minimum, or one with equal quantiles, is
insufficient and produces no score.

This is a winsorized linear position inside a fitted range, not a percentile
or rank. A value near 100 means that the transformed observation is near or
above the stored upper bound; it does not mean “better than 100%” or “better
than most.”

## Research Impact

Impact first calculates each eligible paper's normalized citation score against
the same canonical field, publication year, document type, and common citation
cutoff. The fractionally attributed weighted mean is retained as raw MNCS.
PP(top 10%) is companion evidence; its threshold uses tie-aware `log1p`
midranks inside the paper cohort. Entity MNCS values receive a
presentation-only stored robust `log1p` 5th/95th transform inside the compatible
entity cohort. Neither transformation removes source coverage or social bias.

## Collaboration / Connectivity

The primary collaboration indicator is an entity-appropriate fraction:
collaborative-paper share for researchers, cross-institution share for
institutions, and international share for countries. It maps directly from
`0–1` to `0–100`. Partner counts and graph edges remain companion evidence and
do not replace this scalar with centrality or prestige.

## Research Diversity

Diversity uses normalized Shannon evenness over an explicit, versioned
canonical category universe and maps directly from `0–1` to `0–100`. A valid
concentration can therefore produce zero, while insufficient field coverage
produces no observation. The partition must use the exact reviewed
category-universe proof, including the current ontology version; an arbitrary
caller-selected denominator cannot become a certified observation.

## Research Momentum / Sustainability

Momentum preserves the log ratio between adjacent complete three-year
Activity windows. Within the same field cohort it subtracts the cohort median,
uses `1.4826 × MAD` with `IQR / 1.349` as a deterministic fallback, clips at
the configured robust-z bound, and maps the centered result around `50`. A
fully tied eligible cohort maps to neutral `50`; incomplete or insufficient
history remains missing. This is backward-looking normalization, not a
forecast.

## Reconstruction record

A normalized observation is reconstructable only when it retains:

- raw value and raw unit;
- normalized value;
- metric-definition and algorithm versions;
- normalization method and version;
- cohort key and cohort size;
- fitted parameters or category/window totals;
- input dataset/update version and acquisition scope;
- entity, field/domain, and period partition;
- input count and quality flags;
- evidence-certification manifest digest and Atlas Scale version;
- explicit observation cutoff where the metric depends on one.

The persisted `MetricObservation` additionally records when it was calculated;
the pure certification/normalization proof is reconstructable without making
wall-clock execution time part of the formula.

Physics-wide aggregation accepts certified field Atlas observations and a
reviewed field-population proof. It cannot use an unnormalized raw result in
place of a normalized field value.

Changing a formula, cohort rule, minimum, or transform creates a new algorithm
or metric version. Older values retain their original meaning.

The exact v1 algorithms and method versions are canonical in
[Metric System v1](metrics-spec-v1.md). Thresholds and publication rules are
canonical in [Metric System v1 validation](metric-validation.md).
Evidence eligibility and exact source-year rules are canonical in
[Scientific Evidence Certification v1](evidence-certification.md).
