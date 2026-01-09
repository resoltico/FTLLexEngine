"""Hypothesis property-based tests for parsing type guards.

Type guards work with tuple return types from parsing functions:
- Type guards now work with the new tuple return types
- Tests validate type narrowing with (result, errors) tuple unpacking

Unified None handling:
- All type guards now accept None and return False
- Removed "check errors first" pattern - guards are now safe to call directly

Tests type guard correctness, type narrowing properties, and edge cases.
Ensures 100% coverage of parsing/guards.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.parsing.guards import (
    is_valid_currency,
    is_valid_date,
    is_valid_datetime,
    is_valid_decimal,
    is_valid_number,
)

# ============================================================================
# HYPOTHESIS STRATEGIES
# ============================================================================


# Strategy for Decimal values
decimals = st.decimals(allow_nan=True, allow_infinity=True, places=2)

# Strategy for floats
floats = st.floats(allow_nan=True, allow_infinity=True)

# Strategy for currency tuples
currency_tuples = st.tuples(
    st.decimals(allow_nan=True, allow_infinity=True, places=2),
    st.from_regex(r"[A-Z]{3}", fullmatch=True),
)


# ============================================================================
# PROPERTY TESTS - is_valid_decimal
# ============================================================================


class TestValidDecimalGuard:
    """Test is_valid_decimal() type guard properties.

    Accepts None and returns False for None values.
    """

    @given(value=st.decimals(allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_finite_decimal_returns_true(self, value: Decimal) -> None:
        """PROPERTY: Finite Decimal values return True."""
        assert is_valid_decimal(value) is True

    @given(value=st.none())
    @settings(max_examples=50)
    def test_none_returns_false(self, value: None) -> None:
        """PROPERTY: None returns False (unified API)."""
        assert is_valid_decimal(value) is False

    @given(value=st.just(Decimal("NaN")))
    @settings(max_examples=50)
    def test_nan_returns_false(self, value: Decimal) -> None:
        """PROPERTY: NaN Decimal returns False."""
        assert value.is_nan()
        assert is_valid_decimal(value) is False

    @given(value=st.just(Decimal("Infinity")))
    @settings(max_examples=50)
    def test_positive_infinity_returns_false(self, value: Decimal) -> None:
        """PROPERTY: Positive infinity Decimal returns False."""
        assert value.is_infinite()
        assert is_valid_decimal(value) is False

    @given(value=st.just(Decimal("-Infinity")))
    @settings(max_examples=50)
    def test_negative_infinity_returns_false(self, value: Decimal) -> None:
        """PROPERTY: Negative infinity Decimal returns False."""
        assert value.is_infinite()
        assert is_valid_decimal(value) is False


# ============================================================================
# PROPERTY TESTS - is_valid_number
# ============================================================================


class TestValidNumberGuard:
    """Test is_valid_number() type guard properties.

    Accepts None and returns False for None values.
    """

    @given(value=st.floats(allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_finite_float_returns_true(self, value: float) -> None:
        """PROPERTY: Finite float values return True."""
        assert is_valid_number(value) is True

    @given(value=st.none())
    @settings(max_examples=50)
    def test_none_returns_false(self, value: None) -> None:
        """PROPERTY: None returns False (unified API)."""
        assert is_valid_number(value) is False

    @given(value=st.just(float("nan")))
    @settings(max_examples=50)
    def test_nan_returns_false(self, value: float) -> None:
        """PROPERTY: NaN float returns False."""
        assert is_valid_number(value) is False

    @given(value=st.just(float("inf")))
    @settings(max_examples=50)
    def test_positive_infinity_returns_false(self, value: float) -> None:
        """PROPERTY: Positive infinity float returns False."""
        assert is_valid_number(value) is False

    @given(value=st.just(float("-inf")))
    @settings(max_examples=50)
    def test_negative_infinity_returns_false(self, value: float) -> None:
        """PROPERTY: Negative infinity float returns False."""
        assert is_valid_number(value) is False


# ============================================================================
# PROPERTY TESTS - is_valid_currency
# ============================================================================


class TestValidCurrencyGuard:
    """Test is_valid_currency() type guard properties."""

    @given(
        amount=st.decimals(allow_nan=False, allow_infinity=False, places=2),
        currency=st.from_regex(r"[A-Z]{3}", fullmatch=True),
    )
    @settings(max_examples=200)
    def test_valid_currency_tuple_returns_true(
        self, amount: Decimal, currency: str
    ) -> None:
        """PROPERTY: Valid (Decimal, str) tuple returns True."""
        value = (amount, currency)
        assert is_valid_currency(value) is True

    @given(value=st.none())
    @settings(max_examples=50)
    def test_none_returns_false(self, value: None) -> None:
        """PROPERTY: None returns False."""
        assert is_valid_currency(value) is False

    @given(currency=st.from_regex(r"[A-Z]{3}", fullmatch=True))
    @settings(max_examples=50)
    def test_nan_amount_returns_false(self, currency: str) -> None:
        """PROPERTY: NaN amount returns False."""
        value = (Decimal("NaN"), currency)
        assert is_valid_currency(value) is False

    @given(currency=st.from_regex(r"[A-Z]{3}", fullmatch=True))
    @settings(max_examples=50)
    def test_infinite_amount_returns_false(self, currency: str) -> None:
        """PROPERTY: Infinite amount returns False."""
        value = (Decimal("Infinity"), currency)
        assert is_valid_currency(value) is False


# ============================================================================
# PROPERTY TESTS - is_valid_date
# ============================================================================


class TestValidDateGuard:
    """Test is_valid_date() type guard properties."""

    @given(
        year=st.integers(min_value=1900, max_value=2100),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
    )
    @settings(max_examples=200)
    def test_valid_date_returns_true(self, year: int, month: int, day: int) -> None:
        """PROPERTY: Valid date objects return True."""
        value = date(year, month, day)
        assert is_valid_date(value) is True

    @given(value=st.none())
    @settings(max_examples=50)
    def test_none_returns_false(self, value: None) -> None:
        """PROPERTY: None returns False."""
        assert is_valid_date(value) is False


# ============================================================================
# PROPERTY TESTS - is_valid_datetime
# ============================================================================


class TestValidDatetimeGuard:
    """Test is_valid_datetime() type guard properties."""

    @given(
        year=st.integers(min_value=1900, max_value=2100),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    @settings(max_examples=200)
    def test_valid_datetime_returns_true(
        self, year: int, month: int, day: int, hour: int, minute: int
    ) -> None:
        """PROPERTY: Valid datetime objects return True."""
        value = datetime(year, month, day, hour, minute, tzinfo=UTC)
        assert is_valid_datetime(value) is True

    @given(value=st.none())
    @settings(max_examples=50)
    def test_none_returns_false(self, value: None) -> None:
        """PROPERTY: None returns False."""
        assert is_valid_datetime(value) is False


# ============================================================================
# PROPERTY TESTS - TYPE NARROWING INTEGRATION
# ============================================================================


class TestTypeNarrowingIntegration:
    """Test type guard integration with actual parsing functions.

    Tests updated for tuple return type API.
    """

    @given(
        amount=st.decimals(
            min_value=Decimal("0.01"), max_value=Decimal("9999.99"), places=2
        ),
        currency=st.from_regex(r"[A-Z]{3}", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_currency_type_narrowing(self, amount: Decimal, currency: str) -> None:
        """PROPERTY: Type guard correctly narrows currency result type."""
        from ftllexengine.parsing import parse_currency

        currency_str = f"{currency} {amount}"
        result, errors = parse_currency(currency_str, "en_US")

        if not errors and is_valid_currency(result):
            # After type narrowing, mypy knows result is tuple[Decimal, str]
            parsed_amount, parsed_currency = result
            assert isinstance(parsed_amount, Decimal)
            assert isinstance(parsed_currency, str)
            assert parsed_amount.is_finite()

    @given(
        year=st.integers(min_value=2000, max_value=2068),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
    )
    @settings(max_examples=100)
    def test_date_type_narrowing(self, year: int, month: int, day: int) -> None:
        """PROPERTY: Type guard correctly narrows date result type."""
        from ftllexengine.parsing import parse_date

        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        result, errors = parse_date(date_str, "en_US")

        if not errors and is_valid_date(result):
            # After type narrowing, mypy knows result is date
            assert isinstance(result, date)
            assert result.year == year

    @given(
        year=st.integers(min_value=2000, max_value=2068),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    @settings(max_examples=100)
    def test_datetime_type_narrowing(
        self, year: int, month: int, day: int, hour: int, minute: int
    ) -> None:
        """PROPERTY: Type guard correctly narrows datetime result type."""
        from ftllexengine.parsing import parse_datetime

        datetime_str = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00"
        result, errors = parse_datetime(datetime_str, "en_US")

        if not errors and is_valid_datetime(result):
            # After type narrowing, mypy knows result is datetime
            assert isinstance(result, datetime)
            assert result.year == year

    @given(
        value=st.floats(
            min_value=-999999.99,
            max_value=999999.99,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=100)
    def test_number_type_narrowing(self, value: float) -> None:
        """PROPERTY: Type guard correctly narrows number result type."""
        from ftllexengine.parsing import parse_number
        from ftllexengine.runtime.functions import number_format

        formatted = number_format(value, "en_US")
        result, errors = parse_number(str(formatted), "en_US")

        if not errors and result is not None and is_valid_number(result):
            # After type narrowing, mypy knows result is float
            assert isinstance(result, float)

    @given(
        value=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("999999.99"),
            places=2,
        ),
    )
    @settings(max_examples=100)
    def test_decimal_type_narrowing(self, value: Decimal) -> None:
        """PROPERTY: Type guard correctly narrows decimal result type."""
        from ftllexengine.parsing import parse_decimal
        from ftllexengine.runtime.functions import number_format

        formatted = number_format(float(value), "en_US", minimum_fraction_digits=2)
        result, errors = parse_decimal(str(formatted), "en_US")

        if not errors and result is not None and is_valid_decimal(result):
            # After type narrowing, mypy knows result is Decimal
            assert isinstance(result, Decimal)
            assert result.is_finite()
