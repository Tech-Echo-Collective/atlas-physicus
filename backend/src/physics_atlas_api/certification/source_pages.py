"""Compact record-to-page membership extracted by the existing provider parser.

Page bytes and record metadata have different checksums. This receipt preserves
that relationship without retaining either payload or claiming year completeness.
Transport provenance is upstream; content addressing is not origin authentication.
"""

import hashlib
import json
from dataclasses import dataclass

from ..connectors.base import ConnectorError, SourceRecord
from ..connectors.inspire import InspireConnector
from .contracts import CertificationError, canonical_digest

RECORD_PAGE_MEMBERSHIP_VERSION = "record-page-membership-v1"
MAXIMUM_SOURCE_PAGE_BYTES = 8 * 1024 * 1024
MAXIMUM_SOURCE_PAGE_RECORDS = 1000


def _sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


@dataclass(frozen=True)
class SourceRecordPageReceipt:
    provider: str
    partition_id: str
    page_checksum: str
    response_bytes: int
    record_checksums: tuple[tuple[str, str], ...]
    membership_digest: str
    version: str = RECORD_PAGE_MEMBERSHIP_VERSION

    def __post_init__(self) -> None:
        if (
            self.provider != "inspire"
            or not self.partition_id.strip()
            or self.version != RECORD_PAGE_MEMBERSHIP_VERSION
            or not _sha256(self.page_checksum)
            or isinstance(self.response_bytes, bool)
            or not 0 < self.response_bytes <= MAXIMUM_SOURCE_PAGE_BYTES
            or not isinstance(self.record_checksums, tuple)
            or len(self.record_checksums) > MAXIMUM_SOURCE_PAGE_RECORDS
            or any(
                not record_id.strip() or not _sha256(checksum)
                for record_id, checksum in self.record_checksums
            )
            or len({record_id for record_id, _ in self.record_checksums})
            != len(self.record_checksums)
            or self.membership_digest != self.content_digest
        ):
            raise CertificationError(
                "source page membership receipt is invalid or changed"
            )

    @property
    def content_digest(self) -> str:
        return canonical_digest(
            (
                self.provider,
                self.partition_id,
                self.page_checksum,
                self.response_bytes,
                self.record_checksums,
                self.version,
            )
        )


def capture_inspire_source_page(
    payload: bytes,
    *,
    connector: InspireConnector,
    partition_id: str,
) -> tuple[SourceRecordPageReceipt, tuple[SourceRecord, ...]]:
    """Verify exact page membership; return parsed records for ephemeral processing."""
    if (
        not isinstance(payload, bytes)
        or not 0 < len(payload) <= MAXIMUM_SOURCE_PAGE_BYTES
    ):
        raise CertificationError("source page exceeds the bounded byte limit")
    if not isinstance(connector, InspireConnector) or not partition_id.strip():
        raise CertificationError(
            "source page requires its existing parser and partition"
        )
    try:
        decoded = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as error:
        raise CertificationError("source page JSON is invalid") from error
    if not isinstance(decoded, dict):
        raise CertificationError("source page must be a provider response object")
    hits = decoded.get("hits")
    raw_records = hits.get("hits") if isinstance(hits, dict) else None
    if (
        not isinstance(raw_records, list)
        or len(raw_records) > MAXIMUM_SOURCE_PAGE_RECORDS
    ):
        raise CertificationError("source page exceeds the bounded record inventory")
    try:
        records = tuple(connector._records(decoded))
    except ConnectorError as error:
        raise CertificationError("source page cannot be parsed completely") from error
    membership = tuple((item.source_record_id, item.checksum) for item in records)
    page_checksum = hashlib.sha256(payload).hexdigest()
    receipt = SourceRecordPageReceipt(
        provider="inspire",
        partition_id=partition_id,
        page_checksum=page_checksum,
        response_bytes=len(payload),
        record_checksums=membership,
        membership_digest=canonical_digest(
            (
                "inspire",
                partition_id,
                page_checksum,
                len(payload),
                membership,
                RECORD_PAGE_MEMBERSHIP_VERSION,
            )
        ),
    )
    return receipt, records
