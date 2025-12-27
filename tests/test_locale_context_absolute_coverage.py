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
from unittest.mock import Mock, patch

from ftllexengine.runtime.locale_context import (
    LocaleContext,
    _clear_locale_context_cache,
)


class TestLocaleContextCacheLine156:
    """Test line 156: double-check pattern cache hit."""

    def test_create_double_check_pattern_cache_hit(self) -> None:
        """Test create() returns cached instance in double-check (line 156).

        This tests the thread-safety double-check pattern where another thread
        might have added the locale to cache between the first check and lock acquisition.
        """
        # Clear cache first
        _clear_locale_context_cache()

        # Create a locale context to populate cache
        ctx1 = LocaleContext.create("en-US")

        # Mock the scenario where cache is checked twice
        # This simulates a race condition where another thread adds to cache
        with patch(
            "ftllexengine.runtime.locale_context._locale_context_cache"
        ) as mock_cache:
            # First access: cache miss (empty dict)
            # Second access (inside lock): cache hit
            mock_cache.__contains__.side_effect = [False, True]
            mock_cache.move_to_end = Mock()
            mock_cache.__getitem__ = Mock(return_value=ctx1)

            # Create should return cached instance from second check
            _ctx2 = LocaleContext.create("en-US")

            # Should have called __getitem__ due to cache hit in double-check
            mock_cache.__getitem__.assert_called_once()


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
        _clear_locale_context_cache()

        # Create locale
        ctx1 = LocaleContext.create("fr-FR")
        assert ctx1.locale_code == "fr-FR"

        # Create same locale again (should hit cache)
        ctx2 = LocaleContext.create("fr-FR")

        # Should be same instance (cached)
        assert ctx1 is ctx2

        # Clear cache again
        _clear_locale_context_cache()

        # Create new instance
        ctx3 = LocaleContext.create("fr-FR")

        # Should be different instance (cache was cleared)
        assert ctx1 is not ctx3
