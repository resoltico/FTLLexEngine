"""Thread-safe LRU cache with fail-closed integrity verification.

Provides format caching for ``format_pattern()`` calls with:
- accidental-corruption detection on every lookup;
- write-once semantics for race detection;
- a bounded debug ring for routine cache traffic;
- a structured critical integrity-event sink for incident evidence;
- immutable cache entries and canonical versioned cache keys.

The cache contract is intentionally separate from formatting strictness.
Formatting fallback behavior is user-facing; cache corruption and key-contract
failures are system-integrity events.
"""

from __future__ import annotations

import hmac
import time
from collections import OrderedDict, deque
from secrets import token_bytes
from threading import Lock
from typing import TYPE_CHECKING, NoReturn, final

from ftllexengine.constants import DEFAULT_CACHE_SIZE, DEFAULT_MAX_ENTRY_PAYLOAD_BYTES
from ftllexengine.core.validators import require_bool, require_positive_int
from ftllexengine.integrity import (
    CacheCorruptionError,
    CacheKeySerializationError,
    IntegrityCheckFailedError,
    IntegrityContext,
    WriteConflictError,
)
from ftllexengine.runtime.cache_audit import _CacheAuditMixin
from ftllexengine.runtime.cache_events import (
    CacheDebugLogEntry,
    CacheIntegrityEvent,
    CacheIntegrityEventKind,
    IntegrityEventSink,
    MemoryIntegrityEventSink,
)
from ftllexengine.runtime.cache_integrity_eventing import _CacheIntegrityEventMixin
from ftllexengine.runtime.cache_introspection import _CacheKeyMixin, _CacheStatsMixin
from ftllexengine.runtime.cache_types import (
    _DEFAULT_MAX_ERRORS_PER_ENTRY,
    CacheStats,
    HashableValue,
    IntegrityCacheEntry,
    _CacheKey,
    _estimate_error_payload_bytes,
)
from ftllexengine.runtime.cache_validation import (
    validate_optional_debug_fingerprint_key,
    validate_optional_integrity_event_sink,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.diagnostics import FrozenFluentError

__all__ = [
    "CacheDebugLogEntry",
    "CacheIntegrityEvent",
    "CacheIntegrityEventKind",
    "CacheStats",
    "HashableValue",
    "IntegrityCache",
    "IntegrityCacheEntry",
    "IntegrityEventSink",
    "MemoryIntegrityEventSink",
]


@final
class IntegrityCache(
    _CacheStatsMixin,
    _CacheAuditMixin,
    _CacheIntegrityEventMixin,
    _CacheKeyMixin,
):
    """Fail-closed format cache with explicit integrity ownership.

    Thread-safe LRU cache that provides:
    - accidental-corruption detection on every ``get()``;
    - write-once semantics (optional) to detect conflicting writes;
    - a bounded debug ring for recent routine cache traffic;
    - a structured integrity-event sink for critical incidents.

    Thread Safety:
        All operations are protected by ``threading.Lock``.

    Payload Budget:
        ``max_entry_payload_bytes`` bounds the retained UTF-8 payload of the
        formatted string plus the serialized diagnostic content cached with it.
        This is a deterministic retained-payload contract, not a claim about
        Python allocator overhead.
    """

    __slots__ = (
        "_cache",
        "_cache_generation",
        "_combined_payload_skips",
        "_corruption_detected",
        "_debug_fingerprint_key",
        "_debug_log",
        "_debug_sequence",
        "_error_bloat_skips",
        "_hits",
        "_idempotent_writes",
        "_integrity_event_sink",
        "_integrity_events_emitted",
        "_lock",
        "_max_debug_entries",
        "_max_entry_payload_bytes",
        "_max_errors_per_entry",
        "_maxsize",
        "_misses",
        "_oversize_skips",
        "_sequence",
        "_uncacheable_function_skips",
        "_unhashable_skips",
        "_write_once",
        "_write_once_conflicts",
    )

    def __init__(
        self,
        maxsize: int = DEFAULT_CACHE_SIZE,
        max_entry_payload_bytes: int = DEFAULT_MAX_ENTRY_PAYLOAD_BYTES,
        max_errors_per_entry: int = _DEFAULT_MAX_ERRORS_PER_ENTRY,
        *,
        write_once: bool = False,
        enable_debug_log: bool = False,
        max_debug_entries: int = 10000,
        integrity_event_sink: IntegrityEventSink | None = None,
        debug_fingerprint_key: bytes | None = None,
    ) -> None:
        """Initialize the integrity cache.

        Premise:
            The cache owns both its integrity posture and its content-based
            retained-payload budget.

        Reason:
            Constructor validation keeps those boundaries explicit: callers get
            one fail-closed cache whose debug ring, integrity-event sink, and
            payload-byte limits are all checked before any entries can exist.
        """
        require_positive_int(maxsize, "maxsize")
        require_positive_int(max_entry_payload_bytes, "max_entry_payload_bytes")
        require_positive_int(max_errors_per_entry, "max_errors_per_entry")
        require_bool(write_once, "write_once")
        require_bool(enable_debug_log, "enable_debug_log")
        require_positive_int(max_debug_entries, "max_debug_entries")
        validated_sink = validate_optional_integrity_event_sink(integrity_event_sink)
        validated_debug_key = validate_optional_debug_fingerprint_key(debug_fingerprint_key)

        self._cache: OrderedDict[_CacheKey, IntegrityCacheEntry] = OrderedDict()
        self._maxsize = maxsize
        self._max_entry_payload_bytes = max_entry_payload_bytes
        self._max_errors_per_entry = max_errors_per_entry
        self._lock = Lock()
        self._write_once = write_once
        self._cache_generation = 0

        self._debug_log: deque[CacheDebugLogEntry] | None = (
            deque(maxlen=max_debug_entries) if enable_debug_log else None
        )
        self._debug_sequence = 0
        self._max_debug_entries = max_debug_entries
        self._debug_fingerprint_key = (
            validated_debug_key if validated_debug_key is not None else token_bytes(32)
        )
        self._integrity_event_sink = validated_sink

        self._hits = 0
        self._misses = 0
        self._unhashable_skips = 0
        self._oversize_skips = 0
        self._error_bloat_skips = 0
        self._combined_payload_skips = 0
        self._corruption_detected = 0
        self._integrity_events_emitted = 0
        self._idempotent_writes = 0
        self._write_once_conflicts = 0
        self._uncacheable_function_skips = 0
        self._sequence = 0

    def _raise_key_contract_error(
        self,
        *,
        operation: str,
        message_id: str,
        attribute: str | None,
        locale_code: str,
        use_isolating: bool,
        detail: str,
    ) -> NoReturn:
        """Raise a typed key-contract failure and emit structured evidence."""
        with self._lock:
            self._unhashable_skips += 1
            self._emit_integrity_event(
                kind=CacheIntegrityEventKind.KEY_SERIALIZATION_FAILED,
                key=None,
                message_id=message_id,
                locale_code=locale_code,
                attribute=attribute,
                use_isolating=use_isolating,
                cache_sequence=self._sequence,
                detail=detail,
            )
        context = IntegrityContext(
            component="cache",
            operation=operation,
            key=message_id,
            expected="cache-key contract",
            actual=detail,
            timestamp=time.monotonic(),
            wall_time_unix=time.time(),
        )
        msg = f"Cache key contract failed for '{message_id}': {detail}"
        raise CacheKeySerializationError(msg, context=context)

    def get(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
        *,
        use_isolating: bool,
        function_generation: int = 0,
    ) -> IntegrityCacheEntry | None:
        """Get a cached entry with integrity verification."""
        key = self._make_key(
            message_id,
            args,
            attribute,
            locale_code,
            use_isolating=use_isolating,
            function_generation=function_generation,
        )
        if key is None:
            self._raise_key_contract_error(
                operation="get",
                message_id=message_id,
                attribute=attribute,
                locale_code=locale_code,
                use_isolating=use_isolating,
                detail="arguments could not be encoded into the canonical cache key",
            )

        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                self._record_debug_operation("MISS", key, None)
                return None

            if not entry.verify():
                self._corruption_detected += 1
                self._record_debug_operation("CORRUPTION", key, entry)
                self._emit_integrity_event(
                    kind=CacheIntegrityEventKind.ENTRY_CORRUPTION,
                    key=key,
                    message_id=message_id,
                    locale_code=locale_code,
                    attribute=attribute,
                    use_isolating=use_isolating,
                    cache_sequence=entry.sequence,
                    detail="cached entry failed checksum verification",
                )
                del self._cache[key]
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

            expected_key_hash = IntegrityCache._compute_key_binding_digest(key)
            if not hmac.compare_digest(entry.key_hash, expected_key_hash):
                self._corruption_detected += 1
                self._record_debug_operation("KEY_CONFUSION", key, entry)
                self._emit_integrity_event(
                    kind=CacheIntegrityEventKind.KEY_CONFUSION,
                    key=key,
                    message_id=message_id,
                    locale_code=locale_code,
                    attribute=attribute,
                    use_isolating=use_isolating,
                    cache_sequence=entry.sequence,
                    detail="cached entry key binding did not match lookup slot",
                )
                del self._cache[key]
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

            self._cache.move_to_end(key)
            self._hits += 1
            self._record_debug_operation("HIT", key, entry)
            return entry

    def put(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
        *,
        use_isolating: bool,
        function_generation: int = 0,
        formatted: str,
        errors: tuple[FrozenFluentError, ...],
    ) -> None:
        """Store a cache entry with integrity metadata."""
        retained_errors = tuple(error.sanitized_for_cache() for error in errors)
        formatted_payload_bytes = len(formatted.encode("utf-8", errors="surrogatepass"))
        if formatted_payload_bytes > self._max_entry_payload_bytes:
            with self._lock:
                self._oversize_skips += 1
            return

        if len(retained_errors) > self._max_errors_per_entry:
            with self._lock:
                self._error_bloat_skips += 1
            return

        total_payload_bytes = formatted_payload_bytes + sum(
            _estimate_error_payload_bytes(error) for error in retained_errors
        )
        if total_payload_bytes > self._max_entry_payload_bytes:
            with self._lock:
                self._combined_payload_skips += 1
            return

        key = self._make_key(
            message_id,
            args,
            attribute,
            locale_code,
            use_isolating=use_isolating,
            function_generation=function_generation,
        )
        if key is None:
            self._raise_key_contract_error(
                operation="put",
                message_id=message_id,
                attribute=attribute,
                locale_code=locale_code,
                use_isolating=use_isolating,
                detail="arguments could not be encoded into the canonical cache key",
            )

        with self._lock:
            if self._write_once and key in self._cache:
                existing = self._cache[key]
                new_content_hash = IntegrityCacheEntry._compute_content_hash(  # noqa: SLF001 - co-module pure helper
                    formatted,
                    retained_errors,
                )
                if hmac.compare_digest(existing.content_hash, new_content_hash):
                    self._idempotent_writes += 1
                    self._record_debug_operation("WRITE_ONCE_IDEMPOTENT", key, existing)
                    return

                self._write_once_conflicts += 1
                self._record_debug_operation("WRITE_ONCE_CONFLICT", key, existing)
                self._emit_integrity_event(
                    kind=CacheIntegrityEventKind.WRITE_CONFLICT,
                    key=key,
                    message_id=message_id,
                    locale_code=locale_code,
                    attribute=attribute,
                    use_isolating=use_isolating,
                    cache_sequence=existing.sequence,
                    detail="write-once conflict detected for an existing cache key",
                )
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

            self._sequence += 1
            entry = IntegrityCacheEntry.create(
                formatted,
                retained_errors,
                self._sequence,
                IntegrityCache._compute_key_binding_digest(key),
            )
            if not entry.verify():
                self._record_debug_operation("ENTRY_VERIFICATION_FAILED", key, entry)
                self._emit_integrity_event(
                    kind=CacheIntegrityEventKind.ENTRY_VERIFICATION_FAILED,
                    key=key,
                    message_id=message_id,
                    locale_code=locale_code,
                    attribute=attribute,
                    use_isolating=use_isolating,
                    cache_sequence=entry.sequence,
                    detail="new cache entry failed immediate verification",
                )
                context = IntegrityContext(
                    component="cache",
                    operation="put",
                    key=message_id,
                    expected="freshly constructed entry passes verify()",
                    actual="verify() returned False",
                    timestamp=time.monotonic(),
                    wall_time_unix=time.time(),
                )
                msg = f"New cache entry failed immediate verification for '{message_id}'"
                raise IntegrityCheckFailedError(msg, context=context)

            is_update = key in self._cache
            if not is_update and len(self._cache) >= self._maxsize:
                evicted_key, evicted_entry = self._cache.popitem(last=False)
                self._record_debug_operation("EVICT", evicted_key, evicted_entry)

            if is_update:
                self._cache.move_to_end(key)
            self._cache[key] = entry
            self._record_debug_operation("PUT", key, entry)

    def note_uncacheable_result(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
        *,
        use_isolating: bool,
        function_generation: int = 0,
    ) -> None:
        """Record that one resolution result was intentionally not cached.

        Premise:
            Non-cacheable custom functions are a correctness choice, not a
            cache-size miss.

        Reason:
            Operators need a distinct counter for “cache disabled by purity
            contract” so they do not misdiagnose the bypass as insufficient
            capacity or unhashable input.
        """
        key = self._make_key(
            message_id,
            args,
            attribute,
            locale_code,
            use_isolating=use_isolating,
            function_generation=function_generation,
        )
        with self._lock:
            self._uncacheable_function_skips += 1
            if key is not None:
                self._record_debug_operation("BYPASS_NONCACHEABLE_FUNCTION", key, None)

    def clear(self) -> None:
        """Clear all cached entries and advance the cache generation."""
        with self._lock:
            self._cache.clear()
            self._cache_generation += 1
