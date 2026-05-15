"""Shared cache types and immutable entry structures."""

from __future__ import annotations

import hashlib
import hmac
import struct
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import cast

from ftllexengine.core.value_types import FluentNumber
from ftllexengine.diagnostics import FrozenFluentError

__all__ = [
    "_DEFAULT_MAX_ERRORS_PER_ENTRY",
    "CacheStats",
    "HashableValue",
    "IntegrityCacheEntry",
    "_CacheKey",
    "_CacheValue",
    "_estimate_error_payload_bytes",
]


@dataclass(frozen=True, slots=True)
class CacheStats(Mapping[str, int | float | bool]):
    """Immutable cache statistics snapshot returned by ``IntegrityCache``.

    Premise:
        Operational evidence is part of the cache contract, not an incidental
        debugging convenience.

    Reason:
        Returning a mutable ``dict`` weakens the public surface by suggesting
        callers can edit cache state. This snapshot behaves like a read-only
        mapping for ergonomics while keeping the contract immutable.
    """

    size: int
    maxsize: int
    max_entry_payload_bytes: int
    max_errors_per_entry: int
    hits: int
    misses: int
    hit_rate: float
    unhashable_skips: int
    oversize_skips: int
    error_bloat_skips: int
    combined_payload_skips: int
    corruption_detected: int
    integrity_events_emitted: int
    idempotent_writes: int
    write_once_conflicts: int
    uncacheable_function_skips: int
    sequence: int
    cache_generation: int
    write_once: bool
    debug_log_enabled: bool
    debug_log_entries: int

    def __getitem__(self, key: str) -> int | float | bool:
        """Provide mapping-style access for existing operational call sites."""
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return cast("int | float | bool", getattr(self, key))

    def __iter__(self) -> Iterator[str]:
        """Iterate over public statistic field names in declaration order."""
        return iter(self.__dataclass_fields__)

    def __len__(self) -> int:
        """Return the number of exposed cache statistic fields."""
        return len(self.__dataclass_fields__)

    def as_dict(self) -> dict[str, int | float | bool]:
        """Materialize an ordinary ``dict`` when a concrete mapping is required."""
        return {key: self[key] for key in self}


_DEFAULT_MAX_ERRORS_PER_ENTRY: int = 50
_PAYLOAD_BASE_BYTES: int = 8


def _encoded_length(value: str) -> int:
    """Return the stored UTF-8 byte length for one text field."""
    return len(value.encode("utf-8", errors="surrogatepass"))


def _estimate_error_payload_bytes(error: FrozenFluentError) -> int:
    """Estimate the serialized payload bytes retained for one cached error.

    Premise:
        The cache budget must describe what the cache actually retains, not a
        vague approximation of process memory.

    Reason:
        A payload-byte estimate is deterministic and portable across Python
        builds, unlike object-allocator overhead. The cache therefore limits
        retained error payload, while overall entry count stays bounded by
        ``maxsize``.
    """
    payload = _PAYLOAD_BASE_BYTES + _encoded_length(error.message)

    if error.diagnostic is not None:
        diagnostic = error.diagnostic
        payload += _encoded_length(diagnostic.code.name)
        payload += _encoded_length(diagnostic.message)
        for attr in (
            diagnostic.hint,
            diagnostic.help_url,
            diagnostic.function_name,
            diagnostic.argument_name,
            diagnostic.expected_type,
            diagnostic.received_type,
            diagnostic.ftl_location,
        ):
            if attr is not None:
                payload += _encoded_length(attr)
        if diagnostic.span is not None:
            payload += 16
        if diagnostic.resolution_path is not None:
            for path_element in diagnostic.resolution_path:
                payload += _encoded_length(path_element)

    if error.context is not None:
        context = error.context
        payload += _encoded_length(context.input_value)
        payload += _encoded_length(context.locale_code)
        payload += _encoded_length(context.parse_type)
        payload += _encoded_length(context.fallback_value)

    return payload


type HashableValue = (
    str
    | int
    | bool
    | Decimal
    | datetime
    | date
    | FluentNumber
    | None
    | tuple["HashableValue", ...]
    | frozenset["HashableValue"]
)

type _CacheKey = (
    tuple[str, tuple[tuple[str, HashableValue], ...], str | None, str, bool, int]
)
type _CacheValue = tuple[str, tuple[FrozenFluentError, ...]]


@dataclass(frozen=True, slots=True)
class IntegrityCacheEntry:
    """Immutable cache entry with accidental-corruption detection metadata.

    Premise:
        Cache entries can outlive the request that produced them.

    Reason:
        The entry stores the sanitized error snapshot returned by
        ``FrozenFluentError.sanitized_for_cache()`` rather than the live error
        object, so retention follows the cache privacy contract instead of the
        transient runtime contract.
    """

    formatted: str
    errors: tuple[FrozenFluentError, ...]
    checksum: bytes
    created_at: float
    sequence: int
    key_hash: bytes
    content_hash: bytes = field(init=False, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        """Compute and store ``content_hash`` after field initialization."""
        object.__setattr__(
            self, "content_hash", self._compute_content_hash(self.formatted, self.errors)
        )

    @classmethod
    def create(
        cls,
        formatted: str,
        errors: tuple[FrozenFluentError, ...],
        sequence: int,
        key_hash: bytes,
    ) -> IntegrityCacheEntry:
        """Create an entry with computed accidental-corruption digest."""
        created_at = time.monotonic()
        checksum = cls._compute_checksum(formatted, errors, created_at, sequence, key_hash)
        return cls(
            formatted=formatted,
            errors=errors,
            checksum=checksum,
            created_at=created_at,
            sequence=sequence,
            key_hash=key_hash,
        )

    @staticmethod
    def _feed_errors(h: hashlib.blake2b, errors: tuple[FrozenFluentError, ...]) -> None:
        """Feed the error sequence into an active hasher."""
        h.update(len(errors).to_bytes(4, "big"))
        for error in errors:
            h.update(b"\x01")
            h.update(error.content_hash)

    @staticmethod
    def _compute_checksum(
        formatted: str,
        errors: tuple[FrozenFluentError, ...],
        created_at: float,
        sequence: int,
        key_hash: bytes,
    ) -> bytes:
        """Compute a BLAKE2b-128 digest for content plus metadata.

        Premise:
            Cache entries need a cheap detector for accidental mutation and key
            confusion inside the current process.

        Reason:
            This digest is not advertised as tamper evidence against code that
            can rewrite both payload and digest; it is a fail-closed accidental
            corruption detector.
        """
        h = hashlib.blake2b(digest_size=16)
        encoded = formatted.encode("utf-8", errors="surrogatepass")
        h.update(len(encoded).to_bytes(4, "big"))
        h.update(encoded)
        IntegrityCacheEntry._feed_errors(h, errors)
        h.update(struct.pack(">d", created_at))
        h.update(sequence.to_bytes(8, "big"))
        h.update(key_hash)
        return h.digest()

    def verify(self) -> bool:
        """Verify entry integrity recursively."""
        expected_content = self._compute_content_hash(self.formatted, self.errors)
        if not hmac.compare_digest(self.content_hash, expected_content):
            return False

        expected = self._compute_checksum(
            self.formatted, self.errors, self.created_at, self.sequence, self.key_hash
        )
        if not hmac.compare_digest(self.checksum, expected):
            return False

        return all(error.verify_integrity() for error in self.errors)

    def as_result(self) -> _CacheValue:
        """Extract the formatted result and cached error tuple."""
        return (self.formatted, self.errors)

    @staticmethod
    def _compute_content_hash(
        formatted: str,
        errors: tuple[FrozenFluentError, ...],
    ) -> bytes:
        """Compute a BLAKE2b-128 digest of content only."""
        h = hashlib.blake2b(digest_size=16)
        encoded = formatted.encode("utf-8", errors="surrogatepass")
        h.update(len(encoded).to_bytes(4, "big"))
        h.update(encoded)
        IntegrityCacheEntry._feed_errors(h, errors)
        return h.digest()
