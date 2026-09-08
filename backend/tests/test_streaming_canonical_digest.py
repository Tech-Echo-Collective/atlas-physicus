"""Exact legacy JSON/SHA equivalence on bounded generated and source inputs."""

import hashlib
import json
import random
import tracemalloc
from dataclasses import dataclass, field, make_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from fractions import Fraction

import pytest
from test_launch_attribution import _author, _link
from test_launch_metric_coverage import _build, _proofs

from physics_atlas_api.certification import CertificationError, canonical_digest
from physics_atlas_api.certification.build_cache import bounded_build_verification_cache
from physics_atlas_api.certification.contracts import _canonical_value
from physics_atlas_api.certification.streaming_digest import (
    _CanonicalEncoder,
    streaming_canonical_digest,
)


def legacy_bytes(value: object) -> bytes:
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class Shared:
    z: object
    a: str = "Atlas—物理"


def test_canonical_golden_types_unicode_order_and_collisions() -> None:
    class Status(Enum):
        VALUE = "needs_review"

    @dataclass(frozen=True)
    class Uncached:
        value: object = field(compare=False)

    values = (
        None,
        True,
        False,
        0,
        1,
        -1,
        10**100,
        -0.0,
        0.0,
        1e-20,
        1e20,
        'quotes"\\\n\t\u0000 💫物理',
        {"💫", "\ue000", "\U00010000", "a", "\n"},
        frozenset((Fraction(1, 3), Fraction(1, 2))),
        date(2020, 1, 2),
        datetime(2020, 1, 2, 3, 4, 5, 123456, tzinfo=UTC),
        Decimal("1.00"),
        Fraction(-3, 8),
        Status.VALUE,
        {1: "overwritten", "1": Shared(("retained", 3)), 2: [0, None]},
        {"1": "overwritten", 1: "last insertion wins"},
        Uncached((Shared((1, 2)), {"missing": None, "zero": 0})),
    )
    for value in values:
        expected = legacy_bytes(value)
        encoded: list[bytes] = []
        encoder = _CanonicalEncoder(encoded.append)
        encoder.write(value)
        assert b"".join(encoded) == expected
        assert streaming_canonical_digest(value) == hashlib.sha256(expected).hexdigest()
        with bounded_build_verification_cache():
            assert canonical_digest(value) == hashlib.sha256(expected).hexdigest()


def test_generated_nested_values_keep_exact_persisted_sha() -> None:
    rng = random.Random(781903)  # noqa: S311 -- deterministic test generation, not security

    def generate(depth: int) -> object:
        if depth == 0:
            return rng.choice((None, False, 0, -0.0, 1.25, "é中💫"))
        children = [generate(depth - 1) for _ in range(3)]
        return rng.choice(
            (
                children,
                tuple(children),
                {str(i): v for i, v in enumerate(children)},
                Shared(tuple(children)),
            )
        )

    for _ in range(40):
        value = generate(3)
        assert (
            streaming_canonical_digest(value)
            == hashlib.sha256(legacy_bytes(value)).hexdigest()
        )


def test_scalar_tokens_match_native_json_without_fragment_entries() -> None:
    values = (None, False, True, 0, -7, 10**100, '"\\\n\t\u0000物理💫')
    for ensure_ascii in (False, True):
        for value in values:
            encoded: list[bytes] = []
            encoder = _CanonicalEncoder(encoded.append)
            encoder.write(value, ensure_ascii)
            assert b"".join(encoded) == json.dumps(
                value, ensure_ascii=ensure_ascii, separators=(",", ":")
            ).encode("utf-8")
            assert not encoder.fragments and not encoder.pending


def test_member_token_reuse_remains_bounded_and_keeps_actual_values() -> None:
    encoded: list[bytes] = []
    encoder = _CanonicalEncoder(encoded.append)
    for index in range(140):
        value_type = make_dataclass(f"Record{index}", [("value", object)], frozen=True)
        for value in (None, 0, ("evidence", index)):
            record = value_type(value)
            encoded.clear()
            encoder.write(record)
            assert b"".join(encoded) == legacy_bytes(record)
        assert len(encoder.member_tokens) <= 128


def test_mutable_values_and_unsupported_overwritten_values_fail_closed() -> None:
    mutable = [1, {"data": 2}]
    encoded: list[bytes] = []
    encoder = _CanonicalEncoder(encoded.append)
    encoder.write(mutable)
    assert b"".join(encoded) == legacy_bytes(mutable)
    mutable[1]["data"] = 9  # type: ignore[index]
    encoded.clear()
    encoder.write(mutable)
    assert b"".join(encoded) == legacy_bytes(mutable)
    for value in (
        float("nan"),
        float("inf"),
        b"unsupported",
        {1: float("nan"), "1": "last"},
    ):
        with pytest.raises(CertificationError):
            streaming_canonical_digest(value)


def test_shared_dag_streams_without_expanded_json_memory() -> None:
    leaf = Shared(tuple(f"source-reference-{i:03}" for i in range(40)))
    graph = (leaf,) * 10_000
    expected = hashlib.sha256(legacy_bytes(graph)).hexdigest()
    tracemalloc.start()
    actual = streaming_canonical_digest(graph)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert actual == expected
    assert peak < 2 * 1024 * 1024


def test_representative_existing_source_proof_has_identical_sha() -> None:
    built = _build([[_author(1, [_link("200")]), _author(2, [_link("201")])]])
    proof = _proofs(built)[0]
    expected = canonical_digest((proof, built.source_year))
    assert streaming_canonical_digest((proof, built.source_year)) == expected
    with bounded_build_verification_cache():
        assert canonical_digest((proof, built.source_year)) == expected
