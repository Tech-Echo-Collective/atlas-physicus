"""Exact structural digest compatibility on bounded synthetic projections."""

from contextlib import nullcontext
from dataclasses import replace
from datetime import date
from unittest.mock import Mock

import pytest

from physics_atlas_api.certification import years as year_rules
from physics_atlas_api.certification.build_cache import (
    bounded_build_verification_cache,
)
from physics_atlas_api.certification.contracts import (
    EvidenceKind,
    EvidenceReference,
    canonical_digest,
)
from physics_atlas_api.certification.years import SourceYearPaperProjection

KINDS: tuple[EvidenceKind, ...] = (
    "canonical-paper-identity",
    "publication-metric-date",
    "field-weight-conservation",
    "provenance-completeness",
)


def _projection(researchers: int = 2) -> SourceYearPaperProjection:
    return SourceYearPaperProjection(
        paper_id="synthetic-digest-fixture",
        publication_date=date(2020, 1, 9),
        occurrence_references=(
            EvidenceReference("test-fixture", "paper", "a" * 64, "snapshot"),
        ),
        field_weights=(("nucl-th", 0.5), ("nucl-ex", 0.5)),
        unmapped_field_mass=0.0,
        field_weight_total=1.0,
        field_weighting_policy_version="synthetic-field-policy-v1",
        entity_shares=tuple(
            ("researcher", f"researcher-{index:04d}", 1 / researchers)
            for index in reversed(range(researchers))
        )
        + (
            ("country", "country-fixture", 1.0),
            ("institution", "institution-fixture", 1.0),
        ),
        unresolved_entity_mass=(
            ("researcher", 0.0),
            ("institution", 0.0),
            ("country", 0.0),
        ),
        attribution_policy_version="synthetic-attribution-policy-v1",
    )


def _legacy_digest(projection: SourceYearPaperProjection, kind: EvidenceKind) -> str:
    # Original eager payload expression, retained as the compatibility oracle.
    values: dict[EvidenceKind, object] = {
        "canonical-paper-identity": {"paper_id": projection.paper_id},
        "publication-metric-date": {
            "paper_id": projection.paper_id,
            "publication_date": projection.publication_date,
        },
        "field-weight-conservation": {
            "paper_id": projection.paper_id,
            "field_weights": tuple(sorted(projection.field_weights)),
            "unmapped_field_mass": projection.unmapped_field_mass,
            "field_weight_total": projection.field_weight_total,
            "field_weighting_policy_version": projection.field_weighting_policy_version,
        },
        "provenance-completeness": {
            "paper_id": projection.paper_id,
            "occurrence_references": projection.occurrence_references,
            "entity_shares": tuple(sorted(projection.entity_shares)),
            "unresolved_entity_mass": tuple(sorted(projection.unresolved_entity_mass)),
            "attribution_policy_version": projection.attribution_policy_version,
        },
    }
    return canonical_digest(values[kind])


@pytest.mark.parametrize("researchers", [2, 3000])
@pytest.mark.parametrize("cached", [False, True])
def test_all_four_digests_match_original_sha256(researchers: int, cached: bool) -> None:
    projection = _projection(researchers)
    expected = tuple(_legacy_digest(projection, kind) for kind in KINDS)
    with (
        bounded_build_verification_cache(stream_large_keys=True)
        if cached
        else nullcontext()
    ):
        for _ in range(2):
            assert tuple(projection.decision_value_digest(kind) for kind in KINDS) == (
                expected
            )


@pytest.mark.parametrize("cached", [False, True])
def test_unsupported_structural_kind_still_fails(cached: bool) -> None:
    projection = _projection()
    with bounded_build_verification_cache() if cached else nullcontext():
        with pytest.raises(
            ValueError,
            match="paper-time-affiliation is not a source-year structural dimension",
        ):
            projection.decision_value_digest("paper-time-affiliation")


def test_only_requested_payload_is_constructed() -> None:
    # Explicitly local monkeypatch lifetime: no changed globals escape the test.
    projection = _projection()
    sorted_spy = Mock(wraps=sorted)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(year_rules, "sorted", sorted_spy, raising=False)
        for kind, expected_sorts in zip(KINDS, (0, 0, 1, 2), strict=True):
            sorted_spy.reset_mock()
            projection.decision_value_digest(kind)
            assert sorted_spy.call_count == expected_sorts


def test_repeated_provenance_payload_reuses_only_exact_immutable_values() -> None:
    projection = _projection()
    digest_spy = Mock(wraps=canonical_digest)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(year_rules, "canonical_digest", digest_spy)
        with bounded_build_verification_cache() as cache:
            original = projection.decision_value_digest("provenance-completeness")
            assert (
                projection.decision_value_digest("provenance-completeness") == original
            )
            assert digest_spy.call_count == 1 and cache.stats.hits == 1
            changed = replace(projection, attribution_policy_version="fixture-v2")
            assert changed.decision_value_digest("provenance-completeness") != original
            assert digest_spy.call_count == 2
            # Even a field not serialized in this dimension remains in the full key.
            changed = replace(projection, publication_date=date(2020, 2, 1))
            assert changed.decision_value_digest("provenance-completeness") == original
            assert digest_spy.call_count == 3
        assert cache.stats.entries == 0


@pytest.mark.parametrize("nested", [False, True])
def test_forged_frozen_mutation_cannot_return_a_stale_digest(nested: bool) -> None:
    projection = _projection()
    with bounded_build_verification_cache():
        original = projection.decision_value_digest("provenance-completeness")
        if nested:
            object.__setattr__(
                projection.occurrence_references[0], "checksum", "b" * 64
            )
        else:
            object.__setattr__(projection, "attribution_policy_version", "forged-v2")
        changed = projection.decision_value_digest("provenance-completeness")
        assert changed != original
        assert changed == _legacy_digest(projection, "provenance-completeness")


def test_forged_invalid_share_remains_invalid_not_a_cached_valid_digest() -> None:
    projection = _projection()
    with bounded_build_verification_cache():
        projection.decision_value_digest("provenance-completeness")
        object.__setattr__(
            projection, "entity_shares", (("researcher", "x", float("nan")),)
        )
        with pytest.raises(ValueError):
            projection.decision_value_digest("provenance-completeness")
        with pytest.raises(ValueError, match="entity attribution ledger is invalid"):
            projection.__post_init__()
