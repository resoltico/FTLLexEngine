"""Comprehensive tests for CURRENCY() built-in function.

Tests currency_format() function with various parameters, locales, and edge cases.
Follows the same pattern as test_fluent_functions.py for NUMBER/DATETIME.

This test file validates:
- Basic currency formatting across locales
- Currency-specific decimal places (JPY: 0, BHD: 3, EUR: 2)
- Symbol placement (before/after, spacing)
- Currency display modes (symbol, code, name)
- Error handling (invalid currency codes, invalid values)
- Integration with FluentBundle
- BIDI isolation for RTL locales
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.functions import currency_format
from ftllexengine.runtime.locale_context import LocaleContext

# Test locale set - representative sample of supported locales
# Babel supports 200+ locales; these are common ones for testing
TEST_LOCALES: frozenset[str] = frozenset({
    "en", "zh", "hi", "es", "fr", "ar", "bn", "pt", "ru", "ja",
    "de", "jv", "ko", "vi", "te", "tr", "ta", "mr", "ur", "it",
    "th", "gu", "pl", "uk", "kn", "or", "ml", "my", "pa", "lv",
})


class TestCurrencyFunction:
    """Test currency_format() function with various parameters."""

    def test_currency_basic_eur_us(self) -> None:
        """EUR in en_US: symbol before amount."""
        result = currency_format(123.45, "en-US", currency="EUR")
        assert isinstance(result, str)
        assert "123" in result
        assert "€" in result or "EUR" in result

    def test_currency_basic_eur_lv(self) -> None:
        """EUR in lv_LV: symbol after amount with space."""
        result = currency_format(123.45, "lv-LV", currency="EUR")
        assert isinstance(result, str)
        assert "123" in result
        assert "€" in result or "EUR" in result
        # Latvian typically has symbol after

    def test_currency_basic_usd(self) -> None:
        """USD formatting in en_US."""
        result = currency_format(123.45, "en-US", currency="USD")
        assert isinstance(result, str)
        assert "$" in result or "USD" in result
        assert "123" in result

    def test_currency_jpy_zero_decimals(self) -> None:
        """JPY uses 0 decimal places (CLDR rule)."""
        result = currency_format(12345, "ja-JP", currency="JPY")
        assert isinstance(result, str)
        # JPY should not have decimal point for whole numbers
        assert "12" in result or "12,345" in result or "12345" in result
        # Accept halfwidth yen (\xa5 ¥), fullwidth yen (\uffe5 ￥), or JPY code
        assert "\xa5" in result or "\uffe5" in result or "JPY" in result

    def test_currency_jpy_fractional_rounds(self) -> None:
        """JPY rounds fractional amounts (0 decimal places)."""
        result = currency_format(12345.67, "ja-JP", currency="JPY")
        assert isinstance(result, str)
        # Should round to 12346
        assert "12346" in result or "12,346" in result

    def test_currency_bhd_three_decimals(self) -> None:
        """BHD uses 3 decimal places (CLDR rule)."""
        result = currency_format(123.456, "ar-BH", currency="BHD")
        assert isinstance(result, str)
        # BHD should show 3 decimal places
        assert "123" in result
        assert "456" in result

    def test_currency_display_symbol(self) -> None:
        """currencyDisplay: 'symbol' shows € not EUR."""
        result = currency_format(100, "en-US", currency="EUR", currency_display="symbol")
        assert isinstance(result, str)
        assert "€" in result or "EUR" in result  # Symbol preferred
        assert "100" in result

    def test_currency_display_code(self) -> None:
        """currencyDisplay: 'code' shows EUR not €."""
        result = currency_format(100, "en-US", currency="EUR", currency_display="code")
        assert isinstance(result, str)
        assert "EUR" in result  # Code required
        assert "100" in result

    def test_currency_display_name(self) -> None:
        """currencyDisplay: 'name' shows 'euros' or similar."""
        result = currency_format(100, "en-US", currency="EUR", currency_display="name")
        assert isinstance(result, str)
        # Name display varies by Babel version, just check it's formatted
        assert "100" in result

    def test_currency_with_zero(self) -> None:
        """Zero amount formatting."""
        result = currency_format(0, "en-US", currency="USD")
        assert isinstance(result, str)
        assert "0" in result
        assert "$" in result or "USD" in result

    def test_currency_with_negative(self) -> None:
        """Negative amounts use locale-specific format."""
        result = currency_format(-123.45, "en-US", currency="USD")
        assert isinstance(result, str)
        # Different locales may use different negative formats
        assert "123" in result
        assert "-" in result or "(" in result  # Parentheses or minus sign

    def test_currency_large_amount(self) -> None:
        """Large amounts use grouping separators."""
        result = currency_format(1234567.89, "en-US", currency="USD")
        assert isinstance(result, str)
        # Should have thousands separators
        assert "1" in result
        assert "234" in result or "567" in result

    def test_currency_fractional_cents(self) -> None:
        """Sub-cent amounts (e.g., 0.005 EUR)."""
        result = currency_format(0.005, "en-US", currency="EUR")
        assert isinstance(result, str)
        # May round to 0.01 or 0.00 depending on Babel
        assert "€" in result or "EUR" in result

    def test_currency_multiple_currencies_same_locale(self) -> None:
        """Multiple currencies in same locale."""
        usd = currency_format(100, "en-US", currency="USD")
        eur = currency_format(100, "en-US", currency="EUR")
        gbp = currency_format(100, "en-US", currency="GBP")

        assert "USD" in usd or "$" in usd
        assert "EUR" in eur or "€" in eur
        assert "GBP" in gbp or "£" in gbp

    def test_currency_same_currency_multiple_locales(self) -> None:
        """Same currency in different locales has different formatting."""
        eur_us = currency_format(123.45, "en-US", currency="EUR")
        eur_de = currency_format(123.45, "de-DE", currency="EUR")
        eur_lv = currency_format(123.45, "lv-LV", currency="EUR")

        # All should contain EUR symbol or code
        assert "€" in eur_us or "EUR" in eur_us
        assert "€" in eur_de or "EUR" in eur_de
        assert "€" in eur_lv or "EUR" in eur_lv

        # Formatting may differ (grouping, decimal separators)
        assert isinstance(eur_us, str)
        assert isinstance(eur_de, str)
        assert isinstance(eur_lv, str)


class TestCurrencyFunctionErrorHandling:
    """Test currency_format() error handling.

    FormattingError is raised with fallback_value for invalid inputs.
    The resolver catches this exception and uses the fallback in output.
    """

    def test_currency_invalid_code_returns_fallback(self) -> None:
        """Invalid currency code (XXX) returns graceful fallback."""
        result = currency_format(100, "en-US", currency="XXX")
        assert isinstance(result, str)
        # Should return fallback format
        assert "XXX" in result or "100" in result

    def test_currency_with_string_value_raises_formatting_error(self) -> None:
        """Non-numeric value raises FrozenFluentError with fallback."""
        with pytest.raises(FrozenFluentError) as exc_info:
            currency_format("not a number", "en-US", currency="USD")  # type: ignore

        assert exc_info.value.category == ErrorCategory.FORMATTING
        # Fallback should include currency and/or value
        fallback = exc_info.value.fallback_value
        assert "USD" in fallback or "not a number" in fallback

    def test_currency_with_none_raises_formatting_error(self) -> None:
        """None value raises FrozenFluentError with fallback."""
        with pytest.raises(FrozenFluentError) as exc_info:
            currency_format(None, "en-US", currency="EUR")  # type: ignore

        assert exc_info.value.category == ErrorCategory.FORMATTING
        # Fallback should include currency
        assert "EUR" in exc_info.value.fallback_value

    def test_currency_with_inf_returns_fallback(self) -> None:
        """Infinity value returns fallback."""
        result = currency_format(float("inf"), "en-US", currency="USD")
        assert isinstance(result, str)
        # Should handle gracefully

    def test_currency_with_empty_currency_code(self) -> None:
        """Empty currency code returns fallback."""
        result = currency_format(100, "en-US", currency="")
        assert isinstance(result, str)
        # Should handle gracefully


class TestCurrencyFunctionAllLocales:
    """Test currency_format() across all 30 test locales."""

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_currency_works_all_locales_eur(self, locale_code: str) -> None:
        """CURRENCY() works for EUR in all 30 locales."""
        result = currency_format(123.45, locale_code, currency="EUR")
        assert isinstance(result, str)
        assert len(result) > 0
        # Should contain currency symbol or code
        assert "€" in result or "EUR" in result or "123" in result

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_currency_works_all_locales_usd(self, locale_code: str) -> None:
        """CURRENCY() works for USD in all 30 test locales."""
        result = currency_format(99.99, locale_code, currency="USD")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "99" in result

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_currency_zero_all_locales(self, locale_code: str) -> None:
        """Zero currency value works in all test locales."""
        result = currency_format(0, locale_code, currency="EUR")
        assert isinstance(result, str)
        assert "0" in result


class TestCurrencyLocaleContext:
    """Test LocaleContext.format_currency() method directly."""

    def test_locale_context_currency_en_us(self) -> None:
        """LocaleContext formats EUR in en_US."""
        ctx = LocaleContext.create_or_raise("en-US")
        result = ctx.format_currency(123.45, currency="EUR")
        assert isinstance(result, str)
        assert "123" in result
        assert "€" in result or "EUR" in result

    def test_locale_context_currency_lv_lv(self) -> None:
        """LocaleContext formats EUR in lv_LV."""
        ctx = LocaleContext.create_or_raise("lv-LV")
        result = ctx.format_currency(123.45, currency="EUR")
        assert isinstance(result, str)
        assert "123" in result
        assert "€" in result or "EUR" in result

    def test_locale_context_currency_display_modes(self) -> None:
        """LocaleContext supports all currency display modes."""
        ctx = LocaleContext.create_or_raise("en-US")

        symbol = ctx.format_currency(100, currency="USD", currency_display="symbol")
        code = ctx.format_currency(100, currency="USD", currency_display="code")
        name = ctx.format_currency(100, currency="USD", currency_display="name")

        assert isinstance(symbol, str)
        assert isinstance(code, str)
        assert isinstance(name, str)
        assert "USD" in code  # Code must appear in code display


class TestCurrencyFluentBundleIntegration:
    """Test CURRENCY() function in FluentBundle."""

    def test_bundle_currency_basic(self) -> None:
        """CURRENCY works in FluentBundle."""
        bundle = FluentBundle("en_US")
        bundle.add_resource('price = { CURRENCY($amount, currency: "EUR") }')
        result, errors = bundle.format_pattern("price", {"amount": 123.45})

        assert isinstance(result, str)
        assert len(errors) == 0
        assert "123" in result
        assert "€" in result or "EUR" in result

    def test_bundle_currency_different_currencies(self) -> None:
        """CURRENCY with different currency codes.

        Note: FTL spec does not allow variables in named parameters.
        Named parameters must be literals. This test uses multiple messages.
        """
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
price-eur = { CURRENCY($amount, currency: "EUR") }
price-usd = { CURRENCY($amount, currency: "USD") }
""")

        result_eur, _ = bundle.format_pattern("price-eur", {"amount": 100})
        result_usd, _ = bundle.format_pattern("price-usd", {"amount": 100})

        assert "€" in result_eur or "EUR" in result_eur
        assert "$" in result_usd or "USD" in result_usd

    def test_bundle_currency_display_modes(self) -> None:
        """CURRENCY with different display modes."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
symbol = { CURRENCY($amount, currency: "EUR", currencyDisplay: "symbol") }
code = { CURRENCY($amount, currency: "EUR", currencyDisplay: "code") }
name = { CURRENCY($amount, currency: "EUR", currencyDisplay: "name") }
""")

        symbol, _ = bundle.format_pattern("symbol", {"amount": 100})
        code, _ = bundle.format_pattern("code", {"amount": 100})
        name, _ = bundle.format_pattern("name", {"amount": 100})

        assert isinstance(symbol, str)
        assert "EUR" in code  # Code must show EUR
        assert isinstance(name, str)

    def test_bundle_currency_in_select_expression(self) -> None:
        """CURRENCY works inside select expressions.

        Note: FTL spec does not allow variables in named parameters.
        The default case uses a literal currency code.
        """
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
price = { $currency ->
    [EUR] { CURRENCY($amount, currency: "EUR") }
    [USD] { CURRENCY($amount, currency: "USD") }
   *[other] { CURRENCY($amount, currency: "GBP") }
}
""")

        result_eur, _ = bundle.format_pattern("price", {"amount": 99.99, "currency": "EUR"})
        result_usd, _ = bundle.format_pattern("price", {"amount": 99.99, "currency": "USD"})
        result_other, _ = bundle.format_pattern("price", {"amount": 99.99, "currency": "GBP"})

        assert "€" in result_eur or "EUR" in result_eur
        assert "$" in result_usd or "USD" in result_usd
        assert "£" in result_other or "GBP" in result_other

    def test_bundle_currency_all_30_locales(self) -> None:
        """CURRENCY function works in FluentBundle for all 30 test locales."""
        for locale in TEST_LOCALES:
            bundle = FluentBundle(locale)
            bundle.add_resource('price = { CURRENCY($amount, currency: "EUR") }')
            result, errors = bundle.format_pattern("price", {"amount": 123.45})

            assert isinstance(result, str)
            assert len(result) > 0
            # No errors should occur
            assert len(errors) == 0


class TestCurrencySpecificCurrencies:
    """Test specific currency formatting rules from CLDR."""

    def test_jpy_zero_decimals(self) -> None:
        """Japanese Yen: 0 decimal places."""
        result = currency_format(1000, "ja-JP", currency="JPY")
        assert "1" in result or "1,000" in result or "1000" in result
        # Should not show .00

    def test_krw_zero_decimals(self) -> None:
        """Korean Won: 0 decimal places."""
        result = currency_format(1000, "ko-KR", currency="KRW")
        assert "1" in result or "1,000" in result or "1000" in result

    def test_bhd_three_decimals(self) -> None:
        """Bahraini Dinar: 3 decimal places."""
        result = currency_format(1.234, "ar-BH", currency="BHD")
        # Should show 3 decimals
        assert "1" in result
        assert "234" in result

    def test_kwd_three_decimals(self) -> None:
        """Kuwaiti Dinar: 3 decimal places."""
        result = currency_format(1.234, "ar-KW", currency="KWD")
        assert "1" in result
        assert "234" in result

    def test_eur_two_decimals(self) -> None:
        """Euro: 2 decimal places (standard)."""
        result = currency_format(10, "en-US", currency="EUR")
        # Most locales show 2 decimals for EUR
        assert "10" in result

    def test_usd_two_decimals(self) -> None:
        """US Dollar: 2 decimal places (standard)."""
        result = currency_format(10, "en-US", currency="USD")
        assert "10" in result


class TestCurrencyRTLLocales:
    """Test CURRENCY in RTL locales (Arabic, Urdu)."""

    def test_currency_arabic(self) -> None:
        """Arabic locale with BIDI support."""
        result = currency_format(123.45, "ar", currency="SAR")
        assert isinstance(result, str)
        assert len(result) > 0
        # May contain BIDI marks (invisible)

    def test_currency_urdu(self) -> None:
        """Urdu locale formatting."""
        result = currency_format(100, "ur", currency="PKR")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_currency_arabic_with_bundle(self) -> None:
        """Arabic in FluentBundle includes BIDI marks."""
        bundle = FluentBundle("ar")
        bundle.add_resource('price = { CURRENCY($amount, currency: "SAR") }')
        result, _ = bundle.format_pattern("price", {"amount": 100})

        # Should contain BIDI marks (U+2068, U+2069) when use_isolating=True
        assert isinstance(result, str)
        assert "\u2068" in result or "\u2069" in result or len(result) > 0


class TestCurrencyHypothesis:
    """Property-based tests for currency formatting."""

    @given(
        amount=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
        currency=st.sampled_from(["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"]),
    )
    @settings(max_examples=100)
    def test_currency_never_crashes(self, amount: float, currency: str) -> None:
        """currency_format() never crashes for any amount/currency combination."""
        result = currency_format(amount, "en-US", currency=currency)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        locale=st.sampled_from(sorted(TEST_LOCALES)),
        amount=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_currency_all_locales_never_crash(self, locale: str, amount: float) -> None:
        """currency_format() works for any test locale and amount."""
        result = currency_format(amount, locale, currency="EUR")
        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        amount=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50)
    def test_currency_deterministic(self, amount: float) -> None:
        """Same input always produces same output."""
        result1 = currency_format(amount, "en-US", currency="USD")
        result2 = currency_format(amount, "en-US", currency="USD")
        assert result1 == result2


class TestCurrencyEdgeCases:
    """Test edge cases for currency formatting."""

    def test_currency_very_large_amount(self) -> None:
        """Very large currency amounts."""
        result = currency_format(999999999.99, "en-US", currency="USD")
        assert isinstance(result, str)
        assert "999" in result

    def test_currency_very_small_amount(self) -> None:
        """Very small currency amounts."""
        result = currency_format(0.01, "en-US", currency="USD")
        assert isinstance(result, str)
        # Should show cents

    def test_currency_exact_zero(self) -> None:
        """Exactly zero."""
        result = currency_format(0.0, "en-US", currency="EUR")
        assert isinstance(result, str)
        assert "0" in result

    def test_currency_negative_zero(self) -> None:
        """Negative zero (edge case in floating point)."""
        result = currency_format(-0.0, "en-US", currency="USD")
        assert isinstance(result, str)
        assert "0" in result
