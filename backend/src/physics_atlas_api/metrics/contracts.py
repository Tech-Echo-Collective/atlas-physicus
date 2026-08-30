from dataclasses import dataclass
from typing import Literal

MetricScientificStatus = Literal["experimental-candidate", "validated"]


@dataclass(frozen=True)
class MetricContractProvenance:
    source: str
    source_scope: str
    status: MetricScientificStatus


@dataclass(frozen=True)
class MetricScientificContract:
    metric_id: str
    name: str
    interpretation: str
    formula: str
    input_observations: tuple[str, ...]
    aggregation_levels: tuple[str, ...]
    aggregation_rule: str
    time_window: str
    field_normalization: str
    entity_normalization: str
    missing_data_behavior: str
    minimum_data_requirements: tuple[str, ...]
    version: str
    algorithm_version: str
    normalization_version: str
    raw_unit: str
    normalized_range: tuple[float, float]
    provenance: MetricContractProvenance
    high_score_meaning: str
    low_score_meaning: str
    does_not_mean: tuple[str, ...]
    known_limitations: tuple[str, ...]

    @property
    def implementation_status(self) -> MetricScientificStatus:
        return self.provenance.status

    def required_data_metadata(self) -> list[str]:
        """Return versioned registry metadata without implying activation."""
        return [
            f"contract-version:{self.version}",
            f"algorithm-version:{self.algorithm_version}",
            f"normalization-version:{self.normalization_version}",
            f"source-scope:{self.provenance.source_scope}",
            f"raw-unit:{self.raw_unit}",
            *(f"input:{item}" for item in self.input_observations),
            *(f"minimum:{item}" for item in self.minimum_data_requirements),
        ]


_PROVENANCE = MetricContractProvenance(
    source="Physics Atlas v3.0.5 candidate metric methodology",
    source_scope="hep-th-v1",
    status="experimental-candidate",
)


METRIC_CONTRACTS: dict[str, MetricScientificContract] = {
    "research_activity_score": MetricScientificContract(
        metric_id="research_activity_score",
        name="Research Activity",
        interpretation=(
            "Observed publication participation within a defined field, entity type, "
            "and closed time window; it describes output volume, not research quality."
        ),
        formula=(
            "A(e,f,t) = sum_p w(p,e) * s(p,f) over canonical papers in the "
            "closed years t-2..t. w(p,e) is the conserved paper-time fractional "
            "entity attribution and s(p,f) is the versioned field share."
        ),
        input_observations=(
            "canonical paper identifier and publication year",
            "reviewed paper-field classification",
            "authorship for researcher aggregation",
            "paper-time reviewed affiliation and institution location for "
            "geographic aggregation",
        ),
        aggregation_levels=(
            "researcher",
            "institution",
            "country",
            "research-field",
            "science-domain",
        ),
        aggregation_rule=(
            "Each paper has total attribution one. Equal author shares are divided "
            "equally across each author's valid paper-time affiliations, then by the "
            "versioned paper-field shares. Unresolved mass is not redistributed."
        ),
        time_window="Three complete calendar years ending at the selected year.",
        field_normalization=(
            "Normalize only inside one field or a paper-deduplicated science-domain "
            "cohort; do not compare raw counts across fields."
        ),
        entity_normalization=(
            "Apply log1p to the raw count and robust 5th-to-95th-percentile cohort "
            "scaling separately for entity type, scope, and window."
        ),
        missing_data_behavior=(
            "Emit no observation when source-window coverage, attribution, or cohort "
            "requirements fail. Absence is not converted to zero."
        ),
        minimum_data_requirements=(
            "complete acquisition coverage for all three years",
            "at least 10 fractional papers for the entity",
            "at least 5 distinct identifiable researchers",
            "at least 30 eligible entities in the normalization cohort",
            "non-degenerate robust cohort bounds",
            "reviewed affiliation coverage for geographic observations",
        ),
        version="activity-fractional-output-v1",
        algorithm_version="activity-field-weighted-fractional-publication-v1",
        normalization_version="robust-log-winsorized-cohort-v1",
        raw_unit="fractional attributed canonical papers",
        normalized_range=(0.0, 100.0),
        provenance=_PROVENANCE,
        high_score_meaning=(
            "Observed publication participation lies nearer the upper end of the "
            "stored robust range fitted to the same documented cohort."
        ),
        low_score_meaning=(
            "Observed publication participation lies nearer the lower end of the "
            "stored robust range fitted to the same documented cohort."
        ),
        does_not_mean=(
            "research quality",
            "scientific value",
            "institutional or researcher rank",
            "a cohort percentile",
            "individual contribution share",
        ),
        known_limitations=(
            "Publication databases have field-, source-, and language-dependent "
            "coverage.",
            "Equal fractional attribution is a conservative counting policy, not a "
            "claim about intellectual contribution.",
            "Entity size and collaboration practices affect output counts.",
            "The winsorized linear display score is cohort-relative; it is neither "
            "an absolute quantity nor a percentile.",
        ),
    ),
    "research_impact": MetricScientificContract(
        metric_id="research_impact",
        name="Research Impact",
        interpretation=(
            "Recorded citation attention relative to papers of similar field and age; "
            "it is not a measure of scientific value or institutional quality."
        ),
        formula=(
            "For each mature eligible paper p, NCS_p is its citation count divided "
            "by the mean citation count in the same field, publication year, and "
            "document type at a common cutoff. I(e,f,t) is the fractional-attribution "
            "weighted mean NCS (MNCS). PP(top 10%) is preserved as companion evidence."
        ),
        input_observations=(
            "canonical paper identifier and publication year",
            "reviewed paper-field classification",
            "timestamped non-self citation count",
            "citation observation cutoff",
            "reviewed authorship and affiliation attribution",
        ),
        aggregation_levels=("researcher", "institution", "country"),
        aggregation_rule=(
            "Deduplicate canonical papers and weight each eligible paper by its "
            "conserved entity and field attribution. Average paper NCS values by "
            "those weights; publication volume does not add a separate bonus."
        ),
        time_window=(
            "Papers in the selected closed three-year output window, observed no "
            "earlier than 24 months after publication."
        ),
        field_normalization=(
            "Calculate expected citations within the same field, publication year, "
            "document type, and common citation cutoff."
        ),
        entity_normalization=(
            "Preserve raw MNCS and map it to the display range using stored robust "
            "same-field entity-cohort parameters."
        ),
        missing_data_behavior=(
            "A recorded zero citation count is valid; an absent or incomparable "
            "citation observation is missing and is excluded. Emit no entity "
            "observation when coverage thresholds fail."
        ),
        minimum_data_requirements=(
            "at least 10 mature eligible papers for the entity",
            "at least 90 percent citation-observation coverage",
            "at least 50 papers in every field-age normalization cohort",
            "a common recorded citation cutoff",
            "reviewed affiliation coverage for geographic observations",
        ),
        version="impact-fractional-mncs-pp10-v1",
        algorithm_version="impact-field-year-document-fractional-mncs-v1",
        normalization_version="field-year-document-mncs-robust-v1",
        raw_unit="fractional mean normalized citation score (MNCS)",
        normalized_range=(0.0, 100.0),
        provenance=_PROVENANCE,
        high_score_meaning=(
            "The entity's eligible papers received more recorded citation attention, "
            "on average, than same-field and same-age comparison papers."
        ),
        low_score_meaning=(
            "The entity's eligible papers received less recorded citation attention, "
            "on average, than same-field and same-age comparison papers."
        ),
        does_not_mean=(
            "scientific correctness",
            "scientific value",
            "research quality",
            "future influence",
            "institutional or researcher rank",
        ),
        known_limitations=(
            "Citation practices and database coverage differ across fields and "
            "sources.",
            "Citation counts remain mutable and cannot remove every form of age bias.",
            "Non-self-citation metadata can be incomplete or provider-specific.",
            "MNCS and PP(top 10%) each hide variation among an entity's papers.",
        ),
    ),
    "collaboration": MetricScientificContract(
        metric_id="collaboration",
        name="Collaboration / Connectivity",
        interpretation=(
            "Breadth of directly supported scientific relationships in a bounded "
            "co-participation graph; it does not encode prestige or collaboration "
            "quality."
        ),
        formula=(
            "C(e,f,t) is an entity-type-specific fractional publication proportion: "
            "collaborative papers for researchers, cross-institution papers for "
            "institutions, and international papers for countries."
        ),
        input_observations=(
            "canonical papers and reviewed paper-field classifications",
            "resolved authorship edges",
            "paper-time reviewed affiliation edges",
            "institution location metadata for country relationships",
        ),
        aggregation_levels=("researcher", "institution", "country"),
        aggregation_rule=(
            "Weight numerator and denominator by conserved entity and field "
            "attribution. Preserve partner counts and graph edges as companion "
            "evidence; no centrality or prestige weighting is applied."
        ),
        time_window="Three complete calendar years ending at the selected year.",
        field_normalization=(
            "Calculate each proportion within one field, entity type, closed window, "
            "dataset, and acquisition scope before any Physics-wide aggregation."
        ),
        entity_normalization=(
            "The primary proportion is naturally bounded and maps directly from "
            "[0,1] to [0,100] within the exact field/entity/window partition."
        ),
        missing_data_behavior=(
            "Emit no observation when relationship or attribution coverage is below "
            "the minimum. Unresolved relationships are not treated as absent edges."
        ),
        minimum_data_requirements=(
            "complete acquisition coverage for all three years",
            "at least 10 fractional papers for the entity",
            "at least 5 identifiable researchers",
            "at least 90 percent resolvable relationship coverage",
            "at least 30 eligible entities in the normalization cohort",
            "reviewed affiliations for institution and country observations",
        ),
        version="connectivity-collaboration-proportions-v1",
        algorithm_version="connectivity-fractional-collaboration-share-v1",
        normalization_version="bounded-collaboration-proportion-v1",
        raw_unit="fractional collaborative publication proportion",
        normalized_range=(0.0, 100.0),
        provenance=_PROVENANCE,
        high_score_meaning=(
            "A greater share of the supported publication evidence contains the "
            "entity-type-specific collaboration relationship."
        ),
        low_score_meaning=(
            "A smaller share of the supported publication evidence contains the "
            "entity-type-specific collaboration relationship."
        ),
        does_not_mean=(
            "prestige",
            "collaboration quality",
            "scientific value",
            "network centrality rank",
            "individual contribution share",
        ),
        known_limitations=(
            "Incomplete identity or affiliation resolution removes observable edges.",
            "Large collaborations affect companion partner counts even though the "
            "primary scalar is a bounded publication proportion.",
            "Direct-neighbor breadth does not describe relationship strength.",
            "The candidate deliberately avoids centrality-based prestige signals.",
        ),
    ),
    "research_diversity": MetricScientificContract(
        metric_id="research_diversity",
        name="Research Diversity",
        interpretation=(
            "Evenness of observed research participation across a reviewed category "
            "set; greater breadth is descriptive and is not automatically better."
        ),
        formula=(
            "Each paper assigned to k eligible categories contributes 1/k to each. "
            "Let q_j be entity e's resulting share in category j. "
            "D(e,t) = 100 * (-sum_j(q_j * ln(q_j))) / ln(K), where K is the "
            "documented eligible category count."
        ),
        input_observations=(
            "canonical papers and publication years",
            "reviewed multi-label field or subfield classifications",
            "documented eligible category universe",
            "reviewed authorship and affiliation attribution",
        ),
        aggregation_levels=("researcher", "institution", "country"),
        aggregation_rule=(
            "Use conserved entity attribution and allocate each paper's field share "
            "across its reviewed labels, so unresolved mass is not redistributed and "
            "a paper cannot contribute more than its supported fractional share."
        ),
        time_window="Three complete calendar years ending at the selected year.",
        field_normalization=(
            "Use one versioned category universe for the selected domain or field; "
            "do not compare scores produced from different taxonomies."
        ),
        entity_normalization=(
            "Normalized Shannon evenness is already bounded from 0 to 100; no "
            "cross-entity percentile transform is applied."
        ),
        missing_data_behavior=(
            "Emit no observation when the category universe, classification coverage, "
            "or entity sample is insufficient. Unclassified papers are not assigned "
            "to a synthetic category or counted as zero diversity."
        ),
        minimum_data_requirements=(
            "at least 2 reviewed eligible categories",
            "at least 15 fractional papers for the entity",
            "at least 90 percent reviewed classification coverage",
            "complete acquisition coverage for all three years",
            "reviewed affiliation coverage for geographic observations",
        ),
        version="diversity-normalized-shannon-v1",
        algorithm_version="diversity-attributed-category-entropy-v1",
        normalization_version="normalized-shannon-evenness-v1",
        raw_unit="normalized Shannon evenness",
        normalized_range=(0.0, 100.0),
        provenance=_PROVENANCE,
        high_score_meaning=(
            "Observed participation is spread more evenly across the documented "
            "eligible categories."
        ),
        low_score_meaning=(
            "Observed participation is concentrated in fewer documented categories."
        ),
        does_not_mean=(
            "research quality",
            "interdisciplinary value",
            "resilience",
            "institutional or researcher rank",
        ),
        known_limitations=(
            "Results depend strongly on taxonomy design and classification quality.",
            "The hep-th-v1 acquisition boundary is conditioned on one field.",
            "Multi-label fractional assignment is a counting convention, not "
            "contribution allocation.",
            "Small publication sets produce unstable breadth estimates.",
        ),
    ),
    "momentum": MetricScientificContract(
        metric_id="momentum",
        name="Research Momentum",
        interpretation=(
            "Observed change in publication participation between two complete equal "
            "historical windows; it is descriptive and is not a prediction."
        ),
        formula=(
            "Let R be fractional Activity in years t-2..t and B be fractional "
            "Activity in years t-5..t-3. g(e)=log(R/B). Subtract the same-field "
            "cohort median g and apply the stored robust median/MAD display transform."
        ),
        input_observations=(
            "version-compatible raw Research Activity counts",
            "six complete calendar years of source coverage",
            "stable entity and affiliation resolution across both windows",
        ),
        aggregation_levels=(
            "researcher",
            "institution",
            "country",
            "research-field",
            "science-domain",
        ),
        aggregation_rule=(
            "Use version-compatible, distinct-paper Activity counts for the exact "
            "same entity partition in both windows; do not extrapolate or pool "
            "different scopes."
        ),
        time_window=(
            "Two adjacent three-year windows: baseline t-5..t-3 and recent t-2..t."
        ),
        field_normalization=(
            "Compare only version-compatible Activity observations from the same field "
            "or paper-deduplicated domain scope."
        ),
        entity_normalization=(
            "Subtract the same-field cohort median log change, scale by stored robust "
            "dispersion, clip only at documented bounds, and map to [0,100]."
        ),
        missing_data_behavior=(
            "Emit no observation if either window is incomplete, version-incompatible, "
            "or below the minimum evidence threshold. Missing windows are not a "
            "field-median Momentum observation."
        ),
        minimum_data_requirements=(
            "complete acquisition coverage for all six years",
            "at least 10 fractional papers in each three-year window",
            "compatible Activity definition, algorithm, and dataset scope",
            "reviewed affiliation coverage for geographic observations",
        ),
        version="momentum-field-relative-log-change-v1",
        algorithm_version="momentum-adjacent-window-relative-log-change-v1",
        normalization_version="field-relative-robust-log-change-v1",
        raw_unit="relative log fractional activity change",
        normalized_range=(0.0, 100.0),
        provenance=_PROVENANCE,
        high_score_meaning=(
            "Observed fractional publication activity changed more positively than "
            "the same-field cohort median between the two completed windows."
        ),
        low_score_meaning=(
            "Observed fractional publication activity changed less positively than "
            "the same-field cohort median between the two completed windows."
        ),
        does_not_mean=(
            "future growth",
            "future decline",
            "scientific sustainability",
            "research quality",
            "institutional or researcher rank",
        ),
        known_limitations=(
            "Boundary changes and retrospective provider corrections can affect "
            "windows.",
            "The ratio is unstable for sparse entities, hence the evidence threshold.",
            "Observed change does not explain its causes or persistence.",
            "The candidate measures momentum only and does not prove sustainability.",
        ),
    ),
}

CANDIDATE_METRIC_IDS = tuple(METRIC_CONTRACTS)


def get_metric_contract(metric_id: str) -> MetricScientificContract | None:
    return METRIC_CONTRACTS.get(metric_id)
