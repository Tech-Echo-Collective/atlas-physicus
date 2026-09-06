"""Small in-memory bridge from acquired source records to scientific inputs.

No acquisition, database, artifact writer, metric activation or complete-year
assertion lives here. The acquisition caller verifies the transport and page
inventory and releases each raw page/record after retaining these compact facts.
Canonicalization delegates to the existing exact-identifier implementation.
"""

from dataclasses import dataclass, replace
from typing import Literal, cast

from ..connectors.base import SourceRecord
from ..connectors.inspire import InspireConnector
from ..fields import ProviderCategoryEvidence, ProviderFieldProjection
from ..historical_replay import (
    CANONICAL_PAPER_MERGE_POLICY_VERSION,
    CanonicalPaperComponent,
    PaperEvidenceOccurrence,
    StrongIdentifier,
    StrongIdentifierScheme,
    build_canonical_paper_merge_plan,
)
from .automation import (
    AutomaticEvidenceContext,
    AutomaticFieldEvidence,
    SourceBoundPaperFacts,
    capture_automatic_paper_facts,
)
from .contracts import CertificationError, EvidenceReference, canonical_digest
from .fields import automatic_field_ledger
from .launch_scope import BOUNDED_LAUNCH_DATE_BASIS, BOUNDED_LAUNCH_SCOPE

LAUNCH_INPUT_PROJECTION_VERSION = "bounded-launch-source-inputs-v2"
MAXIMUM_LAUNCH_INPUT_OCCURRENCES = 20_000
# INSPIRE's material schema distinguishes correction/extension documents from
# the main publication. Do not infer equivalence for other material roles.
# https://inspire-schemas.readthedocs.io/en/latest/schemas/elements/material.html
INSPIRE_DOI_MATERIALS = frozenset(
    {
        "addendum",
        "additional material",
        "data",
        "erratum",
        "editorial note",
        "preprint",
        "publication",
        "reprint",
        "software",
        "translation",
    }
)
RELATED_DOI_MATERIALS = frozenset({"erratum", "addendum"})


@dataclass(frozen=True)
class LaunchDOIAssertion:
    """One role-preserving DOI assertion from a checksummed source record."""

    position: int
    value: str
    material: str | None
    source: str | None
    source_reference: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.position, bool)
            or not isinstance(self.position, int)
            or self.position < 1
            or not isinstance(self.value, str)
            or not self.value.strip()
            or (
                self.material is not None
                and (
                    not isinstance(self.material, str)
                    or self.material not in INSPIRE_DOI_MATERIALS
                )
            )
            or (
                self.source is not None
                and (not isinstance(self.source, str) or not self.source.strip())
            )
        ):
            raise CertificationError("launch DOI assertion or material is invalid")

    @property
    def identifier(self) -> StrongIdentifier | None:
        try:
            return StrongIdentifier("doi", self.value)
        except ValueError:
            return None

    @property
    def is_related_document(self) -> bool:
        return self.material in RELATED_DOI_MATERIALS


@dataclass(frozen=True)
class LaunchAffiliationFact:
    """Paper-native text/IDs only; not an institution identity approval."""

    source_field: Literal["authors[].affiliations", "authors[].raw_affiliations"]
    position: int
    text: str | None
    provider_reference: str | None
    identifiers: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class LaunchAuthorAffiliations:
    author_position: int
    display_name: str | None
    structured: tuple[LaunchAffiliationFact, ...]
    raw: tuple[LaunchAffiliationFact, ...]
    author_affiliation_identifiers: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class LaunchSourceOccurrence:
    reference: EvidenceReference
    identity: PaperEvidenceOccurrence
    source_facts: SourceBoundPaperFacts
    field_evidence: AutomaticFieldEvidence
    authors: tuple[LaunchAuthorAffiliations, ...]
    invalid_identifiers: tuple[tuple[str, str], ...]
    doi_assertions: tuple[LaunchDOIAssertion, ...]
    version: str = LAUNCH_INPUT_PROJECTION_VERSION

    def __post_init__(self) -> None:
        if (
            self.version != LAUNCH_INPUT_PROJECTION_VERSION
            or self.reference != self.source_facts.reference
            or self.identity.provider != self.reference.provider
            or self.identity.source_record_id != self.reference.source_record_id
            or self.identity.source_reference != canonical_digest(self.reference)
            or self.field_evidence.context != self.source_facts.context
            or self.field_evidence.references != (self.reference,)
            or self.source_facts.context.acquisition_scope != BOUNDED_LAUNCH_SCOPE
            or self.source_facts.declared_date_basis != BOUNDED_LAUNCH_DATE_BASIS
        ):
            raise CertificationError("launch occurrence source lineage is inconsistent")
        self.source_facts.__post_init__()
        if not isinstance(self.doi_assertions, tuple) or any(
            not isinstance(item, LaunchDOIAssertion) for item in self.doi_assertions
        ):
            raise CertificationError("launch DOI evidence requires typed assertions")
        for item in self.doi_assertions:
            item.__post_init__()
            if item.source_reference != canonical_digest(self.reference):
                raise CertificationError("launch DOI evidence source checksum differs")
        if tuple(item.position for item in self.doi_assertions) != tuple(
            range(1, len(self.doi_assertions) + 1)
        ):
            raise CertificationError("launch DOI evidence inventory is incomplete")
        expected_dois = {
            item.identifier
            for item in self.doi_assertions
            if not item.is_related_document and item.identifier is not None
        }
        related_dois = {
            item.identifier
            for item in self.doi_assertions
            if item.is_related_document and item.identifier is not None
        }
        if expected_dois & related_dois:
            raise CertificationError(
                "source DOI has conflicting primary and related-document roles"
            )
        if expected_dois != {
            item for item in self.identity.identifiers if item.scheme == "doi"
        }:
            raise CertificationError(
                "launch primary DOI identity differs from source roles"
            )
        if self.source_facts.author_count != len(self.authors) and not (
            self.source_facts.author_count is None and not self.authors
        ):
            raise CertificationError(
                "launch author inventory differs from source facts"
            )
        if tuple(item.author_position for item in self.authors) != tuple(
            range(1, len(self.authors) + 1)
        ):
            raise CertificationError("launch author positions are incomplete")
        # Reconstruct the existing mapping rather than accepting stored field scores.
        automatic_field_ledger(self.field_evidence)

    @property
    def content_digest(self) -> str:
        return canonical_digest(self)


@dataclass(frozen=True)
class LaunchCanonicalPaper:
    component: CanonicalPaperComponent
    occurrences: tuple[LaunchSourceOccurrence, ...]

    @property
    def paper_id(self) -> str:
        return self.component.canonical_id or self.component.candidate_id

    @property
    def field_evidence(self) -> AutomaticFieldEvidence:
        return AutomaticFieldEvidence(
            context=self.occurrences[0].source_facts.context,
            projections=tuple(
                projection
                for item in self.occurrences
                for projection in item.field_evidence.projections
            ),
            references=tuple(item.reference for item in self.occurrences),
        )


@dataclass(frozen=True)
class LaunchCanonicalInputs:
    papers: tuple[LaunchCanonicalPaper, ...]
    occurrence_count: int
    duplicate_occurrences: int
    merge_digest: str
    merge_policy_version: str = CANONICAL_PAPER_MERGE_POLICY_VERSION
    version: str = LAUNCH_INPUT_PROJECTION_VERSION


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _doi_assertions(
    record: SourceRecord, reference: EvidenceReference
) -> tuple[LaunchDOIAssertion, ...]:
    values = record.raw.get("dois", [])
    if not isinstance(values, list):
        raise CertificationError("paper DOI inventory is malformed")
    result: list[LaunchDOIAssertion] = []
    for position, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            raise CertificationError("paper DOI assertion is malformed")
        value = item.get("value")
        material = item.get("material")
        source = item.get("source")
        if (
            not isinstance(value, str)
            or not value.strip()
            or ("material" in item and not isinstance(material, str))
            or ("source" in item and not isinstance(source, str))
        ):
            raise CertificationError("paper DOI material/value/source is malformed")
        result.append(
            LaunchDOIAssertion(
                position=position,
                value=value,
                material=material,
                source=source,
                source_reference=canonical_digest(reference),
            )
        )
    return tuple(result)


def _identifiers(value: object) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CertificationError("affiliation identifiers are malformed")
    result: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise CertificationError("affiliation identifier entry is malformed")
        scheme = _text(item.get("schema")) or _text(item.get("scheme"))
        identifier = _text(item.get("value"))
        if scheme is None or identifier is None:
            raise CertificationError("affiliation identifier lacks scheme or value")
        result.append((scheme, identifier))
    return tuple(sorted(set(result)))


def _affiliations(
    author: dict[str, object],
    key: Literal["affiliations", "raw_affiliations"],
) -> tuple[LaunchAffiliationFact, ...]:
    value = author.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CertificationError("paper-native affiliation inventory is malformed")
    result = []
    for position, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise CertificationError("paper-native affiliation entry is malformed")
        link = item.get("record")
        if isinstance(link, dict):
            link = link.get("$ref")
        result.append(
            LaunchAffiliationFact(
                source_field=(
                    "authors[].affiliations"
                    if key == "affiliations"
                    else "authors[].raw_affiliations"
                ),
                position=position,
                text=_text(item.get("value")) or _text(item.get("name")),
                provider_reference=_text(link),
                identifiers=tuple(
                    sorted(
                        set(
                            pair
                            for identifier_key in (
                                "identifiers",
                                "external_ids",
                                "externalIds",
                            )
                            for pair in _identifiers(item.get(identifier_key))
                        )
                    )
                ),
            )
        )
    return tuple(result)


def _author_affiliations(record: SourceRecord) -> tuple[LaunchAuthorAffiliations, ...]:
    value = record.raw.get("authors")
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise CertificationError("launch source author inventory is malformed")
    return tuple(
        LaunchAuthorAffiliations(
            author_position=position,
            display_name=_text(item.get("full_name")) or _text(item.get("name")),
            structured=_affiliations(item, "affiliations"),
            raw=_affiliations(item, "raw_affiliations"),
            author_affiliation_identifiers=_identifiers(
                item.get("affiliations_identifiers")
            ),
        )
        for position, item in enumerate(value, start=1)
    )


def capture_launch_occurrence(
    record: SourceRecord,
    *,
    reference: EvidenceReference,
    connector: InspireConnector,
    dataset_version: str,
) -> LaunchSourceOccurrence:
    """Extract a compact record while its real acquired payload is still in memory."""
    if record.provider != "inspire" or not isinstance(connector, InspireConnector):
        raise CertificationError("bounded launch inputs require the INSPIRE parser")
    occurrence_id = f"source-occurrence:{canonical_digest(reference)}"
    context = AutomaticEvidenceContext(
        occurrence_id, dataset_version, BOUNDED_LAUNCH_SCOPE
    )
    facts = capture_automatic_paper_facts(
        record,
        context=context,
        reference=reference,
        declared_date_basis=BOUNDED_LAUNCH_DATE_BASIS,
    )
    doi_assertions = _doi_assertions(record, reference)
    normalized = connector.normalize_record(record)
    # The legacy normalizer exposes its first DOI without its material role.
    # Reconstruct DOI identity solely from the complete role-aware inventory,
    # including when an erratum happens to be first in provider order.
    candidates: list[tuple[str, object]] = [
        (scheme, value) for scheme, value in normalized.external_ids if scheme != "doi"
    ]
    candidates.extend(
        ("doi", item.value) for item in doi_assertions if not item.is_related_document
    )
    candidates.append(("inspire", record.source_record_id))
    for key, scheme in (("arxiv_eprints", "arxiv"),):
        values = record.raw.get(key, [])
        if not isinstance(values, list):
            raise CertificationError("paper strong-identifier inventory is malformed")
        for item in values:
            candidates.append(
                (scheme, item.get("value") if isinstance(item, dict) else item)
            )
    identifiers: set[StrongIdentifier] = set()
    invalid: set[tuple[str, str]] = {
        ("doi", item.value) for item in doi_assertions if item.identifier is None
    }
    for scheme, value in candidates:
        if scheme not in {"doi", "arxiv", "inspire"} or value is None:
            continue
        try:
            identifiers.add(
                StrongIdentifier(cast(StrongIdentifierScheme, scheme), str(value))
            )
        except ValueError:
            invalid.add((scheme, str(value)))
    category_values = normalized.attributes.get("raw_category_evidence", [])
    if not isinstance(category_values, list):
        raise CertificationError("normalized field evidence is malformed")
    categories = tuple(
        ProviderCategoryEvidence(
            category=item["category"],
            role=item["role"],
            taxonomy=item.get("taxonomy"),
            source=item.get("source"),
        )
        for item in category_values
    )
    document_types = record.raw.get("document_type")
    document_type = (
        document_types[0]
        if isinstance(document_types, list) and len(document_types) == 1
        else _text(document_types)
    )
    return LaunchSourceOccurrence(
        reference=reference,
        identity=PaperEvidenceOccurrence(
            occurrence_id=occurrence_id,
            provider="inspire",
            source_record_id=record.source_record_id,
            source_reference=canonical_digest(reference),
            identifiers=tuple(sorted(identifiers)),
            title=normalized.canonical_name,
            # No names/journal secondary key and no earliest-date substitution.
            year=facts.exact_date.year if facts.exact_date is not None else None,
            document_type=document_type,
        ),
        source_facts=facts,
        field_evidence=AutomaticFieldEvidence(
            context=context,
            projections=(
                ProviderFieldProjection(
                    provider="inspire",
                    source_record_id=record.source_record_id,
                    categories=categories,
                    source_snapshot_id=reference.source_snapshot_id,
                ),
            ),
            references=(reference,),
        ),
        authors=_author_affiliations(record),
        invalid_identifiers=tuple(sorted(invalid)),
        doi_assertions=doi_assertions,
    )


def _canonical_context(
    occurrence: LaunchSourceOccurrence,
    paper_id: str,
) -> LaunchSourceOccurrence:
    context = replace(occurrence.source_facts.context, paper_id=paper_id)
    return replace(
        occurrence,
        source_facts=replace(
            occurrence.source_facts,
            context=context,
            authors=tuple(
                replace(item, context=context)
                for item in occurrence.source_facts.authors
            ),
        ),
        field_evidence=replace(occurrence.field_evidence, context=context),
    )


def canonicalize_launch_inputs(
    occurrences: tuple[LaunchSourceOccurrence, ...],
) -> LaunchCanonicalInputs:
    """Deduplicate exact occurrences then apply the existing strong-ID merge policy.

    The 20k bound limits this trial; it neither claims provider completeness nor
    permits metric activation. Multiple selected revisions are rejected; conflicted
    identifier components remain candidates, never repaired by names or dates.
    """
    if (
        not isinstance(occurrences, tuple)
        or not 0 < len(occurrences) <= MAXIMUM_LAUNCH_INPUT_OCCURRENCES
    ):
        raise CertificationError(
            "launch input inventory must contain 1–20,000 occurrences"
        )
    by_id: dict[str, LaunchSourceOccurrence] = {}
    dataset_versions = set()
    for item in occurrences:
        if not isinstance(item, LaunchSourceOccurrence):
            raise CertificationError(
                "launch canonicalization requires typed captured occurrences"
            )
        item.__post_init__()
        dataset_versions.add(item.source_facts.context.dataset_version)
        prior = by_id.setdefault(item.identity.occurrence_id, item)
        if prior != item:
            raise CertificationError(
                "one launch source occurrence has contradictory projections"
            )
    if len(dataset_versions) != 1:
        raise CertificationError("launch occurrence dataset versions differ")
    selected_records = [
        (item.reference.provider, item.reference.source_record_id)
        for item in by_id.values()
    ]
    if len(selected_records) != len(set(selected_records)):
        raise CertificationError(
            "launch input contains multiple selected occurrences of one provider record"
        )
    plan = build_canonical_paper_merge_plan(
        (item.identity for item in by_id.values()),
        enable_secondary_merge=False,
    )
    papers = tuple(
        LaunchCanonicalPaper(
            component=component,
            occurrences=tuple(
                _canonical_context(
                    by_id[item.occurrence_id],
                    component.canonical_id or component.candidate_id,
                )
                for item in component.occurrences
            ),
        )
        for component in plan.components
    )
    return LaunchCanonicalInputs(
        papers=papers,
        occurrence_count=len(by_id),
        duplicate_occurrences=len(occurrences) - len(by_id),
        merge_digest=plan.digest,
        merge_policy_version=plan.policy_version,
    )
