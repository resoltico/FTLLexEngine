"""Structured cache debug and integrity event contracts.

The cache has two different evidence surfaces:

1. a bounded debug ring for routine cache traffic such as hits and misses;
2. a critical integrity-event channel for corruption, write conflicts, and
   contract failures that operators may need to retain durably.

Keeping those surfaces separate prevents normal volume from overwriting the
small set of events that actually matter during incident response.
"""

from __future__ import annotations

import asyncio
import threading
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic, time
from typing import Protocol, Self, final

__all__ = [
    "CacheDebugLogEntry",
    "CacheIntegrityCorrelationScope",
    "CacheIntegrityEvent",
    "CacheIntegrityEventKind",
    "IntegrityEventSink",
    "MemoryIntegrityEventSink",
]


_cache_integrity_correlation_id: ContextVar[str | None] = ContextVar(
    "ftllexengine_cache_integrity_correlation_id",
    default=None,
)


class CacheIntegrityEventKind(StrEnum):
    """Critical cache-integrity event kinds."""

    ENTRY_CORRUPTION = "entry_corruption"
    KEY_CONFUSION = "key_confusion"
    WRITE_CONFLICT = "write_conflict"
    KEY_SERIALIZATION_FAILED = "key_serialization_failed"
    ENTRY_VERIFICATION_FAILED = "entry_verification_failed"


@dataclass(frozen=True, slots=True)
class CacheDebugLogEntry:
    """One bounded debug-log record for routine cache traffic.

    Premise:
        Debug history is useful for local cache tuning, but it is not the same
        artifact as incident-grade integrity evidence.

    Reason:
        The entry stores keyed fingerprints and cache sequencing data so callers
        can inspect recent cache behavior without treating the ring buffer as an
        append-only audit ledger.
    """

    operation: str
    key_fingerprint: str
    timestamp_monotonic: float
    wall_time_unix: float
    debug_sequence: int
    cache_sequence: int
    cache_generation: int
    checksum_hex: str


@dataclass(frozen=True, slots=True)
class CacheIntegrityEvent:
    """Structured critical integrity evidence emitted by the cache."""

    kind: CacheIntegrityEventKind
    message_id: str
    locale_code: str
    attribute: str | None
    use_isolating: bool
    key_fingerprint: str | None
    event_sequence: int
    cache_sequence: int
    cache_generation: int
    correlation_id: str | None
    thread_id: int
    task_name: str | None
    detail: str
    timestamp_monotonic: float = field(default_factory=monotonic)
    wall_time_unix: float = field(default_factory=time)


class IntegrityEventSink(Protocol):
    """Consumer of structured critical cache-integrity events."""

    def record(self, event: CacheIntegrityEvent, /) -> None:
        """Persist or forward one critical integrity event."""


@final
class MemoryIntegrityEventSink:
    """Thread-safe in-memory sink for tests and embedded diagnostics.

    Premise:
        The library cannot assume every application wants file or network I/O
        for integrity events.

    Reason:
        A small in-memory sink gives callers and tests a concrete implementation
        while leaving durable retention to explicit application wiring.
    """

    __slots__ = ("_events", "_lock")

    def __init__(self) -> None:
        self._events: list[CacheIntegrityEvent] = []
        self._lock = threading.Lock()

    def record(self, event: CacheIntegrityEvent, /) -> None:
        """Append one event to the in-memory list."""
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> tuple[CacheIntegrityEvent, ...]:
        """Return an immutable view of recorded events."""
        with self._lock:
            return tuple(self._events)


@final
class CacheIntegrityCorrelationScope:
    """Context manager that binds one correlation ID to emitted integrity events.

    Premise:
        Request correlation belongs to the call context, not to the cache key.

    Reason:
        A context-local scope lets services attach request or job identifiers to
        critical cache events without widening every formatting method signature.
    """

    __slots__ = ("_correlation_id", "_token")

    def __init__(self, correlation_id: str) -> None:
        self._correlation_id = correlation_id
        self._token: Token[str | None] | None = None

    def __enter__(self) -> Self:
        self._token = _cache_integrity_correlation_id.set(self._correlation_id)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        if self._token is not None:
            _cache_integrity_correlation_id.reset(self._token)


def current_cache_integrity_correlation_id() -> str | None:
    """Return the correlation ID bound to the current logical execution flow."""
    return _cache_integrity_correlation_id.get()


def current_cache_integrity_task_name() -> str | None:
    """Return the current asyncio task name when cache work runs inside a task."""
    try:
        task = asyncio.current_task()
    except RuntimeError:
        return None
    return task.get_name() if task is not None else None
