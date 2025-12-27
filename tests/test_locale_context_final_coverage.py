"""Final coverage tests for runtime/locale_context.py achieving 100%.

Covers remaining uncovered lines: double-check cache pattern and datetime formatting edge case.

Python 3.13+.
"""

from datetime import UTC, datetime
from unittest.mock import patch

from ftllexengine.locale_utils import normalize_locale
from ftllexengine.runtime.locale_context import LocaleContext


class TestLocaleContextCachingRaceCondition:
    """Test cache double-check pattern for thread safety."""

    def test_cache_double_check_pattern(self) -> None:
        """Test cache double-check pattern when another thread adds entry first."""
        # Clear cache first
        LocaleContext.clear_cache()

        # Create first instance
        ctx1 = LocaleContext.create("en-US")

        # Simulate race condition: manually add to cache while holding lock
        # to test the double-check return path
        with LocaleContext._cache_lock:
            # Cache key is normalized
            cache_key = normalize_locale("en-US")

            # The key should already be in cache from ctx1 creation
            assert cache_key in LocaleContext._cache

            # Try to create again - should hit the double-check return
            # This simulates the case where between the first check and lock acquisition,
            # another thread added the entry
            ctx2 = LocaleContext.create("en-US")

        # Both should reference the same cached object
        assert ctx1 is ctx2


class TestDateTimeFormattingEdgeCases:
    """Test datetime formatting edge cases."""

    def test_datetime_pattern_as_string(self) -> None:
        """Test datetime formatting when pattern is a string (line 384)."""
        ctx = LocaleContext.create("en-US")

        # Create a datetime with both date and time components
        dt = datetime(2023, 12, 25, 15, 30, 45, tzinfo=UTC)

        # Mock datetime_pattern to be a string instead of DateTimePattern object
        # This forces the code to use str.format() path at line 384
        with patch.object(
            ctx.babel_locale.datetime_formats,
            "get",
            return_value="{1} at {0}",  # String pattern, not DateTimePattern object
        ):
            result = ctx.format_datetime(
                dt,
                date_style="medium",
                time_style="short",
            )

            # Should format successfully using string.format()
            assert isinstance(result, str)
            # Result should contain both date and time parts
            assert "at" in result
