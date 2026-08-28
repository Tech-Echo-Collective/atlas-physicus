from dataclasses import dataclass

from .base import ConnectorConfigurationError, ProviderName


@dataclass(frozen=True)
class AcquisitionScope:
    """Versioned provider filters for one bounded Atlas acquisition corpus."""

    id: str
    inspire_query: str
    arxiv_query: str

    def cursor_scope(self, provider: ProviderName, policy_version: str) -> str:
        return f"{self.id}:{provider}:{policy_version}"


HEP_TH_V1 = AcquisitionScope(
    id="hep-th-v1",
    inspire_query="subject:Theory-HEP",
    arxiv_query="cat:hep-th",
)

SUPPORTED_ACQUISITION_SCOPES = {HEP_TH_V1.id: HEP_TH_V1}


def resolve_acquisition_scope(scope_id: str) -> AcquisitionScope:
    try:
        return SUPPORTED_ACQUISITION_SCOPES[scope_id]
    except KeyError as error:
        supported = ", ".join(sorted(SUPPORTED_ACQUISITION_SCOPES))
        raise ConnectorConfigurationError(
            f"Unsupported acquisition scope {scope_id!r}; supported: {supported}"
        ) from error
