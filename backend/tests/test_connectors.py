from pathlib import Path

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
from physics_atlas_api.connectors.http import FixtureTransport
from physics_atlas_api.connectors.orcid import OrcidConnector


def test_all_provider_connectors_normalize_deterministic_fixtures(
    fixture_directory: Path,
) -> None:
    settings = Settings(
        database_url="sqlite://",
        fixture_mode=True,
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


def test_provider_categories_are_mapped_without_becoming_the_taxonomy() -> None:
    mapping = map_provider_categories(
        "arxiv", ["astro-ph.CO", "physics.plasm-ph", "unknown-provider-label"]
    )

    assert mapping.raw_categories[-1] == "unknown-provider-label"
    assert set(mapping.atlas_field_ids) == {"astro-ph", "gr-qc", "plasma"}
    assert 0 < mapping.confidence < 1
    assert "not a definitive scientific taxonomy" in mapping.uncertainty_note


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
