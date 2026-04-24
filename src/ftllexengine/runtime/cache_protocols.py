"""Typing protocols for IntegrityCache mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections import OrderedDict, deque
    from threading import Lock

    from .cache_types import CacheStats, IntegrityCacheEntry, WriteLogEntry, _CacheKey


class CacheStateProtocol(Protocol):
    """Structural contract implemented by IntegrityCache."""

    _audit_log: deque[WriteLogEntry] | None
    _cache: OrderedDict[_CacheKey, IntegrityCacheEntry]
    _combined_weight_skips: int
    _corruption_detected: int
    _error_bloat_skips: int
    _hits: int
    _idempotent_writes: int
    _lock: Lock
    _max_entry_weight: int
    _max_errors_per_entry: int
    _maxsize: int
    _misses: int
    _oversize_skips: int
    _sequence: int
    _strict: bool
    _unhashable_skips: int
    _write_once: bool
    _write_once_conflicts: int

    def get_stats(self) -> CacheStats:
        ...  # pragma: no cover - typing-only protocol declaration
