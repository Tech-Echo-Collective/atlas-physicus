# Metric normalization

Normalization makes a supported raw observation legible on the existing
0–100 heat scale. It does not create evidence, repair missing inputs, or make
unlike scientific contexts interchangeable.

## Rules

1. Preserve the raw observation and raw unit.
2. Fit parameters only within an explicit cohort: metric version, entity type,
   field/domain, time window, acquisition scope, and input dataset version.
3. Store the transform name, cohort key, fitted parameters, cohort size, and
   calculation timestamp with the normalized result.
4. Emit no observation when inputs or cohort minimums fail. Missing is not zero.
5. Never reuse parameters across dataset modes or silently refit an older
   calculation version.
6. Keep metric-specific transforms. A single global min/max rule is not
   scientifically defensible for every distribution.

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
produces no observation.

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
- input count, calculation time, and quality flags.

Changing a formula, cohort rule, minimum, or transform creates a new algorithm
or metric version. Older values retain their original meaning.

The exact v1 algorithms and method versions are canonical in
[Metric System v1](metrics-spec-v1.md). Thresholds and publication rules are
canonical in [Metric System v1 validation](metric-validation.md).
