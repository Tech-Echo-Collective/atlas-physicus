"""Staging-safe raw acquisition for the bounded hep-th-v1 history trial.

This module deliberately stops at immutable provider page envelopes.  It does
not import the database package, read or write source cursors, resolve entities,
materialize relationships, or calculate metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urljoin, urlparse

from defusedxml import ElementTree as ET

from .config import Settings, get_settings
from .connectors.acquisition import HEP_TH_V1
from .connectors.arxiv import ArxivConnector
from .connectors.base import ConnectorError, SourceTransport
from .connectors.http import ProviderHttpTransport
from .connectors.inspire import InspireConnector

BackfillMode = Literal["plan", "acquire"]
BackfillProvider = Literal["inspire", "arxiv"]

BACKFILL_SCOPE = HEP_TH_V1.id
BACKFILL_YEARS = tuple(range(2020, 2026))
BACKFILL_PROVIDERS: tuple[BackfillProvider, ...] = ("inspire", "arxiv")
BACKFILL_MANIFEST_VERSION = "hep-th-v1-historical-raw-acquisition-manifest-v1"
BACKFILL_PARTITION_STATE_VERSION = (
    "hep-th-v1-historical-raw-acquisition-partition-state-v1"
)
INSPIRE_QUERY_VERSION = "hep-th-v1:inspire:earliest-record-date-v1"
LEGACY_INSPIRE_QUERY_VERSION = "hep-th-v1:inspire:publication-year-v1"
ARXIV_QUERY_VERSION = "hep-th-v1:arxiv:submission-year-v1"
OFFICIAL_INSPIRE_BASE_URL = "https://inspirehep.net/api"
OFFICIAL_ARXIV_BASE_URL = "https://export.arxiv.org/api/query"
OPEN_SEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"


class BackfillSafetyError(ValueError):
    """Raised before any network or filesystem mutation for an unsafe request."""


class BackfillAcquisitionError(RuntimeError):
    """Raised when a provider page cannot establish complete bounded evidence."""


@dataclass(frozen=True)
class HistoricalPartition:
    provider: BackfillProvider
    year: int
    query: str
    query_version: str
    source_version: str
    endpoint: str
    page_size: int

    @property
    def id(self) -> str:
        return f"{BACKFILL_SCOPE}:{self.provider}:{self.year}"

    @property
    def query_checksum(self) -> str:
        return hashlib.sha256(self.query.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoredPage:
    page_number: int
    record_count: int
    checksum: str
    path: str

    def as_dict(self) -> dict[str, object]:
        return {
            "page_number": self.page_number,
            "record_count": self.record_count,
            "checksum": self.checksum,
            "path": self.path,
        }


@dataclass
class PartitionResult:
    partition: HistoricalPartition
    expected_total: int | None = None
    records_seen: int = 0
    seen_unique_ids: int = 0
    unique_ids_checksum: str | None = None
    duplicate_count: int = 0
    page_count: int = 0
    terminal_status: str = "not-executed"
    complete: bool = False
    pages: list[StoredPage] = field(default_factory=list)
    resume_checkpoint: dict[str, object] | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        body: dict[str, object] = {
            "partition_id": self.partition.id,
            "provider": self.partition.provider,
            "year": self.partition.year,
            "query": self.partition.query,
            "query_version": self.partition.query_version,
            "query_checksum": self.partition.query_checksum,
            "source_version": self.partition.source_version,
            "endpoint": self.partition.endpoint,
            "page_size": self.partition.page_size,
            "expected_total": self.expected_total,
            "records_seen": self.records_seen,
            "seen_unique_ids": self.seen_unique_ids,
            "unique_ids_checksum": self.unique_ids_checksum,
            "duplicate_count": self.duplicate_count,
            "page_count": self.page_count,
            "terminal_status": self.terminal_status,
            "complete": self.complete,
            "pages": [item.as_dict() for item in self.pages],
            "resume_checkpoint": self.resume_checkpoint,
            "error": self.error,
        }
        body["partition_checksum"] = _json_checksum(body)
        return body


@dataclass(frozen=True)
class BackfillManifest:
    mode: BackfillMode
    executed: bool
    created_at: datetime
    partitions: tuple[PartitionResult, ...]
    output_path: Path | None = None

    @property
    def successful(self) -> bool:
        if not self.executed:
            return True
        if self.mode == "plan":
            return all(item.terminal_status == "counted" for item in self.partitions)
        return all(item.complete for item in self.partitions)

    def as_dict(self) -> dict[str, object]:
        body: dict[str, object] = {
            "manifest_version": BACKFILL_MANIFEST_VERSION,
            "mode": self.mode,
            "executed": self.executed,
            "created_at": self.created_at.astimezone(UTC).isoformat(),
            "acquisition_scope": BACKFILL_SCOPE,
            "years": list(BACKFILL_YEARS),
            "providers": list(BACKFILL_PROVIDERS),
            "database_access": False,
            "canonical_materialization": False,
            "acquisition_complete": (
                self.executed
                and self.mode == "acquire"
                and all(item.complete for item in self.partitions)
            ),
            "partitions": [item.as_dict() for item in self.partitions],
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


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _page_relative_path(
    partition: HistoricalPartition,
    checksum: str,
) -> Path:
    suffix = ".json" if partition.provider == "inspire" else ".xml"
    return (
        Path("pages") / partition.provider / str(partition.year) / f"{checksum}{suffix}"
    )


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def validate_request(
    *,
    scope: str,
    start_year: int,
    end_year: int,
    output: Path | None,
    execute: bool,
    repo_root: Path | None = None,
) -> Path | None:
    """Fail closed before constructing a live provider transport."""

    if scope != BACKFILL_SCOPE:
        raise BackfillSafetyError(
            f"unsupported scope {scope!r}; this tool is fixed to {BACKFILL_SCOPE}"
        )
    if (start_year, end_year) != (BACKFILL_YEARS[0], BACKFILL_YEARS[-1]):
        raise BackfillSafetyError(
            "this bounded trial is fixed to the closed years 2020-2025"
        )
    if not execute:
        return None
    if output is None:
        raise BackfillSafetyError("--output is required with --execute")

    resolved_output = output.expanduser().resolve()
    resolved_repository = (repo_root or repository_root()).resolve()
    if _is_within(resolved_output, resolved_repository):
        raise BackfillSafetyError(
            "backfill evidence must be written outside the repository; tracked "
            "source, pipeline, and fixture directories are forbidden"
        )
    if resolved_output == Path(resolved_output.anchor):
        raise BackfillSafetyError("the filesystem root is not a valid output directory")
    return resolved_output


def _inspire_query(year: int) -> str:
    return (
        f"document_type:article and {HEP_TH_V1.inspire_query} and "
        f"de >= {year}-01-01 and de <= {year}-12-31"
    )


def _arxiv_query(year: int) -> str:
    return (
        f"({HEP_TH_V1.arxiv_query}) AND "
        f"submittedDate:[{year}01010000 TO {year}12312359]"
    )


def build_partitions(
    *,
    scope: str = BACKFILL_SCOPE,
    start_year: int = BACKFILL_YEARS[0],
    end_year: int = BACKFILL_YEARS[-1],
    inspire_base_url: str = OFFICIAL_INSPIRE_BASE_URL,
    arxiv_base_url: str = OFFICIAL_ARXIV_BASE_URL,
    inspire_page_size: int = 250,
    arxiv_page_size: int = 100,
) -> tuple[HistoricalPartition, ...]:
    validate_request(
        scope=scope,
        start_year=start_year,
        end_year=end_year,
        output=None,
        execute=False,
    )
    if not 1 <= inspire_page_size <= 250:
        raise BackfillSafetyError("INSPIRE page size must be within 1-250")
    if not 1 <= arxiv_page_size <= 100:
        raise BackfillSafetyError("arXiv page size must be within 1-100")

    partitions: list[HistoricalPartition] = []
    for year in BACKFILL_YEARS:
        partitions.extend(
            (
                HistoricalPartition(
                    provider="inspire",
                    year=year,
                    query=_inspire_query(year),
                    query_version=INSPIRE_QUERY_VERSION,
                    source_version=InspireConnector.source_version,
                    endpoint=f"{inspire_base_url.rstrip('/')}/literature",
                    page_size=inspire_page_size,
                ),
                HistoricalPartition(
                    provider="arxiv",
                    year=year,
                    query=_arxiv_query(year),
                    query_version=ARXIV_QUERY_VERSION,
                    source_version=ArxivConnector.source_version,
                    endpoint=arxiv_base_url,
                    page_size=arxiv_page_size,
                ),
            )
        )
    return tuple(partitions)


def _validate_partitions(partitions: Sequence[HistoricalPartition]) -> None:
    expected = {
        (provider, year) for year in BACKFILL_YEARS for provider in BACKFILL_PROVIDERS
    }
    observed = {(item.provider, item.year) for item in partitions}
    if len(partitions) != len(expected) or observed != expected:
        raise BackfillSafetyError(
            "the bounded run must contain exactly one INSPIRE and arXiv partition "
            "for every year from 2020 through 2025"
        )
    for item in partitions:
        expected_query = (
            _inspire_query(item.year)
            if item.provider == "inspire"
            else _arxiv_query(item.year)
        )
        expected_version = (
            INSPIRE_QUERY_VERSION if item.provider == "inspire" else ARXIV_QUERY_VERSION
        )
        maximum_page_size = 250 if item.provider == "inspire" else 100
        if item.query != expected_query or item.query_version != expected_version:
            raise BackfillSafetyError(
                f"partition {item.id} does not use the approved historical query"
            )
        if not 1 <= item.page_size <= maximum_page_size:
            raise BackfillSafetyError(
                f"partition {item.id} exceeds its provider page-size bound"
            )
        if _origin(item.endpoint)[0] != "https":
            raise BackfillSafetyError(
                f"partition {item.id} must use a provider HTTPS endpoint"
            )


def _validate_live_provider_partitions(
    partitions: Sequence[HistoricalPartition],
) -> None:
    """Keep the executable CLI fixed to the two approved public APIs."""

    official = {
        item.id: item.endpoint
        for item in build_partitions(
            inspire_base_url=OFFICIAL_INSPIRE_BASE_URL,
            arxiv_base_url=OFFICIAL_ARXIV_BASE_URL,
        )
    }
    for item in partitions:
        if item.endpoint != official[item.id]:
            raise BackfillSafetyError(
                f"live partition {item.id} must use its official provider endpoint"
            )


def _exact_inspire_total(payload: Mapping[str, Any]) -> int:
    hits = payload.get("hits")
    if not isinstance(hits, Mapping):
        raise BackfillAcquisitionError("INSPIRE response is missing its hits envelope")
    raw_total = hits.get("total")
    if isinstance(raw_total, bool):
        raise BackfillAcquisitionError("INSPIRE returned an invalid total")
    if isinstance(raw_total, int):
        total = raw_total
    elif isinstance(raw_total, Mapping):
        relation = raw_total.get("relation")
        value = raw_total.get("value")
        if relation != "eq" or isinstance(value, bool) or not isinstance(value, int):
            raise BackfillAcquisitionError(
                "INSPIRE did not return an exact bounded result total"
            )
        total = value
    else:
        raise BackfillAcquisitionError("INSPIRE response omitted its result total")
    if total < 0:
        raise BackfillAcquisitionError("INSPIRE returned a negative result total")
    return total


def _arxiv_envelope(xml: str, connector: ArxivConnector) -> tuple[int, list[str]]:
    try:
        root = ET.fromstring(xml)
    except Exception as error:
        raise BackfillAcquisitionError("arXiv returned malformed XML") from error
    total_element = root.find(f"{OPEN_SEARCH}totalResults")
    try:
        total = (
            int((total_element.text or "").strip()) if total_element is not None else -1
        )
    except ValueError as error:
        raise BackfillAcquisitionError("arXiv returned an invalid total") from error
    if total < 0:
        raise BackfillAcquisitionError("arXiv response omitted its result total")
    try:
        identifiers = [item.source_record_id for item in connector._records(xml)]
    except ConnectorError as error:
        raise BackfillAcquisitionError(str(error)) from error
    return total, identifiers


def _inspire_envelope(
    text: str, connector: InspireConnector
) -> tuple[dict[str, Any], int, list[str]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise BackfillAcquisitionError("INSPIRE returned malformed JSON") from error
    if not isinstance(payload, dict):
        raise BackfillAcquisitionError("INSPIRE returned a non-object JSON envelope")
    total = _exact_inspire_total(payload)
    try:
        identifiers = [item.source_record_id for item in connector._records(payload)]
    except ConnectorError as error:
        raise BackfillAcquisitionError(str(error)) from error
    return payload, total, identifiers


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host:
        raise BackfillAcquisitionError(
            "provider page URL is missing a safe HTTP origin"
        )
    if parsed.username is not None or parsed.password is not None:
        raise BackfillAcquisitionError("provider page URL contains user information")
    try:
        port = parsed.port
    except ValueError as error:
        raise BackfillAcquisitionError(
            "provider page URL has an invalid port"
        ) from error
    return parsed.scheme, host, port or (443 if parsed.scheme == "https" else 80)


def _validated_inspire_next(
    value: str,
    *,
    partition: HistoricalPartition,
) -> str:
    resolved = urljoin(f"{partition.endpoint}/", value)
    if _origin(resolved) != _origin(partition.endpoint):
        raise BackfillAcquisitionError("INSPIRE pagination crossed provider origin")
    parsed = urlparse(resolved)
    if parsed.path.rstrip("/") != urlparse(partition.endpoint).path.rstrip("/"):
        raise BackfillAcquisitionError(
            "INSPIRE pagination left the literature endpoint"
        )
    if parsed.fragment:
        raise BackfillAcquisitionError("INSPIRE pagination URL contains a fragment")
    query = parse_qs(parsed.query, keep_blank_values=True)
    supplied_query = query.get("q", [])
    if len(supplied_query) != 1 or " ".join(supplied_query[0].split()) != " ".join(
        partition.query.split()
    ):
        raise BackfillAcquisitionError(
            "INSPIRE pagination changed the historical acquisition query"
        )
    sizes = query.get("size", [])
    if len(sizes) > 1:
        raise BackfillAcquisitionError(
            "INSPIRE pagination contains multiple page sizes"
        )
    if sizes:
        try:
            supplied_size = int(sizes[0])
        except ValueError as error:
            raise BackfillAcquisitionError(
                "INSPIRE pagination contains an invalid page size"
            ) from error
        if not 1 <= supplied_size <= partition.page_size:
            raise BackfillAcquisitionError(
                "INSPIRE pagination exceeded the bounded page size"
            )
    return resolved


def _store_page(
    output: Path,
    partition: HistoricalPartition,
    *,
    page_number: int,
    content: str,
    record_count: int,
) -> StoredPage:
    payload = content.encode("utf-8")
    checksum = hashlib.sha256(payload).hexdigest()
    relative = _page_relative_path(partition, checksum)
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as error:
        if destination.read_bytes() != payload:
            raise BackfillAcquisitionError(
                "content-addressed page path contains different bytes"
            ) from error
    return StoredPage(
        page_number=page_number,
        record_count=record_count,
        checksum=checksum,
        path=relative.as_posix(),
    )


class HistoricalRawAcquirer:
    """Acquire independent provider/year partitions without touching persistence."""

    def __init__(
        self,
        transports: Mapping[BackfillProvider, SourceTransport],
        partitions: Sequence[HistoricalPartition],
        *,
        output: Path,
        resume_partitions: Mapping[str, PartitionResult] | None = None,
        persist_partition: Callable[[PartitionResult], None] | None = None,
        progress: Callable[[BackfillMode, PartitionResult], None] | None = None,
        maximum_pages_per_partition: int = 10_000,
    ):
        self.transports = transports
        self.partitions = tuple(partitions)
        _validate_partitions(self.partitions)
        self.output = output
        self.resume_partitions = dict(resume_partitions or {})
        unknown_resume = set(self.resume_partitions) - {
            item.id for item in self.partitions
        }
        if unknown_resume:
            raise BackfillSafetyError("resume state contains unknown partitions")
        self.persist_partition = persist_partition
        self.progress = progress
        self.maximum_pages_per_partition = maximum_pages_per_partition
        if maximum_pages_per_partition < 1:
            raise ValueError("maximum pages per partition must be positive")

    def run(self, mode: BackfillMode) -> tuple[PartitionResult, ...]:
        if mode == "acquire":
            self._verify_all_resume_partitions()
        results: list[PartitionResult] = []
        for partition in self.partitions:
            try:
                result = (
                    self._count_partition(partition)
                    if mode == "plan"
                    else self._acquire_partition(partition)
                )
            except BackfillSafetyError:
                raise
            except Exception as error:
                result = PartitionResult(
                    partition=partition,
                    terminal_status="failed",
                    error=f"{type(error).__name__}: {error}"[:1000],
                )
            results.append(result)
            if mode == "acquire" and self.persist_partition is not None:
                self.persist_partition(result)
            if self.progress is not None:
                self.progress(mode, result)
        return tuple(results)

    def _verify_all_resume_partitions(self) -> None:
        """Verify all local evidence before allowing the first provider request."""

        for partition in self.partitions:
            if partition.id not in self.resume_partitions:
                continue
            transport = self.transports[partition.provider]
            connector: InspireConnector | ArxivConnector
            if partition.provider == "inspire":
                connector = InspireConnector(
                    transport, partition.endpoint.removesuffix("/literature")
                )
            else:
                connector = ArxivConnector(transport, partition.endpoint)
            self._restored_state(partition, connector)

    def _count_partition(self, partition: HistoricalPartition) -> PartitionResult:
        if partition.provider == "inspire":
            text = self.transports["inspire"].get_text(
                partition.endpoint,
                params={"q": partition.query, "sort": "mostrecent", "size": 1},
            )
            inspire_connector = InspireConnector(
                self.transports["inspire"],
                partition.endpoint.removesuffix("/literature"),
            )
            _, total, identifiers = _inspire_envelope(text, inspire_connector)
        else:
            text = self.transports["arxiv"].get_text(
                partition.endpoint,
                params={
                    "search_query": partition.query,
                    "start": 0,
                    "max_results": 1,
                    "sortBy": "submittedDate",
                    "sortOrder": "ascending",
                },
            )
            arxiv_connector = ArxivConnector(
                self.transports["arxiv"], partition.endpoint
            )
            total, identifiers = _arxiv_envelope(text, arxiv_connector)
        page = _store_page(
            self.output,
            partition,
            page_number=1,
            content=text,
            record_count=len(identifiers),
        )
        seen_identifiers = set(identifiers)
        return PartitionResult(
            partition=partition,
            expected_total=total,
            records_seen=len(identifiers),
            seen_unique_ids=len(seen_identifiers),
            unique_ids_checksum=_ids_checksum(seen_identifiers),
            duplicate_count=len(identifiers) - len(seen_identifiers),
            page_count=1,
            terminal_status="counted",
            pages=[page],
        )

    def _acquire_partition(self, partition: HistoricalPartition) -> PartitionResult:
        if partition.provider == "inspire":
            return self._acquire_inspire(partition)
        return self._acquire_arxiv(partition)

    def _restored_state(
        self,
        partition: HistoricalPartition,
        connector: InspireConnector | ArxivConnector,
    ) -> tuple[
        PartitionResult | None,
        list[StoredPage],
        int | None,
        int,
        set[str],
    ]:
        previous = self.resume_partitions.get(partition.id)
        if previous is None:
            return None, [], None, 0, set()
        if previous.partition != partition:
            raise BackfillSafetyError(
                f"resume state for {partition.id} does not match the active plan"
            )

        pages = sorted(previous.pages, key=lambda item: item.page_number)
        if [item.page_number for item in pages] != list(range(1, len(pages) + 1)):
            raise BackfillSafetyError(
                f"resume pages for {partition.id} are not contiguous"
            )
        identifiers: set[str] = set()
        records_seen = 0
        expected_total: int | None = None
        for page in pages:
            if Path(page.path) != _page_relative_path(partition, page.checksum):
                raise BackfillSafetyError(
                    f"resume page path is noncanonical for {partition.id}"
                )
            page_path = (self.output / page.path).resolve()
            if not _is_within(page_path, self.output.resolve()):
                raise BackfillSafetyError(
                    f"resume page for {partition.id} leaves the output directory"
                )
            payload = page_path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != page.checksum:
                raise BackfillSafetyError(
                    f"resume page checksum failed for {partition.id}"
                )
            text = payload.decode("utf-8")
            if partition.provider == "inspire":
                if not isinstance(connector, InspireConnector):
                    raise AssertionError("INSPIRE partition has the wrong parser")
                _, total, page_ids = _inspire_envelope(text, connector)
            else:
                if not isinstance(connector, ArxivConnector):
                    raise AssertionError("arXiv partition has the wrong parser")
                total, page_ids = _arxiv_envelope(text, connector)
            if expected_total is None:
                expected_total = total
            elif expected_total != total:
                raise BackfillSafetyError(
                    f"resume page totals disagree for {partition.id}"
                )
            if len(page_ids) != page.record_count:
                raise BackfillSafetyError(
                    f"resume page record count failed for {partition.id}"
                )
            records_seen += len(page_ids)
            identifiers.update(page_ids)

        duplicates = records_seen - len(identifiers)
        if (
            previous.expected_total != expected_total
            or previous.records_seen != records_seen
            or previous.seen_unique_ids != len(identifiers)
            or previous.duplicate_count != duplicates
            or previous.page_count != len(pages)
            or previous.unique_ids_checksum != _ids_checksum(identifiers)
        ):
            raise BackfillSafetyError(
                f"resume partition summary failed verification for {partition.id}"
            )
        if previous.complete:
            if (
                expected_total is None
                or len(identifiers) != expected_total
                or duplicates != 0
                or previous.terminal_status != "complete"
            ):
                raise BackfillSafetyError(
                    f"completed resume partition is inconsistent for {partition.id}"
                )
            return previous, pages, expected_total, records_seen, identifiers
        return None, pages, expected_total, records_seen, identifiers

    @staticmethod
    def _failed_partition(
        partition: HistoricalPartition,
        *,
        error: Exception,
        expected_total: int | None,
        records_seen: int,
        identifiers: set[str],
        pages: list[StoredPage],
        resume_checkpoint: dict[str, object],
    ) -> PartitionResult:
        return PartitionResult(
            partition=partition,
            expected_total=expected_total,
            records_seen=records_seen,
            seen_unique_ids=len(identifiers),
            unique_ids_checksum=_ids_checksum(identifiers),
            duplicate_count=records_seen - len(identifiers),
            page_count=len(pages),
            terminal_status="failed",
            complete=False,
            pages=pages,
            resume_checkpoint=resume_checkpoint,
            error=f"{type(error).__name__}: {error}"[:1000],
        )

    def _acquire_inspire(self, partition: HistoricalPartition) -> PartitionResult:
        transport = self.transports["inspire"]
        connector = InspireConnector(
            transport, partition.endpoint.removesuffix("/literature")
        )
        restored, pages, expected_total, records_seen, identifiers = (
            self._restored_state(partition, connector)
        )
        if restored is not None:
            return restored
        previous = self.resume_partitions.get(partition.id)
        raw_checkpoint = previous.resume_checkpoint if previous is not None else None
        checkpoint_next = raw_checkpoint.get("next_url") if raw_checkpoint else None
        if checkpoint_next is not None and not isinstance(checkpoint_next, str):
            raise BackfillSafetyError(
                f"resume checkpoint is invalid for {partition.id}"
            )
        if pages and not checkpoint_next:
            # A terminal duplicate/count failure has no safe unseen next page.
            assert previous is not None
            return previous
        next_url = (
            _validated_inspire_next(checkpoint_next, partition=partition)
            if isinstance(checkpoint_next, str) and checkpoint_next
            else None
        )
        visited_urls: set[str] = set()
        terminal_reached = False

        for page_number in range(len(pages) + 1, self.maximum_pages_per_partition + 1):
            request_checkpoint: dict[str, object] = {"next_url": next_url}
            try:
                if next_url is None:
                    text = transport.get_text(
                        partition.endpoint,
                        params={
                            "q": partition.query,
                            "sort": "mostrecent",
                            "size": partition.page_size,
                        },
                    )
                else:
                    if next_url in visited_urls:
                        raise BackfillAcquisitionError(
                            "INSPIRE pagination repeated a page URL"
                        )
                    visited_urls.add(next_url)
                    text = transport.get_text(next_url)
                payload, total, page_ids = _inspire_envelope(text, connector)
                if expected_total is None:
                    expected_total = total
                elif expected_total != total:
                    raise BackfillAcquisitionError(
                        "INSPIRE result total changed during the closed partition"
                    )
                links = payload.get("links")
                if not isinstance(links, Mapping):
                    raise BackfillAcquisitionError(
                        "INSPIRE response is missing its pagination links"
                    )
                raw_next = links.get("next")
                if raw_next is None or raw_next == "":
                    validated_next = None
                    terminal_reached = True
                elif not isinstance(raw_next, str):
                    raise BackfillAcquisitionError(
                        "INSPIRE response contains a malformed next link"
                    )
                else:
                    validated_next = _validated_inspire_next(
                        raw_next, partition=partition
                    )
                stored_page = _store_page(
                    self.output,
                    partition,
                    page_number=page_number,
                    content=text,
                    record_count=len(page_ids),
                )
            except Exception as error:
                return self._failed_partition(
                    partition,
                    error=error,
                    expected_total=expected_total,
                    records_seen=records_seen,
                    identifiers=identifiers,
                    pages=pages,
                    resume_checkpoint=request_checkpoint,
                )
            records_seen += len(page_ids)
            identifiers.update(page_ids)
            pages.append(stored_page)
            next_url = validated_next
            if terminal_reached:
                break

        duplicate_count = records_seen - len(identifiers)
        complete = bool(
            terminal_reached
            and expected_total is not None
            and len(identifiers) == expected_total
            and duplicate_count == 0
        )
        if not terminal_reached:
            terminal_status = "page-limit-exceeded"
        elif duplicate_count:
            terminal_status = "duplicate-records"
        elif expected_total != len(identifiers):
            terminal_status = "count-mismatch"
        else:
            terminal_status = "complete"
        return PartitionResult(
            partition=partition,
            expected_total=expected_total,
            records_seen=records_seen,
            seen_unique_ids=len(identifiers),
            unique_ids_checksum=_ids_checksum(identifiers),
            duplicate_count=duplicate_count,
            page_count=len(pages),
            terminal_status=terminal_status,
            complete=complete,
            pages=pages,
            resume_checkpoint=(None if terminal_reached else {"next_url": next_url}),
        )

    def _acquire_arxiv(self, partition: HistoricalPartition) -> PartitionResult:
        transport = self.transports["arxiv"]
        connector = ArxivConnector(transport, partition.endpoint)
        restored, pages, expected_total, records_seen, identifiers = (
            self._restored_state(partition, connector)
        )
        if restored is not None:
            return restored
        previous = self.resume_partitions.get(partition.id)
        raw_checkpoint = previous.resume_checkpoint if previous is not None else None
        checkpoint_start = raw_checkpoint.get("start") if raw_checkpoint else 0
        if isinstance(checkpoint_start, bool) or not isinstance(checkpoint_start, int):
            raise BackfillSafetyError(
                f"resume checkpoint is invalid for {partition.id}"
            )
        if checkpoint_start != records_seen:
            raise BackfillSafetyError(
                f"resume offset does not match preserved pages for {partition.id}"
            )
        if pages and raw_checkpoint is None:
            assert previous is not None
            return previous
        start = checkpoint_start
        terminal_reached = False

        for page_number in range(len(pages) + 1, self.maximum_pages_per_partition + 1):
            try:
                text = transport.get_text(
                    partition.endpoint,
                    params={
                        "search_query": partition.query,
                        "start": start,
                        "max_results": partition.page_size,
                        "sortBy": "submittedDate",
                        "sortOrder": "ascending",
                    },
                )
                total, page_ids = _arxiv_envelope(text, connector)
                if expected_total is None:
                    expected_total = total
                elif expected_total != total:
                    raise BackfillAcquisitionError(
                        "arXiv result total changed during the closed partition"
                    )
                stored_page = _store_page(
                    self.output,
                    partition,
                    page_number=page_number,
                    content=text,
                    record_count=len(page_ids),
                )
            except Exception as error:
                return self._failed_partition(
                    partition,
                    error=error,
                    expected_total=expected_total,
                    records_seen=records_seen,
                    identifiers=identifiers,
                    pages=pages,
                    resume_checkpoint={"start": start},
                )
            records_seen += len(page_ids)
            identifiers.update(page_ids)
            pages.append(stored_page)
            start += len(page_ids)
            if start >= total:
                terminal_reached = True
                break
            if not page_ids:
                break

        duplicate_count = records_seen - len(identifiers)
        complete = bool(
            terminal_reached
            and expected_total is not None
            and len(identifiers) == expected_total
            and duplicate_count == 0
        )
        if not terminal_reached:
            terminal_status = "incomplete-page-stream"
        elif duplicate_count:
            terminal_status = "duplicate-records"
        elif expected_total != len(identifiers):
            terminal_status = "count-mismatch"
        else:
            terminal_status = "complete"
        return PartitionResult(
            partition=partition,
            expected_total=expected_total,
            records_seen=records_seen,
            seen_unique_ids=len(identifiers),
            unique_ids_checksum=_ids_checksum(identifiers),
            duplicate_count=duplicate_count,
            page_count=len(pages),
            terminal_status=terminal_status,
            complete=complete,
            pages=pages,
            resume_checkpoint=(None if terminal_reached else {"start": start}),
        )


def _provider_transport(
    settings: Settings, base_url: str, interval: float
) -> ProviderHttpTransport:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme != "https" or not host:
        raise BackfillSafetyError("historical provider URLs must use HTTPS")
    return ProviderHttpTransport(
        timeout_seconds=settings.provider_timeout_seconds,
        minimum_intervals={host: interval},
        allowed_hosts={host},
    )


def _write_manifest(output: Path, manifest: BackfillManifest) -> Path:
    payload = manifest.as_dict()
    checksum = str(payload["manifest_checksum"])
    destination = output / "manifests" / f"{checksum}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    try:
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    except FileExistsError as error:
        if destination.read_text(encoding="utf-8") != rendered:
            raise BackfillAcquisitionError(
                "content-addressed manifest path contains different content"
            ) from error
    return destination


def _partition_result_from_dict(
    value: Mapping[str, Any],
    partitions: Mapping[str, HistoricalPartition],
) -> PartitionResult:
    raw_checksum = value.get("partition_checksum")
    unsigned = dict(value)
    unsigned.pop("partition_checksum", None)
    if (
        not isinstance(raw_checksum, str)
        or not _is_sha256(raw_checksum)
        or _json_checksum(unsigned) != raw_checksum
    ):
        raise BackfillSafetyError("resume partition checksum is invalid")
    partition_id = value.get("partition_id")
    if not isinstance(partition_id, str) or partition_id not in partitions:
        raise BackfillSafetyError("resume manifest contains an unknown partition")
    partition = partitions[partition_id]
    expected_identity = {
        "provider": partition.provider,
        "year": partition.year,
        "query": partition.query,
        "query_checksum": partition.query_checksum,
        "source_version": partition.source_version,
        "endpoint": partition.endpoint,
        "page_size": partition.page_size,
    }
    identity_changed = any(
        value.get(key) != expected for key, expected in expected_identity.items()
    )
    query_version = value.get("query_version")
    query_version_is_current = query_version == partition.query_version
    query_version_is_corrected_legacy_label = (
        partition.provider == "inspire"
        and partition.query_version == INSPIRE_QUERY_VERSION
        and query_version == LEGACY_INSPIRE_QUERY_VERSION
    )
    if identity_changed or not (
        query_version_is_current or query_version_is_corrected_legacy_label
    ):
        raise BackfillSafetyError(
            f"resume partition metadata changed for {partition.id}"
        )

    raw_pages = value.get("pages")
    if not isinstance(raw_pages, list):
        raise BackfillSafetyError("resume partition pages are malformed")
    pages: list[StoredPage] = []
    for raw_page in raw_pages:
        if not isinstance(raw_page, Mapping):
            raise BackfillSafetyError("resume page metadata is malformed")
        page_number = raw_page.get("page_number")
        record_count = raw_page.get("record_count")
        checksum = raw_page.get("checksum")
        path = raw_page.get("path")
        if (
            isinstance(page_number, bool)
            or not isinstance(page_number, int)
            or page_number < 1
            or isinstance(record_count, bool)
            or not isinstance(record_count, int)
            or record_count < 0
            or not isinstance(checksum, str)
            or not _is_sha256(checksum)
            or not isinstance(path, str)
            or not path
        ):
            raise BackfillSafetyError("resume page metadata is invalid")
        pages.append(StoredPage(page_number, record_count, checksum, path))

    def optional_nonnegative_int(name: str) -> int | None:
        raw = value.get(name)
        if raw is None:
            return None
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise BackfillSafetyError(f"resume field {name} is invalid")
        return int(raw)

    records_seen = optional_nonnegative_int("records_seen")
    unique_count = optional_nonnegative_int("seen_unique_ids")
    duplicates = optional_nonnegative_int("duplicate_count")
    page_count = optional_nonnegative_int("page_count")
    if None in (records_seen, unique_count, duplicates, page_count):
        raise BackfillSafetyError("resume partition counts are incomplete")
    assert records_seen is not None
    assert unique_count is not None
    assert duplicates is not None
    assert page_count is not None
    checkpoint = value.get("resume_checkpoint")
    if checkpoint is not None and not isinstance(checkpoint, dict):
        raise BackfillSafetyError("resume checkpoint is malformed")
    terminal_status = value.get("terminal_status")
    if not isinstance(terminal_status, str):
        raise BackfillSafetyError("resume terminal status is malformed")
    unique_checksum = value.get("unique_ids_checksum")
    if unique_checksum is not None and not isinstance(unique_checksum, str):
        raise BackfillSafetyError("resume unique-ID checksum is malformed")
    error = value.get("error")
    if error is not None and not isinstance(error, str):
        raise BackfillSafetyError("resume error field is malformed")
    complete = value.get("complete")
    if not isinstance(complete, bool):
        raise BackfillSafetyError("resume completion field is malformed")
    return PartitionResult(
        partition=partition,
        expected_total=optional_nonnegative_int("expected_total"),
        records_seen=records_seen,
        seen_unique_ids=unique_count,
        unique_ids_checksum=unique_checksum,
        duplicate_count=duplicates,
        page_count=page_count,
        terminal_status=terminal_status,
        complete=complete,
        pages=pages,
        resume_checkpoint=dict(checkpoint) if checkpoint is not None else None,
        error=error,
    )


def _partition_state_directory(
    output: Path,
    partition: HistoricalPartition,
) -> Path:
    return output / "partition-state" / partition.provider / str(partition.year)


def _write_partition_state(output: Path, result: PartitionResult) -> Path:
    body: dict[str, object] = {
        "state_version": BACKFILL_PARTITION_STATE_VERSION,
        "manifest_version": BACKFILL_MANIFEST_VERSION,
        "acquisition_scope": BACKFILL_SCOPE,
        "partition": result.as_dict(),
    }
    body["state_checksum"] = _json_checksum(body)
    checksum = str(body["state_checksum"])
    destination = _partition_state_directory(output, result.partition) / (
        f"{checksum}.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(body, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    try:
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    except FileExistsError as error:
        if destination.read_text(encoding="utf-8") != rendered:
            raise BackfillSafetyError(
                "content-addressed partition state contains different content"
            ) from error
    except OSError as error:
        raise BackfillSafetyError("partition state could not be persisted") from error
    return destination


def load_partition_states(
    output: Path,
    partitions: Sequence[HistoricalPartition],
) -> dict[str, PartitionResult]:
    index = {item.id: item for item in partitions}
    restored: dict[str, PartitionResult] = {}
    for partition in partitions:
        directory = _partition_state_directory(output, partition)
        if not directory.is_dir():
            continue
        candidates: list[PartitionResult] = []
        for path in directory.glob("*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise BackfillSafetyError("partition state cannot be read") from error
            if not isinstance(value, dict):
                raise BackfillSafetyError("partition state is not a JSON object")
            raw_checksum = value.get("state_checksum")
            unsigned = dict(value)
            unsigned.pop("state_checksum", None)
            if (
                not isinstance(raw_checksum, str)
                or not _is_sha256(raw_checksum)
                or _json_checksum(unsigned) != raw_checksum
                or path.name != f"{raw_checksum}.json"
            ):
                raise BackfillSafetyError("partition state checksum is invalid")
            if (
                value.get("state_version") != BACKFILL_PARTITION_STATE_VERSION
                or value.get("manifest_version") != BACKFILL_MANIFEST_VERSION
                or value.get("acquisition_scope") != BACKFILL_SCOPE
            ):
                raise BackfillSafetyError(
                    "partition state is outside the bounded trial"
                )
            raw_partition = value.get("partition")
            if not isinstance(raw_partition, Mapping):
                raise BackfillSafetyError("partition state payload is malformed")
            result = _partition_result_from_dict(raw_partition, index)
            if result.partition != partition:
                raise BackfillSafetyError("partition state is stored in the wrong path")
            candidates.append(result)
        if candidates:
            restored[partition.id] = max(
                candidates,
                key=lambda item: (
                    item.complete,
                    item.page_count,
                    item.records_seen,
                ),
            )
    return restored


def load_resume_manifest(
    manifest_path: Path,
    *,
    output: Path,
    partitions: Sequence[HistoricalPartition],
) -> dict[str, PartitionResult]:
    resolved_output = output.resolve()
    resolved_manifest = manifest_path.resolve()
    if not _is_within(resolved_manifest, resolved_output / "manifests"):
        raise BackfillSafetyError(
            "resume manifest must belong to the active output directory"
        )
    try:
        value = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BackfillSafetyError("resume manifest cannot be read") from error
    if not isinstance(value, dict):
        raise BackfillSafetyError("resume manifest is not a JSON object")
    raw_checksum = value.get("manifest_checksum")
    unsigned = dict(value)
    unsigned.pop("manifest_checksum", None)
    if (
        not isinstance(raw_checksum, str)
        or not _is_sha256(raw_checksum)
        or _json_checksum(unsigned) != raw_checksum
        or resolved_manifest.name != f"{raw_checksum}.json"
    ):
        raise BackfillSafetyError("resume manifest checksum is invalid")
    if (
        value.get("manifest_version") != BACKFILL_MANIFEST_VERSION
        or value.get("mode") != "acquire"
        or value.get("executed") is not True
        or value.get("acquisition_scope") != BACKFILL_SCOPE
        or value.get("years") != list(BACKFILL_YEARS)
        or value.get("providers") != list(BACKFILL_PROVIDERS)
        or value.get("database_access") is not False
        or value.get("canonical_materialization") is not False
    ):
        raise BackfillSafetyError("resume manifest is outside the bounded raw trial")
    partition_index = {item.id: item for item in partitions}
    raw_partitions = value.get("partitions")
    if not isinstance(raw_partitions, list) or len(raw_partitions) != len(
        partition_index
    ):
        raise BackfillSafetyError("resume manifest partition set is incomplete")
    restored: dict[str, PartitionResult] = {}
    for raw_partition in raw_partitions:
        if not isinstance(raw_partition, Mapping):
            raise BackfillSafetyError("resume partition is malformed")
        result = _partition_result_from_dict(raw_partition, partition_index)
        if result.partition.id in restored:
            raise BackfillSafetyError("resume manifest repeats a partition")
        restored[result.partition.id] = result
    if set(restored) != set(partition_index):
        raise BackfillSafetyError("resume manifest partition set does not match")
    return restored


def latest_resume_manifest(output: Path) -> Path | None:
    manifest_directory = output / "manifests"
    if not manifest_directory.is_dir():
        return None
    candidates: list[tuple[datetime, Path]] = []
    for path in manifest_directory.glob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BackfillSafetyError(
                "the output manifest directory contains unreadable state"
            ) from error
        if not isinstance(value, dict):
            raise BackfillSafetyError("the output manifest is not a JSON object")
        raw_checksum = value.get("manifest_checksum")
        unsigned = dict(value)
        unsigned.pop("manifest_checksum", None)
        if (
            not isinstance(raw_checksum, str)
            or not _is_sha256(raw_checksum)
            or _json_checksum(unsigned) != raw_checksum
            or path.name != f"{raw_checksum}.json"
        ):
            raise BackfillSafetyError("the output manifest checksum is invalid")
        if value.get("manifest_version") != BACKFILL_MANIFEST_VERSION:
            raise BackfillSafetyError("the output contains a foreign manifest")
        if value.get("mode") != "acquire":
            continue
        created_at = value.get("created_at")
        if not isinstance(created_at, str):
            continue
        try:
            timestamp = datetime.fromisoformat(created_at)
        except ValueError as error:
            raise BackfillSafetyError(
                "an acquisition manifest has an invalid timestamp"
            ) from error
        if timestamp.tzinfo is None:
            raise BackfillSafetyError(
                "an acquisition manifest timestamp lacks a timezone"
            )
        candidates.append((timestamp, path))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def preview_manifest(
    mode: BackfillMode,
    partitions: Sequence[HistoricalPartition],
    *,
    now: datetime | None = None,
) -> BackfillManifest:
    return BackfillManifest(
        mode=mode,
        executed=False,
        created_at=now or datetime.now(UTC),
        partitions=tuple(PartitionResult(item) for item in partitions),
    )


def execute_backfill(
    mode: BackfillMode,
    *,
    output: Path,
    settings: Settings | None = None,
    now: datetime | None = None,
    partitions: Sequence[HistoricalPartition] | None = None,
    transports: Mapping[BackfillProvider, SourceTransport] | None = None,
    resume_manifest: Path | None = None,
    progress: Callable[[BackfillMode, PartitionResult], None] | None = None,
) -> BackfillManifest:
    active_settings = settings or get_settings()
    active_partitions = tuple(
        partitions
        or build_partitions(
            inspire_base_url=active_settings.inspire_base_url,
            arxiv_base_url=active_settings.arxiv_base_url,
        )
    )
    resolved_output = validate_request(
        scope=BACKFILL_SCOPE,
        start_year=BACKFILL_YEARS[0],
        end_year=BACKFILL_YEARS[-1],
        output=output,
        execute=True,
    )
    assert resolved_output is not None
    _validate_partitions(active_partitions)
    if transports is None:
        _validate_live_provider_partitions(active_partitions)
    resolved_resume = resume_manifest
    if mode == "acquire" and resolved_resume is None:
        resolved_resume = latest_resume_manifest(resolved_output)
    resume_partitions = (
        load_resume_manifest(
            resolved_resume,
            output=resolved_output,
            partitions=active_partitions,
        )
        if resolved_resume is not None
        else {}
    )
    if mode == "acquire":
        for partition_id, state in load_partition_states(
            resolved_output, active_partitions
        ).items():
            previous = resume_partitions.get(partition_id)
            state_rank = (state.complete, state.page_count, state.records_seen)
            previous_rank = (
                (previous.complete, previous.page_count, previous.records_seen)
                if previous is not None
                else None
            )
            if previous_rank is None or state_rank >= previous_rank:
                resume_partitions[partition_id] = state

    def persist_result(result: PartitionResult) -> None:
        _write_partition_state(resolved_output, result)

    persist_partition = persist_result if mode == "acquire" else None

    if transports is not None:
        results = HistoricalRawAcquirer(
            transports,
            active_partitions,
            output=resolved_output,
            resume_partitions=resume_partitions,
            persist_partition=persist_partition,
            progress=progress,
        ).run(mode)
    else:
        with ExitStack() as stack:
            inspire_transport = stack.enter_context(
                _provider_transport(
                    active_settings, active_settings.inspire_base_url, 1.0
                )
            )
            arxiv_transport = stack.enter_context(
                _provider_transport(
                    active_settings, active_settings.arxiv_base_url, 3.0
                )
            )
            results = HistoricalRawAcquirer(
                {"inspire": inspire_transport, "arxiv": arxiv_transport},
                active_partitions,
                output=resolved_output,
                resume_partitions=resume_partitions,
                persist_partition=persist_partition,
                progress=progress,
            ).run(mode)

    manifest = BackfillManifest(
        mode=mode,
        executed=True,
        created_at=now or datetime.now(UTC),
        partitions=results,
    )
    manifest_path = _write_manifest(resolved_output, manifest)
    return BackfillManifest(
        mode=manifest.mode,
        executed=manifest.executed,
        created_at=manifest.created_at,
        partitions=manifest.partitions,
        output_path=manifest_path,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or acquire the staging-only hep-th-v1 2020-2025 raw history; "
            "no database or metric writes are performed"
        )
    )
    parser.add_argument("mode", choices=["plan", "acquire"])
    parser.add_argument("--scope", default=BACKFILL_SCOPE)
    parser.add_argument("--start-year", type=int, default=BACKFILL_YEARS[0])
    parser.add_argument("--end-year", type=int, default=BACKFILL_YEARS[-1])
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--resume-manifest",
        type=Path,
        help=(
            "verified earlier acquisition manifest; otherwise the latest valid "
            "manifest in the output directory is resumed automatically"
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="permit provider requests and immutable output writes",
    )
    return parser


def _print_progress(mode: BackfillMode, result: PartitionResult) -> None:
    expected = "unknown" if result.expected_total is None else result.expected_total
    print(
        " ".join(
            (
                f"mode={mode}",
                f"provider={result.partition.provider}",
                f"year={result.partition.year}",
                f"status={result.terminal_status}",
                f"seen={result.seen_unique_ids}",
                f"expected={expected}",
            )
        ),
        file=sys.stderr,
        flush=True,
    )


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = validate_request(
        scope=args.scope,
        start_year=args.start_year,
        end_year=args.end_year,
        output=args.output,
        execute=args.execute,
    )
    if args.resume_manifest is not None and (
        not args.execute or args.mode != "acquire"
    ):
        raise BackfillSafetyError(
            "--resume-manifest is valid only with acquire --execute"
        )
    settings = get_settings()
    partitions = build_partitions(
        scope=args.scope,
        start_year=args.start_year,
        end_year=args.end_year,
        inspire_base_url=settings.inspire_base_url,
        arxiv_base_url=settings.arxiv_base_url,
    )
    if not args.execute:
        manifest = preview_manifest(args.mode, partitions)
    else:
        assert output is not None
        manifest = execute_backfill(
            args.mode,
            output=output,
            settings=settings,
            partitions=partitions,
            resume_manifest=args.resume_manifest,
            progress=_print_progress,
        )
    payload = manifest.as_dict()
    if manifest.output_path is not None:
        payload["manifest_path"] = str(manifest.output_path)
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if manifest.successful else 1


if __name__ == "__main__":
    raise SystemExit(run())
