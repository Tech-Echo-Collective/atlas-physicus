from dataclasses import dataclass
from typing import Literal

Provider = Literal["arxiv", "inspire", "crossref"]


@dataclass(frozen=True)
class FieldMappingResult:
    """Explicit, uncertainty-bearing bridge from provider labels to Atlas fields."""

    raw_categories: tuple[str, ...]
    atlas_field_ids: tuple[str, ...]
    confidence: float
    method: str = "provider-category-rules-v1"
    uncertainty_note: str = (
        "Provider categories are acquisition metadata, not a definitive "
        "scientific taxonomy."
    )


ARXIV_CATEGORY_MAP: dict[str, tuple[str, ...]] = {
    "hep-th": ("hep-th",),
    "hep-ph": ("hep-ph",),
    "hep-ex": ("hep-ex",),
    "hep-lat": ("hep-th", "hep-ph"),
    "gr-qc": ("gr-qc",),
    "quant-ph": ("quant-ph",),
    "astro-ph": ("astro-ph",),
    "astro-ph.CO": ("astro-ph", "gr-qc"),
    "astro-ph.HE": ("astro-ph", "hep-ph"),
    "cond-mat": ("cond-mat",),
    "cond-mat.mes-hall": ("cond-mat",),
    "cond-mat.stat-mech": ("cond-mat", "math-ph"),
    "physics.atom-ph": ("amo",),
    "physics.chem-ph": ("amo",),
    "nucl-th": ("nucl-th",),
    "nucl-ex": ("nucl-ex",),
    "physics.plasm-ph": ("plasma",),
    "physics.bio-ph": ("biophysics",),
    "q-bio": ("biophysics",),
    "math-ph": ("math-ph",),
}

INSPIRE_CATEGORY_MAP: dict[str, tuple[str, ...]] = {
    "Theory-HEP": ("hep-th",),
    "Phenomenology-HEP": ("hep-ph",),
    "Experiment-HEP": ("hep-ex",),
    "Gravitation and Cosmology": ("gr-qc", "astro-ph"),
    "Lattice": ("hep-th", "hep-ph"),
    "Nuclear Physics - Theory": ("nucl-th",),
    "Nuclear Physics - Experiment": ("nucl-ex",),
    "Mathematical Physics": ("math-ph",),
}

CROSSREF_SUBJECT_MAP: dict[str, tuple[str, ...]] = {
    "Atomic and Molecular Physics, and Optics": ("amo",),
    "Condensed Matter Physics": ("cond-mat",),
    "Nuclear and High Energy Physics": ("hep-ph", "hep-ex", "nucl-th", "nucl-ex"),
    "Astronomy and Astrophysics": ("astro-ph",),
    "Biophysics": ("biophysics",),
    "Mathematical Physics": ("math-ph",),
    "Plasma Physics": ("plasma",),
}


def map_provider_categories(
    provider: Provider, categories: list[str]
) -> FieldMappingResult:
    mapping = {
        "arxiv": ARXIV_CATEGORY_MAP,
        "inspire": INSPIRE_CATEGORY_MAP,
        "crossref": CROSSREF_SUBJECT_MAP,
    }[provider]
    field_ids: list[str] = []
    matched = 0
    for category in categories:
        direct = mapping.get(category)
        if direct is None and provider == "arxiv":
            prefix = category.split(".", 1)[0]
            direct = mapping.get(prefix)
        if direct:
            matched += 1
            field_ids.extend(direct)
    unique = tuple(dict.fromkeys(field_ids))
    confidence = (
        round(0.55 + 0.35 * (matched / max(1, len(categories))), 2) if unique else 0.0
    )
    return FieldMappingResult(tuple(categories), unique, confidence)
