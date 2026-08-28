import json
from pathlib import Path

from sqlalchemy.orm import Session

from physics_atlas_api import models
from physics_atlas_api.seed import ensure_reference_data, seed_reference_data

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DATA = REPOSITORY_ROOT / "src" / "data" / "demo" / "atlas.json"


def test_ensure_reference_data_repairs_a_partial_seed(session: Session) -> None:
    payload = json.loads(REFERENCE_DATA.read_text(encoding="utf-8"))
    seed_reference_data(session, payload)
    session.delete(session.get_one(models.ResearchField, "hep-th"))
    session.delete(session.get_one(models.Country, "country-us"))
    session.delete(session.get_one(models.MetricDefinition, "research_activity_score"))
    session.commit()

    ensure_reference_data(session)

    assert session.get(models.ScienceDomain, "physics") is not None
    assert session.get(models.ResearchField, "hep-th") is not None
    assert session.get(models.Country, "country-us") is not None
    assert session.get(models.MetricDefinition, "research_activity_score") is not None


def test_ensure_reference_data_is_idempotent(session: Session) -> None:
    ensure_reference_data(session)
    domain = session.get_one(models.ScienceDomain, "physics")
    original_created_at = domain.created_at

    ensure_reference_data(session)

    assert (
        session.get_one(models.ScienceDomain, "physics").created_at
        == original_created_at
    )
