"""Tests for number parsing functions.

Functions return tuple[value, errors]:
- parse_decimal() returns tuple[Decimal | None, tuple[FluentParseError, ...]]
- Functions never raise exceptions; errors returned in tuple

Validates parse_decimal() across multiple locales and roundtrip correctness.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from ftllexengine.parsing import parse_decimal, parse_fluent_number
from ftllexengine.parsing.numbers import _validate_group_positions
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


class TestValidateGroupPositions:
    """Direct tests for _validate_group_positions branch coverage.

    The helper is private but tested directly via import because the paths
    it guards (separator in decimal part only, non-digit groups, wrong middle
    group size) are not reachable via parse_decimal without crafted inputs
    that bypass the caller's pre-condition checks.
    """

    def test_group_sep_in_decimal_part_only_returns_true(self) -> None:
        """Returns True when group_sep appears only in the decimal part.

        The caller requires group_sep in value, but split on decimal_sep
        isolates an int_part that does not contain group_sep. Validation
        is a no-op: Babel will handle the decimal correctly.
        """
        # decimal_sep="." splits "1234.5,0" → int_part="1234"; "," not in "1234"
        result = _validate_group_positions(
            "1234.5,0",
            group_sep=",",
            decimal_sep=".",
            primary_group=3,
            secondary_group=3,
        )
        assert result is True

    def test_non_digit_groups_returns_true(self) -> None:
        """Returns True when groups contain non-digit characters.

        Babel will reject the value independently; duplicate error reporting
        is avoided by skipping the grouping check.
        """
        # int_part="abc,123"; "abc".isdigit()=False
        result = _validate_group_positions(
            "abc,123",
            group_sep=",",
            decimal_sep=".",
            primary_group=3,
            secondary_group=3,
        )
        assert result is True

    def test_wrong_middle_group_size_returns_false(self) -> None:
        """Returns False when a middle group has the wrong digit count.

        "1,2,345": groups=["1","2","345"]. Rightmost "345" has 3 digits
        (passes primary_group=3). Middle "2" has 1 digit (fails secondary_group=3).
        """
        result = _validate_group_positions(
            "1,2,345",
            group_sep=",",
            decimal_sep=".",
            primary_group=3,
            secondary_group=3,
        )
        assert result is False

    def test_locale_symbol_extraction_failure_uses_defaults(self) -> None:
        """Babel locale symbol access failure falls back to empty group_sep.

        When AttributeError is raised by the locale object's number_symbols
        mapping, the except clause sets group_sep='' so grouping validation
        is skipped entirely.
        """
        mock_locale = MagicMock()
        # Make number_symbols[...] raise AttributeError (malformed CLDR data)
        mock_locale.number_symbols.__getitem__.side_effect = AttributeError(
            "no number_symbols"
        )
        mock_cls = MagicMock()
        mock_cls.parse.return_value = mock_locale

        with patch(
            "ftllexengine.parsing.numbers.get_locale_class", return_value=mock_cls,
        ):
            # With empty group_sep, validation is skipped.
            # babel_parse_decimal may succeed or fail with the mock; function
            # must not propagate an exception either way.
            _result, errors = parse_decimal("1234.56", "en_US")
            assert isinstance(errors, tuple)
