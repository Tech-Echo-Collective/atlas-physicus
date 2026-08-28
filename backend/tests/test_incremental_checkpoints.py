import re
from typing import Any

import pytest
from sqlalchemy.orm import Session

from physics_atlas_api import models
from physics_atlas_api.config import Settings
from physics_atlas_api.connectors.arxiv import ArxivConnector
from physics_atlas_api.connectors.base import ConnectorConfigurationError
from physics_atlas_api.connectors.factory import build_connectors
from physics_atlas_api.connectors.inspire import InspireConnector
from physics_atlas_api.connectors.ror import RorConnector
from physics_atlas_api.scheduler import UpdateScheduler


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
        record_id = "2" if url.endswith("page=2") else "1"
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
            }
        }
        if record_id == "1":
            payload["links"] = {"next": "https://inspire.test/api/literature?page=2"}
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
    assert first.checkpoint["nextUrl"].endswith("page=2")
    assert first.raw_payload[0]["body"]["hits"]["hits"][0]["id"] == "1"
    first_query = transport.params[0]
    assert first_query is not None
    assert re.fullmatch(
        r"document_type:article and du >= \d{4}-\d{2}-\d{2} "
        r"and du <= \d{4}-\d{2}-\d{2}",
        first_query["q"],
    )

    connector.set_checkpoint(first.checkpoint)
    second = connector.fetch_new_records(first.next_cursor, limit=10)
    assert second.next_cursor == first.checkpoint["until"]
    assert second.checkpoint == {}
    assert transport.urls[-1].endswith("page=2")


class ProviderContractTransport:
    def __init__(self) -> None:
        self.json_params: list[dict[str, Any] | None] = []
        self.text_params: list[dict[str, Any] | None] = []

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del url, headers
        self.json_params.append(params)
        return {"items": [], "meta": {"number_of_results": 0}}

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


def test_ror_and_arxiv_use_provider_native_closed_windows() -> None:
    transport = ProviderContractTransport()
    ror = RorConnector(transport, "https://api.ror.test/v2")
    ror.set_checkpoint(
        {
            "since": "2026-08-01T18:30:00+00:00",
            "until": "2026-08-08T23:59:59+00:00",
            "page": 1,
        }
    )

    ror_batch = ror.fetch_new_records(None)

    ror_params = transport.json_params[-1]
    assert ror_params is not None
    assert ror_params["query.advanced"] == (
        "admin.last_modified.date:[2026-08-01 TO 2026-08-08]"
    )
    assert ror_batch.next_cursor == "2026-08-08"
    assert ror_batch.raw_payload[0]["body"]["meta"]["number_of_results"] == 0

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
    assert "lastUpdatedDate" not in str(arxiv_params["search_query"])
    assert arxiv_params["sortBy"] == "submittedDate"
    assert arxiv_batch.next_cursor == "2026-08-02T00:00:00+00:00"
    assert arxiv_batch.raw_payload[0]["body"].startswith("<feed")


def test_pending_checkpoint_is_due_without_waiting_for_next_cadence(
    session: Session,
) -> None:
    session.add(
        models.SourceCursor(
            source="inspire",
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
