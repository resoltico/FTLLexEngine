# mypy: ignore-errors
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from ftllexengine.integrity import WriteConflictError
from ftllexengine.runtime.cache import (
    CacheIntegrityEventKind,
    IntegrityCache,
    MemoryIntegrityEventSink,
)

_FG = 0


def _put(cache: IntegrityCache, message_id: str, formatted: str = "value") -> None:
    cache.put(
        message_id,
        None,
        None,
        "en",
        use_isolating=True,
        function_generation=_FG,
        formatted=formatted,
        errors=(),
    )


class TestWriteOnceAndDebugEvidence:
    """Write-once conflicts and debug retention should be explicit."""

    def test_write_once_conflict_raises_and_increments_counter(self) -> None:
        cache = IntegrityCache(write_once=True)
        _put(cache, "msg", "one")

        with pytest.raises(WriteConflictError):
            _put(cache, "msg", "two")

        assert cache.get_stats()["write_once_conflicts"] == 1

    def test_idempotent_duplicate_write_does_not_raise(self) -> None:
        cache = IntegrityCache(write_once=True)
        _put(cache, "msg", "one")
        _put(cache, "msg", "one")

        assert cache.get_stats()["idempotent_writes"] == 1

    def test_debug_log_retention_is_bounded(self) -> None:
        cache = IntegrityCache(enable_debug_log=True, max_debug_entries=3)
        for idx in range(5):
            _put(cache, f"msg{idx}")

        debug_log = cache.get_debug_log()
        assert len(debug_log) == 3
        assert all(entry.operation == "PUT" for entry in debug_log)


class TestIntegrityEventEmission:
    """Critical evidence should go to the event sink, not the debug ring."""

    def test_write_conflict_emits_structured_event(self) -> None:
        sink = MemoryIntegrityEventSink()
        cache = IntegrityCache(write_once=True, integrity_event_sink=sink)
        _put(cache, "msg", "one")

        with pytest.raises(WriteConflictError):
            _put(cache, "msg", "two")

        events = sink.snapshot()
        assert len(events) == 1
        assert events[0].kind is CacheIntegrityEventKind.WRITE_CONFLICT
        assert events[0].message_id == "msg"


class TestConcurrentWriteOnce:
    """Concurrent identical writes should converge without false conflicts."""

    def test_identical_concurrent_writes_are_idempotent(self) -> None:
        cache = IntegrityCache(write_once=True)

        def worker() -> None:
            _put(cache, "msg", "value")

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: worker(), range(4)))

        stats = cache.get_stats()
        assert stats["write_once_conflicts"] == 0
        assert stats["idempotent_writes"] >= 1
