"""Paper-time affiliation extraction, conservative resolution, and persistence."""

import hashlib
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import models
from ..connectors.base import NormalizedRecord, normalize_external_id
from ..search_index import normalize_search_term
from .contracts import (
    FRACTIONAL_ATTRIBUTION_V1,
    AuthorAttributionInput,
    ContributionEvidence,
    PaperTimeAffiliationAssertion,
)
from .fractional import FractionalAttributionResult, calculate_fractional_attribution

MATERIALIZATION_VERSION = "paper-time-affiliation-materialization-v1"


@dataclass(frozen=True)
class MaterializedAuthorIdentity:
    author_position: int
    raw_author_name: str
    researcher_id: str | None
    authorship_id: str | None
    resolution_status: str


@dataclass(frozen=True)
class _AssertionEvidence:
    assertion: PaperTimeAffiliationAssertion
    raw_affiliation: str | None
    provider_affiliation_id: str | None
    subunit_label: str | None
    resolution_evidence: tuple[dict[str, Any], ...]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _decimal(value: Fraction) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        return Decimal(value.numerator) / Decimal(value.denominator)


def _author_name(raw_author: dict[str, Any], position: int) -> str:
    return str(
        raw_author.get("full_name")
        or " ".join(
            str(raw_author.get(key, "")).strip()
            for key in ("given", "family")
            if raw_author.get(key)
        )
        or raw_author.get("name")
        or f"Unnamed author {position}"
    ).strip()


def _provider_institution_identifier(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value)
    if (parsed.hostname or "").casefold().rstrip(".") == "inspirehep.net":
        segments = [item for item in parsed.path.split("/") if item]
        if len(segments) >= 2 and segments[-2].casefold() == "institutions":
            return normalize_external_id("inspire-institution", segments[-1])
    return normalize_external_id("inspire-institution", value)


def _identifier_candidates(
    raw_affiliation: dict[str, Any],
    author: dict[str, Any],
    affiliation_index: int,
    affiliation_count: int,
) -> tuple[tuple[str, str], ...]:
    raw_identifiers: list[Any] = []
    for key in ("identifiers", "external_ids", "externalIds"):
        value = raw_affiliation.get(key)
        if isinstance(value, list):
            raw_identifiers.extend(value)

    author_identifiers = author.get("affiliations_identifiers")
    if not raw_identifiers and isinstance(author_identifiers, list):
        if affiliation_count == 1:
            raw_identifiers.extend(author_identifiers)
        elif len(author_identifiers) == affiliation_count:
            raw_identifiers.append(author_identifiers[affiliation_index])

    result: list[tuple[str, str]] = []
    record = raw_affiliation.get("record")
    reference = (
        record.get("$ref")
        if isinstance(record, dict)
        else record
        if isinstance(record, str)
        else None
    )
    provider_identifier = _provider_institution_identifier(reference)
    if provider_identifier is not None:
        result.append(provider_identifier)

    for raw_identifier in raw_identifiers:
        if not isinstance(raw_identifier, dict):
            continue
        scheme = raw_identifier.get("schema") or raw_identifier.get("scheme")
        value = raw_identifier.get("value")
        if not scheme or not value:
            continue
        normalized_scheme = str(scheme).strip().casefold().replace(" ", "-")
        if normalized_scheme == "inspire":
            normalized_scheme = "inspire-institution"
        identifier = normalize_external_id(normalized_scheme, value)
        if identifier is not None and identifier[0] in {"ror", "inspire-institution"}:
            result.append(identifier)
    return tuple(dict.fromkeys(result))


def _resolve_institution(
    session: Session,
    *,
    raw_name: str | None,
    identifiers: tuple[tuple[str, str], ...],
) -> tuple[str, str | None, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    authority_entity_ids: set[str] = set()
    for scheme, value in identifiers:
        authority = session.scalar(
            select(models.AuthorityIdentifier).where(
                models.AuthorityIdentifier.entity_type == "institution",
                models.AuthorityIdentifier.scheme == scheme,
                models.AuthorityIdentifier.value == value,
            )
        )
        evidence.append(
            {
                "method": "authority-identifier",
                "scheme": scheme,
                "value": value,
                "candidateEntityId": authority.entity_id if authority else None,
            }
        )
        if authority is not None:
            authority_entity_ids.add(authority.entity_id)

    if len(authority_entity_ids) == 1:
        return "resolved", next(iter(authority_entity_ids)), evidence
    if len(authority_entity_ids) > 1:
        return "ambiguous", None, evidence

    if raw_name and raw_name.strip():
        normalized = normalize_search_term(raw_name)
        exact_ids = set(
            session.scalars(
                select(models.EntitySearchTerm.entity_id).where(
                    models.EntitySearchTerm.entity_type == "institution",
                    models.EntitySearchTerm.normalized_term == normalized,
                    models.EntitySearchTerm.match_method.in_(
                        ["canonical-name", "alias", "historical-name"]
                    ),
                )
            )
        )
        evidence.append(
            {
                "method": "unique-exact-name",
                "inputValue": raw_name,
                "candidateEntityIds": sorted(exact_ids),
            }
        )
        if len(exact_ids) == 1:
            return "resolved", next(iter(exact_ids)), evidence
        if len(exact_ids) > 1:
            return "ambiguous", None, evidence
    return "unresolved", None, evidence


def _raw_affiliations(author: dict[str, Any]) -> list[dict[str, Any]]:
    value = author.get("affiliations")
    if not isinstance(value, list):
        return []
    return [item if isinstance(item, dict) else {"value": str(item)} for item in value]


def _contribution_evidence(
    author: dict[str, Any], provider: str, source_record_id: str
) -> tuple[ContributionEvidence, ...]:
    evidence: list[ContributionEvidence] = []
    for key in (
        "contribution",
        "contributions",
        "credit",
        "credit_roles",
        "corresponding",
    ):
        value = author.get(key)
        if value is None:
            continue
        evidence.append(
            ContributionEvidence(
                evidence_type=key,
                statement=str(value),
                source=provider,
                version=source_record_id,
            )
        )
    return tuple(evidence)


def _assertions_for_author(
    session: Session,
    record: NormalizedRecord,
    author: dict[str, Any],
    position: int,
) -> tuple[tuple[PaperTimeAffiliationAssertion, ...], dict[str, _AssertionEvidence]]:
    raw_affiliations = _raw_affiliations(author)
    assertions: list[PaperTimeAffiliationAssertion] = []
    by_id: dict[str, _AssertionEvidence] = {}
    for index, raw_affiliation in enumerate(raw_affiliations):
        raw_name_value = raw_affiliation.get("value") or raw_affiliation.get("name")
        raw_name = str(raw_name_value).strip() if raw_name_value else None
        identifiers = _identifier_candidates(
            raw_affiliation, author, index, len(raw_affiliations)
        )
        status, institution_id, evidence = _resolve_institution(
            session, raw_name=raw_name, identifiers=identifiers
        )
        country_id: str | None = None
        subunit_label: str | None = raw_name
        if institution_id is not None:
            institution = session.get(models.Institution, institution_id)
            if institution is None:
                status = "unresolved"
                institution_id = None
            else:
                country_id = institution.country_id
                known_names = {
                    institution.canonical_name.casefold(),
                    *(item.casefold() for item in institution.aliases),
                    *(item.casefold() for item in institution.historical_names),
                }
                if raw_name is not None and raw_name.casefold() in known_names:
                    subunit_label = None

        provider_id = identifiers[0][1] if identifiers else None
        assertion_id = (
            f"paper-affiliation-assertion-"
            f"{_digest(f'{record.provider}|{record.source_record_id}|{position}|{index}|{raw_name}|{identifiers}')[:28]}"
        )
        assertion = PaperTimeAffiliationAssertion(
            assertion_id=assertion_id,
            resolution_status=status,  # type: ignore[arg-type]
            source=record.provider,
            source_record_id=record.source_record_id,
            evidence_version=MATERIALIZATION_VERSION,
            institution_id=institution_id,
            country_id=country_id,
        )
        assertions.append(assertion)
        by_id[assertion_id] = _AssertionEvidence(
            assertion=assertion,
            raw_affiliation=raw_name,
            provider_affiliation_id=provider_id,
            subunit_label=subunit_label,
            resolution_evidence=tuple(evidence),
        )
    return tuple(assertions), by_id


def materialize_paper_time_affiliations(
    session: Session,
    *,
    record: NormalizedRecord,
    paper_id: str,
    source_snapshot_id: str,
    dataset_version: str,
    author_identities: dict[int, MaterializedAuthorIdentity],
) -> FractionalAttributionResult:
    """Materialize exact paper-time evidence without guessing or renormalizing."""

    raw_authors = record.attributes.get("authors", [])
    if not isinstance(raw_authors, list) or not raw_authors:
        raise ValueError(
            "paper-time attribution requires provider author appearances; "
            "missing authors are not zero"
        )

    inputs: list[AuthorAttributionInput] = []
    assertion_evidence: dict[str, _AssertionEvidence] = {}
    contribution_by_position: dict[int, tuple[ContributionEvidence, ...]] = {}
    raw_author_names: dict[int, str] = {}
    for position, value in enumerate(raw_authors, start=1):
        raw_author = value if isinstance(value, dict) else {"name": str(value)}
        identity = author_identities.get(position)
        raw_name = (
            identity.raw_author_name if identity else _author_name(raw_author, position)
        )
        raw_author_names[position] = raw_name
        assertions, evidence = _assertions_for_author(
            session, record, raw_author, position
        )
        assertion_evidence.update(evidence)
        contribution = _contribution_evidence(
            raw_author, record.provider, record.source_record_id
        )
        contribution_by_position[position] = contribution
        inputs.append(
            AuthorAttributionInput(
                author_slot_id=(
                    f"{record.provider}:{record.source_record_id}:author:{position}"
                ),
                author_position=position,
                researcher_id=identity.researcher_id if identity else None,
                affiliations=assertions,
                contribution_evidence=contribution,
            )
        )

    result = calculate_fractional_attribution(paper_id, inputs)
    session.execute(
        update(models.PaperAffiliation)
        .where(
            models.PaperAffiliation.paper_id == paper_id,
            models.PaperAffiliation.is_current,
        )
        .values(is_current=False)
    )

    for share_index, share in enumerate(result.shares):
        identity = author_identities.get(share.author_position)
        evidence_items = [
            assertion_evidence[assertion_id]
            for assertion_id in share.affiliation_assertion_ids
            if assertion_id in assertion_evidence
        ]
        if share.status == "allocated":
            affiliation_status = "resolved"
        elif share.status == "withheld-ambiguous-affiliation":
            affiliation_status = "ambiguous"
        elif share.status == "withheld-no-affiliation":
            affiliation_status = "missing"
        else:
            affiliation_status = "unresolved"
        effective_count = share.author_weight / share.weight
        row_id = (
            "paper-affiliation-"
            + _digest(
                "|".join(
                    (
                        paper_id,
                        source_snapshot_id,
                        str(share.author_position),
                        str(share_index),
                        *share.affiliation_assertion_ids,
                    )
                )
            )[:32]
        )
        values: dict[str, Any] = {
            "paper_id": paper_id,
            "authorship_id": identity.authorship_id if identity else None,
            "researcher_id": share.researcher_id,
            "institution_id": share.institution_id,
            "country_id": share.country_id,
            "source_snapshot_id": source_snapshot_id,
            "dataset_version": dataset_version,
            "provider": record.provider,
            "source_record_id": record.source_record_id,
            "author_position": share.author_position,
            "raw_author_name": raw_author_names[share.author_position],
            "raw_affiliation": "; ".join(
                item.raw_affiliation
                for item in evidence_items
                if item.raw_affiliation is not None
            )
            or None,
            "provider_affiliation_id": "; ".join(
                item.provider_affiliation_id
                for item in evidence_items
                if item.provider_affiliation_id is not None
            )
            or None,
            "subunit_label": "; ".join(
                item.subunit_label
                for item in evidence_items
                if item.subunit_label is not None
            )
            or None,
            "author_resolution_status": (
                identity.resolution_status if identity else "unresolved"
            ),
            "affiliation_resolution_status": affiliation_status,
            "author_weight": _decimal(share.author_weight),
            "affiliation_weight": _decimal(share.weight / share.author_weight),
            "attribution_weight": _decimal(share.weight),
            "author_weight_numerator": share.author_weight.numerator,
            "author_weight_denominator": share.author_weight.denominator,
            "attribution_weight_numerator": share.weight.numerator,
            "attribution_weight_denominator": share.weight.denominator,
            "effective_affiliation_count": int(effective_count),
            "attribution_policy_version": FRACTIONAL_ATTRIBUTION_V1.version,
            "materialization_version": MATERIALIZATION_VERSION,
            "contribution_evidence": [
                {
                    "evidenceType": item.evidence_type,
                    "statement": item.statement,
                    "source": item.source,
                    "version": item.version,
                    "numericWeightApplied": False,
                }
                for item in contribution_by_position[share.author_position]
            ],
            "resolution_evidence": [
                evidence
                for item in evidence_items
                for evidence in item.resolution_evidence
            ],
            "is_current": True,
            "provenance_json": {
                **record.provenance,
                "sourceSnapshotId": source_snapshot_id,
                "datasetVersion": dataset_version,
                "attributionPolicyVersion": FRACTIONAL_ATTRIBUTION_V1.version,
                "materializationVersion": MATERIALIZATION_VERSION,
                "allocationStatus": share.status,
                "exactAttributionFraction": (
                    f"{share.weight.numerator}/{share.weight.denominator}"
                ),
            },
        }
        row = session.get(models.PaperAffiliation, row_id)
        if row is None:
            session.add(models.PaperAffiliation(id=row_id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
    return result
