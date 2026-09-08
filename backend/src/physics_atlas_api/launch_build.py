"""Explicit bounded launch acquisition, never imported by the production worker.

Run only with one owner-supplied private ephemeral directory. Provider pages are
processed and discarded. Checkpoint pickles are local trusted working state, NOT
published evidence or input accepted from another party. The launch owner removes
the directory on success or failure. No production database is used here.
"""

from __future__ import annotations

import argparse
import gc
import gzip
import hashlib
import json
import os
import pickle
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from fractions import Fraction
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from .certification.contracts import EvidenceReference, canonical_digest
from .certification.launch_attribution import (
    LAUNCH_ATTRIBUTION_VERSION,
    LaunchAttributionResult,
    attribute_launch_record,
)
from .certification.launch_capture import (
    CompletedLaunchPage,
    FetchedLaunchPage,
    collect_launch_year,
)
from .certification.launch_inputs import (
    LAUNCH_INPUT_PROJECTION_VERSION,
    capture_launch_occurrence,
)
from .certification.launch_scope import (
    BoundedLaunchSourcePlan,
    bounded_launch_source_plan,
)
from .certification.ror_affiliation_match import (
    RORAffiliationMatchResult,
    certify_paper_raw_affiliation_match,
    ror_affiliation_reference_id,
    ror_affiliation_request_uri,
)
from .certification.ror_grid_crosswalk import (
    RORGridCrosswalkResult,
    capture_ror_grid_crosswalk,
    inspire_grid_id,
    ror_grid_request_uri,
)
from .connectors.acquisition import AcquisitionScope
from .connectors.base import SourceRecord, normalize_external_id
from .connectors.inspire import InspireConnector

MAX_EPHEMERAL_BYTES = 1_900_000_000  # Leave headroom below the owner's hard 2 GB.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
PAGE_CHECKPOINT_VERSION = "ephemeral-compact-launch-page-v1"
MAX_PAGE_CHECKPOINT_BYTES = 64 * 1024 * 1024


def _storage_bytes(root: Path) -> int:
    return sum(
        p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink()
    )


def _publish_checkpoint(
    root: Path, destination: Path, *parts: bytes | memoryview
) -> None:
    temporary = root / f".page-write-{uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            for part in parts:
                stream.write(part)
            stream.flush()
            os.fsync(stream.fileno())
        # Both paths briefly name the SAME inode, not two physical payloads.
        # Exclusive linking cannot replace another attempt's completed artifact.
        os.link(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()  # Only the exact temporary file this call created.


def _write_checkpoint(root: Path, destination: Path, value: object) -> int:
    """Reserve actual compressed bytes before any filesystem write.

    This is trusted ephemeral working state, not a public deserialization API.
    Other launch jobs share the root, so retain a 100 MB safety margin.
    """
    if destination.parent != root or destination.exists() or destination.is_symlink():
        raise ValueError("checkpoint must be new and inside the launch root")
    buffer = BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=1, mtime=0) as stream:
        pickle.dump(value, stream, protocol=5)
    payload = buffer.getbuffer()
    if _storage_bytes(root) + len(payload) > MAX_EPHEMERAL_BYTES - 100_000_000:
        raise RuntimeError("checkpoint exceeds reserved disk budget; not written")
    _publish_checkpoint(root, destination, payload)
    return len(payload)


def _check_page_attributions(
    page: CompletedLaunchPage, results: tuple[LaunchAttributionResult, ...]
) -> None:
    page.__post_init__()
    if (
        len(results) != len(page.occurrences)
        or any(not isinstance(item, LaunchAttributionResult) for item in results)
        or tuple(item.paper_reference for item in results)
        != tuple(item.reference for item in page.occurrences)
        or any(item.version != LAUNCH_ATTRIBUTION_VERSION for item in results)
        or any(
            item.version != LAUNCH_INPUT_PROJECTION_VERSION for item in page.occurrences
        )
    ):
        raise ValueError("page checkpoint attribution inventory/version differs")


def _page_metadata(page: CompletedLaunchPage, payload: bytes) -> dict[str, object]:
    return {
        "format": PAGE_CHECKPOINT_VERSION,
        "planDigest": canonical_digest(page.plan),
        "year": page.plan.calendar_year,
        "page": page.request.page_number,
        "pageSize": page.request_page_size,
        "records": len(page.occurrences),
        "payloadBytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "projectionVersion": LAUNCH_INPUT_PROJECTION_VERSION,
        "attributionVersion": LAUNCH_ATTRIBUTION_VERSION,
    }


def _write_page_checkpoint(
    root: Path, page: CompletedLaunchPage, results: tuple[LaunchAttributionResult, ...]
) -> Path:
    """Publish one checksummed compact page atomically, without replacing lineage.

    The single-line JSON envelope describes the following gzip/pickle bytes.
    Only this owner's private working directory is a trusted pickle source.
    Checkpoints are temporary and never production artifacts or raw responses.
    """
    _check_page_attributions(page, results)
    destination = root / (
        f"source-{page.plan.calendar_year}-page-{page.request.page_number:05d}.checkpoint"
    )
    if destination.exists() or destination.is_symlink():
        raise ValueError("page checkpoint already exists; never overwrite")
    payload = gzip.compress(
        pickle.dumps((page, results), protocol=5), compresslevel=1, mtime=0
    )
    envelope = (
        json.dumps(_page_metadata(page, payload), sort_keys=True).encode() + b"\n"
    )
    size = len(envelope) + len(payload)
    if size > MAX_PAGE_CHECKPOINT_BYTES or (
        _storage_bytes(root) + size > MAX_EPHEMERAL_BYTES - 100_000_000
    ):
        raise RuntimeError("page checkpoint exceeds reserved disk budget; not written")
    _publish_checkpoint(root, destination, envelope, payload)
    return destination


def _load_page_checkpoints(
    root: Path, *, year: int, dataset_version: str, page_size: int
) -> tuple[tuple[CompletedLaunchPage, ...], tuple[LaunchAttributionResult, ...]]:
    pages: list[CompletedLaunchPage] = []
    results: list[LaunchAttributionResult] = []
    plan: BoundedLaunchSourcePlan | None = None
    for path in sorted(root.glob(f"source-{year}-page-*.checkpoint")):
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > MAX_PAGE_CHECKPOINT_BYTES
        ):
            raise ValueError("invalid local page checkpoint file")
        envelope, separator, payload = path.read_bytes().partition(b"\n")
        if not separator or len(envelope) > 4096:
            raise ValueError("invalid page checkpoint envelope")
        metadata = json.loads(envelope)
        if (
            not isinstance(metadata, dict)
            or metadata.get("format") != PAGE_CHECKPOINT_VERSION
            or metadata.get("payloadBytes") != len(payload)
            or metadata.get("sha256") != hashlib.sha256(payload).hexdigest()
        ):
            raise ValueError("page checkpoint checksum/format mismatch")
        # Integrity is checked BEFORE deserialization; never accept external files.
        with gzip.GzipFile(fileobj=BytesIO(payload), mode="rb") as stream:
            expanded = stream.read(MAX_PAGE_CHECKPOINT_BYTES * 8 + 1)
        if len(expanded) > MAX_PAGE_CHECKPOINT_BYTES * 8:
            raise ValueError("page checkpoint expansion exceeds its bound")
        saved = pickle.loads(expanded)  # noqa: S301 -- checksum-checked own local state
        if not isinstance(saved, tuple) or len(saved) != 2:
            raise ValueError("invalid compact page checkpoint")
        page, attributions = saved
        if not isinstance(page, CompletedLaunchPage) or not isinstance(
            attributions, tuple
        ):
            raise ValueError("invalid compact page checkpoint types")
        _check_page_attributions(page, attributions)
        expected = bounded_launch_source_plan(
            calendar_year=year, cutoff=page.plan.cutoff, dataset_version=dataset_version
        )
        number = len(pages) + 1
        if (
            page.plan != expected
            or (plan is not None and page.plan != plan)
            or page.request_page_size != page_size
            or page.request.page_number != number
            or path.name != f"source-{year}-page-{number:05d}.checkpoint"
            or metadata != _page_metadata(page, payload)
        ):
            raise ValueError("incompatible or noncontiguous page checkpoint")
        plan = page.plan
        pages.append(page)
        results.extend(attributions)
    return tuple(pages), tuple(results)


def _coverage(results: list[LaunchAttributionResult]) -> dict[str, object]:
    canonical = sum(
        (
            sum(item.fractional.institution_weights().values(), Fraction(0))
            if item.fractional
            else Fraction(0)
            for item in results
        ),
        Fraction(0),
    )
    present = sum(
        (item.paper_time_affiliation_weight or Fraction(0) for item in results),
        Fraction(0),
    )
    return {
        "canonicalMass": float(canonical),
        "canonicalCoverage": float(canonical / len(results)) if results else None,
        "affiliationMass": float(present),
        "affiliationCoverage": float(present / len(results)) if results else None,
        "researcherStates": dict(Counter(item.researcher_state for item in results)),
        "unresolvedReasons": dict(
            sum(
                (Counter(dict(item.unresolved_reason_counts)) for item in results),
                start=Counter(),
            )
        ),
    }


class LaunchTransport:
    """Exact HTTPS origins, bounded responses, shared provider pacing and retries."""

    def __init__(self) -> None:
        self.client = httpx.Client(
            timeout=45,
            follow_redirects=False,
            headers={
                "User-Agent": "AtlasPhysicus/3.0.5 bounded-scientific-launch (+https://atlas.techecho.org)",
            },
        )
        self.locks = {host: Lock() for host in ("inspirehep.net", "api.ror.org")}
        self.last: dict[str, float] = {}
        self.stats: Counter[str] = Counter()
        self.receipts: list[dict[str, Any]] = []

    def fetch(self, uri: str) -> FetchedLaunchPage:
        parsed = urlsplit(uri)
        host = parsed.netloc
        if parsed.scheme != "https" or host not in self.locks:
            raise ValueError("unapproved launch provider origin")
        delay = 0.55 if host == "inspirehep.net" else 0.3
        for attempt in range(4):
            with self.locks[host]:
                time.sleep(max(0, self.last.get(host, 0) + delay - time.monotonic()))
                self.last[host] = time.monotonic()
            requested = datetime.now(UTC)
            try:
                with self.client.stream("GET", uri) as response:
                    status = response.status_code
                    if status == 429 or status >= 500:
                        self.stats[f"retry-{status}"] += 1
                        time.sleep(
                            min(
                                60,
                                max(6, float(response.headers.get("retry-after", 6)))
                                * (attempt + 1),
                            )
                        )
                        continue
                    response.raise_for_status()
                    chunks = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise ValueError("provider page exceeded the 8 MiB bound")
                        chunks.append(chunk)
                    payload = b"".join(chunks)
            except httpx.TransportError:
                if attempt == 3:
                    raise
                self.stats["transport-retry"] += 1
                time.sleep(6 * (attempt + 1))
                continue
            received = datetime.now(UTC)
            with self.locks[host]:
                self.stats[host] += 1
                self.stats["response-bytes"] += len(payload)
                self.stats["max-response-bytes"] = max(
                    self.stats["max-response-bytes"], len(payload)
                )
                self.receipts.append(
                    {
                        "uri": uri,
                        "requested": requested.isoformat(),
                        "received": received.isoformat(),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "bytes": len(payload),
                        "status": status,
                    }
                )
            return FetchedLaunchPage(uri, requested, received, payload)
        raise RuntimeError(
            "provider unavailable after bounded retries; not missing evidence"
        )


def collect(*, root: Path, years: tuple[int, ...], dataset_version: str) -> None:
    root = root.resolve(strict=True)
    if (
        not root.is_dir()
        or not root.name.startswith("atlas-live-launch.")
        or root.parent != Path("/private/tmp")
    ):
        raise ValueError("launch requires the explicit isolated ephemeral directory")
    receipt_name = (
        "acquisition-receipts-"
        + "-".join(map(str, years))
        + "-"
        + uuid4().hex
        + ".json"
    )
    receipt_path = root / receipt_name
    transport = LaunchTransport()
    connector = InspireConnector(
        transport,  # type: ignore[arg-type]
        "https://inspirehep.net/api",
        acquisition_scope=AcquisitionScope(
            "nuclear-physics-launch-v1",
            "(subject:Theory-Nucl or subject:Experiment-Nucl)",
            "(cat:nucl-th OR cat:nucl-ex)",
        ),
    )
    authority_cache: dict[
        tuple[str, str], tuple[SourceRecord, EvidenceReference] | None
    ] = {}
    match_cache: dict[str, FetchedLaunchPage] = {}
    grid_cache: dict[EvidenceReference, RORGridCrosswalkResult | None] = {}
    snapshot = "launch-authority:" + datetime.now(UTC).isoformat()
    executor = ThreadPoolExecutor(max_workers=4)

    def authority(
        provider: str, identifier: str
    ) -> tuple[SourceRecord, EvidenceReference] | None:
        key = provider, identifier
        if key in authority_cache:
            return authority_cache[key]
        uri = (
            f"https://inspirehep.net/api/institutions/{identifier}"
            if provider == "inspire"
            else f"https://api.ror.org/v2/organizations/{identifier}"
        )
        try:
            response = transport.fetch(uri)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 404:
                raise
            authority_cache[key] = None
            return None
        raw = json.loads(response.payload)
        if provider == "inspire":
            raw = raw["metadata"]
        record = SourceRecord(provider, identifier, raw)  # type: ignore[arg-type]
        reference = EvidenceReference(provider, identifier, record.checksum, snapshot)
        result = record, reference
        authority_cache[key] = result
        return result

    def raw_match(
        record: SourceRecord, reference: EvidenceReference, author: int, slot: int
    ) -> RORAffiliationMatchResult:
        text = record.raw["authors"][author]["raw_affiliations"][slot]["value"]
        uri = ror_affiliation_request_uri(text)
        response = match_cache.get(uri)
        if response is None:
            response = transport.fetch(uri)
            match_cache[uri] = response
        # Restore this exact response's authority before the immediate consumer;
        # another query may have returned a later version of the same ROR record.
        for item in json.loads(response.payload)["items"]:
            organization = item["organization"]
            identifier = organization["id"].removeprefix("https://ror.org/")
            ror_record = SourceRecord("ror", identifier, organization)
            authority_cache[("ror", identifier)] = (
                ror_record,
                EvidenceReference("ror", identifier, ror_record.checksum, snapshot),
            )
        return certify_paper_raw_affiliation_match(
            paper_record=record,
            paper_reference=reference,
            author_index=author,
            raw_affiliation_index=slot,
            request_uri=uri,
            response_payload=response.payload,
            response_reference=EvidenceReference(
                "ror",
                ror_affiliation_reference_id(text),
                hashlib.sha256(response.payload).hexdigest(),
                snapshot,
            ),
            requested_at=response.requested_at,
            received_at=response.received_at,
            http_status=200,
        )

    def grid_match(
        record: SourceRecord, reference: EvidenceReference
    ) -> RORGridCrosswalkResult | None:
        if reference in grid_cache:
            return grid_cache[reference]
        grid = inspire_grid_id(record)
        if grid is None:
            return None
        uri = ror_grid_request_uri(grid)
        response = transport.fetch(uri)
        result = capture_ror_grid_crosswalk(
            institution_record=record,
            institution_reference=reference,
            response_payload=response.payload,
            request_uri=uri,
            requested_at=response.requested_at,
            received_at=response.received_at,
            source_snapshot_id=snapshot,
        )
        grid_cache[reference] = result
        return result

    try:
        for year in years:
            destination = root / f"source-{year}.pickle.gz"
            if destination.exists():
                raise ValueError(
                    "refusing to overwrite an existing acquired checkpoint"
                )
            if _storage_bytes(root) > MAX_EPHEMERAL_BYTES - 200_000_000:
                raise RuntimeError(
                    "insufficient disk headroom; stop before acquiring next year"
                )
            resume_pages, saved_results = _load_page_checkpoints(
                root, year=year, dataset_version=dataset_version, page_size=5
            )
            results = list(saved_results)
            del saved_results

            def process(
                record: SourceRecord,
                reference: EvidenceReference,
                collected: list[LaunchAttributionResult] = results,
            ) -> None:
                occurrence = capture_launch_occurrence(
                    record,
                    reference=reference,
                    connector=connector,
                    dataset_version=dataset_version,
                )
                collected.append(
                    attribute_launch_record(
                        record,
                        reference=reference,
                        source_facts=occurrence.source_facts,
                        institution_lookup=lambda identifier: authority(
                            "inspire", identifier
                        ),
                        ror_lookup=lambda identifier: authority("ror", identifier),
                        raw_match=raw_match,
                        grid_match=grid_match,
                    )
                )

            def fetch(uri: str) -> FetchedLaunchPage:
                response = transport.fetch(uri)
                # Prefetch only exact IDs on this page; no authority discovery corpus.
                payload = json.loads(response.payload)
                ids = set()
                raw_queries = set()
                for hit in payload["hits"]["hits"]:
                    for author in hit["metadata"].get("authors", []):
                        if not author.get("affiliations"):
                            for raw in author.get("raw_affiliations") or []:
                                value = raw.get("value")
                                if isinstance(value, str) and value.strip():
                                    raw_queries.add(ror_affiliation_request_uri(value))
                        for affiliation in author.get("affiliations", []):
                            link = affiliation.get("record", {}).get("$ref", "")
                            if link.startswith(
                                "https://inspirehep.net/api/institutions/"
                            ):
                                identifier = link.rsplit("/", 1)[-1]
                                if identifier.isdecimal():
                                    ids.add(identifier)
                list(
                    executor.map(
                        lambda identifier: authority("inspire", identifier), sorted(ids)
                    )
                )
                # The same bounded page's exact authority IDs and native text
                # may be fetched concurrently under the shared provider pacer.
                # No additional institution discovery query or corpus is used.
                ror_ids = set()
                for identifier in ids:
                    known = authority_cache.get(("inspire", identifier))
                    if known is None:
                        continue
                    for item in known[0].raw.get("external_system_identifiers") or []:
                        if str(item.get("schema", "")).casefold() != "ror":
                            continue
                        normalized = normalize_external_id("ror", item.get("value"))
                        if normalized is not None:
                            ror_ids.add(normalized[1])
                list(
                    executor.map(
                        lambda identifier: authority("ror", identifier), sorted(ror_ids)
                    )
                )

                def prefetch_raw(query: str) -> None:
                    if query not in match_cache:
                        match_cache[query] = transport.fetch(query)

                list(executor.map(prefetch_raw, sorted(raw_queries)))
                return response

            plan = (
                resume_pages[0].plan
                if resume_pages
                else bounded_launch_source_plan(
                    calendar_year=year,
                    cutoff=datetime.now(UTC),
                    dataset_version=dataset_version,
                )
            )

            def checkpoint(
                page: CompletedLaunchPage,
                collected: list[LaunchAttributionResult] = results,
            ) -> None:
                # Only the newly completed page, never a growing full-corpus graph.
                _write_page_checkpoint(
                    root, page, tuple(collected[-len(page.occurrences) :])
                )

            def progress(
                current: int,
                total: int,
                current_year: int = year,
                collected: list[LaunchAttributionResult] = results,
            ) -> None:
                if current % 50 == 0 or current == total:
                    print(
                        json.dumps(
                            {
                                "stage": "acquisition",
                                "year": current_year,
                                "records": current,
                                "total": total,
                                "authorities": len(authority_cache),
                                "rawQueries": len(match_cache),
                                "network": dict(transport.stats),
                                "coverage": _coverage(collected),
                            }
                        ),
                        flush=True,
                    )

            captured = collect_launch_year(
                plan,
                connector=connector,
                fetch=fetch,
                process_record=process,
                request_page_size=5,
                progress=progress,
                resume_pages=resume_pages,
                page_completed=checkpoint,
                resume_fetch=transport.fetch,
            )
            _write_checkpoint(root, destination, (captured, tuple(results)))
            stats: dict[str, Any] = {
                "year": year,
                "papers": len(results),
                "checkpointBytes": destination.stat().st_size,
                "network": dict(transport.stats),
            }
            stats.update(_coverage(results))
            print(json.dumps({"stage": "year-collected", **stats}), flush=True)
            (root / f"source-{year}-summary.json").write_text(
                json.dumps(stats, sort_keys=True), encoding="utf-8"
            )
            if _storage_bytes(root) >= MAX_EPHEMERAL_BYTES:
                raise RuntimeError(
                    "ephemeral storage budget reached; no further processing"
                )
            del results, captured
            gc.collect()
    finally:
        executor.shutdown(wait=True)
        transport.client.close()
        with receipt_path.open("x", encoding="utf-8") as stream:
            json.dump(transport.receipts, stream, separators=(",", ":"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ephemeral-root", type=Path, required=True)
    parser.add_argument(
        "--years", nargs="+", type=int, choices=range(2018, 2024), required=True
    )
    parser.add_argument("--dataset-version", required=True)
    args = parser.parse_args()
    collect(
        root=args.ephemeral_root,
        years=tuple(args.years),
        dataset_version=args.dataset_version,
    )
