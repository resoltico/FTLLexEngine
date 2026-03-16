"""Tests for core/value_types.py value construction contracts.

Covers the non-bool, non-int, non-Decimal type guard that raises TypeError
for values outside the permitted union (int | Decimal), the bool rejection
guard, the negative-precision guard, and the make_fluent_number() helper.
Also covers private precision-inference helpers directly.

Python 3.13+.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ftllexengine.core.value_types import (
    FluentNumber,
    _infer_visible_precision,
    _normalize_numeric_text,
    _parse_numeric_segment,
    _unwrap_parenthesized_negative,
    _visible_precision_from_value,
    make_fluent_number,
)


class TestFluentNumberInvalidValueType:
    """FluentNumber rejects values that are not int or Decimal."""

    def test_string_value_raises_type_error(self) -> None:
        """FluentNumber with str value raises TypeError.

        The type annotation constrains value to int | Decimal, but runtime
        callers can bypass it. The guard catches this and raises TypeError
        with a message naming the actual type.
        """
        with pytest.raises(TypeError, match="must be int or Decimal"):
            FluentNumber(value="not-a-number", formatted="0")  # type: ignore[arg-type]

    def test_float_value_raises_type_error(self) -> None:
        """FluentNumber with float value raises TypeError.

        float is deliberately excluded: IEEE 754 cannot represent most
        decimal fractions exactly. Callers must use Decimal(str(float_val)).
        """
        with pytest.raises(TypeError, match="must be int or Decimal"):
            FluentNumber(value=3.14, formatted="3.14")  # type: ignore[arg-type]

    def test_list_value_raises_type_error(self) -> None:
        """FluentNumber with list value raises TypeError."""
        with pytest.raises(TypeError, match="must be int or Decimal"):
            FluentNumber(value=[1, 2], formatted="[1, 2]")  # type: ignore[arg-type]

    def test_none_value_raises_type_error(self) -> None:
        """FluentNumber with None value raises TypeError."""
        with pytest.raises(TypeError, match="must be int or Decimal"):
            FluentNumber(value=None, formatted="None")  # type: ignore[arg-type]

    def test_error_message_includes_actual_type_name(self) -> None:
        """TypeError message names the actual type received."""
        with pytest.raises(TypeError, match="got str"):
            FluentNumber(value="bad", formatted="bad")  # type: ignore[arg-type]

    def test_bool_value_raises_type_error(self) -> None:
        """FluentNumber with bool raises TypeError.

        bool is an int subtype but is checked first (before the int|Decimal guard)
        because it carries no numeric localization semantics.
        """
        with pytest.raises(TypeError, match="not bool"):
            FluentNumber(value=True, formatted="true")

    def test_valid_int_value_accepted(self) -> None:
        """FluentNumber with int value is accepted."""
        fn = FluentNumber(value=42, formatted="42")
        assert fn.value == 42
        assert str(fn) == "42"

    def test_valid_decimal_value_accepted(self) -> None:
        """FluentNumber with Decimal value is accepted."""
        fn = FluentNumber(value=Decimal("3.14"), formatted="3.14", precision=2)
        assert fn.value == Decimal("3.14")
        assert str(fn) == "3.14"


class TestMakeFluentNumber:
    """make_fluent_number() derives FluentNumber precision consistently."""

    def test_default_format_preserves_decimal_trailing_zeros(self) -> None:
        """Default formatting uses Decimal string form and visible precision."""
        fn = make_fluent_number(Decimal("12.3400"))

        assert fn.value == Decimal("12.3400")
        assert fn.formatted == "12.3400"
        assert fn.precision == 4

    def test_integer_defaults_to_zero_precision(self) -> None:
        """Integers without explicit formatting have zero visible decimals."""
        fn = make_fluent_number(42)

        assert fn.value == 42
        assert fn.formatted == "42"
        assert fn.precision == 0

    def test_formatted_integer_can_expose_fraction_digits(self) -> None:
        """Explicit formatted strings control visible precision for int values."""
        fn = make_fluent_number(42, formatted="42.00")

        assert fn.formatted == "42.00"
        assert fn.precision == 2

    def test_grouped_integer_does_not_treat_group_separator_as_decimal(self) -> None:
        """Grouping separators are ignored when they preserve the original value."""
        fn = make_fluent_number(1234, formatted="1,234")

        assert fn.formatted == "1,234"
        assert fn.precision == 0

    def test_localized_formatted_string_uses_visible_precision(self) -> None:
        """Localized decimal separators are inferred from the rendered string."""
        fn = make_fluent_number(Decimal("1234.50"), formatted="1 234,50 EUR")

        assert fn.formatted == "1 234,50 EUR"
        assert fn.precision == 2

    def test_formatted_decimal_can_express_trailing_zero_precision_for_int_value(self) -> None:
        """Value reconciliation distinguishes decimal formatting from grouping."""
        fn = make_fluent_number(1, formatted="1,000")

        assert fn.formatted == "1,000"
        assert fn.precision == 3

    def test_bool_value_raises_type_error(self) -> None:
        """Bool inputs are rejected just like direct FluentNumber construction."""
        with pytest.raises(TypeError, match="not bool"):
            make_fluent_number(True)


class TestPrivateHelpers:
    """Direct tests for private precision-inference helpers.

    These functions are internal implementation details of the visible-precision
    algorithm. Testing them directly achieves branch coverage for paths that
    require crafted inputs not produced by the public API.
    """

    def test_visible_precision_from_value_int(self) -> None:
        """Integer value always returns zero precision."""
        assert _visible_precision_from_value(5) == 0
        assert _visible_precision_from_value(0) == 0
        assert _visible_precision_from_value(-42) == 0

    def test_visible_precision_from_value_decimal_with_fraction(self) -> None:
        """Decimal with negative exponent returns digit count after decimal point."""
        assert _visible_precision_from_value(Decimal("1.23")) == 2
        assert _visible_precision_from_value(Decimal("0.001")) == 3
        assert _visible_precision_from_value(Decimal("1.0")) == 1

    def test_visible_precision_from_value_decimal_whole_number(self) -> None:
        """Decimal with non-negative exponent returns zero precision."""
        assert _visible_precision_from_value(Decimal(100)) == 0
        assert _visible_precision_from_value(Decimal("1E+2")) == 0

    def test_unwrap_parenthesized_negative_with_parens(self) -> None:
        """Parenthesized segment is stripped and marked negative."""
        inner, negative = _unwrap_parenthesized_negative("(1.23)")
        assert inner == "1.23"
        assert negative is True

    def test_unwrap_parenthesized_negative_without_parens(self) -> None:
        """Non-parenthesized segment is returned as-is, not negative."""
        inner, negative = _unwrap_parenthesized_negative("1.23")
        assert inner == "1.23"
        assert negative is False

    def test_normalize_numeric_text_sign_after_digit_is_skipped(self) -> None:
        """Sign character appearing after digits is discarded (duplicate/mid-number)."""
        # '+' after '1' → normalized=['1'], saw_sign=False, but normalized is non-empty
        # so the continue branch fires and '+' is dropped
        result = _normalize_numeric_text("1+2", decimal_symbol=None)
        assert result == "12"

    def test_normalize_numeric_text_double_sign_second_dropped(self) -> None:
        """Second sign character is discarded when saw_sign is already True."""
        # First '+' sets saw_sign=True; second '+' sees saw_sign=True → continue
        result = _normalize_numeric_text("++5", decimal_symbol=None)
        assert result == "+5"

    def test_normalize_numeric_text_paren_chars_skipped(self) -> None:
        """Parenthesis characters inside a normalized segment are silently skipped."""
        # After outer-paren stripping by _unwrap_parenthesized_negative, inner parens
        # like in "((1.23))" → inner="(1.23)" → _normalize_numeric_text sees parens
        result = _normalize_numeric_text("(1.23)", decimal_symbol=".")
        assert result == "1.23"

    def test_parse_numeric_segment_normalize_returns_none(self) -> None:
        """Returns None when _normalize_numeric_text produces None (invalid chars)."""
        # 'X' is not a digit, sign, separator, or paren → normalize returns None
        result = _parse_numeric_segment("1X2", decimal_symbol=None)
        assert result is None

    def test_parse_numeric_segment_empty_after_normalize(self) -> None:
        """Returns None when normalized text is sign-only (no digits)."""
        result = _parse_numeric_segment("+", decimal_symbol=None)
        assert result is None

    def test_parse_numeric_segment_invalid_operation(self) -> None:
        """Returns None when Decimal() raises InvalidOperation on normalized text."""
        # Two decimal points produce "1.2.3" which is not a valid Decimal literal
        result = _parse_numeric_segment("1.2.3", decimal_symbol=".")
        assert result is None

    def test_parse_numeric_segment_parenthesized_negate(self) -> None:
        """Parenthesized value is negated to produce the correct negative Decimal."""
        result = _parse_numeric_segment("(1,23)", decimal_symbol=",")
        assert result == Decimal("-1.23")

    def test_infer_visible_precision_multi_segment_continues(self) -> None:
        """Loop continues to the next segment when the first does not match target.

        "99 and 1.23" yields two segments: "99" (does not reconcile to 1.23) and
        "1.23" (matches). The loop-continuation branch (first segment not matching)
        is the path under test.
        """
        result = _infer_visible_precision(Decimal("1.23"), "99 and 1.23")
        assert result == 2

    def test_infer_visible_precision_no_matching_segment_falls_back(self) -> None:
        """Falls back to _visible_precision_from_value when no segment reconciles.

        A formatted string with no numeric content produces no segments, so the
        fallback path is taken. For a Decimal value, this exercises the Decimal
        branch of _visible_precision_from_value.
        """
        result = _infer_visible_precision(Decimal("1.23"), "no-numbers")
        # Fallback uses Decimal exponent: -2 fraction digits for Decimal("1.23")
        assert result == 2


# ===========================================================================
# FluentNumber.decimal_value property
# ===========================================================================


class TestFluentNumberDecimalValue:
    """FluentNumber.decimal_value returns exact Decimal regardless of value type."""

    def test_int_value_coerced_to_decimal(self) -> None:
        """Integer value is coerced to exact Decimal."""
        fn = FluentNumber(value=42, formatted="42", precision=0)
        result = fn.decimal_value
        assert isinstance(result, Decimal)
        assert result == Decimal(42)

    def test_decimal_value_returned_as_is(self) -> None:
        """Decimal value is returned without copying."""
        d = Decimal("1234.50")
        fn = FluentNumber(value=d, formatted="1,234.50", precision=2)
        result = fn.decimal_value
        assert result is d  # exact same object (Decimal is immutable)
        assert result == Decimal("1234.50")

    def test_zero_int_value(self) -> None:
        """Zero integer yields Decimal('0')."""
        fn = FluentNumber(value=0, formatted="0", precision=0)
        assert fn.decimal_value == Decimal(0)

    def test_large_int_exact_conversion(self) -> None:
        """Large integers convert exactly (no float precision loss)."""
        large = 10 ** 18
        fn = FluentNumber(value=large, formatted=str(large), precision=0)
        assert fn.decimal_value == Decimal(large)

    def test_negative_int_value(self) -> None:
        """Negative integer converts correctly."""
        fn = FluentNumber(value=-7, formatted="-7", precision=0)
        assert fn.decimal_value == Decimal(-7)

    def test_trailing_zeros_preserved_for_decimal(self) -> None:
        """Trailing zeros in Decimal are preserved (financial significance)."""
        d = Decimal("1.50")
        fn = FluentNumber(value=d, formatted="1.50", precision=2)
        result = fn.decimal_value
        # Decimal('1.50') and Decimal('1.5') compare equal but have different scales.
        # The property returns the original object, so scale is preserved.
        assert result == Decimal("1.50")
        assert str(result) == "1.50"

    def test_decimal_value_type_is_always_decimal(self) -> None:
        """Property always returns Decimal regardless of input type."""
        int_fn = FluentNumber(value=5, formatted="5", precision=0)
        dec_fn = FluentNumber(value=Decimal(5), formatted="5", precision=0)
        assert isinstance(int_fn.decimal_value, Decimal)
        assert isinstance(dec_fn.decimal_value, Decimal)
        assert int_fn.decimal_value == dec_fn.decimal_value
