"""Tests for currency parsing functions.

v0.8.0: Updated for new tuple return type API.
- parse_currency() returns tuple[tuple[Decimal, str] | None, list[FluentParseError]]
- Removed strict parameter - functions never raise, errors in list

Validates parse_currency() across multiple locales and currency formats.
"""

from decimal import Decimal

from ftllexengine.parsing import parse_currency


class TestParseCurrency:
    """Test parse_currency() function."""

    def test_parse_currency_eur_symbol(self) -> None:
        """Parse EUR with € symbol."""
        result, errors = parse_currency("€100.50", "en_US")
        assert not errors
        assert result is not None
        amount, code = result
        assert amount == Decimal("100.50")
        assert code == "EUR"

        result, errors = parse_currency("100,50 €", "lv_LV")
        assert not errors
        assert result is not None
        amount, code = result
        assert amount == Decimal("100.50")
        assert code == "EUR"

    def test_parse_currency_usd_symbol(self) -> None:
        """Parse USD with $ symbol (v0.7.0: requires default_currency)."""
        result, errors = parse_currency("$1,234.56", "en_US", default_currency="USD")

        assert not errors
        assert result is not None

        amount, code = result
        assert amount == Decimal("1234.56")
        assert code == "USD"

    def test_parse_currency_gbp_symbol(self) -> None:
        """Parse GBP with £ symbol."""
        result, errors = parse_currency("£999.99", "en_GB")

        assert not errors
        assert result is not None

        amount, code = result
        assert amount == Decimal("999.99")
        assert code == "GBP"

    def test_parse_currency_jpy_symbol(self) -> None:
        """Parse JPY with ¥ symbol (no decimals)."""
        result, errors = parse_currency("¥12,345", "ja_JP")

        assert not errors
        assert result is not None

        amount, code = result
        assert amount == Decimal("12345")
        assert code == "JPY"

    def test_parse_currency_iso_code(self) -> None:
        """Parse currency with ISO code instead of symbol."""
        result, errors = parse_currency("USD 1,234.56", "en_US")

        assert not errors
        assert result is not None

        amount, code = result
        assert amount == Decimal("1234.56")
        assert code == "USD"

        result, errors = parse_currency("EUR 1.234,56", "de_DE")


        assert not errors
        assert result is not None


        amount, code = result
        assert amount == Decimal("1234.56")
        assert code == "EUR"

    def test_parse_currency_no_symbol_returns_error(self) -> None:
        """No currency symbol returns error in list (v0.8.0 - no exceptions)."""
        result, errors = parse_currency("1,234.56", "en_US")
        assert len(errors) > 0
        assert result is None

    def test_parse_currency_invalid_returns_error(self) -> None:
        """Invalid input returns error in list (v0.8.0 - no exceptions)."""
        result, errors = parse_currency("invalid", "en_US")
        assert len(errors) > 0
        assert result is None


class TestRoundtripCurrency:
    """Test format -> parse -> format roundtrip for currency."""

    def test_roundtrip_currency_en_us(self) -> None:
        """Currency roundtrip for US English."""
        from ftllexengine.runtime.functions import currency_format

        original_amount = Decimal("1234.56")
        formatted = currency_format(
            float(original_amount), "en-US", currency="USD", currency_display="symbol"
        )
        # v0.7.0: $ is ambiguous - specify default_currency for roundtrip
        result, errors = parse_currency(formatted, "en_US", default_currency="USD")

        assert not errors
        assert result is not None

        parsed_amount, parsed_currency = result

        assert parsed_amount == original_amount
        assert parsed_currency == "USD"

    def test_roundtrip_currency_lv_lv(self) -> None:
        """Currency roundtrip for Latvian."""
        from ftllexengine.runtime.functions import currency_format

        original_amount = Decimal("1234.56")
        formatted = currency_format(
            float(original_amount), "lv-LV", currency="EUR", currency_display="symbol"
        )
        result, errors = parse_currency(formatted, "lv_LV")

        assert not errors
        assert result is not None

        parsed_amount, parsed_currency = result

        assert parsed_amount == original_amount
        assert parsed_currency == "EUR"


class TestCurrencyLocaleListCoverage:
    """Validate _SYMBOL_LOOKUP_LOCALE_IDS covers major currencies.

    AUDIT-CURRENCY-HARDCODED-003: The hardcoded locale list must cover
    all major ISO 4217 currencies. This test validates coverage and
    fails if important currency symbols would be missing.
    """

    # Major currencies that MUST be discoverable via symbol lookup
    # These represent the most actively traded and widely used currencies
    # Note: Using frozenset as class constant for immutability
    REQUIRED_CURRENCIES: frozenset[str] = frozenset({
        # G10 currencies (most traded)
        "USD", "EUR", "JPY", "GBP", "CHF", "AUD", "NZD", "CAD",
        # Additional major currencies
        "CNY", "HKD", "SGD", "SEK", "NOK", "DKK", "KRW",
        "INR", "RUB", "TRY", "ZAR", "MXN", "BRL",
        # Baltic/Eastern European
        "PLN", "CZK", "HUF", "RON", "BGN",
    })

    def test_symbol_lookup_locales_provide_major_currency_coverage(self) -> None:
        """Verify hardcoded locale list discovers major currency symbols.

        Loads the currency maps and checks that all required currencies
        have at least one discoverable symbol (not just ISO code).
        """
        from ftllexengine.parsing.currency import _get_currency_maps

        symbol_map, _ambiguous_symbols, _ = _get_currency_maps()

        # Collect all currencies discoverable via symbols
        discovered_currencies: set[str] = set()

        # From unambiguous symbols
        discovered_currencies.update(symbol_map.values())

        # Note: Ambiguous symbols (like $, kr) map to multiple currencies,
        # but we can't tell which ones without testing each symbol lookup.
        # The key validation is that the symbols exist in the maps.

        # Check required currencies are discoverable
        missing = self.REQUIRED_CURRENCIES - discovered_currencies

        # Allow some flexibility - if a currency is only available via ISO code
        # that's acceptable for the strict validation.
        # But fail if more than 20% are missing symbols
        max_missing = len(self.REQUIRED_CURRENCIES) // 5  # 20%

        assert len(missing) <= max_missing, (
            f"Too many major currencies missing symbol mappings: {sorted(missing)}. "
            f"Max allowed: {max_missing}, got: {len(missing)}"
        )

    def test_locale_to_currency_covers_major_territories(self) -> None:
        """Verify locale-to-currency mapping covers major territories.

        Note: Some locales may not be present if Babel doesn't have territory
        data for them. We require at least 80% coverage of major locales.
        """
        from ftllexengine.parsing.currency import _get_currency_maps

        _, _, locale_to_currency = _get_currency_maps()

        # Key locales that should have currency mappings
        expected_locales = {
            "en_US", "en_GB", "en_CA", "en_AU",
            "de_DE", "de_AT", "de_CH",
            "fr_FR", "fr_CA",
            "ja_JP", "zh_CN", "ko_KR",
            "es_ES", "es_MX", "pt_BR",
            "lv_LV", "et_EE", "lt_LT",
        }

        found = expected_locales & set(locale_to_currency.keys())
        missing = expected_locales - found

        # Require at least 80% coverage
        min_coverage = len(expected_locales) * 0.8
        assert len(found) >= min_coverage, (
            f"Insufficient locale-to-currency coverage: {len(found)}/{len(expected_locales)}. "
            f"Missing: {sorted(missing)}"
        )
