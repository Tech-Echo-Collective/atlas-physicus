# Physics Atlas Metric System v1

Status: **formulas implemented as a versioned, deterministic scientific
framework; not scientifically validated and not active on live data**.

Physics Atlas Metric System v1 contains exactly five descriptive dimensions:

| ID | Dimension | Primary raw interpretation |
| --- | --- | --- |
| `research_activity_score` | Research Activity | Field-weighted fractional publication activity |
| `research_impact` | Research Impact | Fractionally attributed field-, year-, and document-normalized citation attention |
| `collaboration` | Collaboration / Connectivity | Fractionally weighted collaboration proportion appropriate to the entity type |
| `research_diversity` | Research Diversity | Normalized Shannon evenness across a versioned canonical category set |
| `momentum` | Research Momentum / Sustainability | Backward-looking field-relative change between adjacent complete windows |

The five dimensions form one system. None is an overall scientific score, and
none measures researcher worth, institutional prestige, scientific quality, or
future potential. No partial subset may be presented as a validated production
Metric System.

## Shared calculation boundary

Every calculation is scoped to an exact partition containing:

- entity type and canonical entity ID;
- canonical field ID or Physics domain;
- terminal year and common observation date;
- immutable dataset version and acquisition scope;
- scientific-attribution, ontology, provider-mapping, metric-definition,
  algorithm, normalization, and threshold versions.

For paper `p`, entity `e`, and field `f`, let:

- `w(p,e)` be the resolved Fractional Attribution v1 share;
- `s(p,f)` be the versioned provider-to-Atlas field share;
- `a(p,e,f) = w(p,e) × s(p,f)`.

Unresolved affiliation or field mass is not redistributed. A measured zero can
be a valid input, but absent, immature, unresolved, or insufficient evidence
produces no observation. Every eligible result preserves its raw value,
components, input count and digest, fitted normalization parameters, quality
reasons, and full version lineage.

## 1. Research Activity v1

Definition version: `activity-fractional-output-v1`.

For a field and the trailing three complete calendar years ending at `t`:

```text
A(e,f,t) = Σp a(p,e,f)
```

The sum is the entity's fractional attributed canonical-paper mass. Companion
evidence includes distinct papers and distinct identifiable researchers. It
describes observed publication activity only; it is not productivity quality,
excellence, or scientific value.

### Display normalization

Activity is normalized inside the same field, entity type, window, acquisition
scope, and dataset lineage:

1. apply `log1p` to each eligible raw Activity value;
2. fit the 5th and 95th quantiles to an eligible cohort;
3. winsorize at those bounds and linearly map to `0–100`.

The fitted bounds and cohort definition are stored. This is a robust display
transform, not a percentile rank. The raw fractional-paper quantity remains
available.

## 2. Research Impact v1

Definition version: `impact-fractional-mncs-pp10-v1`.

Eligible papers are compared at a common citation cutoff within the same
canonical field, publication year, and document type. For paper `p`:

```text
expected(p) = mean recorded citations in its comparison cohort
NCS(p)      = recorded citations(p) / expected(p)

MNCS(e,f,t) = Σp a(p,e,f) × NCS(p) / Σp a(p,e,f)
```

The primary raw value is the fractionally weighted mean normalized citation
score. `PP(top 10%)` is retained as companion evidence: it is the fractionally
weighted share of eligible papers at or above the tie-aware 90th percentile in
their comparison cohort.

Papers must have a recorded citation observation at the common cutoff and a
mature citation window. Under Validation Thresholds v1 the minimum age is 24
months. A recorded citation count of zero is data; a missing citation
observation is not zero. A comparison cohort with no positive expected citation
mean is ineligible.

MNCS is preserved as the raw value. A presentation-only `log1p` plus stored
5th/95th robust cohort transform maps eligible entity MNCS values to `0–100`.
Impact describes recorded citation attention, not correctness, quality, value,
or future influence.

## 3. Collaboration / Connectivity v1

Definition version: `connectivity-collaboration-proportions-v1`.

For a paper-level relationship indicator `I(p)` in `{0,1}`:

```text
C(e,f,t) = Σp a(p,e,f) × I(p) / Σp a(p,e,f)
```

The primary indicator is entity-type specific:

| Entity type | Primary indicator |
| --- | --- |
| Researcher | Collaborative publication |
| Institution | Cross-institution publication |
| Country | International publication |

All three supported proportions, unique partner institutions, and graph edges
remain companion evidence. Unresolved relationships are not treated as absent
edges. The primary proportion is naturally bounded and maps directly from
`0–1` to `0–100`; it is not converted into a cohort rank.

Centrality is not used as prestige, quality, or scientific value. Network
position can remain auditable graph evidence without entering the primary v1
scalar.

## 4. Research Diversity v1

Definition version: `diversity-normalized-shannon-v1`.

Let the versioned eligible category universe contain `K >= 2` canonical
subfields. Paper multi-field shares and entity attribution produce category
mass `x_j`; let `q_j = x_j / Σx_j`. Then:

```text
H(e) = -Σj q_j ln(q_j)
D(e) = H(e) / ln(K)
display = 100 × D(e)
```

The primary raw value is normalized Shannon evenness in `0–1`. The eligible
category universe and ontology version are part of the observation provenance.
Companion components are:

- variety: number of categories with positive supported mass;
- balance: normalized Shannon evenness;
- disparity: reserved as missing in v1 until a defensible field-distance model
  exists;
- optional future Rao–Stirling evidence under a new version.

A low eligible score means concentration in the documented category universe.
Low field-attribution coverage means no score. The two cases are never
collapsed. High Diversity is not inherently better.

## 5. Research Momentum / Sustainability v1

Definition version: `momentum-field-relative-log-change-v1`.

The formal terminal year must be complete. The current incomplete calendar year
is excluded. Let `B` be fractional Activity in years `t-5..t-3` and `R` be
fractional Activity in years `t-2..t`:

```text
g(e,f,t) = ln(R / B)
```

Both windows must independently pass the evidence minimum. The same-field
cohort median is subtracted from `g`. The robust scale is
`1.4826 × MAD`, with `IQR / 1.349` as a deterministic fallback. The centered
value is clipped at the documented robust-z bound and mapped around neutral
`50` to `0–100`. A fully tied valid cohort maps to `50`; missing history does
not.

Stored companion evidence includes:

- baseline and recent fractional paper mass;
- complete-window coverage;
- fraction of six years with positive observed activity (persistence);
- median absolute deviation of annual `log1p` changes (volatility).

Momentum is backward-looking observed evolution. It is not a forecast, trading
signal, growth promise, or proof of sustainability. RSI, MACD, and predictive
trend logic are outside this system.

## Metric-specific normalization

The metrics deliberately do not share one generic transform:

| Metric | Raw preservation | Display method |
| --- | --- | --- |
| Activity | Fractional paper mass | `log1p`, 5th/95th robust winsorized cohort scale |
| Impact | MNCS; PP(top 10%) companion | Field/year/document normalization, then robust MNCS display scale |
| Connectivity | Fractional relationship proportion | Direct bounded `0–1` to `0–100` |
| Diversity | Normalized Shannon evenness | Direct `0–1` to `0–100` |
| Momentum | Log ratio `ln(R/B)` | Same-field median/MAD robust centered scale |

Normalization happens only within a compatible field, time, entity type,
dataset, and acquisition cohort. Fitted parameters, clipping bounds, cohort
size, input manifest digest, and normalization version make the display value
reconstructable. A normalization failure withholds the observation.

## Physics-wide aggregation

Physics-wide values follow this required order:

```text
raw evidence
→ paper-time entity attribution
→ versioned field attribution
→ field-specific raw metric
→ field-specific normalization
→ Physics-domain aggregation
```

Aggregation version: `physics-field-balanced-coverage-aware-v1`.

Publication volume is used only as expected-evidence coverage, not as the final
field weight. For each entity, field-evidence coverage is:

```text
available expected field mass / total expected field mass
```

If coverage passes the configured threshold, the Physics-domain value is the
equal arithmetic mean of the available eligible field-normalized scores. A
large publishing field therefore cannot dominate solely through volume. A
missing field is not inserted as zero, and an entity is not duplicated across
fields. Branch and child results are never double-counted.

This policy is explicit and reproducible, but it remains experimental. A future
change to field balance or coverage handling requires a new aggregation
version.

## User-defined composite

The exploratory composite remains:

```text
H = Σ wi Mi
```

Users set nonnegative weights for exactly Activity, Impact, Connectivity,
Diversity, and Momentum. The confirmed total must equal exactly `100%`.
Invalid drafts do not update the map, and a missing required component is not
replaced by zero. Confirmation is explicit. Presets are perspectives, not an
official default ranking, and `H` must never be called an overall scientific
score.

## Activation status and limitations

The algorithms and provenance contracts are implemented for deterministic
testing. That does not establish representative coverage, construct validity,
bias control, external review, or live scientific readiness. The current
bounded `hep-th-v1` production dataset does not pass the complete five-metric
activation requirements. All five live metric layers remain withheld together.

See [Metric Validation](metric-validation.md) for thresholds, reference
ecosystem checks, and the Joint Activation Gate; [Scientific Attribution](scientific-attribution.md)
for the entity weights; and [Field Ontology](field-ontology.md) for
classification rules.
