"""Tests for FormatCache behavior, CacheConfig validation, lifecycle management, and thread safety.

Covers:
- FormatCache via FluentBundle: enabled/disabled, hits, misses, invalidation, LRU eviction
- CacheConfig: frozen dataclass validation, immutability, defaults
- Cache lifecycle: clearing locale, date, currency, and all caches
- Thread safety: concurrent reads, cache clears, and LRU eviction under contention
"""

# ruff: noqa: PLC0415

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

import ftllexengine
from ftllexengine import FluentBundle
from ftllexengine.constants import DEFAULT_CACHE_SIZE, DEFAULT_MAX_ENTRY_SIZE
from ftllexengine.locale_utils import clear_locale_cache, get_babel_locale
from ftllexengine.parsing import clear_currency_caches, clear_date_caches
from ftllexengine.parsing.currency import (
    _build_currency_maps_from_cldr,
    _get_currency_maps,
    _get_currency_pattern,
)
from ftllexengine.parsing.dates import _get_date_patterns, _get_datetime_patterns
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.runtime.cache_config import CacheConfig

# ============================================================================
# FORMAT CACHE BEHAVIOR VIA FLUENTBUNDLE
# ============================================================================


class TestCacheDisabled:
    """Test behavior when caching is disabled (default)."""

    def test_caching_disabled_by_default(self) -> None:
        """Caching is disabled by default."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg = Hello")

        # Cache methods should handle None cache gracefully
        bundle.clear_cache()  # Should not raise
        stats = bundle.get_cache_stats()
        assert stats is None

    def test_format_without_cache(self) -> None:
        """Format works normally without cache."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        result1, errors1 = bundle.format_pattern("msg", {"name": "Alice"})
        result2, errors2 = bundle.format_pattern("msg", {"name": "Alice"})

        assert result1 == result2 == "Hello, Alice!"
        assert errors1 == errors2 == ()


class TestCacheEnabled:
    """Test behavior when caching is enabled."""

    def test_enable_cache(self) -> None:
        """Enable caching via constructor."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        assert bundle.get_cache_stats() is not None

    def test_cache_hit(self) -> None:
        """Cache hit on repeated format call."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        # First call - cache miss
        result1, errors1 = bundle.format_pattern("msg", {"name": "Alice"})
        stats1 = bundle.get_cache_stats()
        assert stats1 is not None
        assert stats1["misses"] == 1
        assert stats1["hits"] == 0

        # Second call - cache hit
        result2, errors2 = bundle.format_pattern("msg", {"name": "Alice"})
        stats2 = bundle.get_cache_stats()
        assert stats2 is not None
        assert stats2["misses"] == 1
        assert stats2["hits"] == 1

        # Results must match
        assert result1 == result2 == "Hello, Alice!"
        assert errors1 == errors2 == ()

    def test_cache_miss_different_args(self) -> None:
        """Cache miss when args differ."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        result1, _ = bundle.format_pattern("msg", {"name": "Alice"})
        result2, _ = bundle.format_pattern("msg", {"name": "Bob"})

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["misses"] == 2  # Two different cache keys
        assert stats["hits"] == 0

        assert result1 == "Hello, Alice!"
        assert result2 == "Hello, Bob!"

    def test_cache_miss_different_message_id(self) -> None:
        """Cache miss when message_id differs."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("""
            msg1 = Message 1
            msg2 = Message 2
        """)

        bundle.format_pattern("msg1")
        bundle.format_pattern("msg2")

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["misses"] == 2
        assert stats["hits"] == 0

    def test_cache_miss_different_attribute(self) -> None:
        """Cache miss when attribute differs."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("""
            msg = Hello
                .tooltip = Tooltip text
                .aria-label = Aria label
        """)

        bundle.format_pattern("msg")
        bundle.format_pattern("msg", attribute="tooltip")
        bundle.format_pattern("msg", attribute="aria-label")

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["misses"] == 3  # Three different cache keys
        assert stats["hits"] == 0


class TestCacheInvalidation:
    """Test cache invalidation on bundle mutations."""

    def test_cache_cleared_on_add_resource(self) -> None:
        """Cache is cleared when add_resource is called."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        # Warm up cache
        bundle.format_pattern("msg")
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 1

        # Add new resource - cache should be cleared
        bundle.add_resource("msg2 = World")
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 0  # Cache cleared
        assert stats["hits"] == 0  # Stats reset
        assert stats["misses"] == 0

    def test_cache_cleared_on_add_function(self) -> None:
        """Cache is cleared when add_function is called."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        # Warm up cache
        bundle.format_pattern("msg")
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 1

        # Add custom function - cache should be cleared
        def CUSTOM(value: str) -> str:  # noqa: N802
            return value.upper()

        bundle.add_function("CUSTOM", CUSTOM)
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 0  # Cache cleared

    def test_manual_cache_clear(self) -> None:
        """Manual cache clear works."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        # Warm up cache
        bundle.format_pattern("msg")
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 1

        # Manual clear
        bundle.clear_cache()
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 0


class TestCacheSize:
    """Test cache size limits and LRU eviction."""

    def test_cache_size_limit(self) -> None:
        """Cache respects size limit."""
        bundle = FluentBundle("en", cache=CacheConfig(size=2))
        bundle.add_resource("msg1 = Message 1")
        bundle.add_resource("msg2 = Message 2")
        bundle.add_resource("msg3 = Message 3")

        # Add 3 entries (size limit is 2)
        bundle.format_pattern("msg1")
        bundle.format_pattern("msg2")
        bundle.format_pattern("msg3")

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2  # Size limit enforced
        assert stats["maxsize"] == 2

    def test_lru_eviction(self) -> None:
        """LRU eviction removes oldest entry."""
        bundle = FluentBundle("en", cache=CacheConfig(size=2))
        bundle.add_resource("msg1 = Message 1")
        bundle.add_resource("msg2 = Message 2")
        bundle.add_resource("msg3 = Message 3")

        # Add msg1 and msg2 to cache
        bundle.format_pattern("msg1")
        bundle.format_pattern("msg2")

        # Add msg3 - should evict msg1 (oldest)
        bundle.format_pattern("msg3")

        # Access msg1 again - should be cache miss
        bundle.format_pattern("msg1")

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["misses"] == 4  # msg1, msg2, msg3, msg1 again
        assert stats["hits"] == 0

    def test_cache_size_validation(self) -> None:
        """Cache size must be positive (validated at CacheConfig construction)."""
        with pytest.raises(ValueError, match="size must be positive"):
            CacheConfig(size=0)

        with pytest.raises(ValueError, match="size must be positive"):
            CacheConfig(size=-1)


class TestCacheConfigValidation:
    """CacheConfig frozen dataclass: validation, immutability, defaults."""

    @given(value=st.integers(max_value=0))
    def test_size_rejects_non_positive(self, value: int) -> None:
        """size <= 0 raises ValueError at construction."""
        with pytest.raises(ValueError, match="size must be positive"):
            CacheConfig(size=value)
        event(f"size={value}")

    @given(value=st.integers(max_value=0))
    def test_max_entry_weight_rejects_non_positive(self, value: int) -> None:
        """max_entry_weight <= 0 raises ValueError at construction."""
        with pytest.raises(ValueError, match="max_entry_weight must be positive"):
            CacheConfig(max_entry_weight=value)
        event(f"max_entry_weight={value}")

    @given(value=st.integers(max_value=0))
    def test_max_errors_per_entry_rejects_non_positive(self, value: int) -> None:
        """max_errors_per_entry <= 0 raises ValueError at construction."""
        with pytest.raises(ValueError, match="max_errors_per_entry must be positive"):
            CacheConfig(max_errors_per_entry=value)
        event(f"max_errors_per_entry={value}")

    @given(value=st.integers(max_value=0))
    def test_max_audit_entries_rejects_non_positive(self, value: int) -> None:
        """max_audit_entries <= 0 raises ValueError at construction."""
        with pytest.raises(ValueError, match="max_audit_entries must be positive"):
            CacheConfig(max_audit_entries=value)
        event(f"max_audit_entries={value}")

    @given(
        size=st.integers(min_value=1, max_value=100_000),
        max_entry_weight=st.integers(min_value=1, max_value=100_000),
        max_errors_per_entry=st.integers(min_value=1, max_value=1000),
        max_audit_entries=st.integers(min_value=1, max_value=100_000),
        write_once=st.booleans(),
        integrity_strict=st.booleans(),
        enable_audit=st.booleans(),
    )
    def test_valid_construction_preserves_all_fields(
        self,
        size: int,
        max_entry_weight: int,
        max_errors_per_entry: int,
        max_audit_entries: int,
        write_once: bool,
        integrity_strict: bool,
        enable_audit: bool,
    ) -> None:
        """All positive numeric fields and any boolean combination succeeds."""
        cfg = CacheConfig(
            size=size,
            write_once=write_once,
            integrity_strict=integrity_strict,
            enable_audit=enable_audit,
            max_audit_entries=max_audit_entries,
            max_entry_weight=max_entry_weight,
            max_errors_per_entry=max_errors_per_entry,
        )
        assert cfg.size == size
        assert cfg.write_once is write_once
        assert cfg.integrity_strict is integrity_strict
        assert cfg.enable_audit is enable_audit
        assert cfg.max_audit_entries == max_audit_entries
        assert cfg.max_entry_weight == max_entry_weight
        assert cfg.max_errors_per_entry == max_errors_per_entry
        strict_label = "strict" if integrity_strict else "lenient"
        event(f"outcome={strict_label}")

    def test_defaults_match_constants(self) -> None:
        """Default CacheConfig() uses documented constant defaults."""
        cfg = CacheConfig()
        assert cfg.size == DEFAULT_CACHE_SIZE
        assert cfg.max_entry_weight == DEFAULT_MAX_ENTRY_SIZE
        assert cfg.write_once is False
        assert cfg.integrity_strict is True
        assert cfg.enable_audit is False
        assert cfg.max_audit_entries == 10_000
        assert cfg.max_errors_per_entry == 50

    def test_immutability_enforced(self) -> None:
        """Frozen dataclass rejects field mutation."""
        cfg = CacheConfig()
        with pytest.raises(AttributeError):
            cfg.size = 999  # type: ignore[misc]
        with pytest.raises(AttributeError):
            cfg.write_once = True  # type: ignore[misc]
        with pytest.raises(AttributeError):
            cfg.integrity_strict = False  # type: ignore[misc]

    def test_equality_and_identity(self) -> None:
        """Equal configs compare equal; different configs compare unequal."""
        a = CacheConfig(size=500, write_once=True)
        b = CacheConfig(size=500, write_once=True)
        c = CacheConfig(size=500, write_once=False)
        assert a == b
        assert a is not b
        assert a != c


class TestCacheStats:
    """Test cache statistics reporting."""

    def test_hit_rate_calculation(self) -> None:
        """Hit rate is calculated correctly."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        # 1 miss
        bundle.format_pattern("msg")
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hit_rate"] == 0  # 0/1 = 0%

        # 1 hit
        bundle.format_pattern("msg")
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hit_rate"] == 50  # 1/2 = 50%

        # 2 more hits
        bundle.format_pattern("msg")
        bundle.format_pattern("msg")
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hit_rate"] == 75  # 3/4 = 75%


class TestCacheIntrospection:
    """Test cache introspection APIs."""

    def test_cache_len(self) -> None:
        """__len__ returns cache size."""
        bundle = FluentBundle("en", cache=CacheConfig(size=10))
        bundle.add_resource("msg1 = Message 1\nmsg2 = Message 2")

        # Cache is empty initially
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy
        assert len(cache) == 0

        # Add entries
        bundle.format_pattern("msg1")
        assert len(cache) == 1

        bundle.format_pattern("msg2")
        assert len(cache) == 2

    def test_cache_maxsize_property(self) -> None:
        """maxsize property returns configured max size."""
        bundle = FluentBundle("en", cache=CacheConfig(size=500))
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy
        assert cache.maxsize == 500

    def test_cache_hits_property(self) -> None:
        """hits property returns hit count."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # No hits initially
        assert cache.hits == 0

        # First call is miss
        bundle.format_pattern("msg")
        assert cache.hits == 0

        # Second call is hit
        bundle.format_pattern("msg")
        assert cache.hits == 1

        # Third call is hit
        bundle.format_pattern("msg")
        assert cache.hits == 2

    def test_cache_misses_property(self) -> None:
        """misses property returns miss count."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # No misses initially
        assert cache.misses == 0

        # First call is miss
        bundle.format_pattern("msg")
        assert cache.misses == 1

        # Second call is hit (miss count unchanged)
        bundle.format_pattern("msg")
        assert cache.misses == 1

    def test_cache_put_updates_existing_key(self) -> None:
        """Updating existing cache entry moves it to end (LRU)."""
        cache = IntegrityCache(strict=False, maxsize=2)

        # Put initial value
        cache.put("msg1", {"name": "Alice"}, None, "en", True, "Hello Alice", ())
        assert len(cache) == 1

        # Put same key again (should call move_to_end)
        cache.put("msg1", {"name": "Alice"}, None, "en", True, "Hello Alice!", ())
        assert len(cache) == 1  # Size unchanged

        # Verify value was updated
        entry = cache.get("msg1", {"name": "Alice"}, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Hello Alice!"  # Updated value


# ============================================================================
# CACHE LIFECYCLE: CLEARING LOCALE, DATE, CURRENCY, AND ALL CACHES
# ============================================================================


class TestLocaleCacheClear:
    """Test locale_utils.clear_locale_cache() function."""

    def test_clear_empty_cache_is_noop(self) -> None:
        """Clearing an empty cache does not raise."""
        clear_locale_cache()
        clear_locale_cache()  # Multiple clears are safe

    def test_clear_removes_cached_locales(self) -> None:
        """Clearing cache removes cached Babel Locale objects."""
        # Populate cache
        locale1 = get_babel_locale("en_US")
        locale2 = get_babel_locale("de_DE")

        # Verify cache is populated (cache_info shows hits=0, misses=2)
        info_before = get_babel_locale.cache_info()
        assert info_before.misses >= 2

        # Clear cache
        clear_locale_cache()

        # Cache should be empty (currsize=0)
        info_after = get_babel_locale.cache_info()
        assert info_after.currsize == 0

        # Re-fetch should create new cache entries
        locale1_new = get_babel_locale("en_US")
        locale2_new = get_babel_locale("de_DE")

        # Verify these are new objects (equal but potentially different instances)
        assert locale1_new.language == locale1.language
        assert locale2_new.language == locale2.language

    def test_clear_cache_info_resets(self) -> None:
        """Cache statistics reset after clear."""
        # Clear first to ensure clean state
        clear_locale_cache()

        # Populate cache
        get_babel_locale("en_US")
        get_babel_locale("en_US")  # Should be cache hit

        info = get_babel_locale.cache_info()
        assert info.hits >= 1

        # Clear
        clear_locale_cache()

        # Hits/misses reset
        info_after = get_babel_locale.cache_info()
        assert info_after.hits == 0
        assert info_after.misses == 0


class TestDateCachesClear:
    """Test parsing.dates.clear_date_caches() function."""

    def test_clear_empty_cache_is_noop(self) -> None:
        """Clearing empty date caches does not raise."""
        clear_date_caches()
        clear_date_caches()  # Multiple clears are safe

    def test_clear_removes_date_patterns(self) -> None:
        """Clearing cache removes cached date patterns."""
        # Populate caches by accessing patterns
        _get_date_patterns("en_US")
        _get_datetime_patterns("en_US")

        # Verify caches are populated
        date_info = _get_date_patterns.cache_info()
        datetime_info = _get_datetime_patterns.cache_info()
        assert date_info.currsize >= 1
        assert datetime_info.currsize >= 1

        # Clear caches
        clear_date_caches()

        # Verify caches are empty
        date_info_after = _get_date_patterns.cache_info()
        datetime_info_after = _get_datetime_patterns.cache_info()
        assert date_info_after.currsize == 0
        assert datetime_info_after.currsize == 0


class TestCurrencyCachesClear:
    """Test parsing.currency.clear_currency_caches() function."""

    def test_clear_empty_cache_is_noop(self) -> None:
        """Clearing empty currency caches does not raise."""
        clear_currency_caches()
        clear_currency_caches()  # Multiple clears are safe

    def test_clear_removes_pattern_cache(self) -> None:
        """Clearing cache removes currency pattern cache."""
        # Populate pattern cache
        _get_currency_pattern()

        # Verify cache is populated
        info = _get_currency_pattern.cache_info()
        assert info.currsize >= 1

        # Clear caches
        clear_currency_caches()

        # Verify cache is empty
        info_after = _get_currency_pattern.cache_info()
        assert info_after.currsize == 0

    def test_clear_removes_all_currency_caches(self) -> None:
        """Clearing removes all three currency cache layers."""
        # Populate all caches
        _get_currency_pattern()
        _get_currency_maps()  # This triggers _build_currency_maps_from_cldr

        # Verify caches populated
        assert _get_currency_pattern.cache_info().currsize >= 1
        assert _get_currency_maps.cache_info().currsize >= 1

        # Clear all
        clear_currency_caches()

        # Verify all caches empty
        assert _get_currency_pattern.cache_info().currsize == 0
        assert _get_currency_maps.cache_info().currsize == 0
        assert _build_currency_maps_from_cldr.cache_info().currsize == 0


class TestClearAllCaches:
    """Test ftllexengine.clear_all_caches() unified function."""

    def test_clear_all_empty_is_noop(self) -> None:
        """Clearing all caches when empty does not raise."""
        ftllexengine.clear_all_caches()
        ftllexengine.clear_all_caches()  # Multiple clears are safe

    def test_clear_all_clears_locale_cache(self) -> None:
        """clear_all_caches() clears locale cache."""
        # Populate locale cache
        get_babel_locale("en_US")
        assert get_babel_locale.cache_info().currsize >= 1

        # Clear all
        ftllexengine.clear_all_caches()

        # Locale cache should be empty
        assert get_babel_locale.cache_info().currsize == 0

    def test_clear_all_clears_date_caches(self) -> None:
        """clear_all_caches() clears date pattern caches."""
        # Populate date caches
        _get_date_patterns("en_US")
        _get_datetime_patterns("en_US")
        assert _get_date_patterns.cache_info().currsize >= 1

        # Clear all
        ftllexengine.clear_all_caches()

        # Date caches should be empty
        assert _get_date_patterns.cache_info().currsize == 0
        assert _get_datetime_patterns.cache_info().currsize == 0

    def test_clear_all_clears_currency_caches(self) -> None:
        """clear_all_caches() clears currency caches."""
        # Populate currency caches
        _get_currency_pattern()
        assert _get_currency_pattern.cache_info().currsize >= 1

        # Clear all
        ftllexengine.clear_all_caches()

        # Currency caches should be empty
        assert _get_currency_pattern.cache_info().currsize == 0

    def test_clear_all_clears_locale_context_cache(self) -> None:
        """clear_all_caches() clears LocaleContext cache."""
        from ftllexengine.runtime.locale_context import LocaleContext

        # Populate LocaleContext cache
        LocaleContext.create("en_US")
        info = LocaleContext.cache_info()
        size = info["size"]
        assert isinstance(size, int)
        assert size >= 1

        # Clear all
        ftllexengine.clear_all_caches()

        # LocaleContext cache should be empty
        info_after = LocaleContext.cache_info()
        size_after = info_after["size"]
        assert isinstance(size_after, int)
        assert size_after == 0

    def test_clear_all_clears_introspection_cache(self) -> None:
        """clear_all_caches() clears introspection cache."""
        from ftllexengine.introspection import introspect_message
        from ftllexengine.syntax.ast import Message
        from ftllexengine.syntax.parser import FluentParserV1

        # Populate introspection cache
        parser = FluentParserV1()
        resource = parser.parse("msg = Hello { $name }")
        message = resource.entries[0]
        assert isinstance(message, Message)

        result1 = introspect_message(message)

        # Clear all caches
        ftllexengine.clear_all_caches()

        # After clear, introspecting same message should create new result
        result2 = introspect_message(message)

        # Objects are equal but not identical (cache was cleared)
        assert result1 == result2
        assert result1 is not result2


class TestCacheLifecycleExport:
    """Test that cache lifecycle functions are properly exported."""

    def test_clear_all_caches_in_all(self) -> None:
        """clear_all_caches is in ftllexengine.__all__."""
        assert "clear_all_caches" in ftllexengine.__all__

    def test_clear_functions_importable_from_parsing(self) -> None:
        """Cache clear functions are importable from parsing module."""
        from ftllexengine.parsing import clear_currency_caches, clear_date_caches

        # Functions should be callable
        assert callable(clear_currency_caches)
        assert callable(clear_date_caches)

    def test_clear_locale_cache_importable(self) -> None:
        """clear_locale_cache is importable from locale_utils."""
        from ftllexengine.locale_utils import clear_locale_cache

        assert callable(clear_locale_cache)


class TestCacheLifecycleIdempotency:
    """Test idempotency property of cache clear functions."""

    def test_locale_clear_idempotent(self) -> None:
        """Multiple locale cache clears are equivalent to single clear."""
        get_babel_locale("en_US")
        clear_locale_cache()
        clear_locale_cache()
        clear_locale_cache()
        assert get_babel_locale.cache_info().currsize == 0

    def test_date_clear_idempotent(self) -> None:
        """Multiple date cache clears are equivalent to single clear."""
        _get_date_patterns("en_US")
        clear_date_caches()
        clear_date_caches()
        clear_date_caches()
        assert _get_date_patterns.cache_info().currsize == 0

    def test_currency_clear_idempotent(self) -> None:
        """Multiple currency cache clears are equivalent to single clear."""
        _get_currency_pattern()
        clear_currency_caches()
        clear_currency_caches()
        clear_currency_caches()
        assert _get_currency_pattern.cache_info().currsize == 0

    def test_clear_all_idempotent(self) -> None:
        """Multiple clear_all_caches calls are equivalent to single call."""
        get_babel_locale("en_US")
        _get_date_patterns("en_US")
        _get_currency_pattern()

        ftllexengine.clear_all_caches()
        ftllexengine.clear_all_caches()
        ftllexengine.clear_all_caches()

        assert get_babel_locale.cache_info().currsize == 0
        assert _get_date_patterns.cache_info().currsize == 0
        assert _get_currency_pattern.cache_info().currsize == 0


# ============================================================================
# THREAD SAFETY
# ============================================================================


class TestCacheConcurrency:
    """Test cache thread safety."""

    def test_concurrent_reads(self) -> None:
        """Concurrent reads are thread-safe."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        def format_message(name: str) -> str:
            result, _ = bundle.format_pattern("msg", {"name": name})
            return result

        # Concurrent reads from multiple threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(format_message, "Alice") for _ in range(100)]
            results = [future.result() for future in as_completed(futures)]

        # All results should be identical
        assert all(r == "Hello, Alice!" for r in results)

        # Check cache was populated
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hits"] > 0  # At least some cache hits

    def test_concurrent_different_args(self) -> None:
        """Concurrent reads with different args are thread-safe."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        names = ["Alice", "Bob", "Charlie", "David"]

        def format_message(name: str) -> str:
            result, _ = bundle.format_pattern("msg", {"name": name})
            return result

        # Concurrent reads with different args
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(format_message, names[i % len(names)]) for i in range(100)
            ]
            results = [future.result() for future in as_completed(futures)]

        # Check results are correct
        for result in results:
            assert result.startswith("Hello, ")

    def test_concurrent_cache_clear(self) -> None:
        """Concurrent cache clear is thread-safe."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        errors = []

        def format_and_clear() -> None:
            try:
                for _ in range(10):
                    bundle.format_pattern("msg")
                    bundle.clear_cache()
            except Exception as e:  # pylint: disable=broad-exception-caught
                errors.append(e)

        # Multiple threads formatting and clearing
        threads = [threading.Thread(target=format_and_clear) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # No exceptions should occur
        assert len(errors) == 0

    def test_concurrent_add_resource(self) -> None:
        """Concurrent add_resource with formatting is thread-safe."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        errors = []

        def format_message() -> None:
            try:
                for _ in range(10):
                    bundle.format_pattern("msg")
            except Exception as e:  # pylint: disable=broad-exception-caught
                errors.append(e)

        def add_resource() -> None:
            try:
                for i in range(5):
                    bundle.add_resource(f"msg{i} = World {i}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                errors.append(e)

        # Mix of formatting and resource addition
        format_threads = [threading.Thread(target=format_message) for _ in range(3)]
        add_threads = [threading.Thread(target=add_resource) for _ in range(2)]

        all_threads = format_threads + add_threads
        for thread in all_threads:
            thread.start()
        for thread in all_threads:
            thread.join()

        # No exceptions should occur
        assert len(errors) == 0


class TestCacheRaceConditions:
    """Test for potential race conditions."""

    def test_no_race_on_lru_eviction(self) -> None:
        """No race condition during LRU eviction."""
        bundle = FluentBundle("en", cache=CacheConfig(size=10))
        bundle.add_resource(
            "\n".join([f"msg{i} = Message {i}" for i in range(20)])
        )

        def format_messages() -> None:
            for i in range(20):
                bundle.format_pattern(f"msg{i}")

        # Multiple threads causing evictions
        threads = [threading.Thread(target=format_messages) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Cache should be at or below size limit
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] <= 10

    def test_cache_stats_consistency(self) -> None:
        """Cache stats remain consistent under concurrent access."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        def format_many() -> None:
            for _ in range(100):
                bundle.format_pattern("msg")

        # Multiple threads accessing cache
        threads = [threading.Thread(target=format_many) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Stats should be consistent
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hits"] + stats["misses"] == 500  # 100 * 5 threads
        assert stats["hits"] >= 495  # At least 495 hits (first 5 are misses)
