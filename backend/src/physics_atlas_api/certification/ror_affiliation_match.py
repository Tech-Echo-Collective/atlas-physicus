"""Bounded ROR cross-check of exact paper-native affiliation text.

The trusted acquisition caller supplies actual response bytes and timestamps.
Checksums bind the evidence; a URL alone does not authenticate provider origin.
This module performs no network access and retains no provider payload. A ROR
suggestion is never sufficient by itself, and is not relabelled a direct ROR
assertion in the original paper. Unresolved cases keep their attribution mass.
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, fields, replace
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

import pycountry

from ..connectors.base import SourceRecord, normalize_external_id
from .contracts import (
    CertificationError,
    CertificationState,
    EvidenceReference,
    canonical_digest,
)
from .institutions import (
    InstitutionAuthorityRecord,
    InstitutionCertificationResult,
    InstitutionResolutionEvidence,
    certify_institution,
    institution_authority_version,
)

ROR_AFFILIATION_MATCH_VERSION = "paper-native-ror-affiliation-crosscheck-v1"
MAXIMUM_ROR_MATCH_BYTES = 8 * 1024 * 1024
MAXIMUM_ROR_MATCH_CANDIDATES = 100
_ENDPOINT = "https://api.ror.org/v2/organizations"


def ror_affiliation_request_uri(raw_affiliation: str) -> str:
    if not isinstance(raw_affiliation, str) or not raw_affiliation.strip():
        raise CertificationError(
            "ROR affiliation query needs exact nonempty source text"
        )
    return f"{_ENDPOINT}?{urlencode({'affiliation': raw_affiliation})}"


def ror_affiliation_reference_id(raw_affiliation: str) -> str:
    return f"affiliation-query:{hashlib.sha256(raw_affiliation.encode()).hexdigest()}"


def _normal(value: str) -> str:
    # No transliteration, stop-word removal, abbreviation expansion or fuzzy match.
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _contains(text: str, term: str) -> bool:
    return (
        bool(term)
        and re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text) is not None
    )


def _simple_subunit(clause: str) -> bool:
    """Recognize a small grammatical subset, not arbitrary prefixed affiliations.

    These words only bound address parsing; they do not classify scientific fields.
    Unknown department names remain unresolved rather than swallowing another
    institution hidden after e.g. 'Department of Physics at Other University'.
    """
    subject = (
        r"(?:physics|theoretical physics|experimental physics|nuclear physics|"
        r"particle physics|applied physics|astronomy|astrophysics|mathematics|"
        r"applied mathematics|chemistry|biology|computer science|science|sciences|"
        r"engineering)"
    )
    return (
        re.fullmatch(
            rf"(?:department|dept\.?|faculty|school|division) (?:of )?{subject}"
            rf"(?: (?:and|&) {subject})?",
            clause,
        )
        is not None
    )


@dataclass(frozen=True)
class RORAffiliationMatchReceipt:
    paper_reference: EvidenceReference
    source_field: str
    raw_affiliation: str
    publication_date: date
    request_uri: str
    response_reference: EvidenceReference
    requested_at: datetime
    received_at: datetime
    response_bytes: int
    candidate_ror_ids: tuple[str, ...]
    chosen_ror_id: str | None
    chosen_organization_checksum: str | None
    matched_label: str | None
    country_code: str | None
    city: str | None
    state: CertificationState
    reasons: tuple[str, ...]
    version: str = ROR_AFFILIATION_MATCH_VERSION

    @property
    def input_digest(self) -> str:
        return canonical_digest(
            {
                item.name: getattr(self, item.name)
                for item in fields(self)
                if item.name not in {"state", "reasons"}
            }
        )

    @property
    def content_digest(self) -> str:
        return canonical_digest(self)


@dataclass(frozen=True)
class RORAffiliationMatchResult:
    receipt: RORAffiliationMatchReceipt
    certification: InstitutionCertificationResult | None

    def __post_init__(self) -> None:
        if self.receipt.version != ROR_AFFILIATION_MATCH_VERSION:
            raise CertificationError("ROR affiliation cross-check version is stale")
        if self.certification is None:
            if self.receipt.state == "certified" or not self.receipt.reasons:
                raise CertificationError(
                    "unresolved ROR match cannot claim certification"
                )
        elif (
            self.certification.state != self.receipt.state
            or self.certification.reasons != self.receipt.reasons
            or self.certification.evidence.source_manifest_digest
            != self.receipt.input_digest
            or self.certification.rule_version != ROR_AFFILIATION_MATCH_VERSION
            or self.certification.match_method != ROR_AFFILIATION_MATCH_VERSION
        ):
            raise CertificationError(
                "ROR affiliation result differs from its exact receipt"
            )

    @property
    def state(self) -> CertificationState:
        return self.receipt.state

    @property
    def canonical_institution_id(self) -> str | None:
        return (
            self.certification.canonical_institution_id
            if self.certification is not None and self.state == "certified"
            else None
        )


def _names(organization: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    entries = organization.get("names")
    if not isinstance(entries, list):
        raise CertificationError("ROR matching authority lacks name metadata")
    display = []
    labels = []
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("value"), str)
            or not entry["value"].strip()
            or not isinstance(entry.get("types"), list)
        ):
            raise CertificationError("ROR matching authority name is malformed")
        kinds = entry["types"]
        if "ror_display" in kinds:
            display.append(entry["value"])
        if "acronym" not in kinds and any(
            kind in kinds for kind in ("ror_display", "label", "alias")
        ):
            labels.append(entry["value"])
    if len(display) != 1:
        raise CertificationError("ROR matching authority display name is not unique")
    return display[0], tuple(sorted(set(labels)))


def _geography(
    organization: dict[str, Any],
    tail: tuple[str, ...],
) -> tuple[str | None, str | None, str | None]:
    """Require country corroboration and exact supplied city, never guess geography."""
    if not tail:
        return None, None, "paper-native geographic corroboration is missing"
    locations = organization.get("locations")
    if not isinstance(locations, list) or not locations:
        return None, None, "affiliation address has no ROR location corroboration"
    observed_countries = set()
    country_clauses = set()
    for index, clause in enumerate(tail):
        for country in pycountry.countries:
            names = {
                _normal(country.name),
                _normal(getattr(country, "official_name", country.name)),
                _normal(getattr(country, "common_name", country.name)),
            }
            codes = {_normal(country.alpha_2), _normal(country.alpha_3)}
            if clause in codes or any(_contains(clause, name) for name in names):
                observed_countries.add(country.alpha_2)
                country_clauses.add(index)
    if len(observed_countries) != 1:
        return (
            None,
            None,
            "affiliation country is absent, ambiguous or not exactly supported",
        )
    country_code = next(iter(observed_countries))
    candidates = []
    for location in locations:
        details = (
            location.get("geonames_details") if isinstance(location, dict) else None
        )
        if not isinstance(details, dict):
            raise CertificationError("ROR matching location metadata is malformed")
        if details.get("country_code") == country_code:
            candidates.append(details)
    if not candidates:
        return None, None, "paper-native country contradicts the chosen ROR location"
    address = " ".join(tail)
    cities = tuple(
        sorted(
            {
                details["name"]
                for details in candidates
                if isinstance(details.get("name"), str)
                and _contains(address, _normal(details["name"]))
            }
        )
    )
    # A country-only suffix does not invent a city. A longer address must contain
    # one exact matching city; unknown or contradictory address strings fail closed.
    country_only = (
        len(tail) == 1
        and 0 in country_clauses
        and any(
            tail[0] == _normal(name)
            for country in pycountry.countries
            if country.alpha_2 == country_code
            for name in (
                country.name,
                getattr(country, "official_name", country.name),
                getattr(country, "common_name", country.name),
                country.alpha_2,
                country.alpha_3,
            )
        )
    )
    if not country_only and len(cities) != 1:
        return (
            country_code,
            None,
            "paper-native city is absent or inconsistent with ROR",
        )
    allowed_terms = {_normal(city) for city in cities}
    for country in pycountry.countries:
        if country.alpha_2 == country_code:
            allowed_terms.update(
                _normal(name)
                for name in (
                    country.name,
                    getattr(country, "official_name", country.name),
                    getattr(country, "common_name", country.name),
                    country.alpha_2,
                    country.alpha_3,
                )
            )
    for details in candidates:
        if details.get("name") in cities:
            allowed_terms.update(
                _normal(details[key])
                for key in (
                    "country_subdivision_name",
                    "country_subdivision_code",
                )
                if isinstance(details.get(key), str) and details[key]
            )
    for clause in tail:
        remaining = clause
        for term in sorted(allowed_terms, key=len, reverse=True):
            remaining = re.sub(r"(?<!\w)" + re.escape(term) + r"(?!\w)", "", remaining)
        if any(character.isalpha() for character in remaining):
            return (
                country_code,
                cities[0] if cities else None,
                (
                    "additional unclassified address or institution clause "
                    "remains unresolved"
                ),
            )
    return country_code, cities[0] if cities else None, None


def certify_paper_raw_affiliation_match(
    *,
    paper_record: SourceRecord,
    paper_reference: EvidenceReference,
    author_index: int,
    raw_affiliation_index: int,
    request_uri: str,
    response_payload: bytes,
    response_reference: EvidenceReference,
    requested_at: datetime,
    received_at: datetime,
    http_status: int,
) -> RORAffiliationMatchResult:
    """Cross-check one author appearance without acquiring or persisting data."""
    if (
        paper_record.provider != "inspire"
        or paper_reference.provider != paper_record.provider
        or paper_reference.source_record_id != paper_record.source_record_id
        or paper_reference.checksum != paper_record.checksum
        or not paper_reference.source_snapshot_id
        or str(paper_record.raw.get("control_number", ""))
        != paper_record.source_record_id
    ):
        raise CertificationError(
            "raw affiliation does not bind the exact INSPIRE paper"
        )
    authors = paper_record.raw.get("authors")
    if (
        isinstance(author_index, bool)
        or not isinstance(author_index, int)
        or not isinstance(authors, list)
        or not 0 <= author_index < len(authors)
        or not isinstance(authors[author_index], dict)
    ):
        raise CertificationError("raw affiliation author position is invalid")
    affiliations = authors[author_index].get("raw_affiliations")
    if (
        isinstance(raw_affiliation_index, bool)
        or not isinstance(raw_affiliation_index, int)
        or not isinstance(affiliations, list)
        or not 0 <= raw_affiliation_index < len(affiliations)
        or not isinstance(affiliations[raw_affiliation_index], dict)
    ):
        raise CertificationError("paper-native raw affiliation position is invalid")
    raw = affiliations[raw_affiliation_index].get("value")
    if not isinstance(raw, str) or not raw.strip():
        raise CertificationError("paper-native raw affiliation text is missing")
    raw_date = paper_record.raw.get("preprint_date")
    if (
        not isinstance(raw_date, str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date) is None
    ):
        raise CertificationError(
            "paper-native affiliation lacks an exact preprint date"
        )
    try:
        publication_date = date.fromisoformat(raw_date)
    except ValueError as error:
        raise CertificationError("paper-native affiliation date is invalid") from error
    url = urlsplit(request_uri)
    if (
        (url.scheme, url.netloc, url.path)
        != ("https", "api.ror.org", "/v2/organizations")
        or url.fragment
        or parse_qsl(url.query, keep_blank_values=True) != [("affiliation", raw)]
        or not isinstance(response_payload, bytes)
        or not 0 < len(response_payload) <= MAXIMUM_ROR_MATCH_BYTES
        or response_reference.provider != "ror"
        or response_reference.source_record_id != ror_affiliation_reference_id(raw)
        or response_reference.checksum != hashlib.sha256(response_payload).hexdigest()
        or not response_reference.source_snapshot_id
        or http_status != 200
        or isinstance(http_status, bool)
        or any(
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
            for value in (requested_at, received_at)
        )
        or received_at < requested_at
        or publication_date > requested_at.date()
    ):
        raise CertificationError(
            "ROR match response does not bind exact query, bytes and times"
        )
    try:
        payload = json.loads(response_payload)
    except (ValueError, UnicodeDecodeError) as error:
        raise CertificationError("ROR match response JSON is invalid") from error
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or len(items) > MAXIMUM_ROR_MATCH_CANDIDATES:
        raise CertificationError(
            "ROR match candidate inventory is invalid or unbounded"
        )
    candidates: dict[str, tuple[dict[str, Any], tuple[str, ...], str]] = {}
    chosen = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("chosen"), bool):
            raise CertificationError("ROR match choice metadata is malformed")
        organization = item.get("organization")
        if not isinstance(organization, dict):
            raise CertificationError("ROR matching candidate is malformed")
        identifier = normalize_external_id("ror", organization.get("id"))
        if identifier is None or identifier[1] in candidates:
            raise CertificationError(
                "ROR matching candidate identities are invalid or duplicate"
            )
        display, labels = _names(organization)
        candidates[identifier[1]] = (organization, labels, display)
        if item["chosen"]:
            chosen.append(identifier[1])
    selected = chosen[0] if len(chosen) == 1 else None
    receipt = RORAffiliationMatchReceipt(
        paper_reference=paper_reference,
        source_field=f"authors[{author_index}].raw_affiliations[{raw_affiliation_index}].value",
        raw_affiliation=raw,
        publication_date=publication_date,
        request_uri=request_uri,
        response_reference=response_reference,
        requested_at=requested_at,
        received_at=received_at,
        response_bytes=len(response_payload),
        candidate_ror_ids=tuple(sorted(candidates)),
        chosen_ror_id=selected,
        chosen_organization_checksum=canonical_digest(candidates[selected][0])
        if selected
        else None,
        matched_label=None,
        country_code=None,
        city=None,
        state="needs_review",
        reasons=("ROR match has no unique chosen authority",),
    )
    if selected is None:
        return RORAffiliationMatchResult(receipt, None)
    organization, labels, display = candidates[selected]
    clauses = tuple(_normal(item) for item in re.split(r"[,;\n]", raw) if _normal(item))
    matched = {
        (index, label)
        for index, clause in enumerate(clauses)
        for label in labels
        if clause == _normal(label)
    }
    matched_positions = {index for index, _ in matched}
    competing = {
        identifier
        for identifier, (_, names, _) in candidates.items()
        if identifier != selected and any(_normal(name) in clauses for name in names)
    }
    if len(matched_positions) != 1 or competing:
        return RORAffiliationMatchResult(
            replace(
                receipt,
                reasons=(
                    "chosen ROR lacks a unique whole institutional clause "
                    "or conflicts with another institution",
                ),
            ),
            None,
        )
    position = next(iter(matched_positions))
    # A second named organization inside one raw assertion is not one affiliation.
    # Unrecognized prefixes are deliberately withheld instead of silently rolled up.
    if any(not _simple_subunit(clause) for clause in clauses[:position]):
        return RORAffiliationMatchResult(
            replace(
                receipt,
                reasons=(
                    "additional organization or unclassified subunit clause "
                    "remains unresolved",
                ),
            ),
            None,
        )
    country_code, city, reason = _geography(organization, clauses[position + 1 :])
    matched_label = sorted(label for _, label in matched)[0]
    receipt = replace(
        receipt, matched_label=matched_label, country_code=country_code, city=city
    )
    if reason is not None:
        return RORAffiliationMatchResult(replace(receipt, reasons=(reason,)), None)
    established = organization.get("established")
    if established is not None and (
        isinstance(established, bool) or not isinstance(established, int)
    ):
        raise CertificationError("ROR organization establishment metadata is malformed")
    if established is not None and established > publication_date.year:
        return RORAffiliationMatchResult(
            replace(
                receipt,
                reasons=(
                    "chosen ROR organization postdates the paper-time affiliation",
                ),
            ),
            None,
        )
    relationships = organization.get("relationships", [])
    if not isinstance(relationships, list):
        raise CertificationError("ROR relationship inventory is malformed")
    parents = set()
    for relationship in relationships:
        if not isinstance(relationship, dict):
            raise CertificationError("ROR relationship metadata is malformed")
        relation_type = relationship.get("type")
        if not isinstance(relation_type, str) or relation_type not in {
            "parent",
            "child",
            "related",
            "predecessor",
            "successor",
        }:
            raise CertificationError("ROR relationship type is unsupported")
        if relation_type in {"predecessor", "successor"}:
            return RORAffiliationMatchResult(
                replace(
                    receipt,
                    reasons=(
                        "historical predecessor/successor identity "
                        "is not established by this match",
                    ),
                ),
                None,
            )
        if relation_type == "parent":
            parent = normalize_external_id("ror", relationship.get("id"))
            if parent is None:
                raise CertificationError("ROR parent identity is malformed")
            parents.add(parent[1])
    authority = InstitutionAuthorityRecord(
        institution_id=f"institution-ror-{selected}",
        ror_id=selected,
        canonical_name=display,
        aliases=labels,
        active=organization.get("status") == "active",
        parent_ror_ids=tuple(sorted(parents)),
    )
    evidence = InstitutionResolutionEvidence(
        raw_name=raw,
        source_evidence_ids=(
            f"inspire:{paper_reference.source_record_id}:{receipt.source_field}",
            f"ror:{response_reference.source_record_id}:{response_reference.checksum}",
        ),
        source_manifest_digest=receipt.input_digest,
        authority_version=institution_authority_version((authority,)),
        # This verified adapter supplies the matched authority target to the
        # unchanged identity/lifecycle validator; the paper did NOT assert it.
        direct_ror_ids=(selected,),
        provider="ror",
        provider_institution_id=response_reference.source_record_id,
    )
    certification = certify_institution(
        evidence, (authority,), retain_exact_ror_identity=True
    )
    certification = replace(
        certification,
        match_method=ROR_AFFILIATION_MATCH_VERSION,
        rule_version=ROR_AFFILIATION_MATCH_VERSION,
    )
    receipt = replace(receipt, state=certification.state, reasons=certification.reasons)
    return RORAffiliationMatchResult(receipt, certification)
