"""Staging-only paired historical evidence capture.

This deliberately narrow acquisition path preserves raw INSPIRE and arXiv
responses for one fixed, closed week in hep-th and Condensed Matter.  It has no
production scope registration, database imports, cursor writes, replay,
certification, metric calculation, or public activation behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import parse_qsl, urlparse

from defusedxml import ElementTree as ET

from .capture_lineage import (
    CapturedTextResponse,
    CaptureTextTransport,
    HttpCaptureLineage,
    LineageProviderHttpTransport,
)
from .config import Settings, get_settings
from .connectors.acquisition import AcquisitionScope
from .connectors.arxiv import ArxivConnector
from .connectors.base import ConnectorError, SourceTransport
from .connectors.inspire import InspireConnector

CaptureProvider = Literal["inspire", "arxiv"]

PAIR_ID = "physics-paired-certification-2020w03-v1"
MANIFEST_VERSION = "physics-paired-raw-capture-manifest-v2"
INTERNAL_LIVE_TRANSPORT_ATTESTATION = "internal-lineage-http-transport"
INJECTED_TRANSPORT_ATTESTATION = "injected-transport"
WINDOW_START = datetime(2020, 1, 13, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2020, 1, 19, 23, 59, tzinfo=UTC)
OFFICIAL_INSPIRE_ENDPOINT = "https://inspirehep.net/api/literature"
OFFICIAL_ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
OPEN_SEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"


class PairedCaptureSafetyError(ValueError):
    """Raised before unsafe evidence acquisition or filesystem mutation."""


class PairedCaptureVerificationError(ValueError):
    """Raised when preserved evidence no longer matches its manifest."""


@dataclass(frozen=True)
class TrialScope:
    id: str
    atlas_field_id: str
    inspire_filter: str
    arxiv_filter: str

    @property
    def parser_scope(self) -> AcquisitionScope:
        # This local object is intentionally never inserted into the production
        # SUPPORTED_ACQUISITION_SCOPES registry.
        return AcquisitionScope(
            id=self.id,
            inspire_query=self.inspire_filter,
            arxiv_query=self.arxiv_filter,
        )


HEP_TH_TRIAL_SCOPE = TrialScope(
    id="hep-th-paired-certification-2020w03-v1",
    atlas_field_id="hep-th",
    inspire_filter="subject:Theory-HEP",
    arxiv_filter="cat:hep-th",
)
COND_MAT_TRIAL_SCOPE = TrialScope(
    id="cond-mat-paired-certification-2020w03-v1",
    atlas_field_id="cond-mat",
    inspire_filter='subject:"Condensed Matter"',
    arxiv_filter="cat:cond-mat.*",
)
TRIAL_SCOPES = (HEP_TH_TRIAL_SCOPE, COND_MAT_TRIAL_SCOPE)
TRIAL_SCOPE_BY_ID = {item.id: item for item in TRIAL_SCOPES}


@dataclass(frozen=True)
class ProviderCaptureCaps:
    page_size: int
    maximum_pages: int
    maximum_total_exclusive: int

    def as_dict(self) -> dict[str, int]:
        return {
            "page_size": self.page_size,
            "maximum_pages": self.maximum_pages,
            "maximum_total_exclusive": self.maximum_total_exclusive,
        }


PROVIDER_CAPS: Mapping[CaptureProvider, ProviderCaptureCaps] = {
    "inspire": ProviderCaptureCaps(
        page_size=250,
        maximum_pages=1,
        maximum_total_exclusive=251,
    ),
    "arxiv": ProviderCaptureCaps(
        page_size=100,
        maximum_pages=10,
        maximum_total_exclusive=1_000,
    ),
}


@dataclass(frozen=True)
class DownstreamTargetCaps:
    paper_lookups_per_scope: int = 400
    institution_recids_per_scope: int = 250
    child_ror_records_per_scope: int = 250
    parent_ror_records_per_scope: int = 250

    def as_dict(self) -> dict[str, int]:
        return {
            "paper_lookups_per_scope": self.paper_lookups_per_scope,
            "institution_recids_per_scope": self.institution_recids_per_scope,
            "child_ror_records_per_scope": self.child_ror_records_per_scope,
            "parent_ror_records_per_scope": self.parent_ror_records_per_scope,
        }

    def validate(
        self,
        *,
        paper_lookups: int,
        institution_recids: int,
        child_ror_records: int,
        parent_ror_records: int,
    ) -> None:
        observed = {
            "paper lookups": (paper_lookups, self.paper_lookups_per_scope),
            "institution recids": (
                institution_recids,
                self.institution_recids_per_scope,
            ),
            "child ROR records": (
                child_ror_records,
                self.child_ror_records_per_scope,
            ),
            "parent ROR records": (
                parent_ror_records,
                self.parent_ror_records_per_scope,
            ),
        }
        for label, (count, limit) in observed.items():
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise PairedCaptureSafetyError(f"{label} count is invalid")
            if count > limit:
                raise PairedCaptureSafetyError(
                    f"{label} exceed the staging-only cap {limit}; shrink the "
                    "trial rather than truncating evidence"
                )


DOWNSTREAM_TARGET_CAPS = DownstreamTargetCaps()


def build_inspire_query(scope: TrialScope) -> str:
    _validate_known_scope(scope)
    return (
        f"document_type:article and {scope.inspire_filter} and "
        "de >= 2020-01-13 and de <= 2020-01-19"
    )


def build_arxiv_query(scope: TrialScope) -> str:
    _validate_known_scope(scope)
    return f"({scope.arxiv_filter}) AND submittedDate:[202001130000 TO 202001192359]"


def _validate_known_scope(scope: TrialScope) -> None:
    if TRIAL_SCOPE_BY_ID.get(scope.id) != scope:
        raise PairedCaptureSafetyError("capture scope is not in the fixed paired trial")


@dataclass(frozen=True)
class TrialPartition:
    scope_id: str
    atlas_field_id: str
    provider: CaptureProvider
    query: str
    endpoint: str
    caps: ProviderCaptureCaps
    query_version: str

    @property
    def id(self) -> str:
        return f"{self.scope_id}:{self.provider}"

    @property
    def query_checksum(self) -> str:
        return hashlib.sha256(self.query.encode("utf-8")).hexdigest()


def build_trial_partitions(
    *,
    inspire_endpoint: str = OFFICIAL_INSPIRE_ENDPOINT,
    arxiv_endpoint: str = OFFICIAL_ARXIV_ENDPOINT,
) -> tuple[TrialPartition, ...]:
    partitions: list[TrialPartition] = []
    for scope in TRIAL_SCOPES:
        partitions.extend(
            (
                TrialPartition(
                    scope_id=scope.id,
                    atlas_field_id=scope.atlas_field_id,
                    provider="inspire",
                    query=build_inspire_query(scope),
                    endpoint=inspire_endpoint,
                    caps=PROVIDER_CAPS["inspire"],
                    query_version=f"{scope.id}:inspire:earliest-record-date-v1",
                ),
                TrialPartition(
                    scope_id=scope.id,
                    atlas_field_id=scope.atlas_field_id,
                    provider="arxiv",
                    query=build_arxiv_query(scope),
                    endpoint=arxiv_endpoint,
                    caps=PROVIDER_CAPS["arxiv"],
                    query_version=f"{scope.id}:arxiv:submission-window-v1",
                ),
            )
        )
    return tuple(partitions)


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme != "https" or not host:
        raise PairedCaptureSafetyError("capture endpoints must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise PairedCaptureSafetyError("capture endpoints must not contain user info")
    try:
        port = parsed.port
    except ValueError as error:
        raise PairedCaptureSafetyError(
            "capture endpoint has an invalid port"
        ) from error
    return parsed.scheme, host, port or 443


def _lineage_url_matches_request(
    url: str,
    endpoint: str,
    params: Mapping[str, object],
) -> bool:
    """Compare exact endpoint path and decoded query, independent of ordering."""

    parsed = urlparse(url)
    expected = urlparse(endpoint)
    if (
        _origin(url) != _origin(endpoint)
        or parsed.path != expected.path
        or parsed.params
        or parsed.fragment
        or expected.query
    ):
        return False
    observed_query = sorted(parse_qsl(parsed.query, keep_blank_values=True))
    expected_query = sorted((key, str(value)) for key, value in params.items())
    return observed_query == expected_query


def _expected_page_request(
    partition: TrialPartition,
    *,
    page_number: int,
    prior_record_count: int,
) -> dict[str, object]:
    if partition.provider == "inspire":
        if page_number != 1 or prior_record_count != 0:
            raise PairedCaptureVerificationError(
                "INSPIRE paired capture may contain only its fixed first page"
            )
        return {
            "q": partition.query,
            "sort": "mostrecent",
            "size": partition.caps.page_size,
        }
    return {
        "search_query": partition.query,
        "start": prior_record_count,
        "max_results": partition.caps.page_size,
        "sortBy": "submittedDate",
        "sortOrder": "ascending",
    }


def _validate_partitions(partitions: Sequence[TrialPartition]) -> None:
    if len(partitions) != 4:
        raise PairedCaptureSafetyError(
            "paired capture requires exactly two providers for both trial scopes"
        )
    endpoints: dict[CaptureProvider, set[str]] = {"inspire": set(), "arxiv": set()}
    for partition in partitions:
        endpoints[partition.provider].add(partition.endpoint)
        _origin(partition.endpoint)
    if any(len(values) != 1 for values in endpoints.values()):
        raise PairedCaptureSafetyError("provider endpoints differ across paired scopes")
    expected = build_trial_partitions(
        inspire_endpoint=next(iter(endpoints["inspire"])),
        arxiv_endpoint=next(iter(endpoints["arxiv"])),
    )
    if tuple(partitions) != expected:
        raise PairedCaptureSafetyError(
            "partitions do not match the fixed paired capture plan"
        )


@dataclass(frozen=True)
class CapturedPage:
    page_number: int
    record_count: int | None
    checksum: str
    path: str
    lineage: HttpCaptureLineage

    def as_dict(self) -> dict[str, object]:
        return {
            "page_number": self.page_number,
            "record_count": self.record_count,
            "checksum": self.checksum,
            "path": self.path,
            "http_lineage": self.lineage.as_dict(),
        }


@dataclass(frozen=True)
class CapturePartitionResult:
    partition: TrialPartition
    expected_total: int | None = None
    records_seen: int = 0
    unique_records_seen: int = 0
    unique_ids_checksum: str | None = None
    duplicate_count: int = 0
    complete: bool = False
    terminal_status: str = "not-executed"
    pages: tuple[CapturedPage, ...] = field(default_factory=tuple)
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        body: dict[str, object] = {
            "partition_id": self.partition.id,
            "scope_id": self.partition.scope_id,
            "atlas_field_id": self.partition.atlas_field_id,
            "provider": self.partition.provider,
            "window_start_utc": WINDOW_START.isoformat(),
            "window_end_utc": WINDOW_END.isoformat(),
            "query": self.partition.query,
            "query_version": self.partition.query_version,
            "query_checksum": self.partition.query_checksum,
            "endpoint": self.partition.endpoint,
            "caps": self.partition.caps.as_dict(),
            "expected_total": self.expected_total,
            "records_seen": self.records_seen,
            "unique_records_seen": self.unique_records_seen,
            "unique_ids_checksum": self.unique_ids_checksum,
            "duplicate_count": self.duplicate_count,
            "page_count": len(self.pages),
            "complete": self.complete,
            "terminal_status": self.terminal_status,
            "pages": [item.as_dict() for item in self.pages],
            "error": self.error,
        }
        body["partition_checksum"] = _json_checksum(body)
        return body


@dataclass(frozen=True)
class PairedCaptureManifest:
    partitions: tuple[CapturePartitionResult, ...]
    completed_at: datetime
    transport_attestation: str

    @property
    def complete(self) -> bool:
        return len(self.partitions) == 4 and all(
            item.complete for item in self.partitions
        )

    def as_dict(self) -> dict[str, object]:
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise PairedCaptureSafetyError("manifest completion time must be aware")
        partition_documents = [item.as_dict() for item in self.partitions]
        partition_checksums = [
            str(item["partition_checksum"]) for item in partition_documents
        ]
        body: dict[str, object] = {
            "manifest_version": MANIFEST_VERSION,
            "pair_id": PAIR_ID,
            "completed_at": self.completed_at.astimezone(UTC).isoformat(),
            "window_start_utc": WINDOW_START.isoformat(),
            "window_end_utc": WINDOW_END.isoformat(),
            "window_end_precision": "minute-inclusive",
            "scope_ids": [item.id for item in TRIAL_SCOPES],
            "providers": ["inspire", "arxiv"],
            "staging_only": True,
            "production_scope_registration": False,
            "database_access": False,
            "database_writes": False,
            "public_metric_activation": False,
            "transport_attestation": self.transport_attestation,
            "provider_endpoints_official": all(
                self.transport_attestation == INTERNAL_LIVE_TRANSPORT_ATTESTATION
                and item.partition.endpoint
                == (
                    OFFICIAL_INSPIRE_ENDPOINT
                    if item.partition.provider == "inspire"
                    else OFFICIAL_ARXIV_ENDPOINT
                )
                for item in self.partitions
            ),
            "downstream_target_caps": DOWNSTREAM_TARGET_CAPS.as_dict(),
            "capture_complete": self.complete,
            "partition_checksums": partition_checksums,
            "evidence_set_checksum": _json_checksum(partition_checksums),
            "partitions": partition_documents,
        }
        body["manifest_checksum"] = _json_checksum(body)
        return body


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _json_checksum(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _ids_checksum(identifiers: set[str]) -> str:
    return hashlib.sha256("\n".join(sorted(identifiers)).encode()).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_staging_output(
    output: Path,
    *,
    repo_root: Path | None = None,
) -> Path:
    resolved = output.expanduser().resolve()
    repository = (repo_root or repository_root()).resolve()
    if resolved == Path(resolved.anchor):
        raise PairedCaptureSafetyError("filesystem root is not a capture directory")
    if _is_within(resolved, repository):
        raise PairedCaptureSafetyError(
            "paired evidence must be stored outside the source repository"
        )
    return resolved


def _page_path(partition: TrialPartition, checksum: str) -> Path:
    suffix = ".json" if partition.provider == "inspire" else ".xml"
    return (
        Path("pages")
        / partition.scope_id
        / partition.provider
        / (f"{checksum}{suffix}")
    )


def _store_page(
    output: Path,
    partition: TrialPartition,
    *,
    page_number: int,
    response: CapturedTextResponse,
) -> CapturedPage:
    payload = response.body.encode("utf-8")
    checksum = hashlib.sha256(payload).hexdigest()
    relative = _page_path(partition, checksum)
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as error:
        if destination.read_bytes() != payload:
            raise PairedCaptureVerificationError(
                "content-addressed page contains different bytes"
            ) from error
    return CapturedPage(
        page_number=page_number,
        record_count=None,
        checksum=checksum,
        path=relative.as_posix(),
        lineage=response.lineage,
    )


def _exact_inspire_total(payload: Mapping[str, Any]) -> int:
    hits = payload.get("hits")
    if not isinstance(hits, Mapping):
        raise ConnectorError("INSPIRE response is missing its hits envelope")
    raw_total = hits.get("total")
    if isinstance(raw_total, bool):
        raise ConnectorError("INSPIRE returned an invalid total")
    if isinstance(raw_total, int):
        total = raw_total
    elif isinstance(raw_total, Mapping):
        value = raw_total.get("value")
        exact = raw_total.get("relation") == "eq"
        if not exact or isinstance(value, bool) or not isinstance(value, int):
            raise ConnectorError("INSPIRE did not return an exact result total")
        total = value
    else:
        raise ConnectorError("INSPIRE response omitted its result total")
    if total < 0:
        raise ConnectorError("INSPIRE returned a negative result total")
    return total


def _parse_inspire(
    body: str,
    partition: TrialPartition,
) -> tuple[dict[str, Any], int, list[str]]:
    try:
        value = json.loads(body)
    except json.JSONDecodeError as error:
        raise ConnectorError("INSPIRE returned malformed JSON") from error
    if not isinstance(value, dict):
        raise ConnectorError("INSPIRE returned a non-object JSON envelope")
    total = _exact_inspire_total(value)
    scope = TRIAL_SCOPE_BY_ID[partition.scope_id]
    parser = InspireConnector(
        # Parsing is deliberately offline.  The connector stores its transport,
        # but ``_records`` never invokes it.
        cast(SourceTransport, None),
        partition.endpoint.removesuffix("/literature"),
        acquisition_scope=scope.parser_scope,
    )
    records = parser._records(value)
    return value, total, [item.source_record_id for item in records]


def _parse_arxiv(
    body: str,
    partition: TrialPartition,
) -> tuple[int, list[str]]:
    try:
        root = ET.fromstring(body)
    except Exception as error:
        raise ConnectorError("arXiv returned malformed XML") from error
    total_element = root.find(f"{OPEN_SEARCH}totalResults")
    try:
        total = (
            int((total_element.text or "").strip()) if total_element is not None else -1
        )
    except ValueError as error:
        raise ConnectorError("arXiv returned an invalid total") from error
    if total < 0:
        raise ConnectorError("arXiv response omitted its result total")
    scope = TRIAL_SCOPE_BY_ID[partition.scope_id]
    parser = ArxivConnector(
        # Parsing is deliberately offline.  The connector stores its transport,
        # but ``_records`` never invokes it.
        cast(SourceTransport, None),
        partition.endpoint,
        acquisition_scope=scope.parser_scope,
    )
    records = parser._records(body)
    return total, [item.source_record_id for item in records]


def _failure(
    partition: TrialPartition,
    *,
    status: str,
    pages: Sequence[CapturedPage] = (),
    expected_total: int | None = None,
    records_seen: int = 0,
    identifiers: set[str] | None = None,
    error: str,
) -> CapturePartitionResult:
    unique = identifiers or set()
    return CapturePartitionResult(
        partition=partition,
        expected_total=expected_total,
        records_seen=records_seen,
        unique_records_seen=len(unique),
        unique_ids_checksum=_ids_checksum(unique),
        duplicate_count=records_seen - len(unique),
        complete=False,
        terminal_status=status,
        pages=tuple(pages),
        error=error[:1000],
    )


class PairedRawAcquirer:
    """Preserve four fixed raw partitions without touching canonical storage."""

    def __init__(
        self,
        transports: Mapping[CaptureProvider, CaptureTextTransport],
        partitions: Sequence[TrialPartition],
        *,
        output: Path,
    ):
        self.partitions = tuple(partitions)
        _validate_partitions(self.partitions)
        if set(transports) != {"inspire", "arxiv"}:
            raise PairedCaptureSafetyError(
                "paired capture requires exactly INSPIRE and arXiv transports"
            )
        self.transports = transports
        self.output = output

    def acquire(self) -> tuple[CapturePartitionResult, ...]:
        results: list[CapturePartitionResult] = []
        failed = False
        for partition in self.partitions:
            if failed:
                results.append(CapturePartitionResult(partition=partition))
                continue
            try:
                result = (
                    self._acquire_inspire(partition)
                    if partition.provider == "inspire"
                    else self._acquire_arxiv(partition)
                )
            except Exception as error:
                result = _failure(
                    partition,
                    status="request-or-storage-failed",
                    error=f"{type(error).__name__}: {error}",
                )
            results.append(result)
            failed = not result.complete
        return tuple(results)

    def _captured_page(
        self,
        partition: TrialPartition,
        *,
        page_number: int,
        params: dict[str, Any],
    ) -> tuple[CapturedTextResponse, CapturedPage]:
        response = self.transports[partition.provider].get_captured_text(
            partition.endpoint,
            params=params,
        )
        expected_origin = _origin(partition.endpoint)
        if (
            _origin(response.lineage.request_url) != expected_origin
            or _origin(response.lineage.response_url) != expected_origin
        ):
            raise PairedCaptureSafetyError(
                "provider request or response crossed the partition origin"
            )
        return response, _store_page(
            self.output,
            partition,
            page_number=page_number,
            response=response,
        )

    def _acquire_inspire(self, partition: TrialPartition) -> CapturePartitionResult:
        assert partition.provider == "inspire"
        response, stored = self._captured_page(
            partition,
            page_number=1,
            params={
                "q": partition.query,
                "sort": "mostrecent",
                "size": partition.caps.page_size,
            },
        )
        try:
            payload, total, page_ids = _parse_inspire(
                response.body,
                partition,
            )
        except Exception as error:
            return _failure(
                partition,
                status="invalid-provider-envelope",
                pages=(stored,),
                error=f"{type(error).__name__}: {error}",
            )
        stored = replace(stored, record_count=len(page_ids))
        identifiers = set(page_ids)
        if len(page_ids) > partition.caps.page_size:
            return _failure(
                partition,
                status="page-size-cap-exceeded",
                pages=(stored,),
                expected_total=total,
                records_seen=len(page_ids),
                identifiers=identifiers,
                error="INSPIRE returned more rows than the requested page cap",
            )
        if total >= partition.caps.maximum_total_exclusive:
            return _failure(
                partition,
                status="total-cap-exceeded",
                pages=(stored,),
                expected_total=total,
                records_seen=len(page_ids),
                identifiers=identifiers,
                error=(
                    f"INSPIRE total {total} exceeds the complete one-page cap "
                    f"{partition.caps.maximum_total_exclusive - 1}"
                ),
            )
        raw_links = payload.get("links")
        if not isinstance(raw_links, Mapping):
            return _failure(
                partition,
                status="invalid-pagination-envelope",
                pages=(stored,),
                expected_total=total,
                records_seen=len(page_ids),
                identifiers=identifiers,
                error="INSPIRE response omitted its pagination links",
            )
        if raw_links.get("next"):
            return _failure(
                partition,
                status="unexpected-pagination",
                pages=(stored,),
                expected_total=total,
                records_seen=len(page_ids),
                identifiers=identifiers,
                error="INSPIRE returned a next page inside a one-page trial",
            )
        duplicates = len(page_ids) - len(identifiers)
        complete = len(identifiers) == total and duplicates == 0
        return CapturePartitionResult(
            partition=partition,
            expected_total=total,
            records_seen=len(page_ids),
            unique_records_seen=len(identifiers),
            unique_ids_checksum=_ids_checksum(identifiers),
            duplicate_count=duplicates,
            complete=complete,
            terminal_status="complete" if complete else "count-mismatch",
            pages=(stored,),
            error=None if complete else "INSPIRE page did not match its exact total",
        )

    def _acquire_arxiv(self, partition: TrialPartition) -> CapturePartitionResult:
        assert partition.provider == "arxiv"
        pages: list[CapturedPage] = []
        identifiers: set[str] = set()
        records_seen = 0
        expected_total: int | None = None
        for page_number in range(1, partition.caps.maximum_pages + 1):
            response, stored = self._captured_page(
                partition,
                page_number=page_number,
                params={
                    "search_query": partition.query,
                    "start": records_seen,
                    "max_results": partition.caps.page_size,
                    "sortBy": "submittedDate",
                    "sortOrder": "ascending",
                },
            )
            try:
                total, page_ids = _parse_arxiv(
                    response.body,
                    partition,
                )
            except Exception as error:
                pages.append(stored)
                return _failure(
                    partition,
                    status="invalid-provider-envelope",
                    pages=pages,
                    expected_total=expected_total,
                    records_seen=records_seen,
                    identifiers=identifiers,
                    error=f"{type(error).__name__}: {error}",
                )
            stored = replace(stored, record_count=len(page_ids))
            pages.append(stored)
            if len(page_ids) > partition.caps.page_size:
                return _failure(
                    partition,
                    status="page-size-cap-exceeded",
                    pages=pages,
                    expected_total=total,
                    records_seen=records_seen + len(page_ids),
                    identifiers=identifiers | set(page_ids),
                    error="arXiv returned more rows than the requested page cap",
                )
            if total >= partition.caps.maximum_total_exclusive:
                return _failure(
                    partition,
                    status="total-cap-exceeded",
                    pages=pages,
                    expected_total=total,
                    records_seen=records_seen + len(page_ids),
                    identifiers=identifiers | set(page_ids),
                    error=(
                        f"arXiv total {total} exceeds the staging cap "
                        f"{partition.caps.maximum_total_exclusive - 1}"
                    ),
                )
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                return _failure(
                    partition,
                    status="changing-provider-total",
                    pages=pages,
                    expected_total=expected_total,
                    records_seen=records_seen + len(page_ids),
                    identifiers=identifiers | set(page_ids),
                    error="arXiv total changed during the closed capture",
                )
            records_seen += len(page_ids)
            identifiers.update(page_ids)
            if records_seen == total:
                duplicates = records_seen - len(identifiers)
                complete = duplicates == 0
                return CapturePartitionResult(
                    partition=partition,
                    expected_total=total,
                    records_seen=records_seen,
                    unique_records_seen=len(identifiers),
                    unique_ids_checksum=_ids_checksum(identifiers),
                    duplicate_count=duplicates,
                    complete=complete,
                    terminal_status="complete" if complete else "duplicate-records",
                    pages=tuple(pages),
                    error=None if complete else "arXiv pages contain duplicate IDs",
                )
            if not page_ids or records_seen > total:
                return _failure(
                    partition,
                    status="incomplete-page-stream",
                    pages=pages,
                    expected_total=total,
                    records_seen=records_seen,
                    identifiers=identifiers,
                    error="arXiv pages did not advance to the exact total",
                )
        return _failure(
            partition,
            status="page-cap-exceeded",
            pages=pages,
            expected_total=expected_total,
            records_seen=records_seen,
            identifiers=identifiers,
            error="arXiv capture exceeded ten pages; shrink the trial",
        )


def capture_plan() -> dict[str, object]:
    partitions = build_trial_partitions()
    return {
        "pair_id": PAIR_ID,
        "manifest_version": MANIFEST_VERSION,
        "executed": False,
        "staging_only": True,
        "database_access": False,
        "database_writes": False,
        "production_scope_registration": False,
        "public_metric_activation": False,
        "provider_endpoints_official": True,
        "window_start_utc": WINDOW_START.isoformat(),
        "window_end_utc": WINDOW_END.isoformat(),
        "downstream_target_caps": DOWNSTREAM_TARGET_CAPS.as_dict(),
        "partitions": [
            {
                "partition_id": item.id,
                "scope_id": item.scope_id,
                "atlas_field_id": item.atlas_field_id,
                "provider": item.provider,
                "query": item.query,
                "query_version": item.query_version,
                "query_checksum": item.query_checksum,
                "endpoint": item.endpoint,
                "caps": item.caps.as_dict(),
            }
            for item in partitions
        ],
    }


def _write_manifest(output: Path, manifest: PairedCaptureManifest) -> Path:
    value = manifest.as_dict()
    checksum = str(value["manifest_checksum"])
    destination = output / "manifests" / f"{checksum}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    try:
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    except FileExistsError as error:
        if destination.read_text(encoding="utf-8") != rendered:
            raise PairedCaptureVerificationError(
                "content-addressed manifest contains different content"
            ) from error
    return destination


def _live_transport(
    settings: Settings,
    endpoint: str,
    *,
    interval: float,
) -> LineageProviderHttpTransport:
    _, host, _ = _origin(endpoint)
    return LineageProviderHttpTransport(
        timeout_seconds=settings.provider_timeout_seconds,
        minimum_intervals={host: interval},
        allowed_hosts={host},
    )


def execute_paired_capture(
    *,
    output: Path,
    partitions: Sequence[TrialPartition] | None = None,
    transports: Mapping[CaptureProvider, CaptureTextTransport] | None = None,
    settings: Settings | None = None,
    completed_at: datetime | None = None,
    repo_root: Path | None = None,
) -> tuple[PairedCaptureManifest, Path]:
    active_partitions = tuple(partitions or build_trial_partitions())
    _validate_partitions(active_partitions)
    resolved_output = validate_staging_output(output, repo_root=repo_root)
    if transports is not None:
        transport_attestation = INJECTED_TRANSPORT_ATTESTATION
        results = PairedRawAcquirer(
            transports,
            active_partitions,
            output=resolved_output,
        ).acquire()
    else:
        transport_attestation = INTERNAL_LIVE_TRANSPORT_ATTESTATION
        if active_partitions != build_trial_partitions():
            raise PairedCaptureSafetyError(
                "live capture is restricted to official provider endpoints"
            )
        active_settings = settings or get_settings()
        with ExitStack() as stack:
            live_transports: dict[CaptureProvider, CaptureTextTransport] = {
                "inspire": stack.enter_context(
                    _live_transport(
                        active_settings, OFFICIAL_INSPIRE_ENDPOINT, interval=1
                    )
                ),
                "arxiv": stack.enter_context(
                    _live_transport(
                        active_settings, OFFICIAL_ARXIV_ENDPOINT, interval=3
                    )
                ),
            }
            results = PairedRawAcquirer(
                live_transports,
                active_partitions,
                output=resolved_output,
            ).acquire()
    manifest = PairedCaptureManifest(
        partitions=results,
        completed_at=completed_at or datetime.now(UTC),
        transport_attestation=transport_attestation,
    )
    return manifest, _write_manifest(resolved_output, manifest)


@dataclass(frozen=True)
class _VerifiedPageContent:
    total: int
    record_ids: tuple[str, ...]
    inspire_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class _RecomputedPartition:
    expected_total: int
    records_seen: int
    unique_records_seen: int
    unique_ids_checksum: str
    duplicate_count: int
    complete: bool
    terminal_status: str


def _parse_verified_page(
    body: bytes,
    partition: TrialPartition,
) -> _VerifiedPageContent:
    try:
        decoded = body.decode("utf-8")
        if partition.provider == "inspire":
            payload, total, identifiers = _parse_inspire(decoded, partition)
            return _VerifiedPageContent(
                total=total,
                record_ids=tuple(identifiers),
                inspire_payload=payload,
            )
        total, identifiers = _parse_arxiv(decoded, partition)
        return _VerifiedPageContent(total=total, record_ids=tuple(identifiers))
    except (UnicodeDecodeError, ConnectorError, ET.ParseError) as error:
        raise PairedCaptureVerificationError(
            f"preserved {partition.provider} page cannot be reparsed"
        ) from error


def _recompute_inspire_partition(
    partition: TrialPartition,
    pages: Sequence[_VerifiedPageContent],
) -> _RecomputedPartition:
    if len(pages) != 1:
        raise PairedCaptureVerificationError(
            "INSPIRE partition must retain exactly one parsed page"
        )
    page = pages[0]
    identifiers = set(page.record_ids)
    records_seen = len(page.record_ids)
    duplicates = records_seen - len(identifiers)
    payload = page.inspire_payload
    if payload is None:
        raise PairedCaptureVerificationError("INSPIRE page payload is unavailable")

    if records_seen > partition.caps.page_size:
        status = "page-size-cap-exceeded"
        complete = False
    elif page.total >= partition.caps.maximum_total_exclusive:
        status = "total-cap-exceeded"
        complete = False
    else:
        links = payload.get("links")
        if not isinstance(links, Mapping):
            status = "invalid-pagination-envelope"
            complete = False
        elif links.get("next"):
            status = "unexpected-pagination"
            complete = False
        else:
            complete = len(identifiers) == page.total and duplicates == 0
            status = "complete" if complete else "count-mismatch"

    return _RecomputedPartition(
        expected_total=page.total,
        records_seen=records_seen,
        unique_records_seen=len(identifiers),
        unique_ids_checksum=_ids_checksum(identifiers),
        duplicate_count=duplicates,
        complete=complete,
        terminal_status=status,
    )


def _recompute_arxiv_partition(
    partition: TrialPartition,
    pages: Sequence[_VerifiedPageContent],
) -> _RecomputedPartition:
    if not pages or len(pages) > partition.caps.maximum_pages:
        raise PairedCaptureVerificationError("arXiv page set exceeds its capture plan")

    expected_total: int | None = None
    records_seen = 0
    identifiers: set[str] = set()
    terminal_status: str | None = None
    complete = False
    terminal_page = 0

    for page_number, page in enumerate(pages, start=1):
        page_records = len(page.record_ids)
        combined = identifiers | set(page.record_ids)
        combined_seen = records_seen + page_records
        if page_records > partition.caps.page_size:
            expected_total = page.total
            records_seen = combined_seen
            identifiers = combined
            terminal_status = "page-size-cap-exceeded"
            terminal_page = page_number
            break
        if page.total >= partition.caps.maximum_total_exclusive:
            expected_total = page.total
            records_seen = combined_seen
            identifiers = combined
            terminal_status = "total-cap-exceeded"
            terminal_page = page_number
            break
        if expected_total is None:
            expected_total = page.total
        elif page.total != expected_total:
            records_seen = combined_seen
            identifiers = combined
            terminal_status = "changing-provider-total"
            terminal_page = page_number
            break

        records_seen = combined_seen
        identifiers = combined
        if records_seen == expected_total:
            duplicates = records_seen - len(identifiers)
            complete = duplicates == 0
            terminal_status = "complete" if complete else "duplicate-records"
            terminal_page = page_number
            break
        if not page.record_ids or records_seen > expected_total:
            terminal_status = "incomplete-page-stream"
            terminal_page = page_number
            break

    if expected_total is None:
        raise PairedCaptureVerificationError("arXiv partition omitted a result total")
    if terminal_status is None:
        if len(pages) != partition.caps.maximum_pages:
            raise PairedCaptureVerificationError(
                "arXiv partition stops before a terminal capture condition"
            )
        terminal_status = "page-cap-exceeded"
        terminal_page = len(pages)
    if terminal_page != len(pages):
        raise PairedCaptureVerificationError(
            "partition retains pages after its terminal capture condition"
        )

    duplicates = records_seen - len(identifiers)
    return _RecomputedPartition(
        expected_total=expected_total,
        records_seen=records_seen,
        unique_records_seen=len(identifiers),
        unique_ids_checksum=_ids_checksum(identifiers),
        duplicate_count=duplicates,
        complete=complete,
        terminal_status=terminal_status,
    )


def _verify_partition_summary(
    raw_partition: Mapping[str, object],
    recomputed: _RecomputedPartition,
) -> None:
    expected: dict[str, object] = {
        "expected_total": recomputed.expected_total,
        "records_seen": recomputed.records_seen,
        "unique_records_seen": recomputed.unique_records_seen,
        "unique_ids_checksum": recomputed.unique_ids_checksum,
        "duplicate_count": recomputed.duplicate_count,
        "complete": recomputed.complete,
        "terminal_status": recomputed.terminal_status,
    }
    for key, value in expected.items():
        actual = raw_partition.get(key)
        if type(actual) is not type(value) or actual != value:
            raise PairedCaptureVerificationError(
                f"partition {key} differs from reparsed provider evidence"
            )
    error = raw_partition.get("error")
    if recomputed.complete:
        if error is not None:
            raise PairedCaptureVerificationError(
                "complete partition unexpectedly retains an error"
            )
    elif not isinstance(error, str) or not error.strip():
        raise PairedCaptureVerificationError(
            "incomplete partition lacks an explicit terminal error"
        )


def verify_paired_capture_manifest(path: Path, *, output: Path) -> dict[str, Any]:
    resolved_output = output.resolve()
    resolved_path = path.resolve()
    if not _is_within(resolved_path, resolved_output / "manifests"):
        raise PairedCaptureVerificationError(
            "manifest is outside the active evidence directory"
        )
    try:
        value = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PairedCaptureVerificationError("manifest cannot be read") from error
    if not isinstance(value, dict):
        raise PairedCaptureVerificationError("manifest is not a JSON object")
    checksum = value.get("manifest_checksum")
    unsigned = dict(value)
    unsigned.pop("manifest_checksum", None)
    if (
        not _is_sha256(checksum)
        or checksum != _json_checksum(unsigned)
        or resolved_path.name != f"{checksum}.json"
    ):
        raise PairedCaptureVerificationError("manifest checksum is invalid")
    required_identity = {
        "manifest_version": MANIFEST_VERSION,
        "pair_id": PAIR_ID,
        "window_start_utc": WINDOW_START.isoformat(),
        "window_end_utc": WINDOW_END.isoformat(),
        "scope_ids": [item.id for item in TRIAL_SCOPES],
        "providers": ["inspire", "arxiv"],
        "staging_only": True,
        "production_scope_registration": False,
        "database_access": False,
        "database_writes": False,
        "public_metric_activation": False,
        "window_end_precision": "minute-inclusive",
        "downstream_target_caps": DOWNSTREAM_TARGET_CAPS.as_dict(),
    }
    if any(value.get(key) != expected for key, expected in required_identity.items()):
        raise PairedCaptureVerificationError(
            "manifest identity or safety flags changed"
        )
    completed_at = value.get("completed_at")
    if not isinstance(completed_at, str):
        raise PairedCaptureVerificationError("manifest completion time is missing")
    try:
        parsed_completed_at = datetime.fromisoformat(completed_at)
    except ValueError as error:
        raise PairedCaptureVerificationError(
            "manifest completion time is invalid"
        ) from error
    if parsed_completed_at.tzinfo is None or parsed_completed_at.utcoffset() is None:
        raise PairedCaptureVerificationError(
            "manifest completion time is not timezone-aware"
        )
    raw_partitions = value.get("partitions")
    if not isinstance(raw_partitions, list) or len(raw_partitions) != 4:
        raise PairedCaptureVerificationError("manifest partition set is incomplete")
    endpoints_by_provider: dict[str, set[str]] = {"inspire": set(), "arxiv": set()}
    for raw_partition in raw_partitions:
        if isinstance(raw_partition, dict):
            provider = raw_partition.get("provider")
            endpoint = raw_partition.get("endpoint")
            if (
                isinstance(provider, str)
                and provider in endpoints_by_provider
                and isinstance(endpoint, str)
            ):
                endpoints_by_provider[provider].add(endpoint)
    if any(len(endpoints) != 1 for endpoints in endpoints_by_provider.values()):
        raise PairedCaptureVerificationError("manifest provider endpoints are mixed")
    try:
        expected_partitions = build_trial_partitions(
            inspire_endpoint=next(iter(endpoints_by_provider["inspire"])),
            arxiv_endpoint=next(iter(endpoints_by_provider["arxiv"])),
        )
        _validate_partitions(expected_partitions)
    except (PairedCaptureSafetyError, StopIteration) as error:
        raise PairedCaptureVerificationError(
            "manifest provider endpoints are invalid"
        ) from error
    expected_by_id = {item.id: item for item in expected_partitions}
    transport_attestation = value.get("transport_attestation")
    if transport_attestation not in {
        INTERNAL_LIVE_TRANSPORT_ATTESTATION,
        INJECTED_TRANSPORT_ATTESTATION,
    }:
        raise PairedCaptureVerificationError(
            "manifest transport attestation is invalid"
        )
    official_endpoints = (
        expected_partitions == build_trial_partitions()
        and transport_attestation == INTERNAL_LIVE_TRANSPORT_ATTESTATION
    )
    if value.get("provider_endpoints_official") is not official_endpoints:
        raise PairedCaptureVerificationError(
            "manifest provider-endpoint classification is invalid"
        )
    partition_checksums: list[str] = []
    partition_ids: list[str] = []
    completed_partitions: list[bool] = []
    execution_stopped = False
    for raw_partition in raw_partitions:
        if not isinstance(raw_partition, dict):
            raise PairedCaptureVerificationError("partition entry is malformed")
        partition_checksum = raw_partition.get("partition_checksum")
        unsigned_partition = dict(raw_partition)
        unsigned_partition.pop("partition_checksum", None)
        if not _is_sha256(partition_checksum) or partition_checksum != _json_checksum(
            unsigned_partition
        ):
            raise PairedCaptureVerificationError("partition checksum is invalid")
        partition_checksums.append(cast(str, partition_checksum))
        partition_id = raw_partition.get("partition_id")
        if not isinstance(partition_id, str) or partition_id not in expected_by_id:
            raise PairedCaptureVerificationError("partition ID is malformed")
        partition_ids.append(partition_id)
        expected_partition = expected_by_id[partition_id]
        expected_partition_identity: dict[str, object] = {
            "scope_id": expected_partition.scope_id,
            "atlas_field_id": expected_partition.atlas_field_id,
            "provider": expected_partition.provider,
            "window_start_utc": WINDOW_START.isoformat(),
            "window_end_utc": WINDOW_END.isoformat(),
            "query": expected_partition.query,
            "query_version": expected_partition.query_version,
            "query_checksum": expected_partition.query_checksum,
            "endpoint": expected_partition.endpoint,
            "caps": expected_partition.caps.as_dict(),
        }
        if any(
            raw_partition.get(key) != expected
            for key, expected in expected_partition_identity.items()
        ):
            raise PairedCaptureVerificationError("partition plan identity changed")
        partition_complete = raw_partition.get("complete")
        if not isinstance(partition_complete, bool):
            raise PairedCaptureVerificationError("partition completion is invalid")
        completed_partitions.append(partition_complete)
        scope_id = raw_partition.get("scope_id")
        provider = raw_partition.get("provider")
        raw_pages = raw_partition.get("pages")
        if (
            scope_id not in TRIAL_SCOPE_BY_ID
            or provider not in {"inspire", "arxiv"}
            or not isinstance(raw_pages, list)
        ):
            raise PairedCaptureVerificationError("partition identity is invalid")
        if not all(isinstance(item, dict) for item in raw_pages):
            raise PairedCaptureVerificationError("page entry is malformed")
        page_count = raw_partition.get("page_count")
        if (
            isinstance(page_count, bool)
            or not isinstance(page_count, int)
            or page_count != len(raw_pages)
        ):
            raise PairedCaptureVerificationError("partition page count is invalid")
        observed_page_numbers = [item.get("page_number") for item in raw_pages]
        if any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in observed_page_numbers
        ) or observed_page_numbers != list(range(1, len(raw_pages) + 1)):
            raise PairedCaptureVerificationError("page numbers are not contiguous")
        parsed_pages: list[_VerifiedPageContent] = []
        for raw_page in raw_pages:
            if not isinstance(raw_page, dict):
                raise PairedCaptureVerificationError("page entry is malformed")
            page_checksum = raw_page.get("checksum")
            page_path = raw_page.get("path")
            if not _is_sha256(page_checksum) or not isinstance(page_path, str):
                raise PairedCaptureVerificationError("page identity is invalid")
            expected_path = _page_path(
                TrialPartition(
                    scope_id=cast(str, scope_id),
                    atlas_field_id=(
                        TRIAL_SCOPE_BY_ID[cast(str, scope_id)].atlas_field_id
                    ),
                    provider=cast(CaptureProvider, provider),
                    query="",
                    endpoint="https://invalid.example",
                    caps=PROVIDER_CAPS[cast(CaptureProvider, provider)],
                    query_version="",
                ),
                cast(str, page_checksum),
            ).as_posix()
            if page_path != expected_path:
                raise PairedCaptureVerificationError("page path is noncanonical")
            evidence_path = (resolved_output / page_path).resolve()
            if not _is_within(evidence_path, resolved_output / "pages"):
                raise PairedCaptureVerificationError("page leaves evidence directory")
            try:
                body = evidence_path.read_bytes()
            except OSError as error:
                raise PairedCaptureVerificationError("page cannot be read") from error
            if hashlib.sha256(body).hexdigest() != page_checksum:
                raise PairedCaptureVerificationError("page checksum is invalid")
            parsed_page = _parse_verified_page(body, expected_partition)
            record_count = raw_page.get("record_count")
            if (
                isinstance(record_count, bool)
                or not isinstance(record_count, int)
                or record_count != len(parsed_page.record_ids)
            ):
                raise PairedCaptureVerificationError(
                    "page record count differs from reparsed provider evidence"
                )
            prior_record_count = sum(len(item.record_ids) for item in parsed_pages)
            parsed_pages.append(parsed_page)
            lineage = raw_page.get("http_lineage")
            if not isinstance(lineage, dict):
                raise PairedCaptureVerificationError("HTTP lineage is missing")
            raw_status_code = lineage.get("status_code")
            if isinstance(raw_status_code, bool) or not isinstance(
                raw_status_code, int
            ):
                raise PairedCaptureVerificationError("HTTP lineage status is invalid")
            try:
                started = datetime.fromisoformat(str(lineage["request_started_at"]))
                received = datetime.fromisoformat(str(lineage["response_received_at"]))
                verified_lineage = HttpCaptureLineage(
                    request_started_at=started,
                    response_received_at=received,
                    request_url=str(lineage["request_url"]),
                    response_url=str(lineage["response_url"]),
                    status_code=raw_status_code,
                    provider_date=cast(str | None, lineage.get("provider_date")),
                    etag=cast(str | None, lineage.get("etag")),
                    last_modified=cast(str | None, lineage.get("last_modified")),
                    content_type=cast(str | None, lineage.get("content_type")),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise PairedCaptureVerificationError(
                    "HTTP lineage is invalid"
                ) from error
            if not 200 <= verified_lineage.status_code < 300:
                raise PairedCaptureVerificationError(
                    "preserved provider page does not have a successful HTTP status"
                )
            if verified_lineage.response_received_at > parsed_completed_at:
                raise PairedCaptureVerificationError(
                    "manifest completion precedes a provider response"
                )
            partition_endpoint = cast(str, raw_partition["endpoint"])
            try:
                expected_request = _expected_page_request(
                    expected_partition,
                    page_number=cast(int, raw_page["page_number"]),
                    prior_record_count=prior_record_count,
                )
                if not _lineage_url_matches_request(
                    str(lineage["request_url"]),
                    partition_endpoint,
                    expected_request,
                ) or not _lineage_url_matches_request(
                    str(lineage["response_url"]),
                    partition_endpoint,
                    expected_request,
                ):
                    raise PairedCaptureVerificationError(
                        "HTTP lineage differs from the fixed page request"
                    )
            except PairedCaptureSafetyError as error:
                raise PairedCaptureVerificationError(
                    "HTTP lineage origin is invalid"
                ) from error

        if execution_stopped:
            expected_not_executed: dict[str, object] = {
                "expected_total": None,
                "records_seen": 0,
                "unique_records_seen": 0,
                "unique_ids_checksum": None,
                "duplicate_count": 0,
                "complete": False,
                "terminal_status": "not-executed",
                "error": None,
            }
            if raw_pages or any(
                type(raw_partition.get(key)) is not type(expected)
                or raw_partition.get(key) != expected
                for key, expected in expected_not_executed.items()
            ):
                raise PairedCaptureVerificationError(
                    "partition was executed after the paired capture had failed"
                )
            continue

        if not parsed_pages:
            expected_request_failure: dict[str, object] = {
                "expected_total": None,
                "records_seen": 0,
                "unique_records_seen": 0,
                "unique_ids_checksum": _ids_checksum(set()),
                "duplicate_count": 0,
                "complete": False,
                "terminal_status": "request-or-storage-failed",
            }
            if any(
                type(raw_partition.get(key)) is not type(expected)
                or raw_partition.get(key) != expected
                for key, expected in expected_request_failure.items()
            ) or not isinstance(raw_partition.get("error"), str):
                raise PairedCaptureVerificationError(
                    "empty executed partition has invalid failure semantics"
                )
            execution_stopped = True
            continue

        recomputed = (
            _recompute_inspire_partition(expected_partition, parsed_pages)
            if expected_partition.provider == "inspire"
            else _recompute_arxiv_partition(expected_partition, parsed_pages)
        )
        _verify_partition_summary(raw_partition, recomputed)
        execution_stopped = not recomputed.complete
    expected_partition_ids = [item.id for item in expected_partitions]
    if partition_ids != expected_partition_ids:
        raise PairedCaptureVerificationError("manifest mixes paired partitions")
    if value.get("partition_checksums") != partition_checksums or value.get(
        "evidence_set_checksum"
    ) != _json_checksum(partition_checksums):
        raise PairedCaptureVerificationError("paired partition binding is invalid")
    if value.get("capture_complete") is not all(completed_partitions):
        raise PairedCaptureVerificationError("paired completion state is invalid")
    return value


def run() -> None:
    parser = argparse.ArgumentParser(
        description="Plan or explicitly execute the staging-only paired capture"
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm-pair-id")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(capture_plan(), indent=2, sort_keys=True))
        return
    if args.output is None:
        parser.error("--output is required with --execute")
    if args.confirm_pair_id != PAIR_ID:
        parser.error(f"--confirm-pair-id must equal {PAIR_ID}")
    manifest, path = execute_paired_capture(output=args.output)
    print(json.dumps({"manifest": str(path), **manifest.as_dict()}, indent=2))
    if not manifest.complete:
        sys.exit(1)


if __name__ == "__main__":
    run()
