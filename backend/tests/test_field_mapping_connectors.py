from pathlib import Path

import pytest

from physics_atlas_api.config import Settings
from physics_atlas_api.connectors.base import SourceRecord
from physics_atlas_api.connectors.factory import build_connectors


def test_arxiv_parser_preserves_primary_secondary_and_foreign_taxonomy_evidence(
    fixture_directory: Path,
) -> None:
    connector = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["arxiv"]
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/2608.99999v1</id>
        <updated>2026-08-29T00:00:00Z</updated>
        <published>2026-08-29T00:00:00Z</published>
        <title>Versioned field mapping fixture</title>
        <summary>Deterministic test metadata.</summary>
        <author><name>Field Mapper</name></author>
        <arxiv:primary_category term="hep-th"
          scheme="http://arxiv.org/schemas/atom" />
        <category term="hep-th" scheme="http://arxiv.org/schemas/atom" />
        <category term="gr-qc" scheme="http://arxiv.org/schemas/atom" />
        <category term="I.2.6" scheme="http://acm.example/taxonomy" />
      </entry>
    </feed>"""

    record = connector._records(xml)[0]  # type: ignore[attr-defined]
    evidence = record.raw["category_evidence"]
    assert [(item["category"], item["role"]) for item in evidence] == [
        ("hep-th", "primary"),
        ("gr-qc", "secondary"),
        ("I.2.6", "unspecified"),
    ]

    normalized = connector.normalize_record(record)
    assert normalized.attributes["atlas_field_candidates"] == ["hep-th", "gr-qc"]
    assert normalized.attributes["field_mapping_confidence"] is None
    assert normalized.attributes["field_mapping_coverage"] == pytest.approx(2 / 3)
    assert normalized.attributes["atlas_field_assignments"] == [
        {"field_id": "hep-th", "weight": pytest.approx(1 / 3)},
        {"field_id": "gr-qc", "weight": pytest.approx(1 / 3)},
    ]
    provenance = normalized.attributes["field_mapping_provenance"]
    assert provenance["category_mappings"][-1]["status"] == "unmapped"
    assert provenance["unmapped_field_mass"] == pytest.approx(1 / 3)


def test_inspire_normalizer_preserves_source_and_does_not_invent_category_role(
    fixture_directory: Path,
) -> None:
    connector = build_connectors(
        Settings(database_url="sqlite://", fixture_mode=True), fixture_directory
    )["inspire"]
    record = SourceRecord(
        provider="inspire",
        source_record_id="field-mapping-fixture",
        raw={
            "titles": [{"title": "INSPIRE field mapping fixture"}],
            "publication_info": [{"year": 2026}],
            "inspire_categories": [
                {"term": "Lattice", "source": "curator"},
                {"term": "Unmapped INSPIRE Category", "source": "legacy"},
            ],
            "authors": [],
        },
    )

    normalized = connector.normalize_record(record)
    assert normalized.attributes["raw_category_evidence"] == [
        {
            "category": "Lattice",
            "role": "unspecified",
            "taxonomy": "inspire-category",
            "source": "curator",
        },
        {
            "category": "Unmapped INSPIRE Category",
            "role": "unspecified",
            "taxonomy": "inspire-category",
            "source": "legacy",
        },
    ]
    assert normalized.attributes["atlas_field_candidates"] == ["hep-lat"]
    assert normalized.attributes["field_mapping_coverage"] == pytest.approx(0.5)
    assert normalized.attributes["atlas_field_assignments"] == [
        {"field_id": "hep-lat", "weight": 0.5}
    ]
    assert normalized.attributes["field_mapping_provenance"][
        "unmapped_field_mass"
    ] == pytest.approx(0.5)
