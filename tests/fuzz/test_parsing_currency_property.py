"""Property-based fuzz tests for ftllexengine.parsing.currency.

Tests parse_currency() and currency-related strategies for HypoFuzz coverage.
All tests that call parse_currency() are guarded by a Babel availability check
because the currency parser requires Babel for CLDR data.

Target Coverage:
- currency_amount_magnitude: micro/small/medium/large/huge
- currency_input_type: unambiguous_symbol/ambiguous_symbol/iso_code/invalid
- currency_input_format: prefix/suffix/iso_prefix/iso_suffix
- currency_ambiguous_symbol: dollar/yen/pound/krona/other
- currency_iso_position: prefix/suffix
- currency_invalid_reason: no_symbol/no_digits/empty/garbage/bad_iso
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import event, given, settings

from ftllexengine.core.babel_compat import is_babel_available
from tests.strategies import (
    ambiguous_currency_inputs,
    currency_amounts,
    invalid_currency_inputs,
    iso_code_currency_inputs,
    unambiguous_currency_inputs,
)

pytestmark = pytest.mark.fuzz

_BABEL_AVAILABLE = is_babel_available()


class TestCurrencyAmountStrategy:
    """Property tests for currency_amounts() strategy.

    These tests do not require Babel — they verify the strategy produces
    structurally valid Decimal amounts across all magnitude categories.
    """

    @given(amount=currency_amounts())
    @settings(max_examples=200, deadline=None)
    def test_currency_amount_positive(self, amount: Decimal) -> None:
        """Property: currency_amounts() generates positive amounts."""
        event(f"outcome=magnitude_positive={amount > 0}")
        assert isinstance(amount, Decimal)
        assert amount > Decimal("0")

    @given(amount=currency_amounts())
    @settings(max_examples=200, deadline=None)
    def test_currency_amount_finite(self, amount: Decimal) -> None:
        """Property: currency_amounts() generates finite, non-NaN amounts."""
        event(f"outcome=is_finite={amount.is_finite()}")
        assert amount.is_finite()
        assert not amount.is_nan()
        assert not amount.is_infinite()

    @given(amount=currency_amounts())
    @settings(max_examples=200, deadline=None)
    def test_currency_amount_two_decimal_places(self, amount: Decimal) -> None:
        """Property: currency_amounts() uses exactly 2 decimal places."""
        _sign, _digits, exponent = amount.as_tuple()
        event(f"outcome=exponent={exponent}")
        # All generated amounts use places=2 (Decimal with 2 fractional digits)
        assert exponent == -2


@pytest.mark.skipif(
    not _BABEL_AVAILABLE, reason="Babel required for parse_currency tests"
)
class TestParseCurrencyProperties:
    """Property tests for parse_currency() requiring Babel.

    Tests use currency input strategies to exercise all input type and
    format categories. Results are checked for structural correctness:
    parse_currency always returns (result|None, tuple[errors]).
    """

    @given(input_data=unambiguous_currency_inputs())
    @settings(max_examples=200, deadline=None)
    def test_unambiguous_inputs_return_valid_structure(
        self, input_data: tuple[str, str, str]
    ) -> None:
        """Property: Unambiguous inputs return correct (result, errors) structure."""
        from ftllexengine.parsing.currency import parse_currency  # noqa: PLC0415
        value, locale, _expected_code = input_data
        result, errors = parse_currency(value, locale)
        has_result = result is not None
        event(f"outcome=parsed={has_result}")
        assert isinstance(errors, tuple)
        if result is not None:
            amount, code = result
            assert isinstance(amount, Decimal)
            assert isinstance(code, str)
            assert len(code) == 3  # ISO 4217: 3-char codes

    @given(input_data=iso_code_currency_inputs())
    @settings(max_examples=200, deadline=None)
    def test_iso_code_inputs_return_valid_structure(
        self, input_data: tuple[str, str, str]
    ) -> None:
        """Property: ISO code inputs return structurally valid results."""
        from ftllexengine.parsing.currency import parse_currency  # noqa: PLC0415
        value, locale, expected_code = input_data
        result, errors = parse_currency(value, locale)
        has_result = result is not None
        event(f"outcome=parsed={has_result}")
        assert isinstance(errors, tuple)
        if result is not None:
            amount, code = result
            assert isinstance(amount, Decimal)
            assert code == expected_code

    @given(input_data=invalid_currency_inputs())
    @settings(max_examples=200, deadline=None)
    def test_invalid_inputs_fail_gracefully(
        self, input_data: tuple[str, str]
    ) -> None:
        """Property: Invalid currency inputs return None or errors, never crash."""
        from ftllexengine.parsing.currency import parse_currency  # noqa: PLC0415
        value, locale = input_data
        result, errors = parse_currency(value, locale)
        has_error = len(errors) > 0
        event(f"outcome=has_error={has_error}")
        # Invalid input should return no result, or have errors in the tuple
        assert result is None or len(errors) > 0

    @given(input_data=ambiguous_currency_inputs())
    @settings(max_examples=200, deadline=None)
    def test_ambiguous_inputs_with_locale_inference(
        self, input_data: tuple[str, str, str, str]
    ) -> None:
        """Property: Ambiguous symbol inputs with infer_from_locale return structure."""
        from ftllexengine.parsing.currency import parse_currency  # noqa: PLC0415
        value, locale, _default_currency, _expected_code = input_data
        result, errors = parse_currency(value, locale, infer_from_locale=True)
        has_result = result is not None
        event(f"outcome=resolved={has_result}")
        assert isinstance(errors, tuple)
        if result is not None:
            amount, code = result
            assert isinstance(amount, Decimal)
            assert len(code) == 3  # ISO 4217: 3-char codes
