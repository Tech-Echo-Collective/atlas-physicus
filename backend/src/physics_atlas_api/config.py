from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets are supplied only through the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PHYSICS_ATLAS_",
        extra="ignore",
        populate_by_name=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(
        default=(
            "postgresql+psycopg://physics_atlas:physics_atlas@db:5432/physics_atlas"
        ),
        validation_alias=AliasChoices(
            "PHYSICS_ATLAS_DATABASE_URL",
            "DATABASE_URL",
        ),
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("PHYSICS_ATLAS_PORT", "PORT"),
    )
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"
    api_prefix: str = "/api"
    default_page_size: int = Field(default=50, ge=1, le=200)
    max_page_size: int = Field(default=200, ge=1, le=500)
    provider_timeout_seconds: float = Field(default=15, ge=1, le=60)
    worker_poll_seconds: int = Field(default=3600, ge=60)
    resource_check_max_per_run: int = Field(default=100, ge=1, le=1000)
    resource_check_allowed_hosts: str = (
        "ror.org,orcid.org,arxiv.org,inspirehep.net,doi.org,crossref.org"
    )
    fixture_mode: bool = True
    fixture_directory: Path | None = None
    reference_data_path: Path | None = None
    acquisition_scope: str = "hep-th-v1"
    ror_record_ids: str = ""
    inspire_base_url: str = "https://inspirehep.net/api"
    arxiv_base_url: str = "https://export.arxiv.org/api/query"
    ror_base_url: str = "https://api.ror.org/v2"
    orcid_base_url: str = "https://pub.orcid.org/v3.0"
    crossref_base_url: str = "https://api.crossref.org/v1"
    crossref_mailto: str | None = None
    orcid_client_id: str | None = None
    orcid_client_secret: str | None = None
    orcid_access_token: str | None = None

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_postgresql_driver(cls, value: object) -> object:
        """Use the installed psycopg 3 driver for platform PostgreSQL URLs."""

        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @model_validator(mode="after")
    def reject_production_fixture_mode(self) -> Self:
        if self.environment == "production" and self.fixture_mode:
            raise ValueError("fixture mode must be disabled in production")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [
            value.strip() for value in self.cors_origins.split(",") if value.strip()
        ]

    @property
    def resource_allowed_hosts(self) -> set[str]:
        return {
            value.strip().casefold().rstrip(".")
            for value in self.resource_check_allowed_hosts.split(",")
            if value.strip()
        }

    @property
    def configured_ror_record_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                value.strip()
                for value in self.ror_record_ids.split(",")
                if value.strip()
            )
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
