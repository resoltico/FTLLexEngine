"""Property-based tests for Babel Protocol conformance and coverage.

Tests that actual Babel modules conform to the Protocol definitions in
babel_compat.py. These tests achieve 100% coverage of Protocol method
definitions by exercising them through typed references.

Python 3.13+.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.core.babel_compat import (
    BabelDatesProtocol,
    BabelNumbersProtocol,
    get_babel_dates,
    get_babel_numbers,
)

# ============================================================================
# Strategies for Property-Based Testing
# ============================================================================

# Valid locale codes for testing
_LOCALE_CODES = st.sampled_from(
    [
        "en_US",
        "de_DE",
        "fr_FR",
        "es_ES",
        "ja_JP",
        "ar_SA",
        "ru_RU",
        "zh_CN",
    ]
)

# Number values for formatting tests
_NUMBER_VALUES = st.one_of(
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.floats(
        min_value=-1_000_000.0,
        max_value=1_000_000.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    st.builds(
        Decimal,
        st.decimals(
            min_value=Decimal("-1000000"),
            max_value=Decimal("1000000"),
            allow_nan=False,
            allow_infinity=False,
            places=2,
        ),
    ),
)

# Currency codes (ISO 4217)
_CURRENCY_CODES = st.sampled_from(
    ["USD", "EUR", "GBP", "JPY", "CNY", "RUB", "BRL", "INR", "CAD", "AUD"]
)

# Date/time format patterns
_DATE_FORMATS = st.sampled_from(["short", "medium", "long", "full"])


# ============================================================================
# BabelNumbersProtocol Tests
# ============================================================================


class TestBabelNumbersProtocolConformance:
    """Test that babel.numbers module conforms to BabelNumbersProtocol.

    These tests achieve coverage of Protocol method definitions by calling
    real Babel functions through Protocol-typed variables.
    """

    @given(
        number=_NUMBER_VALUES,
        locale=_LOCALE_CODES,
    )
    @example(number=1234.56, locale="en_US")
    @example(number=Decimal("1234.56"), locale="de_DE")
    @example(number=1000000, locale="fr_FR")
    def test_format_decimal_conformance(
        self,
        number: int | float | Decimal,
        locale: str,
    ) -> None:
        """BabelNumbersProtocol.format_decimal conforms to actual babel.numbers.

        Property: format_decimal returns a string for all valid inputs.
        Coverage: Exercises BabelNumbersProtocol.format_decimal (line 55-62).
        """
        num_type = type(number).__name__
        event(f"number_type={num_type}")
        event(f"locale={locale}")

        numbers: BabelNumbersProtocol = get_babel_numbers()
        result = numbers.format_decimal(number, locale=locale)

        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        number=_NUMBER_VALUES,
        currency=_CURRENCY_CODES,
        locale=_LOCALE_CODES,
    )
    @example(number=1234.56, currency="USD", locale="en_US")
    @example(number=Decimal("99.99"), currency="EUR", locale="de_DE")
    @example(number=1000000, currency="JPY", locale="ja_JP")
    def test_format_currency_conformance(
        self,
        number: int | float | Decimal,
        currency: str,
        locale: str,
    ) -> None:
        """BabelNumbersProtocol.format_currency conforms to actual babel.numbers.

        Property: format_currency returns a string for all valid inputs.
        Coverage: Exercises BabelNumbersProtocol.format_currency (line 64-74).
        """
        num_type = type(number).__name__
        event(f"number_type={num_type}")
        event(f"currency={currency}")
        event(f"locale={locale}")

        numbers: BabelNumbersProtocol = get_babel_numbers()
        result = numbers.format_currency(number, currency, locale=locale)

        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        number=st.floats(
            min_value=-1.0,
            max_value=1.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        locale=_LOCALE_CODES,
    )
    @example(number=0.1234, locale="en_US")
    @example(number=Decimal("0.5"), locale="de_DE")
    @example(number=1.0, locale="fr_FR")
    def test_format_percent_conformance(
        self,
        number: float | Decimal,
        locale: str,
    ) -> None:
        """BabelNumbersProtocol.format_percent conforms to actual babel.numbers.

        Property: format_percent returns a string for all valid inputs.
        Coverage: Exercises BabelNumbersProtocol.format_percent (line 76-83).
        """
        num_type = type(number).__name__
        event(f"number_type={num_type}")
        event(f"locale={locale}")

        numbers: BabelNumbersProtocol = get_babel_numbers()
        result = numbers.format_percent(number, locale=locale)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_currency_with_format_type(self) -> None:
        """BabelNumbersProtocol.format_currency supports format_type parameter.

        Coverage: Exercises format_type parameter (line 71).
        """
        numbers: BabelNumbersProtocol = get_babel_numbers()

        # Test standard format (default)
        result_standard = numbers.format_currency(
            100.0, "USD", locale="en_US", format_type="standard"
        )
        assert isinstance(result_standard, str)

        # Test accounting format
        result_accounting = numbers.format_currency(
            -100.0, "USD", locale="en_US", format_type="accounting"
        )
        assert isinstance(result_accounting, str)

        # Test name format
        result_name = numbers.format_currency(
            100.0, "USD", locale="en_US", format_type="name"
        )
        assert isinstance(result_name, str)

    def test_format_currency_with_currency_digits(self) -> None:
        """BabelNumbersProtocol.format_currency supports currency_digits parameter.

        Coverage: Exercises currency_digits parameter (line 70).
        """
        numbers: BabelNumbersProtocol = get_babel_numbers()

        # Test with currency_digits=True (default)
        result_with_digits = numbers.format_currency(
            100.0, "USD", locale="en_US", currency_digits=True
        )
        assert isinstance(result_with_digits, str)

        # Test with currency_digits=False
        result_without_digits = numbers.format_currency(
            100.0, "USD", locale="en_US", currency_digits=False
        )
        assert isinstance(result_without_digits, str)


# ============================================================================
# BabelDatesProtocol Tests
# ============================================================================


class TestBabelDatesProtocolConformance:
    """Test that babel.dates module conforms to BabelDatesProtocol.

    These tests achieve coverage of Protocol method definitions by calling
    real Babel functions through Protocol-typed variables.
    """

    @given(
        format_pattern=_DATE_FORMATS,
        locale=_LOCALE_CODES,
    )
    @example(format_pattern="medium", locale="en_US")
    @example(format_pattern="short", locale="de_DE")
    @example(format_pattern="full", locale="ja_JP")
    def test_format_datetime_conformance(
        self,
        format_pattern: str,
        locale: str,
    ) -> None:
        """BabelDatesProtocol.format_datetime conforms to actual babel.dates.

        Property: format_datetime returns a string for all valid inputs.
        Coverage: Exercises BabelDatesProtocol.format_datetime (line 93-101).
        """
        event(f"format={format_pattern}")
        event(f"locale={locale}")

        dates_module: BabelDatesProtocol = get_babel_dates()
        test_datetime = datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)

        result = dates_module.format_datetime(
            test_datetime, format=format_pattern, locale=locale
        )

        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        format_pattern=_DATE_FORMATS,
        locale=_LOCALE_CODES,
    )
    @example(format_pattern="medium", locale="en_US")
    @example(format_pattern="short", locale="de_DE")
    @example(format_pattern="full", locale="ja_JP")
    def test_format_date_conformance(
        self,
        format_pattern: str,
        locale: str,
    ) -> None:
        """BabelDatesProtocol.format_date conforms to actual babel.dates.

        Property: format_date returns a string for all valid inputs.
        Coverage: Exercises BabelDatesProtocol.format_date (line 103-110).
        """
        event(f"format={format_pattern}")
        event(f"locale={locale}")

        dates_module: BabelDatesProtocol = get_babel_dates()
        test_date = date(2024, 1, 15)

        result = dates_module.format_date(
            test_date, format=format_pattern, locale=locale
        )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_date_accepts_datetime(self) -> None:
        """BabelDatesProtocol.format_date accepts datetime objects.

        Coverage: Exercises date | datetime union type (line 105).
        """
        dates_module: BabelDatesProtocol = get_babel_dates()

        # Test with datetime object (not just date)
        test_datetime = datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)
        result = dates_module.format_date(test_datetime, format="medium", locale="en_US")

        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        format_pattern=_DATE_FORMATS,
        locale=_LOCALE_CODES,
    )
    @example(format_pattern="medium", locale="en_US")
    @example(format_pattern="short", locale="de_DE")
    @example(format_pattern="full", locale="ja_JP")
    def test_format_time_conformance(
        self,
        format_pattern: str,
        locale: str,
    ) -> None:
        """BabelDatesProtocol.format_time conforms to actual babel.dates.

        Property: format_time returns a string for all valid inputs.
        Coverage: Exercises BabelDatesProtocol.format_time (line 112-120).
        """
        event(f"format={format_pattern}")
        event(f"locale={locale}")

        dates_module: BabelDatesProtocol = get_babel_dates()
        test_time = datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)

        result = dates_module.format_time(
            test_time, format=format_pattern, locale=locale
        )

        assert isinstance(result, str)
        assert len(result) > 0


# ============================================================================
# Protocol Type Safety Tests
# ============================================================================


class TestProtocolTypeSafety:
    """Test that Protocol definitions provide correct type safety."""

    def test_babel_numbers_protocol_has_all_methods(self) -> None:
        """BabelNumbersProtocol includes all required formatting methods."""
        numbers = get_babel_numbers()

        # Verify all Protocol methods exist
        assert hasattr(numbers, "format_decimal")
        assert hasattr(numbers, "format_currency")
        assert hasattr(numbers, "format_percent")

        # Verify they're callable
        assert callable(numbers.format_decimal)
        assert callable(numbers.format_currency)
        assert callable(numbers.format_percent)

    def test_babel_dates_protocol_has_all_methods(self) -> None:
        """BabelDatesProtocol includes all required formatting methods."""
        dates_module = get_babel_dates()

        # Verify all Protocol methods exist
        assert hasattr(dates_module, "format_datetime")
        assert hasattr(dates_module, "format_date")
        assert hasattr(dates_module, "format_time")

        # Verify they're callable
        assert callable(dates_module.format_datetime)
        assert callable(dates_module.format_date)
        assert callable(dates_module.format_time)

    def test_protocol_return_types_are_strings(self) -> None:
        """All Protocol formatting methods return strings."""
        numbers = get_babel_numbers()
        dates_module = get_babel_dates()

        # Test numbers Protocol
        assert isinstance(numbers.format_decimal(100, locale="en_US"), str)
        assert isinstance(numbers.format_currency(100, "USD", locale="en_US"), str)
        assert isinstance(numbers.format_percent(0.5, locale="en_US"), str)

        # Test dates Protocol
        test_date = date(2024, 1, 15)
        test_datetime = datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)

        assert isinstance(dates_module.format_date(test_date, locale="en_US"), str)
        assert isinstance(
            dates_module.format_datetime(test_datetime, locale="en_US"), str
        )
        assert isinstance(
            dates_module.format_time(test_datetime, locale="en_US"), str
        )


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestProtocolEdgeCases:
    """Test edge cases for Protocol conformance."""

    def test_format_decimal_with_none_format(self) -> None:
        """Protocol allows format=None for format_decimal.

        Coverage: Exercises optional format parameter (line 58).
        """
        numbers: BabelNumbersProtocol = get_babel_numbers()
        result = numbers.format_decimal(1234.5, format=None, locale="en_US")
        assert isinstance(result, str)

    def test_format_decimal_with_none_locale(self) -> None:
        """Protocol allows locale=None for format_decimal.

        Coverage: Exercises optional locale parameter (line 59).
        """
        numbers: BabelNumbersProtocol = get_babel_numbers()
        # Babel uses default locale when None
        result = numbers.format_decimal(1234.5, format=None, locale=None)
        assert isinstance(result, str)

    def test_format_currency_with_none_format(self) -> None:
        """Protocol allows format=None for format_currency.

        Coverage: Exercises optional format parameter (line 68).
        """
        numbers: BabelNumbersProtocol = get_babel_numbers()
        result = numbers.format_currency(100.0, "USD", format=None, locale="en_US")
        assert isinstance(result, str)

    def test_format_percent_with_none_format(self) -> None:
        """Protocol allows format=None for format_percent.

        Coverage: Exercises optional format parameter (line 79).
        """
        numbers: BabelNumbersProtocol = get_babel_numbers()
        result = numbers.format_percent(0.5, format=None, locale="en_US")
        assert isinstance(result, str)

    def test_format_datetime_with_none_tzinfo(self) -> None:
        """Protocol allows tzinfo=None for format_datetime.

        Coverage: Exercises optional tzinfo parameter (line 97).
        """
        dates_module: BabelDatesProtocol = get_babel_dates()
        test_datetime = datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)
        result = dates_module.format_datetime(
            test_datetime, format="medium", tzinfo=None, locale="en_US"
        )
        assert isinstance(result, str)

    def test_format_time_with_none_tzinfo(self) -> None:
        """Protocol allows tzinfo=None for format_time.

        Coverage: Exercises optional tzinfo parameter (line 116).
        """
        dates_module: BabelDatesProtocol = get_babel_dates()
        test_time = datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)
        result = dates_module.format_time(
            test_time, format="medium", tzinfo=None, locale="en_US"
        )
        assert isinstance(result, str)


# ============================================================================
# Regression Tests
# ============================================================================


class TestProtocolRegressions:
    """Regression tests for Protocol-related issues."""

    def test_format_currency_all_format_types(self) -> None:
        """All format_type values work correctly.

        Regression: Ensure all Literal values are valid.
        """
        numbers: BabelNumbersProtocol = get_babel_numbers()

        format_types = ["standard", "accounting", "name"]
        for fmt_type in format_types:
            result = numbers.format_currency(
                100.0,
                "USD",
                locale="en_US",
                format_type=fmt_type,  # type: ignore[arg-type]
            )
            assert isinstance(result, str)

    def test_decimal_type_handling(self) -> None:
        """Decimal type is properly handled by all number formatters.

        Regression: Decimal should work identically to float.
        """
        numbers: BabelNumbersProtocol = get_babel_numbers()

        test_decimal = Decimal("1234.56")

        # All formatters should accept Decimal
        assert isinstance(numbers.format_decimal(test_decimal, locale="en_US"), str)
        assert isinstance(
            numbers.format_currency(test_decimal, "USD", locale="en_US"), str
        )
        assert isinstance(
            numbers.format_percent(Decimal("0.5"), locale="en_US"), str
        )


# ============================================================================
# Protocol Ellipsis Coverage Tests
# ============================================================================


class TestProtocolEllipsisExecution:
    """Direct execution of Protocol methods to achieve coverage of ellipsis statements.

    Protocol method bodies contain ellipsis (...) which are technically executable
    statements. While Protocols cannot be instantiated, their methods can be accessed
    and called directly from the class, causing the ellipsis to evaluate to None.

    This test class achieves coverage of the ellipsis lines (62, 74, 83, 101, 110, 120)
    by directly invoking the Protocol methods.
    """

    def test_babel_numbers_protocol_format_decimal_ellipsis(self) -> None:
        """Execute BabelNumbersProtocol.format_decimal body directly.

        Coverage: Line 62 (ellipsis statement in Protocol method).
        """
        # Access and execute format_decimal method body (line 62)
        result_decimal = BabelNumbersProtocol.format_decimal(
            None,  # type: ignore[arg-type]
            1000,
            format=None,
            locale=None,
        )
        assert result_decimal is None  # Ellipsis evaluates to None

    def test_babel_numbers_protocol_format_currency_ellipsis(self) -> None:
        """Execute BabelNumbersProtocol.format_currency body directly.

        Coverage: Line 74 (ellipsis statement in Protocol method).
        """
        # Access and execute format_currency method body (line 74)
        result_currency = BabelNumbersProtocol.format_currency(
            None,  # type: ignore[arg-type]
            1000,
            "USD",
            format=None,
            locale=None,
            currency_digits=True,
            format_type="standard",
        )
        assert result_currency is None  # Ellipsis evaluates to None

    def test_babel_numbers_protocol_format_percent_ellipsis(self) -> None:
        """Execute BabelNumbersProtocol.format_percent body directly.

        Coverage: Line 83 (ellipsis statement in Protocol method).
        """
        # Access and execute format_percent method body (line 83)
        result_percent = BabelNumbersProtocol.format_percent(
            None,  # type: ignore[arg-type]
            0.5,
            format=None,
            locale=None,
        )
        assert result_percent is None  # Ellipsis evaluates to None

    def test_babel_dates_protocol_format_datetime_ellipsis(self) -> None:
        """Execute BabelDatesProtocol.format_datetime body directly.

        Coverage: Line 101 (ellipsis statement in Protocol method).
        """
        test_datetime = datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)

        # Access and execute format_datetime method body (line 101)
        result_datetime = BabelDatesProtocol.format_datetime(
            None,  # type: ignore[arg-type]
            test_datetime,
            format="medium",
            tzinfo=None,
            locale=None,
        )
        assert result_datetime is None  # Ellipsis evaluates to None

    def test_babel_dates_protocol_format_date_ellipsis(self) -> None:
        """Execute BabelDatesProtocol.format_date body directly.

        Coverage: Line 110 (ellipsis statement in Protocol method).
        """
        test_date = date(2024, 1, 15)

        # Access and execute format_date method body (line 110)
        result_date = BabelDatesProtocol.format_date(
            None,  # type: ignore[arg-type]
            test_date,
            format="medium",
            locale=None,
        )
        assert result_date is None  # Ellipsis evaluates to None

    def test_babel_dates_protocol_format_time_ellipsis(self) -> None:
        """Execute BabelDatesProtocol.format_time body directly.

        Coverage: Line 120 (ellipsis statement in Protocol method).
        """
        test_datetime = datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)

        # Access and execute format_time method body (line 120)
        result_time = BabelDatesProtocol.format_time(
            None,  # type: ignore[arg-type]
            test_datetime,
            format="medium",
            tzinfo=None,
            locale=None,
        )
        assert result_time is None  # Ellipsis evaluates to None
