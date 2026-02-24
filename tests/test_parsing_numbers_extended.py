"""Comprehensive property-based tests for parsing.numbers module.

Tests locale-aware decimal parsing with error handling.

"""

from decimal import Decimal

from hypothesis import assume, event, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.parsing.numbers import parse_decimal


class TestParseDecimalProperties:
    """Property-based tests for parse_decimal function."""

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_parse_decimal_never_raises(self, value: str, locale_code: str) -> None:
        """Property: parse_decimal never raises exceptions regardless of input."""
        result, errors = parse_decimal(value, locale_code)
        assert isinstance(result, (Decimal, type(None)))
        assert isinstance(errors, tuple)
        parsed = result is not None
        event(f"parsed={parsed}")

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
        n_errors = len(errors)
        event(f"error_count={n_errors}")

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_parse_decimal_result_xor_errors(self, value: str, locale_code: str) -> None:
        """Property: parse_decimal returns either result OR errors, not both."""
        result, errors = parse_decimal(value, locale_code)
        if result is None:
            assert len(errors) > 0
            event("outcome=error_branch")
        else:
            assert isinstance(result, Decimal)
            assert len(errors) == 0
            event("outcome=success_branch")

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
        sign = "neg" if value < 0 else "non_neg"
        event(f"value_sign={sign}")

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
        str_value = str(value)
        result, errors = parse_decimal(str_value, "en_US")
        assert not errors
        if result is not None:
            assert result == value
        sign = "neg" if value < 0 else "non_neg"
        event(f"value_sign={sign}")

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


class TestParseDecimalErrorTypes:
    """Tests for specific error types and parse_type field values."""

    def test_parse_decimal_error_has_decimal_parse_type(self) -> None:
        """Verify parse_decimal errors have parse_type='decimal'."""
        _, errors = parse_decimal("invalid", "en_US")
        assert len(errors) == 1
        assert errors[0].context is not None
        assert errors[0].context.parse_type == "decimal"

    def test_parse_decimal_locale_error_has_decimal_parse_type(self) -> None:
        """Verify parse_decimal locale errors have parse_type='decimal'."""
        _, errors = parse_decimal("123", "xx_INVALID")
        assert len(errors) == 1
        assert errors[0].context is not None
        assert errors[0].context.parse_type == "decimal"


class TestParseDecimalLocaleVariations:
    """Tests for various locale-specific number formats."""

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


class TestParseDecimalEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_parse_decimal_very_small(self) -> None:
        """Verify parse_decimal handles very small decimal numbers."""
        result, errors = parse_decimal("0.000001", "en_US")
        assert result == Decimal("0.000001")
        assert errors == ()

    def test_parse_decimal_very_large(self) -> None:
        """Verify parse_decimal handles very large decimal numbers."""
        result, errors = parse_decimal("999999999.99", "en_US")
        assert result == Decimal("999999999.99")
        assert errors == ()

    def test_parse_decimal_whitespace_only(self) -> None:
        """Verify parse_decimal handles whitespace-only string."""
        result, errors = parse_decimal("   ", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_parse_decimal_leading_trailing_whitespace(self) -> None:
        """Verify parse_decimal handles numbers with leading/trailing whitespace."""
        result, errors = parse_decimal("  123.45  ", "en_US")
        assert isinstance(result, (Decimal, type(None)))
        assert isinstance(errors, tuple)

    @given(
        st.text(
            alphabet=st.characters(
                blacklist_characters="0123456789.,-+ ",
                blacklist_categories=("Nd",),  # type: ignore[arg-type]
            ),
            min_size=1,
        )
    )
    def test_parse_decimal_no_digits(self, value: str) -> None:
        """Property: parse_decimal returns error for strings with no digits."""
        assume(value.strip() != "")
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
        result, errors = parse_decimal(value, "en_US")
        assert result is None
        assert len(errors) == 1
        has_space = " " in value
        event(f"has_space={has_space}")
