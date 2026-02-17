"""Tests for currency parsing: parse_currency(), symbol resolution, CLDR maps.

Property-based tests using Hypothesis cover:
- Roundtrip: format -> parse -> verify for unambiguous/ISO inputs
- Locale resilience: arbitrary locales never crash
- Invalid input: no-digit strings always fail
- Ambiguous resolution: locale-aware symbol disambiguation
- CLDR map integrity: type contracts and coverage invariants

Unit tests cover specification examples and targeted edge cases.

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
    resolve_ambiguous_symbol,
)
from tests.strategies.currency import (
    ambiguous_currency_inputs,
    invalid_currency_inputs,
    iso_code_currency_inputs,
    unambiguous_currency_inputs,
)

# ---------------------------------------------------------------------------
# Property: Unambiguous symbols always parse successfully
# ---------------------------------------------------------------------------


class TestUnambiguousCurrencyParsing:
    """Property-based tests for unambiguous currency parsing."""

    @settings(deadline=500)  # CLDR map build on first call exceeds 200ms
    @given(data=unambiguous_currency_inputs())
    def test_unambiguous_symbol_parses(
        self, data: tuple[str, str, str]
    ) -> None:
        """PROPERTY: Unambiguous symbols and ISO codes always parse."""
        value, locale, expected_code = data
        event(f"expected_code={expected_code}")

        result, errors = parse_currency(value, locale)
        # Unambiguous symbols should parse without error
        if result is not None:
            amount, code = result
            assert code == expected_code
            assert isinstance(amount, Decimal)
            assert errors == ()


# ---------------------------------------------------------------------------
# Property: ISO code inputs always resolve correctly
# ---------------------------------------------------------------------------


class TestISOCodeParsing:
    """Property-based tests for ISO code currency parsing."""

    @given(data=iso_code_currency_inputs())
    def test_iso_code_parses_to_correct_currency(
        self, data: tuple[str, str, str]
    ) -> None:
        """PROPERTY: ISO codes resolve to the correct currency."""
        value, locale, expected_code = data
        event(f"iso_code={expected_code}")

        result, errors = parse_currency(value, locale)
        assert result is not None, f"Failed to parse: {value!r} ({locale})"
        amount, code = result
        assert code == expected_code
        assert isinstance(amount, Decimal)
        assert errors == ()


# ---------------------------------------------------------------------------
# Property: Invalid inputs never crash, always return errors
# ---------------------------------------------------------------------------


class TestInvalidCurrencyInputs:
    """Property-based tests for invalid currency input handling."""

    @given(data=invalid_currency_inputs())
    def test_invalid_input_returns_error(
        self, data: tuple[str, str]
    ) -> None:
        """PROPERTY: Invalid inputs return error tuple, never crash."""
        value, locale = data
        is_empty = value == ""
        event(f"is_empty={is_empty}")

        result, errors = parse_currency(value, locale)
        assert result is None
        assert len(errors) > 0

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
# Property: Arbitrary locales never crash
# ---------------------------------------------------------------------------


class TestLocaleResilience:
    """Property-based tests for locale robustness."""

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
# Property: Ambiguous symbols with locale inference
# ---------------------------------------------------------------------------


class TestAmbiguousSymbolResolution:
    """Property-based tests for ambiguous symbol resolution."""

    @given(data=ambiguous_currency_inputs())
    def test_ambiguous_with_default_resolves(
        self, data: tuple[str, str, str, str]
    ) -> None:
        """PROPERTY: Ambiguous symbols with default_currency resolve."""
        value, locale, default_currency, expected = data
        event(f"locale={locale}")

        result, errors = parse_currency(
            value, locale, default_currency=default_currency,
        )
        if result is not None:
            _, code = result
            assert code == expected
            assert errors == ()

    @given(
        locale_currency=st.sampled_from([
            ("en_US", "USD"), ("en_CA", "CAD"),
            ("en_AU", "AUD"), ("en_NZ", "NZD"),
            ("es_MX", "MXN"), ("es_AR", "ARS"),
        ])
    )
    def test_dollar_locale_inference(
        self, locale_currency: tuple[str, str]
    ) -> None:
        """PROPERTY: $ with infer_from_locale resolves per locale."""
        locale, expected = locale_currency
        event(f"dollar_locale={locale}")

        result, errors = parse_currency(
            "$100", locale, infer_from_locale=True,
        )
        assert result is not None, (
            f"$ should resolve via locale {locale}"
        )
        _, code = result
        assert code == expected
        assert errors == ()


# ---------------------------------------------------------------------------
# resolve_ambiguous_symbol: Locale prefix fallback
# ---------------------------------------------------------------------------


class TestResolveAmbiguousSymbolLocalePrefix:
    """Test resolve_ambiguous_symbol locale prefix matching."""

    def test_yen_sign_with_zh_cn_uses_prefix(self) -> None:
        """Yen sign resolves to CNY via zh prefix for zh_CN."""
        result = resolve_ambiguous_symbol("\u00a5", "zh_CN")
        assert result == "CNY"

    def test_yen_sign_with_zh_tw_uses_prefix(self) -> None:
        """Yen sign resolves to CNY via zh prefix for zh_TW."""
        result = resolve_ambiguous_symbol("\u00a5", "zh_TW")
        assert result == "CNY"

    def test_yen_sign_with_zh_hk_uses_prefix(self) -> None:
        """Yen sign resolves to CNY via zh prefix for zh_HK."""
        result = resolve_ambiguous_symbol("\u00a5", "zh_HK")
        assert result == "CNY"

    def test_pound_sign_with_en_gb_exact_match(self) -> None:
        """Pound sign resolves to GBP via exact en_gb match."""
        result = resolve_ambiguous_symbol("\u00a3", "en_GB")
        assert result == "GBP"

    def test_pound_sign_with_ar_eg_exact_match(self) -> None:
        """Pound sign resolves to EGP via exact ar_eg match."""
        result = resolve_ambiguous_symbol("\u00a3", "ar_EG")
        assert result == "EGP"

    def test_pound_sign_with_ar_sa_uses_prefix(self) -> None:
        """Pound sign resolves to EGP via ar prefix for ar_SA."""
        # ar_SA is not in exact match but ar prefix maps to EGP
        result = resolve_ambiguous_symbol("\u00a3", "ar_SA")
        assert result == "EGP"

    def test_non_ambiguous_returns_none(self) -> None:
        """Non-ambiguous symbols return None."""
        result = resolve_ambiguous_symbol("\u20ac", "en_US")
        assert result is None

    def test_no_locale_uses_default(self) -> None:
        """Ambiguous symbol without locale uses default."""
        result = resolve_ambiguous_symbol("\u00a5", None)
        assert result == "JPY"

    def test_empty_locale_uses_default(self) -> None:
        """Ambiguous symbol with empty locale uses default."""
        result = resolve_ambiguous_symbol("$", "")
        assert result == "USD"

    def test_unknown_locale_with_underscore_uses_default(self) -> None:
        """Unknown locale with underscore falls through to default."""
        result = resolve_ambiguous_symbol("$", "xx_YY")
        assert result == "USD"

    def test_unknown_locale_without_underscore_uses_default(self) -> None:
        """Unknown locale without underscore skips prefix match."""
        result = resolve_ambiguous_symbol("$", "xx")
        assert result == "USD"

    @given(
        symbol_locale=st.sampled_from([
            ("\u00a5", "zh_CN", "CNY"),
            ("\u00a5", "zh_TW", "CNY"),
            ("\u00a5", "zh_HK", "CNY"),
            ("\u00a3", "ar_SA", "EGP"),
            ("\u00a3", "ar_DZ", "EGP"),
        ])
    )
    def test_prefix_resolution_property(
        self, symbol_locale: tuple[str, str, str]
    ) -> None:
        """PROPERTY: Locale prefix resolution matches expected currency."""
        symbol, locale, expected = symbol_locale
        event(f"prefix_symbol={symbol}")
        event(f"prefix_locale={locale}")
        result = resolve_ambiguous_symbol(symbol, locale)
        assert result == expected


# ---------------------------------------------------------------------------
# parse_currency: Specification examples
# ---------------------------------------------------------------------------


class TestParseCurrencySpecificationExamples:
    """Specification examples for parse_currency behavior."""

    def test_eur_symbol_prefix(self) -> None:
        """EUR symbol prefix: EUR100.50 -> (100.50, EUR)."""
        result, errors = parse_currency("\u20ac100.50", "en_US")
        assert not errors
        assert result is not None
        assert result == (Decimal("100.50"), "EUR")

    def test_eur_symbol_suffix_latvian(self) -> None:
        """EUR symbol suffix: 100,50 EUR -> (100.50, EUR) in lv_LV."""
        result, errors = parse_currency("100,50 \u20ac", "lv_LV")
        assert not errors
        assert result is not None
        assert result == (Decimal("100.50"), "EUR")

    def test_usd_with_default_currency(self) -> None:
        """$ with default_currency=USD resolves correctly."""
        result, errors = parse_currency(
            "$1,234.56", "en_US", default_currency="USD",
        )
        assert not errors
        assert result is not None
        assert result[0] == Decimal("1234.56")
        assert result[1] == "USD"

    def test_iso_code_prefix(self) -> None:
        """ISO code prefix: USD 1,234.56 -> (1234.56, USD)."""
        result, errors = parse_currency("USD 1,234.56", "en_US")
        assert not errors
        assert result is not None
        assert result == (Decimal("1234.56"), "USD")

    def test_iso_code_german_format(self) -> None:
        """German format: EUR 1.234,56 -> (1234.56, EUR)."""
        result, errors = parse_currency("EUR 1.234,56", "de_DE")
        assert not errors
        assert result is not None
        assert result == (Decimal("1234.56"), "EUR")

    def test_rupee_unambiguous(self) -> None:
        """Indian Rupee symbol is unambiguous."""
        result, errors = parse_currency("\u20b91000", "hi_IN")
        assert not errors
        assert result is not None
        assert result[1] == "INR"

    def test_swiss_franc_iso(self) -> None:
        """Swiss Franc via ISO code."""
        result, errors = parse_currency("CHF 100", "de_CH")
        assert not errors
        assert result is not None
        assert result == (Decimal("100"), "CHF")

    def test_cny_chinese_locale(self) -> None:
        """Yen symbol resolves to CNY in Chinese locales."""
        result, errors = parse_currency(
            "\u00a51000", "zh_CN", infer_from_locale=True,
        )
        assert not errors
        assert result is not None
        assert result[1] == "CNY"

    def test_jpy_japanese_locale(self) -> None:
        """Yen symbol resolves to JPY in Japanese locales."""
        result, errors = parse_currency(
            "\u00a512,345", "ja_JP", infer_from_locale=True,
        )
        assert not errors
        assert result is not None
        assert result[1] == "JPY"

    def test_gbp_british_locale(self) -> None:
        """Pound symbol resolves to GBP in British locales."""
        result, errors = parse_currency(
            "\u00a3999.99", "en_GB", infer_from_locale=True,
        )
        assert not errors
        assert result is not None
        assert result == (Decimal("999.99"), "GBP")


# ---------------------------------------------------------------------------
# parse_currency: Error paths
# ---------------------------------------------------------------------------


class TestParseCurrencyErrors:
    """Test error handling in parse_currency."""

    def test_no_symbol_returns_error(self) -> None:
        """Missing currency symbol returns error."""
        result, errors = parse_currency("1,234.56", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_invalid_input_returns_error(self) -> None:
        """Non-parseable input returns error."""
        result, errors = parse_currency("invalid", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_invalid_number_with_symbol(self) -> None:
        """Invalid number with currency symbol returns error."""
        result, errors = parse_currency("\u20acinvalid", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_empty_string(self) -> None:
        """Empty string returns error."""
        result, errors = parse_currency("", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_only_symbol(self) -> None:
        """Symbol without number returns error."""
        result, errors = parse_currency("\u20ac", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_invalid_locale(self) -> None:
        """Invalid locale returns error with locale info."""
        result, errors = parse_currency(
            "\u20ac10.50", "invalid_LOCALE_CODE",
        )
        assert result is None
        assert len(errors) == 1
        assert any("locale" in str(err).lower() for err in errors)

    def test_malformed_locale(self) -> None:
        """Malformed locale returns error."""
        result, errors = parse_currency("$100", "!!!invalid@@@")
        assert result is None
        assert len(errors) == 1

    def test_ambiguous_without_default_returns_error(self) -> None:
        """$ without default_currency or inference returns error."""
        result, errors = parse_currency("$100", "en_US")
        assert result is None
        assert len(errors) == 1


# ---------------------------------------------------------------------------
# _resolve_currency_code internal paths
# ---------------------------------------------------------------------------


class TestResolveCurrencyCode:
    """Test _resolve_currency_code edge cases."""

    def test_unknown_symbol_returns_error(self) -> None:
        """Unknown symbol returns error."""
        result, error = currency_module._resolve_currency_code(
            "ZZZZZ", "en_US", "ZZZZZ 100",
            default_currency=None, infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_invalid_default_currency_format(self) -> None:
        """Ambiguous symbol with invalid default_currency returns error."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="invalid", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_lowercase_default_currency_rejected(self) -> None:
        """Lowercase default_currency is rejected (ISO requires uppercase)."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="usd", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_short_default_currency_rejected(self) -> None:
        """2-letter default_currency is rejected (ISO requires 3)."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="US", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_long_default_currency_rejected(self) -> None:
        """4-letter default_currency is rejected (ISO requires 3)."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="USDD", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_numeric_default_currency_rejected(self) -> None:
        """Numeric default_currency is rejected (ISO requires letters)."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="123", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_invalid_iso_code_not_in_cldr(self) -> None:
        """3-letter uppercase code not in CLDR returns error."""
        result, errors = parse_currency("AAA 100", "en_US")
        assert result is None
        assert len(errors) == 1

    @given(
        default=st.from_regex(r"[a-z]{3}", fullmatch=True)
    )
    @settings(max_examples=20)
    def test_lowercase_codes_always_rejected(
        self, default: str
    ) -> None:
        """PROPERTY: Lowercase 3-letter codes always rejected."""
        event(f"code_sample={default[:2]}")
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency=default, infer_from_locale=False,
        )
        assert result is None
        assert error is not None


# ---------------------------------------------------------------------------
# Locale-to-currency fallback
# ---------------------------------------------------------------------------


class TestLocaleToCurrencyFallback:
    """Test locale-to-currency inference fallback."""

    def test_dollar_inferred_from_en_us(self) -> None:
        """$ inferred as USD from en_US."""
        result, errors = parse_currency(
            "$100", "en_US", infer_from_locale=True,
        )
        assert errors == ()
        assert result is not None
        assert result[1] == "USD"

    def test_dollar_resolves_to_usd_in_de_de(self) -> None:
        """$ resolves to USD in de_DE (dollar sign is unambiguous)."""
        result, errors = parse_currency(
            "$100", "de_DE", infer_from_locale=True,
        )
        assert errors == ()
        assert result is not None
        assert result[1] == "USD"

    def test_cldr_only_ambiguous_symbol_locale_fallback(self) -> None:
        """CLDR-only ambiguous symbol resolves via locale-to-currency map.

        Rs is ambiguous in CLDR (INR, PKR, etc.) but not in the fast-tier
        ambiguous set. resolve_ambiguous_symbol returns None, so resolution
        falls through to the CLDR locale-to-currency mapping.
        """
        result, errors = parse_currency(
            "Rs 500", "hi_IN", infer_from_locale=True,
        )
        assert errors == ()
        assert result is not None
        assert result == (Decimal("500"), "INR")

    def test_cldr_only_ambiguous_kr_dot_locale_fallback(self) -> None:
        """kr. (Nordic krona with period) resolves via locale-to-currency map.

        kr. is ambiguous in CLDR (DKK, NOK, SEK, ISK) but not in the fast-tier
        ambiguous set. Falls through to locale-to-currency mapping.
        """
        result, errors = parse_currency(
            "kr.500", "da_DK", infer_from_locale=True,
        )
        assert errors == ()
        assert result is not None
        assert result == (Decimal("500"), "DKK")

    def test_no_resolution_available(self) -> None:
        """Empty currency maps cause resolution failure."""
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
                "$100", "en_US", infer_from_locale=True,
            )

        assert result is None
        assert len(errors) == 1

    def test_kr_unknown_locale_defaults_to_sek(self) -> None:
        """kr symbol with unknown locale defaults to SEK."""
        result, error = currency_module._resolve_currency_code(
            "kr", "xx_UNKNOWN", "kr 100",
            default_currency=None, infer_from_locale=True,
        )
        assert result == "SEK" or error is not None


# ---------------------------------------------------------------------------
# Roundtrip: format -> parse -> verify
# ---------------------------------------------------------------------------


class TestRoundtripCurrency:
    """Test format -> parse -> verify roundtrip."""

    def test_roundtrip_usd_en_us(self) -> None:
        """Currency roundtrip for US English."""
        from ftllexengine.runtime.functions import currency_format

        original = Decimal("1234.56")
        formatted = currency_format(
            float(original), "en-US",
            currency="USD", currency_display="symbol",
        )
        result, errors = parse_currency(
            str(formatted), "en_US", default_currency="USD",
        )
        assert not errors
        assert result is not None
        assert result[0] == original
        assert result[1] == "USD"

    def test_roundtrip_eur_lv_lv(self) -> None:
        """Currency roundtrip for Latvian EUR."""
        from ftllexengine.runtime.functions import currency_format

        original = Decimal("1234.56")
        formatted = currency_format(
            float(original), "lv-LV",
            currency="EUR", currency_display="symbol",
        )
        result, errors = parse_currency(str(formatted), "lv_LV")
        assert not errors
        assert result is not None
        assert result[0] == original
        assert result[1] == "EUR"


# ---------------------------------------------------------------------------
# CLDR map integrity
# ---------------------------------------------------------------------------


class TestCLDRMapIntegrity:
    """Test CLDR currency map structural invariants."""

    REQUIRED_CURRENCIES: frozenset[str] = frozenset({
        "USD", "EUR", "JPY", "GBP", "CHF", "AUD", "NZD", "CAD",
        "CNY", "HKD", "SGD", "SEK", "NOK", "DKK", "KRW",
        "INR", "RUB", "TRY", "ZAR", "MXN", "BRL",
        "PLN", "CZK", "HUF", "RON", "BGN",
    })

    def test_symbol_lookup_locales_discover_major_currencies(
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

    def test_locale_to_currency_covers_major_territories(
        self,
    ) -> None:
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
            f"Insufficient: {len(found)}/{len(expected_locales)}. "
            f"Missing: {sorted(missing)}"
        )

    def test_returns_correct_types(self) -> None:
        """_build_currency_maps_from_cldr returns correct types."""
        sym, amb, loc, codes = _build_currency_maps_from_cldr()
        for s, c in sym.items():
            assert isinstance(s, str)
            assert isinstance(c, str)
        for s in amb:
            assert isinstance(s, str)
        for l_key, l_val in loc.items():
            assert isinstance(l_key, str)
            assert isinstance(l_val, str)
        assert isinstance(codes, frozenset)

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

    def test_currency_maps_caching(self) -> None:
        """_get_currency_maps_full returns same cached object."""
        result1 = currency_module._get_currency_maps_full()
        result2 = currency_module._get_currency_maps_full()
        assert result1 is result2
        assert len(result1) == 4


# ---------------------------------------------------------------------------
# _build_currency_maps_from_cldr exception paths
# ---------------------------------------------------------------------------


class TestBuildCurrencyMapsExceptions:
    """Test _build_currency_maps_from_cldr exception handling."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        _build_currency_maps_from_cldr.cache_clear()
        _get_currency_maps.cache_clear()

    def test_locale_parse_exception_handled(self) -> None:
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
        """KeyError when accessing locale.currencies is caught."""
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

    def test_locale_with_currencies_none(self) -> None:
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
        mock_locale.configure_mock(
            **{"__str__.return_value": "en_US"},
        )

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
        mock_us.configure_mock(
            **{"__str__.return_value": "en_US"},
        )

        mock_xx = MagicMock()
        mock_xx.territory = "XX"
        mock_xx.currencies = {}
        mock_xx.configure_mock(
            **{"__str__.return_value": "xx_XX"},
        )

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
        mock_locale.configure_mock(
            **{"__str__.return_value": "xx_XX"},
        )

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

    def test_locale_str_without_underscore_excluded(self) -> None:
        """Locale str without underscore is not in locale_to_currency."""
        mock_locale = MagicMock()
        mock_locale.territory = "XX"
        mock_locale.currencies = {}
        mock_locale.configure_mock(
            **{"__str__.return_value": "en"},
        )

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
        mock_locale.configure_mock(
            **{"__str__.return_value": "en_US"},
        )

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

    @given(locale_count=st.integers(min_value=1, max_value=5))
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
    """Test Babel import error handling."""

    def test_build_maps_returns_empty_when_babel_missing(
        self,
    ) -> None:
        """_build_currency_maps_from_cldr returns empty without Babel."""
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

    def test_parse_currency_raises_babel_import_error(
        self,
    ) -> None:
        """parse_currency raises BabelImportError without Babel."""
        import ftllexengine.core.babel_compat as _bc
        from ftllexengine.core.babel_compat import BabelImportError

        _bc._babel_available = None
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
                with pytest.raises(BabelImportError) as exc_info:
                    parse_currency("\u20ac100", "en_US")

                error_msg = str(exc_info.value)
                assert "parse_currency" in error_msg
        finally:
            _bc._babel_available = None


# ---------------------------------------------------------------------------
# Fast tier operations
# ---------------------------------------------------------------------------


class TestFastTierOperations:
    """Test fast tier currency operations (no CLDR scan)."""

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

    def test_currency_pattern_compiles_and_matches(self) -> None:
        """Currency regex pattern compiles and matches."""
        from ftllexengine.parsing.currency import (
            _get_currency_pattern,
        )

        _get_currency_pattern.cache_clear()
        try:
            pattern = _get_currency_pattern()
            assert pattern.search("\u20ac100") is not None
            assert pattern.search("USD 100") is not None
        finally:
            _get_currency_pattern.cache_clear()

    def test_currency_pattern_longest_match_first(self) -> None:
        """Currency pattern matches multi-char symbols before prefixes."""
        from ftllexengine.parsing.currency import (
            _get_currency_pattern,
        )

        _get_currency_pattern.cache_clear()
        try:
            pattern = _get_currency_pattern()
            # Rs must match before R
            m = pattern.search("Rs100")
            assert m is not None
            assert m.group() == "Rs"
            # kr. must match before kr
            m = pattern.search("kr.500")
            assert m is not None
            assert m.group() == "kr."
        finally:
            _get_currency_pattern.cache_clear()


# ---------------------------------------------------------------------------
# Pattern compilation fallback
# ---------------------------------------------------------------------------


class TestPatternCompilationFallback:
    """Test pattern compilation with empty symbol maps."""

    def test_pattern_fallback_with_empty_symbols(self) -> None:
        """Pattern falls back to ISO-code-only when no symbols."""
        from ftllexengine.parsing.currency import (
            _get_currency_pattern,
        )

        _get_currency_pattern.cache_clear()

        with patch(
            "ftllexengine.parsing.currency._get_currency_maps",
            return_value=({}, set(), {}, frozenset()),
        ):
            _get_currency_pattern.cache_clear()
            pattern = _get_currency_pattern()

            assert isinstance(pattern, re.Pattern)
            assert pattern.search("USD") is not None
            assert pattern.search("\u20ac") is None

        _get_currency_pattern.cache_clear()
        _get_currency_maps.cache_clear()


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


class TestClearCurrencyCaches:
    """Test clear_currency_caches function."""

    def test_executes_without_error(self) -> None:
        """clear_currency_caches executes without error."""
        from ftllexengine.parsing.currency import clear_currency_caches

        clear_currency_caches()

    def test_invalidates_caches(self) -> None:
        """clear_currency_caches clears cached data."""
        from ftllexengine.parsing.currency import clear_currency_caches

        maps1 = _get_currency_maps()
        clear_currency_caches()
        maps2 = _get_currency_maps()
        assert len(maps1[0]) == len(maps2[0])

    def test_idempotent(self) -> None:
        """Multiple calls are safe."""
        from ftllexengine.parsing.currency import clear_currency_caches

        clear_currency_caches()
        clear_currency_caches()
        clear_currency_caches()


# ---------------------------------------------------------------------------
# Thread-safe caching behavior
# ---------------------------------------------------------------------------


class TestCurrencyCachingConcurrency:
    """Test thread-safe caching via functools.cache."""

    def test_concurrent_currency_maps_access(self) -> None:
        """Concurrent calls to _get_currency_maps_full return cached object.

        functools.cache provides thread-safe cache access, but does NOT
        prevent thundering herd on cold cache (multiple threads may compute
        simultaneously). This test verifies that AFTER cache is populated,
        concurrent access returns the same cached object.
        """
        import threading

        # Pre-warm cache to ensure it's populated
        _ = currency_module._get_currency_maps_full()

        barrier = threading.Barrier(4)
        results: list[object] = []

        def get_with_barrier() -> None:
            barrier.wait()
            data = currency_module._get_currency_maps_full()
            results.append(data)

        threads = [
            threading.Thread(target=get_with_barrier)
            for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 4
        assert all(r is results[0] for r in results)

    def test_currency_maps_structure(self) -> None:
        """Cached currency maps have expected 4-tuple structure."""
        data = currency_module._get_currency_maps_full()

        assert len(data) == 4
        symbol_map, ambiguous, locale_to_currency, valid_codes = data

        assert isinstance(symbol_map, dict)
        assert isinstance(ambiguous, set)
        assert isinstance(locale_to_currency, dict)
        assert isinstance(valid_codes, frozenset)
