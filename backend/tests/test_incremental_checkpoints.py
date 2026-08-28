import re
from typing import Any
from urllib.parse import urlencode

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from physics_atlas_api import models
from physics_atlas_api.config import Settings
from physics_atlas_api.connectors.arxiv import ArxivConnector
from physics_atlas_api.connectors.base import (
    ConnectorConfigurationError,
    ConnectorError,
    parse_provider_datetime,
)
from physics_atlas_api.connectors.factory import build_connectors
from physics_atlas_api.connectors.inspire import InspireConnector
from physics_atlas_api.connectors.ror import RorConnector
from physics_atlas_api.scheduler import UpdateScheduler
from physics_atlas_api.updates.engine import IncrementalUpdateEngine


class PagedInspireTransport:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.params: list[dict[str, Any] | None] = []

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del headers
        self.urls.append(url)
        self.params.append(params)
        record_id = "2" if "page=2" in url else "1"
        payload: dict[str, Any] = {
            "hits": {
                "hits": [
                    {
                        "id": record_id,
                        "metadata": {
                            "control_number": int(record_id),
                            "last_updated": "2026-08-27T00:00:00+00:00",
                        },
                    }
                ]
            },
            "links": {},
        }
        if record_id == "1":
            assert params is not None
            payload["links"] = {
                "next": (
                    "https://inspire.test/api/literature?"
                    + urlencode({"q": str(params["q"]), "page": 2})
                )
            }
        return payload

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        del url, params, headers
        raise AssertionError("INSPIRE checkpoint test does not request text")


def test_closed_window_checkpoint_advances_only_after_last_page() -> None:
    transport = PagedInspireTransport()
    connector = InspireConnector(transport, "https://inspire.test/api")

    first = connector.fetch_new_records(None, limit=10)
    assert first.next_cursor is None
    assert "page=2" in first.checkpoint["nextUrl"]
    assert first.replay_checkpoint == {
        "since": first.checkpoint["since"],
        "until": first.checkpoint["until"],
    }
    assert first.raw_payload[0]["body"]["hits"]["hits"][0]["id"] == "1"
    first_query = transport.params[0]
    assert first_query is not None
    assert re.fullmatch(
        r"document_type:article and subject:Theory-HEP and "
        r"du >= \d{4}-\d{2}-\d{2} "
        r"and du <= \d{4}-\d{2}-\d{2}",
        first_query["q"],
    )

    connector.set_checkpoint(first.checkpoint)
    second = connector.fetch_new_records(first.next_cursor, limit=10)
    assert second.next_cursor == first.checkpoint["until"]
    assert second.checkpoint == {}
    assert second.replay_checkpoint == {
        "since": first.checkpoint["since"],
        "until": first.checkpoint["until"],
        "nextUrl": first.checkpoint["nextUrl"],
    }
    assert "page=2" in transport.urls[-1]


class ProviderContractTransport:
    def __init__(self) -> None:
        self.json_urls: list[str] = []
        self.json_params: list[dict[str, Any] | None] = []
        self.text_params: list[dict[str, Any] | None] = []

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del headers
        self.json_urls.append(url)
        self.json_params.append(params)
        record_id = url.rsplit("/", 1)[-1]
        return {
            "id": f"https://ror.org/{record_id}",
            "names": [{"value": record_id, "types": ["ror_display"]}],
            "locations": [],
            "links": [],
        }

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        del url, headers
        self.text_params.append(params)
        return "<feed xmlns='http://www.w3.org/2005/Atom'></feed>"


class FailingArxivTransport:
    def __init__(self, failure: str) -> None:
        self.failure = failure

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del url, params, headers
        raise AssertionError("arXiv recovery test does not request JSON")

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        del url, params, headers
        if self.failure == "request":
            raise ConnectorError("provider request timed out")
        return "<html><body>upstream error</body></html>"


def test_ror_fetches_only_configured_targets_in_bounded_pages() -> None:
    transport = ProviderContractTransport()
    ror = RorConnector(
        transport,
        "https://api.ror.test/v2",
        record_ids=("03yrm5c26", "02mhbdp94"),
    )

    assert ror.record_ids == ("02mhbdp94", "03yrm5c26")
    first = ror.fetch_new_records(None, limit=1)
    assert [record.source_record_id for record in first.records] == ["02mhbdp94"]
    assert first.next_cursor is None
    assert first.checkpoint["targetIndex"] == 1
    assert first.replay_checkpoint == {
        "until": first.checkpoint["until"],
        "targetIndex": 0,
    }
    assert transport.json_urls == ["https://api.ror.test/v2/organizations/02mhbdp94"]
    assert transport.json_params == [None]

    ror.set_checkpoint(first.checkpoint)
    second = ror.fetch_new_records(first.next_cursor, limit=1)
    assert [record.source_record_id for record in second.records] == ["03yrm5c26"]
    assert second.next_cursor == first.checkpoint["until"]
    assert second.checkpoint == {}
    assert second.replay_checkpoint == {
        "until": first.checkpoint["until"],
        "targetIndex": 1,
    }
    assert transport.json_urls[-1].endswith("/organizations/03yrm5c26")


def test_ror_without_configured_targets_is_disabled_and_does_not_request() -> None:
    transport = ProviderContractTransport()
    ror = RorConnector(transport, "https://api.ror.test/v2")

    batch = ror.fetch_new_records("existing-cursor")

    assert ror.enabled is False
    assert batch.records == ()
    assert batch.next_cursor == "existing-cursor"
    assert transport.json_urls == []


def test_arxiv_uses_hep_th_submitted_date_closed_window() -> None:
    transport = ProviderContractTransport()

    arxiv = ArxivConnector(transport, "https://export.arxiv.test/api/query")
    arxiv.set_checkpoint(
        {
            "since": "2026-08-01T00:00:00+00:00",
            "until": "2026-08-02T00:00:00+00:00",
            "start": 0,
        }
    )

    arxiv_batch = arxiv.fetch_new_records(None)

    arxiv_params = transport.text_params[-1]
    assert arxiv_params is not None
    assert "submittedDate:[202608010000 TO 202608020000]" in str(
        arxiv_params["search_query"]
    )
    assert str(arxiv_params["search_query"]).startswith(
        "(cat:hep-th) AND submittedDate:"
    )
    assert "physics.*" not in str(arxiv_params["search_query"])
    assert "lastUpdatedDate" not in str(arxiv_params["search_query"])
    assert arxiv_params["sortBy"] == "submittedDate"
    assert arxiv_batch.next_cursor == "2026-08-02T00:00:00+00:00"
    assert arxiv_batch.replay_checkpoint == {
        "since": "2026-08-01T00:00:00+00:00",
        "until": "2026-08-02T00:00:00+00:00",
        "start": 0,
    }
    assert arxiv_batch.raw_payload[0]["body"].startswith("<feed")


@pytest.mark.parametrize("failure", ["request", "malformed-envelope"])
def test_provider_failure_persists_the_fixed_request_window(
    session: Session,
    failure: str,
) -> None:
    connector = ArxivConnector(
        FailingArxivTransport(failure), "https://export.arxiv.test/api/query"
    )

    result = IncrementalUpdateEngine(session, connector).run()

    assert result.status == "failed"
    state = session.get(models.SourceCursor, "arxiv")
    assert state is not None
    assert state.cursor is None
    assert state.checkpoint["start"] == 0
    assert parse_provider_datetime(str(state.checkpoint["since"])) is not None
    assert parse_provider_datetime(str(state.checkpoint["until"])) is not None


def test_cursor_from_different_acquisition_scope_fails_closed(
    session: Session,
    fixture_directory,
) -> None:  # type: ignore[no-untyped-def]
    connector = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["inspire"]
    session.add(
        models.SourceCursor(
            source="inspire",
            scope_version="legacy-unbounded-v1",
            cursor="2026-08-01",
            checkpoint={"nextUrl": "https://inspirehep.net/api/literature?page=2"},
        )
    )
    session.commit()

    result = IncrementalUpdateEngine(session, connector).run()

    assert result.status == "failed"
    state = session.get(models.SourceCursor, "inspire")
    assert state is not None
    assert state.scope_version == "legacy-unbounded-v1"
    assert state.cursor == "2026-08-01"
    assert state.checkpoint == {
        "nextUrl": "https://inspirehep.net/api/literature?page=2"
    }
    assert session.scalar(select(func.count()).select_from(models.SourceSnapshot)) == 0
    run = session.scalar(select(models.UpdateRun))
    assert run is not None
    assert "Persisted source cursor scope does not match" in str(run.error)


def test_pending_checkpoint_is_due_without_waiting_for_next_cadence(
    session: Session,
) -> None:
    session.add(
        models.SourceCursor(
            source="inspire",
            scope_version="hep-th-v1:inspire:updated-articles-v1",
            cursor=None,
            checkpoint={"nextUrl": "https://inspire.test/page=2"},
        )
    )
    session.commit()

    assert UpdateScheduler(session).due_sources(["inspire"]) == ["inspire"]


def test_identity_and_doi_enrichment_connectors_are_not_global_pollers(
    fixture_directory,
) -> None:  # type: ignore[no-untyped-def]
    connectors = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )

    with pytest.raises(ConnectorConfigurationError):
        connectors["orcid"].fetch_new_records(None)
    with pytest.raises(ConnectorConfigurationError):
        connectors["crossref"].fetch_new_records(None)
