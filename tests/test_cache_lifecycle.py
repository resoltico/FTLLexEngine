"""Tests for cache lifecycle management API.

Validates cache clear functions across all modules:
- locale_utils.clear_locale_cache()
- parsing.dates.clear_date_caches()
- parsing.currency.clear_currency_caches()
- ftllexengine.clear_all_caches()

Property: All clear functions are idempotent and thread-safe.
"""
# ruff: noqa: PLC0415

from __future__ import annotations

import ftllexengine
from ftllexengine.locale_utils import clear_locale_cache, get_babel_locale
from ftllexengine.parsing import clear_currency_caches, clear_date_caches
from ftllexengine.parsing.currency import (
    _build_currency_maps_from_cldr,
    _get_currency_maps,
    _get_currency_pattern,
)
from ftllexengine.parsing.dates import _get_date_patterns, _get_datetime_patterns


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
        # (We can't directly check introspection cache size, but we can verify
        # the behavior: same message after clear creates new object)
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
