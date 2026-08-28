import hashlib
import re
import unicodedata

from sqlalchemy import delete
from sqlalchemy.orm import Session

from . import models


def normalize_search_term(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    normalized = ascii_value.casefold().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def _lookup_variants(value: str) -> set[str]:
    normalized = normalize_search_term(value)
    tokens = {item for item in re.split(r"[^a-z0-9]+", normalized) if len(item) >= 2}
    return {normalized, *tokens}


def refresh_search_terms(
    session: Session,
    *,
    entity_type: str,
    entity_id: str,
    canonical_name: str,
    aliases: list[str],
    historical_names: list[str],
    external_ids: list[dict[str, str]],
) -> None:
    """Replace one canonical entity's compact, indexed evidence projection."""
    session.execute(
        delete(models.EntitySearchTerm).where(
            models.EntitySearchTerm.entity_type == entity_type,
            models.EntitySearchTerm.entity_id == entity_id,
        )
    )
    evidence = [
        ("canonical-name", canonical_name),
        *(("alias", value) for value in aliases),
        *(("historical-name", value) for value in historical_names),
        *(
            ("external-identifier", str(value.get("value", "")))
            for value in external_ids
            if value.get("value")
        ),
    ]
    seen: set[tuple[str, str]] = set()
    for match_method, display_value in evidence:
        for lookup_value in _lookup_variants(display_value):
            key = (match_method, lookup_value)
            if key in seen:
                continue
            seen.add(key)
            digest = hashlib.sha256(
                f"{entity_type}:{entity_id}:{match_method}:{lookup_value}".encode()
            ).hexdigest()[:28]
            session.add(
                models.EntitySearchTerm(
                    id=f"search-term-{digest}",
                    entity_type=entity_type,
                    entity_id=entity_id,
                    term=display_value,
                    normalized_term=lookup_value,
                    match_method=match_method,
                )
            )
