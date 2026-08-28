from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import models

SOURCE_CADENCE = {
    "inspire": timedelta(days=1),
    "arxiv": timedelta(days=1),
    "ror": timedelta(days=7),
}


class UpdateScheduler:
    advisory_lock_id = 7040304

    def __init__(self, session: Session):
        self.session = session

    def due_sources(
        self, sources: list[str], *, now: datetime | None = None
    ) -> list[str]:
        current = now or datetime.now(UTC)
        due = []
        for source in sources:
            if source not in SOURCE_CADENCE:
                continue
            state = self.session.get(models.SourceCursor, source)
            if state is not None and state.checkpoint:
                due.append(source)
                continue
            cadence = SOURCE_CADENCE[source]
            if state is None or state.last_success_at is None:
                due.append(source)
                continue
            last_success = state.last_success_at
            if last_success.tzinfo is None:
                last_success = last_success.replace(tzinfo=UTC)
            if current - last_success >= cadence:
                due.append(source)
        return due

    def acquire_lock(self) -> bool:
        if self.session.bind is None or self.session.bind.dialect.name != "postgresql":
            return True
        return bool(
            self.session.scalar(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": self.advisory_lock_id},
            )
        )

    def release_lock(self) -> None:
        if (
            self.session.bind is not None
            and self.session.bind.dialect.name == "postgresql"
        ):
            self.session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": self.advisory_lock_id},
            )
