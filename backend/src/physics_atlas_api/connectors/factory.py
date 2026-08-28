from pathlib import Path

from ..config import Settings
from . import (
    ArxivConnector,
    CrossrefConnector,
    InspireConnector,
    OrcidConnector,
    RorConnector,
)
from .base import ConnectorConfigurationError, SourceConnector, SourceTransport
from .http import FixtureTransport, ProviderHttpTransport


def build_connectors(
    settings: Settings, fixture_directory: Path | None = None
) -> dict[str, SourceConnector]:
    if settings.fixture_mode:
        directory = (
            fixture_directory
            or settings.fixture_directory
            or Path(__file__).resolve().parents[3] / "fixtures"
        )
        if not directory.is_dir():
            raise ConnectorConfigurationError(
                f"Deterministic fixture directory does not exist: {directory}"
            )
        transport: SourceTransport = FixtureTransport(directory)
    else:
        transport = ProviderHttpTransport(
            timeout_seconds=settings.provider_timeout_seconds,
            minimum_intervals={
                "inspirehep.net": 1.0,
                "export.arxiv.org": 3.0,
                "api.ror.org": 0.2,
                "pub.orcid.org": 1.0,
                "api.crossref.org": 1.0,
            },
        )
    return {
        "inspire": InspireConnector(transport, settings.inspire_base_url),
        "arxiv": ArxivConnector(transport, settings.arxiv_base_url),
        "ror": RorConnector(transport, settings.ror_base_url),
        "orcid": OrcidConnector(
            transport,
            settings.orcid_base_url,
            access_token=settings.orcid_access_token,
            require_credentials=not settings.fixture_mode,
        ),
        "crossref": CrossrefConnector(
            transport, settings.crossref_base_url, mailto=settings.crossref_mailto
        ),
    }
