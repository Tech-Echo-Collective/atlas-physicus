"""Versioned provider-category mapping into the Atlas field ontology.

Provider classifications remain source evidence.  Mapping is exact and
versioned; it does not infer an Atlas field from a provider prefix, author
order, or the distinction between primary and secondary classifications.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Literal

from .ontology import PHYSICS_FIELD_ONTOLOGY_V1, PHYSICS_FIELD_ONTOLOGY_VERSION

Provider = Literal["arxiv", "inspire", "crossref"]
ProviderCategoryRole = Literal["primary", "secondary", "unspecified"]
MappingStatus = Literal["mapped", "unmapped"]

PROVIDER_FIELD_MAPPING_VERSION = "provider-field-mapping-v1"
FIELD_WEIGHTING_POLICY_VERSION = "equal-supported-fields-v1"

ARXIV_CATEGORY_TAXONOMY = "arxiv-category"
INSPIRE_CATEGORY_TAXONOMY = "inspire-category"
CROSSREF_SUBJECT_TAXONOMY = "crossref-subject"

_DEFAULT_TAXONOMY: Mapping[Provider, str] = MappingProxyType(
    {
        "arxiv": ARXIV_CATEGORY_TAXONOMY,
        "inspire": INSPIRE_CATEGORY_TAXONOMY,
        "crossref": CROSSREF_SUBJECT_TAXONOMY,
    }
)


@dataclass(frozen=True)
class ProviderCategoryEvidence:
    """One provider classification, retained even when no Atlas rule matches."""

    category: str
    role: ProviderCategoryRole = "unspecified"
    taxonomy: str | None = None
    scheme: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class FieldMappingRule:
    id: str
    provider: Provider
    taxonomy: str
    provider_category: str
    atlas_field_ids: tuple[str, ...]
    rationale: str
    mapping_version: str = PROVIDER_FIELD_MAPPING_VERSION
    ontology_version: str = PHYSICS_FIELD_ONTOLOGY_VERSION


@dataclass(frozen=True)
class CategoryMapping:
    evidence: ProviderCategoryEvidence
    status: MappingStatus
    atlas_field_ids: tuple[str, ...]
    rule_id: str | None
    uncertainty_note: str


@dataclass(frozen=True)
class AtlasFieldAssignment:
    field_id: str
    weight: float
    supporting_rule_ids: tuple[str, ...]
    provider_roles: tuple[ProviderCategoryRole, ...]


@dataclass(frozen=True)
class FieldMappingResult:
    """Reconstructable mapping outcome with a compatibility-facing API."""

    provider: Provider
    raw_categories: tuple[str, ...]
    category_mappings: tuple[CategoryMapping, ...]
    assignments: tuple[AtlasFieldAssignment, ...]
    mapping_coverage: float | None
    mapping_version: str = PROVIDER_FIELD_MAPPING_VERSION
    ontology_version: str = PHYSICS_FIELD_ONTOLOGY_VERSION
    weighting_policy_version: str = FIELD_WEIGHTING_POLICY_VERSION

    @property
    def atlas_field_ids(self) -> tuple[str, ...]:
        return tuple(assignment.field_id for assignment in self.assignments)

    @property
    def unmapped_categories(self) -> tuple[str, ...]:
        return tuple(
            result.evidence.category
            for result in self.category_mappings
            if result.status == "unmapped"
        )

    @property
    def confidence(self) -> None:
        """No calibrated probability is available for these deterministic rules."""

        return None

    @property
    def method(self) -> str:
        """Compatibility alias used by the existing materialization boundary."""

        return self.mapping_version

    @property
    def uncertainty_note(self) -> str:
        if self.unmapped_categories:
            return (
                "Provider classifications are evidence, not the Atlas ontology; "
                "one or more raw categories remain unmapped and no confidence "
                "probability has been calibrated."
            )
        return (
            "Provider classifications are evidence, not the Atlas ontology; "
            "the exact mapping rules have no calibrated confidence probability."
        )

    def provenance_payload(self) -> dict[str, object]:
        """Return JSON-compatible evidence for raw-record persistence."""

        return {
            "provider": self.provider,
            "ontology_version": self.ontology_version,
            "mapping_version": self.mapping_version,
            "weighting_policy_version": self.weighting_policy_version,
            "mapping_coverage": self.mapping_coverage,
            "confidence": None,
            "category_mappings": [
                {
                    "category": result.evidence.category,
                    "role": result.evidence.role,
                    "taxonomy": result.evidence.taxonomy,
                    "scheme": result.evidence.scheme,
                    "source": result.evidence.source,
                    "status": result.status,
                    "atlas_field_ids": list(result.atlas_field_ids),
                    "rule_id": result.rule_id,
                    "uncertainty_note": result.uncertainty_note,
                }
                for result in self.category_mappings
            ],
            "assignments": [
                {
                    "field_id": assignment.field_id,
                    "weight": assignment.weight,
                    "supporting_rule_ids": list(assignment.supporting_rule_ids),
                    "provider_roles": list(assignment.provider_roles),
                }
                for assignment in self.assignments
            ],
            "uncertainty_note": self.uncertainty_note,
        }


def _rule(
    provider: Provider,
    category: str,
    targets: tuple[str, ...],
    rationale: str,
    *,
    taxonomy: str | None = None,
) -> FieldMappingRule:
    rule_taxonomy = taxonomy or _DEFAULT_TAXONOMY[provider]
    safe_category = re.sub(r"[^a-z0-9]+", "-", category.casefold()).strip("-")
    return FieldMappingRule(
        id=f"{provider}-{safe_category}-{PROVIDER_FIELD_MAPPING_VERSION}",
        provider=provider,
        taxonomy=rule_taxonomy,
        provider_category=category,
        atlas_field_ids=targets,
        rationale=rationale,
    )


_ARXIV_RULES = (
    _rule("arxiv", "hep-th", ("hep-th",), "Direct high-energy theory category."),
    _rule("arxiv", "hep-ph", ("hep-ph",), "Direct HEP phenomenology category."),
    _rule("arxiv", "hep-ex", ("hep-ex",), "Direct HEP experiment category."),
    _rule("arxiv", "hep-lat", ("hep-lat",), "Direct HEP lattice category."),
    _rule("arxiv", "gr-qc", ("gr-qc",), "Direct gravitation and cosmology category."),
    _rule("arxiv", "quant-ph", ("quant-ph",), "Direct quantum science category."),
    _rule("arxiv", "math-ph", ("math-ph",), "Direct mathematical physics category."),
    _rule("arxiv", "nucl-th", ("nucl-th",), "Direct nuclear theory category."),
    _rule("arxiv", "nucl-ex", ("nucl-ex",), "Direct nuclear experiment category."),
    _rule("arxiv", "astro-ph", ("astro-ph",), "Legacy broad astrophysics category."),
    _rule(
        "arxiv",
        "astro-ph.CO",
        ("astro-ph", "gr-qc"),
        "Cosmology evidence supports both astrophysics and gravitation/cosmology.",
    ),
    *(
        _rule(
            "arxiv",
            category,
            ("astro-ph",),
            "Explicit arXiv astrophysics subcategory.",
        )
        for category in (
            "astro-ph.EP",
            "astro-ph.GA",
            "astro-ph.HE",
            "astro-ph.IM",
            "astro-ph.SR",
        )
    ),
    _rule(
        "arxiv",
        "cond-mat",
        ("cond-mat",),
        "Legacy broad condensed-matter category.",
    ),
    *(
        _rule(
            "arxiv",
            category,
            ("cond-mat",),
            "Explicit arXiv condensed-matter subcategory.",
        )
        for category in (
            "cond-mat.dis-nn",
            "cond-mat.mes-hall",
            "cond-mat.mtrl-sci",
            "cond-mat.other",
            "cond-mat.quant-gas",
            "cond-mat.str-el",
            "cond-mat.supr-con",
        )
    ),
    _rule(
        "arxiv",
        "cond-mat.soft",
        ("cond-mat", "soft-matter"),
        "Soft matter is retained in condensed matter and the interdisciplinary branch.",
    ),
    _rule(
        "arxiv",
        "cond-mat.stat-mech",
        ("cond-mat", "stat-nonlinear"),
        "Statistical mechanics supports both documented Atlas fields.",
    ),
    *(
        _rule(
            "arxiv",
            category,
            ("amo",),
            "Explicit atomic, molecular, or optical physics category.",
        )
        for category in ("physics.atom-ph", "physics.atm-clus", "physics.optics")
    ),
    _rule("arxiv", "physics.plasm-ph", ("plasma",), "Direct plasma physics category."),
    _rule(
        "arxiv",
        "physics.bio-ph",
        ("biophysics",),
        "Direct biological physics category.",
    ),
    *(
        _rule(
            "arxiv",
            category,
            ("stat-nonlinear",),
            "Explicit nonlinear sciences category.",
        )
        for category in ("nlin.AO", "nlin.CD", "nlin.CG", "nlin.PS", "nlin.SI")
    ),
)

_INSPIRE_RULES = (
    _rule("inspire", "Theory-HEP", ("hep-th",), "Direct INSPIRE HEP theory category."),
    _rule(
        "inspire",
        "Phenomenology-HEP",
        ("hep-ph",),
        "Direct INSPIRE HEP phenomenology category.",
    ),
    _rule(
        "inspire",
        "Experiment-HEP",
        ("hep-ex",),
        "Direct INSPIRE HEP experiment category.",
    ),
    _rule("inspire", "Lattice", ("hep-lat",), "Direct INSPIRE lattice category."),
    _rule(
        "inspire",
        "Gravitation and Cosmology",
        ("gr-qc",),
        "Direct INSPIRE gravitation and cosmology category.",
    ),
    _rule(
        "inspire",
        "Astrophysics",
        ("astro-ph",),
        "Direct INSPIRE astrophysics category.",
    ),
    _rule(
        "inspire",
        "Theory-Nucl",
        ("nucl-th",),
        "Direct INSPIRE nuclear theory category.",
    ),
    _rule(
        "inspire",
        "Nuclear Physics - Theory",
        ("nucl-th",),
        "Preserved legacy INSPIRE nuclear-theory spelling.",
    ),
    _rule(
        "inspire",
        "Experiment-Nucl",
        ("nucl-ex",),
        "Direct INSPIRE nuclear experiment category.",
    ),
    _rule(
        "inspire",
        "Nuclear Physics - Experiment",
        ("nucl-ex",),
        "Preserved legacy INSPIRE nuclear-experiment spelling.",
    ),
    _rule(
        "inspire",
        "Mathematical Physics",
        ("math-ph",),
        "Direct INSPIRE mathematical-physics category.",
    ),
    _rule(
        "inspire",
        "Math and Math Physics",
        ("math-ph",),
        "Preserved INSPIRE mathematical-physics spelling.",
    ),
)

_CROSSREF_RULES = (
    _rule(
        "crossref",
        "Atomic and Molecular Physics, and Optics",
        ("amo",),
        "Exact Crossref subject; retained as broad supporting evidence.",
    ),
    _rule(
        "crossref",
        "Condensed Matter Physics",
        ("cond-mat",),
        "Exact Crossref subject; retained as broad supporting evidence.",
    ),
    _rule(
        "crossref",
        "Nuclear and High Energy Physics",
        ("hep", "nuclear"),
        "Broad Crossref subject maps only to broad Atlas branches.",
    ),
    _rule(
        "crossref",
        "Astronomy and Astrophysics",
        ("astro-ph",),
        "Exact Crossref subject; retained as broad supporting evidence.",
    ),
    _rule("crossref", "Biophysics", ("biophysics",), "Exact Crossref subject."),
    _rule(
        "crossref",
        "Mathematical Physics",
        ("math-ph",),
        "Exact Crossref subject.",
    ),
    _rule("crossref", "Plasma Physics", ("plasma",), "Exact Crossref subject."),
)

PROVIDER_FIELD_MAPPING_RULES_V1 = (
    *_ARXIV_RULES,
    *_INSPIRE_RULES,
    *_CROSSREF_RULES,
)


def _build_rule_index() -> Mapping[tuple[Provider, str, str], FieldMappingRule]:
    index: dict[tuple[Provider, str, str], FieldMappingRule] = {}
    rule_ids: set[str] = set()
    for rule in PROVIDER_FIELD_MAPPING_RULES_V1:
        if rule.id in rule_ids:
            raise ValueError(f"Duplicate provider field-mapping rule ID: {rule.id}")
        if rule.mapping_version != PROVIDER_FIELD_MAPPING_VERSION:
            raise ValueError(f"Rule {rule.id} has an inconsistent mapping version")
        if rule.ontology_version != PHYSICS_FIELD_ONTOLOGY_VERSION:
            raise ValueError(f"Rule {rule.id} has an inconsistent ontology version")
        if not rule.atlas_field_ids:
            raise ValueError(f"Rule {rule.id} has no Atlas target")
        for field_id in rule.atlas_field_ids:
            if not PHYSICS_FIELD_ONTOLOGY_V1.contains(field_id):
                raise ValueError(f"Rule {rule.id} targets unknown field {field_id}")
        key = (rule.provider, rule.taxonomy, rule.provider_category)
        if key in index:
            raise ValueError(f"Duplicate provider field-mapping rule: {key}")
        index[key] = rule
        rule_ids.add(rule.id)
    return MappingProxyType(index)


_RULE_INDEX = _build_rule_index()


def _evidence(
    provider: Provider, value: str | ProviderCategoryEvidence
) -> ProviderCategoryEvidence:
    if isinstance(value, str):
        return ProviderCategoryEvidence(
            category=value,
            taxonomy=_DEFAULT_TAXONOMY[provider],
        )
    if value.taxonomy is None:
        return replace(value, taxonomy=_DEFAULT_TAXONOMY[provider])
    return value


def map_provider_categories(
    provider: Provider,
    categories: Sequence[str | ProviderCategoryEvidence],
) -> FieldMappingResult:
    """Map exact provider evidence and assign equal unique-field shares."""

    evidence = tuple(_evidence(provider, value) for value in categories)
    category_mappings: list[CategoryMapping] = []
    rule_support: dict[str, set[str]] = {}
    role_support: dict[str, set[ProviderCategoryRole]] = {}
    mapped_count = 0

    for item in evidence:
        taxonomy = item.taxonomy or _DEFAULT_TAXONOMY[provider]
        rule = _RULE_INDEX.get((provider, taxonomy, item.category))
        if rule is None:
            category_mappings.append(
                CategoryMapping(
                    evidence=item,
                    status="unmapped",
                    atlas_field_ids=(),
                    rule_id=None,
                    uncertainty_note=(
                        "No exact rule in provider-field-mapping-v1; the raw "
                        "category remains unassigned."
                    ),
                )
            )
            continue

        mapped_count += 1
        category_mappings.append(
            CategoryMapping(
                evidence=item,
                status="mapped",
                atlas_field_ids=rule.atlas_field_ids,
                rule_id=rule.id,
                uncertainty_note=(
                    "Exact versioned mapping; semantic confidence is not calibrated."
                ),
            )
        )
        for field_id in rule.atlas_field_ids:
            rule_support.setdefault(field_id, set()).add(rule.id)
            role_support.setdefault(field_id, set()).add(item.role)

    ordered_field_ids = sorted(
        rule_support,
        key=lambda field_id: PHYSICS_FIELD_ONTOLOGY_V1.get(field_id).display_order,
    )
    share = 1.0 / len(ordered_field_ids) if ordered_field_ids else 0.0
    role_order = {"primary": 0, "secondary": 1, "unspecified": 2}
    assignments = tuple(
        AtlasFieldAssignment(
            field_id=field_id,
            weight=share,
            supporting_rule_ids=tuple(sorted(rule_support[field_id])),
            provider_roles=tuple(
                sorted(
                    role_support[field_id],
                    key=lambda role: role_order[role],
                )
            ),
        )
        for field_id in ordered_field_ids
    )
    coverage = mapped_count / len(evidence) if evidence else None
    return FieldMappingResult(
        provider=provider,
        raw_categories=tuple(item.category for item in evidence),
        category_mappings=tuple(category_mappings),
        assignments=assignments,
        mapping_coverage=coverage,
    )
