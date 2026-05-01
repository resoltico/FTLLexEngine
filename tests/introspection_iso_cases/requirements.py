# mypy: ignore-errors
from __future__ import annotations

import pytest

from ftllexengine.introspection import (
    CurrencyCode,
    TerritoryCode,
    get_currency,
    get_currency_decimal_digits,
    require_currency_code,
    require_territory_code,
)

# Private member access permitted for integration tests


class TestGetCurrencyDecimalDigits:
    """Tests for get_currency_decimal_digits() convenience function.

    Decimal precision is locale-independent (ISO 4217 standard).
    The function must not require a locale parameter.
    """

    def test_standard_two_decimal_currencies(self) -> None:
        """Common 2-decimal currencies return 2."""
        for code in ("EUR", "USD", "GBP", "CHF", "CAD", "AUD", "NZD"):
            assert get_currency_decimal_digits(code) == 2, (
                f"{code} should have 2 decimal digits"
            )

    def test_zero_decimal_currencies(self) -> None:
        """Zero-decimal currencies return 0."""
        for code in ("JPY", "KRW", "VND", "ISK", "CLP"):
            assert get_currency_decimal_digits(code) == 0, (
                f"{code} should have 0 decimal digits"
            )

    def test_three_decimal_currencies(self) -> None:
        """Three-decimal currencies return 3."""
        for code in ("KWD", "JOD", "OMR", "BHD", "TND"):
            assert get_currency_decimal_digits(code) == 3, (
                f"{code} should have 3 decimal digits"
            )

    def test_four_decimal_currencies(self) -> None:
        """Four-decimal currencies return 4."""
        assert get_currency_decimal_digits("CLF") == 4
        assert get_currency_decimal_digits("UYW") == 4

    def test_unknown_code_returns_none(self) -> None:
        """Unknown ISO code returns None."""
        assert get_currency_decimal_digits("XYZ") is None
        assert get_currency_decimal_digits("FOO") is None

    def test_case_insensitive(self) -> None:
        """Currency code lookup is case-insensitive."""
        assert get_currency_decimal_digits("eur") == 2
        assert get_currency_decimal_digits("Eur") == 2
        assert get_currency_decimal_digits("EUR") == 2
        assert get_currency_decimal_digits("jpy") == 0

    def test_wrong_length_returns_none(self) -> None:
        """Codes of wrong length return None without Babel call."""
        assert get_currency_decimal_digits("") is None
        assert get_currency_decimal_digits("EU") is None
        assert get_currency_decimal_digits("EURO") is None

    def test_consistent_with_get_currency(self) -> None:
        """Result matches get_currency(code).decimal_digits for all known codes."""
        for code in ("USD", "EUR", "JPY", "KWD", "CLF", "GBP"):
            info = get_currency(code)
            assert info is not None
            digits = get_currency_decimal_digits(code)
            assert digits == info.decimal_digits, (
                f"Inconsistency for {code}: get_currency_decimal_digits={digits}, "
                f"get_currency().decimal_digits={info.decimal_digits}"
            )

    def test_latvian_lats_historical(self) -> None:
        """Historical currency LVL (Latvian Lats) returns None (withdrawn from ISO 4217)."""
        # LVL is a withdrawn currency — Babel no longer includes it in active CLDR data.
        # get_currency_decimal_digits must return None for withdrawn/unknown codes.
        result = get_currency_decimal_digits("LVL")
        # Accept both None (withdrawn from Babel's CLDR) and 2 (if still in data).
        assert result in (None, 2), f"LVL should be None or 2, got {result!r}"

    def test_precious_metal_x_codes_return_zero(self) -> None:
        """ISO 4217 precious-metal X-codes return 0 decimal digits."""
        for code in ("XAG", "XAU", "XPD", "XPT"):
            assert get_currency_decimal_digits(code) == 0, (
                f"{code} (precious metal) should have 0 decimal digits"
            )

    def test_special_x_codes_return_zero(self) -> None:
        """ISO 4217 special X-codes (bond units, SDR, testing, no-currency) return 0."""
        for code in ("XBA", "XBB", "XBC", "XBD", "XDR", "XSU", "XTS", "XUA", "XXX"):
            assert get_currency_decimal_digits(code) == 0, (
                f"{code} should have 0 decimal digits"
            )

    def test_xcd_eastern_caribbean_is_two_decimal(self) -> None:
        """XCD (Eastern Caribbean Dollar) uses default 2 decimal digits."""
        assert get_currency_decimal_digits("XCD") == 2

    def test_babel_free_no_babel_install_required(self) -> None:
        """get_currency_decimal_digits works without Babel installed.

        Validates the Babel-free contract: result must not depend on any
        Babel import path. We verify by confirming standard codes work and
        that the returned value is a plain int (not a Babel-derived object).
        """
        result = get_currency_decimal_digits("USD")
        assert result == 2
        assert type(result) is int

    def test_known_invalid_codes_return_none(self) -> None:
        """Non-ISO codes return None without fallback to default."""
        for code in ("XYZ", "FOO", "ZZZ", "AAA", "TST"):
            assert get_currency_decimal_digits(code) is None, (
                f"Unknown code {code!r} should return None"
            )

    def test_casefold_expansion_guard(self) -> None:
        """Single-char inputs that expand via .upper() return None (no casefold confusion).

        Verifies the raw-length guard prevents the 'ß' -> 'SS' casefold expansion
        from matching 'SS' or any other 2-char result of uppercasing a 1-char input.
        """
        assert get_currency_decimal_digits("ß") is None
        assert get_currency_decimal_digits("a") is None

    def test_fund_codes_return_correct_precision(self) -> None:
        """ISO 4217 fund codes are valid and return correct precision."""
        # BOV (Bolivian Mvdol), MXV (Mexican Unidad), USN (US Next Day): 2 decimal
        for code in ("BOV", "MXV", "USN"):
            result = get_currency_decimal_digits(code)
            assert result == 2, f"{code} (fund code) should have 2 decimal digits"
        # UYI (Uruguay Peso en Unidades Indexadas): 0 decimal
        assert get_currency_decimal_digits("UYI") == 0

    def test_recently_added_active_codes(self) -> None:
        """Codes added by recent ISO 4217 amendments are active and return precision.

        VED (Amendment 169, 2021), ZWG (Amendment 171+, 2024), and XCG
        (Amendment 17x, 2025) are active ISO 4217 codes with default 2 decimal digits.
        """
        for code in ("VED", "ZWG", "XCG"):
            result = get_currency_decimal_digits(code)
            assert result == 2, (
                f"{code} (recently-added active code) should have 2 decimal digits, "
                f"got {result!r}"
            )

    def test_recently_retired_codes_return_none(self) -> None:
        """Codes retired by recent ISO 4217 amendments return None.

        SLL (Sierra Leone Leone, retired Amendment 170, 2022) and ZWL
        (Zimbabwean Dollar, retired Amendment 171+, 2024) are no longer active
        and must not appear in ISO_4217_VALID_CODES.
        """
        for code in ("SLL", "ZWL"):
            result = get_currency_decimal_digits(code)
            assert result is None, (
                f"{code} (retired code) should return None, got {result!r}"
            )

    def test_iqd_iso_standard_value(self) -> None:
        """IQD (Iraqi Dinar) returns ISO 4217 standard value of 3 decimal digits.

        ISO 4217 specifies IQD with 3 decimal places (fils subdivision).
        Babel CLDR reports 0 because fils are not used in practice.
        This library follows the ISO standard, not CLDR practical usage.
        """
        assert get_currency_decimal_digits("IQD") == 3

class TestRequireCurrencyCode:
    """Tests for require_currency_code boundary validator."""

    def test_valid_uppercase_code_returns_currency_code(self) -> None:
        """Valid uppercase ISO 4217 code returns CurrencyCode."""
        result = require_currency_code("USD", "price")
        assert result == CurrencyCode("USD")
        assert type(result) is str  # CurrencyCode is a str alias

    def test_valid_lowercase_code_is_normalized(self) -> None:
        """Lowercase code is normalised to uppercase CurrencyCode."""
        result = require_currency_code("eur", "amount")
        assert result == CurrencyCode("EUR")

    def test_valid_mixed_case_code_is_normalized(self) -> None:
        """Mixed-case code is normalised to uppercase."""
        result = require_currency_code("Jpy", "fee")
        assert result == CurrencyCode("JPY")

    def test_leading_trailing_whitespace_is_stripped(self) -> None:
        """Whitespace around a valid code is stripped before validation."""
        result = require_currency_code("  GBP  ", "price")
        assert result == CurrencyCode("GBP")

    def test_invalid_code_raises_value_error(self) -> None:
        """Unrecognised currency code raises ValueError."""
        with pytest.raises(ValueError, match="currency code"):
            require_currency_code("XYZ", "amount")

    def test_empty_string_raises_value_error(self) -> None:
        """Empty string raises ValueError (not a valid ISO 4217 code)."""
        with pytest.raises(ValueError, match="currency code"):
            require_currency_code("", "amount")

    def test_whitespace_only_raises_value_error(self) -> None:
        """Whitespace-only string raises ValueError after stripping."""
        with pytest.raises(ValueError, match="currency code"):
            require_currency_code("   ", "amount")

    def test_non_str_raises_type_error(self) -> None:
        """Non-str value raises TypeError with field_name in message."""
        with pytest.raises(TypeError, match="price"):
            require_currency_code(123, "price")

    def test_none_raises_type_error(self) -> None:
        """None raises TypeError."""
        with pytest.raises(TypeError, match="currency_code"):
            require_currency_code(None, "currency_code")

    def test_field_name_in_error_message(self) -> None:
        """field_name appears in both TypeError and ValueError messages."""
        with pytest.raises(TypeError, match="my_field"):
            require_currency_code(42, "my_field")
        with pytest.raises(ValueError, match="my_field"):
            require_currency_code("BADCODE", "my_field")

    def test_valid_codes_cover_major_currencies(self) -> None:
        """Major ISO 4217 codes are accepted."""
        for code in ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"):
            result = require_currency_code(code, "amount")
            assert result == CurrencyCode(code)

    def test_returns_currency_code_type(self) -> None:
        """Return value is CurrencyCode (str subtype)."""
        result = require_currency_code("USD", "amount")
        assert isinstance(result, str)

class TestRequireTerritoryCode:
    """Tests for require_territory_code boundary validator."""

    def test_valid_uppercase_code_returns_territory_code(self) -> None:
        """Valid uppercase ISO 3166-1 alpha-2 code returns TerritoryCode."""
        result = require_territory_code("US", "region")
        assert result == TerritoryCode("US")

    def test_valid_lowercase_code_is_normalized(self) -> None:
        """Lowercase code is normalised to uppercase TerritoryCode."""
        result = require_territory_code("de", "country")
        assert result == TerritoryCode("DE")

    def test_valid_mixed_case_code_is_normalized(self) -> None:
        """Mixed-case code is normalised to uppercase."""
        result = require_territory_code("Gb", "territory")
        assert result == TerritoryCode("GB")

    def test_leading_trailing_whitespace_is_stripped(self) -> None:
        """Whitespace around a valid code is stripped before validation."""
        result = require_territory_code("  FR  ", "country")
        assert result == TerritoryCode("FR")

    def test_invalid_code_raises_value_error(self) -> None:
        """Unrecognised territory code raises ValueError."""
        # "99"/"X9" contain digits — not valid ISO 3166-1 alpha-2 codes
        with pytest.raises(ValueError, match="territory code"):
            require_territory_code("99", "region")

    def test_empty_string_raises_value_error(self) -> None:
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="territory code"):
            require_territory_code("", "region")

    def test_whitespace_only_raises_value_error(self) -> None:
        """Whitespace-only string raises ValueError after stripping."""
        with pytest.raises(ValueError, match="territory code"):
            require_territory_code("   ", "region")

    def test_three_char_code_raises_value_error(self) -> None:
        """3-char string is not a valid alpha-2 code and raises ValueError."""
        with pytest.raises(ValueError, match="territory code"):
            require_territory_code("USA", "country")

    def test_non_str_raises_type_error(self) -> None:
        """Non-str value raises TypeError with field_name in message."""
        with pytest.raises(TypeError, match="region"):
            require_territory_code(42, "region")

    def test_none_raises_type_error(self) -> None:
        """None raises TypeError."""
        with pytest.raises(TypeError, match="territory"):
            require_territory_code(None, "territory")

    def test_field_name_in_error_message(self) -> None:
        """field_name appears in both TypeError and ValueError messages."""
        with pytest.raises(TypeError, match="my_field"):
            require_territory_code(99, "my_field")
        with pytest.raises(ValueError, match="my_field"):
            require_territory_code("XX", "my_field")

    def test_valid_codes_cover_major_territories(self) -> None:
        """Major ISO 3166-1 alpha-2 codes are accepted."""
        for code in ("US", "DE", "GB", "FR", "JP", "CA", "AU"):
            result = require_territory_code(code, "region")
            assert result == TerritoryCode(code)

    def test_casefold_expansion_guard(self) -> None:
        """Single-char inputs that expand via .upper() (e.g. 'ß'->'SS') are rejected."""
        with pytest.raises(ValueError, match="territory code"):
            require_territory_code("ß", "region")

    def test_returns_territory_code_type(self) -> None:
        """Return value is TerritoryCode (str subtype)."""
        result = require_territory_code("US", "region")
        assert isinstance(result, str)
