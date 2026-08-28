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
            "A(e,f,t) = count(distinct canonical papers attributed to entity e, "
            "classified in field f, and published in the closed years t-2..t). "
            "For a science-domain scope, papers are deduplicated across field links."
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
            "Deduplicate canonical papers within each entity partition. Attribute a "
            "multi-institution paper to every reviewed participating affiliation; "
            "do not divide or assign ownership. Deduplicate papers again for field "
            "and science-domain totals."
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
            "at least 3 attributed distinct papers for the entity",
            "at least 30 eligible entities in the normalization cohort",
            "non-degenerate robust cohort bounds",
            "reviewed affiliation coverage for geographic observations",
        ),
        version="activity-output-participation-v1",
        algorithm_version="activity-distinct-paper-window-v1",
        normalization_version="robust-log-winsorized-cohort-v1",
        raw_unit="distinct attributed canonical papers",
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
            "Full participation attribution does not measure contribution size.",
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
            "For each eligible paper p, I_p is the midrank percentile of "
            "log1p(non-self citation count at the calculation cutoff) within the same "
            "field and publication-year cohort. I(e,f,t) is the arithmetic mean of "
            "I_p over eligible papers attributed to entity e in the selected window."
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
            "Deduplicate canonical papers, compute one eligible percentile per paper, "
            "then take the arithmetic mean for each supported entity partition. "
            "Multi-institution work may support every reviewed affiliation; output "
            "volume does not add a separate bonus."
        ),
        time_window=(
            "Papers in the selected closed three-year output window, observed no "
            "earlier than 24 months after publication."
        ),
        field_normalization=(
            "Calculate paper midrank percentiles only within the same field and "
            "publication-year cohort at a common citation cutoff."
        ),
        entity_normalization=(
            "Average eligible paper percentiles; do not add publication volume to the "
            "impact score."
        ),
        missing_data_behavior=(
            "A recorded zero citation count is valid; an absent or incomparable "
            "citation observation is missing and is excluded. Emit no entity "
            "observation when coverage thresholds fail."
        ),
        minimum_data_requirements=(
            "at least 5 mature eligible papers for the entity",
            "at least 80 percent citation-observation coverage",
            "at least 50 papers in every field-age normalization cohort",
            "a common recorded citation cutoff",
            "reviewed affiliation coverage for geographic observations",
        ),
        version="impact-field-age-percentile-v1",
        algorithm_version="impact-entity-mean-paper-percentile-v1",
        normalization_version="field-age-log-midrank-v1",
        raw_unit="mean same-field same-age paper percentile",
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
            "A mean percentile hides variation among an entity's papers.",
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
            "C(e,f,t) = count(distinct supported neighbors of entity e in papers "
            "classified in field f and published in the closed years t-2..t). "
            "Neighbors are coauthors for researchers, co-participating institutions "
            "for institutions, and co-participating countries for countries."
        ),
        input_observations=(
            "canonical papers and reviewed paper-field classifications",
            "resolved authorship edges",
            "paper-time reviewed affiliation edges",
            "institution location metadata for country relationships",
        ),
        aggregation_levels=("researcher", "institution", "country"),
        aggregation_rule=(
            "Count each directly supported neighbor once per entity partition. "
            "Repeated joint papers do not add neighbors, and no centrality or "
            "prestige weighting is applied."
        ),
        time_window="Three complete calendar years ending at the selected year.",
        field_normalization=(
            "Construct and normalize a separate direct-neighbor graph for each field "
            "or paper-deduplicated domain scope."
        ),
        entity_normalization=(
            "Apply log1p to distinct-neighbor count and robust 5th-to-95th-percentile "
            "cohort scaling separately by entity type, scope, and window."
        ),
        missing_data_behavior=(
            "Emit no observation when relationship or attribution coverage is below "
            "the minimum. Unresolved relationships are not treated as absent edges."
        ),
        minimum_data_requirements=(
            "complete acquisition coverage for all three years",
            "at least 3 attributed distinct papers for the entity",
            "at least 90 percent resolvable relationship coverage",
            "at least 30 eligible entities in the normalization cohort",
            "reviewed affiliations for institution and country observations",
        ),
        version="connectivity-distinct-partners-v1",
        algorithm_version="connectivity-direct-neighbor-count-v1",
        normalization_version="robust-log-winsorized-cohort-v1",
        raw_unit="distinct directly supported neighbors",
        normalized_range=(0.0, 100.0),
        provenance=_PROVENANCE,
        high_score_meaning=(
            "Distinct directly observed partner breadth lies nearer the upper end of "
            "the stored robust range fitted to the same cohort."
        ),
        low_score_meaning=(
            "Distinct directly observed partner breadth lies nearer the lower end of "
            "the stored robust range fitted to the same cohort."
        ),
        does_not_mean=(
            "prestige",
            "collaboration quality",
            "scientific value",
            "network centrality rank",
            "a cohort percentile",
            "individual contribution share",
        ),
        known_limitations=(
            "Incomplete identity or affiliation resolution removes observable edges.",
            "Large collaborations can dominate neighbor counts.",
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
            "Deduplicate canonical papers per entity and allocate each paper's total "
            "category weight fractionally across its reviewed labels, so one paper "
            "contributes one unit in total."
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
            "at least 10 attributed distinct papers for the entity",
            "at least 90 percent reviewed classification coverage",
            "complete acquisition coverage for all three years",
            "reviewed affiliation coverage for geographic observations",
        ),
        version="diversity-normalized-shannon-v1",
        algorithm_version="diversity-fractional-category-entropy-v1",
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
            "Let R be attributed Activity in years t-2..t and B be attributed "
            "Activity in years t-5..t-3. M_raw=(R-B)/(R+B), and the display score "
            "is M=50*(M_raw+1)."
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
            "The symmetric change ratio is directly bounded to [-1,1] and linearly "
            "mapped to [0,100]; no cohort rank is applied."
        ),
        missing_data_behavior=(
            "Emit no observation if either window is incomplete, version-incompatible, "
            "or below the minimum evidence threshold. Two absent windows are not "
            "zero momentum."
        ),
        minimum_data_requirements=(
            "complete acquisition coverage for all six years",
            "at least 10 attributed distinct papers across both windows",
            "compatible Activity definition, algorithm, and dataset scope",
            "reviewed affiliation coverage for geographic observations",
        ),
        version="momentum-symmetric-window-change-v1",
        algorithm_version="momentum-adjacent-three-year-change-v1",
        normalization_version="bounded-symmetric-change-v1",
        raw_unit="symmetric activity change ratio",
        normalized_range=(0.0, 100.0),
        provenance=_PROVENANCE,
        high_score_meaning=(
            "Observed publication participation is greater in the recent window than "
            "in the baseline window."
        ),
        low_score_meaning=(
            "Observed publication participation is lower in the recent window than "
            "in the baseline window."
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
