import hashlib
import json
import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..attribution.materialization import (
    MaterializedAuthorIdentity,
    materialize_paper_time_affiliations,
)
from ..connectors.base import (
    NormalizedRecord,
    SourceConnector,
    SourceRecord,
    compact_ids,
    external_id,
)
from ..metrics.recomputation import (
    MetricRecalculationContract,
    MetricRecomputationPlanner,
    NoFormulaMetricRecalculator,
)
from ..search_index import refresh_search_terms

logger = logging.getLogger("physics_atlas_api.updates")


@dataclass(frozen=True)
class UpdateResult:
    run_id: str
    status: str
    source: str
    snapshot_id: str | None
    cursor_before: str | None
    cursor_after: str | None
    records_fetched: int
    records_added: int
    records_changed: int
    records_unresolved: int
    records_failed: int
    affected_partitions: int
    idempotent_replay: bool = False


@dataclass
class ChangeCounts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    unresolved: int = 0
    failed: int = 0


def _safe_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized[:120]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _publication_date(value: Any) -> tuple[date | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, None
    normalized = value.strip()[:10]
    try:
        if re.fullmatch(r"\d{4}", normalized):
            return date(int(normalized), 1, 1), "year"
        if re.fullmatch(r"\d{4}-\d{2}", normalized):
            year, month = (int(item) for item in normalized.split("-"))
            return date(year, month, 1), "month"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
            return date.fromisoformat(normalized), "day"
    except ValueError:
        return None, None
    return None, None


def _external_id_dicts(record: NormalizedRecord) -> list[dict[str, str]]:
    return [{"scheme": scheme, "value": value} for scheme, value in record.external_ids]


def _authority_schemes(kind: str) -> tuple[str, ...]:
    if kind == "institution":
        return ("ror",)
    if kind == "researcher":
        return ("orcid", "inspire-author")
    if kind == "paper":
        return ("doi", "arxiv", "inspire")
    return ()


def _has_authority_identifier(record: NormalizedRecord) -> bool:
    supported = _authority_schemes(record.kind)
    return any(scheme in supported and value for scheme, value in record.external_ids)


def _normalize_identity_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    normalized = ascii_value.casefold().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def _name_similarity(left: str, right: str) -> float:
    def bigrams(value: str) -> set[str]:
        compact = value.replace(" ", "")
        if len(compact) < 2:
            return {compact} if compact else set()
        return {compact[index : index + 2] for index in range(len(compact) - 1)}

    normalized_left = _normalize_identity_name(left)
    normalized_right = _normalize_identity_name(right)
    if normalized_left == normalized_right:
        return 1.0
    left_pairs = bigrams(normalized_left)
    right_pairs = bigrams(normalized_right)
    if not left_pairs or not right_pairs:
        return 0.0
    return (2 * len(left_pairs & right_pairs)) / (len(left_pairs) + len(right_pairs))


class IncrementalUpdateEngine:
    """Auditable, cursor-based, idempotent updater for changed provider records."""

    # These identify unchanged resolver/planner behavior, not the package release.
    resolver_version = "authority-gated-v3.0.4-alpha"
    calculation_version = "metric-partition-contract-v3.0.4-alpha"

    def __init__(
        self,
        session: Session,
        connector: SourceConnector,
        *,
        planner: MetricRecomputationPlanner | None = None,
        recalculator: MetricRecalculationContract | None = None,
    ):
        self.session = session
        self.connector = connector
        self.planner = planner or MetricRecomputationPlanner()
        self.recalculator = recalculator or NoFormulaMetricRecalculator()
        self.fixture_mode = bool(getattr(connector.transport, "is_fixture", False))

    def _new_run(self, cursor_before: str | None) -> models.UpdateRun:
        run = models.UpdateRun(
            id=f"update-run-{uuid.uuid4()}",
            source=self.connector.provider,
            status="running",
            started_at=datetime.now(UTC),
            cursor_before=cursor_before,
            cursor_after=cursor_before,
            affected_entities=[],
            affected_metric_partitions=[],
        )
        self.session.add(run)
        self.session.commit()
        return run

    def _fail_run(
        self,
        run_id: str,
        error: Exception,
        replay_checkpoint: dict[str, Any] | None = None,
    ) -> UpdateResult:
        self.session.rollback()
        run = self.session.get(models.UpdateRun, run_id)
        assert run is not None
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.records_failed = max(1, run.records_failed)
        run.error = f"{type(error).__name__}: {error}"[:4000]
        cursor = self.session.get(models.SourceCursor, self.connector.provider)
        if cursor is None:
            cursor = models.SourceCursor(
                source=self.connector.provider,
                scope_version=self.connector.cursor_scope,
                cursor=run.cursor_before,
                checkpoint={},
            )
            self.session.add(cursor)
        if replay_checkpoint is not None:
            cursor.checkpoint = dict(replay_checkpoint)
        cursor.last_attempt_at = run.finished_at
        cursor.consecutive_failures = (cursor.consecutive_failures or 0) + 1
        self.session.commit()
        logger.exception(
            "incremental update failed",
            extra={
                "event": "update.failed",
                "source": self.connector.provider,
                "run_id": run_id,
            },
        )
        return UpdateResult(
            run_id=run.id,
            status=run.status,
            source=run.source,
            snapshot_id=None,
            cursor_before=run.cursor_before,
            cursor_after=run.cursor_before,
            records_fetched=run.records_fetched,
            records_added=run.records_added,
            records_changed=run.records_changed,
            records_unresolved=run.records_unresolved,
            records_failed=run.records_failed,
            affected_partitions=0,
        )

    def run(self, *, limit: int = 100) -> UpdateResult:
        dataset_state = self.session.get(models.DatasetState, "current")
        if dataset_state is not None and dataset_state.dataset_kind != "live-api":
            raise RuntimeError(
                "Live ingestion cannot write into a synthetic or historical "
                "pilot dataset"
            )
        if dataset_state is not None:
            stored_fixture_mode = dataset_state.provenance_json.get("fixtureMode")
            if not isinstance(stored_fixture_mode, bool):
                raise RuntimeError(
                    "Live dataset provenance is missing its fixture-mode marker"
                )
            if stored_fixture_mode != self.fixture_mode:
                raise RuntimeError(
                    "Deterministic fixtures and provider-derived records cannot "
                    "be written into the same live dataset"
                )
            stored_dataset_scope = dataset_state.provenance_json.get("acquisitionScope")
            if not isinstance(stored_dataset_scope, str) or not stored_dataset_scope:
                raise RuntimeError(
                    "Live dataset provenance is missing its acquisition-scope marker; "
                    "migrate or replace the dataset explicitly before ingestion"
                )
            if stored_dataset_scope != self.connector.dataset_scope:
                raise RuntimeError(
                    "Configured acquisition scope cannot write into a live dataset "
                    f"created for a different scope: stored={stored_dataset_scope!r}, "
                    f"configured={self.connector.dataset_scope!r}"
                )
        cursor_state = self.session.get(models.SourceCursor, self.connector.provider)
        cursor_before = cursor_state.cursor if cursor_state else None
        run = self._new_run(cursor_before)
        replay_checkpoint: dict[str, Any] | None = None
        fetch_started = False
        try:
            if (
                cursor_state is not None
                and cursor_state.scope_version != self.connector.cursor_scope
            ):
                raise RuntimeError(
                    "Persisted source cursor scope does not match the configured "
                    f"acquisition scope for {self.connector.provider}: "
                    f"stored={cursor_state.scope_version!r}, "
                    f"configured={self.connector.cursor_scope!r}. "
                    "Reset or migrate the cursor explicitly before ingestion."
                )
            self.connector.set_checkpoint(
                cursor_state.checkpoint if cursor_state else {}
            )
            fetch_started = True
            batch = self.connector.fetch_updated_records(cursor_before, limit)
            replay_checkpoint = (
                dict(batch.replay_checkpoint)
                if batch.replay_checkpoint is not None
                else dict(cursor_state.checkpoint if cursor_state else {})
            )
            stored_run = self.session.get(models.UpdateRun, run.id)
            assert stored_run is not None
            run = stored_run
            run.records_fetched = len(batch.records)

            snapshot_payload = (
                list(batch.raw_payload)
                if batch.raw_payload
                else [record.raw for record in batch.records]
            )
            batch_checksum = _digest(
                json.dumps(
                    {
                        "acquisitionScope": self.connector.cursor_scope,
                        "payload": snapshot_payload,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            snapshot_id = f"snapshot-{self.connector.provider}-{batch_checksum[:24]}"
            snapshot = self.session.scalar(
                select(models.SourceSnapshot).where(
                    models.SourceSnapshot.source == self.connector.provider,
                    models.SourceSnapshot.content_checksum == batch_checksum,
                )
            )
            existing_update = None
            if snapshot:
                existing_update = self.session.scalar(
                    select(models.DatasetUpdate).where(
                        models.DatasetUpdate.source_snapshot_ids.contains([snapshot.id])
                    )
                )
            if snapshot and existing_update:
                self._complete_cursor(
                    cursor_state,
                    batch.next_cursor,
                    batch.checkpoint,
                    batch.fetched_at,
                )
                run.status = "succeeded"
                run.finished_at = datetime.now(UTC)
                run.cursor_after = batch.next_cursor
                run.records_added = 0
                run.records_changed = 0
                self.session.commit()
                return UpdateResult(
                    run.id,
                    run.status,
                    run.source,
                    snapshot.id,
                    cursor_before,
                    batch.next_cursor,
                    len(batch.records),
                    0,
                    0,
                    0,
                    0,
                    0,
                    True,
                )

            if snapshot is None:
                previous = self.session.scalar(
                    select(models.SourceSnapshot)
                    .where(models.SourceSnapshot.source == self.connector.provider)
                    .order_by(models.SourceSnapshot.captured_at.desc())
                    .limit(1)
                )
                snapshot = models.SourceSnapshot(
                    id=snapshot_id,
                    source=self.connector.provider,
                    source_version=self.connector.source_version,
                    captured_at=batch.fetched_at,
                    update_mode="incremental",
                    record_count=len(batch.records),
                    previous_snapshot_id=previous.id if previous else None,
                    content_checksum=batch_checksum,
                    storage_reference=f"database://source_snapshots/{snapshot_id}",
                    raw_payload=snapshot_payload,
                    provenance_json={
                        "source": (
                            f"deterministic {self.connector.provider} fixture"
                            if self.fixture_mode
                            else self.connector.source_version
                        ),
                        "sourceType": (
                            "synthetic-demo" if self.fixture_mode else "external-api"
                        ),
                        "version": self.connector.source_version,
                        "status": "synthetic" if self.fixture_mode else "unverified",
                        "retrievedAt": batch.fetched_at.isoformat(),
                        "acquisitionScope": self.connector.cursor_scope,
                    },
                )
                self.session.add(snapshot)

            dataset_version = (
                f"live-{batch.fetched_at.strftime('%Y%m%dT%H%M%SZ')}-{snapshot.id[-8:]}"
            )
            counts = ChangeCounts()
            normalized_with_ids: list[tuple[NormalizedRecord, str | None]] = []
            affected_entities: list[dict[str, str]] = []
            for source_record in batch.records:
                try:
                    normalized = self.connector.normalize_record(source_record)
                    canonical_id, outcome = self._apply_record(
                        source_record, normalized, snapshot.id, dataset_version
                    )
                    setattr(counts, outcome, getattr(counts, outcome) + 1)
                    normalized_with_ids.append((normalized, canonical_id))
                    if canonical_id:
                        affected_entities.append(
                            {"entityType": normalized.kind, "entityId": canonical_id}
                        )
                except (
                    Exception
                ):  # one malformed record must not erase the source checkpoint audit
                    logger.exception(
                        "source record failed",
                        extra={
                            "event": "update.record_failed",
                            "source": self.connector.provider,
                            "run_id": run.id,
                        },
                    )
                    counts.failed += 1

            if counts.failed:
                raise RuntimeError(
                    f"{counts.failed} source record(s) failed; cursor was not advanced"
                )

            partitions = self.planner.for_records(normalized_with_ids)
            self.recalculator.recalculate(
                self.session, partitions, dataset_version=dataset_version
            )
            update = models.DatasetUpdate(
                id=f"dataset-update-{snapshot.id[-32:]}",
                applied_at=datetime.now(UTC),
                update_mode="incremental",
                source_snapshot_ids=[snapshot.id],
                previous_dataset_version=self._current_dataset_version(),
                dataset_version=dataset_version,
                resolver_version=self.resolver_version,
                metric_calculation_version=self.calculation_version,
                changes={
                    "created": counts.created,
                    "updated": counts.updated,
                    "unchanged": counts.unchanged,
                    "unresolved": counts.unresolved,
                    "failed": counts.failed,
                },
                affected_entities=affected_entities,
                provenance_json={
                    "source": "Physics Atlas incremental update engine",
                    "sourceType": "derived",
                    "version": "v3.0.5-alpha",
                    "status": "unverified",
                    "acquisitionScope": self.connector.dataset_scope,
                },
            )
            self.session.add(update)
            self._update_dataset_state(update, snapshot)
            self._complete_cursor(
                cursor_state,
                batch.next_cursor,
                batch.checkpoint,
                batch.fetched_at,
            )

            run.status = "succeeded"
            run.finished_at = datetime.now(UTC)
            run.cursor_after = batch.next_cursor
            run.records_added = counts.created
            run.records_changed = counts.updated
            run.records_unresolved = counts.unresolved
            run.records_failed = counts.failed
            run.affected_entities = affected_entities
            run.affected_metric_partitions = [
                item.as_dict() for item in sorted(partitions)
            ]
            self.session.commit()
            logger.info(
                "incremental update succeeded",
                extra={
                    "event": "update.succeeded",
                    "source": self.connector.provider,
                    "run_id": run.id,
                    "records": len(batch.records),
                },
            )
            return UpdateResult(
                run.id,
                run.status,
                run.source,
                snapshot.id,
                cursor_before,
                batch.next_cursor,
                len(batch.records),
                counts.created,
                counts.updated,
                counts.unresolved,
                counts.failed,
                len(partitions),
            )
        except Exception as error:
            if replay_checkpoint is None and fetch_started:
                replay_checkpoint = self.connector.get_replay_checkpoint()
                if replay_checkpoint is None:
                    replay_checkpoint = dict(
                        cursor_state.checkpoint if cursor_state else {}
                    )
            return self._fail_run(run.id, error, replay_checkpoint)

    def _current_dataset_version(self) -> str | None:
        state = self.session.get(models.DatasetState, "current")
        return state.provenance_json.get("version") if state else None

    def _complete_cursor(
        self,
        cursor_state: models.SourceCursor | None,
        next_cursor: str | None,
        checkpoint: dict[str, object],
        attempted_at: datetime,
    ) -> None:
        state = cursor_state or self.session.get(
            models.SourceCursor, self.connector.provider
        )
        if state is None:
            state = models.SourceCursor(
                source=self.connector.provider,
                scope_version=self.connector.cursor_scope,
                cursor=next_cursor,
                checkpoint={},
            )
            self.session.add(state)
        elif state.scope_version != self.connector.cursor_scope:
            raise RuntimeError(
                "Refusing to advance a source cursor for a different acquisition scope"
            )
        state.scope_version = self.connector.cursor_scope
        state.cursor = next_cursor
        state.checkpoint = checkpoint
        state.last_attempt_at = attempted_at
        state.last_success_at = attempted_at
        state.consecutive_failures = 0

    def _update_dataset_state(
        self, update: models.DatasetUpdate, snapshot: models.SourceSnapshot
    ) -> None:
        state = self.session.get(models.DatasetState, "current")
        if state is None:
            state = models.DatasetState(
                id="current",
                schema_version="3.0.5-alpha",
                dataset_kind="live-api",
                period=str(datetime.now(UTC).year),
                generated_at=update.applied_at,
                latest_update_at=update.applied_at,
                source_snapshot_ids=[snapshot.id],
                update_sequence=1,
                disclaimer=(
                    "Deterministic connector fixture data for development only."
                    if self.fixture_mode
                    else (
                        "Continuously refreshed source metadata; coverage is "
                        "incomplete and the Atlas is not a ranking system."
                    )
                ),
                provenance_json={
                    "source": (
                        "Physics Atlas deterministic connector fixtures"
                        if self.fixture_mode
                        else "Physics Atlas live-data service"
                    ),
                    "sourceType": (
                        "synthetic-demo" if self.fixture_mode else "derived"
                    ),
                    "version": update.dataset_version,
                    "status": "synthetic" if self.fixture_mode else "unverified",
                    "fixtureMode": self.fixture_mode,
                    "acquisitionScope": self.connector.dataset_scope,
                },
            )
            self.session.add(state)
            return
        state.latest_update_at = update.applied_at
        state.source_snapshot_ids = list(
            dict.fromkeys([*state.source_snapshot_ids, snapshot.id])
        )
        state.update_sequence += 1
        state.provenance_json = {
            **state.provenance_json,
            "version": update.dataset_version,
        }

    def _apply_record(
        self,
        source_record: SourceRecord,
        normalized: NormalizedRecord,
        snapshot_id: str,
        dataset_version: str,
    ) -> tuple[str | None, str]:
        canonical_external_ids = compact_ids(
            *(external_id(scheme, value) for scheme, value in normalized.external_ids)
        )
        normalized = replace(
            normalized,
            external_ids=canonical_external_ids,
            provenance={
                **normalized.provenance,
                **(
                    {
                        "source": f"deterministic {normalized.provider} fixture",
                        "sourceType": "synthetic-demo",
                        "status": "synthetic",
                    }
                    if self.fixture_mode
                    else {}
                ),
                "sourceSnapshotId": snapshot_id,
            },
        )
        raw_digest = _digest(source_record.checksum + snapshot_id)[:24]
        raw_id = f"raw-{normalized.provider}-{raw_digest}"
        raw = self.session.get(models.RawEntityRecord, raw_id)
        if raw is None:
            raw = models.RawEntityRecord(
                id=raw_id,
                entity_type=normalized.kind,
                source=normalized.provider,
                source_record_id=normalized.source_record_id,
                source_snapshot_id=snapshot_id,
                raw_name=normalized.canonical_name,
                external_ids=_external_id_dicts(normalized),
                attributes_json=normalized.attributes,
                raw_payload=normalized.raw,
                ingested_at=datetime.now(UTC),
                provenance_json={
                    **normalized.provenance,
                    "sourceSnapshotId": snapshot_id,
                },
            )
            self.session.add(raw)
            self.session.flush()

        if normalized.kind == "paper":
            paper_id, outcome, conflict_evidence = self._upsert_paper(normalized)
            resolution_id = f"resolution-{raw.id}-{self.resolver_version}"
            if paper_id is None:
                conflict_candidates = sorted(
                    {
                        str(item["candidateEntityId"])
                        for item in conflict_evidence
                        if item.get("candidateEntityId")
                    }
                )
                is_conflict = bool(conflict_evidence)
                if self.session.get(models.IdentityResolution, resolution_id) is None:
                    self.session.add(
                        models.IdentityResolution(
                            id=resolution_id,
                            raw_entity_record_id=raw.id,
                            entity_type="paper",
                            status="ambiguous" if is_conflict else "unresolved",
                            canonical_entity_id=None,
                            method=(
                                "external-identifier"
                                if is_conflict
                                else "insufficient-metadata"
                            ),
                            confidence=1.0 if is_conflict else 0.0,
                            evidence=(
                                conflict_evidence
                                if is_conflict
                                else [
                                    {
                                        "method": "required-metadata",
                                        "inputValue": "publication_year",
                                        "score": 0.0,
                                        "reason": "missing-or-invalid",
                                    }
                                ]
                            ),
                            resolver_version=self.resolver_version,
                            resolved_at=datetime.now(UTC),
                            provenance_json={
                                "source": "Physics Atlas identity resolution",
                                "sourceType": "derived",
                                "version": self.resolver_version,
                                "status": "unverified",
                                "sourceSnapshotId": snapshot_id,
                            },
                        )
                    )
                review_id = f"review-{resolution_id}"
                if self.session.get(models.IdentityReview, review_id) is None:
                    self.session.add(
                        models.IdentityReview(
                            id=review_id,
                            resolution_id=resolution_id,
                            status="needs_review",
                            candidate_entity_ids=conflict_candidates,
                        )
                    )
                return None, "unresolved"
            if self.session.get(models.IdentityResolution, resolution_id) is None:
                authority_method = (
                    "external-identifier"
                    if normalized.external_ids
                    else "source-record-identifier"
                )
                self.session.add(
                    models.IdentityResolution(
                        id=resolution_id,
                        raw_entity_record_id=raw.id,
                        entity_type="paper",
                        status="matched",
                        canonical_entity_id=paper_id,
                        method=authority_method,
                        confidence=1.0,
                        evidence=[
                            {
                                "method": authority_method,
                                "inputValue": normalized.source_record_id,
                                "candidateEntityId": paper_id,
                                "score": 1.0,
                            }
                        ],
                        resolver_version=self.resolver_version,
                        resolved_at=datetime.now(UTC),
                        provenance_json={
                            "source": "Physics Atlas identity resolution",
                            "sourceType": "derived",
                            "version": self.resolver_version,
                            "status": "unverified",
                            "sourceSnapshotId": snapshot_id,
                        },
                    )
                )
            self._upsert_paper_relationships(
                normalized, paper_id, snapshot_id, dataset_version
            )
            return paper_id, outcome

        canonical_id, resolution_status, method, confidence, created, evidence = (
            self._resolve_identity(normalized)
        )
        resolution_id = f"resolution-{raw.id}-{self.resolver_version}"
        resolution = self.session.get(models.IdentityResolution, resolution_id)
        if resolution is None:
            resolution = models.IdentityResolution(
                id=resolution_id,
                raw_entity_record_id=raw.id,
                entity_type=normalized.kind,
                status=resolution_status,
                canonical_entity_id=canonical_id,
                method=method,
                confidence=confidence,
                evidence=evidence,
                resolver_version=self.resolver_version,
                resolved_at=datetime.now(UTC),
                provenance_json={
                    "source": "Physics Atlas identity resolution",
                    "sourceType": "derived",
                    "version": self.resolver_version,
                    "status": "unverified",
                },
            )
            self.session.add(resolution)
        if resolution_status != "matched":
            review_id = f"review-{resolution_id}"
            if self.session.get(models.IdentityReview, review_id) is None:
                self.session.add(
                    models.IdentityReview(
                        id=review_id,
                        resolution_id=resolution_id,
                        status="needs_review",
                        candidate_entity_ids=[
                            item.get("candidateEntityId")
                            for item in resolution.evidence
                            if item.get("candidateEntityId")
                        ],
                    )
                )
            return None, "unresolved"
        if canonical_id:
            self._upsert_resources(normalized, canonical_id)
            changed = (
                False
                if created
                else self._update_canonical_entity(normalized, canonical_id)
            )
            entity = (
                self.session.get(models.Institution, canonical_id)
                if normalized.kind == "institution"
                else self.session.get(models.Researcher, canonical_id)
            )
            if entity is not None:
                refresh_search_terms(
                    self.session,
                    entity_type=normalized.kind,
                    entity_id=canonical_id,
                    canonical_name=entity.canonical_name,
                    aliases=entity.aliases,
                    historical_names=entity.historical_names,
                    external_ids=entity.external_ids,
                )
        else:
            changed = False
        return (
            canonical_id,
            "created" if created else "updated" if changed else "unchanged",
        )

    def _resolve_identity(
        self, record: NormalizedRecord
    ) -> tuple[
        str | None,
        str,
        str | None,
        float,
        bool,
        list[dict[str, object]],
    ]:
        authority_matches: set[tuple[str, str]] = set()
        for scheme, value in record.external_ids:
            identifier = self.session.scalar(
                select(models.AuthorityIdentifier).where(
                    models.AuthorityIdentifier.scheme == scheme,
                    models.AuthorityIdentifier.value == value,
                )
            )
            if identifier:
                authority_matches.add((identifier.entity_type, identifier.entity_id))
        expected_type = record.kind
        valid_matches = {
            entity_id
            for entity_type, entity_id in authority_matches
            if entity_type == expected_type
        }
        if len(valid_matches) == 1:
            canonical_id = next(iter(valid_matches))
            return (
                canonical_id,
                "matched",
                "external-identifier",
                1.0,
                False,
                [
                    {
                        "method": "external-identifier",
                        "inputValue": ", ".join(
                            f"{scheme}:{value}" for scheme, value in record.external_ids
                        ),
                        "candidateEntityId": canonical_id,
                        "score": 1.0,
                    }
                ],
            )
        if len(valid_matches) > 1:
            evidence = [
                {
                    "method": "external-identifier",
                    "inputValue": record.canonical_name,
                    "candidateEntityId": entity_id,
                    "score": 1.0,
                }
                for entity_id in sorted(valid_matches)[:3]
            ]
            return None, "ambiguous", None, 1.0, False, evidence

        if record.attributes.get(
            "requires_authority"
        ) and not _has_authority_identifier(record):
            return None, "unresolved", None, 0.0, False, []

        normalized_name = _normalize_identity_name(record.canonical_name)
        exact_terms = [
            term
            for term in self.session.scalars(
                select(models.EntitySearchTerm).where(
                    models.EntitySearchTerm.entity_type == record.kind,
                    models.EntitySearchTerm.normalized_term == normalized_name,
                    models.EntitySearchTerm.match_method.in_(
                        ["canonical-name", "alias", "historical-name"]
                    ),
                )
            )
            if _normalize_identity_name(term.term) == normalized_name
        ]
        exact_by_entity: dict[str, models.EntitySearchTerm] = {}
        method_score = {
            "canonical-name": 0.99,
            "alias": 0.96,
            "historical-name": 0.9,
        }
        for term in exact_terms:
            current = exact_by_entity.get(term.entity_id)
            if (
                current is None
                or method_score[term.match_method] > method_score[current.match_method]
            ):
                exact_by_entity[term.entity_id] = term

        if record.kind == "institution" and len(exact_by_entity) > 1:
            country_code = record.attributes.get("country_code")
            if isinstance(country_code, str) and country_code:
                contextual_ids = set(
                    self.session.scalars(
                        select(models.Institution.id)
                        .join(
                            models.Country,
                            models.Country.id == models.Institution.country_id,
                        )
                        .where(
                            models.Institution.id.in_(exact_by_entity),
                            models.Country.iso_alpha2 == country_code.upper(),
                        )
                    )
                )
                if contextual_ids:
                    exact_by_entity = {
                        entity_id: term
                        for entity_id, term in exact_by_entity.items()
                        if entity_id in contextual_ids
                    }

        exact_evidence = [
            {
                "method": term.match_method,
                "inputValue": record.canonical_name,
                "candidateEntityId": entity_id,
                "canonicalValue": term.term,
                "score": method_score[term.match_method],
            }
            for entity_id, term in sorted(exact_by_entity.items())
        ]
        if len(exact_by_entity) == 1:
            canonical_id, exact_term = next(iter(exact_by_entity.items()))
            self._attach_authority_ids(record, canonical_id)
            return (
                canonical_id,
                "matched",
                exact_term.match_method,
                method_score[exact_term.match_method],
                False,
                exact_evidence,
            )
        if len(exact_by_entity) > 1:
            confidence = max(
                method_score[term.match_method] for term in exact_by_entity.values()
            )
            return (
                None,
                "ambiguous",
                None,
                confidence,
                False,
                exact_evidence[:3],
            )

        fuzzy_evidence: list[dict[str, object]] = []
        top_score = 0.0
        if normalized_name:
            fuzzy_terms = list(
                self.session.scalars(
                    select(models.EntitySearchTerm)
                    .where(
                        models.EntitySearchTerm.entity_type == record.kind,
                        models.EntitySearchTerm.match_method.in_(
                            ["canonical-name", "alias", "historical-name"]
                        ),
                        func.substr(models.EntitySearchTerm.normalized_term, 1, 1)
                        == normalized_name[0],
                    )
                    .limit(500)
                )
            )
            best_by_entity: dict[str, tuple[float, str]] = {}
            for term in fuzzy_terms:
                score = min(
                    0.89, _name_similarity(record.canonical_name, term.term) * 0.89
                )
                current_best = best_by_entity.get(term.entity_id)
                if current_best is None or score > current_best[0]:
                    best_by_entity[term.entity_id] = (score, term.term)
            ranked_fuzzy = [
                (entity_id, score, canonical_value)
                for entity_id, (score, canonical_value) in sorted(
                    best_by_entity.items(), key=lambda item: item[1][0], reverse=True
                )[:3]
            ]
            fuzzy_evidence = [
                {
                    "method": "fuzzy-name",
                    "inputValue": record.canonical_name,
                    "candidateEntityId": entity_id,
                    "canonicalValue": canonical_value,
                    "score": score,
                }
                for entity_id, score, canonical_value in ranked_fuzzy
            ]
            top_score = ranked_fuzzy[0][1] if ranked_fuzzy else 0.0
            second_score = ranked_fuzzy[1][1] if len(ranked_fuzzy) > 1 else 0.0
            if top_score >= 0.75:
                if len(fuzzy_evidence) > 1 and top_score - second_score < 0.05:
                    return None, "ambiguous", None, top_score, False, fuzzy_evidence
                canonical_id = ranked_fuzzy[0][0]
                self._attach_authority_ids(record, canonical_id)
                return (
                    canonical_id,
                    "matched",
                    "fuzzy-name",
                    top_score,
                    False,
                    fuzzy_evidence[:1],
                )

        authority_schemes = _authority_schemes(record.kind)
        authority_match = next(
            (
                (scheme, value)
                for scheme, value in record.external_ids
                if scheme in authority_schemes
            ),
            None,
        )
        authority_scheme, authority_value = authority_match or (None, None)
        if not authority_value:
            return None, "unresolved", None, top_score, False, fuzzy_evidence
        canonical_id = f"{record.kind}-{authority_scheme}-{_safe_id(authority_value)}"
        if record.kind == "institution":
            country_code = record.attributes.get("country_code")
            country = self.session.scalar(
                select(models.Country).where(models.Country.iso_alpha2 == country_code)
            )
            if country is None:
                return None, "unresolved", None, 0.0, False, []
            self.session.add(
                models.Institution(
                    id=canonical_id,
                    canonical_name=record.canonical_name,
                    aliases=record.attributes.get("aliases", []),
                    historical_names=[],
                    external_ids=_external_id_dicts(record),
                    identity_confidence=1.0,
                    country_id=country.id,
                    city=record.attributes.get("city") or "Unknown",
                    longitude=record.attributes.get("longitude"),
                    latitude=record.attributes.get("latitude"),
                    field_ids=[],
                    provenance_json=record.provenance,
                )
            )
        else:
            self.session.add(
                models.Researcher(
                    id=canonical_id,
                    canonical_name=record.canonical_name,
                    aliases=record.attributes.get("aliases", []),
                    historical_names=[],
                    external_ids=_external_id_dicts(record),
                    identity_confidence=1.0,
                    field_ids=[],
                    provenance_json=record.provenance,
                )
            )
        self.session.flush()
        self._attach_authority_ids(record, canonical_id)
        return (
            canonical_id,
            "matched",
            "external-identifier",
            1.0,
            True,
            [
                {
                    "method": "external-identifier",
                    "inputValue": f"{authority_scheme}:{authority_value}",
                    "candidateEntityId": canonical_id,
                    "score": 1.0,
                }
            ],
        )

    def _update_canonical_entity(
        self, record: NormalizedRecord, canonical_id: str
    ) -> bool:
        """Apply authority-backed metadata without changing relationship meaning."""
        if not _has_authority_identifier(record):
            return False
        entity: models.Institution | models.Researcher | None
        if record.kind == "institution":
            entity = self.session.get(models.Institution, canonical_id)
        elif record.kind == "researcher":
            entity = self.session.get(models.Researcher, canonical_id)
        else:
            return False
        if entity is None:
            return False

        changed = False
        if entity.canonical_name != record.canonical_name:
            entity.historical_names = list(
                dict.fromkeys([*entity.historical_names, entity.canonical_name])
            )
            entity.canonical_name = record.canonical_name
            changed = True
        aliases = list(
            dict.fromkeys([*entity.aliases, *record.attributes.get("aliases", [])])
        )
        external_ids = list(
            {
                (item["scheme"], item["value"]): item
                for item in [*entity.external_ids, *_external_id_dicts(record)]
            }.values()
        )
        if aliases != entity.aliases:
            entity.aliases = aliases
            changed = True
        if external_ids != entity.external_ids:
            entity.external_ids = external_ids
            changed = True

        if isinstance(entity, models.Institution):
            institution_updates = {
                "city": record.attributes.get("city"),
                "latitude": record.attributes.get("latitude"),
                "longitude": record.attributes.get("longitude"),
            }
            for attribute, value in institution_updates.items():
                if value is not None and getattr(entity, attribute) != value:
                    setattr(entity, attribute, value)
                    changed = True
        if changed:
            entity.provenance_json = record.provenance
        return changed

    def _upsert_paper_relationships(
        self,
        record: NormalizedRecord,
        paper_id: str,
        snapshot_id: str,
        dataset_version: str,
    ) -> None:
        """Resolve author identity, then preserve every paper-time affiliation slot."""
        raw_authors = record.attributes.get("authors", [])
        if not isinstance(raw_authors, list):
            return
        author_identities: dict[int, MaterializedAuthorIdentity] = {}
        for position, author in enumerate(raw_authors, start=1):
            raw_author = author if isinstance(author, dict) else {"name": str(author)}
            name = str(
                raw_author.get("full_name")
                or " ".join(
                    str(raw_author.get(key, "")).strip()
                    for key in ("given", "family")
                    if raw_author.get(key)
                )
                or raw_author.get("name")
                or f"Unnamed author {position}"
            ).strip()
            identifiers: list[tuple[str, str]] = []
            recid = raw_author.get("recid")
            if recid is not None:
                identifiers.append(("inspire-author", str(recid)))
            orcid_value = raw_author.get("ORCID") or raw_author.get("orcid")
            if orcid_value:
                identifiers.append(
                    ("orcid", str(orcid_value).rstrip("/").rsplit("/", 1)[-1])
                )
            for identifier in raw_author.get("ids", []):
                if not isinstance(identifier, dict) or not identifier.get("value"):
                    continue
                schema = str(identifier.get("schema", "")).casefold()
                if schema == "orcid":
                    identifiers.append(("orcid", str(identifier["value"])))
                elif schema in {"inspire bai", "inspire"}:
                    identifiers.append(("inspire-author", str(identifier["value"])))
            normalized_author = NormalizedRecord(
                provider=record.provider,
                kind="researcher",
                source_record_id=(f"{record.source_record_id}:author:{position}"),
                canonical_name=name,
                external_ids=tuple(dict.fromkeys(identifiers)),
                attributes={"aliases": [], "requires_authority": True},
                raw=raw_author,
                provenance=record.provenance,
                updated_at=record.updated_at,
            )
            source_author = SourceRecord(
                provider=record.provider,
                source_record_id=normalized_author.source_record_id,
                raw=raw_author,
                updated_at=record.updated_at,
            )
            researcher_id, _ = self._apply_record(
                source_author, normalized_author, snapshot_id, dataset_version
            )
            if researcher_id is None:
                author_identities[position] = MaterializedAuthorIdentity(
                    author_position=position,
                    raw_author_name=name,
                    researcher_id=None,
                    authorship_id=None,
                    resolution_status="unresolved",
                )
                continue
            authorship_id = f"authorship-{_digest(paper_id + researcher_id)[:24]}"
            authorship = self.session.get(models.Authorship, authorship_id)
            if authorship is None:
                self.session.add(
                    models.Authorship(
                        id=authorship_id,
                        paper_id=paper_id,
                        researcher_id=researcher_id,
                        author_position=position,
                        provenance_json=record.provenance,
                    )
                )
            else:
                authorship.author_position = position
                authorship.provenance_json = record.provenance
            author_identities[position] = MaterializedAuthorIdentity(
                author_position=position,
                raw_author_name=name,
                researcher_id=researcher_id,
                authorship_id=authorship_id,
                resolution_status="resolved",
            )
        if raw_authors:
            materialize_paper_time_affiliations(
                self.session,
                record=record,
                paper_id=paper_id,
                source_snapshot_id=snapshot_id,
                dataset_version=dataset_version,
                author_identities=author_identities,
            )

    def _attach_authority_ids(
        self, record: NormalizedRecord, canonical_id: str
    ) -> None:
        for scheme, value in record.external_ids:
            existing = self.session.scalar(
                select(models.AuthorityIdentifier).where(
                    models.AuthorityIdentifier.scheme == scheme,
                    models.AuthorityIdentifier.value == value,
                )
            )
            if existing is None:
                self.session.add(
                    models.AuthorityIdentifier(
                        id=f"authority-{scheme}-{_digest(value)[:20]}",
                        entity_type=record.kind,
                        entity_id=canonical_id,
                        scheme=scheme,
                        value=value,
                        is_authoritative=True,
                        provenance_json=record.provenance,
                    )
                )

    def _paper_candidates(
        self, record: NormalizedRecord
    ) -> dict[str, list[dict[str, object]]]:
        candidates: dict[str, list[dict[str, object]]] = {}

        def add_candidate(
            entity_id: str,
            *,
            method: str,
            input_value: str,
            canonical_value: str | None = None,
        ) -> None:
            if self.session.get(models.Paper, entity_id) is None:
                return
            evidence = {
                "method": method,
                "inputValue": input_value,
                "candidateEntityId": entity_id,
                "score": 1.0,
                **(
                    {"canonicalValue": canonical_value}
                    if canonical_value is not None
                    else {}
                ),
            }
            bucket = candidates.setdefault(entity_id, [])
            if evidence not in bucket:
                bucket.append(evidence)

        for scheme, value in record.external_ids:
            if scheme not in _authority_schemes("paper"):
                continue
            authority = self.session.scalar(
                select(models.AuthorityIdentifier).where(
                    models.AuthorityIdentifier.scheme == scheme,
                    models.AuthorityIdentifier.value == value,
                    models.AuthorityIdentifier.entity_type == "paper",
                )
            )
            if authority is not None:
                add_candidate(
                    authority.entity_id,
                    method="external-identifier",
                    input_value=f"{scheme}:{value}",
                    canonical_value=f"{scheme}:{value}",
                )

            direct_paper = None
            if scheme == "doi":
                direct_paper = self.session.scalar(
                    select(models.Paper).where(models.Paper.doi == value)
                )
            elif scheme == "arxiv":
                direct_paper = self.session.scalar(
                    select(models.Paper).where(models.Paper.arxiv_id == value)
                )
            if direct_paper is not None:
                add_candidate(
                    direct_paper.id,
                    method="external-identifier",
                    input_value=f"{scheme}:{value}",
                    canonical_value=f"{scheme}:{value}",
                )

        source_primary = f"{record.provider}-{record.source_record_id}"
        source_slug = _safe_id(source_primary)[:96] or "record"
        source_id = f"paper-{source_slug}-{_digest(source_primary)[:16]}"
        add_candidate(
            source_id,
            method="source-record-identifier",
            input_value=record.source_record_id,
        )
        return candidates

    def _upsert_paper(
        self, record: NormalizedRecord
    ) -> tuple[str | None, str, list[dict[str, object]]]:
        ids = dict(record.external_ids)
        candidates = self._paper_candidates(record)
        if len(candidates) > 1:
            return (
                None,
                "unresolved",
                [
                    evidence
                    for entity_id in sorted(candidates)
                    for evidence in candidates[entity_id]
                ],
            )
        paper = (
            self.session.get(models.Paper, next(iter(candidates)))
            if candidates
            else None
        )
        if paper is not None:
            identifier_conflicts = [
                {
                    "method": "external-identifier",
                    "inputValue": f"{scheme}:{incoming}",
                    "candidateEntityId": paper.id,
                    "canonicalValue": f"{scheme}:{current}",
                    "score": 0.0,
                }
                for scheme, current, incoming in (
                    ("doi", paper.doi, ids.get("doi")),
                    ("arxiv", paper.arxiv_id, ids.get("arxiv")),
                )
                if current and incoming and current != incoming
            ]
            if identifier_conflicts:
                return None, "unresolved", identifier_conflicts
        if paper is None:
            primary = (
                ids.get("doi")
                or ids.get("arxiv")
                or f"{record.provider}-{record.source_record_id}"
            )
            publication_year = record.attributes.get("publication_year")
            if not isinstance(publication_year, int) or isinstance(
                publication_year, bool
            ):
                return None, "unresolved", []
            readable_id = _safe_id(primary)[:96] or "record"
            paper_id = f"paper-{readable_id}-{_digest(primary)[:16]}"
            publication_date, date_precision = _publication_date(
                record.attributes.get("publication_date")
            )
            paper = models.Paper(
                id=paper_id,
                title=record.attributes.get("title") or record.canonical_name,
                summary=record.attributes.get("abstract") or "",
                publication_year=publication_year,
                publication_date=publication_date,
                publication_date_precision=date_precision,
                document_type=str(record.attributes.get("document_type") or "article"),
                doi=ids.get("doi"),
                arxiv_id=ids.get("arxiv"),
                external_ids=_external_id_dicts(record),
                provenance_json=record.provenance,
            )
            self.session.add(paper)
            self.session.flush()
            outcome = "created"
        else:
            incoming_title = record.attributes.get("title") or record.canonical_name
            incoming_summary = record.attributes.get("abstract") or paper.summary
            supplied_year = record.attributes.get("publication_year")
            incoming_year = (
                supplied_year
                if isinstance(supplied_year, int)
                and not isinstance(supplied_year, bool)
                else paper.publication_year
            )
            incoming_date, incoming_date_precision = _publication_date(
                record.attributes.get("publication_date")
            )
            incoming_document_type = str(
                record.attributes.get("document_type") or paper.document_type
            )
            incoming_external_ids = list(
                {
                    (item["scheme"], item["value"]): item
                    for item in [*paper.external_ids, *_external_id_dicts(record)]
                }.values()
            )
            changed = (
                incoming_title != paper.title
                or incoming_summary != paper.summary
                or incoming_year != paper.publication_year
                or (
                    incoming_date is not None
                    and incoming_date != paper.publication_date
                )
                or (
                    incoming_date_precision is not None
                    and incoming_date_precision != paper.publication_date_precision
                )
                or incoming_document_type != paper.document_type
                or (ids.get("doi") is not None and paper.doi is None)
                or (ids.get("arxiv") is not None and paper.arxiv_id is None)
                or incoming_external_ids != paper.external_ids
                or record.provenance != paper.provenance_json
            )
            if changed:
                paper.title = incoming_title
                paper.summary = incoming_summary
                paper.publication_year = incoming_year
                if incoming_date is not None:
                    paper.publication_date = incoming_date
                    paper.publication_date_precision = incoming_date_precision
                paper.document_type = incoming_document_type
                if paper.doi is None:
                    paper.doi = ids.get("doi")
                if paper.arxiv_id is None:
                    paper.arxiv_id = ids.get("arxiv")
                paper.external_ids = incoming_external_ids
                paper.provenance_json = record.provenance
            outcome = "updated" if changed else "unchanged"
        raw_assignments = record.attributes.get("atlas_field_assignments", [])
        assignments = (
            [item for item in raw_assignments if isinstance(item, dict)]
            if isinstance(raw_assignments, list)
            else []
        )
        if not assignments:
            assignments = [
                {"field_id": field_id, "weight": 1.0}
                for field_id in record.attributes.get("atlas_field_candidates", [])
                if isinstance(field_id, str)
            ]
        assignment_field_ids = {
            str(item["field_id"])
            for item in assignments
            if item.get("field_id") is not None
        }
        known_fields = set(
            self.session.scalars(
                select(models.ResearchField.id).where(
                    models.ResearchField.id.in_(assignment_field_ids)
                )
            )
        )
        mapping_provenance = record.attributes.get("field_mapping_provenance", {})
        if not isinstance(mapping_provenance, dict):
            mapping_provenance = {}
        provenance_assignments = mapping_provenance.get("assignments", [])
        assignment_metadata = (
            {
                str(item.get("field_id")): item
                for item in provenance_assignments
                if isinstance(item, dict) and item.get("field_id")
            }
            if isinstance(provenance_assignments, list)
            else {}
        )
        category_mappings = mapping_provenance.get("category_mappings", [])
        all_category_mappings = (
            [item for item in category_mappings if isinstance(item, dict)]
            if isinstance(category_mappings, list)
            else []
        )

        for existing_link in self.session.scalars(
            select(models.PaperField).where(models.PaperField.paper_id == paper.id)
        ):
            link_provenance = existing_link.provenance_json or {}
            same_source_record = (
                link_provenance.get("mappingProvider") == record.provider
                and link_provenance.get(
                    "mappingSourceRecordId",
                    link_provenance.get("sourceRecordId"),
                )
                == record.source_record_id
            )
            if same_source_record and existing_link.field_id not in known_fields:
                self.session.delete(existing_link)

        for assignment in assignments:
            field_id = str(assignment.get("field_id", ""))
            if field_id not in known_fields:
                continue
            metadata = assignment_metadata.get(field_id, {})
            raw_roles = metadata.get("provider_roles", [])
            roles = (
                [str(item) for item in raw_roles] if isinstance(raw_roles, list) else []
            )
            classification_role = (
                roles[0]
                if len(set(roles)) == 1
                else "mixed"
                if roles
                else "unspecified"
            )
            weight = Decimal(str(assignment.get("weight", 0)))
            if weight <= 0 or weight > 1:
                raise ValueError("field attribution weights must be within (0, 1]")
            supporting_categories = [
                item
                for item in all_category_mappings
                if field_id in item.get("atlas_field_ids", [])
            ]
            link = self.session.get(models.PaperField, (paper.id, field_id))
            values: dict[str, Any] = {
                "classification_method": record.attributes.get(
                    "field_mapping_method", "provider-category-rules-v1"
                ),
                "confidence": record.attributes.get("field_mapping_confidence"),
                "weight": weight,
                "classification_role": classification_role,
                "ontology_version": record.attributes.get(
                    "field_ontology_version", "legacy-flat-physics-fields-v1"
                ),
                "mapping_rule_version": record.attributes.get(
                    "field_mapping_method", "provider-category-rules-v1"
                ),
                "weighting_policy_version": record.attributes.get(
                    "field_weighting_policy_version", "legacy-full-membership-v1"
                ),
                "provider_categories": supporting_categories,
                "uncertainty_note": record.attributes.get("field_mapping_uncertainty"),
                "provenance_json": {
                    **record.provenance,
                    "mappingProvider": record.provider,
                    "mappingSourceRecordId": record.source_record_id,
                    "fieldMapping": mapping_provenance,
                },
            }
            if link is None:
                self.session.add(
                    models.PaperField(
                        paper_id=paper.id,
                        field_id=field_id,
                        **values,
                    )
                )
            else:
                for key, value in values.items():
                    setattr(link, key, value)
        self._attach_authority_ids(record, paper.id)
        self._upsert_resources(record, paper.id)
        refresh_search_terms(
            self.session,
            entity_type="paper",
            entity_id=paper.id,
            canonical_name=paper.title,
            aliases=[],
            historical_names=[],
            external_ids=paper.external_ids,
        )
        return paper.id, outcome, []

    def _upsert_resources(self, record: NormalizedRecord, canonical_id: str) -> None:
        resources: list[tuple[str, str, str, dict[str, str] | None]] = []
        ids = dict(record.external_ids)
        if record.kind == "institution":
            for url in record.attributes.get("official_websites", []):
                resources.append(
                    ("official-institution-website", "Official website", url, None)
                )
            if ids.get("ror"):
                resources.append(
                    (
                        "ror",
                        "ROR record",
                        f"https://ror.org/{ids['ror']}",
                        {"scheme": "ror", "value": ids["ror"]},
                    )
                )
        elif record.kind == "researcher" and ids.get("orcid"):
            resources.append(
                (
                    "orcid",
                    "ORCID record",
                    f"https://orcid.org/{ids['orcid']}",
                    {"scheme": "orcid", "value": ids["orcid"]},
                )
            )
        elif record.kind == "paper":
            if ids.get("doi"):
                resources.append(
                    (
                        "doi",
                        "DOI",
                        f"https://doi.org/{ids['doi']}",
                        {"scheme": "doi", "value": ids["doi"]},
                    )
                )
            if ids.get("arxiv"):
                resources.append(
                    (
                        "arxiv",
                        "arXiv",
                        f"https://arxiv.org/abs/{ids['arxiv']}",
                        {"scheme": "arxiv", "value": ids["arxiv"]},
                    )
                )
            if ids.get("inspire"):
                resources.append(
                    (
                        "inspire",
                        "INSPIRE",
                        f"https://inspirehep.net/literature/{ids['inspire']}",
                        {"scheme": "inspire", "value": ids["inspire"]},
                    )
                )
        entity_type = record.kind
        for resource_type, label, url, resource_external_id in resources:
            existing = self.session.scalar(
                select(models.ExternalResource).where(
                    models.ExternalResource.entity_type == entity_type,
                    models.ExternalResource.entity_id == canonical_id,
                    models.ExternalResource.resource_type == resource_type,
                    models.ExternalResource.url == url,
                )
            )
            if existing is None:
                self.session.add(
                    models.ExternalResource(
                        id=(
                            f"resource-{resource_type}-"
                            f"{_digest(canonical_id + url)[:20]}"
                        ),
                        entity_type=entity_type,
                        entity_id=canonical_id,
                        resource_type=resource_type,
                        label=label,
                        url=url,
                        source=record.provider,
                        source_record_id=record.source_record_id,
                        external_id=resource_external_id,
                        is_primary=resource_type
                        in {"official-institution-website", "orcid", "doi"},
                        verified=False,
                        health_status="unknown",
                        provenance_json=record.provenance,
                    )
                )
