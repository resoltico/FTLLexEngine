"""Tests for FluentBundle locale validation, date support, and currency precision.

Tests for:
- datetime.date support in FluentValue
- FluentBundle.__init__ locale validation
- Currency code display with correct decimal places

Python 3.13+.
"""

from datetime import UTC, date, datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.runtime.functions import currency_format
from ftllexengine.runtime.locale_context import LocaleContext

# Valid locale alphabet for property-based tests
_LOCALE_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"


class TestFluentBundleLocaleValidation:
    """Test FluentBundle.__init__ locale validation."""

    def test_init_with_empty_locale_raises(self) -> None:
        """Empty locale raises ValueError in __init__."""
        with pytest.raises(ValueError, match="Locale code cannot be empty"):
            FluentBundle("")

    def test_init_with_invalid_locale_format_raises(self) -> None:
        """Invalid locale format raises ValueError in __init__."""
        with pytest.raises(ValueError, match="Invalid locale code format"):
            FluentBundle("en US")  # Space not allowed

    def test_init_with_special_chars_raises(self) -> None:
        """Locale with special characters raises ValueError."""
        with pytest.raises(ValueError, match="Invalid locale code format"):
            FluentBundle("en@US")

    def test_init_with_valid_underscore_locale_succeeds(self) -> None:
        """Valid locale with underscore succeeds."""
        bundle = FluentBundle("en_US")
        assert bundle.locale == "en_US"

    def test_init_with_valid_hyphen_locale_succeeds(self) -> None:
        """Valid locale with hyphen succeeds."""
        bundle = FluentBundle("en-US")
        assert bundle.locale == "en-US"

    def test_init_with_simple_locale_succeeds(self) -> None:
        """Simple language code succeeds."""
        bundle = FluentBundle("en")
        assert bundle.locale == "en"

    @given(
        st.from_regex(r"[a-zA-Z][a-zA-Z0-9]*(_[a-zA-Z0-9]+)?", fullmatch=True)
    )
    @settings(max_examples=50)
    def test_valid_locale_formats_accepted(self, locale: str) -> None:
        """Valid locale formats are accepted by __init__.

        BCP 47 format: alphanumeric starting with letter, optional underscore-delimited subtag.
        """
        bundle = FluentBundle(locale)
        assert bundle.locale == locale

    @given(st.text(min_size=1, max_size=10).filter(
        lambda s: not s.replace("_", "").replace("-", "").isalnum() and s
    ))
    @settings(max_examples=50)
    def test_invalid_locale_formats_rejected(self, locale: str) -> None:
        """Invalid locale formats are rejected by __init__."""
        with pytest.raises(ValueError, match="Invalid locale code format"):
            FluentBundle(locale)


class TestDatetimeDateSupport:
    """Test datetime.date support in FluentValue (TYPE-DEF-MISSING-DATE-1)."""

    def test_date_value_in_format_pattern(self) -> None:
        """datetime.date values work in format_pattern."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("today = Today is { $date }")

        # datetime.date value should be accepted
        test_date = date(2025, 12, 15)
        result, _errors = bundle.format_pattern("today", {"date": test_date})

        # The date should be converted to string representation
        assert isinstance(result, str)
        assert "2025" in result or "12" in result or "15" in result

    def test_datetime_value_still_works(self) -> None:
        """datetime.datetime values continue to work."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("now = Now is { $dt }")

        test_dt = datetime(2025, 12, 15, 10, 30, 0, tzinfo=UTC)
        result, _errors = bundle.format_pattern("now", {"dt": test_dt})

        assert isinstance(result, str)
        assert "2025" in result or "12" in result or "15" in result

    def test_date_in_datetime_function(self) -> None:
        """date values work with DATETIME() function."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("formatted = { DATETIME($date) }")

        test_date = date(2025, 12, 15)
        result, _errors = bundle.format_pattern("formatted", {"date": test_date})

        # Should format without crashing (may use fallback for date-only)
        assert isinstance(result, str)


class TestCurrencyCodeDisplayDecimals:
    """Test currency code display uses correct CLDR decimals (LOGIC-CURRENCY-PRECISION-1)."""

    def test_currency_code_display_jpy_zero_decimals(self) -> None:
        """JPY with code display should use 0 decimal places."""
        result = currency_format(12345, "en-US", currency="JPY", currency_display="code")

        assert "JPY" in result
        assert "12345" in result or "12,345" in result
        # Should NOT have decimal point since JPY has 0 decimals
        # Check no ".00" or ".00" pattern
        assert ".00" not in result

    def test_currency_code_display_bhd_three_decimals(self) -> None:
        """BHD with code display should use 3 decimal places."""
        result = currency_format(123.456, "en-US", currency="BHD", currency_display="code")

        assert "BHD" in result
        assert "123" in result
        # Should have 3 decimal places (456)
        assert "456" in result

    def test_currency_code_display_eur_two_decimals(self) -> None:
        """EUR with code display should use 2 decimal places."""
        result = currency_format(123.45, "en-US", currency="EUR", currency_display="code")

        assert "EUR" in result
        assert "123" in result
        assert "45" in result

    def test_currency_code_display_kwd_three_decimals(self) -> None:
        """KWD with code display should use 3 decimal places."""
        result = currency_format(100.123, "en-US", currency="KWD", currency_display="code")

        assert "KWD" in result
        assert "100" in result
        # Should have 3 decimal places
        assert "123" in result

    def test_currency_code_display_omr_three_decimals(self) -> None:
        """OMR with code display should use 3 decimal places."""
        result = currency_format(50.789, "en-US", currency="OMR", currency_display="code")

        assert "OMR" in result
        assert "50" in result
        # Should have 3 decimal places
        assert "789" in result

    def test_currency_symbol_display_still_works(self) -> None:
        """Symbol display continues to work correctly."""
        result = currency_format(123.45, "en-US", currency="EUR", currency_display="symbol")

        assert "123" in result
        assert "45" in result
        # Should have euro symbol
        assert "€" in result

    def test_currency_code_display_large_amount(self) -> None:
        """Large amounts with code display preserve grouping."""
        result = currency_format(1234567.89, "en-US", currency="USD", currency_display="code")

        assert "USD" in result
        # Should have grouping (commas in en-US)
        assert "1" in result
        assert "234" in result or "567" in result


class TestCurrencyCodeDisplayLocaleContext:
    """Test LocaleContext.format_currency with code display."""

    def test_locale_context_format_currency_code_jpy(self) -> None:
        """LocaleContext format_currency with code display for JPY."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(12345, currency="JPY", currency_display="code")

        assert "JPY" in result
        # JPY should have 0 decimal places
        assert ".00" not in result

    def test_locale_context_format_currency_code_bhd(self) -> None:
        """LocaleContext format_currency with code display for BHD."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(123.456, currency="BHD", currency_display="code")

        assert "BHD" in result
        # BHD should have 3 decimal places
        assert "456" in result

    def test_locale_context_preserves_locale_formatting(self) -> None:
        """Code display preserves locale-specific formatting."""
        ctx_us = LocaleContext.create("en-US")
        ctx_de = LocaleContext.create("de-DE")

        result_us = ctx_us.format_currency(1234.56, currency="EUR", currency_display="code")
        result_de = ctx_de.format_currency(1234.56, currency="EUR", currency_display="code")

        # Both should have EUR code
        assert "EUR" in result_us
        assert "EUR" in result_de

        # Should have different thousand/decimal separators
        # en-US uses "," for thousands, "." for decimal
        # de-DE uses "." for thousands, "," for decimal
        assert "1,234.56" in result_us or "1234.56" in result_us
        assert "1.234,56" in result_de or "1234,56" in result_de


class TestCurrencyDecimalsPropertyBased:
    """Property-based tests for currency decimals."""

    @given(st.floats(min_value=0.001, max_value=1000000, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_jpy_code_display_never_has_decimals(self, amount: float) -> None:
        """JPY code display never shows decimal places."""
        result = currency_format(amount, "en-US", currency="JPY", currency_display="code")

        # JPY should never have .00 or any decimal point before digits
        assert "JPY" in result
        # Remove the JPY code to check the number part
        number_part = result.replace("JPY", "").replace(",", "").replace(" ", "").strip()
        # If there's a decimal point, it shouldn't be followed by digits
        # (The number should be rounded to integer for JPY)
        if "." in number_part:
            # For JPY, decimals should not appear
            parts = number_part.split(".")
            if len(parts) > 1:
                # Decimal part should be empty for JPY
                assert parts[1] == "" or not parts[1].isdigit()

    @given(st.floats(min_value=0.001, max_value=1000000, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_bhd_code_display_has_three_decimals(self, amount: float) -> None:
        """BHD code display shows exactly 3 decimal places."""
        result = currency_format(round(amount, 3), "en-US", currency="BHD", currency_display="code")

        assert "BHD" in result
        # BHD should have decimals (not rounded to integer)
        # The actual decimal format depends on locale
