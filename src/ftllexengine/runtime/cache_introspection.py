"""Stats and key-shaping helpers for IntegrityCache."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ftllexengine.constants import MAX_DEPTH

from .cache_keys import HASHABLE_NODE_BUDGET, compute_key_hash, make_hashable, make_key

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ftllexengine.core.value_types import FluentValue

    from .cache_protocols import CacheStateProtocol
    from .cache_types import CacheStats, HashableValue, _CacheKey


class _CacheKeyMixin:
    """Static key-shaping helpers preserved on IntegrityCache."""

    _MAX_HASHABLE_NODES: int = HASHABLE_NODE_BUDGET

    @staticmethod
    def _make_hashable(value: object, depth: int = MAX_DEPTH) -> HashableValue:
        """Convert potentially unhashable cache arguments into a stable hashable form."""
        return make_hashable(value, depth=depth)

    @staticmethod
    def _compute_key_hash(key: _CacheKey) -> bytes:
        """Compute the 8-byte key binding used to detect cache slot confusion."""
        return compute_key_hash(key)

    @staticmethod
    def _make_key(
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
        *,
        use_isolating: bool,
    ) -> _CacheKey | None:
        """Create the immutable lookup key for a formatting request."""
        return make_key(
            message_id,
            args,
            attribute,
            locale_code,
            use_isolating=use_isolating,
        )


class _CacheStatsMixin:
    """Stats and property accessors for IntegrityCache."""

    def get_stats(self: CacheStateProtocol) -> CacheStats:
        """Get cache statistics."""
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
                "combined_weight_skips": self._combined_weight_skips,
                "corruption_detected": self._corruption_detected,
                "idempotent_writes": self._idempotent_writes,
                "write_once_conflicts": self._write_once_conflicts,
                "sequence": self._sequence,
                "write_once": self._write_once,
                "strict": self._strict,
                "audit_enabled": self._audit_log is not None,
                "audit_entries": len(self._audit_log) if self._audit_log is not None else 0,
            }

    def __len__(self: CacheStateProtocol) -> int:
        """Get current cache size. Thread-safe."""
        with self._lock:
            return len(self._cache)

    @property
    def size(self: CacheStateProtocol) -> int:
        """Current number of cached entries. Thread-safe."""
        with self._lock:
            return len(self._cache)

    @property
    def maxsize(self: CacheStateProtocol) -> int:
        """Maximum cache size."""
        return self._maxsize

    @property
    def hits(self: CacheStateProtocol) -> int:
        """Number of cache hits. Thread-safe."""
        with self._lock:
            return self._hits

    @property
    def misses(self: CacheStateProtocol) -> int:
        """Number of cache misses. Thread-safe."""
        with self._lock:
            return self._misses

    @property
    def unhashable_skips(self: CacheStateProtocol) -> int:
        """Number of operations skipped due to unhashable args. Thread-safe."""
        with self._lock:
            return self._unhashable_skips

    @property
    def oversize_skips(self: CacheStateProtocol) -> int:
        """Number of operations skipped due to result weight. Thread-safe."""
        with self._lock:
            return self._oversize_skips

    @property
    def max_entry_weight(self: CacheStateProtocol) -> int:
        """Maximum memory weight for cached results."""
        return self._max_entry_weight

    @property
    def corruption_detected(self: CacheStateProtocol) -> int:
        """Number of checksum mismatches detected. Thread-safe."""
        with self._lock:
            return self._corruption_detected

    @property
    def idempotent_writes(self: CacheStateProtocol) -> int:
        """Number of benign concurrent writes with identical content. Thread-safe."""
        with self._lock:
            return self._idempotent_writes

    @property
    def error_bloat_skips(self: CacheStateProtocol) -> int:
        """Number of puts skipped due to excess error count. Thread-safe."""
        with self._lock:
            return self._error_bloat_skips

    @property
    def combined_weight_skips(self: CacheStateProtocol) -> int:
        """Number of puts skipped due to combined formatted+error weight. Thread-safe."""
        with self._lock:
            return self._combined_weight_skips

    @property
    def write_once_conflicts(self: CacheStateProtocol) -> int:
        """Number of true write-once conflicts (different content, same key). Thread-safe."""
        with self._lock:
            return self._write_once_conflicts

    @property
    def write_once(self: CacheStateProtocol) -> bool:
        """Whether write-once mode is enabled."""
        return self._write_once

    @property
    def strict(self: CacheStateProtocol) -> bool:
        """Whether strict mode is enabled."""
        return self._strict
