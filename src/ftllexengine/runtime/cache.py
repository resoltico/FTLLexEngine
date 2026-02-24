"""Thread-safe LRU cache with integrity verification for message formatting.

Provides financial-grade caching of format_pattern() calls with:
- BLAKE2b-128 checksum verification on every get/put
- Write-once semantics (optional) for data race prevention
- Audit logging (optional) for post-mortem analysis
- Immutable cache entries (frozen dataclasses)
- Automatic invalidation on resource/function changes

Architecture:
    - Thread-safe using threading.Lock
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
    All operations protected by Lock. Safe for concurrent reads and writes.

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

import hashlib
import hmac
import struct
import time
from collections import OrderedDict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from threading import Lock
from typing import final

from ftllexengine.constants import DEFAULT_CACHE_SIZE, DEFAULT_MAX_ENTRY_WEIGHT, MAX_DEPTH
from ftllexengine.diagnostics import FrozenFluentError
from ftllexengine.integrity import (
    CacheCorruptionError,
    IntegrityContext,
    WriteConflictError,
)
from ftllexengine.runtime.value_types import FluentNumber, FluentValue

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
#   Python's hash equality means hash(1) == hash(True), causing cache collisions
#   when these values produce different formatted outputs.
#   To prevent this, _make_hashable() returns type-tagged tuples for bool/int:
#   - True  -> ("__bool__", True)
#   - 1     -> ("__int__", 1)
#   - Decimal("1") -> ("__decimal__", "1")
#   These are distinct cache keys despite Python's hash equality.
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

# Internal type alias for cache keys (prefixed with _ per naming convention)
# 5-tuple: (message_id, args_tuple, attribute, locale_code, use_isolating)
type _CacheKey = tuple[str, tuple[tuple[str, HashableValue], ...], str | None, str, bool]

# Internal type alias for legacy cache values (for FormatCache compatibility)
type _CacheValue = tuple[str, tuple[FrozenFluentError, ...]]


@dataclass(frozen=True, slots=True)
class IntegrityCacheEntry:
    """Immutable cache entry with integrity metadata.

    Each entry contains the formatted result, any errors, and two BLAKE2b-128
    hashes: a content-only hash and a full checksum covering content + metadata.
    Both enable detection of memory corruption, hardware faults, or tampering.

    Attributes:
        formatted: Formatted message string
        errors: Tuple of FrozenFluentError instances (immutable)
        checksum: BLAKE2b-128 hash of (formatted, errors, created_at, sequence)
        created_at: Monotonic timestamp when entry was created (time.monotonic())
        sequence: Monotonically increasing sequence number for audit trail
        content_hash: BLAKE2b-128 hash of (formatted, errors) only. Computed once
            at construction via __post_init__; not part of the constructor signature.
            Used for idempotent write detection without recomputation.
    """

    formatted: str
    errors: tuple[FrozenFluentError, ...]
    checksum: bytes
    created_at: float
    sequence: int
    # Computed once from (formatted, errors) at construction; not an __init__ parameter.
    # Stored to avoid BLAKE2b recomputation on every put() idempotency check.
    # Uses object.__setattr__ because frozen=True prevents normal assignment in __post_init__.
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
    ) -> IntegrityCacheEntry:
        """Create entry with computed checksum.

        Factory method that computes the BLAKE2b-128 checksum from the content
        and creates an immutable entry with the current monotonic timestamp.

        Args:
            formatted: Formatted message string
            errors: Tuple of FrozenFluentError instances
            sequence: Sequence number for audit trail

        Returns:
            New IntegrityCacheEntry with computed checksum and content_hash
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
    def _feed_errors(h: hashlib.blake2b, errors: tuple[FrozenFluentError, ...]) -> None:
        """Feed error sequence into hasher via content_hash.

        Shared by both _compute_checksum and _compute_content_hash to eliminate
        duplicated hashing logic. FrozenFluentError is @final and always carries
        a content_hash (bytes), so direct attribute access is safe and correct.
        The b"\\x01" type marker provides structural disambiguation between the
        count field and each hash entry.

        Args:
            h: Active BLAKE2b hasher to update in-place
            errors: Tuple of errors to include in hash
        """
        h.update(len(errors).to_bytes(4, "big"))
        for error in errors:
            # FrozenFluentError is @final; content_hash is always a bytes field.
            # Accessing it directly enforces the type contract and eliminates dead code.
            h.update(b"\x01")  # Type marker: content hash follows
            h.update(error.content_hash)

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
            2. errors: Count + each error as (b"\\x01" + content_hash) using
               FrozenFluentError.content_hash (BLAKE2b-128, always present)
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
        IntegrityCacheEntry._feed_errors(h, errors)
        # Include metadata fields for complete audit trail integrity
        h.update(struct.pack(">d", created_at))  # 8-byte big-endian IEEE 754 double
        h.update(sequence.to_bytes(8, "big", signed=True))  # 8-byte signed int
        return h.digest()

    def verify(self) -> bool:
        """Verify entry integrity recursively.

        Recomputes both the content hash and the full checksum from current
        content, then compares against stored values using constant-time
        comparison (defense against timing attacks). Also recursively verifies
        each contained error's integrity for defense-in-depth.

        Returns:
            True if content_hash matches AND checksum matches AND all errors verify
        """
        # Verify stored content_hash matches recomputed (catches field-level corruption)
        expected_content = self._compute_content_hash(self.formatted, self.errors)
        if not hmac.compare_digest(self.content_hash, expected_content):
            return False
        # Verify full checksum (includes metadata)
        expected = self._compute_checksum(
            self.formatted, self.errors, self.created_at, self.sequence
        )
        if not hmac.compare_digest(self.checksum, expected):
            return False
        # Recursively verify each error's integrity (defense-in-depth).
        # FrozenFluentError is @final, so verify_integrity() is always present.
        # Direct call eliminates the duck-typing overhead and clarifies intent.
        return all(error.verify_integrity() for error in self.errors)

    def as_result(self) -> _CacheValue:
        """Extract formatted result and errors as a tuple.

        Returns:
            (formatted, errors) pair for resolver consumption.
        """
        return (self.formatted, self.errors)

    @staticmethod
    def _compute_content_hash(
        formatted: str,
        errors: tuple[FrozenFluentError, ...],
    ) -> bytes:
        """Compute BLAKE2b-128 hash of content only (excludes metadata).

        Used for idempotent write detection: two entries with identical content
        should have identical content hashes regardless of created_at/sequence.

        Hash Composition:
            1. formatted: Message output (length-prefixed UTF-8)
            2. errors: Count + each error as (b"\\x01" + content_hash) using
               FrozenFluentError.content_hash (BLAKE2b-128, always present)

        Args:
            formatted: Formatted message string
            errors: Tuple of errors to include in hash

        Returns:
            16-byte BLAKE2b digest of content only
        """
        h = hashlib.blake2b(digest_size=16)
        # Length-prefix formatted string for collision resistance
        encoded = formatted.encode("utf-8", errors="surrogatepass")
        h.update(len(encoded).to_bytes(4, "big"))
        h.update(encoded)
        IntegrityCacheEntry._feed_errors(h, errors)
        return h.digest()


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
        All operations are protected by Lock. Safe for concurrent access.

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
        >>> result, errors = entry.as_result()
    """

    __slots__ = (
        "_audit_log",
        "_cache",
        "_corruption_detected",
        "_error_bloat_skips",
        "_hits",
        "_idempotent_writes",
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
        maxsize: int = DEFAULT_CACHE_SIZE,
        max_entry_weight: int = DEFAULT_MAX_ENTRY_WEIGHT,
        max_errors_per_entry: int = _DEFAULT_MAX_ERRORS_PER_ENTRY,
        *,
        write_once: bool = False,
        strict: bool = True,
        enable_audit: bool = False,
        max_audit_entries: int = 10000,
    ) -> None:
        """Initialize integrity cache.

        Args:
            maxsize: Maximum number of entries (default: DEFAULT_CACHE_SIZE from constants)
            max_entry_weight: Maximum memory weight for cached results (default: 10_000).
                Weight is calculated as: len(formatted_str) + sum(error_weight(e) for e in errors),
                where error_weight computes actual content-based weight per error.
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
        self._lock = Lock()
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
        self._idempotent_writes = 0
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
            # WRITE-ONCE: Check for duplicate keys with idempotent write detection
            if self._write_once and key in self._cache:
                existing = self._cache[key]

                # IDEMPOTENT CHECK: Compare content hashes (excludes metadata).
                # Thundering herd scenario: Multiple threads resolve same message
                # simultaneously, all compute identical results. First thread wins,
                # subsequent threads should succeed silently (idempotent write).
                new_content_hash = IntegrityCacheEntry._compute_content_hash(
                    formatted, errors
                )
                if hmac.compare_digest(existing.content_hash, new_content_hash):
                    # Benign race: identical content already cached
                    self._idempotent_writes += 1
                    self._audit("WRITE_ONCE_IDEMPOTENT", key, existing)
                    return

                # TRUE CONFLICT: Different content for same key
                self._audit("WRITE_ONCE_CONFLICT", key, existing)

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
                        new_seq=self._sequence + 1,
                    )
                return

            # Increment sequence for new entry
            self._sequence += 1
            entry = IntegrityCacheEntry.create(formatted, errors, self._sequence)

            # LRU eviction only when adding a new key (not updating an existing one).
            # Without this guard, updating an existing key in a full cache would
            # evict an unrelated LRU entry AND keep the existing key, shrinking
            # the cache by one slot per thundering-herd write to the same key.
            is_update = key in self._cache
            if not is_update and len(self._cache) >= self._maxsize:
                evicted_key, evicted_entry = self._cache.popitem(last=False)
                self._audit("EVICT", evicted_key, evicted_entry)

            # Update existing (promote to MRU end) or insert new
            if is_update:
                self._cache.move_to_end(key)
            self._cache[key] = entry
            self._audit("PUT", key, entry)

    def clear(self) -> None:
        """Clear all cached entries.

        Thread-safe. Call when bundle is mutated (add_resource, add_function).

        Metrics are cumulative and NOT reset on clear. They reflect the total
        operational history of this cache instance. Resetting on clear would
        destroy production observability (hit-rate trends, corruption counts)
        and make auditing impossible after routine cache invalidation.
        """
        with self._lock:
            self._cache.clear()
            # Note: hits/misses/skips/corruption/idempotent_writes NOT reset
            #   — cumulative counters for production observability and audit.
            # Note: sequence NOT reset (monotonic for audit trail)
            # Note: audit log NOT cleared (historical record)

    def get_stats(self) -> dict[str, int | float | bool]:
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
            - idempotent_writes (int): Concurrent writes with identical content (benign races)
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
                "idempotent_writes": self._idempotent_writes,
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

    # Maximum nodes traversed during _make_hashable to prevent exponential
    # expansion of DAG structures with shared references. A 25-level binary
    # DAG has only 25 nodes but expands to 2^25 during tree flattening.
    # 10,000 nodes is generous for legitimate use while blocking abuse.
    _MAX_HASHABLE_NODES: int = 10_000

    @staticmethod
    def _make_hashable(  # noqa: PLR0911, PLR0912 - type dispatch requires multiple returns/branches
        value: object, depth: int = MAX_DEPTH, *, _counter: list[int] | None = None
    ) -> HashableValue:
        """Convert potentially unhashable value to hashable equivalent.

        Converts:
            - list -> ("__list__", tuple) - type-tagged for collision prevention
            - tuple -> ("__tuple__", tuple) - type-tagged for collision prevention
            - dict -> tuple of sorted key-value tuples (recursively)
            - set -> frozenset (recursively)
            - Decimal -> ("__decimal__", str) - str preserves scale for CLDR rules
            - datetime -> ("__datetime__", isoformat, tzinfo_str) - includes timezone
            - date -> ("__date__", isoformat) - no timezone
            - FluentNumber -> type-tagged with underlying type info
            - Mapping ABC -> tuple of sorted key-value tuples (for ChainMap, etc.)
            - Sequence ABC -> ("__seq__", tuple) - for UserList, etc.
            - Known primitive types -> type-tagged tuples

        Type-Tagging Rationale:
            Python's hash equality creates collision risk:
            - hash(1) == hash(True)
            - Decimal("1.0") == Decimal("1") but produce different plural forms
            - datetime objects at same UTC instant with different tzinfo are equal
              but format to different local time strings
            - list vs tuple: str([1,2]) != str((1,2)) but would hash same
            Type-tagging creates distinct cache keys for semantically different values.

        Depth Protection:
            Uses explicit depth tracking consistent with codebase pattern
            (parser, resolver, serializer all use MAX_DEPTH=100). Raises
            TypeError when depth is exhausted, which is caught by _make_key
            and results in graceful cache bypass.

        Node Budget Protection:
            Uses a mutable counter to track total nodes visited across all
            recursive calls. This prevents exponential expansion of DAG
            structures where shared references are traversed independently
            (e.g., l=[l,l] repeated 25 times creates 2^25 tree traversal
            despite only 25 depth levels).

        Args:
            value: Value to convert (typically FluentValue or nested collection)
            depth: Remaining recursion depth (default: MAX_DEPTH)
            _counter: Internal node counter for DAG expansion prevention

        Returns:
            Hashable equivalent of the value

        Raises:
            TypeError: If depth limit exceeded, node budget exceeded, or unknown type
        """
        if _counter is None:
            _counter = [0]
        _counter[0] += 1
        if _counter[0] > IntegrityCache._MAX_HASHABLE_NODES:
            msg = "Node budget exceeded in cache key conversion (possible DAG expansion attack)"
            raise TypeError(msg)

        if depth <= 0:
            msg = "Maximum nesting depth exceeded in cache key conversion"
            raise TypeError(msg)

        def _recurse(v: object) -> HashableValue:
            return IntegrityCache._make_hashable(
                v, depth - 1, _counter=_counter
            )

        match value:
            # str and None: return as-is. Must check str before Sequence (str is Sequence).
            case str() | None:
                return value
            # Type-tag list and tuple distinctly: str([1,2])="[1, 2]" vs str((1,2))="(1, 2)"
            case list():
                return (
                    "__list__",
                    tuple(_recurse(v) for v in value),
                )
            case tuple():
                return (
                    "__tuple__",
                    tuple(_recurse(v) for v in value),
                )
            case dict():
                # Type-tag dict to distinguish from Mapping ABC (e.g., ChainMap).
                # str(dict({"a": 1})) = "{'a': 1}" vs str(ChainMap({"a": 1})) = "ChainMap({'a': 1})"
                # Both must produce distinct cache keys since formatting differs.
                return (
                    "__dict__",
                    tuple(
                        sorted(
                            (k, _recurse(v)) for k, v in value.items()
                        )
                    ),
                )
            case set():
                # Convert mutable set to immutable frozenset for hashability.
                # Tag distinguishes from frozenset since str(set) != str(frozenset).
                return (
                    "__set__",
                    frozenset(_recurse(v) for v in value),
                )
            case frozenset():
                # Explicit frozenset case - already hashable but tag for type distinction.
                # str(frozenset({1})) = "frozenset({1})" vs str({1}) = "{1}"
                return (
                    "__frozenset__",
                    frozenset(_recurse(v) for v in value),
                )
            # Type-tagging for collision prevention: bool MUST be checked before int
            # because bool is a subclass of int in Python. Without separate cases,
            # True and 1 would hash-collide despite producing different formatted output.
            case bool():
                return ("__bool__", value)
            case int():
                return ("__int__", value)
            # Decimal: use str() to preserve scale (Decimal("1.0") vs Decimal("1"))
            # CLDR plural rules use visible fraction digits (v operand) which differs
            case Decimal():
                # NaN normalization: Decimal("NaN").is_nan() for IEEE 754 compliance.
                # Same rationale as float NaN - prevents cache pollution.
                if value.is_nan():
                    return ("__decimal__", "__NaN__")
                return ("__decimal__", str(value))
            case datetime():
                # Include timezone info to distinguish same-instant different-offset datetimes.
                # Two datetimes representing the same UTC instant but with different tzinfo
                # compare equal, but they format to different local time strings.
                tz_key = str(value.tzinfo) if value.tzinfo else "__naive__"
                return ("__datetime__", value.isoformat(), tz_key)
            case date():
                # date has no timezone, isoformat is sufficient for unique key
                return ("__date__", value.isoformat())
            # FluentNumber: type-tag with underlying value type for financial precision
            # Recursively normalize inner value to handle Decimal NaN correctly.
            # Without this, FluentNumber(value=Decimal('NaN')...) creates unretrievable keys.
            case FluentNumber():
                return (
                    "__fluentnumber__",
                    type(value.value).__name__,
                    _recurse(value.value),
                    value.formatted,
                    value.precision,
                )
            case _:
                # Handle Mapping and Sequence ABCs for types like ChainMap, UserList.
                # This fallback catches any Mapping/Sequence not matched above.
                # Must be after specific type checks (dict, list, tuple, str).
                if isinstance(value, Mapping):
                    # Type-tag Mapping ABC to distinguish from dict.
                    return (
                        "__mapping__",
                        tuple(
                            sorted(
                                (k, _recurse(v))
                                for k, v in value.items()
                            )
                        ),
                    )
                if isinstance(value, Sequence):
                    # Generic Sequence (UserList, etc.) - tag distinctly from list/tuple
                    return (
                        "__seq__",
                        tuple(_recurse(v) for v in value),
                    )
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
    def size(self) -> int:
        """Current number of cached entries. Thread-safe."""
        return len(self)

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
    def corruption_detected(self) -> int:
        """Number of checksum mismatches detected. Thread-safe."""
        with self._lock:
            return self._corruption_detected

    @property
    def idempotent_writes(self) -> int:
        """Number of benign concurrent writes with identical content. Thread-safe."""
        with self._lock:
            return self._idempotent_writes

    @property
    def write_once(self) -> bool:
        """Whether write-once mode is enabled."""
        return self._write_once

    @property
    def strict(self) -> bool:
        """Whether strict mode is enabled."""
        return self._strict
