# Metric System v1 dual-track Joint Activation assessment

Date: 2026-09-04

Status: **WITHHELD for all five metrics; Full Physics loading unauthorized;
production unchanged**.

This report compares the preserved `hep-th-v1` baseline with the completed
`cond-mat-validation-v1` trial. Both are specialty-field, `field-conditioned`
tracks. They are shown side by side only: this report does not average their
coverages, add their denominators, or claim a paper-deduplicated union.

## Source evidence

- Preserved [`hep-th-v1` canonical replay](metric-system-v1-hep-th-2020-2025-canonical-replay.md)
  (report-file SHA-256
  `a1698b145869a9f0965d44a31beea39cdd91cf97f92d3071fcd22bc974a17e3d`):
  source manifest
  `e3dba5492e0dee3fb0b359cd90acd9cc07991e83b89cb6f16c49b498c4e65536`,
  replay bundle
  `d125a0861df03c5e1e7e20202db06f7d2506e0e8e9fb3fca732e7208f4349d82`,
  and institution-resolution manifest
  `4e0f58bdc4d44836e013a2b311998858e4a1894bcecd06d617e2cfa5211ece38`.
- Completed [`cond-mat-validation-v1` validation](metric-system-v1-cond-mat-2020-2025-validation.md)
  (report-file SHA-256
  `0db5fa4a66adc1478da8856ee5fea5bcde0999894af6e70326ea1c7555401cfe`):
  source manifest
  `484880ef2fd03163b393fff2a38a1901340550d5423da058c43f5210c9ed0384`,
  replay bundle / field-conditioned `dataSourceVersion`
  `26c51e77b696e2d4d3636074107f0751be9289b9e95f62f837abd8b106f8376f`,
  and content-addressed replay report
  `8d9b04e2616ee8450b7aef919f3dfded2bcb8004c9f4c031fb6aade96f3409cd`.

The original `hep-th-v1` row artifacts are no longer available. Its fractional
mass values below therefore retain the six-decimal precision of the preserved
report; no more exact fraction is invented.

## Separate evidence and threshold deficits

| Activation evidence | `hep-th-v1` (47,726 papers) | `cond-mat-validation-v1` (129,464 papers) |
| --- | --- | --- |
| Paper-time affiliation, minimum 90% | Reported 42,601.726004 / 47,726 = 89.263140%; short by at least 351.673996 paper units | Exact mass `575138025696274847 / 17485049181600`; exact coverage `575138025696274847 / 2263684407246662400` = 25.407165%; short by exactly `1462177940825721313 / 17485049181600` = 83,624.468289 paper units |
| Activation-eligible canonical institution, minimum 95% | Reported 16,689.396051 / 47,726 = 34.969191%; short by at least 28,650.303949 paper units | `None` over the known 129,464-paper denominator; the required numerator is at least `614954 / 5` = 122,990.8 paper units, but the deficit is not measurable because no eligible numerator was materialized |
| Common-cutoff comparable citation, minimum 90% | 0 / 47,726; needs at least 42,954 comparable papers | 0 / 129,464; needs at least 116,518 comparable papers |
| Reviewed field attribution, minimum 90% | 0 / 47,726; needs at least 42,954 reviewed ledgers | 0 / 129,464; needs at least 116,518 reviewed ledgers |
| Certified canonical years | 0 / 6; six remain | 0 / 6; six remain |
| Ready Momentum windows | 0 / 2; both remain | 0 / 2; both remain |
| Metric observations created | 0 | 0 |

For Condensed Matter, zero canonical institutions and researchers were
materialized, but that entity count does not turn canonical-institution
coverage into `0%`; the coverage numerator remains unmeasured. Resolved
relationship coverage and eligible normalization cohorts are likewise not
measurable in either comparison track. Raw record volume, raw citation
presence, event-date coverage, and unreviewed field mass are not substitutes
for the activation denominators above.

## Five-metric result

| Metric | `hep-th-v1` | `cond-mat-validation-v1` | Dual-track decision |
| --- | --- | --- | --- |
| Activity | Withheld | Withheld | **WITHHELD** |
| Impact | Withheld | Withheld | **WITHHELD** |
| Connectivity | Withheld | Withheld | **WITHHELD** |
| Diversity | Withheld; field-conditioned | Withheld; field-conditioned | **WITHHELD**; two specialty trials are not broad Physics |
| Momentum | Withheld | Withheld | **WITHHELD** |

## Exact Joint Activation Gate execution

The gate input uses the non-registered comparison label
`comparison-only:[hep-th-v1,cond-mat-validation-v1]`; it is not an acquisition
scope or a combined dataset. Its boundary is `field-conditioned`. Because no
deduplicated cross-track replay exists, combined affiliation and institution
coverages and `data_source_version` are `null`. Comparable-citation and reviewed
field coverages are exactly zero in both positive-denominator tracks, so zero
remains valid without combining denominators.

Exact input to `assess_joint_metric_activation`:

```json
{
  "acquisition_boundary_kind": "field-conditioned",
  "acquisition_scope": "comparison-only:[hep-th-v1,cond-mat-validation-v1]",
  "algorithms": [
    {
      "algorithm_version": "activity-field-weighted-fractional-publication-v1",
      "definition_version": "activity-fractional-output-v1",
      "deterministic_reproduction_passed": true,
      "implemented": true,
      "metric_id": "research_activity_score",
      "normalization_version": "robust-log-winsorized-cohort-v1"
    },
    {
      "algorithm_version": "impact-field-year-document-fractional-mncs-v1",
      "definition_version": "impact-fractional-mncs-pp10-v1",
      "deterministic_reproduction_passed": true,
      "implemented": true,
      "metric_id": "research_impact",
      "normalization_version": "field-year-document-mncs-robust-v1"
    },
    {
      "algorithm_version": "connectivity-fractional-collaboration-share-v1",
      "definition_version": "connectivity-collaboration-proportions-v1",
      "deterministic_reproduction_passed": true,
      "implemented": true,
      "metric_id": "collaboration",
      "normalization_version": "bounded-collaboration-proportion-v1"
    },
    {
      "algorithm_version": "diversity-attributed-category-entropy-v1",
      "definition_version": "diversity-normalized-shannon-v1",
      "deterministic_reproduction_passed": true,
      "implemented": true,
      "metric_id": "research_diversity",
      "normalization_version": "normalized-shannon-evenness-v1"
    },
    {
      "algorithm_version": "momentum-adjacent-window-relative-log-change-v1",
      "definition_version": "momentum-field-relative-log-change-v1",
      "deterministic_reproduction_passed": true,
      "implemented": true,
      "metric_id": "momentum",
      "normalization_version": "field-relative-robust-log-change-v1"
    }
  ],
  "attribution_policy_version": "fractional-attribution-v1",
  "attribution_validation_passed": true,
  "citation_maturity_validated": false,
  "coverage": {
    "canonical_institution": null,
    "citation": 0.0,
    "field_attribution": 0.0,
    "paper_time_affiliation": null
  },
  "data_source_version": null,
  "deterministic_reproduction_passed": true,
  "diversity_breadth_review_passed": false,
  "diversity_breadth_review_version": null,
  "field_reconciliation_version": "cross-provider-field-reconciliation-v1",
  "field_weight_conservation_passed": true,
  "field_weighting_policy_version": "provider-evidence-conservation-v2",
  "historical_coverage_validated": false,
  "metric_system_version": "physics-atlas-metric-system-v1",
  "normalization_validated": false,
  "ontology_version": "physics-field-ontology-v1",
  "provenance_complete": false,
  "provider_mapping_versions": [
    ["inspire", "provider-field-mapping-v1"],
    ["arxiv", "provider-field-mapping-v1"]
  ],
  "threshold_version": "metric-validation-thresholds-v1"
}
```

Exact result:

```json
{
  "may_activate": false,
  "metric_ids": [
    "research_activity_score",
    "research_impact",
    "collaboration",
    "research_diversity",
    "momentum"
  ],
  "metric_system_version": "physics-atlas-metric-system-v1",
  "reasons": [
    "the acquisition boundary is not certified as broad Physics evidence",
    "data source version is missing",
    "Diversity breadth-review version does not match the contract",
    "broad-field Research Diversity review has not passed",
    "paper-time affiliation coverage is below 90%",
    "canonical institution coverage is below 95%",
    "citation coverage is below 90%",
    "field attribution coverage is below 90%",
    "six-year closed-window historical coverage is not validated",
    "citation-age and common-cutoff handling are not validated",
    "metric-specific normalization validation has not passed",
    "reconstruction provenance is incomplete"
  ],
  "status": "withheld"
}
```

This is a comparison-only gate evaluation, not a reviewed activation manifest.
It authorizes neither a combined corpus nor Full Physics acquisition. Public
Metric System v1 observations remain zero, and production remains
`hep-th-v1`-only.
