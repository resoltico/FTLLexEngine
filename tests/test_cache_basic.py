"""Basic caching functionality tests.

Validates FormatCache and FluentBundle caching behavior.
"""

import pytest

from ftllexengine import FluentBundle
from ftllexengine.runtime.cache import FormatCache


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
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
        assert bundle.get_cache_stats() is not None

    def test_cache_hit(self) -> None:
        """Cache hit on repeated format call."""
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
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
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
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
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
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
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
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
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
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
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
        bundle.add_resource("msg = Hello")

        # Warm up cache
        bundle.format_pattern("msg")
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 1

        # Add custom function - cache should be cleared
        def CUSTOM(value: str) -> str:
            return value.upper()

        bundle.add_function("CUSTOM", CUSTOM)
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 0  # Cache cleared

    def test_manual_cache_clear(self) -> None:
        """Manual cache clear works."""
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
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
        bundle = FluentBundle("en", enable_cache=True, cache_size=2)
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
        bundle = FluentBundle("en", enable_cache=True, cache_size=2)
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
        """Cache size must be positive."""
        with pytest.raises(ValueError, match="maxsize must be positive"):
            FluentBundle("en", enable_cache=True, cache_size=0)

        with pytest.raises(ValueError, match="maxsize must be positive"):
            FluentBundle("en", enable_cache=True, cache_size=-1)


class TestCacheStats:
    """Test cache statistics reporting."""

    def test_hit_rate_calculation(self) -> None:
        """Hit rate is calculated correctly."""
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
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
        bundle = FluentBundle("en", enable_cache=True, cache_size=10)
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
        bundle = FluentBundle("en", enable_cache=True, cache_size=500)
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy
        assert cache.maxsize == 500

    def test_cache_hits_property(self) -> None:
        """hits property returns hit count."""
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
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
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
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
        # Test FormatCache.put() directly
        cache = FormatCache(maxsize=2)

        # Put initial value
        cache.put("msg1", {"name": "Alice"}, None, "en", True, ("Hello Alice", ()))
        assert len(cache) == 1

        # Put same key again (should call move_to_end)
        cache.put("msg1", {"name": "Alice"}, None, "en", True, ("Hello Alice!", ()))
        assert len(cache) == 1  # Size unchanged

        # Verify value was updated
        result = cache.get("msg1", {"name": "Alice"}, None, "en", True)
        assert result is not None
        assert result[0] == "Hello Alice!"  # Updated value
