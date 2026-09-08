"""Cache equivalence and fail-closed checks on bounded synthetic inputs."""

from dataclasses import dataclass, field, replace
from datetime import date
from unittest.mock import Mock

import pytest
from test_automatic_identity_date_admission import _facts
from test_launch_attribution import _author, _link
from test_launch_metric_coverage import _build, _proofs

from physics_atlas_api.certification import CertificationError, canonical_digest
from physics_atlas_api.certification import automation as automatic_rules
from physics_atlas_api.certification import build_cache as cache_rules
from physics_atlas_api.certification import years as year_rules
from physics_atlas_api.certification.build_cache import (
    bounded_build_verification_cache,
    memoize_immutable,
)
from physics_atlas_api.certification.launch_metric_coverage import (
    certify_launch_source_coverage,
)
from physics_atlas_api.certification.launch_years import _projection


@dataclass(frozen=True)
class FrozenInput:
    value: int | float | bool
    version: str = "test-v1"


def test_original_digest_bytes_types_and_versions_are_unchanged() -> None:
    values = (
        FrozenInput(1),
        FrozenInput(1.0),
        FrozenInput(True),
        FrozenInput(-0.0),
        FrozenInput(0.0),
    )
    expected = tuple(canonical_digest(value) for value in values)
    assert len(set(expected)) == len(values)
    with bounded_build_verification_cache() as cache:
        assert tuple(canonical_digest(value) for value in values) == expected
        assert tuple(canonical_digest(value) for value in values) == expected
        assert cache.stats.hits == len(values)
        assert canonical_digest(replace(values[0], version="test-v2")) not in expected
        assert cache.stats.misses == len(values) + 1
    assert cache.stats.entries == 0


def test_mutable_nested_and_compare_excluded_inputs_are_never_cached() -> None:
    @dataclass(frozen=True)
    class Ignored:
        value: int = field(compare=False)

    @dataclass(frozen=True)
    class Unhashed:
        value: int = field(hash=False)

    operation = Mock(return_value=1)
    with bounded_build_verification_cache() as cache:
        for value in (
            [1],
            {"data": [1]},
            (FrozenInput(1), [2]),
            Ignored(1),
            Unhashed(1),
        ):
            memoize_immutable("test", (value,), operation)
            memoize_immutable("test", (value,), operation)
        assert operation.call_count == 10
        assert cache.stats.entries == 0 and cache.stats.bypasses == 10


def test_mutation_or_exception_cannot_poison_subsequent_use() -> None:
    operation = Mock(side_effect=[FrozenInput(1), FrozenInput(1)])
    with bounded_build_verification_cache() as cache:
        result = memoize_immutable("test", (FrozenInput(1),), operation)
        object.__setattr__(result, "value", 9)
        recovered = memoize_immutable("test", (FrozenInput(1),), operation)
        assert recovered.value == 1 and operation.call_count == 2
        failing = Mock(side_effect=ValueError("invalid source"))
        for _ in range(2):
            with pytest.raises(ValueError, match="invalid source"):
                memoize_immutable("invalid", (FrozenInput(2),), failing)
        assert failing.call_count == 2
    assert cache.stats.entries == 0


def test_shared_immutable_graph_is_bounded_by_unique_nodes_not_expansion() -> None:
    child = FrozenInput(7)
    shared = (child,) * 100
    graph = (shared,) * 100
    operation = Mock(return_value=1)
    with bounded_build_verification_cache(maximum_key_nodes=16) as cache:
        memoize_immutable("shared", (graph,), operation)
        memoize_immutable("shared", (graph,), operation)
        assert operation.call_count == 1
        assert cache.stats.hits == 1 and cache.stats.bypasses == 0
        # Per-call identity reuse never hides changes to a nested frozen object.
        object.__setattr__(child, "value", 9)
        memoize_immutable("shared", (graph,), operation)
        assert operation.call_count == 2 and cache.stats.misses == 2
    assert cache.stats.entries == 0


def test_tiny_digest_churn_cannot_evict_bounded_expensive_paper_projections() -> None:
    project = Mock(side_effect=lambda: FrozenInput(1))
    digest = Mock(return_value="a" * 64)
    with bounded_build_verification_cache(maximum_entries=6) as cache:
        for paper in range(3):
            memoize_immutable("bounded-launch-source-projection-v1", (paper,), project)
        for scalar in range(100):
            memoize_immutable("legacy-canonical-json-sha256-v1", (scalar,), digest)
        for paper in range(3):
            memoize_immutable("bounded-launch-source-projection-v1", (paper,), project)
        assert project.call_count == 3
        assert cache.stats.entries == cache.stats.peak_entries == 6
        memoize_immutable("bounded-launch-source-projection-v1", (3,), project)
        assert len(cache._reserved) == 3
        assert cache.stats.entries == 6
    assert cache.stats.entries == 0 and not cache._reserved and not cache._ordinary


def test_cache_limits_context_isolation_and_finally_cleanup() -> None:
    operation = Mock(return_value=1)
    with pytest.raises(RuntimeError):
        with bounded_build_verification_cache(
            maximum_entries=2, maximum_key_nodes=16
        ) as cache:
            for value in range(6):
                memoize_immutable("test", (value,), operation)
            assert cache.stats.entries == cache.stats.peak_entries == 2
            memoize_immutable("oversize", (tuple(range(30)),), operation)
            assert cache.stats.bypasses == 1
            with bounded_build_verification_cache() as nested:
                memoize_immutable("test", (5,), operation)
                assert nested.stats.misses == 1
            assert nested.stats.entries == 0
            before = operation.call_count
            memoize_immutable("test", (5,), operation)
            assert operation.call_count == before
            raise RuntimeError("build interrupted")
    assert cache.stats.entries == 0
    before = operation.call_count
    memoize_immutable("test", (5,), operation)
    memoize_immutable("test", (5,), operation)
    assert operation.call_count == before + 2


def test_streaming_key_cache_covers_large_graph_without_a_total_node_bypass() -> None:
    graph = tuple(FrozenInput(value) for value in range(300))
    expected_hash = canonical_digest(graph)
    operation = Mock(return_value=graph)
    with bounded_build_verification_cache(
        maximum_entries=4, maximum_key_nodes=16, stream_large_keys=True
    ) as cache:
        for _ in range(2):
            assert memoize_immutable("large", (graph,), operation) is graph
            assert canonical_digest(graph) == expected_hash
        assert operation.call_count == 1
        assert cache.stats.hits == 2 and cache.stats.bypasses == 0
    assert cache.stats.entries == 0


def test_streaming_key_eviction_cannot_hide_changed_inputs_or_cached_results() -> None:
    graph = tuple(FrozenInput(value) for value in range(100))
    operation = Mock(side_effect=lambda: tuple(FrozenInput(v) for v in range(100)))
    with bounded_build_verification_cache(
        maximum_key_nodes=16, stream_large_keys=True
    ) as cache:
        first = memoize_immutable("large", (graph,), operation)
        # This early object has long since left the per-call 16-entry LRU.
        object.__setattr__(graph[0], "version", "different-source-version")
        second = memoize_immutable("large", (graph,), operation)
        assert second is not first and operation.call_count == 2
        object.__setattr__(second[0], "value", 999)
        third = memoize_immutable("large", (graph,), operation)
        assert third[0].value == 0 and operation.call_count == 3
        assert cache.stats.bypasses == 0


def test_streaming_key_retains_type_distinctions_and_fails_closed_on_mutability() -> (
    None
):
    prefix = tuple(range(100))
    operation = Mock(return_value=1)

    @dataclass(frozen=True)
    class Loop:
        child: object

    cycle = Loop(None)
    object.__setattr__(cycle, "child", cycle)
    with bounded_build_verification_cache(
        maximum_key_nodes=16, stream_large_keys=True
    ) as cache:
        for value in (1, True, 1.0, 0.0, -0.0):
            memoize_immutable("types", (prefix, FrozenInput(value)), operation)
        assert cache.stats.misses == 5
        for value in ([1], {"mutable": 1}, cycle):
            memoize_immutable("invalid", (prefix, value), operation)
        assert cache.stats.bypasses == 3


def test_streaming_key_resident_memo_is_bounded_and_fingerprints_fixed_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = cache_rules.OrderedDict
    peaks: list[int] = []

    class TrackingMemo(original):  # type: ignore[type-arg]
        def __setitem__(self, key, value) -> None:  # type: ignore[no-untyped-def]
            super().__setitem__(key, value)
            assert len(value[1]) == 40  # Type tag + fixed SHA-256; no large leaf copy.
            peaks.append(len(self))

    monkeypatch.setattr(cache_rules, "OrderedDict", TrackingMemo)
    graph = tuple((FrozenInput(i), str(i) * 10_000) for i in range(120))
    small = cache_rules._immutable_key(graph, 16, stream_large_keys=True)
    large = cache_rules._immutable_key(graph, 10_000, stream_large_keys=True)
    assert small == large  # Eviction changes only recomputation, never identity.
    assert max(peaks[:120]) <= 16
    peaks.clear()
    cache_rules._immutable_key(graph, 16, stream_large_keys=True)
    assert max(peaks) <= 16


@pytest.mark.parametrize("stream_large_keys", [False, True])
def test_projection_is_identical_and_invalid_replacements_still_fail(
    stream_large_keys: bool,
) -> None:
    built = _build([[_author(1, [_link("200")]), _author(2, [_link("201")])]])
    proof = _proofs(built)[0]
    expected = _projection(proof.source_paper, proof.attribution_results)
    expected_hash = canonical_digest(expected)
    with bounded_build_verification_cache(
        maximum_key_nodes=32 if stream_large_keys else 1_000_000,
        stream_large_keys=stream_large_keys,
    ) as cache:
        first = _projection(proof.source_paper, proof.attribution_results)
        second = _projection(proof.source_paper, proof.attribution_results)
        assert first == second == expected
        assert canonical_digest(first) == expected_hash
        assert cache.stats.hits > 0
        bad = replace(proof.attribution_results[0], version="invalid-rule")
        with pytest.raises(CertificationError, match="exact paper occurrence"):
            _projection(proof.source_paper, (bad,))
        changed_ref = replace(
            proof.attribution_results[0].paper_reference, checksum="0" * 64
        )
        with pytest.raises(CertificationError):
            _projection(
                proof.source_paper,
                (replace(proof.attribution_results[0], paper_reference=changed_ref),),
            )
    assert cache.stats.entries == 0


@pytest.mark.parametrize("stream_large_keys", [False, True])
def test_source_year_evaluation_preserves_hashes_and_rechecks_policy_and_source(
    monkeypatch: pytest.MonkeyPatch,
    stream_large_keys: bool,
) -> None:
    built = _build([[_author(1, [_link("200")]), _author(2, [_link("201")])]])
    year = built.source_year
    assert year is not None
    expected = year_rules._evaluate_source_year(year.evidence, year.coverage)
    expected_hash = canonical_digest(expected)
    with bounded_build_verification_cache(
        maximum_key_nodes=64 if stream_large_keys else 1_000_000,
        stream_large_keys=stream_large_keys,
    ) as cache:
        for _ in range(2):
            assert (
                year_rules._evaluate_source_year(year.evidence, year.coverage)
                == expected
            )
            year.__post_init__()
        assert canonical_digest(expected) == expected_hash
        before = cache.stats.hits
        year.__post_init__()
        assert cache.stats.hits > before
        # Same evidence object, changed declared scientific rule: never stale-hit.
        monkeypatch.setattr(
            year_rules, "SOURCE_YEAR_CERTIFICATION_RULE_VERSION", "invalid-rule"
        )
        with pytest.raises(CertificationError, match="does not reconstruct"):
            year.__post_init__()
        monkeypatch.undo()
        changed = replace(
            year.evidence,
            paper_projections=(
                replace(
                    year.evidence.paper_projections[0],
                    publication_date=date(2020, 2, 1),
                ),
            ),
        )
        with pytest.raises(CertificationError, match="does not reconstruct"):
            replace(year, evidence=changed)
        assert (
            year_rules._evaluate_source_year(year.evidence, year.coverage) == expected
        )
    assert cache.stats.entries == 0


def test_conditional_and_original_source_quality_never_share_cache() -> None:
    covered = certify_launch_source_coverage(
        _build([[_author(1, [_link("200")]), _author(2)]])
    ).source_year
    enumerated = year_rules.certify_source_year(
        year_rules.EnumeratedLaunchSourceYearEvidence(**vars(covered.evidence)),
        covered.coverage,
    )
    assert enumerated.state == "insufficient_evidence"
    original = year_rules.source_quality_certification(enumerated)
    with bounded_build_verification_cache() as cache:
        conditional = year_rules.qualify_observed_release_source_year(enumerated)
        assert conditional.state == "certified"
        assert year_rules.source_quality_certification(conditional) == original
        assert (
            year_rules.source_quality_certification(conditional).state
            == "insufficient_evidence"
        )
        assert conditional.coverage == enumerated.coverage
        conditional.__post_init__()
    assert cache.stats.entries == 0


def test_paper_identity_view_reuses_exact_decision_not_mutated_facts_or_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = _facts(authors=[{"recid": "42"}, {"recid": "43"}])
    expected = automatic_rules._automatic_paper_identity_view(
        facts, "researcher-identity"
    )
    expected_digest = canonical_digest(expected)
    with bounded_build_verification_cache() as cache:
        assert (
            automatic_rules._automatic_paper_identity_view(facts, "researcher-identity")
            == expected
        )
        before = cache.stats.hits
        assert (
            canonical_digest(
                automatic_rules._automatic_paper_identity_view(
                    facts, "researcher-identity"
                )
            )
            == expected_digest
        )
        assert cache.stats.hits > before
        # A partial paper is not certified just because another paper was cached.
        partial = _facts(authors=[{"recid": "42"}, {}])
        assert (
            automatic_rules._automatic_paper_identity_view(
                partial, "researcher-identity"
            ).state
            == "insufficient_evidence"
        )
        decision = automatic_rules.automatic_paper_identity_decision(
            facts, evidence_kind="researcher-identity"
        )
        monkeypatch.setattr(
            automatic_rules, "AUTOMATIC_RESEARCHER_RULE_VERSION", "invalid-rule"
        )
        with pytest.raises(CertificationError, match="does not reconstruct"):
            decision.__post_init__()
        monkeypatch.undo()
        object.__setattr__(facts.authors[0].facts[0], "value", "0")
        changed = automatic_rules._automatic_paper_identity_view(
            facts, "researcher-identity"
        )
        assert changed.state == "insufficient_evidence" and changed != expected
        with pytest.raises(CertificationError, match="does not reconstruct"):
            decision.__post_init__()
    assert cache.stats.entries == 0
