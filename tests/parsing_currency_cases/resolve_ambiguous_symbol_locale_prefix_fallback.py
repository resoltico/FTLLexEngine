# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

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
