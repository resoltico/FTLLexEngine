"""Tests for bounded cache protection in date parsing.

Validates that parse_date/parse_datetime caches are bounded to prevent
memory exhaustion DoS attacks via arbitrary locale strings.

Security context: Unbounded @cache allows attacker to exhaust memory by
cycling unique fake locale strings. Bounded @lru_cache with maxsize
prevents unbounded growth.
"""

from ftllexengine.constants import MAX_LOCALE_CACHE_SIZE
from ftllexengine.parsing.dates import (
    _get_date_patterns,
    _get_datetime_patterns,
    clear_date_caches,
)


class TestCacheBoundsProtection:
    """Verify caches are bounded to prevent DoS attacks."""

    def test_date_patterns_cache_has_maxsize(self) -> None:
        """Verify _get_date_patterns uses bounded lru_cache."""
        # lru_cache exposes cache_info() with maxsize attribute
        cache_info = _get_date_patterns.cache_info()
        assert cache_info.maxsize == MAX_LOCALE_CACHE_SIZE
        assert cache_info.maxsize is not None  # Not unbounded

    def test_datetime_patterns_cache_has_maxsize(self) -> None:
        """Verify _get_datetime_patterns uses bounded lru_cache."""
        cache_info = _get_datetime_patterns.cache_info()
        assert cache_info.maxsize == MAX_LOCALE_CACHE_SIZE
        assert cache_info.maxsize is not None  # Not unbounded

    def test_cache_eviction_under_pressure(self) -> None:
        """Verify cache evicts old entries when maxsize exceeded."""
        # Clear to start fresh
        clear_date_caches()

        # Fill cache beyond maxsize with fake locales
        # These will return empty tuples but still get cached
        num_locales = MAX_LOCALE_CACHE_SIZE + 50
        for i in range(num_locales):
            fake_locale = f"fake_locale_{i:04d}"
            _get_date_patterns(fake_locale)

        # Cache should be capped at maxsize
        cache_info = _get_date_patterns.cache_info()
        assert cache_info.currsize <= MAX_LOCALE_CACHE_SIZE
        assert cache_info.misses >= num_locales  # All fake locales miss

        # Clean up
        clear_date_caches()

    def test_clear_date_caches_works(self) -> None:
        """Verify clear_date_caches() clears both pattern caches."""
        # Populate caches
        _get_date_patterns("en_US")
        _get_datetime_patterns("en_US")

        # Verify populated
        assert _get_date_patterns.cache_info().currsize > 0
        assert _get_datetime_patterns.cache_info().currsize > 0

        # Clear
        clear_date_caches()

        # Verify cleared
        assert _get_date_patterns.cache_info().currsize == 0
        assert _get_datetime_patterns.cache_info().currsize == 0

    def test_invalid_locales_cached_but_bounded(self) -> None:
        """Invalid locales return empty tuples but are still cached (bounded)."""
        clear_date_caches()

        # Call with invalid locale
        result = _get_date_patterns("not_a_real_locale_xyz")
        assert result == ()  # Empty tuple for unknown locale

        # Verify it was cached
        info = _get_date_patterns.cache_info()
        assert info.currsize >= 1

        # Clean up
        clear_date_caches()


class TestCacheEfficiency:
    """Verify cache hit behavior for legitimate usage."""

    def test_valid_locale_cached(self) -> None:
        """Valid locales are cached and subsequent calls hit cache."""
        clear_date_caches()

        # First call - cache miss
        _get_date_patterns("en_US")
        info1 = _get_date_patterns.cache_info()

        # Second call - cache hit
        _get_date_patterns("en_US")
        info2 = _get_date_patterns.cache_info()

        assert info2.hits > info1.hits  # Second call was a hit
        assert info2.currsize == info1.currsize  # No new entry

        clear_date_caches()

    def test_datetime_patterns_cache_shared_date_patterns(self) -> None:
        """Verify _get_datetime_patterns internally uses _get_date_patterns cache."""
        clear_date_caches()

        # Call datetime patterns (internally calls date patterns)
        _get_datetime_patterns("en_US")

        # Date patterns should also be cached
        date_info = _get_date_patterns.cache_info()
        assert date_info.currsize >= 1  # en_US date patterns cached

        clear_date_caches()
