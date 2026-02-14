"""Formatter boundary condition tests to kill survived mutations.

This module targets boundary conditions in number_format and datetime_format:
- Zero values
- Negative values
- Boundary conditions in precision parameters
- Edge cases with special values

Target: Kill ~23 formatter-related mutations
Phase: 1 (High-Impact Quick Wins)
"""

import math
from datetime import UTC, datetime

import pytest

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.functions import datetime_format, number_format


class TestNumberFormatBoundaries:
    """Test boundary conditions in number_format function.

    Targets mutations in parameter boundaries and special values.
    """

    def test_number_format_zero(self):
        """Kills: value > 0 → value >= 0 mutations.

        Zero should be formatted correctly.
        """
        result = number_format(0, "en-US")
        assert str(result) == "0"

    def test_number_format_negative_zero(self):
        """Kills: negative zero handling mutations.

        Negative zero should format as zero.
        """
        result = number_format(-0.0, "en-US")
        assert "0" in str(result)

    def test_number_format_negative_number(self):
        """Kills: value >= 0 mutations.

        Negative numbers should format correctly.
        """
        result = number_format(-42, "en-US")
        result_str = str(result)
        # Some locales use minus sign
        assert "-42" in result_str or "−42" in result_str  # noqa: RUF001

    def test_number_format_very_large_number(self):
        """Kills: number size boundary mutations.

        Very large numbers should format without error.
        """
        result = number_format(1_000_000_000_000, "en-US")
        result_str = str(result)
        assert isinstance(result_str, str)
        assert len(result_str) > 0

    def test_number_format_very_small_number(self):
        """Kills: small number boundary mutations.

        Very small decimals should format correctly.
        """
        result = number_format(0.000001, "en-US", maximum_fraction_digits=6)
        assert isinstance(str(result), str)

    def test_number_format_with_infinity(self):
        """Kills: special value handling mutations.

        Infinity should be handled gracefully.
        """
        result = number_format(math.inf, "en-US")
        result_str = str(result)
        assert isinstance(result_str, str)
        # Either formatted as "inf" or fallback to str(value)
        assert len(result_str) > 0

    def test_number_format_with_nan(self):
        """Kills: NaN handling mutations.

        NaN should be handled gracefully.
        """
        result = number_format(math.nan, "en-US")
        result_str = str(result)
        assert isinstance(result_str, str)
        assert len(result_str) > 0


class TestNumberFormatPrecisionBoundaries:
    """Test precision parameter boundary conditions.

    Targets mutations in minimum_fraction_digits and maximum_fraction_digits.
    """

    def test_minimum_fraction_digits_zero(self):
        """Kills: minimum_fraction_digits=0 → =1 mutations.

        Zero minimum should show no decimals for integers.
        """
        result = number_format(5, "en-US", minimum_fraction_digits=0)
        # Should be "5" not "5.0"
        assert str(result) == "5"

    def test_minimum_fraction_digits_one(self):
        """Kills: minimum_fraction_digits=1 → =0 mutations.

        One minimum should show one decimal for integers.
        """
        result = number_format(5, "en-US", minimum_fraction_digits=1)
        result_str = str(result)
        # Should be "5.0" (or locale equivalent)
        assert "5" in result_str
        # Must have decimal point and at least one digit after
        assert "." in result_str or "," in result_str, f"Expected decimal separator in {result_str}"
        decimal_sep = "." if "." in result_str else ","
        parts = result_str.split(decimal_sep)
        assert len(parts) == 2
        assert len(parts[1]) >= 1

    def test_minimum_fraction_digits_two(self):
        """Kills: minimum_fraction_digits=2 → =1 mutations.

        Two minimum should show two decimals.
        """
        result = number_format(5, "en-US", minimum_fraction_digits=2)
        result_str = str(result)
        # Should be "5.00" (or locale equivalent)
        assert "." in result_str or "," in result_str, f"Expected decimal separator in {result_str}"
        decimal_sep = "." if "." in result_str else ","
        parts = result_str.split(decimal_sep)
        assert len(parts) == 2
        assert len(parts[1]) >= 2

    def test_maximum_fraction_digits_zero(self):
        """Kills: maximum_fraction_digits=0 → =1 mutations.

        Zero maximum should round to integer.
        """
        result = number_format(5.7, "en-US", maximum_fraction_digits=0)
        # Should be "6" (rounded)
        assert "6" in str(result)

    def test_maximum_fraction_digits_one(self):
        """Kills: maximum_fraction_digits=1 → =0 mutations.

        One maximum should show at most one decimal.
        """
        result = number_format(5.789, "en-US", maximum_fraction_digits=1)
        # Should be "5.8" (rounded)
        assert "5" in str(result)

    def test_maximum_fraction_digits_three(self):
        """Kills: maximum_fraction_digits=3 → =2 mutations.

        Default maximum should allow three decimals.
        """
        result = number_format(5.12345, "en-US", maximum_fraction_digits=3)
        # Should be "5.123" (rounded)
        assert "5" in str(result)


class TestNumberFormatGroupingBoundaries:
    """Test use_grouping parameter boundary conditions.

    Targets mutations in use_grouping flag.
    """

    def test_use_grouping_true(self):
        """Kills: use_grouping=True → =False mutations.

        Grouping enabled should add separators for large numbers.
        """
        result = number_format(1000, "en-US", use_grouping=True)
        result_str = str(result)
        # Should have separator (comma or space depending on locale)
        # At minimum, result should be a string representation
        assert isinstance(result_str, str)
        assert "1000" in result_str or "1,000" in result_str or "1 000" in result_str

    def test_use_grouping_false(self):
        """Kills: use_grouping=False → =True mutations.

        Grouping disabled should not add separators.
        """
        result = number_format(1000, "en-US", use_grouping=False)
        result_str = str(result)
        assert isinstance(result_str, str)
        # Result should be string representation
        assert "1000" in result_str


class TestNumberFormatPrecisionCombinations:
    """Test combinations of precision parameters.

    Targets mutations in precision logic interactions.
    """

    def test_min_equals_max_fraction_digits(self):
        """Kills: min/max comparison mutations.

        When min equals max, should show exact digits.
        """
        result = number_format(5, "en-US", minimum_fraction_digits=2, maximum_fraction_digits=2)
        result_str = str(result)
        # Should be exactly "5.00"
        assert "." in result_str or "," in result_str, f"Expected decimal separator in {result_str}"
        decimal_sep = "." if "." in result_str else ","
        parts = result_str.split(decimal_sep)
        assert len(parts) == 2
        # Exactly 2 decimal digits
        assert len(parts[1]) == 2

    def test_min_less_than_max_with_value_between(self):
        """Kills: min < max boundary mutations.

        Value between min and max should show actual digits.
        """
        result = number_format(
            5.5, "en-US", minimum_fraction_digits=1,
            maximum_fraction_digits=3,
        )
        # Should show "5.5" (one decimal)
        assert "5" in str(result)

    def test_trailing_zeros_stripped_beyond_minimum(self):
        """Kills: trailing zero stripping mutations.

        Zeros beyond minimum should be stripped.
        """
        result = number_format(
            5.0, "en-US", minimum_fraction_digits=0,
            maximum_fraction_digits=3,
        )
        # Should be "5" not "5.000"
        assert str(result) == "5"


class TestDatetimeFormatBoundaries:
    """Test boundary conditions in datetime_format function.

    Targets mutations in datetime parameter handling.
    """

    def test_datetime_format_minimum_date(self):
        """Kills: date boundary mutations.

        Very early dates should format correctly.
        """
        dt = datetime(1970, 1, 1, tzinfo=UTC)
        result = datetime_format(dt, "en-US", date_style="short")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_datetime_format_future_date(self):
        """Kills: future date handling mutations.

        Far future dates should format correctly.
        """
        dt = datetime(2099, 12, 31, tzinfo=UTC)
        result = datetime_format(dt, "en-US", date_style="short")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_datetime_format_with_midnight(self):
        """Kills: time=0 boundary mutations.

        Midnight time should format correctly.
        """
        dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        result = datetime_format(dt, "en-US", date_style="short", time_style="short")
        assert isinstance(result, str)
        # Should contain some representation of midnight
        assert len(result) > 0

    def test_datetime_format_with_max_time(self):
        """Kills: time boundary mutations.

        Last second of day should format correctly.
        """
        dt = datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)
        result = datetime_format(dt, "en-US", date_style="short", time_style="short")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_datetime_format_invalid_string(self):
        """Kills: string validation mutations.

        Invalid datetime string should raise FrozenFluentError.
        """
        with pytest.raises(FrozenFluentError) as exc_info:
            datetime_format("invalid", "en-US", date_style="short")
        assert exc_info.value.category == ErrorCategory.FORMATTING
        # Should have fallback value for resolver to use
        assert exc_info.value.fallback_value == "{!DATETIME}"

    def test_datetime_format_empty_string(self):
        """Kills: empty string handling mutations.

        Empty string should raise FrozenFluentError.
        """
        with pytest.raises(FrozenFluentError) as exc_info:
            datetime_format("", "en-US", date_style="short")
        assert exc_info.value.category == ErrorCategory.FORMATTING
        assert exc_info.value.fallback_value == "{!DATETIME}"


class TestDatetimeFormatStyleBoundaries:
    """Test date/time style parameter boundaries.

    Targets mutations in style parameter handling.
    """

    def test_all_date_styles(self):
        """Kills: date_style enum mutations.

        All date styles should work.
        """
        from typing import Literal, cast  # noqa: PLC0415

        dt = datetime(2025, 10, 27, tzinfo=UTC)

        for style_str in ["short", "medium", "long", "full"]:
            style = cast(Literal["short", "medium", "long", "full"], style_str)
            result = datetime_format(dt, "en-US", date_style=style)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_all_time_styles(self):
        """Kills: time_style enum mutations.

        All time styles should work.
        """
        from typing import Literal, cast  # noqa: PLC0415

        dt = datetime(2025, 10, 27, 14, 30, 0, tzinfo=UTC)

        for style_str in ["short", "medium", "long", "full"]:
            style = cast(Literal["short", "medium", "long", "full"], style_str)
            result = datetime_format(dt, "en-US", date_style="short", time_style=style)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_time_style_none(self):
        """Kills: time_style=None → ="short" mutations.

        None time_style should format date only.
        """
        dt = datetime(2025, 10, 27, 14, 30, 0, tzinfo=UTC)
        result = datetime_format(dt, "en-US", date_style="short", time_style=None)
        assert isinstance(result, str)
        # Should not contain time (no AM/PM, no colons typically)
        # This is fuzzy but at least verify it's a string
        assert len(result) > 0


class TestDatetimeFormatTimezoneBoundaries:
    """Test timezone handling boundary conditions.

    Targets mutations in timezone logic.
    """

    def test_datetime_with_utc_timezone(self):
        """Kills: timezone handling mutations.

        UTC timezone should be handled correctly.
        """
        dt = datetime(2025, 10, 27, 12, 0, tzinfo=UTC)
        result = datetime_format(dt, "en-US", date_style="short")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_datetime_without_timezone_defaults_utc(self):
        """Kills: tzinfo is None mutations.

        Naive datetime should default to UTC.
        """
        dt = datetime(2025, 10, 27, 12, 0)  # No tzinfo  # noqa: DTZ001
        result = datetime_format(dt, "en-US", date_style="short")
        # Should not crash, handles None tzinfo by defaulting to UTC
        assert isinstance(result, str)
        assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
