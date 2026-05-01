# mypy: ignore-errors
from __future__ import annotations

import time

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.constants import DEFAULT_MAX_ENTRY_WEIGHT
from ftllexengine.diagnostics import (
    ErrorCategory,
    FrozenFluentError,
)
from ftllexengine.integrity import CacheCorruptionError, IntegrityContext
from ftllexengine.runtime import FluentBundle
from ftllexengine.runtime.cache import (
    IntegrityCache,
)
from ftllexengine.runtime.cache_config import CacheConfig

# Sentinel key_hash for unit tests that verify checksum mechanics but do not
# need meaningful key binding (all-zeros = "unbound test entry").
_NO_KEY_HASH: bytes = b"\x00" * 8

# ============================================================================
# CHECKSUM VERIFICATION TESTS
# ============================================================================



class TestCacheEntrySizeLimit:
    """IntegrityCache max_entry_weight prevents caching of oversized results."""

    def test_default_max_entry_weight(self) -> None:
        """Default max_entry_weight is DEFAULT_MAX_ENTRY_WEIGHT (10,000 characters)."""
        cache = IntegrityCache(strict=False)
        assert cache.max_entry_weight == DEFAULT_MAX_ENTRY_WEIGHT
        assert cache.max_entry_weight == 10_000

    def test_custom_max_entry_weight(self) -> None:
        """Custom max_entry_weight is stored and returned correctly."""
        cache = IntegrityCache(strict=False, max_entry_weight=1000)
        assert cache.max_entry_weight == 1000

    def test_invalid_max_entry_weight_rejected(self) -> None:
        """Zero and negative max_entry_weight raise ValueError."""
        with pytest.raises(ValueError, match="max_entry_weight must be positive"):
            IntegrityCache(strict=False, max_entry_weight=0)

        with pytest.raises(ValueError, match="max_entry_weight must be positive"):
            IntegrityCache(strict=False, max_entry_weight=-1)

    def test_small_entries_cached(self) -> None:
        """Entries below max_entry_weight are stored and retrievable."""
        cache = IntegrityCache(strict=False, max_entry_weight=1000)

        cache.put("msg", None, None, "en", use_isolating=True, formatted="x" * 100, errors=())

        assert cache.size == 1
        assert cache.oversize_skips == 0

        cached = cache.get("msg", None, None, "en", use_isolating=True)
        assert cached is not None
        assert cached.as_result() == ("x" * 100, ())

    def test_large_entries_not_cached(self) -> None:
        """Entries exceeding max_entry_weight are skipped and counted."""
        cache = IntegrityCache(strict=False, max_entry_weight=100)

        cache.put("msg", None, None, "en", use_isolating=True, formatted="x" * 200, errors=())

        assert cache.size == 0
        assert cache.oversize_skips == 1

        cached = cache.get("msg", None, None, "en", use_isolating=True)
        assert cached is None

    def test_boundary_entry_size(self) -> None:
        """Entry exactly at max_entry_weight is cached (inclusive boundary)."""
        cache = IntegrityCache(strict=False, max_entry_weight=100)

        cache.put("msg", None, None, "en", use_isolating=True, formatted="x" * 100, errors=())

        assert cache.size == 1
        assert cache.oversize_skips == 0

    def test_get_stats_includes_oversize_skips(self) -> None:
        """get_stats() reports oversize_skips and max_entry_weight."""
        cache = IntegrityCache(strict=False, max_entry_weight=50)

        for i in range(5):
            cache.put(f"msg-{i}", None, None, "en", use_isolating=True, formatted="x" * 100, errors=())

        stats = cache.get_stats()
        assert stats["oversize_skips"] == 5
        assert stats["max_entry_weight"] == 50
        assert stats["size"] == 0

    def test_clear_preserves_oversize_skips(self) -> None:
        """clear() removes entries but preserves cumulative oversize_skips counter."""
        cache = IntegrityCache(strict=False, max_entry_weight=50)

        cache.put("msg", None, None, "en", use_isolating=True, formatted="x" * 100, errors=())
        assert cache.oversize_skips == 1

        cache.clear()
        assert cache.oversize_skips == 1

    def test_bundle_cache_uses_default_max_entry_weight(self) -> None:
        """FluentBundle's internal cache uses default max_entry_weight."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg = { $data }")

        small_data = "x" * 100
        bundle.format_pattern("msg", {"data": small_data})

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 1

    @given(st.integers(min_value=1, max_value=1000))
    def test_max_entry_weight_property(self, size: int) -> None:
        """PROPERTY: max_entry_weight is correctly stored and returned."""
        event(f"weight_size={size}")
        cache = IntegrityCache(strict=False, max_entry_weight=size)
        assert cache.max_entry_weight == size

    def test_combined_weight_skips_counter_incremented(self) -> None:
        """Entries skipped due to combined weight increment combined_weight_skips.

        Scenario: formatted string (100 chars) passes check 1 (len <= max_entry_weight=200).
        Error overhead = 100 (base) + 150 (message) = 250. Total = 350 > 200 fails check 3.
        """
        cache = IntegrityCache(strict=False, max_entry_weight=200)
        error = FrozenFluentError("x" * 150, ErrorCategory.REFERENCE)

        cache.put("msg", None, None, "en", use_isolating=True, formatted="x" * 100, errors=(error,))

        stats = cache.get_stats()
        assert stats["combined_weight_skips"] == 1
        assert stats["oversize_skips"] == 0
        assert stats["error_bloat_skips"] == 0
        assert stats["size"] == 0

    def test_combined_weight_skips_distinct_from_oversize_skips(self) -> None:
        """oversize_skips and combined_weight_skips are separate, distinct counters."""
        cache = IntegrityCache(strict=False, max_entry_weight=200)
        heavy_error = FrozenFluentError("x" * 150, ErrorCategory.REFERENCE)

        # Check 1 (oversize): formatted string alone exceeds max_entry_weight
        cache.put("over-msg", None, None, "en", use_isolating=True, formatted="x" * 201, errors=())

        # Check 3 (combined_weight): formatted OK, but combined total exceeds limit
        cache.put("combined-msg", None, None, "en", use_isolating=True, formatted="x" * 100, errors=(heavy_error,))

        stats = cache.get_stats()
        assert stats["oversize_skips"] == 1
        assert stats["combined_weight_skips"] == 1

    def test_combined_weight_skips_distinct_from_error_bloat_skips(self) -> None:
        """error_bloat_skips and combined_weight_skips are separate, distinct counters."""
        cache = IntegrityCache(strict=False, max_entry_weight=200, max_errors_per_entry=2)
        heavy_error = FrozenFluentError("x" * 150, ErrorCategory.REFERENCE)

        # Check 2 (error_bloat): too many errors by count
        many_errors = tuple(
            FrozenFluentError(f"e-{i}", ErrorCategory.REFERENCE) for i in range(3)
        )
        cache.put("bloat-msg", None, None, "en", use_isolating=True, formatted="Hello", errors=many_errors)

        # Check 3 (combined_weight): error count OK (1 <= 2), combined weight fails
        cache.put("combined-msg", None, None, "en", use_isolating=True, formatted="x" * 100, errors=(heavy_error,))

        stats = cache.get_stats()
        assert stats["error_bloat_skips"] == 1
        assert stats["combined_weight_skips"] == 1

    def test_combined_weight_skips_preserved_on_clear(self) -> None:
        """clear() preserves cumulative combined_weight_skips counter."""
        cache = IntegrityCache(strict=False, max_entry_weight=200)
        error = FrozenFluentError("x" * 150, ErrorCategory.REFERENCE)

        cache.put("msg", None, None, "en", use_isolating=True, formatted="x" * 100, errors=(error,))
        assert cache.combined_weight_skips == 1

        cache.clear()
        assert cache.combined_weight_skips == 1

    def test_get_stats_includes_combined_weight_skips(self) -> None:
        """get_stats() reports combined_weight_skips alongside related skip counters."""
        cache = IntegrityCache(strict=False, max_entry_weight=200)
        error = FrozenFluentError("x" * 150, ErrorCategory.REFERENCE)

        cache.put("msg", None, None, "en", use_isolating=True, formatted="x" * 100, errors=(error,))

        stats = cache.get_stats()
        assert "combined_weight_skips" in stats
        assert stats["combined_weight_skips"] == 1

class TestWriteLogEntryWallTime:
    """WriteLogEntry carries both monotonic timestamp and wall_time_unix."""

    def test_write_log_entry_has_wall_time_unix_field(self) -> None:
        """WriteLogEntry.wall_time_unix field exists and is a float."""
        before = time.time()
        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="hello", errors=())
        after = time.time()

        log = cache.get_audit_log()
        assert len(log) >= 1
        entry = log[0]
        assert isinstance(entry.wall_time_unix, float)
        assert isinstance(entry.cache_sequence, int)
        # Wall time should be bracketed between the before/after calls
        assert before <= entry.wall_time_unix <= after

    def test_write_log_entry_timestamp_is_monotonic(self) -> None:
        """WriteLogEntry.timestamp (monotonic) is distinct from wall_time_unix."""

        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="hello", errors=())

        log = cache.get_audit_log()
        entry = log[0]
        # Monotonic and wall clock are different clocks — values may differ
        assert isinstance(entry.timestamp, float)
        assert isinstance(entry.wall_time_unix, float)
        # Both should be positive
        assert entry.timestamp > 0
        assert entry.wall_time_unix > 0

    def test_audit_log_multiple_entries_wall_time_non_decreasing(self) -> None:
        """wall_time_unix values across audit entries are non-decreasing."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.put("a", None, None, "en", use_isolating=True, formatted="A", errors=())
        cache.put("b", None, None, "en", use_isolating=True, formatted="B", errors=())
        cache.put("c", None, None, "en", use_isolating=True, formatted="C", errors=())

        log = cache.get_audit_log()
        wall_times = [e.wall_time_unix for e in log]
        for i in range(len(wall_times) - 1):
            assert wall_times[i] <= wall_times[i + 1], (
                f"wall_time_unix not non-decreasing at index {i}: "
                f"{wall_times[i]} > {wall_times[i + 1]}"
            )

    def test_audit_log_sequence_is_monotonic_even_with_misses(self) -> None:
        """Audit-event sequence increases monotonically across misses and hits."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.get("missing", None, None, "en", use_isolating=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="hello", errors=())
        cache.get("msg", None, None, "en", use_isolating=True)

        log = cache.get_audit_log()
        sequences = [entry.sequence for entry in log]
        assert sequences == sorted(sequences)
        assert [entry.operation for entry in log] == ["MISS", "PUT", "HIT"]
        assert [entry.cache_sequence for entry in log] == [0, 1, 1]

class TestIntegrityContextWallTime:
    """IntegrityContext.wall_time_unix is populated at integrity error sites."""

    def test_integrity_context_wall_time_unix_field_exists(self) -> None:
        """IntegrityContext accepts wall_time_unix and stores it correctly."""
        t = time.time()
        ctx = IntegrityContext(
            component="test",
            operation="check",
            timestamp=time.monotonic(),
            wall_time_unix=t,
        )
        assert ctx.wall_time_unix == t

    def test_integrity_context_wall_time_unix_defaults_to_none(self) -> None:
        """IntegrityContext.wall_time_unix defaults to None for backwards compat."""
        ctx = IntegrityContext(component="test", operation="check")
        assert ctx.wall_time_unix is None

    def test_cache_corruption_error_context_has_wall_time(self) -> None:
        """CacheCorruptionError raised by strict cache carries wall_time_unix."""
        cache = IntegrityCache(enable_audit=True, strict=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="ok", errors=())

        # Corrupt the checksum by manipulating the stored entry directly
        key = next(iter(cache._cache))
        entry = cache._cache[key]

        # Corrupt the checksum in-place via object.__setattr__ (frozen dataclass).
        # content_hash is field(init=False), so we cannot pass it to __init__.
        object.__setattr__(entry, "checksum", b"\x00" * 16)  # deliberately invalid
        cache._cache[key] = entry

        before = time.time()
        with pytest.raises(CacheCorruptionError) as exc_info:
            cache.get("msg", None, None, "en", use_isolating=True)
        after = time.time()

        ctx = exc_info.value.context
        assert ctx is not None
        assert ctx.wall_time_unix is not None
        assert before <= ctx.wall_time_unix <= after
