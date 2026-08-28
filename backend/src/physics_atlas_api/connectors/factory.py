from pathlib import Path
from urllib.parse import urlparse

from ..config import Settings
from . import (
    ArxivConnector,
    CrossrefConnector,
    InspireConnector,
    OrcidConnector,
    RorConnector,
)
from .acquisition import resolve_acquisition_scope
from .base import ConnectorConfigurationError, SourceConnector, SourceTransport
from .http import FixtureTransport, ProviderHttpTransport


def _live_transport(
    settings: Settings, base_url: str, minimum_interval: float
) -> ProviderHttpTransport:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host:
        raise ConnectorConfigurationError(
            "Provider base URLs must use HTTP(S) and include a host"
        )
    if settings.environment == "production" and parsed.scheme != "https":
        raise ConnectorConfigurationError(
            "Production provider base URLs must use HTTPS"
        )
    return ProviderHttpTransport(
        timeout_seconds=settings.provider_timeout_seconds,
        minimum_intervals={host: minimum_interval},
        allowed_hosts={host},
    )


def build_connectors(
    settings: Settings, fixture_directory: Path | None = None
) -> dict[str, SourceConnector]:
    acquisition_scope = resolve_acquisition_scope(settings.acquisition_scope)
    transports: dict[str, SourceTransport]
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
        fixture_transport: SourceTransport = FixtureTransport(directory)
        transports = {
            provider: fixture_transport
            for provider in ("inspire", "arxiv", "ror", "orcid", "crossref")
        }
    else:
        transports = {
            "inspire": _live_transport(settings, settings.inspire_base_url, 1.0),
            "arxiv": _live_transport(settings, settings.arxiv_base_url, 3.0),
            "ror": _live_transport(settings, settings.ror_base_url, 0.2),
            "orcid": _live_transport(settings, settings.orcid_base_url, 1.0),
            "crossref": _live_transport(settings, settings.crossref_base_url, 1.0),
        }
    return {
        "inspire": InspireConnector(
            transports["inspire"],
            settings.inspire_base_url,
            acquisition_scope=acquisition_scope,
        ),
        "arxiv": ArxivConnector(
            transports["arxiv"],
            settings.arxiv_base_url,
            acquisition_scope=acquisition_scope,
        ),
        "ror": RorConnector(
            transports["ror"],
            settings.ror_base_url,
            record_ids=settings.configured_ror_record_ids,
            acquisition_scope=acquisition_scope,
        ),
        "orcid": OrcidConnector(
            transports["orcid"],
            settings.orcid_base_url,
            access_token=settings.orcid_access_token,
            require_credentials=not settings.fixture_mode,
            dataset_scope=acquisition_scope.id,
        ),
        "crossref": CrossrefConnector(
            transports["crossref"],
            settings.crossref_base_url,
            mailto=settings.crossref_mailto,
            dataset_scope=acquisition_scope.id,
        ),
    }
