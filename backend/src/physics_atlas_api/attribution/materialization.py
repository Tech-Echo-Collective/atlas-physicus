"""Paper-time affiliation extraction, conservative resolution, and persistence."""

import hashlib
from dataclasses import dataclass, replace
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

MATERIALIZATION_VERSION = "paper-time-affiliation-materialization-v2"
AFFILIATION_EVIDENCE_PRECEDENCE_VERSION = "cross-provider-affiliation-precedence-v1"
_AFFILIATION_EVIDENCE_PRECEDENCE = {
    "arxiv": 2,
    "crossref": 3,
    "inspire": 3,
}


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


def _affiliation_evidence_priority(provider: str) -> int:
    """Return the frozen historical-evidence priority for a supported provider."""

    priority = _AFFILIATION_EVIDENCE_PRECEDENCE.get(provider.casefold())
    if priority is None:
        raise ValueError(
            f"{provider!r} is not an approved paper-time affiliation provider; "
            "current profile/homepage evidence must not enter historical projection"
        )
    return priority


def _current_evidence_positions(
    rows: list[models.PaperAffiliation],
) -> set[int]:
    return {
        row.author_position
        for row in rows
        if row.affiliation_resolution_status != "missing"
    }


def _incoming_evidence_positions(
    result: FractionalAttributionResult,
) -> set[int]:
    return {
        share.author_position
        for share in result.shares
        if share.status != "withheld-no-affiliation"
    }


def _current_rows_by_position(
    rows: list[models.PaperAffiliation],
) -> dict[int, list[models.PaperAffiliation]]:
    grouped: dict[int, list[models.PaperAffiliation]] = {}
    for row in rows:
        grouped.setdefault(row.author_position, []).append(row)
    return grouped


def _author_weights_by_position(
    current_rows: dict[int, list[models.PaperAffiliation]],
    result: FractionalAttributionResult,
) -> tuple[dict[int, Fraction], dict[int, Fraction]]:
    current_weights: dict[int, Fraction] = {}
    for position, rows in current_rows.items():
        weights = {
            Fraction(row.author_weight_numerator, row.author_weight_denominator)
            for row in rows
        }
        if len(weights) != 1:
            raise ValueError(
                "current paper-time rows disagree about one author's exact weight"
            )
        current_weights[position] = next(iter(weights))

    incoming_weights: dict[int, Fraction] = {}
    for share in result.shares:
        previous = incoming_weights.setdefault(
            share.author_position, share.author_weight
        )
        if previous != share.author_weight:
            raise ValueError(
                "incoming paper-time rows disagree about one author's exact weight"
            )
    return current_weights, incoming_weights


def _validate_mixed_projection_conservation(
    *,
    current_rows: dict[int, list[models.PaperAffiliation]],
    result: FractionalAttributionResult,
    selected_incoming_positions: set[int],
) -> None:
    """Refuse a cross-provider slot merge that would change one-paper mass."""

    current_weights, incoming_weights = _author_weights_by_position(
        current_rows, result
    )
    retained_current_positions = set(current_weights) - selected_incoming_positions
    selected_weight = sum(
        (incoming_weights[position] for position in selected_incoming_positions),
        start=Fraction(0),
    )
    retained_weight = sum(
        (current_weights[position] for position in retained_current_positions),
        start=Fraction(0),
    )
    if selected_weight + retained_weight != 1:
        raise ValueError(
            "cross-provider paper-time author slots cannot be merged while "
            "conserving one paper; retain the evidence as unresolved lineage"
        )


def _conflicting_resolved_positions(
    current_rows: list[models.PaperAffiliation],
    result: FractionalAttributionResult,
) -> set[int]:
    current_targets: dict[int, set[str]] = {}
    incoming_targets: dict[int, set[str]] = {}
    for row in current_rows:
        if row.institution_id is not None:
            current_targets.setdefault(row.author_position, set()).add(
                row.institution_id
            )
    for share in result.shares:
        if share.institution_id is not None:
            incoming_targets.setdefault(share.author_position, set()).add(
                share.institution_id
            )
    return {
        position
        for position in current_targets.keys() & incoming_targets.keys()
        if current_targets[position] != incoming_targets[position]
    }


def _withhold_conflicting_positions(
    result: FractionalAttributionResult, conflicting_positions: set[int]
) -> FractionalAttributionResult:
    if not conflicting_positions:
        return result
    return replace(
        result,
        shares=tuple(
            replace(
                share,
                institution_id=None,
                country_id=None,
                status="withheld-unresolved-affiliation",
            )
            if share.author_position in conflicting_positions
            else share
            for share in result.shares
        ),
    )


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
    affiliation_count: int,
) -> tuple[tuple[str, str], ...]:
    raw_identifiers: list[Any] = []
    for key in ("identifiers", "external_ids", "externalIds"):
        value = raw_affiliation.get(key)
        if isinstance(value, list):
            raw_identifiers.extend(value)

    author_identifiers = author.get("affiliations_identifiers")
    if (
        not raw_identifiers
        and affiliation_count == 1
        and isinstance(author_identifiers, list)
    ):
        # INSPIRE exposes this as an author-level array, separately from the
        # affiliation assertions.  There is no reviewed contract that permits
        # positionally zipping two multi-valued arrays.  A single unique ROR
        # can be aligned only when there is exactly one effective affiliation.
        normalized_author_rors = {
            identifier
            for item in author_identifiers
            if isinstance(item, dict)
            and str(item.get("schema", "")).strip().casefold() == "ror"
            and (identifier := normalize_external_id("ror", item.get("value")))
            is not None
        }
        if len(normalized_author_rors) == 1:
            result_author_ror = next(iter(normalized_author_rors))
            raw_identifiers.append(
                {"schema": result_author_ror[0], "value": result_author_ror[1]}
            )

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

    ror_backed_entity_ids = set(
        session.scalars(
            select(models.AuthorityIdentifier.entity_id).where(
                models.AuthorityIdentifier.entity_type == "institution",
                models.AuthorityIdentifier.scheme == "ror",
                models.AuthorityIdentifier.is_authoritative,
                models.AuthorityIdentifier.entity_id.in_(authority_entity_ids),
            )
        )
    )
    if len(ror_backed_entity_ids) == 1:
        return "resolved", next(iter(ror_backed_entity_ids)), evidence
    if len(ror_backed_entity_ids) > 1:
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
        ror_backed_exact_ids = set(
            session.scalars(
                select(models.AuthorityIdentifier.entity_id).where(
                    models.AuthorityIdentifier.entity_type == "institution",
                    models.AuthorityIdentifier.scheme == "ror",
                    models.AuthorityIdentifier.is_authoritative,
                    models.AuthorityIdentifier.entity_id.in_(exact_ids),
                )
            )
        )
        evidence[-1]["rorBackedCandidateEntityIds"] = sorted(ror_backed_exact_ids)
        if len(ror_backed_exact_ids) == 1:
            return "resolved", next(iter(ror_backed_exact_ids)), evidence
        if len(ror_backed_exact_ids) > 1:
            return "ambiguous", None, evidence
    return "unresolved", None, evidence


def _raw_affiliations(author: dict[str, Any]) -> list[dict[str, Any]]:
    value = author.get("affiliations")
    if isinstance(value, list) and value:
        return [
            item if isinstance(item, dict) else {"value": str(item)} for item in value
        ]
    raw_value = author.get("raw_affiliations")
    if not isinstance(raw_value, list):
        return []
    return [
        item if isinstance(item, dict) else {"value": str(item)} for item in raw_value
    ]


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
            raw_affiliation, author, len(raw_affiliations)
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

    incoming_priority = _affiliation_evidence_priority(record.provider)

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
    current_rows = list(
        session.scalars(
            select(models.PaperAffiliation).where(
                models.PaperAffiliation.paper_id == paper_id,
                models.PaperAffiliation.is_current,
            )
        )
    )
    current_providers = {row.provider.casefold() for row in current_rows}
    current_by_position = _current_rows_by_position(current_rows)
    incoming_positions = {share.author_position for share in result.shares}
    incoming_evidence_positions = _incoming_evidence_positions(result)
    current_evidence_positions = _current_evidence_positions(current_rows)
    cross_provider_replay = bool(
        current_rows and current_providers != {record.provider.casefold()}
    )
    cross_provider_evidence_loss = (
        cross_provider_replay
        and not current_evidence_positions.issubset(incoming_evidence_positions)
    )
    conflicting_positions = (
        _conflicting_resolved_positions(current_rows, result)
        if cross_provider_replay
        else set()
    )
    replace_complete_projection = bool(
        not current_rows or current_providers == {record.provider.casefold()}
    )
    selected_incoming_positions: set[int]
    if replace_complete_projection:
        selected_incoming_positions = incoming_positions
    else:
        result = _withhold_conflicting_positions(result, conflicting_positions)
        selected_incoming_positions = set()
        for position in incoming_positions:
            position_rows = current_by_position.get(position, [])
            if not position_rows or position in conflicting_positions:
                selected_incoming_positions.add(position)
                continue
            incoming_has_evidence = position in incoming_evidence_positions
            current_has_evidence = position in current_evidence_positions
            if incoming_has_evidence != current_has_evidence:
                if incoming_has_evidence:
                    selected_incoming_positions.add(position)
                continue
            current_priority = max(
                _affiliation_evidence_priority(row.provider) for row in position_rows
            )
            if incoming_priority >= current_priority:
                selected_incoming_positions.add(position)
        if selected_incoming_positions:
            _validate_mixed_projection_conservation(
                current_rows=current_by_position,
                result=result,
                selected_incoming_positions=selected_incoming_positions,
            )

    if replace_complete_projection:
        session.execute(
            update(models.PaperAffiliation)
            .where(
                models.PaperAffiliation.paper_id == paper_id,
                models.PaperAffiliation.is_current,
            )
            .values(is_current=False)
        )
    elif selected_incoming_positions:
        session.execute(
            update(models.PaperAffiliation)
            .where(
                models.PaperAffiliation.paper_id == paper_id,
                models.PaperAffiliation.is_current,
                models.PaperAffiliation.author_position.in_(
                    selected_incoming_positions
                ),
            )
            .values(is_current=False)
        )

    for share_index, share in enumerate(result.shares):
        selected_as_current = share.author_position in selected_incoming_positions
        identity = author_identities.get(share.author_position)
        evidence_items = [
            assertion_evidence[assertion_id]
            for assertion_id in share.affiliation_assertion_ids
            if assertion_id in assertion_evidence
        ]
        conflict_evidence = (
            [
                {
                    "method": "cross-provider-affiliation-precedence",
                    "status": "unresolved-conflict",
                    "providers": sorted(
                        current_providers | {record.provider.casefold()}
                    ),
                    "version": AFFILIATION_EVIDENCE_PRECEDENCE_VERSION,
                }
            ]
            if share.author_position in conflicting_positions
            else []
        )
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
            ]
            + conflict_evidence,
            "is_current": selected_as_current,
            "provenance_json": {
                **record.provenance,
                "sourceSnapshotId": source_snapshot_id,
                "datasetVersion": dataset_version,
                "attributionPolicyVersion": FRACTIONAL_ATTRIBUTION_V1.version,
                "materializationVersion": MATERIALIZATION_VERSION,
                "affiliationEvidencePrecedenceVersion": (
                    AFFILIATION_EVIDENCE_PRECEDENCE_VERSION
                ),
                "affiliationEvidencePriority": incoming_priority,
                "selectedAsCurrentProjection": selected_as_current,
                "crossProviderConflictUnresolved": (
                    share.author_position in conflicting_positions
                ),
                "crossProviderEvidenceLossPrevented": (cross_provider_evidence_loss),
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
