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

## Heavy-tailed counts

Activity and Connectivity use a two-stage candidate transform:

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

## Field- and age-normalized citations

Impact uses midrank percentiles of `log1p` citation observations inside the
same reviewed field and publication-year cohort. A tie receives the midpoint
of its occupied ranks. This controls basic field and citation-age differences;
it does not eliminate database coverage, self-citation, or social biases.

## Naturally bounded transforms

Diversity uses normalized Shannon evenness and Momentum uses a symmetric
two-window change. These formulas already have fixed mathematical bounds and
must not be run through an unrelated cohort min/max transform merely to widen
their colors.

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
