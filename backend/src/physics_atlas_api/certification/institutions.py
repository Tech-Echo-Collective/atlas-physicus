import math
from dataclasses import dataclass, replace
from datetime import datetime
from urllib.parse import urlsplit

from ..connectors.base import SourceRecord, normalize_external_id
from ..search_index import normalize_search_term
from .contracts import (
    CertificationError,
    CertificationState,
    EvidenceReference,
    canonical_digest,
)

INSTITUTION_CERTIFICATION_RULE_VERSION = "institution-ror-certification-v1"
EXACT_ROR_IDENTITY_RULE_VERSION = "institution-ror-exact-identity-v1"


@dataclass(frozen=True)
class InstitutionAuthorityRecord:
    institution_id: str
    ror_id: str
    canonical_name: str
    aliases: tuple[str, ...] = ()
    historical_names: tuple[str, ...] = ()
    active: bool = True
    parent_ror_ids: tuple[str, ...] = ()
    parent_rollup_eligible: bool = False

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.institution_id, self.ror_id, self.canonical_name)
        ):
            raise ValueError("institution authority identifiers must be non-empty")
        if len(set(self.parent_ror_ids)) != len(self.parent_ror_ids):
            raise ValueError("institution parent ROR ids must be unique")

    @property
    def exact_names(self) -> frozenset[str]:
        return frozenset(
            normalized
            for value in (
                self.canonical_name,
                *self.aliases,
                *self.historical_names,
            )
            if (normalized := normalize_search_term(value))
        )


@dataclass(frozen=True)
class InstitutionResolutionEvidence:
    raw_name: str | None
    source_evidence_ids: tuple[str, ...]
    source_manifest_digest: str
    authority_version: str
    direct_ror_ids: tuple[str, ...] = ()
    provider: str | None = None
    provider_institution_id: str | None = None
    subunit_label: str | None = None
    context_candidate_ids: tuple[str, ...] = ()
    reviewed_context_institution_id: str | None = None
    reviewed_rollup_institution_id: str | None = None
    review_state: str = "unreviewed"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.authority_version.strip():
            raise ValueError("institution authority version must be non-empty")
        if not self.source_evidence_ids or len(set(self.source_evidence_ids)) != len(
            self.source_evidence_ids
        ):
            raise ValueError("institution source evidence ids must be non-empty/unique")
        if len(self.source_manifest_digest) != 64:
            raise ValueError("institution source manifest digest must be SHA-256")
        try:
            int(self.source_manifest_digest, 16)
        except ValueError as error:
            raise ValueError(
                "institution source manifest digest must be hexadecimal"
            ) from error
        if (self.reviewed_by is None) != (self.reviewed_at is None):
            raise ValueError("institution reviewer and review timestamp must be paired")
        if self.reviewed_at is not None and (
            self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None
        ):
            raise ValueError("institution review timestamp must include a timezone")
        if self.confidence is not None and (
            not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1
        ):
            raise ValueError("institution confidence must be within [0,1]")


@dataclass(frozen=True)
class InstitutionCertificationResult:
    evidence: InstitutionResolutionEvidence
    state: CertificationState
    canonical_institution_id: str | None
    source_institution_id: str | None
    retained_subunit_label: str | None
    match_method: str | None
    candidate_institution_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    rule_version: str = INSTITUTION_CERTIFICATION_RULE_VERSION


def institution_authority_version(
    authority_records: tuple[InstitutionAuthorityRecord, ...],
) -> str:
    """Bind a resolution decision to the exact immutable ROR authority view."""

    if not authority_records:
        raise ValueError("institution authority registry must not be empty")
    ordered_records = tuple(sorted(authority_records, key=lambda item: item.ror_id))
    return f"ror-authority-{canonical_digest(ordered_records)}"


def certify_paper_institution_link(
    *,
    paper_record: SourceRecord,
    paper_reference: EvidenceReference,
    paper_time_provider_institution_id: str,
    institution_record: SourceRecord,
    institution_reference: EvidenceReference,
    ror_record: SourceRecord,
    ror_reference: EvidenceReference,
    raw_affiliation_name: str | None = None,
) -> InstitutionCertificationResult:
    """Follow an exact paper-time INSPIRE ID to its explicit ROR authority link.

    This is not a name match or a current affiliation inference. The caller must
    use the institution ID found in the paper's affiliation record, not an author
    profile; this function verifies that relationship. Provider and ROR records
    are exact known-ID responses. Parent links
    remain metadata, never an automatic permission to roll historical activity up.
    No raw payload or reviewer identity is added to the retained result.
    """
    if (
        paper_reference.provider != "inspire"
        or paper_record.provider != "inspire"
        or not paper_reference.source_snapshot_id
        or institution_record.provider != "inspire"
        or institution_record.source_record_id != paper_time_provider_institution_id
        or not paper_time_provider_institution_id.isdecimal()
        or ror_record.provider != "ror"
    ):
        raise CertificationError("paper-time institution link has invalid identity")
    for record, reference in (
        (paper_record, paper_reference),
        (institution_record, institution_reference),
        (ror_record, ror_reference),
    ):
        if (
            reference.provider != record.provider
            or reference.source_record_id != record.source_record_id
            or reference.checksum != record.checksum
            or not reference.source_snapshot_id
        ):
            raise CertificationError(
                "institution authority reference does not bind source"
            )
    authors = paper_record.raw.get("authors")
    if not isinstance(authors, list):
        raise CertificationError("paper has no affiliation author inventory")
    paper_institution_ids: set[str] = set()
    for author in authors:
        if not isinstance(author, dict):
            raise CertificationError("paper author inventory is malformed")
        affiliations = author.get("affiliations", [])
        if not isinstance(affiliations, list):
            raise CertificationError("paper affiliation inventory is malformed")
        for affiliation in affiliations:
            if not isinstance(affiliation, dict):
                raise CertificationError("paper affiliation entry is malformed")
            link = affiliation.get("record")
            if isinstance(link, dict) and isinstance(link.get("$ref"), str):
                url = urlsplit(link["$ref"])
                prefix = "/api/institutions/"
                if (
                    url.scheme == "https"
                    and url.netloc == "inspirehep.net"
                    and url.path.startswith(prefix)
                    and url.path[len(prefix) :].isdecimal()
                    and not url.query
                    and not url.fragment
                ):
                    paper_institution_ids.add(url.path[len(prefix) :])
    if paper_time_provider_institution_id not in paper_institution_ids:
        raise CertificationError(
            "institution link is absent from paper-time affiliations"
        )
    raw = institution_record.raw
    if str(raw.get("control_number", "")) != institution_record.source_record_id:
        raise CertificationError("institution authority response has another record ID")
    entries = raw.get("external_system_identifiers")
    if not isinstance(entries, list):
        raise CertificationError("institution has no explicit ROR authority link")
    identifiers: set[str] = set()
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or str(entry.get("schema", "")).casefold() != "ror"
        ):
            continue
        normalized = normalize_external_id("ror", str(entry.get("value", "")))
        if normalized is None:
            raise CertificationError("institution has an invalid explicit ROR link")
        identifiers.add(normalized[1])
    if identifiers != {ror_record.source_record_id}:
        raise CertificationError("institution ROR authority is missing or ambiguous")
    if normalize_external_id("ror", str(ror_record.raw.get("id", ""))) != (
        "ror",
        ror_record.source_record_id,
    ):
        raise CertificationError(
            "ROR authority response does not match the exact target"
        )
    names = ror_record.raw.get("names")
    if not isinstance(names, list):
        raise CertificationError("ROR authority lacks canonical name metadata")
    display = tuple(
        entry["value"]
        for entry in names
        if isinstance(entry, dict)
        and isinstance(entry.get("value"), str)
        and entry["value"].strip()
        and isinstance(entry.get("types"), list)
        and "ror_display" in entry["types"]
    )
    if len(display) != 1:
        raise CertificationError("ROR canonical display name is missing or ambiguous")
    parents: set[str] = set()
    relationships = ror_record.raw.get("relationships", [])
    if not isinstance(relationships, list):
        raise CertificationError("ROR authority relationships are malformed")
    for relationship in relationships:
        if not isinstance(relationship, dict):
            raise CertificationError("ROR authority relationship is malformed")
        if str(relationship.get("type", "")).casefold() == "parent":
            parent = normalize_external_id("ror", str(relationship.get("id", "")))
            if parent is None:
                raise CertificationError("ROR parent authority is invalid")
            parents.add(parent[1])
    authority = InstitutionAuthorityRecord(
        institution_id=f"institution-ror-{ror_record.source_record_id}",
        ror_id=ror_record.source_record_id,
        canonical_name=display[0],
        active=ror_record.raw.get("status") == "active",
        parent_ror_ids=tuple(sorted(parents)),
    )
    references = (paper_reference, institution_reference, ror_reference)
    evidence = InstitutionResolutionEvidence(
        raw_name=raw_affiliation_name,
        source_evidence_ids=tuple(
            f"{item.provider}:{item.source_record_id}:{item.checksum}"
            for item in references
        ),
        source_manifest_digest=canonical_digest(references),
        authority_version=institution_authority_version((authority,)),
        direct_ror_ids=(authority.ror_id,),
        provider="inspire",
        provider_institution_id=paper_time_provider_institution_id,
    )
    result = certify_institution(evidence, (authority,), retain_exact_ror_identity=True)
    return replace(
        result,
        match_method="paper-native-provider-id-explicit-ror"
        if result.state == "certified"
        else result.match_method,
    )


def certify_institution(
    evidence: InstitutionResolutionEvidence,
    authority_records: tuple[InstitutionAuthorityRecord, ...],
    *,
    provider_crosswalk: dict[tuple[str, str], str] | None = None,
    retain_exact_ror_identity: bool = False,
) -> InstitutionCertificationResult:
    """Resolve only authority-supported exact evidence; never make a fuzzy guess."""

    by_ror = {record.ror_id: record for record in authority_records}
    if len(by_ror) != len(authority_records):
        raise ValueError("institution authority ROR ids must be unique")
    by_id = {record.institution_id: record for record in authority_records}
    if len(by_id) != len(authority_records):
        raise ValueError("canonical institution ids must be unique")
    expected_authority_version = institution_authority_version(authority_records)
    if evidence.authority_version != expected_authority_version:
        return InstitutionCertificationResult(
            evidence=evidence,
            state="conflicted",
            canonical_institution_id=None,
            source_institution_id=None,
            retained_subunit_label=evidence.subunit_label,
            match_method=None,
            candidate_institution_ids=(),
            reasons=(
                "institution evidence does not bind the exact ROR authority registry",
            ),
        )

    supported_ror_ids = set(evidence.direct_ror_ids)
    crosswalk_ror: str | None = None
    if (
        provider_crosswalk
        and evidence.provider
        and evidence.provider_institution_id
        and (
            crosswalk_ror := provider_crosswalk.get(
                (evidence.provider, evidence.provider_institution_id)
            )
        )
    ):
        if crosswalk_ror not in by_ror:
            return InstitutionCertificationResult(
                evidence=evidence,
                state="insufficient_evidence",
                canonical_institution_id=None,
                source_institution_id=None,
                retained_subunit_label=evidence.subunit_label,
                match_method=None,
                candidate_institution_ids=(),
                reasons=(
                    "provider crosswalk target is absent from the bound authority",
                ),
            )

    unknown_ror_ids = supported_ror_ids - set(by_ror)
    if unknown_ror_ids:
        return InstitutionCertificationResult(
            evidence=evidence,
            state="insufficient_evidence",
            canonical_institution_id=None,
            source_institution_id=None,
            retained_subunit_label=evidence.subunit_label,
            match_method=None,
            candidate_institution_ids=(),
            reasons=("authority metadata is missing for an asserted ROR identifier",),
        )
    if len(supported_ror_ids) > 1 or (
        supported_ror_ids
        and crosswalk_ror is not None
        and crosswalk_ror not in supported_ror_ids
    ):
        candidates = tuple(
            sorted(
                {
                    by_ror[item].institution_id
                    for item in supported_ror_ids
                    | ({crosswalk_ror} if crosswalk_ror is not None else set())
                }
            )
        )
        return InstitutionCertificationResult(
            evidence=evidence,
            state="conflicted",
            canonical_institution_id=None,
            source_institution_id=None,
            retained_subunit_label=evidence.subunit_label,
            match_method=None,
            candidate_institution_ids=candidates,
            reasons=(
                "paper-time institution evidence asserts conflicting ROR targets",
            ),
        )

    source: InstitutionAuthorityRecord | None = None
    method: str | None = None
    if supported_ror_ids:
        source = by_ror[next(iter(supported_ror_ids))]
        method = "direct-ror"

    name_matches: tuple[InstitutionAuthorityRecord, ...] = ()
    if evidence.raw_name and (name := normalize_search_term(evidence.raw_name)):
        name_matches = tuple(
            record for record in authority_records if name in record.exact_names
        )

    if source is None:
        context_candidates = tuple(
            sorted(
                {
                    candidate
                    for candidate in set(evidence.context_candidate_ids)
                    if candidate in by_id
                }
                | {record.institution_id for record in name_matches}
                | (
                    {by_ror[crosswalk_ror].institution_id}
                    if crosswalk_ror is not None
                    else set()
                )
            )
        )
        reviewed_context = evidence.reviewed_context_institution_id
        if (
            reviewed_context is not None
            and evidence.review_state == "reviewed-approved"
            and evidence.reviewed_by is not None
            and evidence.reviewed_at is not None
            and reviewed_context in context_candidates
            and by_id[reviewed_context].active
        ):
            source = by_id[reviewed_context]
            method = "reviewed-context-match"
        else:
            return InstitutionCertificationResult(
                evidence=evidence,
                state="needs_review" if context_candidates else "insufficient_evidence",
                canonical_institution_id=None,
                source_institution_id=None,
                retained_subunit_label=evidence.subunit_label,
                match_method=None,
                candidate_institution_ids=context_candidates,
                reasons=(
                    (
                        "context suggests candidates but lacks an explicit current "
                        "reviewed authority decision"
                        if context_candidates
                        else (
                            "no direct ROR or reviewed authority-backed "
                            "candidate exists"
                        )
                    ),
                ),
            )
    if not source.active:
        return InstitutionCertificationResult(
            evidence=evidence,
            state="needs_review",
            canonical_institution_id=None,
            source_institution_id=source.institution_id,
            retained_subunit_label=evidence.subunit_label,
            match_method=method,
            candidate_institution_ids=(source.institution_id,),
            reasons=("matched ROR organization is inactive or withdrawn",),
        )

    if retain_exact_ror_identity:
        # An independently identified ROR child is still an organization. Its
        # parent relationship does not request a metric rollup. This opt-in
        # adapter preserves the exact source organization and every relationship;
        # the historical parent-rollup contract below remains unchanged.
        if (
            evidence.direct_ror_ids != (source.ror_id,)
            or evidence.reviewed_rollup_institution_id is not None
        ):
            raise CertificationError(
                "exact organization retention needs one direct authority "
                "and cannot request a parent rollup"
            )
        return InstitutionCertificationResult(
            evidence=evidence,
            state="certified",
            canonical_institution_id=source.institution_id,
            source_institution_id=source.institution_id,
            retained_subunit_label=evidence.subunit_label,
            match_method=f"{method}-retain-exact-ror",
            candidate_institution_ids=(source.institution_id,),
            reasons=(),
            rule_version=EXACT_ROR_IDENTITY_RULE_VERSION,
        )

    target = source
    if source.parent_ror_ids:
        parent_candidates = tuple(
            by_ror[ror_id]
            for ror_id in source.parent_ror_ids
            if ror_id in by_ror and by_ror[ror_id].active
        )
        if len(parent_candidates) != 1:
            return InstitutionCertificationResult(
                evidence=evidence,
                state="needs_review",
                canonical_institution_id=None,
                source_institution_id=source.institution_id,
                retained_subunit_label=evidence.subunit_label or source.canonical_name,
                match_method=method,
                candidate_institution_ids=tuple(
                    sorted(item.institution_id for item in parent_candidates)
                ),
                reasons=("subunit does not have exactly one active canonical parent",),
            )
        reviewed_rollup = (
            evidence.review_state == "reviewed-approved"
            and evidence.reviewed_by is not None
            and evidence.reviewed_at is not None
            and evidence.reviewed_rollup_institution_id
            == parent_candidates[0].institution_id
        )
        if not source.parent_rollup_eligible and not reviewed_rollup:
            return InstitutionCertificationResult(
                evidence=evidence,
                state="needs_review",
                canonical_institution_id=None,
                source_institution_id=source.institution_id,
                retained_subunit_label=evidence.subunit_label or source.canonical_name,
                match_method=method,
                candidate_institution_ids=(parent_candidates[0].institution_id,),
                reasons=(
                    "authority hierarchy does not explicitly permit metric rollup",
                ),
            )
        target = parent_candidates[0]
        method = f"{method}-single-active-parent-rollup"

    return InstitutionCertificationResult(
        evidence=evidence,
        state="certified",
        canonical_institution_id=target.institution_id,
        source_institution_id=source.institution_id,
        retained_subunit_label=(
            evidence.subunit_label
            or (source.canonical_name if target is not source else None)
        ),
        match_method=method,
        candidate_institution_ids=(target.institution_id,),
        reasons=(),
    )
