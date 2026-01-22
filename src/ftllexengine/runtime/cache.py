"""Thread-safe LRU cache with integrity verification for message formatting.

Provides financial-grade caching of format_pattern() calls with:
- BLAKE2b-128 checksum verification on every get/put
- Write-once semantics (optional) for data race prevention
- Audit logging (optional) for post-mortem analysis
- Immutable cache entries (frozen dataclasses)
- Automatic invalidation on resource/function changes

Architecture:
    - Thread-safe using threading.RLock (reentrant lock)
    - LRU eviction via OrderedDict
    - Immutable cache keys (tuples of hashable types)
    - Content-addressed entries with BLAKE2b-128 checksums
    - Fail-fast on corruption (strict mode) or silent eviction (non-strict)

Cache Key Structure:
    (message_id, args_tuple, attribute, locale_code, use_isolating)
    - message_id: str
    - args_tuple: tuple[tuple[str, Any], ...] (sorted, frozen)
    - attribute: str | None
    - locale_code: str (for multi-bundle scenarios)
    - use_isolating: bool

Thread Safety:
    All operations protected by RLock. Safe for concurrent reads and writes.

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import struct
import time
from collections import OrderedDict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from threading import RLock
from typing import final

from ftllexengine.constants import DEFAULT_MAX_ENTRY_SIZE, MAX_DEPTH
from ftllexengine.diagnostics import FrozenFluentError
from ftllexengine.integrity import (
    CacheCorruptionError,
    IntegrityContext,
    WriteConflictError,
)
from ftllexengine.runtime.function_bridge import FluentNumber, FluentValue

__all__ = [
    "HashableValue",
    "IntegrityCache",
    "IntegrityCacheEntry",
    "WriteLogEntry",
]

# Base overhead per FrozenFluentError object (dataclass, slots, references).
# Dynamic weight calculation adds actual string lengths on top of this.
_ERROR_BASE_OVERHEAD: int = 100

# Maximum number of errors allowed per cache entry.
# Prevents memory exhaustion from pathological cases where resolution produces
# many errors (e.g., cyclic references, deeply nested validation failures).
_DEFAULT_MAX_ERRORS_PER_ENTRY: int = 50


def _estimate_error_weight(error: FrozenFluentError) -> int:
    """Estimate memory weight of a FrozenFluentError.

    Computes actual weight based on error content rather than using a static
    estimate. This provides accurate memory budget enforcement for financial
    applications where complex errors with detailed diagnostics may exceed
    simple estimates.

    Args:
        error: FrozenFluentError to estimate

    Returns:
        Estimated byte weight of the error
    """
    weight = _ERROR_BASE_OVERHEAD + len(error.message)

    if error.diagnostic is not None:
        diag = error.diagnostic
        weight += len(diag.message)
        # Optional string fields
        for field in (
            diag.hint,
            diag.help_url,
            diag.function_name,
            diag.argument_name,
            diag.expected_type,
            diag.received_type,
            diag.ftl_location,
        ):
            if field is not None:
                weight += len(field)
        # Resolution path
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

# Type alias for hashable values produced by _make_hashable().
# Recursive definition: primitives plus tuple/frozenset of self.
# Note: Decimal, datetime, date, FluentNumber are hashable and preserved unchanged.
#
# Type-Tagging for Collision Prevention:
#   Python's hash equality means hash(1) == hash(True) == hash(1.0), causing
#   cache collisions when these values produce different formatted outputs.
#   To prevent this, _make_hashable() returns type-tagged tuples for bool/int/float:
#   - True  -> ("__bool__", True)
#   - 1     -> ("__int__", 1)
#   - 1.0   -> ("__float__", 1.0)
#   These are distinct cache keys despite Python's hash equality.
type HashableValue = (
    str
    | int
    | float
    | bool
    | Decimal
    | datetime
    | date
    | FluentNumber
    | None
    | tuple["HashableValue", ...]
    | frozenset["HashableValue"]
)

# Internal type alias for cache keys (prefixed with _ per naming convention)
# 5-tuple: (message_id, args_tuple, attribute, locale_code, use_isolating)
type _CacheKey = tuple[str, tuple[tuple[str, HashableValue], ...], str | None, str, bool]

# Internal type alias for legacy cache values (for FormatCache compatibility)
type _CacheValue = tuple[str, tuple[FrozenFluentError, ...]]


@dataclass(frozen=True, slots=True)
class IntegrityCacheEntry:
    """Immutable cache entry with integrity metadata.

    Each entry contains the formatted result, any errors, and a BLAKE2b-128
    checksum computed from the content. The checksum enables detection of
    memory corruption, hardware faults, or tampering.

    Attributes:
        formatted: Formatted message string
        errors: Tuple of FrozenFluentError instances (immutable)
        checksum: BLAKE2b-128 hash of (formatted, errors) for integrity verification
        created_at: Monotonic timestamp when entry was created (time.monotonic())
        sequence: Monotonically increasing sequence number for audit trail
    """

    formatted: str
    errors: tuple[FrozenFluentError, ...]
    checksum: bytes
    created_at: float
    sequence: int

    @classmethod
    def create(
        cls,
        formatted: str,
        errors: tuple[FrozenFluentError, ...],
        sequence: int,
    ) -> IntegrityCacheEntry:
        """Create entry with computed checksum.

        Factory method that computes the BLAKE2b-128 checksum from the content
        and creates an immutable entry with the current monotonic timestamp.

        Args:
            formatted: Formatted message string
            errors: Tuple of FrozenFluentError instances
            sequence: Sequence number for audit trail

        Returns:
            New IntegrityCacheEntry with computed checksum
        """
        # Capture timestamp BEFORE computing checksum to ensure consistency
        created_at = time.monotonic()
        checksum = cls._compute_checksum(formatted, errors, created_at, sequence)
        return cls(
            formatted=formatted,
            errors=errors,
            checksum=checksum,
            created_at=created_at,
            sequence=sequence,
        )

    @staticmethod
    def _compute_checksum(
        formatted: str,
        errors: tuple[FrozenFluentError, ...],
        created_at: float,
        sequence: int,
    ) -> bytes:
        """Compute BLAKE2b-128 hash of cache entry (content + metadata).

        Uses BLAKE2b with 128-bit (16 byte) digest for fast cryptographic
        hashing. This provides collision resistance sufficient for integrity
        verification while minimizing memory overhead.

        Hash Composition:
            All variable-length fields are length-prefixed to prevent collision
            between semantically different values. The checksum covers ALL entry
            fields for complete audit trail integrity:
            1. formatted: Message output (length-prefixed UTF-8)
            2. errors: Count + each error's content_hash
            3. created_at: Monotonic timestamp (8-byte IEEE 754 double)
            4. sequence: Entry sequence number (8-byte signed big-endian)

        Args:
            formatted: Formatted message string
            errors: Tuple of errors to include in hash
            created_at: Monotonic timestamp when entry was created
            sequence: Sequence number for audit trail

        Returns:
            16-byte BLAKE2b digest
        """
        h = hashlib.blake2b(digest_size=16)
        # Length-prefix formatted string for collision resistance
        encoded = formatted.encode("utf-8", errors="surrogatepass")
        h.update(len(encoded).to_bytes(4, "big"))
        h.update(encoded)
        # Include error count and content hashes
        h.update(len(errors).to_bytes(4, "big"))
        for error in errors:
            # Use error's content hash if available, otherwise hash the message
            if hasattr(error, "content_hash"):
                h.update(error.content_hash)
            else:
                error_encoded = str(error).encode("utf-8", errors="surrogatepass")
                h.update(len(error_encoded).to_bytes(4, "big"))
                h.update(error_encoded)
        # Include metadata fields for complete audit trail integrity
        h.update(struct.pack(">d", created_at))  # 8-byte big-endian IEEE 754 double
        h.update(sequence.to_bytes(8, "big", signed=True))  # 8-byte signed int
        return h.digest()

    def verify(self) -> bool:
        """Verify entry integrity recursively.

        Recomputes the checksum from current content and metadata, then compares
        against stored checksum using constant-time comparison (defense against
        timing attacks). Also recursively verifies each contained error's
        integrity for defense-in-depth.

        Returns:
            True if checksum matches AND all errors verify, False otherwise
        """
        # First verify entry-level checksum
        expected = self._compute_checksum(
            self.formatted, self.errors, self.created_at, self.sequence
        )
        if not hmac.compare_digest(self.checksum, expected):
            return False
        # Recursively verify each error's integrity (defense-in-depth)
        # Only verify errors that have the verify_integrity method
        for error in self.errors:
            if hasattr(error, "verify_integrity") and not error.verify_integrity():
                return False
        return True

    def to_tuple(self) -> _CacheValue:
        """Convert to legacy tuple format for backwards compatibility.

        Returns:
            (formatted, errors) tuple matching FormatCache return type
        """
        return (self.formatted, self.errors)


@dataclass(frozen=True, slots=True)
class WriteLogEntry:
    """Immutable audit log entry for cache operations.

    Records cache operations for post-mortem analysis and debugging.
    Used when audit logging is enabled on IntegrityCache.

    Attributes:
        operation: Operation type (GET, PUT, HIT, MISS, EVICT, CORRUPTION)
        key_hash: Hash of cache key (privacy-preserving)
        timestamp: Monotonic timestamp of operation
        sequence: Cache entry sequence number (for PUT operations)
        checksum_hex: Hex representation of entry checksum (for tracing)
    """

    operation: str
    key_hash: str
    timestamp: float
    sequence: int
    checksum_hex: str


@final
class IntegrityCache:
    """Financial-grade format cache with integrity verification.

    Thread-safe LRU cache that provides:
    - BLAKE2b-128 checksum verification on every get()
    - Write-once semantics (optional) to prevent data races
    - Audit logging (optional) for compliance and debugging
    - Fail-fast on corruption (strict mode) or silent eviction

    This is the recommended cache for financial applications where
    silent data corruption is unacceptable.

    Thread Safety:
        All operations are protected by RLock. Safe for concurrent access.

    Memory Protection:
        The max_entry_weight parameter prevents unbounded memory usage.
        Weight is calculated as: len(formatted_str) + (len(errors) * 200).

    Integrity Guarantees:
        - Checksums computed on put(), verified on get()
        - Corruption detected via BLAKE2b-128 mismatch
        - Write-once mode prevents overwrites (data race protection)
        - Audit log provides complete operation history

    Example:
        >>> cache = IntegrityCache(maxsize=1000, strict=True)
        >>> cache.put("msg", None, None, "en_US", False, "Hello", ())
        >>> entry = cache.get("msg", None, None, "en_US", False)
        >>> assert entry is not None
        >>> assert entry.verify()  # Integrity check
        >>> result, errors = entry.to_tuple()  # Legacy format
    """

    __slots__ = (
        "_audit_log",
        "_cache",
        "_corruption_detected",
        "_error_bloat_skips",
        "_hits",
        "_lock",
        "_max_audit_entries",
        "_max_entry_weight",
        "_max_errors_per_entry",
        "_maxsize",
        "_misses",
        "_oversize_skips",
        "_sequence",
        "_strict",
        "_unhashable_skips",
        "_write_once",
    )

    def __init__(
        self,
        maxsize: int = 1000,
        max_entry_weight: int = DEFAULT_MAX_ENTRY_SIZE,
        max_errors_per_entry: int = _DEFAULT_MAX_ERRORS_PER_ENTRY,
        *,
        write_once: bool = False,
        strict: bool = True,
        enable_audit: bool = False,
        max_audit_entries: int = 10000,
    ) -> None:
        """Initialize integrity cache.

        Args:
            maxsize: Maximum number of entries (default: 1000)
            max_entry_weight: Maximum memory weight for cached results (default: 10_000).
                Weight is calculated as: len(formatted_str) + (len(errors) * 200).
            max_errors_per_entry: Maximum number of errors per cache entry (default: 50).
            write_once: If True, reject updates to existing keys (default: False).
                Enables data race prevention for financial applications.
            strict: If True, raise CacheCorruptionError on checksum mismatch (default: True).
                If False, silently evict corrupted entries and return cache miss.
            enable_audit: If True, maintain audit log of all operations (default: False).
            max_audit_entries: Maximum audit log entries before oldest are evicted (default: 10000).

        Raises:
            ValueError: If maxsize, max_entry_weight, or max_errors_per_entry is not positive
        """
        if maxsize <= 0:
            msg = "maxsize must be positive"
            raise ValueError(msg)
        if max_entry_weight <= 0:
            msg = "max_entry_weight must be positive"
            raise ValueError(msg)
        if max_errors_per_entry <= 0:
            msg = "max_errors_per_entry must be positive"
            raise ValueError(msg)

        self._cache: OrderedDict[_CacheKey, IntegrityCacheEntry] = OrderedDict()
        self._maxsize = maxsize
        self._max_entry_weight = max_entry_weight
        self._max_errors_per_entry = max_errors_per_entry
        self._lock = RLock()
        self._write_once = write_once
        self._strict = strict

        # Audit logging with O(1) eviction via deque maxlen
        self._audit_log: deque[WriteLogEntry] | None = (
            deque(maxlen=max_audit_entries) if enable_audit else None
        )
        self._max_audit_entries = max_audit_entries

        # Statistics
        self._hits = 0
        self._misses = 0
        self._unhashable_skips = 0
        self._oversize_skips = 0
        self._error_bloat_skips = 0
        self._corruption_detected = 0
        self._sequence = 0

    def get(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
        use_isolating: bool,
    ) -> IntegrityCacheEntry | None:
        """Get cached entry with integrity verification.

        Thread-safe. Verifies checksum before returning entry.

        Args:
            message_id: Message identifier
            args: Message arguments (may contain unhashable values like lists)
            attribute: Attribute name
            locale_code: Locale code
            use_isolating: Whether Unicode isolation marks are used

        Returns:
            IntegrityCacheEntry if found and valid, None on miss or corruption

        Raises:
            CacheCorruptionError: If strict=True and checksum mismatch detected
        """
        key = self._make_key(message_id, args, attribute, locale_code, use_isolating)

        if key is None:
            with self._lock:
                self._unhashable_skips += 1
                self._misses += 1
            return None

        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                self._audit("MISS", key, None)
                return None

            # INTEGRITY CHECK: Verify checksum before returning
            if not entry.verify():
                self._corruption_detected += 1
                self._audit("CORRUPTION", key, entry)

                if self._strict:
                    # Fail-fast: raise immediately
                    context = IntegrityContext(
                        component="cache",
                        operation="get",
                        key=message_id,
                        expected=entry.checksum.hex(),
                        actual="<recomputed mismatch>",
                        timestamp=time.monotonic(),
                    )
                    msg = f"Cache entry corruption detected for '{message_id}'"
                    raise CacheCorruptionError(msg, context=context)
                # Non-strict: evict corrupted entry, return miss
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (mark as recently used) and record hit
            self._cache.move_to_end(key)
            self._hits += 1
            self._audit("HIT", key, entry)
            return entry

    def put(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
        use_isolating: bool,
        formatted: str,
        errors: tuple[FrozenFluentError, ...],
    ) -> None:
        """Store entry with integrity metadata.

        Thread-safe. Computes checksum and stores immutable entry.

        Args:
            message_id: Message identifier
            args: Message arguments (may contain unhashable values like lists)
            attribute: Attribute name
            locale_code: Locale code
            use_isolating: Whether Unicode isolation marks are used
            formatted: Formatted message string
            errors: Tuple of FrozenFluentError instances

        Raises:
            WriteConflictError: If write_once=True and key already exists (strict mode)
        """
        # Check entry weight before caching
        if len(formatted) > self._max_entry_weight:
            with self._lock:
                self._oversize_skips += 1
            return

        if len(errors) > self._max_errors_per_entry:
            with self._lock:
                self._error_bloat_skips += 1
            return

        # Dynamic weight calculation based on actual error content
        total_weight = len(formatted) + sum(_estimate_error_weight(e) for e in errors)
        if total_weight > self._max_entry_weight:
            with self._lock:
                self._error_bloat_skips += 1
            return

        key = self._make_key(message_id, args, attribute, locale_code, use_isolating)

        if key is None:
            with self._lock:
                self._unhashable_skips += 1
            return

        with self._lock:
            # WRITE-ONCE: Reject updates to existing keys
            if self._write_once and key in self._cache:
                existing = self._cache[key]
                self._audit("WRITE_ONCE_REJECTED", key, existing)

                if self._strict:
                    context = IntegrityContext(
                        component="cache",
                        operation="put",
                        key=message_id,
                        expected="<new entry>",
                        actual=f"<existing seq={existing.sequence}>",
                        timestamp=time.monotonic(),
                    )
                    msg = f"Write-once violation: '{message_id}' already cached"
                    raise WriteConflictError(
                        msg,
                        context=context,
                        existing_seq=existing.sequence,
                        new_seq=self._sequence,
                    )
                return

            # Increment sequence for new entry
            self._sequence += 1
            entry = IntegrityCacheEntry.create(formatted, errors, self._sequence)

            # LRU eviction if needed
            if len(self._cache) >= self._maxsize:
                evicted_key, evicted_entry = self._cache.popitem(last=False)
                self._audit("EVICT", evicted_key, evicted_entry)

            # Update existing or add new
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = entry
            self._audit("PUT", key, entry)

    def clear(self) -> None:
        """Clear all cached entries.

        Thread-safe. Call when bundle is mutated (add_resource, add_function).
        """
        with self._lock:
            self._cache.clear()
            # Reset metrics on clear
            self._hits = 0
            self._misses = 0
            self._unhashable_skips = 0
            self._oversize_skips = 0
            self._error_bloat_skips = 0
            self._corruption_detected = 0
            # Note: sequence NOT reset (monotonic for audit trail)
            # Note: audit log NOT cleared (historical record)

    def get_stats(self) -> dict[str, int | float]:
        """Get cache statistics.

        Thread-safe. Returns current metrics including integrity stats.

        Returns:
            Dict with keys:
            - size (int): Current number of cached entries
            - maxsize (int): Maximum cache capacity
            - max_entry_weight (int): Maximum memory weight for cached results
            - max_errors_per_entry (int): Maximum errors per cache entry
            - hits (int): Number of cache hits
            - misses (int): Number of cache misses
            - hit_rate (float): Hit rate as percentage (0.0-100.0)
            - unhashable_skips (int): Operations skipped due to unhashable args
            - oversize_skips (int): Operations skipped due to result weight
            - error_bloat_skips (int): Operations skipped due to error collection size
            - corruption_detected (int): Number of checksum mismatches detected
            - sequence (int): Current sequence number (total puts)
            - write_once (bool): Whether write-once mode is enabled
            - strict (bool): Whether strict mode is enabled
            - audit_enabled (bool): Whether audit logging is enabled
            - audit_entries (int): Number of audit log entries
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0

            return {
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "max_entry_weight": self._max_entry_weight,
                "max_errors_per_entry": self._max_errors_per_entry,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 2),
                "unhashable_skips": self._unhashable_skips,
                "oversize_skips": self._oversize_skips,
                "error_bloat_skips": self._error_bloat_skips,
                "corruption_detected": self._corruption_detected,
                "sequence": self._sequence,
                "write_once": self._write_once,
                "strict": self._strict,
                "audit_enabled": self._audit_log is not None,
                "audit_entries": len(self._audit_log) if self._audit_log is not None else 0,
            }

    def get_audit_log(self) -> tuple[WriteLogEntry, ...]:
        """Get audit log entries.

        Thread-safe. Returns immutable copy of audit log.

        Returns:
            Tuple of WriteLogEntry instances (empty if audit disabled)
        """
        with self._lock:
            if self._audit_log is None:
                return ()
            return tuple(self._audit_log)

    def _audit(
        self,
        operation: str,
        key: _CacheKey,
        entry: IntegrityCacheEntry | None,
    ) -> None:
        """Record audit log entry (internal, assumes lock held).

        Args:
            operation: Operation type (GET, PUT, HIT, MISS, EVICT, CORRUPTION)
            key: Cache key
            entry: Cache entry (None for MISS operations)
        """
        if self._audit_log is None:
            return

        # Create privacy-preserving key hash
        key_hash = hashlib.blake2b(
            str(key).encode("utf-8", errors="surrogatepass"),
            digest_size=8,
        ).hexdigest()

        log_entry = WriteLogEntry(
            operation=operation,
            key_hash=key_hash,
            timestamp=time.monotonic(),
            sequence=entry.sequence if entry is not None else 0,
            checksum_hex=entry.checksum.hex() if entry is not None else "",
        )

        # deque with maxlen provides automatic O(1) eviction of oldest entries
        self._audit_log.append(log_entry)

    @staticmethod
    def _make_hashable(  # noqa: PLR0911, PLR0912 - type dispatch requires multiple returns/branches
        value: object, depth: int = MAX_DEPTH
    ) -> HashableValue:
        """Convert potentially unhashable value to hashable equivalent.

        Converts:
            - list -> ("__list__", tuple) - type-tagged for collision prevention
            - tuple -> ("__tuple__", tuple) - type-tagged for collision prevention
            - dict -> tuple of sorted key-value tuples (recursively)
            - set -> frozenset (recursively)
            - Decimal -> ("__decimal__", str) - str preserves scale for CLDR rules
            - FluentNumber -> type-tagged with underlying type info
            - Known primitive types -> type-tagged tuples

        Type-Tagging Rationale:
            Python's hash equality creates collision risk:
            - hash(1) == hash(True) == hash(1.0)
            - Decimal("1.0") == Decimal("1") but produce different plural forms
            - list vs tuple: str([1,2]) != str((1,2)) but would hash same
            Type-tagging creates distinct cache keys for semantically different values.

        Depth Protection:
            Uses explicit depth tracking consistent with codebase pattern
            (parser, resolver, serializer all use MAX_DEPTH=100). Raises
            TypeError when depth is exhausted, which is caught by _make_key
            and results in graceful cache bypass.

        Args:
            value: Value to convert (typically FluentValue or nested collection)
            depth: Remaining recursion depth (default: MAX_DEPTH)

        Returns:
            Hashable equivalent of the value

        Raises:
            TypeError: If depth limit exceeded or value is not a known hashable type
        """
        if depth <= 0:
            msg = "Maximum nesting depth exceeded in cache key conversion"
            raise TypeError(msg)

        match value:
            # Type-tag list and tuple distinctly: str([1,2])="[1, 2]" vs str((1,2))="(1, 2)"
            case list():
                return (
                    "__list__",
                    tuple(IntegrityCache._make_hashable(v, depth - 1) for v in value),
                )
            case tuple():
                return (
                    "__tuple__",
                    tuple(IntegrityCache._make_hashable(v, depth - 1) for v in value),
                )
            case dict():
                return tuple(
                    sorted(
                        (k, IntegrityCache._make_hashable(v, depth - 1))
                        for k, v in value.items()
                    )
                )
            case set():
                return frozenset(IntegrityCache._make_hashable(v, depth - 1) for v in value)
            # Type-tagging for collision prevention: bool MUST be checked before int
            # because bool is a subclass of int in Python. Without separate cases,
            # True and 1 would hash-collide despite producing different formatted output.
            case bool():
                return ("__bool__", value)
            case int():
                return ("__int__", value)
            case float():
                # NaN normalization: float("nan") != float("nan") due to IEEE 754.
                # Without normalization, NaN-containing keys are unretrievable,
                # causing cache pollution (DoS risk via cache thrashing).
                if math.isnan(value):
                    return ("__float__", "__NaN__")
                return ("__float__", value)
            case str() | None:
                return value
            # Decimal: use str() to preserve scale (Decimal("1.0") vs Decimal("1"))
            # CLDR plural rules use visible fraction digits (v operand) which differs
            case Decimal():
                # NaN normalization: Decimal("NaN").is_nan() for IEEE 754 compliance.
                # Same rationale as float NaN - prevents cache pollution.
                if value.is_nan():
                    return ("__decimal__", "__NaN__")
                return ("__decimal__", str(value))
            case datetime() | date():
                return value
            # FluentNumber: type-tag with underlying value type for financial precision
            case FluentNumber():
                return (
                    "__fluentnumber__",
                    type(value.value).__name__,
                    value.value,
                    value.formatted,
                    value.precision,
                )
            case _:
                msg = f"Unknown type in cache key: {type(value).__name__}"
                raise TypeError(msg)

    @staticmethod
    def _make_key(
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
        use_isolating: bool,
    ) -> _CacheKey | None:
        """Create immutable cache key from arguments.

        Converts unhashable types (lists, dicts, sets) to hashable equivalents.

        Args:
            message_id: Message identifier
            args: Message arguments (may contain unhashable values)
            attribute: Attribute name
            locale_code: Locale code
            use_isolating: Whether Unicode isolation marks are used

        Returns:
            Immutable cache key tuple, or None if conversion fails
        """
        if args is None:
            args_tuple: tuple[tuple[str, HashableValue], ...] = ()
        else:
            try:
                items: list[tuple[str, HashableValue]] = []
                for k, v in args.items():
                    items.append((k, IntegrityCache._make_hashable(v)))
                args_tuple = tuple(sorted(items))
                hash(args_tuple)
            except (TypeError, RecursionError):
                return None

        return (message_id, args_tuple, attribute, locale_code, use_isolating)

    def __len__(self) -> int:
        """Get current cache size. Thread-safe."""
        with self._lock:
            return len(self._cache)

    @property
    def maxsize(self) -> int:
        """Maximum cache size."""
        return self._maxsize

    @property
    def hits(self) -> int:
        """Number of cache hits. Thread-safe."""
        with self._lock:
            return self._hits

    @property
    def misses(self) -> int:
        """Number of cache misses. Thread-safe."""
        with self._lock:
            return self._misses

    @property
    def unhashable_skips(self) -> int:
        """Number of operations skipped due to unhashable args. Thread-safe."""
        with self._lock:
            return self._unhashable_skips

    @property
    def oversize_skips(self) -> int:
        """Number of operations skipped due to result weight. Thread-safe."""
        with self._lock:
            return self._oversize_skips

    @property
    def max_entry_weight(self) -> int:
        """Maximum memory weight for cached results."""
        return self._max_entry_weight

    @property
    def size(self) -> int:
        """Current number of cached entries. Thread-safe."""
        with self._lock:
            return len(self._cache)

    @property
    def corruption_detected(self) -> int:
        """Number of checksum mismatches detected. Thread-safe."""
        with self._lock:
            return self._corruption_detected

    @property
    def write_once(self) -> bool:
        """Whether write-once mode is enabled."""
        return self._write_once

    @property
    def strict(self) -> bool:
        """Whether strict mode is enabled."""
        return self._strict
