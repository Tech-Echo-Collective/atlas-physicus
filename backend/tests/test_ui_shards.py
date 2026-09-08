"""Bounded offline transport proofs; fixtures never authorize public metrics."""

import copy
import gzip
import json
from dataclasses import replace

import pytest
from test_launch_entities import _fixture

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.automation import (
    UNAMBIGUOUS_RESEARCHER_RULE_VERSION,
)
from physics_atlas_api.certification.launch_entities import build_launch_entities
from physics_atlas_api.metrics import ui_shards


@pytest.fixture
def projection():  # type: ignore[no-untyped-def]
    papers, attributions = _fixture(extra_paper=True)
    options = {
        "geographic_views": (),
        "researcher_projection_version": UNAMBIGUOUS_RESEARCHER_RULE_VERSION,
    }
    inline = build_launch_entities(papers, attributions, **options)
    sink = ui_shards.UIShardBuilder("independent-release-version")
    streamed = build_launch_entities(
        papers, attributions, relationship_sink=sink, **options
    )
    return inline, streamed, sink.finish(streamed.entities)


def _documents(result):  # type: ignore[no-untyped-def]
    return {path: json.loads(gzip.decompress(data)) for _, path, data in result.assets}


def test_stream_restores_every_record_provenance_and_paper_time_link(projection):  # type: ignore[no-untyped-def]
    inline, streamed, result = projection
    result.validate(streamed.entities)
    original = inline.entities.model_dump(mode="json", by_alias=True, exclude_none=True)
    restored = streamed.entities.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    documents = _documents(result)
    for kind in ui_shards.KINDS:
        assert restored[kind] == []
        restored[kind] = [
            row
            for item in result.metadata["shards"]
            if item["kind"] == kind
            for row in documents[item["path"]]["records"]
        ]
        assert len(restored[kind]) == result.metadata["recordCounts"][kind]
        restored[kind].sort(key=lambda row: row["id"])
        original[kind].sort(key=lambda row: row["id"])
    assert restored == original
    assert streamed.source_references == inline.source_references
    assert streamed.entity_counts == inline.entity_counts
    assert streamed.omitted_counts == inline.omitted_counts
    assert streamed.byte_length < inline.byte_length
    index = documents[result.metadata["index"]["path"]]
    assert set(index["paperAuthorCounts"]) == {p["id"] for p in original["papers"]}
    assert set(index["paperAuthorCounts"].values()) == {1}
    for researcher in original["researchers"]:
        assert [
            index["paperIds"][offset]
            for offset in index["researcherPaperIds"][researcher["id"]]
        ] == sorted(
            item["paperId"]
            for item in original["authorships"]
            if item["researcherId"] == researcher["id"]
        )
    assert {a["paperId"] for a in original["affiliations"]} < {
        p["id"] for p in original["papers"]
    }  # Second paper has no affiliation; never invent current employment.


def test_small_shards_are_deterministic_and_each_record_is_stored_once(
    projection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    inline, _, _ = projection
    monkeypatch.setattr(ui_shards, "MAX_UI_SHARD_BYTES", 1600)
    outputs = []
    for _ in range(2):
        builder = ui_shards.UIShardBuilder("release")
        for kind, rows in (
            ("authorships", inline.entities.authorships),
            ("affiliations", inline.entities.affiliations),
            ("externalResources", inline.entities.external_resources),
        ):
            for row in rows:
                builder.add(kind, row)
        core = inline.entities.model_copy(
            update={
                "authorships": [],
                "affiliations": [],
                "external_resources": [],
            }
        )
        result = builder.finish(core)
        result.validate(core)
        assert all(item["decodedBytes"] <= 1600 for item in result.metadata["shards"])
        assert all(not pending for pending in builder.buffers.values())
        assert len(result.metadata["shards"]) > 3
        outputs.append(result)
        with pytest.raises(CertificationError, match="finalized"):
            builder.add("authorships", inline.entities.authorships[0])
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize(
    "failure", ["missing", "checksum", "decoded", "index", "version"]
)
def test_missing_corrupt_or_incomplete_transport_fails_closed(projection, failure):  # type: ignore[no-untyped-def]
    _, streamed, result = projection
    metadata = copy.deepcopy(result.metadata)
    assets = list(result.assets)
    if failure == "missing":
        assets.pop(0)
    elif failure == "checksum":
        key, path, content = assets[0]
        assets[0] = key, path, content[:-1] + bytes([content[-1] ^ 1])
    elif failure == "decoded":
        metadata["shards"][0]["decodedSha256"] = "0" * 64
    elif failure == "index":
        index = _documents(result)[metadata["index"]["path"]]
        index["researcherPaperIds"] = {}
        descriptor, compressed = ui_shards._compressed(
            "ui-index.json.gz", ui_shards._encode(index)
        )
        metadata["index"] = descriptor
        assets[-1] = "ui-index", descriptor["path"], compressed
    else:
        metadata["version"] = "unapproved-transport-version"
    with pytest.raises(CertificationError):
        replace(result, metadata=metadata, assets=tuple(assets)).validate(
            streamed.entities
        )


def test_duplicate_inline_and_orphan_relations_are_refused(projection):  # type: ignore[no-untyped-def]
    inline, streamed, result = projection
    with pytest.raises(CertificationError, match="both inline"):
        result.validate(inline.entities)
    with pytest.raises(CertificationError, match="exact core/author link"):
        result.validate(streamed.entities.model_copy(update={"researchers": []}))
    builder = ui_shards.UIShardBuilder("release")
    builder.add("authorships", inline.entities.authorships[0])
    with pytest.raises(CertificationError, match="duplicate"):
        builder.add("authorships", inline.entities.authorships[0])
    orphan = ui_shards.UIShardBuilder("release")
    orphan.add("affiliations", inline.entities.affiliations[0])
    with pytest.raises(CertificationError, match="exact core/author link"):
        orphan.finish(streamed.entities)


def test_bounds_refuse_without_truncation(projection, monkeypatch):  # type: ignore[no-untyped-def]
    inline, streamed, _ = projection
    with monkeypatch.context() as patch:
        patch.setattr(ui_shards, "MAX_UI_SHARD_BYTES", 5)
        with pytest.raises(CertificationError, match="not truncated"):
            ui_shards.UIShardBuilder("release").add(
                "authorships", inline.entities.authorships[0]
            )
    with monkeypatch.context() as patch:
        patch.setattr(ui_shards, "MAX_UI_SHARDS", 0)
        builder = ui_shards.UIShardBuilder("release")
        builder.add("authorships", inline.entities.authorships[0])
        with pytest.raises(CertificationError, match="no records truncated"):
            builder.finish(streamed.entities)
    with monkeypatch.context() as patch:
        patch.setattr(ui_shards, "MAX_UI_INDEX_BYTES", 1)
        with pytest.raises(CertificationError, match="no index truncated"):
            ui_shards.UIShardBuilder("release").finish(streamed.entities)


def test_sharding_never_satisfies_scientific_activation_gate(projection):  # type: ignore[no-untyped-def]
    from test_metric_activation import complete_evidence
    from test_metric_dataset import NOW, REFERENCE

    from physics_atlas_api.metrics.dataset import build_atlas_dataset

    _, streamed, shards = projection
    with pytest.raises(CertificationError, match="Joint Activation Gate withheld"):
        build_atlas_dataset(
            streamed.entities,
            (),
            replace(complete_evidence(), normalization_validated=False),
            REFERENCE,
            generated_at=NOW,
            ui_shards=shards,
        )
