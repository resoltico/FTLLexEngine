"""Typing protocols for cache mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections import OrderedDict, deque
    from threading import Lock

    from .cache_events import CacheDebugLogEntry, CacheIntegrityEvent, IntegrityEventSink
    from .cache_types import CacheStats, IntegrityCacheEntry, _CacheKey


class CacheStateProtocol(Protocol):
    """Structural contract implemented by ``IntegrityCache``."""

    _cache: OrderedDict[_CacheKey, IntegrityCacheEntry]
    _cache_generation: int
    _combined_payload_skips: int
    _corruption_detected: int
    _debug_log: deque[CacheDebugLogEntry] | None
    _debug_sequence: int
    _debug_fingerprint_key: bytes
    _error_bloat_skips: int
    _hits: int
    _idempotent_writes: int
    _integrity_event_sink: IntegrityEventSink | None
    _integrity_events_emitted: int
    _lock: Lock
    _max_debug_entries: int
    _max_entry_payload_bytes: int
    _max_errors_per_entry: int
    _maxsize: int
    _misses: int
    _oversize_skips: int
    _sequence: int
    _uncacheable_function_skips: int
    _unhashable_skips: int
    _write_once: bool
    _write_once_conflicts: int

    def get_stats(self) -> CacheStats:
        ...  # pragma: no cover - typing-only protocol declaration

    @staticmethod
    def _compute_debug_key_fingerprint(key: _CacheKey, *, secret: bytes) -> str:
        ...  # pragma: no cover - typing-only protocol declaration

    def _build_integrity_event(
        self,
        *,
        kind: object,
        key: _CacheKey | None,
        message_id: str,
        locale_code: str,
        attribute: str | None,
        use_isolating: bool,
        cache_sequence: int,
        detail: str,
    ) -> CacheIntegrityEvent:
        ...  # pragma: no cover - typing-only protocol declaration
