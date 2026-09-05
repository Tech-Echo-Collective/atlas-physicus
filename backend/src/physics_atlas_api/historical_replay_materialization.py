"""Staging-safe, file-only materialization of a historical replay plan.

This boundary verifies an immutable approved historical acquisition, parses
its stored provider pages without network access, and writes a
content-addressed JSON evidence bundle outside the repository. It never imports
the database, touches provider cursors, calculates metrics, or selects
canonical cohort metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, cast
from urllib.parse import urlparse

from defusedxml import ElementTree as ET

from .attribution import (
    FRACTIONAL_ATTRIBUTION_V1,
    AuthorAttributionInput,
    PaperTimeAffiliationAssertion,
    calculate_fractional_attribution,
)
from .backfill import (
    HEP_TH_HISTORICAL_BACKFILL,
    HistoricalBackfillSpec,
    PartitionResult,
    build_partitions,
    load_resume_manifest,
    repository_root,
    resolve_historical_backfill_spec,
)
from .connectors.arxiv import ARXIV, ATOM, ArxivConnector
from .connectors.base import (
    NormalizedRecord,
    SourceRecord,
    SourceTransport,
    external_id,
    normalize_external_id,
)
from .connectors.inspire import InspireConnector
from .fields import (
    PHYSICS_FIELD_ONTOLOGY_VERSION,
    Provider,
    ProviderCategoryEvidence,
    ProviderCategoryRole,
    ProviderFieldProjection,
    reconcile_cross_provider_field_evidence,
)
from .historical_replay import (
    CANONICAL_PAPER_MERGE_POLICY_VERSION,
    PAPER_MERGE_PLAN_VERSION,
    BibliographicDateEvidence,
    CanonicalPaperComponent,
    CanonicalPaperMergePlan,
    PaperEvidenceOccurrence,
    StrongIdentifier,
    StrongIdentifierScheme,
    build_canonical_paper_merge_plan,
)
from .historical_ror import HISTORICAL_CANONICAL_INSTITUTION_VERSION

ReplayMode = Literal["plan", "execute"]

HISTORICAL_REPLAY_VERSION = "hep-th-v1-historical-replay-materialization-v1"
HISTORICAL_REPLAY_BUNDLE_VERSION = "hep-th-v1-historical-replay-bundle-v1"
HISTORICAL_RELATIONSHIP_PROJECTION_VERSION = (
    "hep-th-v1-historical-relationship-projection-v1"
)
CROSS_PROVIDER_AFFILIATION_PRECEDENCE_VERSION = (
    "cross-provider-affiliation-precedence-v1"
)
DIRECT_ROR_ALIGNMENT_VERSION = "direct-ror-affiliation-alignment-v1"


def _replay_versions(spec: HistoricalBackfillSpec) -> tuple[str, str, str]:
    if spec.id == HEP_TH_HISTORICAL_BACKFILL.id:
        return (
            HISTORICAL_REPLAY_VERSION,
            HISTORICAL_REPLAY_BUNDLE_VERSION,
            HISTORICAL_RELATIONSHIP_PROJECTION_VERSION,
        )
    return (
        f"{spec.id}-historical-replay-materialization-v2",
        f"{spec.id}-historical-replay-bundle-v2",
        f"{spec.id}-historical-relationship-projection-v2",
    )


def _canonical_institution_version(spec: HistoricalBackfillSpec) -> str:
    if spec.id == HEP_TH_HISTORICAL_BACKFILL.id:
        return HISTORICAL_CANONICAL_INSTITUTION_VERSION
    return f"{spec.id}-historical-canonical-institutions-v2"


class HistoricalReplaySafetyError(ValueError):
    """Raised before or during replay when immutable evidence cannot be proven."""


@dataclass(frozen=True, order=True)
class PageLineage:
    partition_id: str
    provider: Literal["inspire", "arxiv"]
    acquisition_year: int
    page_number: int
    page_path: str
    page_checksum: str
    query_version: str
    source_version: str

    def as_dict(self) -> dict[str, object]:
        return {
            "partition_id": self.partition_id,
            "provider": self.provider,
            "acquisition_year": self.acquisition_year,
            "page_number": self.page_number,
            "page_path": self.page_path,
            "page_checksum": self.page_checksum,
            "query_version": self.query_version,
            "source_version": self.source_version,
        }


@dataclass(frozen=True)
class VerifiedPaperOccurrence:
    evidence: PaperEvidenceOccurrence
    source_record_checksum: str
    provider_updated_at: str | None
    lineage: PageLineage
    authors: tuple[object, ...]
    category_evidence: tuple[ProviderCategoryEvidence, ...]
    journal_evidence: tuple[str, ...]
    document_type_evidence: tuple[str, ...]
    invalid_identifier_evidence: tuple[dict[str, str], ...]
    invalid_date_evidence: tuple[dict[str, str], ...]
    raw_citation_count: int | None
    non_self_citation_count: int | None

    def source_row(
        self,
        manifest_checksum: str,
        replay_version: str = HISTORICAL_REPLAY_VERSION,
    ) -> dict[str, object]:
        return {
            **self.evidence.as_dict(),
            "source_record_checksum": self.source_record_checksum,
            "provider_updated_at": self.provider_updated_at,
            "lineage": {
                **self.lineage.as_dict(),
                "source_manifest_checksum": manifest_checksum,
                "replay_version": replay_version,
            },
            "author_count": len(self.authors),
            "author_evidence_embedded": False,
            "author_evidence_reference": "immutable-page-lineage",
            "journal_evidence": list(self.journal_evidence),
            "document_type_evidence": list(self.document_type_evidence),
            "category_evidence": [
                {
                    "category": item.category,
                    "role": item.role,
                    "taxonomy": item.taxonomy,
                    "scheme": item.scheme,
                    "source": item.source,
                }
                for item in self.category_evidence
            ],
            "invalid_identifier_evidence": list(self.invalid_identifier_evidence),
            "invalid_date_evidence": list(self.invalid_date_evidence),
            "review_status": "unreviewed",
            "eligible_for_public_metrics": False,
        }


@dataclass(frozen=True)
class VerifiedHistoricalStaging:
    staging_root: Path
    source_manifest_path: Path
    source_manifest_checksum: str
    cutoff_timestamp: str
    occurrences: tuple[VerifiedPaperOccurrence, ...]
    verified_page_count: int
    provider_record_counts: tuple[tuple[str, int], ...]
    spec: HistoricalBackfillSpec
    replay_version: str
    bundle_version: str
    relationship_projection_version: str


@dataclass(frozen=True)
class ReplayArtifact:
    role: str
    relative_path: str
    checksum: str
    byte_count: int
    row_count: int | None
    content: bytes

    def manifest_entry(self) -> dict[str, object]:
        return {
            "role": self.role,
            "path": self.relative_path,
            "checksum": self.checksum,
            "byte_count": self.byte_count,
            "row_count": self.row_count,
        }


@dataclass(frozen=True)
class HistoricalReplayBundle:
    merge_plan: CanonicalPaperMergePlan
    artifacts: tuple[ReplayArtifact, ...]
    replay_digest: str
    report: dict[str, object]
    bundle_manifest: dict[str, object]


@dataclass(frozen=True)
class HistoricalReplayResult:
    mode: ReplayMode
    source_manifest_checksum: str
    replay_digest: str
    report: dict[str, object]
    bundle_manifest: dict[str, object]
    output_manifest_path: Path | None


class _NoNetworkTransport(SourceTransport):
    """Parser dependency that turns accidental provider access into a hard error."""

    is_fixture = False

    def close(self) -> None:
        return None

    def __enter__(self) -> _NoNetworkTransport:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del url, params, headers
        raise HistoricalReplaySafetyError("historical replay forbids network access")

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        del url, params, headers
        raise HistoricalReplaySafetyError("historical replay forbids network access")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _checksum_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _checksum_json(value: object) -> str:
    return _checksum_bytes(_canonical_json(value))


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _normalized_cutoff(value: object) -> str:
    if not isinstance(value, str):
        raise HistoricalReplaySafetyError("source manifest has no UTC cutoff")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise HistoricalReplaySafetyError(
            "source manifest cutoff is invalid"
        ) from error
    if parsed.tzinfo is None:
        raise HistoricalReplaySafetyError("source manifest cutoff lacks a timezone")
    return parsed.astimezone(UTC).isoformat()


def validate_replay_request(
    *,
    staging_root: Path,
    source_manifest: Path,
    output: Path | None,
    execute: bool,
    repo_root: Path | None = None,
) -> tuple[Path, Path, Path | None]:
    resolved_staging = staging_root.expanduser().resolve()
    resolved_manifest = source_manifest.expanduser().resolve()
    resolved_repository = (repo_root or repository_root()).resolve()
    if not resolved_staging.is_dir():
        raise HistoricalReplaySafetyError("staging root does not exist")
    if not _is_within(resolved_manifest, resolved_staging / "manifests"):
        raise HistoricalReplaySafetyError(
            "source manifest must belong to the staging manifest directory"
        )
    if not resolved_manifest.is_file():
        raise HistoricalReplaySafetyError("source manifest does not exist")
    if not execute:
        if output is not None:
            raise HistoricalReplaySafetyError(
                "plan mode does not accept an output path"
            )
        return resolved_staging, resolved_manifest, None
    if output is None:
        raise HistoricalReplaySafetyError("execute mode requires an output path")
    resolved_output = output.expanduser().resolve()
    if resolved_output == Path(resolved_output.anchor):
        raise HistoricalReplaySafetyError("filesystem root is not a replay output")
    if _is_within(resolved_output, resolved_repository):
        raise HistoricalReplaySafetyError(
            "historical replay output must remain outside the repository"
        )
    if _is_within(resolved_output, resolved_staging):
        raise HistoricalReplaySafetyError(
            "historical replay output must not modify the raw staging artifact"
        )
    return resolved_staging, resolved_manifest, resolved_output


def _page_path(
    staging_root: Path,
    partition: PartitionResult,
    page_path: str,
    page_checksum: str,
) -> Path:
    suffix = ".json" if partition.partition.provider == "inspire" else ".xml"
    expected = (
        Path("pages")
        / partition.partition.provider
        / str(partition.partition.year)
        / f"{page_checksum}{suffix}"
    )
    if Path(page_path) != expected:
        raise HistoricalReplaySafetyError(
            f"noncanonical staged page path for {partition.partition.id}"
        )
    resolved = (staging_root / page_path).resolve()
    if not _is_within(resolved, staging_root) or not resolved.is_file():
        raise HistoricalReplaySafetyError("staged page is missing or escapes staging")
    return resolved


def _date_fact(
    occurrence_id: str,
    kind: str,
    value: object,
) -> BibliographicDateEvidence | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", normalized):
        normalized = normalized[:10]
        precision: Literal["year", "month", "day"] = "day"
    elif re.fullmatch(r"\d{4}-\d{2}", normalized):
        precision = "month"
    elif re.fullmatch(r"\d{4}", normalized):
        precision = "year"
    else:
        return None
    try:
        return BibliographicDateEvidence(
            source_occurrence_id=occurrence_id,
            kind=kind,
            value=normalized,
            precision=precision,
        )
    except ValueError:
        return None


def _inspire_journal_evidence(raw: Mapping[str, Any]) -> tuple[str, ...]:
    values: set[str] = set()
    publication_info = raw.get("publication_info")
    if not isinstance(publication_info, list):
        return ()
    for item in publication_info:
        if not isinstance(item, Mapping):
            continue
        free_text = item.get("pubinfo_freetext")
        if isinstance(free_text, str) and free_text.strip():
            values.add(" ".join(free_text.split()))
            continue
        parts = [
            str(item[key]).strip()
            for key in (
                "journal_title",
                "journal_volume",
                "journal_issue",
                "artid",
                "page_start",
                "year",
            )
            if item.get(key) is not None and str(item[key]).strip()
        ]
        if parts:
            values.add(" ".join(parts))
    return tuple(sorted(values))


def _arxiv_journal_evidence(xml: str) -> dict[str, tuple[str, ...]]:
    root = ET.fromstring(xml)
    result: dict[str, tuple[str, ...]] = {}
    for entry in root.findall(f"{ATOM}entry"):
        identifier_element = entry.find(f"{ATOM}id")
        identifier = external_id(
            "arxiv",
            identifier_element.text if identifier_element is not None else None,
        )
        if identifier is None:
            continue
        values = {
            " ".join((item.text or "").split())
            for item in entry.findall(f"{ARXIV}journal_ref")
            if (item.text or "").strip()
        }
        result[identifier[1]] = tuple(sorted(values))
    return result


def _author_names(authors: object) -> tuple[str, ...]:
    if not isinstance(authors, list):
        return ()
    names: list[str] = []
    missing_name = False
    for author in authors:
        if isinstance(author, Mapping):
            value = (
                author.get("full_name")
                or author.get("full_name_unicode_normalized")
                or " ".join(
                    str(author.get(key, "")).strip()
                    for key in ("given", "family")
                    if author.get(key)
                )
                or author.get("name")
            )
        else:
            value = author
        name = str(value or "").strip()
        if name:
            names.append(name)
        else:
            missing_name = True
    return () if missing_name else tuple(names)


def _compact_author_evidence(authors: object) -> tuple[object, ...]:
    """Keep relationship facts only; immutable pages retain the full provider row."""

    if not isinstance(authors, list):
        return ()
    results: list[object] = []
    for item in authors:
        if not isinstance(item, Mapping):
            name = str(item).strip() if item is not None else ""
            results.append({"name": name} if name else {})
            continue
        author: dict[str, object] = {}
        for key in (
            "name",
            "full_name",
            "full_name_unicode_normalized",
            "given",
            "family",
            "recid",
            "record",
            "ORCID",
            "orcid",
            "ids",
            "affiliations_identifiers",
            "contribution",
            "contributions",
            "credit",
            "credit_roles",
            "corresponding",
        ):
            if item.get(key) is not None:
                author[key] = item[key]
        for key in ("affiliations", "raw_affiliations"):
            affiliations = item.get(key)
            if not isinstance(affiliations, list):
                continue
            compact_affiliations: list[object] = []
            for raw_affiliation in affiliations:
                if not isinstance(raw_affiliation, Mapping):
                    compact_affiliations.append({"value": str(raw_affiliation)})
                    continue
                compact_affiliation = {
                    field: raw_affiliation[field]
                    for field in (
                        "value",
                        "name",
                        "record",
                        "identifiers",
                        "external_ids",
                        "externalIds",
                    )
                    if raw_affiliation.get(field) is not None
                }
                compact_affiliations.append(compact_affiliation)
            author[key] = compact_affiliations
        results.append(author)
    return tuple(results)


def _valid_count(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HistoricalReplaySafetyError(f"provider returned invalid {label}")
    return value


def _strong_identifiers(
    record: SourceRecord,
    normalized: NormalizedRecord,
) -> tuple[tuple[StrongIdentifier, ...], tuple[dict[str, str], ...]]:
    candidates: list[tuple[str, object]] = list(normalized.external_ids)
    if record.provider == "inspire":
        candidates.append(("inspire", record.source_record_id))
        for item in record.raw.get("arxiv_eprints") or []:
            if isinstance(item, Mapping):
                candidates.append(("arxiv", item.get("value")))
        for item in record.raw.get("dois") or []:
            candidates.append(
                ("doi", item.get("value") if isinstance(item, Mapping) else item)
            )
    else:
        candidates.extend(
            (
                ("arxiv", record.source_record_id),
                ("doi", record.raw.get("doi")),
            )
        )

    identifiers: set[StrongIdentifier] = set()
    invalid: list[dict[str, str]] = []
    for scheme, raw_value in candidates:
        if scheme not in {"doi", "arxiv", "inspire"} or raw_value is None:
            continue
        try:
            identifiers.add(
                StrongIdentifier(cast(StrongIdentifierScheme, scheme), str(raw_value))
            )
        except ValueError:
            invalid.append({"scheme": scheme, "value": str(raw_value)})
    return tuple(sorted(identifiers)), tuple(
        sorted(invalid, key=lambda item: (item["scheme"], item["value"]))
    )


def _dates_for_record(
    occurrence_id: str,
    record: SourceRecord,
) -> tuple[
    tuple[BibliographicDateEvidence, ...],
    tuple[dict[str, str], ...],
]:
    candidates: list[tuple[str, object]] = []
    if record.provider == "inspire":
        for item in record.raw.get("imprints") or []:
            if isinstance(item, Mapping):
                candidates.append(("formal-publication", item.get("date")))
        for item in record.raw.get("publication_info") or []:
            if isinstance(item, Mapping) and item.get("year") is not None:
                candidates.append(("formal-publication", str(item["year"])))
        candidates.extend(
            (
                ("preprint-submission", record.raw.get("preprint_date")),
                ("provider-earliest", record.raw.get("earliest_date")),
            )
        )
    else:
        candidates.extend(
            (
                ("preprint-submission", record.raw.get("published")),
                ("provider-update", record.raw.get("updated")),
            )
        )

    facts: set[BibliographicDateEvidence] = set()
    invalid: list[dict[str, str]] = []
    for kind, raw_value in candidates:
        if raw_value is None:
            continue
        fact = _date_fact(occurrence_id, kind, raw_value)
        if fact is None:
            invalid.append({"kind": kind, "value": str(raw_value)})
        else:
            facts.add(fact)
    return tuple(sorted(facts)), tuple(
        sorted(invalid, key=lambda item: (item["kind"], item["value"]))
    )


def _category_evidence(
    normalized: NormalizedRecord,
) -> tuple[ProviderCategoryEvidence, ...]:
    raw_evidence = normalized.attributes.get("raw_category_evidence")
    results: list[ProviderCategoryEvidence] = []
    if isinstance(raw_evidence, list):
        for item in raw_evidence:
            if not isinstance(item, Mapping) or not isinstance(
                item.get("category"), str
            ):
                continue
            role_value = item.get("role", "unspecified")
            role: ProviderCategoryRole = (
                cast(ProviderCategoryRole, role_value)
                if role_value in {"primary", "secondary", "unspecified"}
                else "unspecified"
            )
            results.append(
                ProviderCategoryEvidence(
                    category=str(item["category"]),
                    role=role,
                    taxonomy=(
                        str(item["taxonomy"])
                        if item.get("taxonomy") is not None
                        else None
                    ),
                    scheme=(
                        str(item["scheme"]) if item.get("scheme") is not None else None
                    ),
                    source=(
                        str(item["source"]) if item.get("source") is not None else None
                    ),
                )
            )
    if not results:
        raw_categories = normalized.attributes.get("raw_categories")
        if isinstance(raw_categories, list):
            results.extend(
                ProviderCategoryEvidence(category=item)
                for item in raw_categories
                if isinstance(item, str) and item
            )
    return tuple(results)


def _document_type_evidence(
    record: SourceRecord,
    normalized: NormalizedRecord,
) -> tuple[str, ...]:
    raw_value = record.raw.get("document_type")
    candidates = list(raw_value) if isinstance(raw_value, list) else [raw_value]
    candidates.append(normalized.attributes.get("document_type"))
    return tuple(
        sorted(
            {
                " ".join(value.split())
                for value in candidates
                if isinstance(value, str) and value.strip()
            }
        )
    )


def _verified_occurrence(
    record: SourceRecord,
    normalized: NormalizedRecord,
    lineage: PageLineage,
    *,
    journal_evidence: tuple[str, ...],
) -> VerifiedPaperOccurrence:
    occurrence_id = f"{record.provider}:{record.source_record_id}"
    identifiers, invalid_identifiers = _strong_identifiers(record, normalized)
    dates, invalid_dates = _dates_for_record(occurrence_id, record)
    authors_value = normalized.attributes.get("authors")
    authors = _compact_author_evidence(authors_value)
    year_value = normalized.attributes.get("publication_year")
    year = (
        year_value
        if isinstance(year_value, int) and not isinstance(year_value, bool)
        else None
    )
    evidence = PaperEvidenceOccurrence(
        occurrence_id=occurrence_id,
        provider=record.provider,
        source_record_id=record.source_record_id,
        source_reference=(
            f"{lineage.page_path}#{record.provider}:{record.source_record_id}"
        ),
        identifiers=identifiers,
        title=str(normalized.attributes.get("title") or normalized.canonical_name),
        authors=_author_names(authors_value),
        year=year,
        journal=journal_evidence[0] if len(journal_evidence) == 1 else None,
        document_type=str(normalized.attributes.get("document_type") or "") or None,
        dates=dates,
    )
    return VerifiedPaperOccurrence(
        evidence=evidence,
        source_record_checksum=record.checksum,
        provider_updated_at=(
            record.updated_at.astimezone(UTC).isoformat()
            if record.updated_at is not None
            else None
        ),
        lineage=lineage,
        authors=authors,
        category_evidence=_category_evidence(normalized),
        journal_evidence=journal_evidence,
        document_type_evidence=_document_type_evidence(record, normalized),
        invalid_identifier_evidence=invalid_identifiers,
        invalid_date_evidence=invalid_dates,
        raw_citation_count=_valid_count(
            record.raw.get("citation_count"), "raw citation count"
        ),
        non_self_citation_count=_valid_count(
            record.raw.get("citation_count_without_self_citations"),
            "non-self citation count",
        ),
    )


def verify_historical_staging(
    staging_root: Path,
    source_manifest: Path,
) -> VerifiedHistoricalStaging:
    """Verify and parse the complete immutable staging artifact once."""

    try:
        manifest_value = json.loads(source_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoricalReplaySafetyError("source manifest cannot be read") from error
    if not isinstance(manifest_value, dict):
        raise HistoricalReplaySafetyError("source manifest is not an object")
    acquisition_scope = manifest_value.get("acquisition_scope")
    if not isinstance(acquisition_scope, str):
        raise HistoricalReplaySafetyError("source manifest has no acquisition scope")
    try:
        spec = resolve_historical_backfill_spec(acquisition_scope)
    except ValueError as error:
        raise HistoricalReplaySafetyError(
            "source manifest uses an unsupported historical scope"
        ) from error
    partitions = build_partitions(
        scope=spec.id,
        start_year=spec.years[0],
        end_year=spec.years[-1],
    )
    partition_results = load_resume_manifest(
        source_manifest,
        output=staging_root,
        partitions=partitions,
    )
    if (
        manifest_value.get("manifest_version") != spec.manifest_version
        or manifest_value.get("acquisition_scope") != spec.id
        or manifest_value.get("years") != list(spec.years)
        or manifest_value.get("acquisition_complete") is not True
    ):
        raise HistoricalReplaySafetyError(
            "source manifest is not the complete bounded historical acquisition"
        )
    manifest_checksum = manifest_value.get("manifest_checksum")
    if (
        not isinstance(manifest_checksum, str)
        or source_manifest.stem != manifest_checksum
    ):
        raise HistoricalReplaySafetyError("source manifest checksum identity failed")
    cutoff = _normalized_cutoff(manifest_value.get("created_at"))

    transport = _NoNetworkTransport()
    inspire = InspireConnector(
        transport,
        "https://inspirehep.net/api",
        acquisition_scope=spec.acquisition_scope,
    )
    arxiv = ArxivConnector(
        transport,
        "https://export.arxiv.org/api/query",
        acquisition_scope=spec.acquisition_scope,
    )
    occurrences: list[VerifiedPaperOccurrence] = []
    occurrence_ids: set[str] = set()
    provider_counts: dict[str, int] = {"inspire": 0, "arxiv": 0}
    verified_page_count = 0

    for partition in sorted(
        partition_results.values(),
        key=lambda item: (
            item.partition.provider,
            item.partition.year,
            item.partition.segment,
        ),
    ):
        if not partition.complete or partition.terminal_status != "complete":
            raise HistoricalReplaySafetyError(
                f"partition {partition.partition.id} is incomplete"
            )
        partition_ids: set[str] = set()
        records_seen = 0
        for page in sorted(partition.pages, key=lambda item: item.page_number):
            resolved_page = _page_path(
                staging_root,
                partition,
                page.path,
                page.checksum,
            )
            payload = resolved_page.read_bytes()
            if _checksum_bytes(payload) != page.checksum:
                raise HistoricalReplaySafetyError(
                    f"page checksum failed for {page.path}"
                )
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError as error:
                raise HistoricalReplaySafetyError(
                    f"page is not valid UTF-8: {page.path}"
                ) from error
            if partition.partition.provider == "inspire":
                try:
                    document = json.loads(text)
                except json.JSONDecodeError as error:
                    raise HistoricalReplaySafetyError(
                        f"INSPIRE page is invalid JSON: {page.path}"
                    ) from error
                if not isinstance(document, dict):
                    raise HistoricalReplaySafetyError("INSPIRE page is not an object")
                records = inspire._records(document)
                page_journals: dict[str, tuple[str, ...]] = {
                    record.source_record_id: _inspire_journal_evidence(record.raw)
                    for record in records
                }
                normalizer: InspireConnector | ArxivConnector = inspire
            else:
                records = arxiv._records(text)
                page_journals = _arxiv_journal_evidence(text)
                normalizer = arxiv
            if len(records) != page.record_count:
                raise HistoricalReplaySafetyError(
                    f"page record count failed for {page.path}"
                )
            lineage = PageLineage(
                partition_id=partition.partition.id,
                provider=partition.partition.provider,
                acquisition_year=partition.partition.year,
                page_number=page.page_number,
                page_path=page.path,
                page_checksum=page.checksum,
                query_version=partition.partition.query_version,
                source_version=partition.partition.source_version,
            )
            for record in records:
                occurrence_id = f"{record.provider}:{record.source_record_id}"
                if occurrence_id in occurrence_ids:
                    raise HistoricalReplaySafetyError(
                        f"duplicate source occurrence in replay: {occurrence_id}"
                    )
                occurrence_ids.add(occurrence_id)
                partition_ids.add(record.source_record_id)
                normalized = normalizer.normalize_record(record)
                occurrences.append(
                    _verified_occurrence(
                        record,
                        normalized,
                        lineage,
                        journal_evidence=page_journals.get(record.source_record_id, ()),
                    )
                )
                provider_counts[record.provider] += 1
            records_seen += len(records)
            verified_page_count += 1

        unique_checksum = hashlib.sha256(
            "\n".join(sorted(partition_ids)).encode()
        ).hexdigest()
        if (
            records_seen != partition.records_seen
            or len(partition_ids) != partition.seen_unique_ids
            or records_seen - len(partition_ids) != partition.duplicate_count
            or unique_checksum != partition.unique_ids_checksum
            or partition.expected_total != len(partition_ids)
        ):
            raise HistoricalReplaySafetyError(
                f"partition evidence failed verification: {partition.partition.id}"
            )

    replay_version, bundle_version, relationship_version = _replay_versions(spec)
    return VerifiedHistoricalStaging(
        staging_root=staging_root,
        source_manifest_path=source_manifest,
        source_manifest_checksum=manifest_checksum,
        cutoff_timestamp=cutoff,
        occurrences=tuple(
            sorted(occurrences, key=lambda item: item.evidence.occurrence_id)
        ),
        verified_page_count=verified_page_count,
        provider_record_counts=tuple(sorted(provider_counts.items())),
        spec=spec,
        replay_version=replay_version,
        bundle_version=bundle_version,
        relationship_projection_version=relationship_version,
    )


def _jsonl(rows: Iterable[dict[str, object]]) -> tuple[bytes, int]:
    rendered = [_canonical_json(row) for row in rows]
    return b"\n".join(rendered) + (b"\n" if rendered else b""), len(rendered)


def _artifact(
    role: str, directory: str, content: bytes, rows: int | None
) -> ReplayArtifact:
    checksum = _checksum_bytes(content)
    suffix = "jsonl" if rows is not None else "json"
    relative_path = f"{directory}/{checksum}.{suffix}"
    return ReplayArtifact(
        role=role,
        relative_path=relative_path,
        checksum=checksum,
        byte_count=len(content),
        row_count=rows,
        content=content,
    )


def _jsonl_artifact_metadata(
    role: str,
    directory: str,
    rows: Iterable[dict[str, object]],
) -> ReplayArtifact:
    hasher = hashlib.sha256()
    byte_count = 0
    row_count = 0
    for row in rows:
        payload = _canonical_json(row) + b"\n"
        hasher.update(payload)
        byte_count += len(payload)
        row_count += 1
    checksum = hasher.hexdigest()
    return ReplayArtifact(
        role=role,
        relative_path=f"{directory}/{checksum}.jsonl",
        checksum=checksum,
        byte_count=byte_count,
        row_count=row_count,
        content=b"",
    )


def _field_projection(item: VerifiedPaperOccurrence) -> ProviderFieldProjection:
    return ProviderFieldProjection(
        provider=cast(Provider, item.evidence.provider),
        source_record_id=item.evidence.source_record_id,
        categories=item.category_evidence,
        source_snapshot_id=item.lineage.page_checksum,
    )


@dataclass(frozen=True)
class _RelationshipRows:
    researcher_appearances: tuple[dict[str, object], ...]
    affiliation_shares: tuple[dict[str, object], ...]
    institution_anchors: tuple[dict[str, object], ...]
    attribution_ledgers: tuple[dict[str, object], ...]
    report: dict[str, object]


def _fraction_payload(value: Fraction) -> dict[str, int | str]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "exact": f"{value.numerator}/{value.denominator}",
    }


def _author_name(author: Mapping[str, object], position: int) -> str | None:
    name = (
        author.get("full_name")
        or author.get("full_name_unicode_normalized")
        or " ".join(
            str(author.get(key, "")).strip()
            for key in ("given", "family")
            if author.get(key)
        )
        or author.get("name")
    )
    del position
    normalized = " ".join(str(name or "").split())
    return normalized or None


def _inspire_reference_value(value: object, entity_segment: str) -> object:
    if not isinstance(value, str):
        return value
    parsed = urlparse(value)
    if parsed.scheme.casefold() not in {"http", "https"}:
        return value
    if (parsed.hostname or "").casefold().rstrip(".") != "inspirehep.net":
        return None
    segments = [item for item in parsed.path.split("/") if item]
    if len(segments) >= 2 and segments[-2].casefold() == entity_segment:
        return segments[-1]
    return None


def _researcher_identifiers(
    author: Mapping[str, object],
) -> tuple[
    tuple[tuple[str, str], ...],
    tuple[dict[str, str], ...],
]:
    candidates: list[tuple[str, object]] = []
    invalid: list[dict[str, str]] = []
    for key in ("ORCID", "orcid"):
        if author.get(key) is not None:
            candidates.append(("orcid", author[key]))
    if author.get("recid") is not None:
        candidates.append(("inspire-author", author["recid"]))
    record = author.get("record")
    if isinstance(record, Mapping) and record.get("$ref") is not None:
        reference = _inspire_reference_value(record["$ref"], "authors")
        if reference is None:
            invalid.append({"scheme": "inspire-author", "value": str(record["$ref"])})
        else:
            candidates.append(("inspire-author", reference))
    elif isinstance(record, str):
        reference = _inspire_reference_value(record, "authors")
        if reference is None:
            invalid.append({"scheme": "inspire-author", "value": record})
        else:
            candidates.append(("inspire-author", reference))
    identifiers = author.get("ids")
    if isinstance(identifiers, list):
        for item in identifiers:
            if not isinstance(item, Mapping) or item.get("value") is None:
                continue
            raw_scheme = str(item.get("schema") or item.get("scheme") or "")
            normalized_scheme = raw_scheme.strip().casefold()
            if normalized_scheme == "orcid":
                candidates.append(("orcid", item["value"]))
            elif normalized_scheme in {"inspire", "inspire-author"}:
                candidates.append(("inspire-author", item["value"]))
            elif normalized_scheme in {"inspire bai", "inspire-bai"}:
                candidates.append(("inspire-bai", item["value"]))

    valid: set[tuple[str, str]] = set()
    for scheme, value in candidates:
        identifier = normalize_external_id(scheme, value)
        if identifier is None:
            invalid.append({"scheme": scheme, "value": str(value)})
        else:
            valid.add(identifier)
    return tuple(sorted(valid)), tuple(
        sorted(invalid, key=lambda item: (item["scheme"], item["value"]))
    )


def _researcher_identity_candidate(
    identifiers: tuple[tuple[str, str], ...],
) -> tuple[str | None, str, tuple[str, ...]]:
    by_scheme: dict[str, set[str]] = {}
    for scheme, value in identifiers:
        by_scheme.setdefault(scheme, set()).add(value)
    conflicts = tuple(
        sorted(scheme for scheme, values in by_scheme.items() if len(values) > 1)
    )
    if conflicts:
        return None, "needs-review-conflicting-authority-identifiers", conflicts
    for scheme in ("orcid", "inspire-author", "inspire-bai"):
        values = sorted(by_scheme.get(scheme, ()))
        if values:
            identity = {"scheme": scheme, "value": values[0]}
            return (
                f"researcher-authority-candidate-{_checksum_json(identity)[:28]}",
                "unreviewed-authority-evidence",
                (),
            )
    return None, "unresolved-no-authority-identifier", ()


def _raw_affiliations(author: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    value = author.get("affiliations")
    if not isinstance(value, list) or not value:
        value = author.get("raw_affiliations")
    if not isinstance(value, list):
        return ()
    results: list[dict[str, object]] = []
    seen: set[bytes] = set()
    for item in value:
        affiliation = dict(item) if isinstance(item, Mapping) else {"value": str(item)}
        identity = _canonical_json(affiliation)
        if identity in seen:
            continue
        seen.add(identity)
        results.append(affiliation)
    return tuple(results)


def _ror_identifiers(
    groups: Iterable[object],
) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    valid: set[str] = set()
    invalid: list[dict[str, str]] = []
    for group in groups:
        if not isinstance(group, list):
            continue
        for item in group:
            if not isinstance(item, Mapping):
                continue
            scheme = str(item.get("schema") or item.get("scheme") or "")
            if scheme.strip().casefold() != "ror":
                continue
            raw_value = item.get("value")
            normalized = normalize_external_id("ror", raw_value)
            if normalized is None:
                invalid.append({"scheme": "ror", "value": str(raw_value)})
            else:
                valid.add(normalized[1])
    return tuple(sorted(valid)), tuple(sorted(invalid, key=lambda item: item["value"]))


def _provider_institution_identifiers(
    affiliation: Mapping[str, object],
) -> tuple[tuple[str, str], ...]:
    identifiers: set[tuple[str, str]] = set()
    record = affiliation.get("record")
    reference: object | None
    if isinstance(record, Mapping):
        reference = record.get("$ref")
    else:
        reference = record
    if reference is not None:
        normalized = normalize_external_id(
            "inspire-institution",
            _inspire_reference_value(reference, "institutions"),
        )
        if normalized is not None:
            identifiers.add(normalized)
    for key in ("identifiers", "external_ids", "externalIds"):
        values = affiliation.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, Mapping) or item.get("value") is None:
                continue
            raw_scheme = str(item.get("schema") or item.get("scheme") or "")
            scheme = raw_scheme.strip().casefold().replace(" ", "-")
            if scheme == "inspire":
                scheme = "inspire-institution"
            normalized = normalize_external_id(scheme, item["value"])
            if normalized is not None and normalized[0] in {
                "ror",
                "inspire-institution",
            }:
                identifiers.add(normalized)
    return tuple(sorted(identifiers))


def _select_relationship_occurrence(
    component: CanonicalPaperComponent,
    by_occurrence: Mapping[str, VerifiedPaperOccurrence],
) -> tuple[VerifiedPaperOccurrence | None, str]:
    candidates = [
        by_occurrence[item.occurrence_id]
        for item in component.occurrences
        if by_occurrence[item.occurrence_id].authors
    ]
    for provider in ("inspire", "arxiv"):
        provider_candidates = [
            item for item in candidates if item.evidence.provider == provider
        ]
        if len(provider_candidates) == 1:
            return provider_candidates[0], f"selected-{provider}-paper-time-evidence"
        if len(provider_candidates) > 1:
            return None, f"needs-review-multiple-{provider}-author-projections"
    return None, "unresolved-no-paper-time-author-evidence"


def _relationship_rows(
    merge_plan: CanonicalPaperMergePlan,
    by_occurrence: Mapping[str, VerifiedPaperOccurrence],
    staging: VerifiedHistoricalStaging,
) -> _RelationshipRows:
    relationship_version = staging.relationship_projection_version
    canonical_institution_version = _canonical_institution_version(staging.spec)
    appearances: list[dict[str, object]] = []
    shares: list[dict[str, object]] = []
    ledgers: list[dict[str, object]] = []
    anchor_evidence: dict[str, dict[str, object]] = {}
    share_status_counts: dict[str, int] = {}
    relationship_projection_counts: dict[str, int] = {}
    identity_status_counts: dict[str, int] = {}
    total_mass = Fraction(0)
    allocated_mass = Fraction(0)
    withheld_mass = Fraction(0)
    affiliation_evidence_mass = Fraction(0)
    no_affiliation_evidence_mass = Fraction(0)
    unmaterialized_mass = Fraction(0)
    direct_ror_alignment_count = 0

    for component in merge_plan.components:
        selected, selection_status = _select_relationship_occurrence(
            component, by_occurrence
        )
        relationship_projection_counts[selection_status] = (
            relationship_projection_counts.get(selection_status, 0) + 1
        )
        if selected is None:
            unmaterialized_mass += Fraction(1)
            ledgers.append(
                {
                    "candidate_id": component.candidate_id,
                    "canonical_id": component.canonical_id,
                    "paper_identity_status": component.status,
                    "projection_status": selection_status,
                    "selected_source_occurrence_id": None,
                    "author_count": None,
                    "share_count": 0,
                    "total_weight": _fraction_payload(Fraction(0)),
                    "allocated_weight": _fraction_payload(Fraction(0)),
                    "withheld_weight": _fraction_payload(Fraction(0)),
                    "affiliation_evidence_weight": _fraction_payload(Fraction(0)),
                    "no_affiliation_evidence_weight": _fraction_payload(Fraction(0)),
                    "unmaterialized_paper_mass": _fraction_payload(Fraction(1)),
                    "conservation_status": "not-evaluable-missing-author-projection",
                    "conservation_passed": False,
                    "policy_version": FRACTIONAL_ATTRIBUTION_V1.version,
                    "relationship_projection_version": relationship_version,
                    "eligible_for_public_metrics": False,
                }
            )
            continue

        author_inputs: list[AuthorAttributionInput] = []
        assertion_evidence: dict[str, dict[str, object]] = {}
        for position, raw_value in enumerate(selected.authors, start=1):
            author = (
                dict(raw_value)
                if isinstance(raw_value, Mapping)
                else {"name": str(raw_value)}
            )
            name = _author_name(author, position)
            researcher_ids, invalid_researcher_ids = _researcher_identifiers(author)
            researcher_candidate, identity_status, conflict_schemes = (
                _researcher_identity_candidate(researcher_ids)
            )
            identity_status_counts[identity_status] = (
                identity_status_counts.get(identity_status, 0) + 1
            )
            appearance_identity = {
                "candidate_id": component.candidate_id,
                "source_occurrence_id": selected.evidence.occurrence_id,
                "author_position": position,
            }
            appearance_id = (
                f"authorship-appearance-{_checksum_json(appearance_identity)[:28]}"
            )
            appearances.append(
                {
                    "authorship_appearance_id": appearance_id,
                    "candidate_id": component.candidate_id,
                    "canonical_paper_id": component.canonical_id,
                    "paper_identity_status": component.status,
                    "source_occurrence_id": selected.evidence.occurrence_id,
                    "provider": selected.evidence.provider,
                    "source_record_id": selected.evidence.source_record_id,
                    "author_position": position,
                    "raw_author_name": name,
                    "researcher_identity_candidate_id": researcher_candidate,
                    "canonical_researcher_id": None,
                    "identity_status": identity_status,
                    "authority_identifiers": [
                        {"scheme": scheme, "value": value}
                        for scheme, value in researcher_ids
                    ],
                    "conflict_schemes": list(conflict_schemes),
                    "invalid_identifier_evidence": list(invalid_researcher_ids),
                    "selected_projection_status": selection_status,
                    "source_manifest_checksum": staging.source_manifest_checksum,
                    "page_path": selected.lineage.page_path,
                    "page_checksum": selected.lineage.page_checksum,
                    "relationship_projection_version": relationship_version,
                    "eligible_for_public_metrics": False,
                }
            )

            affiliations = _raw_affiliations(author)
            author_rors, invalid_author_rors = _ror_identifiers(
                [author.get("affiliations_identifiers")]
            )
            assertions: list[PaperTimeAffiliationAssertion] = []
            for affiliation_index, affiliation in enumerate(affiliations, start=1):
                local_rors, invalid_local_rors = _ror_identifiers(
                    affiliation.get(key)
                    for key in ("identifiers", "external_ids", "externalIds")
                )
                aligned_ror: str | None = None
                resolution_status: Literal["unresolved", "ambiguous"] = "unresolved"
                alignment_status = "unresolved-no-direct-ror"
                if len(local_rors) == 1:
                    aligned_ror = local_rors[0]
                    alignment_status = "affiliation-local-ror-metadata-pending"
                elif len(local_rors) > 1:
                    resolution_status = "ambiguous"
                    alignment_status = "ambiguous-multiple-affiliation-local-rors"
                elif len(affiliations) == 1 and len(author_rors) == 1:
                    aligned_ror = author_rors[0]
                    alignment_status = "single-affiliation-author-ror-metadata-pending"
                elif len(affiliations) == 1 and len(author_rors) > 1:
                    resolution_status = "ambiguous"
                    alignment_status = "ambiguous-multiple-author-level-rors"
                elif len(affiliations) > 1 and author_rors:
                    alignment_status = (
                        "unresolved-author-level-rors-not-positionally-aligned"
                    )

                raw_name_value = affiliation.get("value") or affiliation.get("name")
                raw_name = (
                    " ".join(str(raw_name_value).split())
                    if raw_name_value is not None
                    else None
                )
                assertion_identity = {
                    "source_occurrence_id": selected.evidence.occurrence_id,
                    "author_position": position,
                    "affiliation_index": affiliation_index,
                    "raw_affiliation": affiliation,
                }
                assertion_id = (
                    f"paper-affiliation-assertion-"
                    f"{_checksum_json(assertion_identity)[:28]}"
                )
                assertion = PaperTimeAffiliationAssertion(
                    assertion_id=assertion_id,
                    resolution_status=resolution_status,
                    source=selected.evidence.provider,
                    source_record_id=selected.evidence.source_record_id,
                    evidence_version=relationship_version,
                )
                assertions.append(assertion)
                anchor_id = (
                    f"institution-authority-ror-{aligned_ror}"
                    if aligned_ror is not None
                    else None
                )
                if aligned_ror is not None and anchor_id is not None:
                    direct_ror_alignment_count += 1
                    anchor = anchor_evidence.setdefault(
                        anchor_id,
                        {
                            "institution_authority_anchor_id": anchor_id,
                            "authority_identifier": {
                                "scheme": "ror",
                                "value": aligned_ror,
                            },
                            "canonical_institution_id": None,
                            "metadata_status": "metadata-pending",
                            "required_authority_bundle_version": (
                                canonical_institution_version
                            ),
                            "source_assertion_ids": set(),
                            "source_occurrence_ids": set(),
                            "relationship_projection_version": relationship_version,
                            "eligible_for_public_metrics": False,
                        },
                    )
                    cast(set[str], anchor["source_assertion_ids"]).add(assertion_id)
                    cast(set[str], anchor["source_occurrence_ids"]).add(
                        selected.evidence.occurrence_id
                    )
                assertion_evidence[assertion_id] = {
                    "raw_affiliation": raw_name,
                    "provider_institution_identifiers": [
                        {"scheme": scheme, "value": value}
                        for scheme, value in _provider_institution_identifiers(
                            affiliation
                        )
                    ],
                    "affiliation_local_ror_ids": list(local_rors),
                    "author_level_ror_ids": list(author_rors),
                    "invalid_ror_evidence": [
                        *invalid_local_rors,
                        *invalid_author_rors,
                    ],
                    "alignment_status": alignment_status,
                    "institution_authority_anchor_id": anchor_id,
                    "canonical_institution_id": None,
                    "country_id": None,
                }
            author_inputs.append(
                AuthorAttributionInput(
                    author_slot_id=appearance_id,
                    author_position=position,
                    researcher_id=None,
                    affiliations=tuple(assertions),
                )
            )

        result = calculate_fractional_attribution(
            component.candidate_id,
            author_inputs,
        )
        total_mass += result.total_weight
        allocated_mass += result.allocated_weight
        withheld_mass += result.withheld_weight
        component_affiliation_evidence_mass = sum(
            (
                share.weight
                for share in result.shares
                if share.affiliation_assertion_ids
            ),
            start=Fraction(0),
        )
        component_no_affiliation_mass = sum(
            (
                share.weight
                for share in result.shares
                if not share.affiliation_assertion_ids
            ),
            start=Fraction(0),
        )
        affiliation_evidence_mass += component_affiliation_evidence_mass
        no_affiliation_evidence_mass += component_no_affiliation_mass
        for share in result.shares:
            share_status_counts[share.status] = (
                share_status_counts.get(share.status, 0) + 1
            )
            evidence_items = [
                assertion_evidence[assertion_id]
                for assertion_id in share.affiliation_assertion_ids
            ]
            affiliation_weight = share.weight / share.author_weight
            share_identity = {
                "candidate_id": component.candidate_id,
                "authorship_appearance_id": share.author_slot_id,
                "assertion_ids": list(share.affiliation_assertion_ids),
                "status": share.status,
            }
            shares.append(
                {
                    "paper_time_affiliation_share_id": (
                        f"paper-time-affiliation-share-"
                        f"{_checksum_json(share_identity)[:28]}"
                    ),
                    "candidate_id": component.candidate_id,
                    "canonical_paper_id": component.canonical_id,
                    "paper_identity_status": component.status,
                    "authorship_appearance_id": share.author_slot_id,
                    "author_position": share.author_position,
                    "affiliation_assertion_ids": list(share.affiliation_assertion_ids),
                    "raw_affiliations": [
                        item["raw_affiliation"] for item in evidence_items
                    ],
                    "institution_authority_anchor_ids": [
                        item["institution_authority_anchor_id"]
                        for item in evidence_items
                        if item["institution_authority_anchor_id"] is not None
                    ],
                    "canonical_institution_id": None,
                    "country_id": None,
                    "resolution_status": share.status,
                    "resolution_evidence": evidence_items,
                    "author_weight": _fraction_payload(share.author_weight),
                    "affiliation_weight": _fraction_payload(affiliation_weight),
                    "attribution_weight": _fraction_payload(share.weight),
                    "policy_id": FRACTIONAL_ATTRIBUTION_V1.policy_id,
                    "policy_version": FRACTIONAL_ATTRIBUTION_V1.version,
                    "direct_ror_alignment_version": DIRECT_ROR_ALIGNMENT_VERSION,
                    "affiliation_precedence_version": (
                        CROSS_PROVIDER_AFFILIATION_PRECEDENCE_VERSION
                    ),
                    "source_occurrence_id": selected.evidence.occurrence_id,
                    "page_path": selected.lineage.page_path,
                    "page_checksum": selected.lineage.page_checksum,
                    "source_manifest_checksum": staging.source_manifest_checksum,
                    "relationship_projection_version": relationship_version,
                    "eligible_for_public_metrics": False,
                }
            )

        ledgers.append(
            {
                "candidate_id": component.candidate_id,
                "canonical_id": component.canonical_id,
                "paper_identity_status": component.status,
                "projection_status": selection_status,
                "selected_source_occurrence_id": selected.evidence.occurrence_id,
                "author_count": len(author_inputs),
                "share_count": len(result.shares),
                "total_weight": _fraction_payload(result.total_weight),
                "allocated_weight": _fraction_payload(result.allocated_weight),
                "withheld_weight": _fraction_payload(result.withheld_weight),
                "affiliation_evidence_weight": _fraction_payload(
                    component_affiliation_evidence_mass
                ),
                "no_affiliation_evidence_weight": _fraction_payload(
                    component_no_affiliation_mass
                ),
                "unmaterialized_paper_mass": _fraction_payload(Fraction(0)),
                "conservation_status": "conserved",
                "conservation_passed": result.total_weight == Fraction(1),
                "policy_version": result.policy_version,
                "relationship_projection_version": relationship_version,
                "eligible_for_public_metrics": False,
            }
        )

    anchors = tuple(
        {
            **{
                key: value
                for key, value in anchor.items()
                if key not in {"source_assertion_ids", "source_occurrence_ids"}
            },
            "source_assertion_ids": sorted(
                cast(set[str], anchor["source_assertion_ids"])
            ),
            "source_occurrence_ids": sorted(
                cast(set[str], anchor["source_occurrence_ids"])
            ),
        }
        for _anchor_id, anchor in sorted(anchor_evidence.items())
    )
    expected_mass = Fraction(len(merge_plan.components))
    mass_conservation_passed = total_mass + unmaterialized_mass == expected_mass
    evidence_mass_conservation_passed = (
        affiliation_evidence_mass + no_affiliation_evidence_mass + unmaterialized_mass
        == expected_mass
    )
    unevaluable_ledger_count = sum(
        item["conservation_status"] == "not-evaluable-missing-author-projection"
        for item in ledgers
    )
    evaluated_conservation_failures = sum(
        item["conservation_status"] != "not-evaluable-missing-author-projection"
        and item["conservation_passed"] is not True
        for item in ledgers
    )
    return _RelationshipRows(
        researcher_appearances=tuple(
            sorted(appearances, key=lambda item: str(item["authorship_appearance_id"]))
        ),
        affiliation_shares=tuple(
            sorted(
                shares,
                key=lambda item: str(item["paper_time_affiliation_share_id"]),
            )
        ),
        institution_anchors=anchors,
        attribution_ledgers=tuple(
            sorted(ledgers, key=lambda item: str(item["candidate_id"]))
        ),
        report={
            "relationship_projection_version": relationship_version,
            "affiliation_precedence_version": (
                CROSS_PROVIDER_AFFILIATION_PRECEDENCE_VERSION
            ),
            "fractional_attribution_policy_version": (
                FRACTIONAL_ATTRIBUTION_V1.version
            ),
            "direct_ror_alignment_version": DIRECT_ROR_ALIGNMENT_VERSION,
            "researcher_appearance_count": len(appearances),
            "researcher_identity_status_counts": identity_status_counts,
            "paper_time_affiliation_share_count": len(shares),
            "affiliation_share_status_counts": share_status_counts,
            "institution_authority_anchor_count": len(anchors),
            "direct_ror_alignment_count": direct_ror_alignment_count,
            "relationship_projection_status_counts": (relationship_projection_counts),
            "evaluated_attribution_paper_mass": _fraction_payload(total_mass),
            "allocated_attribution_mass": _fraction_payload(allocated_mass),
            "withheld_attribution_mass": _fraction_payload(withheld_mass),
            "paper_time_affiliation_evidence_mass": _fraction_payload(
                affiliation_evidence_mass
            ),
            "paper_time_no_affiliation_evidence_mass": _fraction_payload(
                no_affiliation_evidence_mass
            ),
            "paper_time_affiliation_evidence_coverage": (
                float(affiliation_evidence_mass / expected_mass)
                if expected_mass
                else None
            ),
            "unmaterialized_paper_mass": _fraction_payload(unmaterialized_mass),
            "expected_paper_mass": _fraction_payload(expected_mass),
            "relationship_mass_conservation_passed": mass_conservation_passed,
            "affiliation_evidence_mass_conservation_passed": (
                evidence_mass_conservation_passed
            ),
            "attribution_conservation_failures": evaluated_conservation_failures,
            "evaluated_attribution_conservation_failures": (
                evaluated_conservation_failures
            ),
            "unevaluable_attribution_ledger_count": unevaluable_ledger_count,
            "unmaterialized_attribution_ledger_count": unevaluable_ledger_count,
            "canonical_researchers_materialized": 0,
            "canonical_institutions_materialized": 0,
        },
    )


def build_historical_replay_bundle(
    staging: VerifiedHistoricalStaging,
    *,
    artifact_sink: Callable[[ReplayArtifact], None] | None = None,
    row_artifact_sink: (
        Callable[
            [str, str, Iterable[dict[str, object]]],
            ReplayArtifact,
        ]
        | None
    ) = None,
    retain_artifact_content: bool = True,
) -> HistoricalReplayBundle:
    """Build deterministic JSON artifacts from already verified occurrences."""

    ordered_occurrences = tuple(
        sorted(staging.occurrences, key=lambda item: item.evidence.occurrence_id)
    )
    merge_plan = build_canonical_paper_merge_plan(
        item.evidence for item in ordered_occurrences
    )
    by_occurrence = {item.evidence.occurrence_id: item for item in ordered_occurrences}
    component_by_occurrence = {
        occurrence.occurrence_id: component
        for component in merge_plan.components
        for occurrence in component.occurrences
    }
    source_rows = [
        item.source_row(
            staging.source_manifest_checksum,
            staging.replay_version,
        )
        for item in ordered_occurrences
    ]
    component_rows: list[dict[str, object]] = []
    citation_rows: list[dict[str, object]] = []
    field_rows: list[dict[str, object]] = []
    field_conservation_failures = 0

    for component in merge_plan.components:
        lineage = [
            {
                "occurrence_id": occurrence.occurrence_id,
                **by_occurrence[occurrence.occurrence_id].lineage.as_dict(),
                "source_record_checksum": by_occurrence[
                    occurrence.occurrence_id
                ].source_record_checksum,
            }
            for occurrence in component.occurrences
        ]
        component_rows.append(
            {
                **component.as_dict(),
                "source_lineage": lineage,
                "document_type_evidence": [
                    {
                        "source_occurrence_id": occurrence.occurrence_id,
                        "values": list(
                            by_occurrence[
                                occurrence.occurrence_id
                            ].document_type_evidence
                        ),
                    }
                    for occurrence in component.occurrences
                ],
                "source_manifest_checksum": staging.source_manifest_checksum,
                "replay_version": staging.replay_version,
                "merge_policy_version": CANONICAL_PAPER_MERGE_POLICY_VERSION,
                "review_status": (
                    "needs_review"
                    if component.status == "needs_review"
                    else "unreviewed"
                ),
                "canonical_date_selected": False,
                "canonical_document_type_selected": False,
                "canonical_cohort_selected": False,
                "eligible_for_public_metrics": False,
            }
        )

        projections = tuple(
            _field_projection(by_occurrence[item.occurrence_id])
            for item in component.occurrences
        )
        ledger = reconcile_cross_provider_field_evidence(projections)
        assigned_mass = sum(item.weight for item in ledger.assignments)
        conservation_total = assigned_mass + ledger.unmapped_field_mass
        conservation_passed = abs(conservation_total - 1.0) <= 1e-12
        if not conservation_passed:
            field_conservation_failures += 1
        field_rows.append(
            {
                "candidate_id": component.candidate_id,
                "canonical_id": component.canonical_id,
                "paper_identity_status": component.status,
                "review_status": "unreviewed",
                "eligible_for_public_metrics": False,
                "assigned_field_mass": assigned_mass,
                "unmapped_field_mass": ledger.unmapped_field_mass,
                "conservation_total": conservation_total,
                "conservation_passed": conservation_passed,
                "source_occurrence_ids": [
                    item.occurrence_id for item in component.occurrences
                ],
                "source_manifest_checksum": staging.source_manifest_checksum,
                "replay_version": staging.replay_version,
                "field_ontology_version": PHYSICS_FIELD_ONTOLOGY_VERSION,
                "ledger": ledger.provenance_payload(),
            }
        )

    for item in ordered_occurrences:
        if item.raw_citation_count is None and item.non_self_citation_count is None:
            continue
        component = component_by_occurrence[item.evidence.occurrence_id]
        unsigned_observation: dict[str, object] = {
            "candidate_id": component.candidate_id,
            "canonical_id": component.canonical_id,
            "paper_identity_status": component.status,
            "source_occurrence_id": item.evidence.occurrence_id,
            "provider": item.evidence.provider,
            "source_record_id": item.evidence.source_record_id,
            "raw_citation_count": item.raw_citation_count,
            "non_self_citation_count": item.non_self_citation_count,
            "cutoff_timestamp": staging.cutoff_timestamp,
            "cutoff_semantics": "acquisition-manifest-completion-upper-bound",
            "page_capture_timestamp": None,
            "simultaneous_observation_claimed": False,
            "cutoff_note": (
                "The manifest completion timestamp is an acquisition upper bound; "
                "provider page capture timestamps were not recorded."
            ),
            "page_path": item.lineage.page_path,
            "page_checksum": item.lineage.page_checksum,
            "source_record_checksum": item.source_record_checksum,
            "source_manifest_checksum": staging.source_manifest_checksum,
            "replay_version": staging.replay_version,
            "evidence_status": "unreviewed-provider-count",
            "common_cutoff_comparable": False,
            "eligible_for_impact": False,
        }
        citation_rows.append(
            {
                "observation_id": (
                    f"citation-evidence-{_checksum_json(unsigned_observation)[:28]}"
                ),
                **unsigned_observation,
            }
        )

    multi_field_ledger_count = sum(
        len(
            cast(
                list[object],
                cast(dict[str, object], item["ledger"])["assignments"],
            )
        )
        > 1
        for item in field_rows
    )
    ledgers_with_unmapped_mass = sum(
        cast(float, item["unmapped_field_mass"]) > 0 for item in field_rows
    )
    total_assigned_field_mass = sum(
        cast(float, item["assigned_field_mass"]) for item in field_rows
    )
    total_unmapped_field_mass = sum(
        cast(float, item["unmapped_field_mass"]) for item in field_rows
    )

    citation_observation_count = len(citation_rows)
    field_ledger_count = len(field_rows)
    artifacts: list[ReplayArtifact] = []

    def add_jsonl_artifact(
        role: str,
        directory: str,
        rows: Iterable[dict[str, object]],
    ) -> None:
        if row_artifact_sink is not None:
            artifact = row_artifact_sink(role, directory, rows)
        elif retain_artifact_content or artifact_sink is not None:
            content, row_count = _jsonl(rows)
            artifact = _artifact(role, directory, content, row_count)
            if artifact_sink is not None:
                artifact_sink(artifact)
        else:
            artifact = _jsonl_artifact_metadata(role, directory, rows)
        artifacts.append(
            artifact if retain_artifact_content else replace(artifact, content=b"")
        )

    for role, directory, base_artifact_rows in (
        ("source-occurrences", "occurrences", source_rows),
        ("paper-components", "papers", component_rows),
        ("citation-observations", "citations", citation_rows),
        ("field-ledgers", "fields", field_rows),
    ):
        add_jsonl_artifact(role, directory, base_artifact_rows)
    del source_rows, component_rows, citation_rows, field_rows

    relationship_rows = _relationship_rows(merge_plan, by_occurrence, staging)
    for role, directory, relationship_artifact_rows in (
        (
            "researcher-appearances",
            "relationships/researchers",
            relationship_rows.researcher_appearances,
        ),
        (
            "paper-time-affiliation-shares",
            "relationships/affiliations",
            relationship_rows.affiliation_shares,
        ),
        (
            "institution-authority-anchors",
            "relationships/institutions",
            relationship_rows.institution_anchors,
        ),
        (
            "fractional-attribution-ledgers",
            "relationships/attribution",
            relationship_rows.attribution_ledgers,
        ),
    ):
        add_jsonl_artifact(role, directory, relationship_artifact_rows)
    relationship_report = relationship_rows.report
    del relationship_rows

    artifact_entries = [item.manifest_entry() for item in artifacts]
    replay_identity: dict[str, object] = {
        "bundle_version": staging.bundle_version,
        "replay_version": staging.replay_version,
        "source_manifest_checksum": staging.source_manifest_checksum,
        "acquisition_scope": staging.spec.id,
        "cutoff_timestamp": staging.cutoff_timestamp,
        "merge_plan_version": PAPER_MERGE_PLAN_VERSION,
        "merge_plan_digest": merge_plan.digest,
        "canonical_paper_merge_policy_version": (CANONICAL_PAPER_MERGE_POLICY_VERSION),
        "artifacts": artifact_entries,
    }
    replay_digest = _checksum_json(replay_identity)
    status_counts = {
        "matched": sum(item.status == "matched" for item in merge_plan.components),
        "needs_review": sum(
            item.status == "needs_review" for item in merge_plan.components
        ),
    }
    components_with_date_evidence = sum(
        bool(item.date_evidence) for item in merge_plan.components
    )
    date_kind_counts: dict[str, int] = {}
    date_precision_counts: dict[str, int] = {}
    for component in merge_plan.components:
        for fact in component.date_evidence:
            date_kind_counts[fact.kind] = date_kind_counts.get(fact.kind, 0) + 1
            date_precision_counts[fact.precision] = (
                date_precision_counts.get(fact.precision, 0) + 1
            )
    invalid_date_evidence_count = sum(
        len(item.invalid_date_evidence) for item in ordered_occurrences
    )
    merged_components = [
        item for item in merge_plan.components if len(item.occurrences) > 1
    ]
    provider_records_in_merged: dict[str, int] = {}
    provider_records_in_singletons: dict[str, int] = {}
    for component in merge_plan.components:
        destination = (
            provider_records_in_merged
            if len(component.occurrences) > 1
            else provider_records_in_singletons
        )
        for occurrence in component.occurrences:
            destination[occurrence.provider] = (
                destination.get(occurrence.provider, 0) + 1
            )
    components_with_raw_citation_evidence = {
        component_by_occurrence[item.evidence.occurrence_id].candidate_id
        for item in ordered_occurrences
        if item.raw_citation_count is not None
    }
    components_with_non_self_citation_evidence = {
        component_by_occurrence[item.evidence.occurrence_id].candidate_id
        for item in ordered_occurrences
        if item.non_self_citation_count is not None
    }
    source_occurrences_with_raw_citations = sum(
        item.raw_citation_count is not None for item in ordered_occurrences
    )
    source_occurrences_with_non_self_citations = sum(
        item.non_self_citation_count is not None for item in ordered_occurrences
    )
    report: dict[str, object] = {
        **replay_identity,
        "replay_digest": replay_digest,
        "provider_record_counts": dict(staging.provider_record_counts),
        "verified_page_count": staging.verified_page_count,
        "source_occurrence_count": len(ordered_occurrences),
        "paper_component_count": len(merge_plan.components),
        "paper_status_counts": status_counts,
        "merged_paper_component_count": len(merged_components),
        "singleton_paper_component_count": sum(
            len(item.occurrences) == 1 for item in merge_plan.components
        ),
        "cross_provider_paper_component_count": sum(
            len({occurrence.provider for occurrence in item.occurrences}) > 1
            for item in merge_plan.components
        ),
        "same_provider_merged_component_count": sum(
            len(item.occurrences) > 1
            and len({occurrence.provider for occurrence in item.occurrences}) == 1
            for item in merge_plan.components
        ),
        "provider_records_in_merged_components": provider_records_in_merged,
        "provider_records_in_singleton_components": provider_records_in_singletons,
        "components_with_valid_date_evidence": components_with_date_evidence,
        "components_without_valid_date_evidence": (
            len(merge_plan.components) - components_with_date_evidence
        ),
        "normalized_date_evidence_coverage": (
            components_with_date_evidence / len(merge_plan.components)
            if merge_plan.components
            else None
        ),
        "valid_date_evidence_count": sum(date_kind_counts.values()),
        "date_evidence_kind_counts": date_kind_counts,
        "date_evidence_precision_counts": date_precision_counts,
        "invalid_date_evidence_count": invalid_date_evidence_count,
        "citation_observation_count": citation_observation_count,
        "citation_cutoff_timestamp": staging.cutoff_timestamp,
        "citation_cutoff_semantics": ("acquisition-manifest-completion-upper-bound"),
        "citation_page_capture_timestamp_available": False,
        "citation_simultaneous_observation_claimed": False,
        "citation_cutoff_comparable_observation_count": 0,
        "citation_cutoff_comparable_observation_rate": (
            0.0 if citation_observation_count else None
        ),
        "mature_citation_cohort_count": 0,
        "citation_cohort_withholding_reason": (
            "Provider aggregate counts are bound to the replay cutoff, but the "
            "staging corpus has no historical observable-at-cutoff citation "
            "cohorts and no canonical cohort date has been selected."
        ),
        "raw_citation_count_coverage": source_occurrences_with_raw_citations,
        "non_self_citation_count_coverage": (
            source_occurrences_with_non_self_citations
        ),
        "source_occurrences_with_raw_citation_count": (
            source_occurrences_with_raw_citations
        ),
        "source_occurrence_raw_citation_coverage_rate": (
            source_occurrences_with_raw_citations / len(ordered_occurrences)
            if ordered_occurrences
            else None
        ),
        "source_occurrences_with_non_self_citation_count": (
            source_occurrences_with_non_self_citations
        ),
        "source_occurrence_non_self_citation_coverage_rate": (
            source_occurrences_with_non_self_citations / len(ordered_occurrences)
            if ordered_occurrences
            else None
        ),
        "canonical_components_with_raw_citation_evidence": len(
            components_with_raw_citation_evidence
        ),
        "canonical_component_raw_citation_coverage_rate": (
            len(components_with_raw_citation_evidence) / len(merge_plan.components)
            if merge_plan.components
            else None
        ),
        "canonical_components_with_non_self_citation_evidence": len(
            components_with_non_self_citation_evidence
        ),
        "canonical_component_non_self_citation_coverage_rate": (
            len(components_with_non_self_citation_evidence) / len(merge_plan.components)
            if merge_plan.components
            else None
        ),
        "field_ledger_count": field_ledger_count,
        "field_conservation_failures": field_conservation_failures,
        "multi_field_ledger_count": multi_field_ledger_count,
        "multi_field_ledger_rate": (
            multi_field_ledger_count / field_ledger_count
            if field_ledger_count
            else None
        ),
        "field_ledgers_with_unmapped_mass": ledgers_with_unmapped_mass,
        "field_ledgers_with_unmapped_mass_rate": (
            ledgers_with_unmapped_mass / field_ledger_count
            if field_ledger_count
            else None
        ),
        "total_assigned_field_mass": total_assigned_field_mass,
        "total_explicit_unmapped_field_mass": total_unmapped_field_mass,
        "field_ledger_review_status_counts": {
            "reviewed": 0,
            "needs_review": 0,
            "unreviewed": field_ledger_count,
        },
        "reviewed_field_ledger_coverage": 0.0 if field_ledger_count else None,
        "needs_review_field_ledger_coverage": 0.0 if field_ledger_count else None,
        "unreviewed_field_ledger_coverage": 1.0 if field_ledger_count else None,
        "reviewed_field_ledger_count": 0,
        "canonical_cohort_count": 0,
        "raw_acquisition_complete_years": list(staging.spec.years),
        "certified_complete_canonical_years": [],
        "momentum_window_readiness": {
            "2020-2022": False,
            "2023-2025": False,
        },
        "momentum_readiness_reason": (
            "Raw provider partitions are complete, but canonical cohort dates, "
            "reviewed paper-time attribution, and certified canonical-year "
            "completeness remain withheld."
        ),
        **relationship_report,
        "database_access": False,
        "source_cursor_access": False,
        "network_access": False,
        "metric_observations_created": 0,
    }
    report_content = (
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
        + b"\n"
    )
    report_artifact = _artifact("replay-report", "reports", report_content, None)
    if artifact_sink is not None:
        artifact_sink(report_artifact)
    if not retain_artifact_content:
        report_artifact = replace(report_artifact, content=b"")
    all_artifacts = (*artifacts, report_artifact)
    unsigned_bundle_manifest: dict[str, object] = {
        "bundle_version": staging.bundle_version,
        "replay_version": staging.replay_version,
        "source_manifest_checksum": staging.source_manifest_checksum,
        "source_manifest_path": staging.source_manifest_path.name,
        "acquisition_scope": staging.spec.id,
        "cutoff_timestamp": staging.cutoff_timestamp,
        "replay_digest": replay_digest,
        "canonical_paper_merge_policy_version": (CANONICAL_PAPER_MERGE_POLICY_VERSION),
        "merge_plan_version": PAPER_MERGE_PLAN_VERSION,
        "merge_plan_digest": merge_plan.digest,
        "artifacts": [item.manifest_entry() for item in all_artifacts],
        "database_access": False,
        "source_cursor_access": False,
        "network_access": False,
        "canonical_cohort_selected": False,
        "canonical_researchers_materialized": 0,
        "canonical_institutions_materialized": 0,
        "reviewed_field_ledgers": False,
        "metric_observations_created": 0,
    }
    bundle_manifest = {
        **unsigned_bundle_manifest,
        "bundle_manifest_checksum": _checksum_json(unsigned_bundle_manifest),
    }
    return HistoricalReplayBundle(
        merge_plan=merge_plan,
        artifacts=all_artifacts,
        replay_digest=replay_digest,
        report=report,
        bundle_manifest=bundle_manifest,
    )


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError as error:
        if path.read_bytes() != content:
            raise HistoricalReplaySafetyError(
                f"refusing to overwrite non-identical replay artifact: {path}"
            ) from error


def _verify_streamed_artifact(path: Path, artifact: ReplayArtifact) -> None:
    hasher = hashlib.sha256()
    byte_count = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                hasher.update(chunk)
                byte_count += len(chunk)
    except OSError as error:
        raise HistoricalReplaySafetyError(
            f"cannot verify existing replay artifact: {path}"
        ) from error
    if byte_count != artifact.byte_count or hasher.hexdigest() != artifact.checksum:
        raise HistoricalReplaySafetyError(
            f"refusing to overwrite non-identical replay artifact: {path}"
        )


def _write_jsonl_artifact_streaming(
    output: Path,
    role: str,
    directory: str,
    rows: Iterable[dict[str, object]],
) -> ReplayArtifact:
    """Hash then stream one re-iterable row set without retaining artifact bytes."""

    artifact = _jsonl_artifact_metadata(role, directory, rows)
    destination = output / artifact.relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            for row in rows:
                stream.write(_canonical_json(row) + b"\n")
    except FileExistsError:
        _verify_streamed_artifact(destination, artifact)
    else:
        _verify_streamed_artifact(destination, artifact)
    return artifact


def _write_bundle_manifest(output: Path, bundle: HistoricalReplayBundle) -> Path:
    manifest_content = (
        json.dumps(
            bundle.bundle_manifest,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    checksum = str(bundle.bundle_manifest["bundle_manifest_checksum"])
    destination = output / "manifests" / f"{checksum}.json"
    _write_immutable(destination, manifest_content)
    return destination


def materialize_historical_replay(
    *,
    staging_root: Path,
    source_manifest: Path,
    output: Path | None = None,
    execute: bool = False,
    repo_root: Path | None = None,
) -> HistoricalReplayResult:
    resolved_staging, resolved_manifest, resolved_output = validate_replay_request(
        staging_root=staging_root,
        source_manifest=source_manifest,
        output=output,
        execute=execute,
        repo_root=repo_root,
    )
    verified = verify_historical_staging(resolved_staging, resolved_manifest)
    artifact_sink: Callable[[ReplayArtifact], None] | None = None
    row_artifact_sink: (
        Callable[
            [str, str, Iterable[dict[str, object]]],
            ReplayArtifact,
        ]
        | None
    ) = None
    if execute and resolved_output is not None:

        def write_artifact(artifact: ReplayArtifact) -> None:
            _write_immutable(
                resolved_output / artifact.relative_path,
                artifact.content,
            )

        def write_row_artifact(
            role: str,
            directory: str,
            rows: Iterable[dict[str, object]],
        ) -> ReplayArtifact:
            return _write_jsonl_artifact_streaming(
                resolved_output,
                role,
                directory,
                rows,
            )

        artifact_sink = write_artifact
        row_artifact_sink = write_row_artifact
    bundle = build_historical_replay_bundle(
        verified,
        artifact_sink=artifact_sink,
        row_artifact_sink=row_artifact_sink,
        retain_artifact_content=False,
    )
    output_manifest = (
        _write_bundle_manifest(resolved_output, bundle)
        if execute and resolved_output is not None
        else None
    )
    return HistoricalReplayResult(
        mode="execute" if execute else "plan",
        source_manifest_checksum=verified.source_manifest_checksum,
        replay_digest=bundle.replay_digest,
        report=bundle.report,
        bundle_manifest=bundle.bundle_manifest,
        output_manifest_path=output_manifest,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute an offline, file-only canonical replay bundle; "
            "no database, cursors, metrics, or provider network are used"
        )
    )
    parser.add_argument("mode", choices=["plan", "execute"])
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="permit immutable evidence-bundle writes outside the repository",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.mode == "execute" and not args.execute:
        raise HistoricalReplaySafetyError(
            "execute mode requires the explicit --execute confirmation"
        )
    if args.mode == "plan" and args.execute:
        raise HistoricalReplaySafetyError("plan mode cannot receive --execute")
    result = materialize_historical_replay(
        staging_root=args.staging_root,
        source_manifest=args.source_manifest,
        output=args.output,
        execute=bool(args.execute),
    )
    payload: dict[str, object] = {
        "mode": result.mode,
        "source_manifest_checksum": result.source_manifest_checksum,
        "replay_digest": result.replay_digest,
        "report": result.report,
        "bundle_manifest": result.bundle_manifest,
    }
    if result.output_manifest_path is not None:
        payload["output_manifest_path"] = str(result.output_manifest_path)
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(run())
