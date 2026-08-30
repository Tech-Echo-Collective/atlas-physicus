"""Compatibility import for the scientific field-mapping boundary.

Provider connectors historically imported mapping from this module. The
implementation now belongs to :mod:`physics_atlas_api.fields`, keeping source
normalization separate from the canonical Atlas ontology.
"""

from ..fields.mapping import (
    ARXIV_CATEGORY_TAXONOMY,
    CROSSREF_SUBJECT_TAXONOMY,
    FIELD_WEIGHTING_POLICY_VERSION,
    INSPIRE_CATEGORY_TAXONOMY,
    PROVIDER_FIELD_MAPPING_RULES_V1,
    PROVIDER_FIELD_MAPPING_VERSION,
    AtlasFieldAssignment,
    CategoryMapping,
    FieldMappingResult,
    FieldMappingRule,
    Provider,
    ProviderCategoryEvidence,
    ProviderCategoryRole,
    map_provider_categories,
)

__all__ = [
    "ARXIV_CATEGORY_TAXONOMY",
    "CROSSREF_SUBJECT_TAXONOMY",
    "FIELD_WEIGHTING_POLICY_VERSION",
    "INSPIRE_CATEGORY_TAXONOMY",
    "PROVIDER_FIELD_MAPPING_RULES_V1",
    "PROVIDER_FIELD_MAPPING_VERSION",
    "AtlasFieldAssignment",
    "CategoryMapping",
    "FieldMappingResult",
    "FieldMappingRule",
    "Provider",
    "ProviderCategoryEvidence",
    "ProviderCategoryRole",
    "map_provider_categories",
]
