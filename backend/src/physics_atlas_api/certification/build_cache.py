"""Bounded, opt-in reuse of pure calculations during one ephemeral build.

No evidence approval, I/O or persistent cache. Keys contain every immutable
input value and its exact type; mutable inputs use the original path. Oversized
graphs also use that path unless bounded-resident key traversal is opted into.
The first successful calculation still performs all existing checks. A changed
source fact, checksum or version is a different key. Exceptions are not cached.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import cast
from zoneinfo import ZoneInfo

_MISSING = object()
_EXPENSIVE_NAMESPACES = frozenset(
    {
        "bounded-launch-source-projection-v1",
        "bounded-launch-structural-view-v1",
        "exact-source-year-evaluation-v1",
        "exact-coverage-certification-v1",
    }
)
_ACTIVE: ContextVar[BuildVerificationCache | None] = ContextVar(
    "atlas_build_verification_cache", default=None
)


def _immutable_key(
    value: object, maximum_nodes: int, *, stream_large_keys: bool = False
) -> bytes:
    """Internal fixed-size DAG key, never a scientific checksum representation.

    The default limits total unique nodes. The explicit launch mode instead
    limits resident memo/active entries: evicted objects are recomputed, never
    ignored. Its memo stores fixed-size fingerprints, and child hashes stream
    without an expanded list. No scientific checksum representation changes.

    Both modes discard identity reuse after each key, so even forged mutations
    of frozen nested objects are observed on the next call.
    """
    memo: dict[int, tuple[object, bytes]] = OrderedDict() if stream_large_keys else {}
    active: set[int] = set()

    def node(item: object) -> bytes:
        identity = id(item)
        previous = memo.get(identity)
        if previous is not None and previous[0] is item:
            if isinstance(memo, OrderedDict):
                memo.move_to_end(identity)
            return previous[1]
        if identity in active or len(active) >= maximum_nodes:
            raise TypeError("immutable key is cyclic or exceeds bounded unique nodes")
        if isinstance(memo, OrderedDict):
            while len(memo) + len(active) >= maximum_nodes:
                memo.popitem(last=False)
        elif len(memo) + len(active) >= maximum_nodes:
            raise TypeError("immutable key exceeds bounded unique nodes")
        active.add(identity)
        item_type = type(item)
        # Type identity is process-local by design: this cache is never retained.
        tag = id(item_type).to_bytes(8, "big")
        payload: bytes
        if item is None:
            payload = b""
        elif item_type is str:
            payload = cast(str, item).encode("utf-8")
        elif item_type is bytes:
            payload = cast(bytes, item)
        elif item_type in {bool, int}:
            payload = str(item).encode("ascii")
        elif item_type is float:
            payload = cast(float, item).hex().encode("ascii")
        elif item_type is date:
            payload = cast(date, item).isoformat().encode("ascii")
        elif item_type is datetime:
            timestamp = cast(datetime, item)
            if timestamp.tzinfo is not None and type(timestamp.tzinfo) not in {
                timezone,
                ZoneInfo,
            }:
                raise TypeError("cache refuses mutable timezone implementations")
            payload = repr(
                (timestamp.isoformat(), timestamp.fold, str(timestamp.tzinfo))
            ).encode("utf-8")
        elif item_type is Fraction:
            fraction = cast(Fraction, item)
            payload = repr((fraction.numerator, fraction.denominator)).encode("ascii")
        elif item_type is Decimal:
            payload = str(item).encode("ascii")
        elif isinstance(item, Enum):
            name = item.name.encode("utf-8")
            payload = len(name).to_bytes(8, "big") + name + node(item.value)
        elif item_type is tuple:
            digest = hashlib.sha256()
            for member_value in cast(tuple[object, ...], item):
                child = node(member_value)
                digest.update(len(child).to_bytes(8, "big"))
                digest.update(child)
            payload = digest.digest()
        elif is_dataclass(item) and not isinstance(item, type):
            parameters = getattr(item_type, "__dataclass_params__", None)
            members = fields(item)
            if (
                parameters is None
                or not parameters.frozen
                or item_type.__hash__ is None
                or any(not member.compare or member.hash is False for member in members)
            ):
                raise TypeError(
                    "cache requires fully comparable frozen dataclass inputs"
                )
            digest = hashlib.sha256()
            for member in members:
                name, child = (
                    member.name.encode("utf-8"),
                    node(getattr(item, member.name)),
                )
                digest.update(len(name).to_bytes(8, "big"))
                digest.update(name)
                digest.update(len(child).to_bytes(8, "big"))
                digest.update(child)
            payload = digest.digest()
        else:
            raise TypeError("cache refuses mutable or unsupported input")
        # Scalar strings/bytes must not turn a fixed-entry memo into a second
        # expanded data store. This is only an internal process-local cache key.
        result = tag + (
            hashlib.sha256(payload).digest() if stream_large_keys else payload
        )
        active.remove(identity)
        memo[identity] = item, result
        return result

    return hashlib.sha256(node(value)).digest()


@dataclass(frozen=True)
class BuildCacheStats:
    hits: int
    misses: int
    bypasses: int
    entries: int
    peak_entries: int


class BuildVerificationCache:
    def __init__(
        self,
        maximum_entries: int,
        maximum_key_nodes: int,
        *,
        stream_large_keys: bool = False,
    ) -> None:
        if (
            type(maximum_entries) is not int
            or not 1 <= maximum_entries <= 20_000
            or type(maximum_key_nodes) is not int
            or not 16 <= maximum_key_nodes <= 1_000_000
            or type(stream_large_keys) is not bool
        ):
            raise ValueError("verification cache requires explicit bounded limits")
        self.maximum_entries = maximum_entries
        self.maximum_key_nodes = maximum_key_nodes
        self.stream_large_keys = stream_large_keys
        self._values: OrderedDict[object, tuple[object, object]] = OrderedDict()
        self._reserved: OrderedDict[object, None] = OrderedDict()
        self._ordinary: OrderedDict[object, None] = OrderedDict()
        self._reserved_capacity = maximum_entries // 2
        self._hits = self._misses = self._bypasses = self._peak_entries = 0

    @property
    def stats(self) -> BuildCacheStats:
        return BuildCacheStats(
            self._hits,
            self._misses,
            self._bypasses,
            len(self._values),
            self._peak_entries,
        )

    def clear(self) -> None:
        self._values.clear()
        self._reserved.clear()
        self._ordinary.clear()

    def _forget(self, key: object) -> None:
        del self._values[key]
        self._reserved.pop(key, None)
        self._ordinary.pop(key, None)

    def calculate[ResultT](
        self,
        namespace: str,
        inputs: tuple[object, ...],
        operation: Callable[[], ResultT],
    ) -> ResultT:
        try:
            key = (
                namespace,
                _immutable_key(
                    inputs,
                    self.maximum_key_nodes,
                    stream_large_keys=self.stream_large_keys,
                ),
            )
        except TypeError:
            self._bypasses += 1
            return operation()
        existing = self._values.get(key, _MISSING)
        if existing is not _MISSING:
            saved_key, saved_value = cast(tuple[object, object], existing)
            try:
                unchanged = saved_key == _immutable_key(
                    saved_value,
                    self.maximum_key_nodes,
                    stream_large_keys=self.stream_large_keys,
                )
            except TypeError:
                unchanged = False
            if unchanged:
                self._hits += 1
                self._values.move_to_end(key)
                queue = self._reserved if key in self._reserved else self._ordinary
                queue.move_to_end(key)
                return cast(ResultT, saved_value)
            # Even an explicit bypass of a frozen dataclass must not poison reuse.
            self._forget(key)
        self._misses += 1
        result = operation()
        try:
            result_key = _immutable_key(
                result, self.maximum_key_nodes, stream_large_keys=self.stream_large_keys
            )
        except TypeError:
            self._bypasses += 1
            return result
        reserved = namespace in _EXPENSIVE_NAMESPACES and self._reserved_capacity > 0
        if reserved and len(self._reserved) >= self._reserved_capacity:
            self._forget(next(iter(self._reserved)))
        elif len(self._values) >= self.maximum_entries:
            # Thousands of tiny per-author SHA entries must not evict every
            # expensive paper projection before the next coverage pass. Reserve
            # at most half the same global entry budget, not an additional cache.
            victims = self._ordinary if self._ordinary else self._reserved
            self._forget(next(iter(victims)))
        self._values[key] = result_key, result
        (self._reserved if reserved else self._ordinary)[key] = None
        self._peak_entries = max(self._peak_entries, len(self._values))
        return result


@contextmanager
def bounded_build_verification_cache(
    *,
    maximum_entries: int = 2_048,
    maximum_key_nodes: int = 1_000_000,
    stream_large_keys: bool = False,
) -> Iterator[BuildVerificationCache]:
    """One in-memory scope; all values are discarded even after exceptions.

    With stream_large_keys, maximum_key_nodes bounds resident traversal entries,
    not overall graph size. The bounded LRU may recompute evicted shared nodes.
    This option grants no evidence authority and never skips first validation.
    """
    cache = BuildVerificationCache(
        maximum_entries, maximum_key_nodes, stream_large_keys=stream_large_keys
    )
    token = _ACTIVE.set(cache)
    try:
        yield cache
    finally:
        cache.clear()
        _ACTIVE.reset(token)


def memoize_immutable[ResultT](
    namespace: str, inputs: tuple[object, ...], operation: Callable[[], ResultT]
) -> ResultT:
    cache = _ACTIVE.get()
    return (
        operation() if cache is None else cache.calculate(namespace, inputs, operation)
    )


def build_verification_cache_active() -> bool:
    return _ACTIVE.get() is not None
