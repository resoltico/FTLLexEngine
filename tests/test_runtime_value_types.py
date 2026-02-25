"""Tests for runtime/value_types.py: FluentNumber construction invariants.

Covers lines 111-115: the non-bool, non-int, non-Decimal type guard that
raises TypeError for values outside the permitted union (int | Decimal).

The bool guard (lines 103-109) and precision guard (lines 116-122) are
already exercised by other tests; this file covers the remaining branch.

Python 3.13+.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ftllexengine.runtime.value_types import FluentNumber


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
