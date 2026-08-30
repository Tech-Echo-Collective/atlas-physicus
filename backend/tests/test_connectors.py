from pathlib import Path

import httpx
import pytest
from defusedxml.common import DefusedXmlException

from physics_atlas_api.config import Settings
from physics_atlas_api.connectors.base import (
    ConnectorConfigurationError,
    ConnectorError,
    normalize_external_id,
)
from physics_atlas_api.connectors.factory import build_connectors
from physics_atlas_api.connectors.field_mapping import map_provider_categories
from physics_atlas_api.connectors.http import FixtureTransport, ProviderHttpTransport
from physics_atlas_api.connectors.inspire import InspireConnector
from physics_atlas_api.connectors.orcid import OrcidConnector
from physics_atlas_api.connectors.ror import RorConnector


class JsonPayloadTransport:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload
        self.requests: list[str] = []

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        del params, headers
        self.requests.append(url)
        return self.payload

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        del url, params, headers
        raise AssertionError("JSON envelope tests do not request text")


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def provider_transport(
    handler: httpx.BaseTransport,
    *,
    allowed_hosts: set[str] | None = None,
    max_attempts: int = 3,
    minimum_interval: float = 0,
) -> ProviderHttpTransport:
    transport = ProviderHttpTransport(
        timeout_seconds=1,
        allowed_hosts=allowed_hosts or {"provider.test"},
        max_attempts=max_attempts,
        minimum_intervals={"provider.test": minimum_interval},
    )
    transport.client.close()
    transport.client = httpx.Client(
        transport=handler,
        timeout=1,
        follow_redirects=False,
    )
    return transport


def test_all_provider_connectors_normalize_deterministic_fixtures(
    fixture_directory: Path,
) -> None:
    settings = Settings(
        database_url="sqlite://",
        fixture_mode=True,
        ror_record_ids="03yrm5c26",
    )
    connectors = build_connectors(settings, fixture_directory)

    inspire = connectors["inspire"]
    inspire_record = inspire.fetch_new_records(None).records[0]
    inspire_normalized = inspire.normalize_record(inspire_record)
    assert inspire_normalized.kind == "paper"
    assert inspire_normalized.attributes["atlas_field_candidates"] == ["hep-th"]

    arxiv = connectors["arxiv"]
    arxiv_record = arxiv.fetch_new_records(None).records[0]
    arxiv_normalized = arxiv.normalize_record(arxiv_record)
    assert arxiv_normalized.external_ids == (
        ("arxiv", "2608.01234"),
        ("doi", "10.5555/physics-atlas.fixture"),
    )

    ror = connectors["ror"]
    ror_record = ror.fetch_new_records(None).records[0]
    ror_normalized = ror.normalize_record(ror_record)
    assert ror_normalized.kind == "institution"
    assert ror_normalized.attributes["country_code"] == "CH"

    orcid = connectors["orcid"]
    orcid_record = orcid.fetch_record("0000-0002-1825-0097")
    assert orcid_record is not None
    assert orcid.normalize_record(orcid_record).canonical_name == "Ada Fixture"

    crossref = connectors["crossref"]
    crossref_record = crossref.fetch_record("10.5555/physics-atlas.fixture")
    assert crossref_record is not None
    crossref_normalized = crossref.normalize_record(crossref_record)
    assert "math-ph" in crossref_normalized.attributes["atlas_field_candidates"]


def test_factory_rejects_an_unsupported_acquisition_scope(
    fixture_directory: Path,
) -> None:
    with pytest.raises(ConnectorConfigurationError, match="Unsupported acquisition"):
        build_connectors(
            Settings(
                database_url="sqlite://",
                fixture_mode=True,
                acquisition_scope="all-physics-v0",
            ),
            fixture_directory,
        )


def test_factory_requires_https_provider_urls_in_production() -> None:
    with pytest.raises(ConnectorConfigurationError, match="must use HTTPS"):
        build_connectors(
            Settings(
                database_url="sqlite://",
                environment="production",
                fixture_mode=False,
                inspire_base_url="http://inspire.test/api",
            )
        )


def test_provider_categories_are_mapped_without_becoming_the_taxonomy() -> None:
    mapping = map_provider_categories(
        "arxiv", ["astro-ph.CO", "physics.plasm-ph", "unknown-provider-label"]
    )

    assert mapping.raw_categories[-1] == "unknown-provider-label"
    assert set(mapping.atlas_field_ids) == {"astro-ph", "gr-qc", "plasma"}
    assert mapping.confidence is None
    assert mapping.mapping_coverage == pytest.approx(2 / 3)
    assert "not the Atlas ontology" in mapping.uncertainty_note


def test_arxiv_parser_rejects_unsafe_xml_entities(
    fixture_directory: Path,
) -> None:
    connector = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["arxiv"]
    unsafe_xml = """<!DOCTYPE feed [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>
    <feed xmlns='http://www.w3.org/2005/Atom'><entry><id>&xxe;</id></entry></feed>"""

    with pytest.raises(DefusedXmlException):
        connector._records(unsafe_xml)  # type: ignore[attr-defined]


def test_arxiv_parser_rejects_provider_error_feed(fixture_directory: Path) -> None:
    connector = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["arxiv"]
    error_xml = """<feed xmlns='http://www.w3.org/2005/Atom'>
      <entry>
        <id>http://arxiv.org/api/errors#incorrect_query</id>
        <title>Error</title>
        <summary>incorrect query</summary>
      </entry>
    </feed>"""

    with pytest.raises(ConnectorError, match="incorrect query"):
        connector._records(error_xml)  # type: ignore[attr-defined]


def test_arxiv_parser_rejects_non_atom_success_envelope(
    fixture_directory: Path,
) -> None:
    connector = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["arxiv"]

    with pytest.raises(ConnectorError, match="not an Atom feed"):
        connector._records(  # type: ignore[attr-defined]
            "<html><body>upstream error</body></html>"
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"hits": []},
        {"hits": {"hits": "not-a-list"}},
        {"hits": {"hits": [{"id": "123"}]}},
        {"hits": {"hits": [{"metadata": {}}]}},
    ],
)
def test_inspire_rejects_malformed_success_envelopes(
    payload: dict[str, object],
) -> None:
    connector = InspireConnector(
        JsonPayloadTransport(payload), "https://provider.test/api"
    )

    with pytest.raises(ConnectorError, match="INSPIRE response"):
        connector.fetch_new_records(None)

    assert connector.get_cursor() is None
    assert connector.get_checkpoint() == {}


def test_inspire_rejects_missing_pagination_envelope() -> None:
    connector = InspireConnector(
        JsonPayloadTransport({"hits": {"hits": []}}),
        "https://provider.test/api",
    )

    with pytest.raises(ConnectorError, match="missing the pagination links"):
        connector.fetch_new_records(None)

    assert connector.get_cursor() is None
    assert connector.get_checkpoint() == {}
    replay_checkpoint = connector.get_replay_checkpoint()
    assert replay_checkpoint is not None
    assert set(replay_checkpoint) == {"since", "until"}


def test_inspire_rejects_cross_origin_pagination_before_advancing_cursor() -> None:
    connector = InspireConnector(
        JsonPayloadTransport(
            {
                "hits": {"hits": []},
                "links": {"next": "https://other.test/api/literature?page=2"},
            }
        ),
        "https://provider.test/api",
    )

    with pytest.raises(ConnectorError, match="crossed its provider origin"):
        connector.fetch_new_records(None)

    assert connector.get_cursor() is None
    assert connector.get_checkpoint() == {}


def test_inspire_rejects_persisted_cross_origin_pagination_before_request() -> None:
    transport = JsonPayloadTransport({"hits": {"hits": []}})
    connector = InspireConnector(transport, "https://provider.test/api")
    checkpoint = {"nextUrl": "https://other.test/api/literature?page=2"}
    connector.set_checkpoint(checkpoint)

    with pytest.raises(ConnectorError, match="crossed its provider origin"):
        connector.fetch_new_records(None)

    assert transport.requests == []
    assert connector.get_cursor() is None
    assert connector.get_checkpoint() == checkpoint


@pytest.mark.parametrize(
    "next_url",
    [
        "https://provider.test/api/authors?q=subject%3ATheory-HEP",
        "https://provider.test/api/literature?page=2",
        (
            "https://provider.test/api/literature?"
            "q=document_type%3Aarticle+and+subject%3AExperiment-HEP"
        ),
    ],
)
def test_inspire_rejects_same_origin_pagination_outside_bounded_query(
    next_url: str,
) -> None:
    connector = InspireConnector(
        JsonPayloadTransport({"hits": {"hits": []}, "links": {"next": next_url}}),
        "https://provider.test/api",
    )

    with pytest.raises(ConnectorError, match="bounded"):
        connector.fetch_new_records(None)

    assert connector.get_cursor() is None
    assert connector.get_checkpoint() == {}
    replay_checkpoint = connector.get_replay_checkpoint()
    assert replay_checkpoint is not None
    assert set(replay_checkpoint) == {"since", "until"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"items": "not-a-list"},
        {"items": []},
        {"items": [{}]},
        {"id": "https://ror.org/03yrm5c26"},
    ],
)
def test_ror_rejects_malformed_success_envelopes(
    payload: dict[str, object],
) -> None:
    connector = RorConnector(
        JsonPayloadTransport(payload),
        "https://provider.test/v2",
        record_ids=("02mhbdp94",),
    )

    with pytest.raises(ConnectorError, match="ROR response"):
        connector.fetch_new_records(None)

    assert connector.get_cursor() is None
    assert connector.get_checkpoint() == {}


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_provider_transport_paces_network_error_retries(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[httpx.HTTPError],
) -> None:
    attempts = 0
    attempt_times: list[float] = []
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        attempt_times.append(clock.monotonic())
        if attempts < 3:
            raise error_type("provider request failed", request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    monkeypatch.setattr(
        "physics_atlas_api.connectors.http.time.monotonic", clock.monotonic
    )
    monkeypatch.setattr("physics_atlas_api.connectors.http.time.sleep", clock.sleep)
    transport = provider_transport(httpx.MockTransport(handler), minimum_interval=3.0)

    assert transport.get_json("https://provider.test/records") == {"ok": True}
    assert attempts == 3
    assert attempt_times == [100.0, 103.0, 106.0]
    assert clock.sleeps == [0.5, 2.5, 1.0, 2.0]


def test_provider_transport_context_closes_its_client() -> None:
    transport = ProviderHttpTransport(allowed_hosts={"provider.test"})
    client = transport.client

    with transport as entered:
        assert entered is transport
        assert client.is_closed is False

    assert client.is_closed is True


@pytest.mark.parametrize(
    ("retry_after", "expected_delay"),
    [
        ("2", 2.0),
    ],
)
def test_provider_transport_honors_retry_after(
    monkeypatch: pytest.MonkeyPatch,
    retry_after: str,
    expected_delay: float,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": retry_after},
                request=request,
            )
        return httpx.Response(200, json={"ok": True}, request=request)

    monkeypatch.setattr("physics_atlas_api.connectors.http.time.sleep", sleeps.append)
    transport = provider_transport(httpx.MockTransport(handler))

    assert transport.get_json("https://provider.test/records") == {"ok": True}
    assert attempts == 2
    assert sleeps == [expected_delay]


def test_provider_transport_does_not_retry_before_long_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "Fri, 31 Dec 2099 23:59:59 GMT"},
            request=request,
        )

    monkeypatch.setattr("physics_atlas_api.connectors.http.time.sleep", sleeps.append)
    transport = provider_transport(httpx.MockTransport(handler))

    with pytest.raises(ConnectorError, match="beyond the bounded request budget"):
        transport.get_json("https://provider.test/records")

    assert attempts == 1
    assert sleeps == []


def test_provider_transport_recovers_from_retryable_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            503 if attempts == 1 else 200,
            json={"ok": attempts > 1},
            request=request,
        )

    monkeypatch.setattr("physics_atlas_api.connectors.http.time.sleep", sleeps.append)
    transport = provider_transport(httpx.MockTransport(handler))

    assert transport.get_json("https://provider.test/records") == {"ok": True}
    assert attempts == 2
    assert sleeps == [0.5]


def test_provider_transport_reports_exhausted_server_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, request=request)

    monkeypatch.setattr("physics_atlas_api.connectors.http.time.sleep", lambda _: None)
    transport = provider_transport(httpx.MockTransport(handler))

    with pytest.raises(ConnectorError, match="Provider request failed"):
        transport.get_json("https://provider.test/records")

    assert attempts == 3


def test_provider_transport_rejects_redirects_before_disallowed_host_request() -> None:
    requested_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        return httpx.Response(
            302,
            headers={"Location": "https://untrusted.test/records"},
            request=request,
        )

    transport = provider_transport(httpx.MockTransport(handler))

    with pytest.raises(ConnectorError, match="not allowed"):
        transport.get_json("https://provider.test/records")

    assert requested_hosts == ["provider.test"]


@pytest.mark.parametrize(
    "target",
    [
        "https://other.test/records",
        "http://provider.test/records",
        "https://provider.test:444/records",
    ],
)
def test_provider_transport_does_not_forward_auth_across_origins(
    target: str,
) -> None:
    requests: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((str(request.url), request.headers.get("Authorization")))
        return httpx.Response(
            302,
            headers={"Location": target},
            request=request,
        )

    transport = provider_transport(
        httpx.MockTransport(handler),
        allowed_hosts={"provider.test", "other.test"},
    )

    with pytest.raises(ConnectorError, match="crossed its configured origin"):
        transport.get_json(
            "https://provider.test/records",
            headers={"Authorization": "Bearer provider-secret"},
        )

    assert requests == [("https://provider.test/records", "Bearer provider-secret")]


def test_provider_transport_follows_same_origin_redirect() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path == "/records":
            return httpx.Response(
                302,
                headers={"Location": "/v2/records"},
                request=request,
            )
        return httpx.Response(200, json={"ok": True}, request=request)

    transport = provider_transport(httpx.MockTransport(handler))

    assert transport.get_json("https://provider.test/records") == {"ok": True}
    assert requested_urls == [
        "https://provider.test/records",
        "https://provider.test/v2/records",
    ]


def test_provider_transport_validates_the_final_response_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": True},
            request=request,
        )

    transport = provider_transport(
        httpx.MockTransport(handler),
        allowed_hosts={"provider.test", "other.test"},
    )

    def mismatched_response(
        url: str,
        *,
        params: dict[str, object] | None,
        headers: dict[str, str] | None,
    ) -> httpx.Response:
        del url, params, headers
        return httpx.Response(
            200,
            json={"ok": True},
            request=httpx.Request("GET", "https://other.test/records"),
        )

    monkeypatch.setattr(transport, "_request_url", mismatched_response)

    with pytest.raises(ConnectorError, match="response crossed"):
        transport.get_json("https://provider.test/records")


def test_live_connector_transports_are_isolated_by_provider_origin() -> None:
    settings = Settings(
        database_url="sqlite://",
        fixture_mode=False,
        inspire_base_url="https://inspire.test/api",
        arxiv_base_url="https://arxiv.test/api/query",
        ror_base_url="https://ror.test/v2",
        orcid_base_url="https://orcid.test/v3.0",
        crossref_base_url="https://crossref.test/v1",
    )

    connectors = build_connectors(settings)

    assert len({id(connector.transport) for connector in connectors.values()}) == 5
    for provider, connector in connectors.items():
        transport = connector.transport
        assert isinstance(transport, ProviderHttpTransport)
        assert transport.allowed_hosts == {f"{provider}.test"}


@pytest.mark.parametrize(
    ("scheme", "value", "expected"),
    [
        ("DOI", "https://doi.org/10.ABC/Example", ("doi", "10.abc/example")),
        (
            "orcid",
            "https://orcid.org/0000-0002-1825-0097",
            ("orcid", "0000-0002-1825-0097"),
        ),
        ("ROR", "https://ror.org/02mhbdp94", ("ror", "02mhbdp94")),
        (
            "arXiv",
            "https://arxiv.org/pdf/2608.01234v2.pdf",
            ("arxiv", "2608.01234"),
        ),
        (
            "inspire",
            "https://inspirehep.net/literature/451647",
            ("inspire", "451647"),
        ),
        (
            "inspire-author",
            "https://inspirehep.net/authors/1017043",
            ("inspire-author", "1017043"),
        ),
    ],
)
def test_authority_identifiers_have_scheme_specific_canonical_forms(
    scheme: str, value: str, expected: tuple[str, str]
) -> None:
    assert normalize_external_id(scheme, value) == expected


def test_invalid_authority_identifiers_are_not_accepted() -> None:
    assert normalize_external_id("orcid", "0000-0000-0000-0000") is None
    assert normalize_external_id("doi", "not-a-doi") is None
    assert normalize_external_id("ror", "not-ror") is None


def test_orcid_targeted_fetch_requires_provider_credentials(
    fixture_directory: Path,
) -> None:
    connector = OrcidConnector(
        FixtureTransport(fixture_directory),
        "https://pub.orcid.org/v3.0",
        require_credentials=True,
    )

    with pytest.raises(ConnectorConfigurationError, match="access token"):
        connector.fetch_record("0000-0002-1825-0097")
