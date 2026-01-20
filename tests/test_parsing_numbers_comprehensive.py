"""Comprehensive property-based tests for parsing.numbers module.

Tests locale-aware number parsing (float and Decimal) with error handling.

"""

from decimal import Decimal

from hypothesis import assume, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.parsing.numbers import parse_decimal, parse_number


class TestParseNumberProperties:
    """Property-based tests for parse_number function."""

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_parse_number_never_raises(self, value: str, locale_code: str) -> None:
        """Property: parse_number never raises exceptions regardless of input."""
        result, errors = parse_number(value, locale_code)
        # Should always return a tuple
        assert isinstance(result, (float, type(None)))
        assert isinstance(errors, tuple)

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_parse_number_error_structure(self, value: str, locale_code: str) -> None:
        """Property: All errors in parse_number result are FrozenFluentError instances."""
        _, errors = parse_number(value, locale_code)
        for error in errors:
            assert isinstance(error, FrozenFluentError)
            assert error.category == ErrorCategory.PARSE
            assert error.context is not None
            assert hasattr(error.context, "input_value")
            assert hasattr(error.context, "locale_code")
            assert hasattr(error.context, "parse_type")

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_parse_number_result_xor_errors(self, value: str, locale_code: str) -> None:
        """Property: parse_number returns either result OR errors, not both."""
        result, errors = parse_number(value, locale_code)
        # Either result is None with errors, or result is float with no errors
        if result is None:
            assert len(errors) > 0
        else:
            assert isinstance(result, float)
            assert len(errors) == 0

    def test_parse_number_valid_en_us_integer(self) -> None:
        """Verify parse_number handles simple US integer."""
        result, errors = parse_number("42", "en_US")
        assert result == 42.0
        assert errors == ()

    def test_parse_number_valid_en_us_decimal(self) -> None:
        """Verify parse_number handles US decimal with comma separator."""
        result, errors = parse_number("1,234.56", "en_US")
        assert result == 1234.56
        assert errors == ()

    def test_parse_number_valid_lv_lv_decimal(self) -> None:
        """Verify parse_number handles Latvian decimal with space separator."""
        result, errors = parse_number("1 234,56", "lv_LV")
        assert result == 1234.56
        assert errors == ()

    def test_parse_number_invalid_value(self) -> None:
        """Verify parse_number returns error for invalid number string."""
        result, errors = parse_number("not-a-number", "en_US")
        assert result is None
        assert len(errors) == 1
        assert errors[0].context is not None
        assert errors[0].context.parse_type == "number"
        assert errors[0].context.input_value == "not-a-number"
        assert errors[0].context.locale_code == "en_US"

    def test_parse_number_invalid_locale(self) -> None:
        """Verify parse_number returns error for invalid locale code."""
        result, errors = parse_number("123", "invalid_LOCALE")
        assert result is None
        assert len(errors) == 1
        assert errors[0].context is not None
        assert errors[0].context.parse_type == "number"
        assert errors[0].context.input_value == "123"
        assert errors[0].context.locale_code == "invalid_LOCALE"

    def test_parse_number_empty_string(self) -> None:
        """Verify parse_number handles empty string."""
        result, errors = parse_number("", "en_US")
        assert result is None
        assert len(errors) == 1
        assert errors[0].context is not None
        assert errors[0].context.parse_type == "number"

    @given(st.floats(allow_nan=False, allow_infinity=False))
    def test_parse_number_roundtrip_en_us(self, value: float) -> None:
        """Property: Roundtrip parse_number for simple US locale numbers."""
        # Format as simple string without locale-specific separators
        str_value = str(value)
        result, errors = parse_number(str_value, "en_US")

        assert not errors

        # If parsing succeeded, result should be close to original
        if result is not None:
            assert abs(result - value) < 1e-10 or (result == 0.0 and value == 0.0)

    @given(st.integers(min_value=-1000000, max_value=1000000))
    def test_parse_number_integers_en_us(self, value: int) -> None:
        """Property: parse_number correctly parses integer strings."""
        str_value = str(value)
        result, errors = parse_number(str_value, "en_US")
        assert result == float(value)
        assert errors == ()

    def test_parse_number_negative_number(self) -> None:
        """Verify parse_number handles negative numbers."""
        result, errors = parse_number("-123.45", "en_US")
        assert result == -123.45
        assert errors == ()

    def test_parse_number_zero(self) -> None:
        """Verify parse_number handles zero."""
        result, errors = parse_number("0", "en_US")
        assert result == 0.0
        assert errors == ()


class TestParseDecimalProperties:
    """Property-based tests for parse_decimal function."""

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_parse_decimal_never_raises(self, value: str, locale_code: str) -> None:
        """Property: parse_decimal never raises exceptions regardless of input."""
        result, errors = parse_decimal(value, locale_code)
        # Should always return a tuple
        assert isinstance(result, (Decimal, type(None)))
        assert isinstance(errors, tuple)

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_parse_decimal_error_structure(self, value: str, locale_code: str) -> None:
        """Property: All errors in parse_decimal result are FrozenFluentError instances."""
        _, errors = parse_decimal(value, locale_code)
        for error in errors:
            assert isinstance(error, FrozenFluentError)
            assert error.category == ErrorCategory.PARSE
            assert error.context is not None
            assert hasattr(error.context, "input_value")
            assert hasattr(error.context, "locale_code")
            assert hasattr(error.context, "parse_type")

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_parse_decimal_result_xor_errors(self, value: str, locale_code: str) -> None:
        """Property: parse_decimal returns either result OR errors, not both."""
        result, errors = parse_decimal(value, locale_code)
        # Either result is None with errors, or result is Decimal with no errors
        if result is None:
            assert len(errors) > 0
        else:
            assert isinstance(result, Decimal)
            assert len(errors) == 0

    def test_parse_decimal_valid_en_us_integer(self) -> None:
        """Verify parse_decimal handles simple US integer."""
        result, errors = parse_decimal("42", "en_US")
        assert result == Decimal("42")
        assert errors == ()

    def test_parse_decimal_valid_en_us_decimal(self) -> None:
        """Verify parse_decimal handles US decimal with comma separator."""
        result, errors = parse_decimal("1,234.56", "en_US")
        assert result == Decimal("1234.56")
        assert errors == ()

    def test_parse_decimal_valid_lv_lv_decimal(self) -> None:
        """Verify parse_decimal handles Latvian decimal with space separator."""
        result, errors = parse_decimal("1 234,56", "lv_LV")
        assert result == Decimal("1234.56")
        assert errors == ()

    def test_parse_decimal_invalid_value(self) -> None:
        """Verify parse_decimal returns error for invalid number string."""
        result, errors = parse_decimal("not-a-number", "en_US")
        assert result is None
        assert len(errors) == 1
        assert errors[0].context is not None
        assert errors[0].context.parse_type == "decimal"
        assert errors[0].context.input_value == "not-a-number"
        assert errors[0].context.locale_code == "en_US"

    def test_parse_decimal_invalid_locale(self) -> None:
        """Verify parse_decimal returns error for invalid locale code."""
        result, errors = parse_decimal("123", "invalid_LOCALE")
        assert result is None
        assert len(errors) == 1
        assert errors[0].context is not None
        assert errors[0].context.parse_type == "decimal"
        assert errors[0].context.input_value == "123"
        assert errors[0].context.locale_code == "invalid_LOCALE"

    def test_parse_decimal_empty_string(self) -> None:
        """Verify parse_decimal handles empty string."""
        result, errors = parse_decimal("", "en_US")
        assert result is None
        assert len(errors) == 1
        assert errors[0].context is not None
        assert errors[0].context.parse_type == "decimal"

    @given(st.integers(min_value=-1000000, max_value=1000000))
    def test_parse_decimal_integers_en_us(self, value: int) -> None:
        """Property: parse_decimal correctly parses integer strings."""
        str_value = str(value)
        result, errors = parse_decimal(str_value, "en_US")
        assert result == Decimal(value)
        assert errors == ()

    @given(
        st.decimals(
            allow_nan=False,
            allow_infinity=False,
            min_value=Decimal("-1000000"),
            max_value=Decimal("1000000"),
            places=2,
        )
    )
    def test_parse_decimal_roundtrip_en_us(self, value: Decimal) -> None:
        """Property: Roundtrip parse_decimal for simple US locale decimals."""
        # Format as simple string without locale-specific separators
        str_value = str(value)
        result, errors = parse_decimal(str_value, "en_US")

        assert not errors

        # If parsing succeeded, result should equal original
        if result is not None:
            assert result == value

    def test_parse_decimal_negative_number(self) -> None:
        """Verify parse_decimal handles negative numbers."""
        result, errors = parse_decimal("-123.45", "en_US")
        assert result == Decimal("-123.45")
        assert errors == ()

    def test_parse_decimal_zero(self) -> None:
        """Verify parse_decimal handles zero."""
        result, errors = parse_decimal("0", "en_US")
        assert result == Decimal("0")
        assert errors == ()

    def test_parse_decimal_financial_precision(self) -> None:
        """Verify parse_decimal maintains financial precision (no float rounding)."""
        result, errors = parse_decimal("100.50", "en_US")
        assert result == Decimal("100.50")
        assert errors == ()

        # Test VAT calculation from docstring example
        if result is not None:
            vat = result * Decimal("0.21")
            assert vat == Decimal("21.105")


class TestParseNumberErrorTypes:
    """Tests for specific error types and parse_type field values."""

    def test_parse_number_error_has_number_parse_type(self) -> None:
        """Verify parse_number errors have parse_type='number'."""
        _, errors = parse_number("invalid", "en_US")
        assert len(errors) == 1
        assert errors[0].context is not None
        assert errors[0].context.parse_type == "number"

    def test_parse_decimal_error_has_decimal_parse_type(self) -> None:
        """Verify parse_decimal errors have parse_type='decimal'."""
        _, errors = parse_decimal("invalid", "en_US")
        assert len(errors) == 1
        assert errors[0].context is not None
        assert errors[0].context.parse_type == "decimal"

    def test_parse_number_locale_error_has_number_parse_type(self) -> None:
        """Verify parse_number locale errors have parse_type='number'."""
        _, errors = parse_number("123", "xx_INVALID")
        assert len(errors) == 1
        assert errors[0].context is not None
        assert errors[0].context.parse_type == "number"

    def test_parse_decimal_locale_error_has_decimal_parse_type(self) -> None:
        """Verify parse_decimal locale errors have parse_type='decimal'."""
        _, errors = parse_decimal("123", "xx_INVALID")
        assert len(errors) == 1
        assert errors[0].context is not None
        assert errors[0].context.parse_type == "decimal"


class TestParseNumberLocaleVariations:
    """Tests for various locale-specific number formats."""

    def test_parse_number_french_space_separator(self) -> None:
        """Verify parse_number handles French number format with space."""
        result, errors = parse_number("1 234,56", "fr_FR")
        assert result == 1234.56
        assert errors == ()

    def test_parse_number_german_dot_separator(self) -> None:
        """Verify parse_number handles German number format with dot separator."""
        result, errors = parse_number("1.234,56", "de_DE")
        assert result == 1234.56
        assert errors == ()

    def test_parse_decimal_french_space_separator(self) -> None:
        """Verify parse_decimal handles French number format with space."""
        result, errors = parse_decimal("1 234,56", "fr_FR")
        assert result == Decimal("1234.56")
        assert errors == ()

    def test_parse_decimal_german_dot_separator(self) -> None:
        """Verify parse_decimal handles German number format with dot separator."""
        result, errors = parse_decimal("1.234,56", "de_DE")
        assert result == Decimal("1234.56")
        assert errors == ()


class TestParseNumberEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_parse_number_very_small_float(self) -> None:
        """Verify parse_number handles very small floating point numbers."""
        result, errors = parse_number("0.000001", "en_US")
        assert result == 0.000001
        assert errors == ()

    def test_parse_number_very_large_float(self) -> None:
        """Verify parse_number handles very large floating point numbers."""
        result, errors = parse_number("999999999.99", "en_US")
        assert result == 999999999.99
        assert errors == ()

    def test_parse_decimal_very_small_decimal(self) -> None:
        """Verify parse_decimal handles very small decimal numbers."""
        result, errors = parse_decimal("0.000001", "en_US")
        assert result == Decimal("0.000001")
        assert errors == ()

    def test_parse_decimal_very_large_decimal(self) -> None:
        """Verify parse_decimal handles very large decimal numbers."""
        result, errors = parse_decimal("999999999.99", "en_US")
        assert result == Decimal("999999999.99")
        assert errors == ()

    def test_parse_number_whitespace_only(self) -> None:
        """Verify parse_number handles whitespace-only string."""
        result, errors = parse_number("   ", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_parse_decimal_whitespace_only(self) -> None:
        """Verify parse_decimal handles whitespace-only string."""
        result, errors = parse_decimal("   ", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_parse_number_leading_trailing_whitespace(self) -> None:
        """Verify parse_number handles numbers with leading/trailing whitespace."""
        result, errors = parse_number("  123.45  ", "en_US")
        # Babel might handle this - either way, no exception should be raised
        assert isinstance(result, (float, type(None)))
        assert isinstance(errors, tuple)

    @given(
        st.text(
            alphabet=st.characters(
                blacklist_characters="0123456789.,-+ ",
                # Exclude ALL Unicode decimal digits (Nd category)
                blacklist_categories=("Nd",),  # type: ignore[arg-type]
            ),
            min_size=1,
        )
    )
    def test_parse_number_no_digits(self, value: str) -> None:
        """Property: parse_number returns error for strings with no digits."""
        assume(value.strip() != "")  # Skip empty strings
        # Skip special float literals that Babel/Python accept
        special_literals = (
            "inf",
            "infinity",
            "-infinity",
            "+infinity",
            "nan",
            "-nan",
            "+nan",
        )
        assume(value.lower() not in special_literals)
        assume("inf" not in value.lower())
        assume("nan" not in value.lower())
        result, errors = parse_number(value, "en_US")
        # Should fail to parse
        assert result is None
        assert len(errors) == 1
