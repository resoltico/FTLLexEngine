# mypy: ignore-errors
# mypy: ignore-errors
from __future__ import annotations

from decimal import Decimal

import pytest
from babel import numbers as babel_numbers

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.locale_context import LocaleContext

# ============================================================================
# Construction Guard Tests
# ============================================================================



class TestFormatNumber:
    """Test format_number() with various locales and parameters."""

    def test_format_number_en_us_grouping(self) -> None:
        """format_number() formats with grouping for en-US."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(Decimal("1234.5"), use_grouping=True)
        assert "1,234" in result or "1234" in result

    def test_format_number_de_de_grouping(self) -> None:
        """format_number() formats with grouping for de-DE."""
        ctx = LocaleContext.create("de-DE")
        result = ctx.format_number(Decimal("1234.5"), use_grouping=True)
        assert "1.234" in result or "1234" in result

    def test_format_number_fixed_decimals(self) -> None:
        """format_number() formats with fixed decimal places."""
        ctx = LocaleContext.create("en-US")

        result = ctx.format_number(
            Decimal("1234.5"),
            minimum_fraction_digits=2,
            maximum_fraction_digits=2,
        )
        assert result == "1,234.50"

        result = ctx.format_number(
            Decimal("1234.567"),
            minimum_fraction_digits=0,
            maximum_fraction_digits=0,
        )
        assert result == "1,235"
        assert "." not in result

    def test_format_number_fixed_three_decimals(self) -> None:
        """format_number() with fixed 3 decimal places."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(
            Decimal("123.4"),
            minimum_fraction_digits=3,
            maximum_fraction_digits=3,
        )
        assert result == "123.400"

    def test_format_number_custom_pattern(self) -> None:
        """format_number() respects custom pattern."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(
            Decimal("-1234.56"), pattern="#,##0.00;(#,##0.00)"
        )
        assert "1,234.56" in result or "1234.56" in result

    def test_format_number_preserves_decimal_precision(
        self,
    ) -> None:
        """format_number() preserves large decimal precision."""
        ctx = LocaleContext.create("en-US")

        large_decimal = Decimal("123456789.123456789")
        result = ctx.format_number(
            large_decimal,
            minimum_fraction_digits=2,
            maximum_fraction_digits=2,
        )

        assert result == "123,456,789.12"
        assert result.count(".") == 1
        decimal_part = result.split(".")[-1]
        assert len(decimal_part) == 2

    def test_format_number_with_decimal_type(self) -> None:
        """format_number() with Decimal type for fixed decimals."""
        ctx = LocaleContext.create("de-DE")

        value = Decimal("1234.5")
        result = ctx.format_number(
            value,
            minimum_fraction_digits=2,
            maximum_fraction_digits=2,
        )

        assert "," in result
        assert result == "1.234,50"

    def test_format_number_error_raises_formatting_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """format_number() raises FrozenFluentError on error."""
        def mock_format_decimal(
            *_args: object, **_kwargs: object
        ) -> None:
            msg = "Mocked format error"
            raise ValueError(msg)

        monkeypatch.setattr(
            babel_numbers,
            "format_decimal",
            mock_format_decimal,
        )

        ctx = LocaleContext.create("en-US")
        with pytest.raises(FrozenFluentError) as exc_info:
            ctx.format_number(Decimal("123.45"))

        assert (
            exc_info.value.category == ErrorCategory.FORMATTING
        )
        assert exc_info.value.fallback_value == "123.45"

class TestFormatNumberDigitValidation:
    """Test format_number() digit parameter validation."""

    def test_minimum_fraction_digits_negative_raises(
        self,
    ) -> None:
        """Raises ValueError for negative minimum."""
        ctx = LocaleContext.create("en-US")
        with pytest.raises(
            ValueError,
            match=r"minimum_fraction_digits must be",
        ):
            ctx.format_number(
                Decimal("123.45"), minimum_fraction_digits=-1
            )

    def test_minimum_fraction_digits_exceeds_max_raises(
        self,
    ) -> None:
        """Raises ValueError when exceeding MAX_FORMAT_DIGITS."""
        from ftllexengine.constants import (
            MAX_FORMAT_DIGITS,
        )

        ctx = LocaleContext.create("en-US")
        with pytest.raises(
            ValueError,
            match=r"minimum_fraction_digits must be",
        ):
            ctx.format_number(
                Decimal("123.45"),
                minimum_fraction_digits=MAX_FORMAT_DIGITS + 1,
            )

    def test_maximum_fraction_digits_negative_raises(
        self,
    ) -> None:
        """Raises ValueError for negative maximum."""
        ctx = LocaleContext.create("en-US")
        with pytest.raises(
            ValueError,
            match=r"maximum_fraction_digits must be",
        ):
            ctx.format_number(
                Decimal("123.45"), maximum_fraction_digits=-1
            )

    def test_maximum_fraction_digits_exceeds_max_raises(
        self,
    ) -> None:
        """Raises ValueError when exceeding MAX_FORMAT_DIGITS."""
        from ftllexengine.constants import (
            MAX_FORMAT_DIGITS,
        )

        ctx = LocaleContext.create("en-US")
        with pytest.raises(
            ValueError,
            match=r"maximum_fraction_digits must be",
        ):
            ctx.format_number(
                Decimal("123.45"),
                maximum_fraction_digits=MAX_FORMAT_DIGITS + 1,
            )

class TestFormatNumberSpecialValues:
    """Test format_number() with special Decimal values."""

    def test_format_number_positive_infinity(self) -> None:
        """format_number() handles positive infinity."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(Decimal("Infinity"))
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_number_negative_infinity(self) -> None:
        """format_number() handles negative infinity."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(Decimal("-Infinity"))
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_number_nan(self) -> None:
        """format_number() handles NaN."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(Decimal("NaN"))
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_number_infinity_with_grouping(self) -> None:
        """format_number() handles infinity with use_grouping."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(
            Decimal("Infinity"), use_grouping=False
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_number_nan_with_custom_pattern(self) -> None:
        """format_number() handles NaN with custom pattern."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(
            Decimal("NaN"), pattern="#,##0.00"
        )
        assert isinstance(result, str)
        assert len(result) > 0
