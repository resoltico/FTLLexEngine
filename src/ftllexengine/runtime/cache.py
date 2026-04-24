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

import hmac
import time
from collections import OrderedDict, deque
from threading import Lock
from typing import TYPE_CHECKING, final

from ftllexengine.constants import DEFAULT_CACHE_SIZE, DEFAULT_MAX_ENTRY_WEIGHT
from ftllexengine.integrity import (
    CacheCorruptionError,
    IntegrityContext,
    WriteConflictError,
)
from ftllexengine.runtime.cache_audit import _CacheAuditMixin
from ftllexengine.runtime.cache_introspection import _CacheKeyMixin, _CacheStatsMixin
from ftllexengine.runtime.cache_types import (
    _DEFAULT_MAX_ERRORS_PER_ENTRY,
    CacheAuditLogEntry,
    CacheStats,
    HashableValue,
    IntegrityCacheEntry,
    WriteLogEntry,
    _CacheKey,
    _estimate_error_weight,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.diagnostics import FrozenFluentError

__all__ = [
    "CacheAuditLogEntry",
    "CacheStats",
    "HashableValue",
    "IntegrityCache",
    "IntegrityCacheEntry",
    "WriteLogEntry",
]


@final
class IntegrityCache(_CacheStatsMixin, _CacheAuditMixin, _CacheKeyMixin):
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
        Weight is calculated as: len(formatted_str) + sum(_estimate_error_weight(e)
        for e in errors), where _estimate_error_weight measures actual error content
        (message text, diagnostic fields, resolution path strings, context fields).

    Integrity Guarantees:
        - Checksums computed on put(), verified on get()
        - Corruption detected via BLAKE2b-128 mismatch
        - Write-once mode prevents overwrites (data race protection)
        - Audit log provides complete operation history

    Example:
        >>> cache = IntegrityCache(maxsize=1000, strict=True)  # doctest: +SKIP
        >>> cache.put(  # doctest: +SKIP
        ...     "msg",
        ...     None,
        ...     None,
        ...     "en_US",
        ...     use_isolating=False,
        ...     formatted="Hello",
        ...     errors=(),
        ... )
        >>> entry = cache.get("msg", None, None, "en_US", use_isolating=False)  # doctest: +SKIP
        >>> assert entry is not None  # doctest: +SKIP
        >>> assert entry.verify()  # Integrity check  # doctest: +SKIP
        >>> result, errors = entry.as_result()  # doctest: +SKIP
    """

    __slots__ = (
        "_audit_log",
        "_cache",
        "_combined_weight_skips",
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
        "_write_once_conflicts",
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
        self._combined_weight_skips = 0
        self._corruption_detected = 0
        self._idempotent_writes = 0
        self._write_once_conflicts = 0
        self._sequence = 0

    def get(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
        *,
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
        key = self._make_key(message_id, args, attribute, locale_code, use_isolating=use_isolating)

        if key is None:
            with self._lock:
                self._unhashable_skips += 1
            # Unhashable args bypass the cache entirely: no key exists, no
            # lookup occurs. This is not a cache miss — it is a cache bypass.
            # Counting it as a miss would deflate hit_rate and mislead operators
            # into diagnosing insufficient cache size when the real issue is
            # an unhashable argument type. unhashable_skips is the correct counter.
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
                        wall_time_unix=time.time(),
                    )
                    msg = f"Cache entry corruption detected for '{message_id}'"
                    raise CacheCorruptionError(msg, context=context)
                # Non-strict: evict corrupted entry, return miss
                del self._cache[key]
                self._misses += 1
                return None

            # KEY BINDING CHECK: Verify entry is stored under the correct key.
            # Detects key confusion where an entry is moved to a different cache slot
            # while its checksum remains internally consistent (verify() above only
            # checks that the stored key_hash matches the checksum, not that the
            # stored key_hash matches the CURRENT lookup key).
            expected_key_hash = IntegrityCache._compute_key_hash(key)
            if not hmac.compare_digest(entry.key_hash, expected_key_hash):
                self._corruption_detected += 1
                self._audit("CORRUPTION", key, entry)

                if self._strict:
                    context = IntegrityContext(
                        component="cache",
                        operation="get",
                        key=message_id,
                        expected=expected_key_hash.hex(),
                        actual=entry.key_hash.hex(),
                        timestamp=time.monotonic(),
                        wall_time_unix=time.time(),
                    )
                    msg = f"Cache key confusion detected for '{message_id}'"
                    raise CacheCorruptionError(msg, context=context)
                # Non-strict: evict entry with wrong key binding, return miss
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
        *,
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

        # Dynamic weight calculation based on actual error content.
        # Formatted string already passed the per-string check above; this fires when
        # the combined total (formatted + error payload) exceeds the limit.
        # Counted separately from error_bloat_skips so operators can distinguish
        # "too many errors" (error_bloat) from "combined content too heavy" (combined_weight).
        total_weight = len(formatted) + sum(_estimate_error_weight(e) for e in errors)
        if total_weight > self._max_entry_weight:
            with self._lock:
                self._combined_weight_skips += 1
            return

        key = self._make_key(message_id, args, attribute, locale_code, use_isolating=use_isolating)

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
                # Cross-class call within the same module: IntegrityCacheEntry._compute_content_hash
                # is a static pure function needed here to compare hashes without a full entry.
                # Both classes are permanently co-located in cache.py.
                new_content_hash = (
                    IntegrityCacheEntry._compute_content_hash(  # noqa: SLF001 - co-module
                        formatted, errors
                    )
                )
                if hmac.compare_digest(existing.content_hash, new_content_hash):
                    # Benign race: identical content already cached
                    self._idempotent_writes += 1
                    self._audit("WRITE_ONCE_IDEMPOTENT", key, existing)
                    return

                # TRUE CONFLICT: Different content for same key
                self._audit("WRITE_ONCE_CONFLICT", key, existing)
                self._write_once_conflicts += 1

                if self._strict:
                    context = IntegrityContext(
                        component="cache",
                        operation="put",
                        key=message_id,
                        expected="<new entry>",
                        actual=f"<existing seq={existing.sequence}>",
                        timestamp=time.monotonic(),
                        wall_time_unix=time.time(),
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
            entry = IntegrityCacheEntry.create(
                formatted, errors, self._sequence, IntegrityCache._compute_key_hash(key)
            )

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
