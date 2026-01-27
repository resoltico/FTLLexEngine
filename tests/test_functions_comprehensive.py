"""Comprehensive property-based tests for runtime.functions module.

Tests formatting behavior for NUMBER, DATETIME, and CURRENCY functions.
LocaleContext.create() always succeeds with en_US fallback.
"""

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.runtime.function_bridge import FluentNumber
from ftllexengine.runtime.functions import (
    _compute_visible_precision,
    create_default_registry,
    currency_format,
    datetime_format,
    number_format,
)


class TestNumberFormatBehavior:
    """Tests for number_format formatting behavior."""

    def test_number_format_with_invalid_locale_uses_fallback(self) -> None:
        """Verify number_format with invalid locale uses en_US fallback."""
        # Invalid locale should still format successfully using en_US fallback
        result = number_format(1234.5, "invalid-locale")
        # Should contain the number (formatted with en_US rules)
        assert "1" in str(result)
        assert "234" in str(result)

    @given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e10, max_value=1e10))
    def test_number_format_always_returns_fluent_number(self, value: float) -> None:
        """Property: number_format always returns a FluentNumber for any finite float."""
        result = number_format(value, "en-US")
        assert isinstance(result, FluentNumber)

    def test_number_format_invalid_locale_with_pattern(self) -> None:
        """Verify invalid locale with pattern still formats successfully."""
        result = number_format(
            42.0,
            "xx-INVALID",
            pattern="#,##0.00",
            minimum_fraction_digits=2,
        )
        # Should return FluentNumber using en_US fallback
        assert isinstance(result, FluentNumber)
        assert "42" in str(result)

    def test_number_format_success_case_basic(self) -> None:
        """Verify number_format works correctly in success case."""
        result = number_format(1234.5, "en-US", minimum_fraction_digits=2)
        # Should format with locale-specific formatting
        assert "1" in str(result)
        assert "234" in str(result)

    def test_number_format_success_with_grouping(self) -> None:
        """Verify number_format with grouping enabled."""
        result = number_format(1000000, "en-US", use_grouping=True)
        # Should have thousands separators
        assert "," in str(result) or " " in str(result)


class TestDatetimeFormatBehavior:
    """Tests for datetime_format formatting behavior."""

    def test_datetime_format_with_invalid_locale_datetime_input(self) -> None:
        """Verify datetime_format with invalid locale formats datetime."""
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)
        # Invalid locale should still format successfully using en_US fallback
        result = datetime_format(dt, "invalid-locale")
        # Should contain formatted date (using en_US rules)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_datetime_format_with_invalid_locale_string_input(self) -> None:
        """Verify datetime_format with invalid locale handles string input."""
        dt_string = "2025-10-27T14:30:00+00:00"
        # Invalid locale should still format successfully using en_US fallback
        result = datetime_format(dt_string, "bad-locale")
        assert isinstance(result, str)

    @given(st.datetimes(timezones=st.just(UTC)))
    def test_datetime_format_always_returns_string(self, dt: datetime) -> None:
        """Property: datetime_format always returns a string for datetime inputs."""
        result = datetime_format(dt, "en-US")
        assert isinstance(result, str)

    def test_datetime_format_invalid_locale_with_pattern(self) -> None:
        """Verify invalid locale with pattern still formats successfully."""
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result = datetime_format(dt, "invalid", pattern="yyyy-MM-dd")
        # Should return formatted string using en_US fallback
        assert isinstance(result, str)
        assert len(result) > 0

    def test_datetime_format_success_case_basic(self) -> None:
        """Verify datetime_format works correctly in success case."""
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result = datetime_format(dt, "en-US", date_style="short")
        # Should format with locale-specific formatting
        assert "10" in result
        assert "27" in result

    def test_datetime_format_success_with_time_style(self) -> None:
        """Verify datetime_format with both date and time styles."""
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)
        result = datetime_format(dt, "en-US", date_style="medium", time_style="short")
        # Should include both date and time
        assert len(result) > 0


class TestCurrencyFormatBehavior:
    """Tests for currency_format formatting behavior."""

    def test_currency_format_with_invalid_locale(self) -> None:
        """Verify currency_format with invalid locale uses fallback."""
        # Invalid locale should still format successfully using en_US fallback
        result = currency_format(123.45, "invalid-locale", currency="EUR")
        # Should contain currency info (formatted with en_US rules)
        assert isinstance(result, FluentNumber)
        assert "123" in result or "EUR" in result

    @given(
        st.floats(allow_nan=False, allow_infinity=False, min_value=0, max_value=1e10),
        st.sampled_from(["USD", "EUR", "GBP", "JPY", "CHF"]),
    )
    def test_currency_format_always_returns_fluent_number(
        self, value: float, currency: str,
    ) -> None:
        """Property: currency_format always returns a FluentNumber."""
        result = currency_format(value, "en-US", currency=currency)
        assert isinstance(result, FluentNumber)

    def test_currency_format_invalid_locale_with_display_style(self) -> None:
        """Verify invalid locale with display style still formats successfully."""
        result = currency_format(
            100.0,
            "xx-INVALID",
            currency="EUR",
            currency_display="name",
        )
        # Should return FluentNumber using en_US fallback
        assert isinstance(result, FluentNumber)
        assert "100" in result or "EUR" in result or "euro" in str(result).lower()

    def test_currency_format_success_case_basic(self) -> None:
        """Verify currency_format works correctly in success case."""
        result = currency_format(123.45, "en-US", currency="USD")
        # Should format with currency symbol or code
        assert "123" in result

    def test_currency_format_success_with_symbol_display(self) -> None:
        """Verify currency_format with symbol display."""
        result = currency_format(100, "en-US", currency="EUR", currency_display="symbol")
        # Should include currency representation
        assert len(result) > 0


class TestFunctionRegistryIntegration:
    """Tests for create_default_registry() integration."""

    def test_function_registry_contains_number(self) -> None:
        """Verify default registry contains NUMBER function."""
        registry = create_default_registry()
        assert "NUMBER" in registry
        assert registry.has_function("NUMBER")

    def test_function_registry_contains_datetime(self) -> None:
        """Verify default registry contains DATETIME function."""
        registry = create_default_registry()
        assert "DATETIME" in registry
        assert registry.has_function("DATETIME")

    def test_function_registry_contains_currency(self) -> None:
        """Verify default registry contains CURRENCY function."""
        registry = create_default_registry()
        assert "CURRENCY" in registry
        assert registry.has_function("CURRENCY")

    def test_function_registry_count(self) -> None:
        """Verify default registry has exactly 3 built-in functions."""
        registry = create_default_registry()
        assert len(registry) == 3

    def test_function_registry_list_functions(self) -> None:
        """Verify registry.list_functions returns all built-ins."""
        registry = create_default_registry()
        functions = registry.list_functions()
        assert "NUMBER" in functions
        assert "DATETIME" in functions
        assert "CURRENCY" in functions

    def test_number_function_signature_in_registry(self) -> None:
        """Verify NUMBER function has correct signature in registry."""
        registry = create_default_registry()
        sig = registry.get_function_info("NUMBER")
        assert sig is not None
        assert sig.python_name == "number_format"
        assert sig.ftl_name == "NUMBER"
        # Should have camelCase parameter mappings (convert tuple to dict for lookup)
        param_dict = dict(sig.param_mapping)
        assert "minimumFractionDigits" in param_dict
        assert "maximumFractionDigits" in param_dict
        assert "useGrouping" in param_dict

    def test_datetime_function_signature_in_registry(self) -> None:
        """Verify DATETIME function has correct signature in registry."""
        registry = create_default_registry()
        sig = registry.get_function_info("DATETIME")
        assert sig is not None
        assert sig.python_name == "datetime_format"
        assert sig.ftl_name == "DATETIME"
        # Should have camelCase parameter mappings (convert tuple to dict for lookup)
        param_dict = dict(sig.param_mapping)
        assert "dateStyle" in param_dict
        assert "timeStyle" in param_dict

    def test_currency_function_signature_in_registry(self) -> None:
        """Verify CURRENCY function has correct signature in registry."""
        registry = create_default_registry()
        sig = registry.get_function_info("CURRENCY")
        assert sig is not None
        assert sig.python_name == "currency_format"
        assert sig.ftl_name == "CURRENCY"
        # Should have camelCase parameter mappings (convert tuple to dict for lookup)
        param_dict = dict(sig.param_mapping)
        assert "currencyDisplay" in param_dict


class TestComputeVisiblePrecision:
    """Tests for _compute_visible_precision helper function."""

    def test_precision_with_decimal_point(self) -> None:
        """Verify precision counts digits after decimal point."""
        assert _compute_visible_precision("1,234.56", ".") == 2
        assert _compute_visible_precision("1.5", ".") == 1
        assert _compute_visible_precision("1.000", ".") == 3

    def test_precision_with_comma_decimal(self) -> None:
        """Verify precision with comma as decimal separator (European locales)."""
        assert _compute_visible_precision("1.234,56", ",") == 2
        assert _compute_visible_precision("1,5", ",") == 1
        assert _compute_visible_precision("1,000", ",") == 3

    def test_precision_no_decimal(self) -> None:
        """Verify precision is 0 when no decimal separator present."""
        assert _compute_visible_precision("1,234", ".") == 0
        assert _compute_visible_precision("1234", ".") == 0
        assert _compute_visible_precision("1.234", ",") == 0  # Period is thousands sep

    def test_precision_with_trailing_non_digits(self) -> None:
        """Verify precision ignores trailing non-digit characters."""
        # Currency symbols after number
        assert _compute_visible_precision("1,234.56 EUR", ".") == 2
        # Parentheses (accounting format)
        assert _compute_visible_precision("(1,234.56)", ".") == 2

    def test_precision_empty_fraction(self) -> None:
        """Verify precision handles edge cases."""
        # Decimal separator with no following digits should return 0
        assert _compute_visible_precision("1.", ".") == 0


class TestNumberFormatPrecisionCalculation:
    """Tests for NUMBER() precision calculation from formatted string.

    Verifies that FluentNumber.precision reflects the ACTUAL visible fraction
    digit count in the formatted output, not the minimum_fraction_digits parameter.
    This is critical for CLDR plural rule matching (v operand).
    """

    def test_precision_from_formatted_string_not_minimum(self) -> None:
        """Precision reflects actual formatted output, not minimum parameter."""
        # Input: 1.2 with min=0, max=3
        # Formatted: "1.2" (1 visible fraction digit)
        # Precision should be 1, not 0 (the minimum)
        result = number_format(1.2, "en-US", minimum_fraction_digits=0, maximum_fraction_digits=3)
        assert result.precision == 1
        assert str(result) == "1.2"

    def test_precision_with_trailing_zeros(self) -> None:
        """Precision includes trailing zeros when minimum forces them."""
        # Input: 1 with min=2, max=2
        # Formatted: "1.00" (2 visible fraction digits)
        result = number_format(1, "en-US", minimum_fraction_digits=2, maximum_fraction_digits=2)
        assert result.precision == 2
        assert "1.00" in str(result)

    def test_precision_integer_format(self) -> None:
        """Precision is 0 when formatting as integer."""
        # Input: 1.5 with max=0
        # Formatted: "2" (rounded, no fraction digits)
        result = number_format(1.5, "en-US", minimum_fraction_digits=0, maximum_fraction_digits=0)
        assert result.precision == 0
        assert str(result) == "2"

    def test_precision_with_decimal_locale(self) -> None:
        """Precision calculated correctly with comma decimal separator."""
        # German uses comma as decimal separator: 1.234,50
        result = number_format(
            1234.5, "de-DE", minimum_fraction_digits=2, maximum_fraction_digits=2
        )
        assert result.precision == 2
        # Should be formatted with comma decimal
        assert "," in str(result)

    def test_precision_variable_length_decimals(self) -> None:
        """Precision reflects actual digits when between min and max."""
        # Input: 1.23 with min=0, max=5
        # Formatted: "1.23" (2 visible fraction digits)
        result = number_format(1.23, "en-US", minimum_fraction_digits=0, maximum_fraction_digits=5)
        assert result.precision == 2
        assert str(result) == "1.23"

    def test_precision_with_decimal_type(self) -> None:
        """Precision works correctly with Decimal input."""
        value = Decimal("1.23456")
        result = number_format(value, "en-US", minimum_fraction_digits=0, maximum_fraction_digits=3)
        # Should be rounded to 3 decimals: "1.235"
        assert result.precision == 3
        assert "1.235" in str(result)

    def test_precision_whole_number_with_decimal_input(self) -> None:
        """Precision is 0 for whole numbers without minimum fraction digits."""
        # Input: 100.0 with min=0, max=3
        # Formatted: "100" (no trailing .0)
        result = number_format(100.0, "en-US", minimum_fraction_digits=0, maximum_fraction_digits=3)
        assert result.precision == 0
        assert str(result) == "100"

    @given(
        st.decimals(
            min_value=Decimal("-1e6"),
            max_value=Decimal("1e6"),
            allow_nan=False,
            allow_infinity=False,
            places=6,
        ),
        st.integers(min_value=0, max_value=6),
        st.integers(min_value=0, max_value=6),
    )
    def test_precision_always_matches_formatted_output(
        self, value: Decimal, min_frac: int, max_frac: int
    ) -> None:
        """Property: precision always equals actual fraction digit count in output."""
        # Ensure min <= max
        if min_frac > max_frac:
            min_frac, max_frac = max_frac, min_frac

        result = number_format(
            value,
            "en-US",
            minimum_fraction_digits=min_frac,
            maximum_fraction_digits=max_frac,
        )

        # Count actual digits after decimal in formatted string
        formatted_str = str(result)
        if "." in formatted_str:
            _, fraction = formatted_str.rsplit(".", 1)
            actual_digits = sum(1 for c in fraction if c.isdigit())
        else:
            actual_digits = 0

        # Precision must match actual visible digits
        assert result.precision == actual_digits
