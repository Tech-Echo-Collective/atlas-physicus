"""One bounded launch acquisition, with no payload persistence or replay ledger.

The caller owns transport and ephemeral lifetime. A reconciled provider query
is a declared retrieval population, not an atomic or worldwide source snapshot.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from ..connectors.base import SourceRecord
from ..connectors.inspire import InspireConnector
from .contracts import CertificationError, EvidenceReference, canonical_digest
from .launch_inputs import LaunchSourceOccurrence, capture_launch_occurrence
from .launch_scope import BoundedLaunchSourcePlan
from .source_pages import (
    MAXIMUM_SOURCE_PAGE_BYTES,
    SourceRecordPageReceipt,
    capture_inspire_source_page,
)
from .years import RecordPageSourcePartitionEvidence, source_record_inventory_digest

LAUNCH_CAPTURE_VERSION = "bounded-launch-capture-v1"
MAXIMUM_LAUNCH_RECORDS = 20_000
_FIELDS = (
    "control_number,titles,preprint_date,authors,arxiv_eprints,inspire_categories,"
    "document_type,dois,publication_info"
)


@dataclass(frozen=True)
class FetchedLaunchPage:
    request_uri: str
    requested_at: datetime
    received_at: datetime
    payload: bytes

    def __post_init__(self) -> None:
        if (
            self.requested_at.tzinfo is None
            or self.received_at.tzinfo is None
            or self.received_at < self.requested_at
            or not isinstance(self.payload, bytes)
            or not 0 < len(self.payload) <= MAXIMUM_SOURCE_PAGE_BYTES
        ):
            raise CertificationError("invalid bounded source transport receipt")


@dataclass(frozen=True)
class LaunchRequestReceipt:
    request_uri: str
    requested_at: datetime
    received_at: datetime
    page_checksum: str
    provider_total: int
    page_number: int


@dataclass(frozen=True)
class CapturedLaunchYear:
    plan: BoundedLaunchSourcePlan
    occurrences: tuple[LaunchSourceOccurrence, ...]
    partition: RecordPageSourcePartitionEvidence
    requests: tuple[LaunchRequestReceipt, ...]
    manifest_digest: str


@dataclass(frozen=True)
class CompletedLaunchPage:
    """Compact completed-page checkpoint; never contains provider payloads."""

    plan: BoundedLaunchSourcePlan
    request_page_size: int
    occurrences: tuple[LaunchSourceOccurrence, ...]
    receipt: SourceRecordPageReceipt
    request: LaunchRequestReceipt
    version: str = LAUNCH_CAPTURE_VERSION

    def __post_init__(self) -> None:
        self.plan.__post_init__()
        self.receipt.__post_init__()
        query = self.plan.query_partitions[0]
        references = tuple(item.reference for item in self.occurrences)
        if (
            self.version != LAUNCH_CAPTURE_VERSION
            or isinstance(self.request_page_size, bool)
            or not 0 < self.request_page_size <= query.page_size
            or not 0 < len(references) <= self.request_page_size
            or self.receipt.provider != "inspire"
            or self.receipt.partition_id != query.id
            or self.request.page_number < 1
            or self.request.provider_total < len(references)
            or self.request.page_checksum != self.receipt.page_checksum
            or self.request.requested_at.tzinfo is None
            or self.request.received_at < self.request.requested_at
            or self.request.request_uri
            != _request_uri(self.plan, self.request_page_size, self.request.page_number)
            or tuple((ref.source_record_id, ref.checksum) for ref in references)
            != self.receipt.record_checksums
            or any(
                ref.provider != "inspire" or ref.source_snapshot_id != query.id
                for ref in references
            )
        ):
            raise CertificationError("invalid completed launch page")


def _request_uri(plan: BoundedLaunchSourcePlan, page_size: int, page: int) -> str:
    query = plan.query_partitions[0]
    return (
        query.endpoint
        + "?"
        + urlencode(
            {
                "q": query.query,
                "size": page_size,
                "page": page,
                "fields": _FIELDS,
                "sort": "mostrecent",
            }
        )
    )


def _source_total(response: FetchedLaunchPage, uri: str, budget: int) -> int:
    response.__post_init__()
    if response.request_uri != uri:
        raise CertificationError("source transport returned another query")
    total = json.loads(response.payload).get("hits", {}).get("total")
    if isinstance(total, dict):
        if total.get("relation", "eq") != "eq":
            raise CertificationError("source query total is not exact")
        total = total.get("value")
    if isinstance(total, bool) or not isinstance(total, int) or not 0 < total <= budget:
        raise CertificationError("source query exceeds the bounded launch inventory")
    return int(total)


def collect_launch_year(
    plan: BoundedLaunchSourcePlan,
    *,
    connector: InspireConnector,
    fetch: Callable[[str], FetchedLaunchPage],
    progress: Callable[[int, int], None] | None = None,
    remaining_record_budget: int = MAXIMUM_LAUNCH_RECORDS,
    process_record: Callable[[SourceRecord, EvidenceReference], None] | None = None,
    request_page_size: int = 250,
    resume_pages: tuple[CompletedLaunchPage, ...] = (),
    page_completed: Callable[[CompletedLaunchPage], None] | None = None,
    resume_fetch: Callable[[str], FetchedLaunchPage] | None = None,
) -> CapturedLaunchYear:
    """Read bounded pages, discard each raw response, retain compact inputs only."""
    plan.__post_init__()
    if (
        isinstance(remaining_record_budget, bool)
        or not 0 < remaining_record_budget <= MAXIMUM_LAUNCH_RECORDS
    ):
        raise CertificationError("invalid bounded launch record budget")
    query = plan.query_partitions[0]
    if (
        isinstance(request_page_size, bool)
        or not 0 < request_page_size <= query.page_size
    ):
        raise CertificationError("source request exceeds its fixed maximum page size")
    seen: set[str] = set()
    references: list[EvidenceReference] = []
    pages: list[SourceRecordPageReceipt] = []
    requests: list[LaunchRequestReceipt] = []
    occurrences: list[LaunchSourceOccurrence] = []
    expected_total: int | None = None
    page_number = 1
    for saved in resume_pages:
        saved.__post_init__()
        if (
            saved.plan != plan
            or saved.request_page_size != request_page_size
            or saved.request.page_number != page_number
            or (
                expected_total is not None
                and saved.request.provider_total != expected_total
            )
        ):
            raise CertificationError("incompatible or noncontiguous launch checkpoint")
        expected_total = saved.request.provider_total
        for occurrence in saved.occurrences:
            reference = occurrence.reference
            if reference.source_record_id in seen:
                raise CertificationError("checkpoint repeats a source identity")
            seen.add(reference.source_record_id)
            references.append(reference)
            occurrences.append(occurrence)
        pages.append(saved.receipt)
        requests.append(saved.request)
        page_number += 1
    if resume_pages:
        if (
            expected_total is None
            or not len(seen) <= expected_total <= remaining_record_budget
        ):
            raise CertificationError("checkpoint exceeds the bounded launch inventory")
        # Revalidate the live query before trusting an interrupted prefix, even
        # when its final page was saved before final checkpoint publication.
        uri = _request_uri(plan, request_page_size, 1)
        probe = (resume_fetch or fetch)(uri)
        if _source_total(probe, uri, remaining_record_budget) != expected_total:
            raise CertificationError("source query changed since launch checkpoint")
        probe_receipt, probe_records = capture_inspire_source_page(
            probe.payload, connector=connector, partition_id=query.id
        )
        if tuple(item[0] for item in probe_receipt.record_checksums) != tuple(
            item[0] for item in pages[0].record_checksums
        ):
            raise CertificationError("source page ordering changed since checkpoint")
        del probe, probe_receipt, probe_records
    while expected_total is None or len(seen) < expected_total:
        uri = _request_uri(plan, request_page_size, page_number)
        response = fetch(uri)
        total = _source_total(response, uri, remaining_record_budget)
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise CertificationError("source query changed during bounded retrieval")
        receipt, records = capture_inspire_source_page(
            response.payload,
            connector=connector,
            partition_id=query.id,
        )
        if not records or len(records) > request_page_size:
            raise CertificationError("source page is empty, truncated or oversized")
        for record in records:
            if record.source_record_id in seen:
                raise CertificationError("source retrieval repeats an identity")
            seen.add(record.source_record_id)
            reference = EvidenceReference(
                "inspire", record.source_record_id, record.checksum, query.id
            )
            occurrence = capture_launch_occurrence(
                record,
                reference=reference,
                connector=connector,
                dataset_version=plan.dataset_version,
            )
            if process_record is not None:
                process_record(record, reference)
                if record.checksum != reference.checksum:
                    raise CertificationError(
                        "source processing changed its input payload"
                    )
            references.append(reference)
            occurrences.append(occurrence)
        if len(seen) > expected_total:
            raise CertificationError("source records exceed the declared total")
        pages.append(receipt)
        requests.append(
            LaunchRequestReceipt(
                uri,
                response.requested_at,
                response.received_at,
                receipt.page_checksum,
                total,
                page_number,
            )
        )
        # Do not retain provider pages/records in the source collection.
        completed = CompletedLaunchPage(
            plan,
            request_page_size,
            tuple(occurrences[-len(records) :]),
            receipt,
            requests[-1],
        )
        del response, records, record
        if page_completed is not None:
            page_completed(completed)
        if progress is not None:
            progress(len(seen), expected_total)
        page_number += 1
    if expected_total is None:
        raise CertificationError("bounded source query has no exact total")
    partition = RecordPageSourcePartitionEvidence(
        partition_id=query.id,
        provider="inspire",
        expected_unique_records=expected_total,
        observed_records=len(seen),
        observed_unique_records=len(seen),
        duplicate_records=0,
        truncated=False,
        page_checksums=tuple(page.page_checksum for page in pages),
        record_inventory_digest=source_record_inventory_digest(tuple(references)),
        complete=True,
        pages=tuple(pages),
    )
    if not partition.reconciles:
        raise CertificationError("bounded source inventory did not reconcile")
    manifest_digest = canonical_digest(
        (LAUNCH_CAPTURE_VERSION, plan, partition, tuple(requests))
    )
    return CapturedLaunchYear(
        plan, tuple(occurrences), partition, tuple(requests), manifest_digest
    )
