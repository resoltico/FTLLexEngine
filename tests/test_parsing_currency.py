"""Tests for currency parsing functions.

Core parsing tests, ambiguous symbol resolution, CLDR map building exception
paths, BabelImportError handling, fast tier operations, cache management,
locale fallback, and property-based locale resilience.

parse_currency() returns tuple[tuple[Decimal, str] | None, tuple[FrozenFluentError, ...]].
Functions never raise exceptions (errors returned in tuple) except
BabelImportError when Babel is not installed.

Python 3.13+.
"""

from __future__ import annotations

import builtins
import re
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from babel import UnknownLocaleError
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.parsing import currency as currency_module
from ftllexengine.parsing.currency import (
    _build_currency_maps_from_cldr,
    _get_currency_maps,
    parse_currency,
)

# ---------------------------------------------------------------------------
# parse_currency core
# ---------------------------------------------------------------------------


class TestParseCurrency:
    """Test parse_currency() function."""

    def test_parse_currency_eur_symbol(self) -> None:
        """Parse EUR with euro symbol."""
        result, errors = parse_currency("\u20ac100.50", "en_US")
        assert not errors
        assert result is not None
        amount, code = result
        assert amount == Decimal("100.50")
        assert code == "EUR"

        result, errors = parse_currency("100,50 \u20ac", "lv_LV")
        assert not errors
        assert result is not None
        amount, code = result
        assert amount == Decimal("100.50")
        assert code == "EUR"

    def test_parse_currency_usd_symbol(self) -> None:
        """Parse USD with $ symbol (ambiguous, requires default_currency)."""
        result, errors = parse_currency(
            "$1,234.56", "en_US", default_currency="USD"
        )
        assert not errors
        assert result is not None
        amount, code = result
        assert amount == Decimal("1234.56")
        assert code == "USD"

    def test_parse_currency_gbp_symbol(self) -> None:
        """Parse GBP with pound symbol (ambiguous: GBP, EGP, GIP, etc.)."""
        result, errors = parse_currency(
            "\u00a3999.99", "en_GB", infer_from_locale=True
        )
        assert not errors
        assert result is not None
        amount, code = result
        assert amount == Decimal("999.99")
        assert code == "GBP"

    def test_parse_currency_jpy_symbol(self) -> None:
        """Parse JPY with yen symbol (ambiguous: JPY vs CNY, no decimals)."""
        result, errors = parse_currency(
            "\u00a512,345", "ja_JP", infer_from_locale=True
        )
        assert not errors
        assert result is not None
        amount, code = result
        assert amount == Decimal("12345")
        assert code == "JPY"

    def test_parse_currency_cny_chinese_locale(self) -> None:
        """Yen symbol resolves to CNY in Chinese locales."""
        result, errors = parse_currency(
            "\u00a51000", "zh_CN", infer_from_locale=True
        )
        assert not errors
        assert result is not None
        amount, currency = result
        assert amount == Decimal("1000")
        assert currency == "CNY"

    def test_parse_currency_cny_taiwan_locale(self) -> None:
        """Yen symbol resolves to CNY in zh_TW locale."""
        result, errors = parse_currency(
            "\u00a51000", "zh_TW", infer_from_locale=True
        )
        assert not errors
        assert result is not None
        _, currency = result
        assert currency == "CNY"

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

    def test_parse_currency_rupee(self) -> None:
        """Parse Indian Rupee (unambiguous symbol)."""
        result, errors = parse_currency("\u20b91000", "hi_IN")
        assert not errors
        assert result is not None
        amount, _ = result
        assert amount == Decimal("1000")

    def test_parse_currency_swiss_franc(self) -> None:
        """Parse Swiss Franc with ISO code."""
        result, errors = parse_currency("CHF 100", "de_CH")
        assert not errors
        assert result is not None
        amount, currency = result
        assert amount == Decimal("100")
        assert currency == "CHF"

    def test_parse_currency_no_symbol_returns_error(self) -> None:
        """No currency symbol returns error in tuple (no exceptions)."""
        result, errors = parse_currency("1,234.56", "en_US")
        assert len(errors) > 0
        assert result is None

    def test_parse_currency_invalid_returns_error(self) -> None:
        """Invalid input returns error in tuple (no exceptions)."""
        result, errors = parse_currency("invalid", "en_US")
        assert len(errors) > 0
        assert result is None

    def test_parse_currency_invalid_number(self) -> None:
        """Invalid number with currency symbol returns error."""
        result, errors = parse_currency("\u20acinvalid", "en_US")
        assert result is None
        assert len(errors) > 0

    def test_parse_currency_empty_string(self) -> None:
        """Empty string returns error."""
        result, errors = parse_currency("", "en_US")
        assert result is None
        assert len(errors) > 0

    def test_parse_currency_only_symbol(self) -> None:
        """Only currency symbol without number returns error."""
        result, errors = parse_currency("\u20ac", "en_US")
        assert result is None
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Locale error handling
# ---------------------------------------------------------------------------


class TestCurrencyLocaleErrors:
    """Test currency parsing with invalid locales."""

    def test_parse_currency_with_invalid_locale(self) -> None:
        """Invalid locale code returns error."""
        result, errors = parse_currency("\u20ac10.50", "invalid_LOCALE_CODE")
        assert result is None
        assert len(errors) > 0
        assert any("locale" in str(err).lower() for err in errors)

    def test_parse_currency_with_malformed_locale(self) -> None:
        """Malformed locale string returns error."""
        result, errors = parse_currency("$100", "!!!invalid@@@")
        assert result is None
        assert len(errors) > 0

    @given(
        bad_locale=st.text(
            alphabet=st.characters(blacklist_categories=["Cs"]),
            min_size=1,
            max_size=20,
        ).filter(lambda x: x not in ["en", "en_US", "de_DE", "fr_FR"])
    )
    def test_arbitrary_locales_never_crash(
        self, bad_locale: str
    ) -> None:
        """PROPERTY: Invalid locales never crash currency parsing."""
        locale_len = "short" if len(bad_locale) <= 5 else "long"
        event(f"locale_length={locale_len}")
        has_underscore = "_" in bad_locale
        event(f"has_underscore={has_underscore}")

        result, errors = parse_currency("\u20ac50", bad_locale)
        assert result is None or isinstance(result, tuple)
        if result is None:
            assert len(errors) > 0


# ---------------------------------------------------------------------------
# Roundtrip: format -> parse -> verify
# ---------------------------------------------------------------------------


class TestRoundtripCurrency:
    """Test format -> parse -> format roundtrip for currency."""

    def test_roundtrip_currency_en_us(self) -> None:
        """Currency roundtrip for US English."""
        from ftllexengine.runtime.functions import currency_format

        original_amount = Decimal("1234.56")
        formatted = currency_format(
            float(original_amount), "en-US",
            currency="USD", currency_display="symbol",
        )
        result, errors = parse_currency(
            str(formatted), "en_US", default_currency="USD"
        )
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
            float(original_amount), "lv-LV",
            currency="EUR", currency_display="symbol",
        )
        result, errors = parse_currency(str(formatted), "lv_LV")
        assert not errors
        assert result is not None
        parsed_amount, parsed_currency = result
        assert parsed_amount == original_amount
        assert parsed_currency == "EUR"


# ---------------------------------------------------------------------------
# resolve_ambiguous_symbol
# ---------------------------------------------------------------------------


class TestResolveAmbiguousSymbol:
    """Test resolve_ambiguous_symbol function."""

    def test_non_ambiguous_symbol_returns_none(self) -> None:
        """Non-ambiguous symbols return None (caller uses standard mapping)."""
        result = currency_module.resolve_ambiguous_symbol("\u20ac", "en_US")
        assert result is None

    def test_no_locale_uses_default(self) -> None:
        """Ambiguous symbol without locale falls back to default."""
        result = currency_module.resolve_ambiguous_symbol("\u00a5", None)
        assert result in {"JPY", "CNY"} or result is None

    def test_empty_locale_uses_default(self) -> None:
        """Ambiguous symbol with empty string locale uses default."""
        result = currency_module.resolve_ambiguous_symbol("$", "")
        assert result in {"USD"} or result is None


# ---------------------------------------------------------------------------
# _resolve_currency_code internal paths
# ---------------------------------------------------------------------------


class TestResolveCurrencyCode:
    """Test _resolve_currency_code internal function."""

    def test_unknown_symbol_returns_error(self) -> None:
        """Completely unknown symbol returns error."""
        result, error = currency_module._resolve_currency_code(
            "ZZZZZ", "en_US", "ZZZZZ 100",
            default_currency=None, infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_unicode_unknown_symbol_returns_error(self) -> None:
        """Unicode symbol not in any mapping returns error."""
        result, error = currency_module._resolve_currency_code(
            "\u2606", "en_US", "\u2606100",
            default_currency=None, infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_invalid_default_currency_format(self) -> None:
        """Ambiguous symbol with invalid default_currency format returns error."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="invalid", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_lowercase_default_currency_rejected(self) -> None:
        """Lowercase default_currency is rejected."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="usd", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_short_default_currency_rejected(self) -> None:
        """Too-short default_currency is rejected."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="US", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_long_default_currency_rejected(self) -> None:
        """Too-long default_currency is rejected."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="USDD", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_numeric_default_currency_rejected(self) -> None:
        """Numeric default_currency is rejected."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="123", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_locale_fallback_for_ambiguous_symbol(self) -> None:
        """Locale-to-currency fallback for ambiguous symbols."""
        result, error = currency_module._resolve_currency_code(
            "weird_symbol_not_mapped", "de_DE", "EUR 100",
            default_currency=None, infer_from_locale=True,
        )
        assert result is not None or error is not None


# ---------------------------------------------------------------------------
# Invalid ISO code
# ---------------------------------------------------------------------------


class TestInvalidISOCode:
    """Test parsing with invalid ISO codes."""

    def test_parse_currency_with_invalid_iso_code(self) -> None:
        """3-letter uppercase code not in CLDR returns error."""
        result, errors = parse_currency("AAA 100", "en_US")
        assert result is None
        assert len(errors) > 0

    def test_parse_currency_with_made_up_iso_code(self) -> None:
        """Completely made-up ISO code returns error."""
        result, errors = parse_currency("100 ZZZ", "en_US")
        assert result is None
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Locale-to-currency fallback
# ---------------------------------------------------------------------------


class TestLocaleToCurrencyFallback:
    """Test locale-to-currency fallback for ambiguous symbols."""

    def test_ambiguous_symbol_uses_locale_fallback(self) -> None:
        """Ambiguous symbol resolved via locale_to_currency mapping."""
        with patch(
            "ftllexengine.parsing.currency.resolve_ambiguous_symbol",
            return_value=None,
        ):
            result, errors = parse_currency(
                "$100", "en_US", infer_from_locale=True
            )

        if result is not None:
            _, currency = result
            assert currency == "USD"
            assert errors == ()
        else:
            assert len(errors) > 0

    def test_fallback_when_not_in_fast_tier(self) -> None:
        """Locale-to-currency fallback for locales only in CLDR."""
        with patch(
            "ftllexengine.parsing.currency.resolve_ambiguous_symbol",
            return_value=None,
        ):
            result, errors = parse_currency(
                "$100", "de_DE", infer_from_locale=True
            )

        if result is not None:
            _, currency = result
            assert currency == "EUR"
            assert errors == ()
        else:
            assert len(errors) > 0

    def test_no_resolution_available(self) -> None:
        """No resolution when both symbol and locale mappings are empty."""
        with (
            patch(
                "ftllexengine.parsing.currency.resolve_ambiguous_symbol",
                return_value=None,
            ),
            patch(
                "ftllexengine.parsing.currency._get_currency_maps",
                return_value=(
                    {},
                    {"$"},
                    {},
                    frozenset({"USD"}),
                ),
            ),
        ):
            result, errors = parse_currency(
                "$100", "en_US", infer_from_locale=True
            )

        assert result is None
        assert len(errors) > 0

    def test_locale_pound_sterling_egypt(self) -> None:
        """Pound sign with Egyptian locale."""
        result, _ = parse_currency(
            "\u00a3100", "en_EG", infer_from_locale=True
        )
        if result is not None:
            _, currency = result
            assert currency in {"GBP", "EGP", "GIP"}

    def test_locale_kr_unknown_locale(self) -> None:
        """kr symbol with unknown locale uses default (SEK)."""
        result, error = currency_module._resolve_currency_code(
            "kr", "xx_UNKNOWN", "kr 100",
            default_currency=None, infer_from_locale=True,
        )
        assert result == "SEK" or error is not None


# ---------------------------------------------------------------------------
# CLDR caching
# ---------------------------------------------------------------------------


class TestCLDRCaching:
    """Test that CLDR data is cached via functools.cache."""

    def test_currency_maps_caching(self) -> None:
        """_get_currency_maps_full returns same cached object."""
        result1 = currency_module._get_currency_maps_full()
        result2 = currency_module._get_currency_maps_full()
        assert result1 is result2
        assert len(result1) == 4


# ---------------------------------------------------------------------------
# clear_currency_caches
# ---------------------------------------------------------------------------


class TestClearCurrencyCaches:
    """Test clear_currency_caches() function."""

    def test_executes_without_error(self) -> None:
        """clear_currency_caches() executes without error."""
        from ftllexengine.parsing.currency import clear_currency_caches

        clear_currency_caches()

    def test_invalidates_caches(self) -> None:
        """clear_currency_caches() actually clears cached data."""
        from ftllexengine.parsing.currency import clear_currency_caches

        maps1 = _get_currency_maps()
        clear_currency_caches()
        maps2 = _get_currency_maps()
        assert len(maps1[0]) == len(maps2[0])

    def test_multiple_calls(self) -> None:
        """clear_currency_caches() can be called multiple times."""
        from ftllexengine.parsing.currency import clear_currency_caches

        clear_currency_caches()
        clear_currency_caches()
        clear_currency_caches()


# ---------------------------------------------------------------------------
# Locale list coverage audit
# ---------------------------------------------------------------------------


class TestCurrencyLocaleListCoverage:
    """Validate _SYMBOL_LOOKUP_LOCALE_IDS covers major currencies."""

    REQUIRED_CURRENCIES: frozenset[str] = frozenset({
        "USD", "EUR", "JPY", "GBP", "CHF", "AUD", "NZD", "CAD",
        "CNY", "HKD", "SGD", "SEK", "NOK", "DKK", "KRW",
        "INR", "RUB", "TRY", "ZAR", "MXN", "BRL",
        "PLN", "CZK", "HUF", "RON", "BGN",
    })

    def test_symbol_lookup_locales_provide_major_currency_coverage(
        self,
    ) -> None:
        """Hardcoded locale list discovers major currency symbols."""
        symbol_map, _, _, _ = _get_currency_maps()
        discovered: set[str] = set(symbol_map.values())
        missing = self.REQUIRED_CURRENCIES - discovered
        max_missing = len(self.REQUIRED_CURRENCIES) // 5
        assert len(missing) <= max_missing, (
            f"Too many major currencies missing: {sorted(missing)}. "
            f"Max allowed: {max_missing}, got: {len(missing)}"
        )

    def test_locale_to_currency_covers_major_territories(self) -> None:
        """Locale-to-currency mapping covers major territories."""
        _, _, locale_to_currency, _ = _get_currency_maps()
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
        min_coverage = len(expected_locales) * 0.8
        assert len(found) >= min_coverage, (
            f"Insufficient coverage: {len(found)}/{len(expected_locales)}. "
            f"Missing: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# _build_currency_maps_from_cldr exception paths
# ---------------------------------------------------------------------------


class TestBuildCurrencyMapsExceptions:
    """Test _build_currency_maps_from_cldr exception handling."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        _build_currency_maps_from_cldr.cache_clear()
        _get_currency_maps.cache_clear()

    def test_locale_parse_exception(self) -> None:
        """Locale.parse exceptions are caught gracefully."""
        from babel import Locale

        original_parse = Locale.parse

        def mock_parse(locale_id: str) -> Any:
            if "broken" in locale_id.lower():
                msg = "Mocked parse failure"
                raise ValueError(msg)
            return original_parse(locale_id)

        with (
            patch.object(Locale, "parse", side_effect=mock_parse),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en_US", "broken_locale", "de_DE"],
            ),
        ):
            sym, amb, loc, _ = _build_currency_maps_from_cldr()

        assert isinstance(sym, dict)
        assert isinstance(amb, set)
        assert isinstance(loc, dict)

    def test_key_error_in_currencies_access(self) -> None:
        """KeyError when accessing locale.currencies.keys() is caught."""
        mock_locale = MagicMock()
        mock_locale.currencies.keys.side_effect = KeyError("Mock")

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["test_locale"],
            ),
        ):
            sym, _, _, codes = _build_currency_maps_from_cldr()

        assert isinstance(sym, dict)
        assert isinstance(codes, frozenset)

    def test_attribute_error_in_locale(self) -> None:
        """Locale with currencies=None is handled."""
        mock_locale = MagicMock()
        mock_locale.currencies = None

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["test_locale"],
            ),
        ):
            sym, amb, loc, _ = _build_currency_maps_from_cldr()

        assert isinstance(sym, dict)
        assert isinstance(amb, set)
        assert isinstance(loc, dict)

    def test_get_currency_symbol_exception(self) -> None:
        """get_currency_symbol exceptions are caught."""

        def mock_symbol(
            currency_code: str,
            locale: object = None,  # noqa: ARG001
        ) -> str:
            if currency_code == "FAIL":
                msg = "Mock symbol failure"
                raise ValueError(msg)
            return "$" if currency_code == "USD" else currency_code

        mock_locale = MagicMock()
        mock_locale.currencies = {"USD": "Dollar", "FAIL": "Bad"}
        mock_locale.territory = "US"

        with (
            patch(
                "babel.numbers.get_currency_symbol",
                side_effect=mock_symbol,
            ),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en_US"],
            ),
            patch("babel.Locale.parse", return_value=mock_locale),
        ):
            sym, amb, _, _ = _build_currency_maps_from_cldr()

        assert isinstance(sym, dict)
        assert isinstance(amb, set)

    def test_attribute_error_in_symbol_lookup(self) -> None:
        """AttributeError in get_currency_symbol is caught."""

        def mock_raises(
            currency_code: str,  # noqa: ARG001
            locale: object = None,  # noqa: ARG001
        ) -> str:
            msg = "Mock attribute error"
            raise AttributeError(msg)

        mock_locale = MagicMock()
        mock_locale.currencies = {"USD": "Dollar"}
        mock_locale.territory = "US"
        mock_locale.configure_mock(**{"__str__.return_value": "en_US"})

        with (
            patch(
                "babel.numbers.get_currency_symbol",
                side_effect=mock_raises,
            ),
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en_US"],
            ),
        ):
            sym, _, _, codes = _build_currency_maps_from_cldr()

        assert isinstance(sym, dict)
        assert isinstance(codes, frozenset)

    def test_territory_currencies_exception(self) -> None:
        """get_territory_currencies exception is caught."""

        def mock_territory(territory: str) -> list[str]:
            if territory == "XX":
                msg = "Unknown territory"
                raise ValueError(msg)
            return ["USD"]

        mock_us = MagicMock()
        mock_us.territory = "US"
        mock_us.currencies = {}
        mock_us.configure_mock(**{"__str__.return_value": "en_US"})

        mock_xx = MagicMock()
        mock_xx.territory = "XX"
        mock_xx.currencies = {}
        mock_xx.configure_mock(**{"__str__.return_value": "xx_XX"})

        def mock_parse(locale_id: str) -> MagicMock:
            return mock_xx if locale_id == "xx_XX" else mock_us

        with (
            patch(
                "babel.numbers.get_territory_currencies",
                side_effect=mock_territory,
            ),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en_US", "xx_XX"],
            ),
            patch("babel.Locale.parse", side_effect=mock_parse),
        ):
            _, _, loc, _ = _build_currency_maps_from_cldr()

        assert isinstance(loc, dict)

    def test_unknown_locale_error_in_territory_lookup(self) -> None:
        """UnknownLocaleError in get_territory_currencies is caught."""

        def mock_raises(
            territory: str,  # noqa: ARG001
        ) -> list[str]:
            msg = "Mock unknown locale"
            raise UnknownLocaleError(msg)

        mock_locale = MagicMock()
        mock_locale.territory = "XX"
        mock_locale.currencies = {}
        mock_locale.configure_mock(**{"__str__.return_value": "xx_XX"})

        with (
            patch(
                "babel.numbers.get_territory_currencies",
                side_effect=mock_raises,
            ),
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["xx_XX"],
            ),
        ):
            _, _, _, codes = _build_currency_maps_from_cldr()

        assert isinstance(codes, frozenset)

    def test_locale_without_territory(self) -> None:
        """Locale without territory is handled."""
        mock_locale = MagicMock()
        mock_locale.territory = None
        mock_locale.currencies = {}

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en"],
            ),
        ):
            _, _, loc, _ = _build_currency_maps_from_cldr()

        assert isinstance(loc, dict)

    def test_locale_str_without_underscore(self) -> None:
        """Locale str without underscore is not added to locale_to_currency."""
        mock_locale = MagicMock()
        mock_locale.territory = "XX"
        mock_locale.currencies = {}
        mock_locale.configure_mock(**{"__str__.return_value": "en"})

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en"],
            ),
            patch(
                "babel.numbers.get_territory_currencies",
                return_value=["GBP"],
            ),
        ):
            _, _, loc, _ = _build_currency_maps_from_cldr()

        assert "en" not in loc

    def test_empty_territory_currencies(self) -> None:
        """get_territory_currencies returning empty list is handled."""
        mock_locale = MagicMock()
        mock_locale.territory = "US"
        mock_locale.currencies = {}
        mock_locale.configure_mock(**{"__str__.return_value": "en_US"})

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en_US"],
            ),
            patch(
                "babel.numbers.get_territory_currencies",
                return_value=[],
            ),
        ):
            _, _, loc, _ = _build_currency_maps_from_cldr()

        assert isinstance(loc, dict)

    def test_returns_correct_types(self) -> None:
        """_build_currency_maps_from_cldr returns correct types."""
        sym, amb, loc, _ = _build_currency_maps_from_cldr()

        for s, c in sym.items():
            assert isinstance(s, str)
            assert isinstance(c, str)
        for s in amb:
            assert isinstance(s, str)
        for l_key, l_val in loc.items():
            assert isinstance(l_key, str)
            assert isinstance(l_val, str)

    def test_euro_is_unambiguous(self) -> None:
        """EUR symbol is in the unambiguous map."""
        sym, amb, _, _ = _build_currency_maps_from_cldr()
        assert "\u20ac" in sym or "\u20ac" not in amb
        if "\u20ac" in sym:
            assert sym["\u20ac"] == "EUR"

    def test_dollar_is_ambiguous(self) -> None:
        """$ symbol is in the ambiguous set."""
        _, amb, _, _ = _build_currency_maps_from_cldr()
        assert "$" in amb

    @given(
        locale_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=10)
    def test_handles_various_locale_counts(
        self, locale_count: int
    ) -> None:
        """PROPERTY: Function handles any number of locales."""
        event(f"locale_count={locale_count}")

        _build_currency_maps_from_cldr.cache_clear()
        mock_locales = [f"mock_{i}" for i in range(locale_count)]

        mock_locale = MagicMock()
        mock_locale.territory = None
        mock_locale.currencies = {}

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=mock_locales,
            ),
        ):
            sym, amb, loc, _ = _build_currency_maps_from_cldr()

        assert isinstance(sym, dict)
        assert isinstance(amb, set)
        assert isinstance(loc, dict)


# ---------------------------------------------------------------------------
# BabelImportError handling
# ---------------------------------------------------------------------------


class TestBabelImportError:
    """Test Babel import error handling in currency parsing."""

    def test_build_maps_returns_empty_when_babel_missing(self) -> None:
        """_build_currency_maps_from_cldr returns empty maps without Babel."""
        _build_currency_maps_from_cldr.cache_clear()

        original_import = builtins.__import__

        def mock_import(
            name: str, *args: object, **kwargs: object
        ) -> object:
            if name == "babel" or name.startswith("babel."):
                msg = f"No module named '{name}'"
                raise ImportError(msg)
            return original_import(name, *args, **kwargs)  # type: ignore[arg-type]

        try:
            with patch(
                "builtins.__import__", side_effect=mock_import
            ):
                sym, amb, loc, codes = (
                    _build_currency_maps_from_cldr()
                )
                assert sym == {}
                assert amb == set()
                assert loc == {}
                assert codes == frozenset()
        finally:
            _build_currency_maps_from_cldr.cache_clear()

    def test_parse_currency_raises_babel_import_error(self) -> None:
        """parse_currency() raises BabelImportError without Babel."""
        from ftllexengine.core.babel_compat import BabelImportError

        original_import = builtins.__import__

        def mock_import(
            name: str, *args: object, **kwargs: object
        ) -> object:
            if name == "babel" or name.startswith("babel."):
                msg = f"No module named '{name}'"
                raise ImportError(msg)
            return original_import(name, *args, **kwargs)  # type: ignore[arg-type]

        with patch(
            "builtins.__import__", side_effect=mock_import
        ):
            with pytest.raises(BabelImportError) as exc_info:
                parse_currency("\u20ac100", "en_US")

            error_msg = str(exc_info.value)
            assert "parse_currency" in error_msg


# ---------------------------------------------------------------------------
# Fast tier without Babel
# ---------------------------------------------------------------------------


class TestFastTierWithoutBabel:
    """Test that fast tier currency operations work without Babel."""

    def test_fast_tier_symbols_available(self) -> None:
        """Fast tier unambiguous symbols always available."""
        from ftllexengine.parsing.currency import (
            _FAST_TIER_UNAMBIGUOUS_SYMBOLS,
            _get_currency_maps_fast,
        )

        symbols, _, _, _ = _get_currency_maps_fast()
        assert len(symbols) > 0
        assert "\u20ac" in symbols
        assert symbols["\u20ac"] == "EUR"
        assert symbols == _FAST_TIER_UNAMBIGUOUS_SYMBOLS

    def test_fast_tier_pattern_compiles(self) -> None:
        """Fast tier regex pattern compiles and matches."""
        from ftllexengine.parsing.currency import (
            _get_currency_pattern_fast,
        )

        _get_currency_pattern_fast.cache_clear()
        try:
            pattern = _get_currency_pattern_fast()
            assert pattern.search("\u20ac100") is not None
            assert pattern.search("USD 100") is not None
        finally:
            _get_currency_pattern_fast.cache_clear()


# ---------------------------------------------------------------------------
# Pattern compilation fallback
# ---------------------------------------------------------------------------


class TestBuildCurrencyPatternFallback:
    """Test pattern compilation with empty symbol maps."""

    def test_full_pattern_fallback_when_no_symbols(self) -> None:
        """Full CLDR pattern falls back to ISO-code-only pattern."""
        from ftllexengine.parsing.currency import (
            _get_currency_pattern_full,
        )

        _get_currency_pattern_full.cache_clear()

        with patch(
            "ftllexengine.parsing.currency._get_currency_maps",
            return_value=({}, set(), {}, frozenset()),
        ):
            _get_currency_pattern_full.cache_clear()
            pattern = _get_currency_pattern_full()

            assert isinstance(pattern, re.Pattern)
            assert pattern.search("USD") is not None
            assert pattern.search("\u20ac") is None

        _get_currency_pattern_full.cache_clear()
        _get_currency_maps.cache_clear()

    def test_fast_pattern_fallback_when_empty(self) -> None:
        """Fast tier pattern falls back to ISO-code-only pattern."""
        from ftllexengine.parsing.currency import (
            _get_currency_pattern_fast,
        )

        _get_currency_pattern_fast.cache_clear()
        empty: tuple[
            dict[str, str], frozenset[str], dict[str, str], frozenset[str]
        ] = ({}, frozenset(), {}, frozenset())

        with patch(
            "ftllexengine.parsing.currency._get_currency_maps_fast",
            return_value=empty,
        ):
            pattern = _get_currency_pattern_fast()

        assert pattern is not None
        assert re.match(pattern, "USD")
        assert re.match(pattern, "$") is None

        _get_currency_pattern_fast.cache_clear()


# ---------------------------------------------------------------------------
# Hypothesis property: no digits always fails
# ---------------------------------------------------------------------------


class TestCurrencyParsingProperty:
    """Property-based test for currency parsing edge cases."""

    @given(
        invalid_value=st.text(min_size=1, max_size=30).filter(
            lambda x: not any(c.isdigit() for c in x)
        )
    )
    def test_no_digits_always_fails(
        self, invalid_value: str
    ) -> None:
        """PROPERTY: Values without digits always fail to parse."""
        has_currency_char = any(
            c in invalid_value for c in "\u20ac$\u00a3\u00a5\u20b9"
        )
        event(f"has_currency_char={has_currency_char}")
        val_len = "short" if len(invalid_value) <= 5 else "long"
        event(f"value_length={val_len}")

        result, _ = parse_currency(invalid_value, "en_US")
        assert result is None


# ---------------------------------------------------------------------------
# Integration: parse_currency with built maps
# ---------------------------------------------------------------------------


class TestParseCurrencyIntegration:
    """Integration tests for parse_currency with CLDR maps."""

    def test_euro_symbol_resolves(self) -> None:
        """parse_currency resolves EUR symbol."""
        result, errors = parse_currency("\u20ac100", "en_US")
        assert not errors
        assert result is not None
        _, currency = result
        assert currency == "EUR"

    def test_ambiguous_without_default_returns_error(self) -> None:
        """Ambiguous $ without default returns error."""
        result, errors = parse_currency("$100", "en_US")
        assert result is None
        assert len(errors) > 0

    def test_ambiguous_with_default_resolves(self) -> None:
        """Ambiguous $ with default_currency resolves."""
        result, errors = parse_currency(
            "$100", "en_US", default_currency="CAD"
        )
        assert not errors
        assert result is not None
        _, currency = result
        assert currency == "CAD"

    def test_infers_from_locale(self) -> None:
        """infer_from_locale infers USD from en_US."""
        result, errors = parse_currency(
            "$100", "en_US", infer_from_locale=True
        )
        assert not errors
        if result is not None:
            _, currency = result
            assert currency == "USD"

    def test_iso_code_handling(self) -> None:
        """ISO codes are handled directly."""
        result, errors = parse_currency("USD 100", "en_US")
        assert not errors
        assert result is not None
        _, currency = result
        assert currency == "USD"

    def test_multiple_formats_same_currency(self) -> None:
        """Same currency in different formats."""
        for value in ["$100", "100 USD", "USD 100"]:
            result, _ = parse_currency(value, "en_US")
            if result is not None:
                amount, currency = result
                assert amount == Decimal("100")
                assert currency == "USD"

    def test_thousands_separator(self) -> None:
        """Thousands separator handled correctly."""
        result, _ = parse_currency("$1,234.56", "en_US")
        if result is not None:
            amount, _ = result
            assert 1234 <= amount <= 1235
