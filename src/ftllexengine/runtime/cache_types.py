"""Shared cache types and immutable entry structures."""

from __future__ import annotations

import hashlib
import hmac
import struct
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import TypedDict

from ftllexengine.core.value_types import FluentNumber
from ftllexengine.diagnostics import FrozenFluentError

__all__ = [
    "_DEFAULT_MAX_ERRORS_PER_ENTRY",
    "CacheAuditLogEntry",
    "CacheStats",
    "HashableValue",
    "IntegrityCacheEntry",
    "WriteLogEntry",
    "_CacheKey",
    "_CacheValue",
    "_estimate_error_weight",
]


class CacheStats(TypedDict):
    """Typed statistics snapshot returned by IntegrityCache.get_stats()."""

    size: int
    maxsize: int
    max_entry_weight: int
    max_errors_per_entry: int
    hits: int
    misses: int
    hit_rate: float
    unhashable_skips: int
    oversize_skips: int
    error_bloat_skips: int
    corruption_detected: int
    idempotent_writes: int
    write_once_conflicts: int
    combined_weight_skips: int
    sequence: int
    write_once: bool
    strict: bool
    audit_enabled: bool
    audit_entries: int


_ERROR_BASE_OVERHEAD: int = 100
_DEFAULT_MAX_ERRORS_PER_ENTRY: int = 50


def _estimate_error_weight(error: FrozenFluentError) -> int:
    """Estimate the memory weight of one FrozenFluentError."""
    weight = _ERROR_BASE_OVERHEAD + len(error.message)

    if error.diagnostic is not None:
        diag = error.diagnostic
        weight += len(diag.message)
        for attr in (
            diag.hint,
            diag.help_url,
            diag.function_name,
            diag.argument_name,
            diag.expected_type,
            diag.received_type,
            diag.ftl_location,
        ):
            if attr is not None:
                weight += len(attr)
        if diag.resolution_path is not None:
            for path_element in diag.resolution_path:
                weight += len(path_element)

    if error.context is not None:
        ctx = error.context
        weight += len(ctx.input_value)
        weight += len(ctx.locale_code)
        weight += len(ctx.parse_type)
        weight += len(ctx.fallback_value)

    return weight


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

type _CacheKey = tuple[str, tuple[tuple[str, HashableValue], ...], str | None, str, bool]
type _CacheValue = tuple[str, tuple[FrozenFluentError, ...]]


@dataclass(frozen=True, slots=True)
class IntegrityCacheEntry:
    """Immutable cache entry with integrity metadata."""

    formatted: str
    errors: tuple[FrozenFluentError, ...]
    checksum: bytes
    created_at: float
    sequence: int
    key_hash: bytes
    content_hash: bytes = field(init=False, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        """Compute and store content_hash after field initialization."""
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
        """Create entry with computed checksum."""
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
        """Feed error sequence into an active hasher."""
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
        """Compute a BLAKE2b-128 checksum for content plus metadata."""
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
        """Extract formatted result and errors as a tuple."""
        return (self.formatted, self.errors)

    @staticmethod
    def _compute_content_hash(
        formatted: str,
        errors: tuple[FrozenFluentError, ...],
    ) -> bytes:
        """Compute a BLAKE2b-128 hash of content only."""
        h = hashlib.blake2b(digest_size=16)
        encoded = formatted.encode("utf-8", errors="surrogatepass")
        h.update(len(encoded).to_bytes(4, "big"))
        h.update(encoded)
        IntegrityCacheEntry._feed_errors(h, errors)
        return h.digest()


@dataclass(frozen=True, slots=True)
class WriteLogEntry:
    """Immutable audit log entry for cache operations."""

    operation: str
    key_hash: str
    timestamp: float
    sequence: int
    checksum_hex: str
    wall_time_unix: float


CacheAuditLogEntry = WriteLogEntry
