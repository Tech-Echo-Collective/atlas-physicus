from __future__ import annotations

from datetime import date

from .contracts import CertificationError, EvidenceKind, canonical_digest


def _required(value: object, attribute: str) -> object:
    result = getattr(value, attribute, None)
    if result is None:
        raise CertificationError(f"paper projection lacks {attribute}")
    return result


def _required_string_tuple(value: object, attribute: str) -> tuple[str, ...]:
    result = _required(value, attribute)
    if not isinstance(result, tuple) or any(
        not isinstance(item, str) for item in result
    ):
        raise CertificationError(f"paper projection {attribute} is invalid")
    return result


def paper_evidence_value(
    partition: object,
    paper: object,
    evidence_kind: EvidenceKind,
) -> object:
    """Return the exact formula input certified by one paper decision.

    This is deliberately separate from the formula implementation.  It binds
    reviewed evidence decisions to the immutable values that a calculator will
    consume, without changing how any metric is calculated.
    """

    paper_id = _required(paper, "paper_id")
    field_id = _required(partition, "field_id")
    entity_type = _required(partition, "entity_type")
    entity_id = _required(partition, "entity_id")
    publication_date = _required(paper, "publication_date")
    if not isinstance(publication_date, date):
        raise CertificationError("paper projection publication date is invalid")

    common = {"paper_id": paper_id}
    values: dict[EvidenceKind, object] = {
        "canonical-paper-identity": common,
        "publication-metric-date": {
            **common,
            "publication_date": publication_date,
        },
        "researcher-identity": {
            **common,
            "researcher_ids": tuple(
                sorted(_required_string_tuple(paper, "researcher_ids"))
            ),
        },
        "paper-time-affiliation": {
            **common,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "attribution_weight": _required(paper, "attribution_weight"),
        },
        "canonical-institution": {
            **common,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "attribution_weight": _required(paper, "attribution_weight"),
        },
        "field-classification": {
            **common,
            "field_id": field_id,
            "attribution_weight": _required(paper, "attribution_weight"),
            "category_weights": _required(paper, "category_weights"),
        },
        "field-weight-conservation": {
            **common,
            "field_id": field_id,
            "attribution_weight": _required(paper, "attribution_weight"),
            "category_weights": _required(paper, "category_weights"),
        },
        "citation-observation": {
            **common,
            "field_id": field_id,
            "publication_year": publication_date.year,
            "document_type": _required(paper, "document_type"),
            "citation_count": getattr(paper, "citation_count", None),
        },
        "citation-cutoff-compatibility": {
            **common,
            "citation_observed_at": getattr(paper, "citation_observed_at", None),
        },
        "collaboration-relationship": {
            **common,
            "collaborative": getattr(paper, "collaborative", None),
            "cross_institution": getattr(paper, "cross_institution", None),
            "international": getattr(paper, "international", None),
            "partner_entity_ids": tuple(
                sorted(_required_string_tuple(paper, "partner_entity_ids"))
            ),
        },
        "provenance-completeness": {
            **common,
            "publication_date": publication_date,
            "document_type": _required(paper, "document_type"),
            "researcher_ids": tuple(
                sorted(_required_string_tuple(paper, "researcher_ids"))
            ),
            "field_id": field_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "attribution_weight": _required(paper, "attribution_weight"),
            "citation_count": getattr(paper, "citation_count", None),
            "citation_observed_at": getattr(paper, "citation_observed_at", None),
            "collaborative": getattr(paper, "collaborative", None),
            "cross_institution": getattr(paper, "cross_institution", None),
            "international": getattr(paper, "international", None),
            "partner_entity_ids": tuple(
                sorted(_required_string_tuple(paper, "partner_entity_ids"))
            ),
            "category_weights": _required(paper, "category_weights"),
        },
    }
    return values[evidence_kind]


def paper_evidence_value_digest(
    partition: object,
    paper: object,
    evidence_kind: EvidenceKind,
) -> str:
    return canonical_digest(paper_evidence_value(partition, paper, evidence_kind))
