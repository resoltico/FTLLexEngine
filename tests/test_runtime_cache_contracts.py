"""Direct tests for immutable cache surface contracts."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from ftllexengine.core.value_types import FluentNumber
from ftllexengine.diagnostics import Diagnostic, DiagnosticCode, ErrorCategory, FrozenFluentError
from ftllexengine.diagnostics.codes import SourceSpan
from ftllexengine.runtime.cache_events import (
    CacheIntegrityCorrelationScope,
    current_cache_integrity_task_name,
)
from ftllexengine.runtime.cache_key_codec import _encode_hashable_value
from ftllexengine.runtime.cache_keys import _validated_mapping_items, make_hashable
from ftllexengine.runtime.cache_types import (
    CacheStats,
    IntegrityCacheEntry,
    _estimate_error_payload_bytes,
)


def _stats_snapshot() -> CacheStats:
    """Build one representative immutable stats snapshot for direct API tests."""
    return CacheStats(
        size=1,
        maxsize=10,
        max_entry_payload_bytes=100,
        max_errors_per_entry=5,
        hits=2,
        misses=1,
        hit_rate=66.67,
        unhashable_skips=0,
        oversize_skips=0,
        error_bloat_skips=0,
        combined_payload_skips=0,
        corruption_detected=0,
        integrity_events_emitted=0,
        idempotent_writes=0,
        write_once_conflicts=0,
        uncacheable_function_skips=0,
        sequence=3,
        cache_generation=1,
        write_once=False,
        debug_log_enabled=False,
        debug_log_entries=0,
    )


class TestCacheStatsSnapshot:
    """CacheStats should behave like an immutable mapping snapshot."""

    def test_len_matches_number_of_exposed_fields(self) -> None:
        """The snapshot length should reflect the public stats contract exactly."""
        stats = _stats_snapshot()
        assert len(stats) == len(tuple(stats))

    def test_as_dict_materializes_plain_mapping_copy(self) -> None:
        """Callers that need a mutable copy can opt into it explicitly."""
        stats = _stats_snapshot()
        materialized = stats.as_dict()

        assert isinstance(stats, Mapping)
        assert materialized["hits"] == 2
        assert materialized["debug_log_enabled"] is False
        materialized["hits"] = 99
        assert stats["hits"] == 2

    def test_unknown_key_raises_key_error(self) -> None:
        """Mapping-style access should fail fast for unsupported keys."""
        stats = _stats_snapshot()

        with pytest.raises(KeyError, match="missing"):
            _ = stats["missing"]


class TestValidatedMappingItems:
    """Cache-key normalization should reject hostile key types directly."""

    def test_non_string_mapping_key_raises_type_error(self) -> None:
        """Cache-key shaping must not sort or hash arbitrary mapping keys."""
        with pytest.raises(TypeError, match="must be str, got int"):
            _validated_mapping_items({1: "value"})


class TestCacheKeyCodec:
    """The canonical key codec should handle every supported scalar edge."""

    def test_scalar_edge_values_encode_without_error(self) -> None:
        values: tuple[Any, ...] = (
            Decimal("NaN"),
            Decimal("12.34"),
            datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None),
            date(2024, 1, 2),
            FluentNumber(value=1, formatted="1", precision=None),
        )

        for value in values:
            encoded = _encode_hashable_value(cast("Any", value))
            assert isinstance(encoded, bytes)
            assert encoded

    def test_unsupported_scalar_type_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Unsupported cache key value type"):
            _encode_hashable_value(cast("Any", object()))

    def test_make_hashable_supports_generic_sequence_fallback(self) -> None:
        assert make_hashable(range(3)) == (
            "__seq__",
            (("__int__", 0), ("__int__", 1), ("__int__", 2)),
        )


class TestCacheEntryPayloadAccounting:
    """Cached error payload estimation should include structured diagnostics."""

    def test_error_payload_counts_span_and_resolution_path(self) -> None:
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="missing",
            span=SourceSpan(start=0, end=3, line=1, column=1),
            resolution_path=("msg", "attr"),
        )
        error = FrozenFluentError(
            "missing",
            ErrorCategory.REFERENCE,
            diagnostic=diagnostic,
        )

        assert _estimate_error_payload_bytes(error) > len("missing")

    def test_entry_verify_fails_when_content_hash_is_tampered(self) -> None:
        entry = IntegrityCacheEntry.create("value", (), sequence=1, key_hash=b"\x00" * 16)
        object.__setattr__(entry, "content_hash", b"\x01" * 16)

        assert entry.verify() is False


class TestCacheEventHelpers:
    """Async helper surfaces should expose task-local names when available."""

    def test_current_cache_integrity_task_name_uses_active_asyncio_task(self) -> None:
        async def exercise() -> str | None:
            task = asyncio.current_task()
            assert task is not None
            task.set_name("cache-contract-task")
            return current_cache_integrity_task_name()

        assert asyncio.run(exercise()) == "cache-contract-task"

    def test_correlation_scope_exit_without_enter_is_a_no_op(self) -> None:
        scope = CacheIntegrityCorrelationScope("req-123")
        scope.__exit__(None, None, None)
