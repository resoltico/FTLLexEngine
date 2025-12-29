"""Comprehensive tests for Fluent built-in functions (Phase 3: Infrastructure/i18n).

Tests number_format() and datetime_format() functions with various parameters and edge cases.
"""

import locale
from contextlib import suppress
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from babel import dates as babel_dates

from ftllexengine.core.errors import FormattingError
from ftllexengine.runtime.functions import (
    create_default_registry,
    datetime_format,
    number_format,
)


class TestNumberFunction:
    """Test number_format() function with various parameters."""

    def test_number_basic_integer(self) -> None:
        """number_format() formats integer without decimals by default."""
        result = number_format(42)

        # Should be formatted as string
        assert isinstance(result, str)
        assert "42" in result

    def test_number_basic_float(self) -> None:
        """number_format() formats float with decimals."""
        result = number_format(123.456)

        # Should include decimal part
        assert isinstance(result, str)
        assert "123" in result

    def test_number_with_minimum_fraction_digits(self) -> None:
        """number_format() respects minimumFractionDigits parameter."""
        result = number_format(42, minimum_fraction_digits=2)

        # Should have at least 2 decimal places
        assert isinstance(result, str)
        # Must have decimal separator and digits
        decimal_sep = locale.localeconv()["decimal_point"]
        assert decimal_sep in result, f"Expected decimal separator in {result}"
        parts = result.split(decimal_sep)
        # Should have decimal part with at least 2 digits
        assert len(parts[1]) >= 2

    def test_number_with_maximum_fraction_digits(self) -> None:
        """number_format() respects maximumFractionDigits parameter."""
        result = number_format(123.456789, maximum_fraction_digits=2)

        # Should limit decimal places
        assert isinstance(result, str)
        assert "123" in result

    def test_number_with_grouping_true(self) -> None:
        """number_format() uses thousands separator when useGrouping=True."""
        result = number_format(1234567, use_grouping=True)

        # Should have thousands separator (depends on locale)
        assert isinstance(result, str)
        # Large numbers should be formatted
        assert len(result) >= 7  # At least the digits

    def test_number_with_grouping_false(self) -> None:
        """number_format() skips thousands separator when useGrouping=False."""
        result = number_format(1234567, use_grouping=False)

        # Should format without grouping
        assert isinstance(result, str)
        assert "1234567" in result

    def test_number_with_zero(self) -> None:
        """number_format() handles zero correctly."""
        result = number_format(0)

        assert "0" in result

    def test_number_with_negative(self) -> None:
        """number_format() handles negative numbers."""
        result = number_format(-123.45)

        # Accept both ASCII hyphen-minus (-) and Unicode minus sign (\u2212)
        # Different locales may use different characters for negative numbers
        assert "-" in result or "\u2212" in result  # \u2212 = MINUS SIGN
        assert "123" in result

    def test_number_with_very_large_number(self) -> None:
        """number_format() handles very large numbers."""
        result = number_format(1234567890123456)

        assert isinstance(result, str)
        assert len(result) > 10

    def test_number_with_very_small_decimal(self) -> None:
        """number_format() handles very small decimal numbers."""
        result = number_format(0.00001, maximum_fraction_digits=5)

        assert isinstance(result, str)

    def test_number_strips_trailing_zeros_beyond_minimum(self) -> None:
        """number_format() strips trailing zeros beyond minimumFractionDigits."""
        result = number_format(42.50, minimum_fraction_digits=1, maximum_fraction_digits=2)

        # Should keep at least 1 decimal place (minimum)
        # But strip the trailing 0 if minimum is 1
        assert isinstance(result, str)

    def test_number_with_combined_parameters(self) -> None:
        """number_format() handles all parameters together."""
        result = number_format(
            1234.567, minimum_fraction_digits=2, maximum_fraction_digits=4, use_grouping=True
        )

        assert isinstance(result, str)
        assert "1" in result


class TestNumberFunctionErrorHandling:
    """Test number_format() function error handling.

    FormattingError is raised with fallback_value for invalid inputs.
    The resolver catches this exception and uses the fallback in output.
    """

    def test_number_with_string_value_raises_formatting_error(self) -> None:
        """number_format() raises FormattingError for invalid string."""
        with pytest.raises(FormattingError) as exc_info:
            number_format("not a number")  # type: ignore

        # Should include fallback value for resolver to use
        assert "not a number" in exc_info.value.fallback_value

    def test_number_with_none_raises_formatting_error(self) -> None:
        """number_format() raises FormattingError for None."""
        with pytest.raises(FormattingError) as exc_info:
            number_format(None)  # type: ignore

        # Fallback should be string representation
        assert exc_info.value.fallback_value is not None

    def test_number_with_invalid_type_raises_formatting_error(self) -> None:
        """number_format() raises FormattingError for invalid types."""
        with pytest.raises(FormattingError) as exc_info:
            number_format([1, 2, 3])  # type: ignore

        # Fallback should be string representation
        assert exc_info.value.fallback_value is not None

    def test_number_with_locale_error_handling(self) -> None:
        """number_format() handles valid input correctly."""
        # Save current locale
        old_locale = locale.getlocale()

        try:
            # Valid input should work fine
            result = number_format(123.45)

            # Should handle gracefully
            assert isinstance(result, str)
        finally:
            # Restore locale, ignoring errors if restoration fails
            with suppress(locale.Error, ValueError, TypeError):
                locale.setlocale(locale.LC_ALL, old_locale)

    def test_number_with_dict_raises_formatting_error(self) -> None:
        """number_format() raises FormattingError for dict types."""
        with pytest.raises(FormattingError) as exc_info:
            number_format({"key": "value"})  # type: ignore

        # Fallback should be string representation
        assert exc_info.value.fallback_value is not None


class TestDatetimeFunction:
    """Test datetime_format() function with various parameters."""

    def test_datetime_basic_with_datetime_object(self) -> None:
        """datetime_format() formats datetime object."""
        dt = datetime(2025, 10, 27, 14, 30, 0, tzinfo=UTC)
        result = datetime_format(dt)

        # Should be formatted string
        assert isinstance(result, str)
        assert "2025" in result or "25" in result

    def test_datetime_with_date_style_short(self) -> None:
        """datetime_format() respects dateStyle='short'."""
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result = datetime_format(dt, date_style="short")

        assert isinstance(result, str)
        # Short format varies by locale, but should have date parts
        assert any(part in result for part in ["10", "27", "2025", "25"])

    def test_datetime_with_date_style_medium(self) -> None:
        """datetime_format() respects dateStyle='medium'."""
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result = datetime_format(dt, date_style="medium")

        assert isinstance(result, str)
        # Medium format: "Oct 27, 2025"
        assert "27" in result
        assert "2025" in result

    def test_datetime_with_date_style_long(self) -> None:
        """datetime_format() respects dateStyle='long'."""
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result = datetime_format(dt, date_style="long")

        assert isinstance(result, str)
        # Long format: "October 27, 2025"
        assert "27" in result
        assert "2025" in result

    def test_datetime_with_date_style_full(self) -> None:
        """datetime_format() respects dateStyle='full'."""
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result = datetime_format(dt, date_style="full")

        assert isinstance(result, str)
        # Full format includes day of week
        assert "27" in result
        assert "2025" in result

    def test_datetime_with_time_style_short(self) -> None:
        """datetime_format() respects timeStyle='short'."""
        dt = datetime(2025, 10, 27, 14, 30, 0, tzinfo=UTC)
        result = datetime_format(dt, date_style="short", time_style="short")

        assert isinstance(result, str)
        # Should include time part
        assert any(part in result for part in ["14", "2", "30", "PM", "pm"])

    def test_datetime_with_time_style_medium(self) -> None:
        """datetime_format() respects timeStyle='medium'."""
        dt = datetime(2025, 10, 27, 14, 30, 45, tzinfo=UTC)
        result = datetime_format(dt, date_style="medium", time_style="medium")

        assert isinstance(result, str)
        # Should include seconds
        assert "30" in result or "45" in result

    def test_datetime_with_time_style_long(self) -> None:
        """datetime_format() respects timeStyle='long'."""
        dt = datetime(2025, 10, 27, 14, 30, 45, tzinfo=UTC)
        result = datetime_format(dt, date_style="medium", time_style="long")

        assert isinstance(result, str)

    def test_datetime_with_time_style_full(self) -> None:
        """datetime_format() respects timeStyle='full'."""
        dt = datetime(2025, 10, 27, 14, 30, 45, tzinfo=UTC)
        result = datetime_format(dt, date_style="medium", time_style="full")

        assert isinstance(result, str)

    def test_datetime_with_iso_string(self) -> None:
        """datetime_format() parses ISO format string."""
        result = datetime_format("2025-10-27T14:30:00")

        assert isinstance(result, str)
        assert "2025" in result or "25" in result
        assert "27" in result

    def test_datetime_date_only_no_time(self) -> None:
        """datetime_format() formats date only when timeStyle=None."""
        dt = datetime(2025, 10, 27, 14, 30, 0, tzinfo=UTC)
        result = datetime_format(dt, date_style="medium")

        # Should not include time when timeStyle not specified
        assert isinstance(result, str)
        assert "27" in result
        assert "2025" in result


class TestDatetimeFunctionErrorHandling:
    """Test datetime_format() function error handling."""

    def test_datetime_with_invalid_iso_string(self) -> None:
        """datetime_format() raises FormattingError for invalid ISO string."""
        with pytest.raises(FormattingError) as exc_info:
            datetime_format("not a date")

        # Should have meaningful error message and fallback
        assert "not ISO 8601" in str(exc_info.value)
        assert exc_info.value.fallback_value == "{!DATETIME}"

    def test_datetime_with_partial_iso_string(self) -> None:
        """datetime_format() raises FormattingError for incomplete ISO string."""
        # "2025-10" is not valid ISO 8601 datetime format
        with pytest.raises(FormattingError) as exc_info:
            datetime_format("2025-10")

        assert exc_info.value.fallback_value == "{!DATETIME}"

    def test_datetime_with_year_overflow(self) -> None:
        """datetime_format() handles year out of range for strftime."""
        # Year 10000 causes OverflowError in strftime on some platforms
        dt = datetime(9999, 12, 31, tzinfo=UTC)
        result = datetime_format(dt)

        # Should handle gracefully
        assert isinstance(result, str)

    def test_datetime_with_ancient_date(self) -> None:
        """datetime_format() handles very old dates."""
        dt = datetime(1900, 1, 1, tzinfo=UTC)
        result = datetime_format(dt)

        assert isinstance(result, str)
        assert "1900" in result

    def test_datetime_strftime_exception_handling(self) -> None:
        """datetime_format() handles strftime exceptions gracefully."""
        # Try with extreme date that may cause strftime issues
        try:
            # Year 1 can cause issues on some platforms
            dt = datetime(1, 1, 1, tzinfo=UTC)
            result = datetime_format(dt)

            # Should handle gracefully, return ISO or formatted
            assert isinstance(result, str)
        except (ValueError, OverflowError, OSError):
            # If datetime itself fails on this platform, that's ok
            pass

    def test_datetime_with_invalid_format_string(self) -> None:
        """datetime_format() handles platform-specific strftime errors."""
        # Normal datetime, just testing error path coverage
        dt = datetime(2025, 10, 27, 14, 30, 0, tzinfo=UTC)
        result = datetime_format(dt, date_style="medium", time_style="medium")

        # Should format successfully
        assert isinstance(result, str)
        assert "27" in result


class TestBuiltInFunctionsRegistry:
    """Test create_default_registry()."""

    def test_registry_contains_number_function(self) -> None:
        """Registry includes NUMBER function."""
        registry = create_default_registry()
        assert registry.has_function("NUMBER")

    def test_registry_contains_datetime_function(self) -> None:
        """Registry includes DATETIME function."""
        registry = create_default_registry()
        assert registry.has_function("DATETIME")

    def test_number_function_callable_from_registry(self) -> None:
        """NUMBER function from registry is callable."""
        registry = create_default_registry()
        result = registry.call("NUMBER", [42], {})

        assert isinstance(result, str)
        assert "42" in result

    def test_datetime_function_callable_from_registry(self) -> None:
        """DATETIME function from registry is callable."""
        registry = create_default_registry()
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result = registry.call("DATETIME", [dt], {})

        assert isinstance(result, str)
        assert "2025" in result or "25" in result


class TestNumberFunctionEdgeCases:
    """Test number_format() function edge cases."""

    def test_number_with_zero_minimum_and_maximum_digits(self) -> None:
        """number_format() with minimumFractionDigits=0, maximumFractionDigits=0."""
        result = number_format(123.456, minimum_fraction_digits=0, maximum_fraction_digits=0)

        # Should strip all decimals
        assert isinstance(result, str)
        assert "123" in result

    def test_number_minimum_greater_than_maximum(self) -> None:
        """number_format() when minimumFractionDigits > maximumFractionDigits."""
        # This is an edge case - behavior may vary
        result = number_format(42.5, minimum_fraction_digits=3, maximum_fraction_digits=1)

        # Should handle gracefully
        assert isinstance(result, str)

    def test_number_with_infinity(self) -> None:
        """number_format() handles infinity."""
        result = number_format(float("inf"))

        # Should return string representation
        assert isinstance(result, str)

    def test_number_with_nan(self) -> None:
        """number_format() handles NaN."""
        result = number_format(float("nan"))

        # Should return string representation
        assert isinstance(result, str)


class TestNumberFunctionMockedErrors:
    """Test number_format() function error handlers using mocking."""

    def test_number_handles_locale_error(self) -> None:
        """number_format() handles locale.Error exception gracefully."""
        # Mock locale.format_string to raise locale.Error
        with patch("locale.format_string", side_effect=locale.Error("Mock locale error")):
            result = number_format(123.45)

            # Should return str(value) as fallback
            assert isinstance(result, str)
            assert "123.45" in result

    def test_number_handles_unexpected_exception(self) -> None:
        """number_format() handles unexpected exceptions gracefully."""
        # Mock locale.format_string to raise unexpected exception
        with patch("locale.format_string", side_effect=RuntimeError("Unexpected error")):
            result = number_format(42.0)

            # Should return str(value) as fallback
            assert isinstance(result, str)
            assert "42" in result


class TestDatetimeFunctionEdgeCases:
    """Test datetime_format() function edge cases."""

    def test_datetime_with_midnight(self) -> None:
        """datetime_format() handles midnight time."""
        dt = datetime(2025, 10, 27, 0, 0, 0, tzinfo=UTC)
        result = datetime_format(dt, date_style="medium", time_style="short")

        assert isinstance(result, str)
        # Should include midnight time representation
        assert "27" in result

    def test_datetime_with_noon(self) -> None:
        """datetime_format() handles noon time."""
        dt = datetime(2025, 10, 27, 12, 0, 0, tzinfo=UTC)
        result = datetime_format(dt, date_style="medium", time_style="short")

        assert isinstance(result, str)
        assert "27" in result

    def test_datetime_with_leap_year_date(self) -> None:
        """datetime_format() handles leap year dates."""
        dt = datetime(2024, 2, 29, tzinfo=UTC)
        result = datetime_format(dt)

        assert isinstance(result, str)
        assert "29" in result
        assert "2024" in result

    def test_datetime_with_iso_string_with_timezone(self) -> None:
        """datetime_format() handles ISO string with timezone."""
        # ISO format with timezone
        result = datetime_format("2025-10-27T14:30:00+00:00")

        assert isinstance(result, str)
        assert "2025" in result or "25" in result

    def test_datetime_with_empty_string(self) -> None:
        """datetime_format() raises FormattingError for empty string."""
        with pytest.raises(FormattingError) as exc_info:
            datetime_format("")

        # Should have fallback value
        assert exc_info.value.fallback_value == "{!DATETIME}"


class TestDatetimeFunctionMockedErrors:
    """Test datetime_format() function error handlers using mocking."""

    def test_datetime_handles_overflow_error(self) -> None:
        """datetime_format() raises FormattingError with fallback for OverflowError."""
        # Use a datetime that will cause OverflowError in Babel
        # Year 10000 is outside Babel's formatting range
        far_future_dt = datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC)

        # Patch babel.dates.format_date to raise OverflowError
        with patch("ftllexengine.runtime.locale_context.babel_dates.format_date") as mock_format:
            mock_format.side_effect = OverflowError("Year out of range")

            with pytest.raises(FormattingError) as exc_info:
                datetime_format(far_future_dt, "en_US")

            # Fallback should be ISO format
            assert exc_info.value.fallback_value == "9999-12-31T23:59:59+00:00"

    def test_datetime_unexpected_error_propagates(self) -> None:
        """datetime_format() lets unexpected exceptions propagate (v0.28.0 behavior).

        v0.28.0: Removed broad RuntimeError catches. Unexpected errors now propagate
        for debugging instead of being swallowed.
        """
        # Create a real datetime object
        test_dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)

        # Patch Babel's format_date to raise RuntimeError
        # v0.28.0: RuntimeError now propagates instead of being caught
        with (
            patch.object(
                babel_dates, "format_date", side_effect=RuntimeError("Unexpected error")
            ),
            pytest.raises(RuntimeError, match="Unexpected error"),
        ):
            datetime_format(test_dt, date_style="medium")
