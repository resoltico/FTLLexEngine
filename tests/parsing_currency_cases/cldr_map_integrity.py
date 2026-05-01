# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

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

    def test_symbol_map_normalizes_bidi_wrapped_arabic_symbols(self) -> None:
        """CLDR symbol map stores Arabic symbols without formatting-only marks."""
        symbol_map, _, _, _ = _get_currency_maps()
        assert symbol_map["ج.م."] == "EGP"
        assert symbol_map["د.إ."] == "AED"

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
