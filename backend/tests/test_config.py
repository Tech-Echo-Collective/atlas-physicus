from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from physics_atlas_api import main
from physics_atlas_api.config import Settings
from physics_atlas_api.database import create_database_engine


@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://"])
def test_settings_normalize_platform_postgresql_urls(
    monkeypatch: pytest.MonkeyPatch,
    scheme: str,
) -> None:
    monkeypatch.delenv("PHYSICS_ATLAS_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"{scheme}atlas:secret@postgres/atlas")

    settings = Settings(_env_file=None)
    engine = create_database_engine(settings.database_url)
    try:
        assert settings.database_url == (
            "postgresql+psycopg://atlas:secret@postgres/atlas"
        )
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_prefixed_database_url_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://platform/db")
    monkeypatch.setenv("PHYSICS_ATLAS_DATABASE_URL", "sqlite://")

    assert Settings(_env_file=None).database_url == "sqlite://"


@pytest.mark.parametrize(
    "database_url",
    ["sqlite://", "postgresql+psycopg://atlas:secret@postgres/atlas"],
)
def test_settings_preserve_explicit_driver_urls(database_url: str) -> None:
    assert (
        Settings(_env_file=None, database_url=database_url).database_url == database_url
    )


def test_settings_accept_railway_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHYSICS_ATLAS_PORT", raising=False)
    monkeypatch.setenv("PORT", "4317")

    assert Settings(_env_file=None).port == 4317


def test_prefixed_port_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "4317")
    monkeypatch.setenv("PHYSICS_ATLAS_PORT", "8123")

    assert Settings(_env_file=None).port == 8123


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port"])
def test_settings_reject_invalid_port(
    monkeypatch: pytest.MonkeyPatch,
    port: str,
) -> None:
    monkeypatch.delenv("PHYSICS_ATLAS_PORT", raising=False)
    monkeypatch.setenv("PORT", port)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_reject_fixture_mode_in_production() -> None:
    with pytest.raises(ValidationError, match="fixture mode must be disabled"):
        Settings(
            _env_file=None,
            database_url="sqlite://",
            environment="production",
            fixture_mode=True,
        )

    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        environment="production",
        fixture_mode=False,
    )
    assert settings.environment == "production"
    assert settings.fixture_mode is False


def test_api_entrypoint_uses_configured_port(monkeypatch: pytest.MonkeyPatch) -> None:
    uvicorn_run = Mock()
    monkeypatch.setattr(main, "get_settings", lambda: Settings(port=4317))
    monkeypatch.setattr(main.uvicorn, "run", uvicorn_run)

    main.run()

    uvicorn_run.assert_called_once_with(
        "physics_atlas_api.main:app",
        host="0.0.0.0",  # noqa: S104 - verifies the container entrypoint
        port=4317,
        reload=False,
    )
