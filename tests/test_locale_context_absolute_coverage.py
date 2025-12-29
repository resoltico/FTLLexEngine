"""Absolute final coverage tests for runtime/locale_context.py.

Targets remaining uncovered lines to achieve 100% coverage:
- Line 156: Double-check pattern cache hit in create()
- Lines 281-282: Fixed decimals formatting
- Line 384: String formatting for datetime_pattern
- Line 490->514: Branch for currency code display with pattern
- Line 506: Debug logging for currency pattern without placeholder

Python 3.13+.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from ftllexengine.runtime.locale_context import LocaleContext


class TestLocaleContextCacheInfo:
    """Test cache_info() method (lines 143-144)."""

    def test_cache_info_returns_dict(self) -> None:
        """Test cache_info() returns dictionary with expected keys."""
        # Clear cache first
        LocaleContext.clear_cache()

        # Populate cache with a few locales
        LocaleContext.create("en-US")
        LocaleContext.create("de-DE")

        # Get cache info - this covers lines 143-144
        info = LocaleContext.cache_info()

        # Verify structure
        assert isinstance(info, dict)
        assert "size" in info
        assert "max_size" in info
        assert "locales" in info

        # Verify values
        assert info["size"] == 2
        max_size = info["max_size"]
        assert isinstance(max_size, int)
        assert max_size > 0
        assert isinstance(info["locales"], tuple)
        assert "en_US" in info["locales"]
        assert "de_DE" in info["locales"]

    def test_cache_info_after_clear(self) -> None:
        """Test cache_info() returns empty after clearing."""
        LocaleContext.clear_cache()

        info = LocaleContext.cache_info()
        assert info["size"] == 0
        assert info["locales"] == ()


class TestLocaleContextCacheLine156:
    """Test cache identity and thread-safety patterns."""

    def test_cache_returns_same_instance(self) -> None:
        """Test that cache returns the same instance for same locale.

        This validates the cache hit path works correctly.
        """
        # Clear cache first
        LocaleContext.clear_cache()

        # Create a locale context to populate cache
        ctx1 = LocaleContext.create("en-US")

        # Create same locale again - should hit cache
        ctx2 = LocaleContext.create("en-US")

        # Both should be the same instance
        assert ctx1 is ctx2

        # Cache should have exactly one entry
        assert LocaleContext.cache_size() == 1


class TestFormatNumberFixedDecimalsLines281To282:
    """Test lines 281-282: fixed decimals formatting."""

    def test_format_number_fixed_decimals_two_places(self) -> None:
        """Test format_number with fixed 2 decimal places (lines 281-282)."""
        ctx = LocaleContext.create("en-US")

        # Format with minimum and maximum both set to 2 (fixed decimals)
        result = ctx.format_number(
            1234.5, minimum_fraction_digits=2, maximum_fraction_digits=2
        )

        # Should format with exactly 2 decimal places
        assert result == "1,234.50"

    def test_format_number_fixed_decimals_three_places(self) -> None:
        """Test format_number with fixed 3 decimal places."""
        ctx = LocaleContext.create("en-US")

        # Format with fixed 3 decimals
        result = ctx.format_number(
            123.4, minimum_fraction_digits=3, maximum_fraction_digits=3
        )

        # Should have exactly 3 decimal places
        assert result == "123.400"

    def test_format_number_fixed_decimals_zero(self) -> None:
        """Test format_number with fixed 0 decimals (integer formatting)."""
        ctx = LocaleContext.create("en-US")

        # Format with 0 decimals (should round)
        result = ctx.format_number(
            1234.567, minimum_fraction_digits=0, maximum_fraction_digits=0
        )

        # Should have no decimal point
        assert "." not in result
        assert result == "1,235"  # Rounded up


class TestFormatDatetimeLine384:
    """Test line 384: string formatting for datetime_pattern."""

    def test_format_datetime_with_string_pattern(self) -> None:
        """Test format_datetime when datetime_pattern is a string (line 384).

        Some locales return a plain string pattern instead of DateTimePattern object.
        """
        from datetime import UTC, datetime  # noqa: PLC0415

        ctx = LocaleContext.create("en-US")
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)

        # Format with both date and time styles to trigger datetime pattern logic
        # Mock the datetime_pattern to be a plain string
        with patch.object(ctx.babel_locale.datetime_formats, "get") as mock_get:
            # Return a plain string pattern instead of DateTimePattern object
            mock_get.return_value = "{1} at {0}"  # String without format() method

            result = ctx.format_datetime(dt, date_style="medium", time_style="short")

            # Should have formatted using string's .format() method (line 384)
            assert "at" in result  # Pattern had "at" separator


class TestFormatCurrencyCodeDisplayLines490To506:
    """Test lines 490-506: currency code display with pattern checks."""

    def test_format_currency_code_display_with_valid_pattern(self) -> None:
        """Test format_currency with code display and valid pattern (line 490->514)."""
        ctx = LocaleContext.create("en-US")

        # Format with currency_display="code"
        result = ctx.format_currency(123.45, currency="USD", currency_display="code")

        # Should use ISO code (USD) instead of symbol ($)
        assert "USD" in result

    def test_format_currency_code_display_fallback_path(self) -> None:
        """Test format_currency code display fallback paths (lines 490-509).

        Tests the branch where currency pattern validation occurs and
        potential fallback to standard formatting.
        """
        # Use a locale that should have standard currency formatting
        ctx = LocaleContext.create("en-US")

        # Test with valid currency code
        result = ctx.format_currency(123.45, currency="USD", currency_display="code")

        # Should format with USD code instead of $ symbol
        assert "USD" in result
        assert "123.45" in result

    def test_format_currency_symbol_display_standard(self) -> None:
        """Test format_currency with symbol display (default path)."""
        ctx = LocaleContext.create("en-US")

        # Test standard symbol display
        result = ctx.format_currency(123.45, currency="EUR", currency_display="symbol")

        # Should format with currency symbol
        assert "€" in result or "EUR" in result
        assert "123.45" in result


class TestCacheDoubleCheckPattern:
    """Test double-check pattern in cache (line 208)."""

    def test_cache_double_check_direct_simulation(self) -> None:
        """Test cache double-check pattern (line 208) by direct cache manipulation.

        Line 208 returns cached entry when it's found in the second check
        (inside lock) but wasn't in the first check (outside lock).

        We simulate this by:
        1. Make first check (line 185) return False by clearing cache
        2. Insert entry before second check by using side_effect on Locale.parse
        """
        from babel import Locale  # noqa: PLC0415

        from ftllexengine.locale_utils import normalize_locale  # noqa: PLC0415

        # Clear cache first
        LocaleContext.clear_cache()

        cache_key = normalize_locale("en-RACE-TEST")
        pre_inserted_ctx = LocaleContext(
            locale_code="en-RACE-TEST", _babel_locale=Locale.parse("en_US")
        )

        original_parse = Locale.parse

        def parse_with_insertion(code, *args, **kwargs):
            # Insert entry into cache DURING parse (between first check and lock acquisition)
            # This simulates another thread adding the entry
            with LocaleContext._cache_lock:
                if cache_key not in LocaleContext._cache:
                    LocaleContext._cache[cache_key] = pre_inserted_ctx
            return original_parse(code, *args, **kwargs)

        with patch.object(Locale, "parse", side_effect=parse_with_insertion):
            result = LocaleContext.create("en-RACE-TEST")

        # The double-check should find the pre-inserted context
        assert result is pre_inserted_ctx


class TestCurrencyPatternWithoutPlaceholder:
    """Test currency pattern missing placeholder (line 562) and fallback (546->570)."""

    def test_currency_code_display_with_invalid_pattern(self) -> None:
        """Test currency code display when pattern lacks placeholder (line 562).

        This tests the defensive code path where a currency pattern
        doesn't contain the expected currency placeholder character.
        """
        ctx = LocaleContext.create("en-US")

        # Create a mock pattern object without the currency placeholder
        class MockPattern:
            """Mock pattern without currency placeholder."""

            pattern = "#,##0.00"  # Missing U+00A4 placeholder

        # Mock the currency_formats to return our invalid pattern
        with (
            patch.object(
                ctx.babel_locale.currency_formats,
                "get",
                return_value=MockPattern(),
            ),
            patch(
                "ftllexengine.runtime.locale_context.logger"
            ) as mock_logger,
        ):
            # This should hit line 562 (debug logging for missing placeholder)
            # and fall through to default formatting
            result = ctx.format_currency(
                123.45, currency="USD", currency_display="code"
            )

            # Should still return a valid result (fallback path)
            assert isinstance(result, str)
            assert "123" in result

            # Verify debug logging was called (line 562)
            mock_logger.debug.assert_called()

    def test_currency_code_display_with_no_pattern_attribute(self) -> None:
        """Test currency code display when pattern lacks 'pattern' attribute (546->570).

        This tests the branch where standard_pattern exists but doesn't have
        a 'pattern' attribute, falling through to line 570 default format.
        """
        ctx = LocaleContext.create("en-US")

        # Create a mock that is truthy but lacks 'pattern' attribute
        class MockPatternWithoutAttr:
            """Mock pattern object without pattern attribute."""

        mock_obj = MockPatternWithoutAttr()
        assert not hasattr(mock_obj, "pattern")

        # Mock the currency_formats to return our pattern-less object
        with patch.object(
            ctx.babel_locale.currency_formats,
            "get",
            return_value=mock_obj,
        ):
            # This should skip the if block (line 546) and go to line 570
            result = ctx.format_currency(
                123.45, currency="USD", currency_display="code"
            )

            # Should still format using standard symbol display (fallback)
            assert isinstance(result, str)
            assert "123" in result

    def test_currency_code_display_with_none_pattern(self) -> None:
        """Test currency code display when standard pattern is None (546->570).

        This tests the branch where currency_formats.get returns None,
        falling through to line 570 default format.
        """
        ctx = LocaleContext.create("en-US")

        # Mock the currency_formats.get to return None
        with patch.object(
            ctx.babel_locale.currency_formats,
            "get",
            return_value=None,
        ):
            # This should skip the if block (line 546) and go to line 570
            result = ctx.format_currency(
                123.45, currency="USD", currency_display="code"
            )

            # Should still format using standard symbol display (fallback)
            assert isinstance(result, str)
            assert "123" in result


class TestDateTimeStringPatternBranch:
    """Test datetime pattern as string branch (line 440)."""

    def test_format_datetime_with_object_lacking_format_method(self) -> None:
        """Test format_datetime when datetime_formats returns object without format().

        Line 440 handles the case where the datetime_pattern object lacks
        a format() method. The code uses str(datetime_pattern).format() instead.

        We create a mock object that:
        1. Has no 'format' attribute (so hasattr returns False)
        2. Converts to a string with placeholders when str() is called
        """
        from datetime import UTC, datetime  # noqa: PLC0415

        ctx = LocaleContext.create("en-US")
        dt = datetime(2025, 7, 15, 10, 30, 0, tzinfo=UTC)

        # Create an object without format attribute that converts to pattern string
        class PatternWithoutFormat:
            """Mock pattern object without format() method."""

            def __str__(self) -> str:
                return "{1} @ {0}"

        # Verify our mock doesn't have format attribute
        mock_pattern = PatternWithoutFormat()
        assert not hasattr(mock_pattern, "format")

        # Mock datetime_formats.get to return our pattern object
        with patch.object(
            ctx.babel_locale.datetime_formats,
            "get",
            return_value=mock_pattern,
        ):
            result = ctx.format_datetime(dt, date_style="medium", time_style="short")

            # Should use str(pattern).format() path (line 440)
            assert " @ " in result  # Our pattern separator


class TestLocaleContextIntegration:
    """Integration tests combining multiple coverage scenarios."""

    def test_format_number_with_decimal_type(self) -> None:
        """Test format_number with Decimal type for fixed decimals."""
        ctx = LocaleContext.create("de-DE")

        # Use Decimal for precise fixed decimal formatting
        value = Decimal("1234.5")
        result = ctx.format_number(
            value, minimum_fraction_digits=2, maximum_fraction_digits=2
        )

        # Should format with German locale (comma decimal separator)
        assert "," in result
        assert result == "1.234,50"

    def test_clear_cache_and_recreate(self) -> None:
        """Test cache clearing and recreation."""
        # Clear cache
        LocaleContext.clear_cache()

        # Create locale
        ctx1 = LocaleContext.create("fr-FR")
        assert ctx1.locale_code == "fr-FR"

        # Create same locale again (should hit cache)
        ctx2 = LocaleContext.create("fr-FR")

        # Should be same instance (cached)
        assert ctx1 is ctx2

        # Clear cache again
        LocaleContext.clear_cache()

        # Create new instance
        ctx3 = LocaleContext.create("fr-FR")

        # Should be different instance (cache was cleared)
        assert ctx1 is not ctx3
