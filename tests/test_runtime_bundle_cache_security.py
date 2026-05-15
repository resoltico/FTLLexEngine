"""Bundle-level tests for the cache security and evidence contract."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from ftllexengine.constants import DEFAULT_CACHE_SIZE, DEFAULT_MAX_ENTRY_PAYLOAD_BYTES
from ftllexengine.integrity import CacheCorruptionError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.cache import (
    CacheDebugLogEntry,
    CacheIntegrityEventKind,
    MemoryIntegrityEventSink,
)
from ftllexengine.runtime.cache_config import CacheConfig
from ftllexengine.runtime.cache_events import CacheIntegrityCorrelationScope


def _invalid_write_once_config() -> CacheConfig:
    """Build one config with an invalid boolean boundary value.

    Premise:
        The runtime validator owns protection against untyped callers.

    Reason:
        This helper intentionally violates the static type contract so the test
        can prove the constructor rejects bad runtime input at the boundary.
    """
    return CacheConfig(write_once="false")  # type: ignore[arg-type]


def _invalid_debug_log_config() -> CacheConfig:
    """Build one config with an invalid debug-log toggle value."""
    return CacheConfig(enable_debug_log=1)  # type: ignore[arg-type]


def _invalid_payload_budget_config() -> CacheConfig:
    """Build one config with an invalid numeric boundary value."""
    return CacheConfig(max_entry_payload_bytes=True)


def _invalid_fingerprint_key_config() -> CacheConfig:
    """Build one config with a too-short keyed fingerprint secret."""
    return CacheConfig(debug_fingerprint_key=b"short")


def _invalid_fingerprint_key_type_config() -> CacheConfig:
    """Build one config with an invalid fingerprint key type."""
    return CacheConfig(debug_fingerprint_key="not-bytes")  # type: ignore[arg-type]


def _invalid_integrity_event_sink_config() -> CacheConfig:
    """Build one config with a non-sink integrity event consumer."""
    return CacheConfig(integrity_event_sink=object())  # type: ignore[arg-type]


class TestCacheConfigContract:
    """The public cache configuration should validate its security posture."""

    def test_defaults_match_public_contract(self) -> None:
        config = CacheConfig()

        assert config.size == DEFAULT_CACHE_SIZE
        assert config.write_once is False
        assert config.enable_debug_log is False
        assert config.max_debug_entries == 10_000
        assert config.max_entry_payload_bytes == DEFAULT_MAX_ENTRY_PAYLOAD_BYTES
        assert config.max_errors_per_entry == 50
        assert config.integrity_event_sink is None
        assert config.debug_fingerprint_key is None

    @pytest.mark.parametrize(
        ("factory", "expected"),
        [
            (_invalid_write_once_config, "write_once must be bool"),
            (_invalid_debug_log_config, "enable_debug_log must be bool"),
            (_invalid_payload_budget_config, "max_entry_payload_bytes must be int"),
            (
                _invalid_fingerprint_key_type_config,
                "debug_fingerprint_key must be bytes or None",
            ),
            (
                _invalid_fingerprint_key_config,
                "debug_fingerprint_key must contain at least 16 bytes",
            ),
        ],
    )
    def test_invalid_config_values_fail_closed(
        self,
        factory: Any,
        expected: str,
    ) -> None:
        with pytest.raises((TypeError, ValueError), match=expected):
            factory()

    def test_invalid_integrity_event_sink_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="integrity_event_sink must implement"):
            _invalid_integrity_event_sink_config()


class TestBundleCacheDebugLog:
    """The bundle should expose the bounded recent-operation debug ring only."""

    def test_debug_log_absent_when_cache_disabled(self) -> None:
        bundle = FluentBundle("en")
        assert bundle.get_cache_debug_log() is None

    def test_debug_log_empty_when_disabled(self) -> None:
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")

        debug_log = bundle.get_cache_debug_log()
        assert debug_log == ()

    def test_debug_log_records_recent_operations_with_keyed_fingerprint(self) -> None:
        bundle = FluentBundle(
            "en",
            cache=CacheConfig(
                enable_debug_log=True,
                debug_fingerprint_key=b"0123456789abcdef0123456789abcdef",
            ),
        )
        bundle.add_resource("msg = Hello")

        bundle.format_pattern("msg")
        bundle.format_pattern("msg")

        debug_log = bundle.get_cache_debug_log()
        assert debug_log is not None
        assert [entry.operation for entry in debug_log] == ["MISS", "PUT", "HIT"]
        assert all(isinstance(entry, CacheDebugLogEntry) for entry in debug_log)
        assert all(entry.key_fingerprint for entry in debug_log)
        assert all("msg" not in entry.key_fingerprint for entry in debug_log)


class TestBundleCacheIntegrity:
    """Cache integrity failures are independent from formatting strictness."""

    def test_corrupted_cache_entry_raises_even_when_bundle_is_non_strict(self) -> None:
        sink = MemoryIntegrityEventSink()
        bundle = FluentBundle(
            "en",
            strict=False,
            cache=CacheConfig(
                enable_debug_log=True,
                integrity_event_sink=sink,
                debug_fingerprint_key=b"abcdef0123456789abcdef0123456789",
            ),
        )
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")

        cache = bundle._cache
        assert cache is not None
        key = next(iter(cache._cache))
        entry = cache._cache[key]
        cache._cache[key] = replace(entry, formatted="Corrupted")

        with pytest.raises(CacheCorruptionError):
            bundle.format_pattern("msg")

        events = sink.snapshot()
        assert len(events) == 1
        assert events[0].kind is CacheIntegrityEventKind.ENTRY_CORRUPTION
        assert events[0].message_id == "msg"
        assert events[0].locale_code == "en"

    def test_cache_stats_report_integrity_event_and_generation_fields(self) -> None:
        bundle = FluentBundle("en", cache=CacheConfig(enable_debug_log=True))
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")
        bundle.clear_cache()

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["max_entry_payload_bytes"] == DEFAULT_MAX_ENTRY_PAYLOAD_BYTES
        assert stats["debug_log_enabled"] is True
        assert stats["cache_generation"] >= 1
        assert stats["debug_log_entries"] >= 0


class TestCustomFunctionCacheability:
    """Custom functions must opt into cacheability explicitly."""

    def test_custom_function_defaults_to_non_cacheable(self) -> None:
        call_count = 0

        def tick(value: object) -> str:
            nonlocal call_count
            call_count += 1
            return f"{value}:{call_count}"

        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_function("TICK", tick)
        bundle.add_resource("msg = { TICK($value) }")

        first, _ = bundle.format_pattern("msg", {"value": "a"})
        second, _ = bundle.format_pattern("msg", {"value": "a"})

        assert first == "a:1"
        assert second == "a:2"
        assert call_count == 2
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 0
        assert stats["uncacheable_function_skips"] == 2

    def test_custom_function_can_opt_into_caching(self) -> None:
        call_count = 0

        def pure_tick(value: object) -> str:
            nonlocal call_count
            call_count += 1
            return f"{value}:{call_count}"

        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_function("PURE_TICK", pure_tick, cacheable=True)
        bundle.add_resource("msg = { PURE_TICK($value) }")

        first, _ = bundle.format_pattern("msg", {"value": "a"})
        second, _ = bundle.format_pattern("msg", {"value": "a"})

        assert first == "a:1"
        assert second == "a:1"
        assert call_count == 1
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hits"] == 1
        assert stats["size"] == 1


class TestPayloadBudget:
    """The cache should describe and enforce a retained payload-byte budget."""

    def test_large_results_are_computed_but_not_cached(self) -> None:
        bundle = FluentBundle(
            "en",
            cache=CacheConfig(max_entry_payload_bytes=50),
        )
        long_text = "x" * 100
        bundle.add_resource(f"msg = {long_text}")

        result, errors = bundle.format_pattern("msg")

        assert result == long_text
        assert errors == ()
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["oversize_skips"] == 1
        assert stats["size"] == 0


class TestFormattingErrorPrivacy:
    """Cache-retained formatting contexts should not keep raw fallback payloads."""

    def test_cached_formatting_errors_store_redacted_fallback_context(self) -> None:
        bundle = FluentBundle("en", cache=CacheConfig(), strict=False)
        bundle.add_resource("msg = { NUMBER($value) }")

        first_result, first_errors = bundle.format_pattern("msg", {"value": "secret-123"})
        cached_result, cached_errors = bundle.format_pattern("msg", {"value": "secret-123"})

        assert first_result == "secret-123"
        assert cached_result == "secret-123"
        assert len(first_errors) == 1
        assert len(cached_errors) == 1
        assert first_errors[0].fallback_value == "secret-123"
        context = cached_errors[0].context
        assert context is not None
        assert context.fallback_value.startswith("fallback[bytes=")
        assert "secret-123" not in context.fallback_value

    def test_cached_formatting_error_redaction_is_idempotent(self) -> None:
        bundle = FluentBundle("en", cache=CacheConfig(), strict=False)
        bundle.add_resource("msg = { NUMBER($value) }")

        _, cached_errors = bundle.format_pattern("msg", {"value": "secret-123"})
        _, cached_errors = bundle.format_pattern("msg", {"value": "secret-123"})

        assert len(cached_errors) == 1
        assert cached_errors[0].sanitized_for_cache() is cached_errors[0]


class TestCorrelationScope:
    """Integrity events should inherit the current logical correlation ID."""

    def test_integrity_event_sink_receives_correlation_id(self) -> None:
        sink = MemoryIntegrityEventSink()
        bundle = FluentBundle(
            "en",
            strict=False,
            cache=CacheConfig(integrity_event_sink=sink),
        )
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")

        cache = bundle._cache
        assert cache is not None
        key = next(iter(cache._cache))
        entry = cache._cache[key]
        cache._cache[key] = replace(entry, formatted="Corrupted")

        with CacheIntegrityCorrelationScope("req-123"), pytest.raises(
            CacheCorruptionError
        ):
            bundle.format_pattern("msg")

        events = sink.snapshot()
        assert events[0].correlation_id == "req-123"
