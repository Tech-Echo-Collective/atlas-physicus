from types import TracebackType
from typing import Self

import pytest

from physics_atlas_api import worker
from physics_atlas_api.config import Settings
from physics_atlas_api.resources.monitor import HttpResourceTransport


class TrackedTransport:
    def __init__(self) -> None:
        self.enter_count = 0
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1

    def __enter__(self) -> Self:
        self.enter_count += 1
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()


class FakeSessionContext:
    def __enter__(self) -> object:
        return object()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback


class FakeScheduler:
    def __init__(self, *, lock_acquired: bool, due_sources: list[str]) -> None:
        self.lock_acquired = lock_acquired
        self.sources = due_sources
        self.release_count = 0

    def acquire_lock(self) -> bool:
        return self.lock_acquired

    def due_sources(self, sources: list[str]) -> list[str]:
        return [source for source in self.sources if source in sources]

    def release_lock(self) -> None:
        self.release_count += 1


class FakeConnector:
    def __init__(self, transport: TrackedTransport) -> None:
        self.transport = transport
        self.enabled = True


def configure_worker(
    monkeypatch: pytest.MonkeyPatch,
    *,
    scheduler: FakeScheduler,
) -> tuple[TrackedTransport, TrackedTransport, TrackedTransport]:
    shared_provider_transport = TrackedTransport()
    unique_provider_transport = TrackedTransport()
    resource_transport = TrackedTransport()
    connectors = {
        "inspire": FakeConnector(shared_provider_transport),
        "arxiv": FakeConnector(shared_provider_transport),
        "ror": FakeConnector(unique_provider_transport),
    }
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: Settings(database_url="sqlite://", fixture_mode=True),
    )
    monkeypatch.setattr(worker, "build_connectors", lambda *_: connectors)
    monkeypatch.setattr(worker, "HttpResourceTransport", lambda: resource_transport)
    monkeypatch.setattr(worker, "SessionLocal", FakeSessionContext)
    monkeypatch.setattr(worker, "ensure_reference_data", lambda _: None)
    monkeypatch.setattr(worker, "UpdateScheduler", lambda _: scheduler)
    return shared_provider_transport, unique_provider_transport, resource_transport


def test_worker_closes_unique_transports_when_lock_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = FakeScheduler(lock_acquired=False, due_sources=[])
    shared, unique, resource = configure_worker(monkeypatch, scheduler=scheduler)

    assert worker.execute_once(check_resources=True) == 0

    assert (shared.enter_count, shared.close_count) == (1, 1)
    assert (unique.enter_count, unique.close_count) == (1, 1)
    assert (resource.enter_count, resource.close_count) == (1, 1)
    assert scheduler.release_count == 0


def test_resource_transport_context_closes_its_client() -> None:
    transport = HttpResourceTransport()
    client = transport.client

    with transport as entered:
        assert entered is transport
        assert client.is_closed is False

    assert client.is_closed is True


def test_worker_closes_transports_and_releases_lock_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = FakeScheduler(lock_acquired=True, due_sources=["inspire"])
    shared, unique, resource = configure_worker(monkeypatch, scheduler=scheduler)

    class FailingEngine:
        def __init__(self, *args: object) -> None:
            del args

        def run(self) -> None:
            raise RuntimeError("deliberate worker failure")

    monkeypatch.setattr(worker, "IncrementalUpdateEngine", FailingEngine)

    with pytest.raises(RuntimeError, match="deliberate worker failure"):
        worker.execute_once(check_resources=True)

    assert (shared.enter_count, shared.close_count) == (1, 1)
    assert (unique.enter_count, unique.close_count) == (1, 1)
    assert (resource.enter_count, resource.close_count) == (1, 1)
    assert scheduler.release_count == 1
