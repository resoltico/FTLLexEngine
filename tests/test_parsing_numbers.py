"""Tests for number parsing functions.

Functions return tuple[value, errors]:
- parse_decimal() returns tuple[Decimal | None, tuple[FluentParseError, ...]]
- Functions never raise exceptions; errors returned in tuple

Validates parse_decimal() across multiple locales and roundtrip correctness.
"""

from decimal import Decimal

from ftllexengine.parsing import parse_decimal, parse_fluent_number
from ftllexengine.runtime import make_fluent_number


class TestParseDecimal:
    """Test parse_decimal() function."""

    def test_parse_decimal_en_us(self) -> None:
        """Parse US English decimal format."""
        result, errors = parse_decimal("1,234.56", "en_US")
        assert not errors
        assert result == Decimal("1234.56")

        result, errors = parse_decimal("0.01", "en_US")
        assert not errors
        assert result == Decimal("0.01")

    def test_parse_decimal_lv_lv(self) -> None:
        """Parse Latvian decimal format."""
        result, errors = parse_decimal("1 234,56", "lv_LV")
        assert not errors
        assert result == Decimal("1234.56")

        result, errors = parse_decimal("0,01", "lv_LV")
        assert not errors
        assert result == Decimal("0.01")

    def test_parse_decimal_de_de(self) -> None:
        """Parse German decimal format."""
        result, errors = parse_decimal("1.234,56", "de_DE")
        assert not errors
        assert result == Decimal("1234.56")

        result, errors = parse_decimal("0,01", "de_DE")
        assert not errors
        assert result == Decimal("0.01")

    def test_parse_decimal_financial_precision(self) -> None:
        """Decimal preserves financial precision."""
        amount, errors = parse_decimal("100,50", "lv_LV")
        assert not errors
        assert amount is not None
        vat = amount * Decimal("0.21")
        assert vat == Decimal("21.105")  # Exact, no float precision loss

    def test_parse_decimal_rejects_invalid_grouping(self) -> None:
        """Misplaced group separators return error; Babel must not silently strip them.

        Regression: "1,2,3" for en_US previously returned Decimal('123') because
        Babel strips group separators without validating their positions.
        """
        result, errors = parse_decimal("1,2,3", "en_US")
        assert result is None
        assert len(errors) == 1

        # Valid grouping must still succeed.
        result, errors = parse_decimal("1,234", "en_US")
        assert not errors
        assert result == Decimal(1234)

        result, errors = parse_decimal("1,234,567", "en_US")
        assert not errors
        assert result == Decimal(1234567)

        # German: '.' is the group separator; "1.2.3" must also be rejected.
        result, errors = parse_decimal("1.2.3", "de_DE")
        assert result is None
        assert len(errors) == 1

    def test_parse_decimal_rejects_non_bcp47_locale_characters(self) -> None:
        """Locale codes containing non-BCP-47 characters return error, never a result.

        Regression: Babel silently accepts locale codes like "invalid_II/II"
        (containing '/') without raising UnknownLocaleError, then uses default
        number format settings, causing valid-looking values to parse successfully.
        """
        # '/' is not a valid BCP-47 character; must not silently parse "123.45"
        result, errors = parse_decimal("123.45", "invalid_II/II")
        assert result is None
        assert len(errors) == 1

        # Null bytes and other non-ASCII in locale codes must also be rejected.
        result, errors = parse_decimal("123.45", "en\x00US")
        assert result is None
        assert len(errors) == 1

        # Standard valid locale must still work.
        result, errors = parse_decimal("123.45", "en_US")
        assert result == Decimal("123.45")
        assert not errors

    def test_parse_decimal_invalid_returns_error(self) -> None:
        """Invalid input returns error in tuple; function never raises."""
        result, errors = parse_decimal("invalid", "en_US")
        assert len(errors) > 0
        assert result is None
        assert errors[0].parse_type == "decimal"

    def test_parse_decimal_empty_returns_error(self) -> None:
        """Empty input returns error in tuple."""
        result, errors = parse_decimal("", "en_US")
        assert len(errors) > 0
        assert result is None


class TestParseFluentNumber:
    """Test parse_fluent_number() composition and precision behavior."""

    def test_parse_fluent_number_matches_public_composition(self) -> None:
        """parse_fluent_number matches parse_decimal() + make_fluent_number()."""
        parsed_decimal, decimal_errors = parse_decimal("1 234,5600", "lv_LV")
        parsed_fluent, fluent_errors = parse_fluent_number("1 234,5600", "lv_LV")

        assert not decimal_errors
        assert not fluent_errors
        assert parsed_decimal is not None
        assert parsed_fluent == make_fluent_number(parsed_decimal, formatted="1 234,5600")

    def test_parse_fluent_number_preserves_display_text_and_precision(self) -> None:
        """parse_fluent_number preserves the localized string and visible precision."""
        result, errors = parse_fluent_number("1,234.50", "en_US")

        assert not errors
        assert result is not None
        assert result.value == Decimal("1234.50")
        assert str(result) == "1,234.50"
        assert result.precision == 2

    def test_parse_fluent_number_invalid_returns_error(self) -> None:
        """Invalid localized numbers return the same soft-error contract."""
        result, errors = parse_fluent_number("invalid", "en_US")

        assert result is None
        assert len(errors) == 1
        assert errors[0].parse_type == "decimal"


class TestRoundtrip:
    """Test format -> parse -> format roundtrip preservation."""

    def test_roundtrip_decimal_en_us(self) -> None:
        """Decimal roundtrip for US English."""
        from ftllexengine.runtime.functions import number_format

        original = Decimal("1234.5")
        formatted = number_format(original, "en-US", use_grouping=True)
        parsed, errors = parse_decimal(str(formatted), "en_US")
        assert not errors
        assert parsed == original

    def test_roundtrip_decimal_lv_lv(self) -> None:
        """Decimal roundtrip for Latvian."""
        from ftllexengine.runtime.functions import number_format

        original = Decimal("1234.5")
        formatted = number_format(original, "lv-LV", use_grouping=True)
        parsed, errors = parse_decimal(str(formatted), "lv_LV")
        assert not errors
        assert parsed == original

    def test_roundtrip_decimal_precision(self) -> None:
        """Decimal roundtrip preserves financial precision."""
        from ftllexengine.runtime.functions import number_format

        original = Decimal("1234.56")
        formatted = number_format(
            original, "lv-LV", minimum_fraction_digits=2, use_grouping=True
        )
        parsed, errors = parse_decimal(str(formatted), "lv_LV")
        assert not errors
        assert parsed == original
