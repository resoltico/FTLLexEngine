"""Tests for runtime/value_types.py value construction contracts.

Covers lines 111-115: the non-bool, non-int, non-Decimal type guard that
raises TypeError for values outside the permitted union (int | Decimal).

The bool guard (lines 103-109) and precision guard (lines 116-122) are
already exercised by other tests. Also covers make_fluent_number(), the
public helper for constructing FluentNumber instances from domain values.

Python 3.13+.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ftllexengine.runtime.value_types import FluentNumber, make_fluent_number


class TestFluentNumberInvalidValueType:
    """FluentNumber rejects values that are not int or Decimal (lines 111-115)."""

    def test_string_value_raises_type_error(self) -> None:
        """FluentNumber with str value raises TypeError (lines 111-115).

        The type annotation constrains value to int | Decimal, but runtime
        callers can bypass it. The guard catches this and raises TypeError
        with a message naming the actual type.
        """
        with pytest.raises(TypeError, match="must be int or Decimal"):
            FluentNumber(value="not-a-number", formatted="0")  # type: ignore[arg-type]

    def test_float_value_raises_type_error(self) -> None:
        """FluentNumber with float value raises TypeError (lines 111-115).

        float is deliberately excluded: IEEE 754 cannot represent most
        decimal fractions exactly. Callers must use Decimal(str(float_val)).
        """
        with pytest.raises(TypeError, match="must be int or Decimal"):
            FluentNumber(value=3.14, formatted="3.14")  # type: ignore[arg-type]

    def test_list_value_raises_type_error(self) -> None:
        """FluentNumber with list value raises TypeError (lines 111-115)."""
        with pytest.raises(TypeError, match="must be int or Decimal"):
            FluentNumber(value=[1, 2], formatted="[1, 2]")  # type: ignore[arg-type]

    def test_none_value_raises_type_error(self) -> None:
        """FluentNumber with None value raises TypeError (lines 111-115)."""
        with pytest.raises(TypeError, match="must be int or Decimal"):
            FluentNumber(value=None, formatted="None")  # type: ignore[arg-type]

    def test_error_message_includes_actual_type_name(self) -> None:
        """TypeError message names the actual type received."""
        with pytest.raises(TypeError, match="got str"):
            FluentNumber(value="bad", formatted="bad")  # type: ignore[arg-type]

    def test_bool_value_raises_type_error(self) -> None:
        """FluentNumber with bool raises TypeError (lines 103-109).

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
