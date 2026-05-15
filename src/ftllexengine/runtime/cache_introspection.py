"""Stats and key-shaping helpers for ``IntegrityCache``."""

# ruff: noqa: SLF001 - co-module mixins are the owning implementation surface

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ftllexengine.constants import MAX_DEPTH

from .cache_key_codec import compute_debug_key_fingerprint, compute_key_binding_digest
from .cache_keys import HASHABLE_NODE_BUDGET, make_hashable, make_key
from .cache_types import CacheStats

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ftllexengine.core.value_types import FluentValue

    from .cache_protocols import CacheStateProtocol
    from .cache_types import HashableValue, _CacheKey


def _as_cache_state(value: object) -> CacheStateProtocol:
    """Cast one mixin receiver to the structural cache contract."""
    return cast("CacheStateProtocol", value)


class _CacheKeyMixin:
    """Static key-shaping helpers preserved on ``IntegrityCache``."""

    _MAX_HASHABLE_NODES: int = HASHABLE_NODE_BUDGET

    @staticmethod
    def _make_hashable(value: object, depth: int = MAX_DEPTH) -> HashableValue:
        """Convert potentially unhashable cache arguments into a stable form."""
        return make_hashable(value, depth=depth)

    @staticmethod
    def _compute_key_binding_digest(key: _CacheKey) -> bytes:
        """Compute the internal key-binding digest for cache entries."""
        return compute_key_binding_digest(key)

    @staticmethod
    def _compute_debug_key_fingerprint(key: _CacheKey, *, secret: bytes) -> str:
        """Compute the keyed fingerprint exposed through debug/event surfaces."""
        return compute_debug_key_fingerprint(key, secret=secret)

    @staticmethod
    def _make_key(
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
        *,
        use_isolating: bool,
        function_generation: int = 0,
    ) -> _CacheKey | None:
        """Create the immutable lookup key for a formatting request."""
        return make_key(
            message_id,
            args,
            attribute,
            locale_code,
            use_isolating=use_isolating,
            function_generation=function_generation,
        )


class _CacheStatsMixin:
    """Stats and property accessors for ``IntegrityCache``."""

    def get_stats(self: object) -> CacheStats:
        """Get cache statistics."""
        state = _as_cache_state(self)
        with state._lock:
            total = state._hits + state._misses
            hit_rate = (state._hits / total * 100) if total > 0 else 0.0

            return CacheStats(
                size=len(state._cache),
                maxsize=state._maxsize,
                max_entry_payload_bytes=state._max_entry_payload_bytes,
                max_errors_per_entry=state._max_errors_per_entry,
                hits=state._hits,
                misses=state._misses,
                hit_rate=round(hit_rate, 2),
                unhashable_skips=state._unhashable_skips,
                oversize_skips=state._oversize_skips,
                error_bloat_skips=state._error_bloat_skips,
                combined_payload_skips=state._combined_payload_skips,
                corruption_detected=state._corruption_detected,
                integrity_events_emitted=state._integrity_events_emitted,
                idempotent_writes=state._idempotent_writes,
                write_once_conflicts=state._write_once_conflicts,
                uncacheable_function_skips=state._uncacheable_function_skips,
                sequence=state._sequence,
                cache_generation=state._cache_generation,
                write_once=state._write_once,
                debug_log_enabled=state._debug_log is not None,
                debug_log_entries=len(state._debug_log) if state._debug_log is not None else 0,
            )

    def __len__(self: object) -> int:
        """Get current cache size. Thread-safe."""
        state = _as_cache_state(self)
        with state._lock:
            return len(state._cache)

    @property
    def size(self: object) -> int:
        """Current number of cached entries. Thread-safe."""
        state = _as_cache_state(self)
        with state._lock:
            return len(state._cache)

    @property
    def maxsize(self: object) -> int:
        """Maximum cache size."""
        state = _as_cache_state(self)
        return state._maxsize

    @property
    def hits(self: object) -> int:
        """Number of cache hits. Thread-safe."""
        state = _as_cache_state(self)
        with state._lock:
            return state._hits

    @property
    def misses(self: object) -> int:
        """Number of cache misses. Thread-safe."""
        state = _as_cache_state(self)
        with state._lock:
            return state._misses

    @property
    def unhashable_skips(self: object) -> int:
        """Number of operations rejected due to unsupported key input."""
        state = _as_cache_state(self)
        with state._lock:
            return state._unhashable_skips

    @property
    def oversize_skips(self: object) -> int:
        """Number of operations skipped due to payload budget overrun."""
        state = _as_cache_state(self)
        with state._lock:
            return state._oversize_skips

    @property
    def max_entry_payload_bytes(self: object) -> int:
        """Maximum retained payload bytes for cached results."""
        state = _as_cache_state(self)
        return state._max_entry_payload_bytes

    @property
    def corruption_detected(self: object) -> int:
        """Number of checksum mismatches detected. Thread-safe."""
        state = _as_cache_state(self)
        with state._lock:
            return state._corruption_detected

    @property
    def integrity_events_emitted(self: object) -> int:
        """Number of critical integrity events emitted. Thread-safe."""
        state = _as_cache_state(self)
        with state._lock:
            return state._integrity_events_emitted

    @property
    def idempotent_writes(self: object) -> int:
        """Number of benign concurrent writes with identical content. Thread-safe."""
        state = _as_cache_state(self)
        with state._lock:
            return state._idempotent_writes

    @property
    def error_bloat_skips(self: object) -> int:
        """Number of puts skipped due to excess error count. Thread-safe."""
        state = _as_cache_state(self)
        with state._lock:
            return state._error_bloat_skips

    @property
    def combined_payload_skips(self: object) -> int:
        """Number of puts skipped due to combined payload limit. Thread-safe."""
        state = _as_cache_state(self)
        with state._lock:
            return state._combined_payload_skips

    @property
    def write_once_conflicts(self: object) -> int:
        """Number of true write-once conflicts. Thread-safe."""
        state = _as_cache_state(self)
        with state._lock:
            return state._write_once_conflicts

    @property
    def uncacheable_function_skips(self: object) -> int:
        """Number of results not cached due to non-cacheable functions."""
        state = _as_cache_state(self)
        with state._lock:
            return state._uncacheable_function_skips

    @property
    def write_once(self: object) -> bool:
        """Whether write-once mode is enabled."""
        state = _as_cache_state(self)
        return state._write_once
