"""Write unchanged canonical JSON bytes directly to a bounded hashing sink.

The opt-in ephemeral build preserves the original SHA-256 and JSON format.
Direct writes avoid relaying every fragment through each ancestor of the proof.
No expanded proof dictionary/string is constructed; immutable reuse is per call.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from zoneinfo import ZoneInfo

from .contracts import CertificationError

_FRAGMENT_BYTES = 8 * 1024
_CACHE_BYTES = 32 * 1024 * 1024
_CACHE_ENTRIES = 4_096


class _CanonicalEncoder:
    def __init__(
        self, sink: Callable[[bytes], object], *, active: set[int] | None = None
    ) -> None:
        self.sink = sink
        self.fragments: OrderedDict[tuple[int, bool], tuple[object, bytes]] = (
            OrderedDict()
        )
        self.fragment_bytes = 0
        self.active = set() if active is None else active
        self.pending: dict[tuple[int, bool], bytearray] = {}
        self.member_tokens: dict[tuple[type, bool], tuple[tuple[str, bytes], ...]] = {}

    def chunk(self, payload: bytes) -> None:
        self.sink(payload)
        # Large ancestors stop collecting, but continue streaming to the sink.
        for key in tuple(self.pending):
            buffer = self.pending[key]
            if len(buffer) + len(payload) > _FRAGMENT_BYTES:
                del self.pending[key]
            else:
                buffer.extend(payload)

    @staticmethod
    def scalar(value: object, ensure_ascii: bool) -> bytes:
        if type(value) is str:
            encode = (
                json.encoder.encode_basestring_ascii
                if ensure_ascii
                else json.encoder.encode_basestring
            )
            return encode(value).encode("utf-8")
        if value is None:
            return b"null"
        if type(value) is bool:
            return b"true" if value else b"false"
        if type(value) is int:
            return str(value).encode("ascii")
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=ensure_ascii
        ).encode("utf-8")

    def write(self, value: object, ensure_ascii: bool = False) -> bool:
        # Immutable scalar leaves cannot cycle or contain mutable children.
        # Emit the exact same JSON token without allocating a fragment collector
        # and LRU entry for every field value of every proof.
        if value is None or type(value) in {str, int, bool}:
            self.chunk(self.scalar(value, ensure_ascii))
            return True

        key = id(value), ensure_ascii
        previous = self.fragments.get(key)
        if previous is not None and previous[0] is value:
            self.fragments.move_to_end(key)
            self.chunk(previous[1])
            return True
        if id(value) in self.active:
            raise CertificationError("cyclic certification inputs are unsupported")
        self.active.add(id(value))
        self.pending[key] = bytearray()
        try:
            immutable = self.body(value, ensure_ascii)
        finally:
            self.active.remove(id(value))
            buffer = self.pending.pop(key, None)
        if immutable and buffer is not None:
            payload = bytes(buffer)
            while self.fragments and (
                len(self.fragments) >= _CACHE_ENTRIES
                or self.fragment_bytes + len(payload) > _CACHE_BYTES
            ):
                _, (_, evicted) = self.fragments.popitem(last=False)
                self.fragment_bytes -= len(evicted)
            self.fragments[key] = value, payload
            self.fragment_bytes += len(payload)
        return immutable

    def body(self, value: object, ensure_ascii: bool) -> bool:
        if is_dataclass(value) and not isinstance(value, type):
            members = sorted(fields(value), key=lambda member: member.name)
            parameters = getattr(type(value), "__dataclass_params__", None)
            immutable = bool(
                parameters is not None
                and parameters.frozen
                and type(value).__hash__ is not None
                and all(
                    member.compare and member.hash is not False for member in members
                )
            )
            token_key = type(value), ensure_ascii
            tokens = self.member_tokens.get(token_key)
            names = tuple(member.name for member in members)
            if tokens is None or tuple(name for name, _ in tokens) != names:
                tokens = tuple(
                    (name, self.scalar(name, ensure_ascii) + b":") for name in names
                )
                if len(self.member_tokens) < 128:
                    self.member_tokens[token_key] = tokens
            self.chunk(b"{")
            for index, (name, token) in enumerate(tokens):
                if index:
                    self.chunk(b",")
                self.chunk(token)
                child_immutable = self.write(getattr(value, name), ensure_ascii)
                immutable = immutable and child_immutable
            self.chunk(b"}")
            return immutable
        if isinstance(value, Enum):
            return self.write(value.value, ensure_ascii)
        if isinstance(value, datetime):
            self.chunk(self.scalar(value.isoformat(), ensure_ascii))
            return type(value) is datetime and (
                value.tzinfo is None or type(value.tzinfo) in {timezone, ZoneInfo}
            )
        if isinstance(value, date):
            self.chunk(self.scalar(value.isoformat(), ensure_ascii))
            return type(value) is date
        if isinstance(value, (Decimal, Fraction)):
            self.chunk(self.scalar(str(value), ensure_ascii))
            return type(value) in {Decimal, Fraction}
        if isinstance(value, dict):
            # Overwritten values must still be validated, without emitting bytes.
            selected: dict[str, object] = {}
            for key, child in value.items():
                text_key = str(key)
                if text_key in selected:
                    _CanonicalEncoder(lambda _: None, active=self.active).write(
                        selected[text_key], ensure_ascii
                    )
                selected[text_key] = child
            self.chunk(b"{")
            for index, key in enumerate(sorted(selected)):
                if index:
                    self.chunk(b",")
                self.chunk(self.scalar(key, ensure_ascii))
                self.chunk(b":")
                self.write(selected[key], ensure_ascii)
            self.chunk(b"}")
            return False
        if isinstance(value, (tuple, list)):
            immutable = type(value) is tuple
            self.chunk(b"[")
            for index, child in enumerate(value):
                if index:
                    self.chunk(b",")
                child_immutable = self.write(child, ensure_ascii)
                immutable = immutable and child_immutable
            self.chunk(b"]")
            return immutable
        if isinstance(value, (set, frozenset)):
            # Legacy sorting uses ensure_ascii=True, unlike final encoding.
            ordered: list[tuple[bytes, object]] = []
            sorting_bytes = 0
            for child in value:
                buffer = bytearray()

                def collect(chunk: bytes, buffer: bytearray = buffer) -> None:
                    nonlocal sorting_bytes
                    sorting_bytes += len(chunk)
                    if sorting_bytes > _CACHE_BYTES:
                        raise CertificationError(
                            "canonical set ordering exceeds bounded build memory"
                        )
                    buffer.extend(chunk)

                _CanonicalEncoder(collect, active=self.active).write(child, True)
                ordered.append((bytes(buffer), child))
            ordered.sort(key=lambda pair: pair[0])
            self.chunk(b"[")
            for index, (_, child) in enumerate(ordered):
                if index:
                    self.chunk(b",")
                self.write(child, ensure_ascii)
            self.chunk(b"]")
            return False
        if isinstance(value, float):
            if not math.isfinite(value):
                raise CertificationError("certification inputs must be finite")
            self.chunk(self.scalar(value, ensure_ascii))
            return type(value) is float
        if value is None or isinstance(value, (str, int, bool)):
            self.chunk(self.scalar(value, ensure_ascii))
            return value is None or type(value) in {str, int, bool}
        raise CertificationError(
            f"unsupported certification digest value: {type(value).__name__}"
        )


def streaming_canonical_digest(value: object) -> str:
    digest = hashlib.sha256()
    encoder = _CanonicalEncoder(digest.update)
    try:
        encoder.write(value)
        return digest.hexdigest()
    finally:
        encoder.fragments.clear()
        encoder.pending.clear()
        encoder.fragment_bytes = 0
