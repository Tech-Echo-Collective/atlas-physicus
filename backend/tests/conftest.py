import json
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from physics_atlas_api.database import Base, create_database_engine
from physics_atlas_api.seed import seed_dataset

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIRECTORY = REPOSITORY_ROOT / "backend" / "fixtures"


@pytest.fixture
def fixture_directory() -> Path:
    return FIXTURE_DIRECTORY


@pytest.fixture
def database_engine(tmp_path: Path) -> Generator[Engine]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'atlas.sqlite'}")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session(database_engine: Engine) -> Generator[Session]:
    with Session(database_engine) as database_session:
        yield database_session


@pytest.fixture
def seeded_session(session: Session) -> Session:
    payload = json.loads(
        (REPOSITORY_ROOT / "src" / "data" / "demo" / "atlas.json").read_text(
            encoding="utf-8"
        )
    )
    seed_dataset(session, payload)
    return session
