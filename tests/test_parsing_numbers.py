"""Tests for number parsing functions.

v0.8.0: Updated for new tuple return type API.
- parse_number() returns tuple[float, list[FluentParseError]]
- parse_decimal() returns tuple[Decimal, list[FluentParseError]]
- Removed strict parameter - functions never raise, errors in list

Validates parse_number() and parse_decimal() across multiple locales.
"""

from decimal import Decimal

from ftllexengine.parsing import parse_decimal, parse_number


class TestParseNumber:
    """Test parse_number() function."""

    def test_parse_number_en_us(self) -> None:
        """Parse US English number format."""
        result, errors = parse_number("1,234.5", "en_US")
        assert not errors
        assert result == 1234.5

        result, errors = parse_number("1234.5", "en_US")
        assert not errors
        assert result == 1234.5

        result, errors = parse_number("0.5", "en_US")
        assert not errors
        assert result == 0.5

    def test_parse_number_lv_lv(self) -> None:
        """Parse Latvian number format."""
        result, errors = parse_number("1 234,5", "lv_LV")
        assert not errors
        assert result == 1234.5

        result, errors = parse_number("1234,5", "lv_LV")
        assert not errors
        assert result == 1234.5

        result, errors = parse_number("0,5", "lv_LV")
        assert not errors
        assert result == 0.5

    def test_parse_number_de_de(self) -> None:
        """Parse German number format."""
        result, errors = parse_number("1.234,5", "de_DE")
        assert not errors
        assert result == 1234.5

        result, errors = parse_number("1234,5", "de_DE")
        assert not errors
        assert result == 1234.5

        result, errors = parse_number("0,5", "de_DE")
        assert not errors
        assert result == 0.5

    def test_parse_number_invalid_returns_error(self) -> None:
        """Invalid input returns error in list (v0.8.0 - no exceptions)."""
        result, errors = parse_number("invalid", "en_US")
        assert len(errors) > 0
        assert result is None  # v0.9.0: Returns None on failure
        assert errors[0].parse_type == "number"
        assert errors[0].input_value == "invalid"

    def test_parse_number_empty_returns_error(self) -> None:
        """Empty input returns error in list."""
        result, errors = parse_number("", "en_US")
        assert len(errors) > 0
        assert result is None  # v0.9.0: Returns None on failure


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

    def test_parse_decimal_invalid_returns_error(self) -> None:
        """Invalid input returns error in list (v0.8.0 - no exceptions)."""
        result, errors = parse_decimal("invalid", "en_US")
        assert len(errors) > 0
        assert result is None  # v0.9.0: Returns None on failure
        assert errors[0].parse_type == "decimal"


class TestRoundtrip:
    """Test format -> parse -> format roundtrip preservation."""

    def test_roundtrip_number_en_us(self) -> None:
        """Number roundtrip for US English."""
        from ftllexengine.runtime.functions import number_format

        original = 1234.5
        formatted = number_format(original, "en-US", use_grouping=True)
        parsed, errors = parse_number(str(formatted), "en_US")
        assert not errors
        assert parsed == original

    def test_roundtrip_number_lv_lv(self) -> None:
        """Number roundtrip for Latvian."""
        from ftllexengine.runtime.functions import number_format

        original = 1234.5
        formatted = number_format(original, "lv-LV", use_grouping=True)
        parsed, errors = parse_number(str(formatted), "lv_LV")
        assert not errors
        assert parsed == original

    def test_roundtrip_decimal_precision(self) -> None:
        """Decimal roundtrip preserves financial precision."""
        from ftllexengine.runtime.functions import number_format

        original = Decimal("1234.56")
        formatted = number_format(
            float(original), "lv-LV", minimum_fraction_digits=2, use_grouping=True
        )
        parsed, errors = parse_decimal(str(formatted), "lv_LV")
        assert not errors
        assert parsed == original
