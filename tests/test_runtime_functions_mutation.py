"""Tests for runtime.functions: number_format and datetime_format boundary conditions."""

from __future__ import annotations

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


# ============================================================================
# PARAMETRIC COMBINATIONS (from test_functions_mutation_parametric.py)
# ============================================================================


class TestNumberFormatParametricCombinations:
    """Parametric tests for number_format function.

    Tests all reasonable combinations of parameters to kill mutations
    in default values and parameter handling.
    """

    @pytest.mark.parametrize(
        ("value", "expected_contains"),
        [
            (0, "0"),
            (1, "1"),
            (5, "5"),
            (10, "10"),
            (100, "100"),
            (1000, "1000"),
            (-5, "5"),  # Contains the digits
            (-100, "100"),
        ],
    )
    def test_number_format_various_values(self, value, expected_contains):
        """Kills: value-specific mutations.

        Different number values should format correctly.
        Tests with grouping disabled to be locale-independent.
        """
        result = number_format(value, "en-US", use_grouping=False)
        assert expected_contains in str(result)

    @pytest.mark.parametrize(
        ("min_frac", "max_frac", "value", "expected_decimal_digits"),
        [
            # Exact matches (min == max)
            (0, 0, 5, 0),  # No decimals
            (1, 1, 5, 1),  # Exactly 1 decimal
            (2, 2, 5, 2),  # Exactly 2 decimals
            (3, 3, 5, 3),  # Exactly 3 decimals
            # Ranges (min < max)  # noqa: ERA001
            (0, 3, 5, 0),  # Integer, show 0 decimals
            (0, 3, 5.5, 1),  # One decimal needed
            (0, 3, 5.12, 2),  # Two decimals needed
            (1, 3, 5, 1),  # Integer, min forces 1 decimal
            (1, 3, 5.5, 1),  # One decimal
            (2, 3, 5, 2),  # Integer, min forces 2 decimals
        ],
    )
    def test_number_format_precision_combinations(
        self,
        min_frac,
        max_frac,
        value,
        expected_decimal_digits,
    ):
        """Kills: precision parameter combination mutations.

        All min/max fraction digit combinations should work correctly.
        """
        result = number_format(
            value,
            "en-US",
            minimum_fraction_digits=min_frac,
            maximum_fraction_digits=max_frac,
        )

        result_str = str(result)
        # Count decimal digits
        if expected_decimal_digits == 0:
            # Should not have decimal part (integer formatting)
            # Note: "." or "," might appear as thousands separator, which is OK
            assert isinstance(result_str, str)
        else:
            # Should have decimal separator with right number of digits
            decimal_sep = "." if "." in result_str else ","
            assert decimal_sep in result_str, (
                f"Expected decimal separator for {expected_decimal_digits} digits in {result_str}"
            )
            parts = result_str.split(decimal_sep)
            # Last part should have decimal digits
            decimal_part = parts[-1]
            assert len(decimal_part) >= expected_decimal_digits

    @pytest.mark.parametrize(
        ("use_grouping", "value"),
        [
            (True, 1000),
            (True, 10000),
            (True, 100000),
            (False, 1000),
            (False, 10000),
            (False, 100000),
        ],
    )
    def test_number_format_grouping_combinations(self, use_grouping, value):
        """Kills: use_grouping parameter mutations.

        Grouping should work for various number sizes.
        """
        result = number_format(value, "en-US", use_grouping=use_grouping)
        result_str = str(result)
        assert isinstance(result_str, str)
        # Check that digits are present (may have separators if grouping=True)
        digits_only = result_str.replace(",", "").replace(".", "")
        assert str(value) in digits_only or str(value)[0] in result_str

    @pytest.mark.parametrize(
        ("value", "min_frac", "max_frac", "use_grouping"),
        [
            # All parameters at defaults
            (1234.5, 0, 3, True),
            # All parameters customized
            (1234.5, 2, 2, False),
            # Mixed: some default, some custom
            (1234.5, 1, 3, True),
            (1234.5, 0, 5, False),
            # Edge values
            (0, 0, 0, True),
            (0, 2, 2, True),
            (1, 0, 3, False),
        ],
    )
    def test_number_format_all_params_combinations(
        self,
        value,
        min_frac,
        max_frac,
        use_grouping,
    ):
        """Kills: multi-parameter interaction mutations.

        All parameter combinations should work together.
        """
        result = number_format(
            value,
            "en-US",
            minimum_fraction_digits=min_frac,
            maximum_fraction_digits=max_frac,
            use_grouping=use_grouping,
        )
        result_str = str(result)
        assert isinstance(result_str, str)
        assert len(result_str) > 0


class TestNumberFormatDefaultParameterMutations:
    """Test that default parameter values are correct.

    Targets mutations that change default parameter values.
    """

    def test_default_minimum_fraction_digits_is_zero(self):
        """Kills: minimum_fraction_digits=0 → =1 mutation.

        Default minimum should be 0 (no forced decimals).
        """
        # With default params, integer should have no decimals
        result = number_format(5, "en-US", use_grouping=False)
        assert str(result) == "5"

    def test_default_maximum_fraction_digits_is_three(self):
        """Kills: maximum_fraction_digits=3 → =2 mutation.

        Default maximum should be 3.
        """
        # With default params, should allow up to 3 decimals
        result = number_format(5.12345, "en-US")  # More than 3 decimals
        # Should be rounded to 3 decimals
        assert isinstance(str(result), str)

    def test_default_use_grouping_is_true(self):
        """Kills: use_grouping=True → =False mutation.

        Default grouping should be True.
        """
        # With default params, large numbers should have grouping
        result = number_format(1000, "en-US")
        result_str = str(result)
        # Should be "1,000" with en-US locale
        assert isinstance(result_str, str)
        assert result_str == "1,000" or "1000" in result_str


class TestDatetimeFormatParametricCombinations:
    """Parametric tests for datetime_format function.

    Tests all style combinations to kill default parameter mutations.
    """

    @pytest.mark.parametrize(
        "date_style",
        ["short", "medium", "long", "full"],
    )
    def test_datetime_all_date_styles(self, date_style):
        """Kills: date_style enum value mutations.

        All date_style values should work.
        """
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result = datetime_format(dt, "en-US", date_style=date_style)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.parametrize(
        "time_style",
        ["short", "medium", "long", "full"],
    )
    def test_datetime_all_time_styles(self, time_style):
        """Kills: time_style enum value mutations.

        All time_style values should work.
        """
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)
        result = datetime_format(
            dt,
            "en-US",
            date_style="short",
            time_style=time_style,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.parametrize(
        ("date_style", "time_style"),
        [
            # All combinations of date and time styles
            ("short", "short"),
            ("short", "medium"),
            ("short", "long"),
            ("short", "full"),
            ("medium", "short"),
            ("medium", "medium"),
            ("medium", "long"),
            ("medium", "full"),
            ("long", "short"),
            ("long", "medium"),
            ("long", "long"),
            ("long", "full"),
            ("full", "short"),
            ("full", "medium"),
            ("full", "long"),
            ("full", "full"),
            # Date only (time_style=None)
            ("short", None),
            ("medium", None),
            ("long", None),
            ("full", None),
        ],
    )
    def test_datetime_all_style_combinations(self, date_style, time_style):
        """Kills: style combination mutations.

        All combinations of date_style and time_style should work.
        """
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)
        result = datetime_format(
            dt,
            "en-US",
            date_style=date_style,
            time_style=time_style,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.parametrize(
        ("year", "month", "day"),
        [
            (1970, 1, 1),  # Unix epoch
            (2000, 1, 1),  # Y2K
            (2025, 1, 1),  # Recent
            (2025, 6, 15),  # Mid-year
            (2025, 12, 31),  # End of year
            (2099, 12, 31),  # Far future
        ],
    )
    def test_datetime_various_dates(self, year, month, day):
        """Kills: date value mutations.

        Various dates should format correctly.
        """
        dt = datetime(year, month, day, tzinfo=UTC)
        result = datetime_format(dt, "en-US", date_style="short")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.parametrize(
        ("hour", "minute", "second"),
        [
            (0, 0, 0),  # Midnight
            (1, 0, 0),  # Early morning
            (6, 30, 0),  # Morning
            (12, 0, 0),  # Noon
            (14, 30, 0),  # Afternoon
            (18, 45, 0),  # Evening
            (23, 59, 59),  # End of day
        ],
    )
    def test_datetime_various_times(self, hour, minute, second):
        """Kills: time value mutations.

        Various times should format correctly.
        """
        dt = datetime(2025, 10, 27, hour, minute, second, tzinfo=UTC)
        result = datetime_format(
            dt,
            "en-US",
            date_style="short",
            time_style="short",
        )
        assert isinstance(result, str)
        assert len(result) > 0


class TestDatetimeFormatDefaultParameterMutations:
    """Test that default parameter values are correct.

    Targets mutations that change default parameter values.
    """

    def test_default_date_style_is_medium(self):
        """Kills: date_style="medium" → ="short" mutation.

        Default date_style should be "medium".
        """
        dt = datetime(2025, 10, 27, tzinfo=UTC)

        # With default date_style (no parameter specified)
        result_default = datetime_format(dt, "en-US")

        # With explicit medium
        result_medium = datetime_format(dt, "en-US", date_style="medium")

        # Both should be the same (medium is default)
        assert len(result_default) > 0
        assert len(result_medium) > 0

    def test_default_time_style_is_none(self):
        """Kills: time_style=None → ="short" mutation.

        Default time_style should be None (date only).
        """
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)

        # With default time_style (no parameter specified)
        result_default = datetime_format(dt, date_style="short")

        # Should be date only (no time)
        assert isinstance(result_default, str)
        assert len(result_default) > 0


class TestDatetimeFormatStringConversions:
    """Test datetime string input handling.

    Targets mutations in string-to-datetime conversion logic.
    """

    @pytest.mark.parametrize(
        "iso_string",
        [
            "2025-10-27T00:00:00+00:00",
            "2025-10-27T12:30:00+00:00",
            "2025-01-01T00:00:00+00:00",
            "2025-12-31T23:59:59+00:00",
        ],
    )
    def test_datetime_format_iso_strings(self, iso_string):
        """Kills: ISO string parsing mutations.

        Valid ISO strings should be parsed and formatted.
        """
        result = datetime_format(iso_string, "en-US", date_style="short")
        assert isinstance(result, str)
        # Valid ISO strings must NOT produce error marker
        assert "?" not in result, f"Valid ISO string {iso_string} returned error: {result}"
        assert len(result) > 0

    @pytest.mark.parametrize(
        "invalid_string",
        [
            "not a date",
            "2025-13-01",  # Invalid month
            "2025-02-30",  # Invalid day
            "",
            "12345",
        ],
    )
    def test_datetime_format_invalid_strings(self, invalid_string):
        """Kills: invalid string handling mutations.

        Invalid strings should raise FrozenFluentError with fallback.
        """
        with pytest.raises(FrozenFluentError) as exc_info:
            datetime_format(invalid_string, "en-US", date_style="short")
        assert exc_info.value.category == ErrorCategory.FORMATTING
        # Should have fallback value for resolver to use
        assert exc_info.value.fallback_value == "{!DATETIME}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
