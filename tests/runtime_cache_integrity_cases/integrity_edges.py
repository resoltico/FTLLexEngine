# mypy: ignore-errors
from __future__ import annotations

import pytest

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.integrity import CacheKeySerializationError, WriteConflictError
from ftllexengine.runtime.cache import (
    CacheDebugLogEntry,
    CacheIntegrityEventKind,
    IntegrityCache,
    MemoryIntegrityEventSink,
)

_FG = 0


def _put(cache: IntegrityCache, message_id: str, *, args: dict[str, object] | None = None) -> None:
    cache.put(
        message_id,
        args,
        None,
        "en",
        use_isolating=True,
        function_generation=_FG,
        formatted="value",
        errors=(),
    )


class TestDebugLogSurface:
    """The bounded debug log is distinct from integrity events."""

    def test_disabled_debug_log_returns_empty_tuple(self) -> None:
        cache = IntegrityCache()
        _put(cache, "msg")
        assert cache.get_debug_log() == ()

    def test_enabled_debug_log_records_recent_operations(self) -> None:
        cache = IntegrityCache(enable_debug_log=True)
        _put(cache, "msg")
        cache.get("msg", None, None, "en", use_isolating=True, function_generation=_FG)
        cache.get("missing", None, None, "en", use_isolating=True, function_generation=_FG)

        log = cache.get_debug_log()
        assert [entry.operation for entry in log] == ["PUT", "HIT", "MISS"]
        assert all(isinstance(entry, CacheDebugLogEntry) for entry in log)

    def test_debug_log_is_bounded(self) -> None:
        cache = IntegrityCache(enable_debug_log=True, max_debug_entries=2)
        _put(cache, "a")
        _put(cache, "b")
        _put(cache, "c")

        log = cache.get_debug_log()
        assert len(log) == 2
        assert [entry.operation for entry in log] == ["PUT", "PUT"]


class TestKeyContractFailures:
    """Unsupported cache-key values must fail closed."""

    def test_unencodable_args_raise_typed_integrity_error_on_put(self) -> None:
        cache = IntegrityCache()
        with pytest.raises(CacheKeySerializationError, match="Cache key contract failed"):
            _put(cache, "msg", args={"value": object()})

    def test_unencodable_args_raise_typed_integrity_error_on_get(self) -> None:
        cache = IntegrityCache()
        with pytest.raises(CacheKeySerializationError, match="Cache key contract failed"):
            cache.get(
                "msg",
                {"value": object()},
                None,
                "en",
                use_isolating=True,
                function_generation=_FG,
            )

    def test_uncacheable_result_with_unencodable_args_counts_without_debug_log_entry(self) -> None:
        cache = IntegrityCache(enable_debug_log=True)
        cache.note_uncacheable_result(
            "msg",
            {"value": object()},
            None,
            "en",
            use_isolating=True,
            function_generation=_FG,
        )

        assert cache.uncacheable_function_skips == 1
        assert cache.get_debug_log() == ()


class TestIntegrityEventSink:
    """Critical events should emit structured evidence."""

    def test_write_conflict_emits_event(self) -> None:
        sink = MemoryIntegrityEventSink()
        cache = IntegrityCache(write_once=True, integrity_event_sink=sink)
        _put(cache, "msg")

        with pytest.raises(WriteConflictError):
            cache.put(
                "msg",
                None,
                None,
                "en",
                use_isolating=True,
                function_generation=_FG,
                formatted="other",
                errors=(FrozenFluentError("err", ErrorCategory.REFERENCE),),
            )

        events = sink.snapshot()
        assert len(events) == 1
        assert events[0].kind is CacheIntegrityEventKind.WRITE_CONFLICT
