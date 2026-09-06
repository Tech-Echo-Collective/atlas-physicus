"""Source-bound per-paper attribution using existing authority and fraction rules.

Acquisition is injected and owned by the caller. Full provider records are used
only while verifying a paper, then are absent from the returned compact result.
Missing authority/geography remains an explicit withheld share, never zero or a
name-based affiliation guess.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Any
from urllib.parse import urlsplit

import pycountry

from ..attribution import (
    AuthorAttributionInput,
    FractionalAttributionResult,
    PaperTimeAffiliationAssertion,
    calculate_fractional_attribution,
)
from ..attribution.affiliation_identifiers import (
    align_affiliation_ror_evidence as _align_affiliation_ror_evidence,
)
from ..connectors.base import SourceRecord, normalize_external_id
from .automation import (
    ResolvedResearcherIdentifiers,
    SourceBoundPaperFacts,
    automatic_paper_identity_decision,
    capture_automatic_paper_facts,
)
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
    certify_paper_institution_link,
    institution_authority_version,
)
from .ror_affiliation_match import RORAffiliationMatchResult

LAUNCH_ATTRIBUTION_VERSION = "source-bound-launch-attribution-v1"
AuthorityLookup = Callable[[str], tuple[SourceRecord, EvidenceReference] | None]
RawAffiliationLookup = Callable[
    [SourceRecord, EvidenceReference, int, int], RORAffiliationMatchResult | None
]


@dataclass(frozen=True)
class LaunchInstitutionLocation:
    country_code: str
    city: str | None
    latitude: float | None
    longitude: float | None


@dataclass(frozen=True)
class LaunchAffiliationResolution:
    author_position: int
    affiliation_position: int
    source_field: str
    assertion_id: str
    raw_name: str | None
    state: CertificationState
    reasons: tuple[str, ...]
    institution: InstitutionCertificationResult | None
    canonical_name: str | None
    country_code: str | None
    locations: tuple[LaunchInstitutionLocation, ...]
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class LaunchAttributionResult:
    paper_reference: EvidenceReference
    fractional: FractionalAttributionResult | None
    affiliations: tuple[LaunchAffiliationResolution, ...]
    paper_time_affiliation_weight: Fraction | None
    researcher_state: CertificationState
    unresolved_reason_counts: tuple[tuple[str, int], ...]
    version: str = LAUNCH_ATTRIBUTION_VERSION


def _check_record(
    value: tuple[SourceRecord, EvidenceReference],
    provider: str,
    record_id: str,
) -> tuple[SourceRecord, EvidenceReference]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise CertificationError(
            "authority lookup must return an actual record and reference"
        )
    record, reference = value
    if (
        not isinstance(record, SourceRecord)
        or not isinstance(reference, EvidenceReference)
        or record.provider != provider
        or reference.provider != provider
        or record.source_record_id != record_id
        or reference.source_record_id != record_id
        or record.checksum != reference.checksum
        or not reference.source_snapshot_id
    ):
        raise CertificationError(
            "authority lookup does not bind its actual source record"
        )
    if provider == "ror" and normalize_external_id("ror", record.raw.get("id")) != (
        "ror",
        record_id,
    ):
        raise CertificationError("ROR authority payload identifies another institution")
    if provider == "inspire" and str(record.raw.get("control_number", "")) != record_id:
        raise CertificationError(
            "INSPIRE institution payload identifies another institution"
        )
    return record, reference


def _ror_ids(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CertificationError("paper-native ROR identifier inventory is malformed")
    values = set()
    for item in value:
        if not isinstance(item, dict):
            raise CertificationError("paper-native ROR identifier entry is malformed")
        if str(item.get("schema") or item.get("scheme") or "").casefold() != "ror":
            continue
        identifier = normalize_external_id("ror", item.get("value"))
        if identifier is None:
            raise CertificationError("paper-native ROR identifier is invalid")
        values.add(identifier[1])
    return tuple(sorted(values))


def _institution_id(affiliation: dict[str, Any]) -> str | None:
    value = affiliation.get("record")
    if isinstance(value, dict):
        value = value.get("$ref")
    if value is None:
        return None
    if not isinstance(value, str):
        raise CertificationError("paper-native institution link is malformed")
    url = urlsplit(value)
    prefix = "/api/institutions/"
    if (
        url.scheme != "https"
        or url.netloc != "inspirehep.net"
        or not url.path.startswith(prefix)
        or not url.path[len(prefix) :].isdecimal()
        or url.query
        or url.fragment
    ):
        raise CertificationError(
            "paper-native institution link is not an exact INSPIRE ID"
        )
    return url.path[len(prefix) :]


def _authority(record: SourceRecord) -> InstitutionAuthorityRecord:
    names = record.raw.get("names")
    if not isinstance(names, list):
        raise CertificationError("ROR authority has no canonical name inventory")
    display = tuple(
        item["value"]
        for item in names
        if isinstance(item, dict)
        and isinstance(item.get("value"), str)
        and item["value"].strip()
        and isinstance(item.get("types"), list)
        and "ror_display" in item["types"]
    )
    if len(display) != 1:
        raise CertificationError("ROR authority display name is missing or ambiguous")
    relationships = record.raw.get("relationships", [])
    if not isinstance(relationships, list):
        raise CertificationError("ROR authority relationship inventory is malformed")
    parents = set()
    for item in relationships:
        if not isinstance(item, dict):
            raise CertificationError("ROR authority relationship is malformed")
        if str(item.get("type", "")).casefold() == "parent":
            parent = normalize_external_id("ror", item.get("id"))
            if parent is None:
                raise CertificationError("ROR authority parent identifier is invalid")
            parents.add(parent[1])
    return InstitutionAuthorityRecord(
        institution_id=f"institution-ror-{record.source_record_id}",
        ror_id=record.source_record_id,
        canonical_name=display[0],
        active=record.raw.get("status") == "active",
        parent_ror_ids=tuple(sorted(parents)),
    )


def _locations(record: SourceRecord) -> tuple[LaunchInstitutionLocation, ...]:
    values = record.raw.get("locations", [])
    if not isinstance(values, list):
        raise CertificationError("ROR authority location inventory is malformed")
    locations = []
    for item in values:
        details = item.get("geonames_details") if isinstance(item, dict) else None
        if not isinstance(details, dict):
            raise CertificationError("ROR authority location entry is malformed")
        code = details.get("country_code")
        if not isinstance(code, str) or pycountry.countries.get(alpha_2=code) is None:
            raise CertificationError("ROR location has no recognized ISO country code")
        latitude, longitude = details.get("lat"), details.get("lng")
        if not (
            isinstance(latitude, (int, float))
            and not isinstance(latitude, bool)
            and isinstance(longitude, (int, float))
            and not isinstance(longitude, bool)
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            latitude, longitude = None, None
        locations.append(
            LaunchInstitutionLocation(
                code,
                details.get("name") if isinstance(details.get("name"), str) else None,
                float(latitude) if latitude is not None else None,
                float(longitude) if longitude is not None else None,
            )
        )
    return tuple(locations)


def _lifecycle_reasons(
    record: SourceRecord, paper_date: date | None
) -> tuple[str, ...]:
    """A parent is not a rollup request; lifecycle changes still need dated proof."""
    established = record.raw.get("established")
    if established is not None and (
        isinstance(established, bool)
        or not isinstance(established, int)
        or not 0 < established <= 9999
    ):
        raise CertificationError("ROR authority establishment metadata is malformed")
    relationships = record.raw.get("relationships", [])
    if not isinstance(relationships, list):
        raise CertificationError("ROR authority relationship inventory is malformed")
    lifecycle_change = False
    for item in relationships:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("type"), str)
            or item.get("type")
            not in {"parent", "child", "related", "predecessor", "successor"}
            or normalize_external_id("ror", item.get("id")) is None
        ):
            raise CertificationError(
                "ROR authority relationship is malformed or unsupported"
            )
        lifecycle_change = lifecycle_change or item["type"] in {
            "predecessor",
            "successor",
        }
    if paper_date is None:
        return ("institution-exact-paper-time-date-missing",)
    if established is not None and established > paper_date.year:
        return ("institution-authority-established-after-paper",)
    if lifecycle_change:
        return ("institution-lifecycle-requires-dated-resolution",)
    return ()


def _direct_ror_certification(
    *,
    paper_reference: EvidenceReference,
    source_field: str,
    raw_name: str | None,
    record: SourceRecord,
    reference: EvidenceReference,
) -> InstitutionCertificationResult:
    authority = _authority(record)
    references = (paper_reference, reference)
    return certify_institution(
        InstitutionResolutionEvidence(
            raw_name=raw_name,
            source_evidence_ids=(
                f"inspire:{paper_reference.source_record_id}:{source_field}:{paper_reference.checksum}",
                f"ror:{reference.source_record_id}:{reference.checksum}",
            ),
            source_manifest_digest=canonical_digest((references, source_field)),
            authority_version=institution_authority_version((authority,)),
            direct_ror_ids=(record.source_record_id,),
            provider="inspire",
        ),
        (authority,),
        retain_exact_ror_identity=True,
    )


def _resolve_affiliation(
    *,
    record: SourceRecord,
    reference: EvidenceReference,
    author: dict[str, Any],
    author_index: int,
    affiliation: dict[str, Any],
    affiliation_index: int,
    affiliation_count: int,
    source_key: str,
    source_facts: SourceBoundPaperFacts,
    institution_lookup: AuthorityLookup,
    ror_lookup: AuthorityLookup,
    raw_match: RawAffiliationLookup | None,
    structured_certifications: dict[
        tuple[EvidenceReference, EvidenceReference], InstitutionCertificationResult
    ],
) -> LaunchAffiliationResolution:
    source_field = f"authors[{author_index}].{source_key}[{affiliation_index}]"
    assertion_id = f"affiliation:{canonical_digest((reference, source_field))}"
    value = affiliation.get("value") or affiliation.get("name")
    raw_name = value if isinstance(value, str) and value.strip() else None

    def outcome(
        state: CertificationState,
        reasons: tuple[str, ...],
        institution: InstitutionCertificationResult | None = None,
        authority_record: SourceRecord | None = None,
        evidence: tuple[EvidenceReference, ...] = (reference,),
    ) -> LaunchAffiliationResolution:
        locations = _locations(authority_record) if authority_record is not None else ()
        countries = {item.country_code for item in locations}
        country_code = next(iter(countries)) if len(countries) == 1 else None
        if state == "certified" and country_code is None:
            state = "insufficient_evidence"
            reasons = ("authority-country-missing-or-ambiguous",)
        return LaunchAffiliationResolution(
            author_index + 1,
            affiliation_index + 1,
            source_field,
            assertion_id,
            raw_name,
            state,
            reasons,
            institution,
            _authority(authority_record).canonical_name
            if authority_record is not None
            else None,
            country_code,
            locations,
            evidence,
        )

    try:
        local = tuple(
            sorted(
                {
                    value
                    for key in ("identifiers", "external_ids", "externalIds")
                    for value in _ror_ids(affiliation.get(key))
                }
            )
        )
        direct, _, conflicts = _align_affiliation_ror_evidence(
            local_rors=local,
            author_rors=_ror_ids(author.get("affiliations_identifiers")),
            affiliation_count=affiliation_count,
        )
        provider_id = _institution_id(affiliation)
    except CertificationError as error:
        return outcome("conflicted", (str(error),))
    if raw_name is None and provider_id is None and not local:
        return outcome("insufficient_evidence", ("empty-paper-time-affiliation-entry",))
    if conflicts or len(direct) > 1:
        return outcome(
            "conflicted", conflicts or ("multiple-paper-native-ror-targets",)
        )

    provider_source = (
        institution_lookup(provider_id) if provider_id is not None else None
    )
    provider_record = None
    provider_reference = None
    provider_rors: tuple[str, ...] = ()
    if provider_source is not None:
        assert provider_id is not None
        provider_record, provider_reference = _check_record(
            provider_source, "inspire", provider_id
        )
        provider_rors = _ror_ids(provider_record.raw.get("external_system_identifiers"))
        if len(provider_rors) > 1 or (
            direct and provider_rors and direct != provider_rors
        ):
            return outcome(
                "conflicted", ("provider-and-paper-ror-assertions-conflict",)
            )
    target = direct[0] if direct else provider_rors[0] if provider_rors else None
    if target is not None:
        target_source = ror_lookup(target)
        if target_source is None:
            return outcome(
                "insufficient_evidence", ("exact-ror-authority-unavailable",)
            )
        ror_record, ror_reference = _check_record(target_source, "ror", target)
        lifecycle_reasons = _lifecycle_reasons(ror_record, source_facts.exact_date)
        if lifecycle_reasons:
            return outcome(
                "insufficient_evidence",
                lifecycle_reasons,
                authority_record=ror_record,
                evidence=(reference, ror_reference),
            )
        if (
            provider_record is not None
            and provider_reference is not None
            and provider_rors
        ):
            assert provider_id is not None
            cache_key = (provider_reference, ror_reference)
            institution = structured_certifications.get(cache_key)
            if institution is None:
                # The per-slot ID was already read above. Verify the shared
                # paper→authority chain once per exact authority within this call.
                institution = certify_paper_institution_link(
                    paper_record=record,
                    paper_reference=reference,
                    paper_time_provider_institution_id=provider_id,
                    institution_record=provider_record,
                    institution_reference=provider_reference,
                    ror_record=ror_record,
                    ror_reference=ror_reference,
                )
                structured_certifications[cache_key] = institution
            references: tuple[EvidenceReference, ...] = (
                reference,
                provider_reference,
                ror_reference,
            )
        else:
            # Direct IDs here came from this exact row, or the single-row author
            # alignment rule; never from another author's provider resolution.
            institution = _direct_ror_certification(
                paper_reference=reference,
                source_field=source_field,
                raw_name=raw_name,
                record=ror_record,
                reference=ror_reference,
            )
            references = (reference, ror_reference)
        return outcome(
            institution.state, institution.reasons, institution, ror_record, references
        )

    if (
        source_key == "raw_affiliations"
        and raw_name is not None
        and raw_match is not None
    ):
        if source_facts.exact_date is None:
            return outcome(
                "insufficient_evidence", ("raw-affiliation-exact-paper-date-missing",)
            )
        matched = raw_match(record, reference, author_index, affiliation_index)
        if matched is None:
            return outcome(
                "insufficient_evidence", ("raw-affiliation-authority-unavailable",)
            )
        if not isinstance(matched, RORAffiliationMatchResult):
            raise CertificationError(
                "raw affiliation lookup requires an exact typed match result"
            )
        matched.__post_init__()
        receipt = matched.receipt
        if (
            receipt.paper_reference != reference
            or receipt.source_field != f"{source_field}.value"
            or receipt.raw_affiliation != raw_name
            or receipt.publication_date != source_facts.exact_date
        ):
            raise CertificationError(
                "raw affiliation result is not bound to this author's exact source slot"
            )
        if matched.state != "certified":
            return outcome(
                matched.state,
                receipt.reasons,
                evidence=(reference, receipt.response_reference),
            )
        if receipt.chosen_ror_id is None or matched.certification is None:
            raise CertificationError(
                "certified raw affiliation has no authority target"
            )
        if (
            matched.certification.canonical_institution_id
            != f"institution-ror-{receipt.chosen_ror_id}"
            or matched.certification.evidence.direct_ror_ids != (receipt.chosen_ror_id,)
        ):
            raise CertificationError(
                "raw affiliation certification names a different authority target"
            )
        target_source = ror_lookup(receipt.chosen_ror_id)
        if target_source is None:
            return outcome(
                "insufficient_evidence", ("matched-ror-authority-unavailable",)
            )
        ror_record, ror_reference = _check_record(
            target_source, "ror", receipt.chosen_ror_id
        )
        if canonical_digest(ror_record.raw) != receipt.chosen_organization_checksum:
            raise CertificationError(
                "matched ROR authority differs from the verified candidate payload"
            )
        lifecycle_reasons = _lifecycle_reasons(ror_record, source_facts.exact_date)
        if lifecycle_reasons:
            return outcome(
                "insufficient_evidence",
                lifecycle_reasons,
                authority_record=ror_record,
                evidence=(reference, receipt.response_reference, ror_reference),
            )
        locations = _locations(ror_record)
        if {item.country_code for item in locations} != {receipt.country_code}:
            return outcome("conflicted", ("matched-ror-country-is-not-unambiguous",))
        return outcome(
            matched.state,
            receipt.reasons,
            matched.certification,
            ror_record,
            (reference, receipt.response_reference, ror_reference),
        )
    return outcome(
        "insufficient_evidence",
        (
            "paper-native-institution-link-has-no-ror-authority"
            if provider_id is not None
            else "paper-native-affiliation-has-no-resolved-authority",
        ),
    )


def attribute_launch_record(
    record: SourceRecord,
    *,
    reference: EvidenceReference,
    source_facts: SourceBoundPaperFacts,
    institution_lookup: AuthorityLookup,
    ror_lookup: AuthorityLookup,
    raw_match: RawAffiliationLookup | None = None,
) -> LaunchAttributionResult:
    """Verify per-author authority links then invoke Fractional Attribution v1.

    Lookup callbacks may return unavailable evidence, but cannot supply bare
    canonical IDs. Raw match callbacks receive zero-based author/raw-row indices.
    ``paper_time_affiliation_weight`` measures paper-native evidence presence;
    canonical allocated mass is separately exposed by ``fractional``.
    """
    captured = capture_automatic_paper_facts(
        record,
        context=source_facts.context,
        reference=reference,
        declared_date_basis=source_facts.declared_date_basis,
    )
    if record.provider != "inspire" or captured != source_facts:
        raise CertificationError(
            "attribution source facts differ from the actual paper record"
        )
    researcher_state = automatic_paper_identity_decision(
        source_facts, evidence_kind="researcher-identity"
    ).state
    raw_authors = record.raw.get("authors")
    if not isinstance(raw_authors, list) or not raw_authors:
        return LaunchAttributionResult(
            reference,
            None,
            (),
            None,
            researcher_state,
            (("missing-author-inventory", 1),),
        )
    inputs = []
    resolutions: list[LaunchAffiliationResolution] = []
    present_assertions = set()
    reasons: Counter[str] = Counter()
    researcher_assessments = source_facts.researcher_assessments
    structured_certifications: dict[
        tuple[EvidenceReference, EvidenceReference], InstitutionCertificationResult
    ] = {}
    for author_index, author in enumerate(raw_authors):
        if not isinstance(author, dict):
            raise CertificationError("attribution author inventory is malformed")
        source_key = (
            "affiliations" if author.get("affiliations") else "raw_affiliations"
        )
        affiliations = author.get(source_key, [])
        if affiliations is None:
            affiliations = []
        if not isinstance(affiliations, list) or any(
            not isinstance(item, dict) for item in affiliations
        ):
            raise CertificationError("attribution affiliation inventory is malformed")
        assertions = []
        for index, affiliation in enumerate(affiliations):
            resolution = _resolve_affiliation(
                record=record,
                reference=reference,
                author=author,
                author_index=author_index,
                affiliation=affiliation,
                affiliation_index=index,
                affiliation_count=len(affiliations),
                source_key=source_key,
                source_facts=source_facts,
                institution_lookup=institution_lookup,
                ror_lookup=ror_lookup,
                raw_match=raw_match,
                structured_certifications=structured_certifications,
            )
            resolutions.append(resolution)
            if (
                resolution.raw_name is not None
                or affiliation.get("record")
                or any(
                    affiliation.get(key)
                    for key in ("identifiers", "external_ids", "externalIds")
                )
            ):
                present_assertions.add(resolution.assertion_id)
            certified = (
                resolution.state == "certified" and resolution.institution is not None
            )
            institution_id = (
                resolution.institution.canonical_institution_id
                if certified and resolution.institution is not None
                else None
            )
            if certified and (
                institution_id is None or resolution.country_code is None
            ):
                raise CertificationError(
                    "certified affiliation lacks exact canonical geography"
                )
            assertions.append(
                PaperTimeAffiliationAssertion(
                    assertion_id=resolution.assertion_id,
                    resolution_status="resolved"
                    if certified
                    else "ambiguous"
                    if resolution.state == "conflicted"
                    else "unresolved",
                    source="inspire",
                    source_record_id=record.source_record_id,
                    evidence_version=LAUNCH_ATTRIBUTION_VERSION,
                    institution_id=institution_id,
                    country_id=f"country-{resolution.country_code.casefold()}"
                    if certified and resolution.country_code
                    else None,
                )
            )
            if not certified:
                reasons.update(resolution.reasons)
        if not assertions:
            reasons["missing-paper-time-affiliation"] += 1
        author_proof = researcher_assessments[author_index]
        author_value = author_proof.value
        assert isinstance(author_value, ResolvedResearcherIdentifiers)
        identifiers = (
            dict(author_value.identifiers)
            if author_proof.decision.state == "certified"
            else {}
        )
        native_id = identifiers.get("inspire-author")
        inputs.append(
            AuthorAttributionInput(
                author_slot_id=(
                    f"author-slot:{canonical_digest((reference, author_index))}"
                ),
                author_position=author_index + 1,
                researcher_id=f"inspire-author:{native_id}"
                if native_id is not None
                else None,
                affiliations=tuple(assertions),
            )
        )
    fractional = calculate_fractional_attribution(source_facts.context.paper_id, inputs)
    presence = sum(
        (
            share.weight
            for share in fractional.shares
            if set(share.affiliation_assertion_ids) & present_assertions
        ),
        start=Fraction(0),
    )
    return LaunchAttributionResult(
        reference,
        fractional,
        tuple(resolutions),
        presence,
        researcher_state,
        tuple(sorted(reasons.items())),
    )
