"""Runtime bugfixes for v0.101.0: F001, F002, F003.

Tests for:
- F001: _compute_visible_precision with literal digit suffix patterns
- F002: FluentBundle rejects dict as functions parameter
- F003: NaN/Infinity graceful handling in plural category selection
"""

from __future__ import annotations

import sys
from collections import OrderedDict
from decimal import Decimal

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

sys.path.insert(0, "src")

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.functions import _compute_visible_precision
from ftllexengine.runtime.plural_rules import select_plural_category


class TestF001PrecisionLiteralSuffix:
    """F001: _compute_visible_precision caps at max_fraction_digits."""

    def test_no_cap_without_max(self) -> None:
        """Without max_fraction_digits, all trailing digits count."""
        assert _compute_visible_precision("1.25", ".") == 2

    def test_cap_at_max_fraction_digits(self) -> None:
        """With max_fraction_digits=1, precision capped to 1."""
        assert _compute_visible_precision("1.25", ".", max_fraction_digits=1) == 1

    def test_cap_does_not_inflate(self) -> None:
        """Cap does not inflate precision beyond actual digits."""
        assert _compute_visible_precision("1.2", ".", max_fraction_digits=5) == 1

    def test_zero_max_fraction_digits(self) -> None:
        """max_fraction_digits=0 returns 0 precision."""
        assert _compute_visible_precision("1.25", ".", max_fraction_digits=0) == 0

    def test_no_decimal_point(self) -> None:
        """No decimal point returns 0 regardless of cap."""
        assert _compute_visible_precision("125", ".") == 0
        assert _compute_visible_precision("125", ".", max_fraction_digits=3) == 0

    @given(
        frac_digits=st.integers(min_value=0, max_value=20),
        cap=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=50)
    def test_result_never_exceeds_cap(self, frac_digits: int, cap: int) -> None:
        """Result never exceeds max_fraction_digits when provided."""
        event(f"frac_digits={frac_digits}")
        formatted = "1." + "0" * frac_digits if frac_digits > 0 else "1"
        result = _compute_visible_precision(formatted, ".", max_fraction_digits=cap)
        assert result <= cap

    @given(frac_digits=st.integers(min_value=0, max_value=20))
    @settings(max_examples=50)
    def test_result_never_exceeds_actual_digits(self, frac_digits: int) -> None:
        """Result never exceeds actual fraction digit count."""
        event(f"frac_digits={frac_digits}")
        formatted = "1." + "0" * frac_digits if frac_digits > 0 else "1"
        result = _compute_visible_precision(formatted, ".", max_fraction_digits=100)
        assert result <= frac_digits


class TestF002DictFunctionsRejected:
    """F002: FluentBundle rejects dict as functions parameter."""

    def test_dict_raises_type_error(self) -> None:
        """Passing a dict for functions raises TypeError at init time."""
        with pytest.raises(TypeError, match="FunctionRegistry"):
            FluentBundle("en_US", functions={"UPPER": str.upper})  # type: ignore[arg-type]

    def test_none_functions_accepted(self) -> None:
        """None for functions creates default registry."""
        bundle = FluentBundle("en_US", functions=None)
        assert bundle is not None

    def test_ordered_dict_rejected(self) -> None:
        """OrderedDict also rejected (has .copy() but not FunctionRegistry)."""
        with pytest.raises(TypeError, match="FunctionRegistry"):
            FluentBundle("en_US", functions=OrderedDict())  # type: ignore[arg-type]


class TestF003NaNPluralHandling:
    """F003: NaN and Infinity values fall through to 'other' plural category."""

    def test_float_nan_returns_other(self) -> None:
        """float('nan') returns 'other' plural category."""
        result = select_plural_category(float("nan"), "en_US")
        assert result == "other"

    def test_float_inf_returns_other(self) -> None:
        """float('inf') returns 'other' plural category."""
        result = select_plural_category(float("inf"), "en_US")
        assert result == "other"

    def test_float_neg_inf_returns_other(self) -> None:
        """float('-inf') returns 'other' plural category."""
        result = select_plural_category(float("-inf"), "en_US")
        assert result == "other"

    def test_decimal_nan_returns_other(self) -> None:
        """Decimal('NaN') returns 'other' plural category."""
        result = select_plural_category(Decimal("NaN"), "en_US")
        assert result == "other"

    def test_decimal_inf_returns_other(self) -> None:
        """Decimal('Infinity') returns 'other' plural category."""
        result = select_plural_category(Decimal("Infinity"), "en_US")
        assert result == "other"

    def test_normal_numbers_still_work(self) -> None:
        """Normal numbers still get proper plural categories."""
        assert select_plural_category(1, "en_US") == "one"
        assert select_plural_category(0, "en_US") == "other"
        assert select_plural_category(2, "en_US") == "other"

    def test_nan_in_select_expression(self) -> None:
        """NaN in select expression falls through to default variant."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "msg = { NUMBER($count) ->\n"
            "    [one] one item\n"
            "   *[other] many items\n"
            "}"
        )
        result, _errors = bundle.format_pattern("msg", {"count": float("nan")})
        assert "many items" in result
