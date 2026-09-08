"""Explicit arXiv administrator duplicate evidence, never guessed equivalence.

Transport authenticates the official response; this bounded parser binds its
actual bytes and keeps only the irrecoverable identity fact. Legacy extraction
and merge behavior remain unchanged unless the caller supplies this authority.
"""

import hashlib
from dataclasses import dataclass, fields, replace
from datetime import datetime
from html.parser import HTMLParser

from ..historical_replay import PaperEvidenceOccurrence, StrongIdentifier
from .contracts import CertificationError, EvidenceReference, canonical_digest
from .launch_inputs import LaunchSourceOccurrence

ARXIV_ADMIN_DUPLICATE_VERSION = "arxiv-admin-duplicate-identity-v1"
MAXIMUM_ARXIV_IDENTITY_PAGE_BYTES = 256_000
_WITHDRAWN = "This paper has been withdrawn by arXiv Admin"


def _notice(target: str) -> str:
    return (
        "arXiv admin note: This submission has been withdrawn by arXiv "
        f"administrators as it is a duplicate of arXiv:{target}. Please refer "
        "to that document for any more recent versions"
    )


@dataclass(frozen=True)
class ArxivAdminDuplicateEvidence:
    reference: EvidenceReference
    request_uri: str
    requested_at: datetime
    received_at: datetime
    original_id: str
    replacement_id: str
    notice: str
    replacement_uri: str
    withdrawn_marker: str
    version: str = ARXIV_ADMIN_DUPLICATE_VERSION

    def __post_init__(self) -> None:
        original = StrongIdentifier("arxiv", self.original_id).value
        replacement = StrongIdentifier("arxiv", self.replacement_id).value
        if (
            original != self.original_id
            or replacement != self.replacement_id
            or original == replacement
            or self.reference.provider != "arxiv"
            or self.reference.source_record_id != original
            or not self.reference.source_snapshot_id
            or self.request_uri != f"https://arxiv.org/abs/{original}"
            or self.replacement_uri != f"https://arxiv.org/abs/{replacement}"
            or self.requested_at.tzinfo is None
            or self.received_at.tzinfo is None
            or self.received_at < self.requested_at
            or self.notice != _notice(replacement)
            or self.withdrawn_marker != _WITHDRAWN
            or self.version != ARXIV_ADMIN_DUPLICATE_VERSION
        ):
            raise CertificationError(
                "arXiv administrator duplicate evidence is invalid"
            )


class _AuthorityPage(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.identifiers: list[str] = []
        self.comments: list[list[str]] = []
        self.links: list[str] = []
        self.markers: list[list[str]] = []
        self.in_comment = False
        self.in_marker = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "meta" and attributes.get("name") == "citation_arxiv_id":
            self.identifiers.append(attributes.get("content") or "")
        if tag == "td" and "comments" in classes:
            self.in_comment = True
            self.comments.append([])
        if tag == "span" and "error" in classes:
            self.in_marker = True
            self.markers.append([])
        if tag == "a" and self.in_comment:
            self.links.append(attributes.get("href") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self.in_comment = False
        if tag == "span":
            self.in_marker = False

    def handle_data(self, data: str) -> None:
        if self.in_comment:
            self.comments[-1].append(data)
        if self.in_marker:
            self.markers[-1].append(data)


def capture_arxiv_admin_duplicate(
    payload: bytes,
    *,
    request_uri: str,
    requested_at: datetime,
    received_at: datetime,
    source_snapshot_id: str,
) -> ArxivAdminDuplicateEvidence:
    """Extract only one exact native administrator notice from an official read."""
    if not isinstance(payload, bytes) or not (
        0 < len(payload) <= MAXIMUM_ARXIV_IDENTITY_PAGE_BYTES
    ):
        raise CertificationError("arXiv identity page exceeds its bounded size")
    parser = _AuthorityPage()
    try:
        parser.feed(payload.decode("utf-8"))
        parser.close()
    except (UnicodeError, ValueError) as error:
        raise CertificationError("arXiv identity page cannot be parsed") from error
    comments = [" ".join("".join(parts).split()) for parts in parser.comments]
    markers = [" ".join("".join(parts).split()) for parts in parser.markers]
    if (
        len(parser.identifiers) != 1
        or len(comments) != 1
        or markers != [_WITHDRAWN]
        or len(parser.links) != 1
        or not parser.links[0].startswith("https://arxiv.org/abs/")
    ):
        raise CertificationError(
            "arXiv page has no unique administrator duplicate proof"
        )
    original = parser.identifiers[0]
    target = parser.links[0].removeprefix("https://arxiv.org/abs/")
    return ArxivAdminDuplicateEvidence(
        reference=EvidenceReference(
            "arxiv", original, hashlib.sha256(payload).hexdigest(), source_snapshot_id
        ),
        request_uri=request_uri,
        requested_at=requested_at,
        received_at=received_at,
        original_id=original,
        replacement_id=target,
        notice=comments[0],
        replacement_uri=parser.links[0],
        withdrawn_marker=markers[0],
    )


@dataclass(frozen=True, kw_only=True)
class LaunchDuplicateResolvedOccurrence(LaunchSourceOccurrence):
    original_identity: PaperEvidenceOccurrence
    duplicate_authority: ArxivAdminDuplicateEvidence

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.duplicate_authority, ArxivAdminDuplicateEvidence):
            raise CertificationError(
                "launch identity requires exact duplicate authority"
            )
        self.duplicate_authority.__post_init__()
        original = StrongIdentifier("arxiv", self.duplicate_authority.original_id)
        replacement = StrongIdentifier("arxiv", self.duplicate_authority.replacement_id)
        if not {original, replacement} <= set(self.original_identity.identifiers):
            raise CertificationError(
                "duplicate identifiers are not both source asserted"
            )
        expected = replace(
            self.original_identity,
            identifiers=tuple(
                item for item in self.original_identity.identifiers if item != original
            ),
        )
        if expected != self.identity:
            raise CertificationError(
                "duplicate resolution changed unrelated source facts"
            )

    @property
    def identity_references(self) -> tuple[EvidenceReference, ...]:
        return tuple(
            sorted(
                (self.reference, self.duplicate_authority.reference),
                key=canonical_digest,
            )
        )


def resolve_launch_admin_duplicate(
    occurrence: LaunchSourceOccurrence,
    authority: ArxivAdminDuplicateEvidence,
) -> LaunchDuplicateResolvedOccurrence:
    """One exact replacement within an existing occurrence; no new corpus member."""
    if type(occurrence) is not LaunchSourceOccurrence:
        raise CertificationError("duplicate resolution requires an original occurrence")
    occurrence.__post_init__()
    authority.__post_init__()
    original = StrongIdentifier("arxiv", authority.original_id)
    values = {
        field.name: getattr(occurrence, field.name) for field in fields(occurrence)
    }
    values["identity"] = replace(
        occurrence.identity,
        identifiers=tuple(
            item for item in occurrence.identity.identifiers if item != original
        ),
    )
    return LaunchDuplicateResolvedOccurrence(
        **values,
        original_identity=occurrence.identity,
        duplicate_authority=authority,
    )
