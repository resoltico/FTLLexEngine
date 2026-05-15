"""Bounded cache debug-log helpers for ``IntegrityCache``."""

# ruff: noqa: SLF001 - co-module mixins are the owning implementation surface

from __future__ import annotations

from time import monotonic, time
from typing import TYPE_CHECKING, cast

from .cache_events import CacheDebugLogEntry

if TYPE_CHECKING:
    from .cache_protocols import CacheStateProtocol
    from .cache_types import IntegrityCacheEntry, _CacheKey


def _as_cache_state(value: object) -> CacheStateProtocol:
    """Cast one mixin receiver to the structural cache contract.

    Premise:
        The mixins are reused by the concrete cache class, not instantiated on
        their own.

    Reason:
        Mypy cannot infer that relationship from mixin inheritance alone, so
        the cast lives in one helper rather than leaking repeated type noise
        through every method body.
    """
    return cast("CacheStateProtocol", value)


class _CacheAuditMixin:
    """Bounded debug-log behavior."""

    def get_debug_log(self: object) -> tuple[CacheDebugLogEntry, ...]:
        """Return recent cache activity from the bounded debug ring."""
        state = _as_cache_state(self)
        with state._lock:
            if state._debug_log is None:
                return ()
            return tuple(state._debug_log)

    def _record_debug_operation(
        self: object,
        operation: str,
        key: _CacheKey,
        entry: IntegrityCacheEntry | None,
    ) -> None:
        """Record one recent-operation debug entry (lock already held)."""
        state = _as_cache_state(self)
        if state._debug_log is None:
            return

        state._debug_sequence += 1
        key_fingerprint = state._compute_debug_key_fingerprint(
            key,
            secret=state._debug_fingerprint_key,
        )

        log_entry = CacheDebugLogEntry(
            operation=operation,
            key_fingerprint=key_fingerprint,
            timestamp_monotonic=monotonic(),
            wall_time_unix=time(),
            debug_sequence=state._debug_sequence,
            cache_sequence=entry.sequence if entry is not None else state._sequence,
            cache_generation=state._cache_generation,
            checksum_hex=entry.checksum.hex() if entry is not None else "",
        )
        state._debug_log.append(log_entry)
