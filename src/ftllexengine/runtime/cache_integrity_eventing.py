"""Structured cache-integrity event emission helpers."""

# ruff: noqa: SLF001 - co-module mixins are the owning implementation surface

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, cast

from .cache_events import (
    CacheIntegrityEvent,
    CacheIntegrityEventKind,
    current_cache_integrity_correlation_id,
    current_cache_integrity_task_name,
)

if TYPE_CHECKING:
    from .cache_protocols import CacheStateProtocol
    from .cache_types import _CacheKey


def _as_cache_state(value: object) -> CacheStateProtocol:
    """Cast one mixin receiver to the structural cache contract."""
    return cast("CacheStateProtocol", value)


class _CacheIntegrityEventMixin:
    """Critical integrity-event construction and emission."""

    def _build_integrity_event(
        self: object,
        *,
        kind: CacheIntegrityEventKind,
        key: _CacheKey | None,
        message_id: str,
        locale_code: str,
        attribute: str | None,
        use_isolating: bool,
        cache_sequence: int,
        detail: str,
    ) -> CacheIntegrityEvent:
        """Construct one structured critical integrity event."""
        state = _as_cache_state(self)
        state._integrity_events_emitted += 1
        return CacheIntegrityEvent(
            kind=kind,
            message_id=message_id,
            locale_code=locale_code,
            attribute=attribute,
            use_isolating=use_isolating,
            key_fingerprint=(
                state._compute_debug_key_fingerprint(
                    key,
                    secret=state._debug_fingerprint_key,
                )
                if key is not None
                else None
            ),
            event_sequence=state._integrity_events_emitted,
            cache_sequence=cache_sequence,
            cache_generation=state._cache_generation,
            correlation_id=current_cache_integrity_correlation_id(),
            thread_id=threading.get_ident(),
            task_name=current_cache_integrity_task_name(),
            detail=detail,
        )

    def _emit_integrity_event(
        self: object,
        *,
        kind: CacheIntegrityEventKind,
        key: _CacheKey | None,
        message_id: str,
        locale_code: str,
        attribute: str | None,
        use_isolating: bool,
        cache_sequence: int,
        detail: str,
    ) -> CacheIntegrityEvent:
        """Emit one structured critical integrity event."""
        state = _as_cache_state(self)
        event = state._build_integrity_event(
            kind=kind,
            key=key,
            message_id=message_id,
            locale_code=locale_code,
            attribute=attribute,
            use_isolating=use_isolating,
            cache_sequence=cache_sequence,
            detail=detail,
        )
        if state._integrity_event_sink is not None:
            state._integrity_event_sink.record(event)
        return event
