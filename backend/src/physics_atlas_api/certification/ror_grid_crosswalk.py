"""Bounded exact INSPIRE GRID → official ROR identifier crosswalk.

No names, scores, inferred parent identity or lifecycle approval are used here.
The existing attribution validator still checks active status, dated lifecycle
and geography. Transport must authenticate the supplied official response.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from ..connectors.base import SourceRecord, normalize_external_id
from .contracts import CertificationError, EvidenceReference, canonical_digest

ROR_GRID_CROSSWALK_VERSION = "paper-native-inspire-grid-ror-v1"
MAXIMUM_ROR_GRID_RESPONSE_BYTES = 256_000


def inspire_grid_id(record: SourceRecord) -> str | None:
    values = record.raw.get("external_system_identifiers", [])
    if not isinstance(values, list):
        raise CertificationError("INSPIRE external identifier inventory is malformed")
    grids = set()
    for item in values:
        if not isinstance(item, dict):
            raise CertificationError("INSPIRE external identifier is malformed")
        if str(item.get("schema", "")).casefold() != "grid":
            continue
        value = item.get("value")
        if (
            not isinstance(value, str)
            or re.fullmatch(r"grid\.\d+\.[0-9a-f]+", value) is None
        ):
            raise CertificationError("INSPIRE GRID identifier is malformed")
        grids.add(value)
    if len(grids) > 1:
        raise CertificationError("INSPIRE GRID identifiers are ambiguous")
    return next(iter(grids)) if grids else None


def ror_grid_request_uri(grid: str) -> str:
    if re.fullmatch(r"grid\.\d+\.[0-9a-f]+", grid) is None:
        raise CertificationError("exact ROR crosswalk requires a GRID identifier")
    return "https://api.ror.org/v2/organizations?" + urlencode(
        {"query.advanced": f'external_ids.all:"{grid}"', "all_status": "true"}
    )


def _contains_grid(record: SourceRecord, grid: str) -> bool:
    values = record.raw.get("external_ids")
    if not isinstance(values, list):
        raise CertificationError("ROR external identifier inventory is malformed")
    result = False
    for item in values:
        if not isinstance(item, dict):
            raise CertificationError("ROR external identifier entry is malformed")
        if item.get("type") != "grid":
            continue
        identifiers = item.get("all")
        if not isinstance(identifiers, list) or any(
            not isinstance(value, str) for value in identifiers
        ):
            raise CertificationError("ROR GRID identifier inventory is malformed")
        result = result or grid in identifiers
    return result


@dataclass(frozen=True)
class RORGridCrosswalkReceipt:
    grid_id: str
    institution_reference: EvidenceReference
    response_reference: EvidenceReference
    ror_reference: EvidenceReference
    request_uri: str
    requested_at: datetime
    received_at: datetime
    response_bytes: int
    version: str = ROR_GRID_CROSSWALK_VERSION

    @property
    def content_digest(self) -> str:
        return canonical_digest(self)


@dataclass(frozen=True)
class RORGridCrosswalkResult:
    receipt: RORGridCrosswalkReceipt
    ror_record: SourceRecord
    ror_reference: EvidenceReference

    def __post_init__(self) -> None:
        receipt = self.receipt
        if (
            receipt.version != ROR_GRID_CROSSWALK_VERSION
            or receipt.request_uri != ror_grid_request_uri(receipt.grid_id)
            or receipt.institution_reference.provider != "inspire"
            or not receipt.institution_reference.source_snapshot_id
            or receipt.response_reference.provider != "ror"
            or receipt.response_reference.source_record_id
            != f"grid-query:{receipt.grid_id}"
            or not receipt.response_reference.source_snapshot_id
            or receipt.requested_at.tzinfo is None
            or receipt.received_at.tzinfo is None
            or receipt.received_at < receipt.requested_at
            or not 0 < receipt.response_bytes <= MAXIMUM_ROR_GRID_RESPONSE_BYTES
            or receipt.ror_reference != self.ror_reference
            or self.ror_record.provider != "ror"
            or self.ror_reference.provider != "ror"
            or self.ror_record.source_record_id != self.ror_reference.source_record_id
            or self.ror_record.checksum != self.ror_reference.checksum
            or not self.ror_reference.source_snapshot_id
            or normalize_external_id("ror", self.ror_record.raw.get("id"))
            != ("ror", self.ror_record.source_record_id)
            or not _contains_grid(self.ror_record, receipt.grid_id)
        ):
            raise CertificationError("exact ROR GRID crosswalk does not reconstruct")


def capture_ror_grid_crosswalk(
    *,
    institution_record: SourceRecord,
    institution_reference: EvidenceReference,
    response_payload: bytes,
    request_uri: str,
    requested_at: datetime,
    received_at: datetime,
    source_snapshot_id: str,
) -> RORGridCrosswalkResult | None:
    grid = inspire_grid_id(institution_record)
    if (
        grid is None
        or institution_record.provider != "inspire"
        or institution_reference.provider != "inspire"
        or institution_reference.source_record_id != institution_record.source_record_id
        or institution_reference.checksum != institution_record.checksum
        or str(institution_record.raw.get("control_number", ""))
        != institution_record.source_record_id
        or not institution_reference.source_snapshot_id
        or request_uri != ror_grid_request_uri(grid)
        or not isinstance(response_payload, bytes)
        or not 0 < len(response_payload) <= MAXIMUM_ROR_GRID_RESPONSE_BYTES
        or requested_at.tzinfo is None
        or received_at.tzinfo is None
        or received_at < requested_at
        or not source_snapshot_id.strip()
    ):
        raise CertificationError(
            "GRID crosswalk source binding or bounded query is invalid"
        )
    try:
        payload = json.loads(response_payload)
    except (UnicodeError, ValueError) as error:
        raise CertificationError("ROR GRID response cannot be parsed") from error
    if not isinstance(payload, dict):
        raise CertificationError("ROR GRID response is malformed")
    total, items = payload.get("number_of_results"), payload.get("items")
    if (
        isinstance(total, bool)
        or not isinstance(total, int)
        or not isinstance(items, list)
    ):
        raise CertificationError("ROR GRID result inventory is malformed")
    if total == 0 and items == []:
        return None
    if total != 1 or len(items) != 1 or not isinstance(items[0], dict):
        raise CertificationError("ROR GRID identity is ambiguous or incomplete")
    identifier = normalize_external_id("ror", items[0].get("id"))
    if identifier is None:
        raise CertificationError("ROR GRID response has no valid authority ID")
    record = SourceRecord("ror", identifier[1], items[0])
    reference = EvidenceReference(
        "ror", identifier[1], record.checksum, source_snapshot_id
    )
    return RORGridCrosswalkResult(
        RORGridCrosswalkReceipt(
            grid,
            institution_reference,
            EvidenceReference(
                "ror",
                f"grid-query:{grid}",
                hashlib.sha256(response_payload).hexdigest(),
                source_snapshot_id,
            ),
            reference,
            request_uri,
            requested_at,
            received_at,
            len(response_payload),
        ),
        record,
        reference,
    )
