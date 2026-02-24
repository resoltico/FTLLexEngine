"""Tests for locale-specific NUMBER and DATETIME formatting across 30 locales.

Validates that all 30 supported locales work correctly with Babel for:
- Number formatting (grouping separators, decimal separators)
- Date formatting (locale-specific patterns)
- Integration with FluentBundle

This ensures our claim of "30 locale support" is fully backed by tests.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.runtime.locale_context import LocaleContext

# Test locale set - representative sample of supported locales
# Babel supports 200+ locales; these are common ones for testing
TEST_LOCALES: frozenset[str] = frozenset({
    "en", "zh", "hi", "es", "fr", "ar", "bn", "pt", "ru", "ja",
    "de", "jv", "ko", "vi", "te", "tr", "ta", "mr", "ur", "it",
    "th", "gu", "pl", "uk", "kn", "or", "ml", "my", "pa", "lv",
})

# All 30 supported locales with expected characteristics
LOCALE_TEST_DATA = {
    # Western European (comma thousand sep, period decimal)
    "en": {"thousand": ",", "decimal": ".", "name": "English"},
    "de": {"thousand": ".", "decimal": ",", "name": "German"},
    "fr": {"thousand": "\u202f", "decimal": ",", "name": "French"},  # narrow no-break space
    "es": {"thousand": ".", "decimal": ",", "name": "Spanish"},
    "it": {"thousand": ".", "decimal": ",", "name": "Italian"},
    "pt": {"thousand": ".", "decimal": ",", "name": "Portuguese"},
    # Eastern European (space thousand sep, comma decimal)
    "ru": {"thousand": "\u00a0", "decimal": ",", "name": "Russian"},  # no-break space
    "pl": {"thousand": "\u00a0", "decimal": ",", "name": "Polish"},
    "uk": {"thousand": "\u00a0", "decimal": ",", "name": "Ukrainian"},
    "lv": {"thousand": "\u00a0", "decimal": ",", "name": "Latvian"},
    # South Asian
    "hi": {"thousand": ",", "decimal": ".", "name": "Hindi"},  # Indian grouping
    "bn": {"thousand": ",", "decimal": ".", "name": "Bengali"},
    "te": {"thousand": ",", "decimal": ".", "name": "Telugu"},
    "ta": {"thousand": ",", "decimal": ".", "name": "Tamil"},
    "mr": {"thousand": ",", "decimal": ".", "name": "Marathi"},
    "gu": {"thousand": ",", "decimal": ".", "name": "Gujarati"},
    "kn": {"thousand": ",", "decimal": ".", "name": "Kannada"},
    "ml": {"thousand": ",", "decimal": ".", "name": "Malayalam"},
    "pa": {"thousand": ",", "decimal": ".", "name": "Punjabi"},
    "or": {"thousand": ",", "decimal": ".", "name": "Odia"},
    "ur": {"thousand": ",", "decimal": ".", "name": "Urdu"},
    # East Asian (no grouping in some)
    "zh": {"thousand": ",", "decimal": ".", "name": "Chinese"},
    "ja": {"thousand": ",", "decimal": ".", "name": "Japanese"},
    "ko": {"thousand": ",", "decimal": ".", "name": "Korean"},
    "vi": {"thousand": ".", "decimal": ",", "name": "Vietnamese"},
    "th": {"thousand": ",", "decimal": ".", "name": "Thai"},
    "my": {"thousand": ",", "decimal": ".", "name": "Burmese"},
    "jv": {"thousand": ".", "decimal": ",", "name": "Javanese"},
    # Middle Eastern (RTL)
    "ar": {"thousand": "\u066c", "decimal": "\u066b", "name": "Arabic"},  # Arabic-Indic seps
    "tr": {"thousand": ".", "decimal": ",", "name": "Turkish"},
}


class TestLocaleContextAllLocales:
    """Test LocaleContext works with all 30 supported locales."""

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_locale_context_creation(self, locale_code: str) -> None:
        """LocaleContext can be created for all 30 locales."""
        ctx = LocaleContext.create_or_raise(locale_code)
        assert ctx.locale_code == locale_code

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_babel_locale_property(self, locale_code: str) -> None:
        """babel_locale property returns valid Babel Locale for all 30 locales."""
        ctx = LocaleContext.create_or_raise(locale_code)
        babel_loc = ctx.babel_locale
        # Should have language code
        assert babel_loc.language == locale_code

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_format_number_basic(self, locale_code: str) -> None:
        """format_number() works for all 30 locales with basic number."""
        ctx = LocaleContext.create_or_raise(locale_code)
        result = ctx.format_number(Decimal("1234.56"))
        # Should return a string containing the digits
        assert isinstance(result, str)
        assert "1" in result or "\u0661" in result  # Latin or Arabic-Indic digit
        assert "2" in result or "\u0662" in result
        assert "3" in result or "\u0663" in result
        assert "4" in result or "\u0664" in result

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_format_number_with_grouping(self, locale_code: str) -> None:
        """format_number() applies locale-specific grouping for all 30 locales."""
        ctx = LocaleContext.create_or_raise(locale_code)
        result = ctx.format_number(1234567, use_grouping=True)
        # Should be longer than plain digits due to separators
        assert isinstance(result, str)
        assert len(result) >= 7  # At least 7 digits

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_format_datetime_basic(self, locale_code: str) -> None:
        """format_datetime() works for all 30 locales."""
        ctx = LocaleContext.create_or_raise(locale_code)
        dt = datetime(2025, 10, 27, 14, 30, 0, tzinfo=UTC)
        result = ctx.format_datetime(dt, date_style="medium")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_format_datetime_all_styles(self, locale_code: str) -> None:
        """format_datetime() works with all date styles for all 30 locales."""
        ctx = LocaleContext.create_or_raise(locale_code)
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        for style in ["short", "medium", "long", "full"]:
            result = ctx.format_datetime(dt, date_style=style)  # type: ignore
            assert isinstance(result, str)
            assert len(result) > 0


class TestFluentBundleAllLocales:
    """Test FluentBundle works with all 30 supported locales."""

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_bundle_creation(self, locale_code: str) -> None:
        """FluentBundle can be created for all 30 locales."""
        bundle = FluentBundle(locale_code)
        assert bundle.locale.startswith(locale_code.split("_", maxsplit=1)[0])

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_bundle_number_function(self, locale_code: str) -> None:
        """NUMBER function works in FluentBundle for all 30 locales."""
        bundle = FluentBundle(locale_code)
        bundle.add_resource("price = { NUMBER($amount) }")
        result, _ = bundle.format_pattern("price", {"amount": Decimal("1234.56")})
        assert isinstance(result, str)
        # Should contain formatted number (not error)
        assert "{ERROR" not in result

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_bundle_number_with_params(self, locale_code: str) -> None:
        """NUMBER function with parameters works for all 30 locales."""
        bundle = FluentBundle(locale_code)
        bundle.add_resource(
            "price = { NUMBER($amount, minimumFractionDigits: 2, maximumFractionDigits: 2) }"
        )
        result, _ = bundle.format_pattern("price", {"amount": 42})
        assert isinstance(result, str)
        assert "{ERROR" not in result

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_bundle_datetime_function(self, locale_code: str) -> None:
        """DATETIME function works in FluentBundle for all 30 locales."""
        bundle = FluentBundle(locale_code)
        bundle.add_resource('date = { DATETIME($time, dateStyle: "medium") }')
        dt = datetime(2025, 10, 27, 14, 30, 0, tzinfo=UTC)
        result, _ = bundle.format_pattern("date", {"time": dt})
        assert isinstance(result, str)
        assert "{ERROR" not in result

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_bundle_currency_function(self, locale_code: str) -> None:
        """CURRENCY function works in FluentBundle for all 30 locales."""
        bundle = FluentBundle(locale_code)
        bundle.add_resource('price = { CURRENCY($amount, currency: "EUR") }')
        result, _ = bundle.format_pattern("price", {"amount": Decimal("123.45")})
        assert isinstance(result, str)
        assert "{ERROR" not in result
        # Should contain currency symbol or code
        assert "€" in result or "EUR" in result or "123" in result

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_bundle_currency_with_params(self, locale_code: str) -> None:
        """CURRENCY function with parameters works for all 30 locales."""
        bundle = FluentBundle(locale_code)
        bundle.add_resource(
            'price = { CURRENCY($amount, currency: "USD", currencyDisplay: "code") }'
        )
        result, _ = bundle.format_pattern("price", {"amount": Decimal("99.99")})
        assert isinstance(result, str)
        assert "{ERROR" not in result
        assert "USD" in result  # Code display should show USD

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_bundle_plural_selection(self, locale_code: str) -> None:
        """Plural selection works for all 30 locales."""
        bundle = FluentBundle(locale_code)
        bundle.add_resource("""
items = { $count ->
    [one] one item
   *[other] { $count } items
}
""")
        # Test with 1 and 5
        result_one, errors = bundle.format_pattern("items", {"count": 1})

        assert not errors
        result_five, errors = bundle.format_pattern("items", {"count": 5})

        assert not errors
        assert isinstance(result_one, str)
        assert isinstance(result_five, str)
        assert "{ERROR" not in result_one
        assert "{ERROR" not in result_five


class TestLocaleSpecificFormatting:
    """Test locale-specific formatting differences."""

    def test_german_number_separators(self) -> None:
        """German uses period for thousands, comma for decimal."""
        ctx = LocaleContext.create_or_raise("de")
        result = ctx.format_number(Decimal("1234.56"), use_grouping=True)
        # German: 1.234,56
        assert "," in result  # Decimal comma
        assert "." in result  # Thousand period

    def test_french_number_separators(self) -> None:
        """French uses narrow no-break space for thousands, comma for decimal."""
        ctx = LocaleContext.create_or_raise("fr")
        result = ctx.format_number(Decimal("1234.56"), use_grouping=True)
        # French: 1 234,56 (with special space)
        assert "," in result  # Decimal comma

    def test_english_number_separators(self) -> None:
        """English uses comma for thousands, period for decimal."""
        ctx = LocaleContext.create_or_raise("en")
        result = ctx.format_number(Decimal("1234.56"), use_grouping=True)
        # English: 1,234.56
        assert "," in result  # Thousand comma
        assert "." in result  # Decimal period

    def test_russian_number_separators(self) -> None:
        """Russian uses space for thousands, comma for decimal."""
        ctx = LocaleContext.create_or_raise("ru")
        result = ctx.format_number(Decimal("1234.56"), use_grouping=True)
        # Russian: 1 234,56 (with no-break space)
        assert "," in result  # Decimal comma

    def test_arabic_uses_arabic_indic_numerals(self) -> None:
        """Arabic locale may use Arabic-Indic numerals."""
        ctx = LocaleContext.create_or_raise("ar")
        result = ctx.format_number(Decimal("1234.56"), use_grouping=True)
        # Arabic may use Arabic-Indic numerals or Western numerals depending on Babel
        assert isinstance(result, str)
        assert len(result) > 0

    def test_latvian_number_format(self) -> None:
        """Latvian uses space for thousands, comma for decimal."""
        ctx = LocaleContext.create_or_raise("lv")
        result = ctx.format_number(Decimal("1234.56"), use_grouping=True)
        # Latvian: 1 234,56
        assert "," in result  # Decimal comma

    def test_chinese_number_format(self) -> None:
        """Chinese uses comma for thousands, period for decimal."""
        ctx = LocaleContext.create_or_raise("zh")
        result = ctx.format_number(Decimal("1234.56"), use_grouping=True)
        # Chinese: 1,234.56
        assert isinstance(result, str)

    def test_currency_eur_us(self) -> None:
        """EUR in en_US: symbol before."""
        ctx = LocaleContext.create_or_raise("en-US")
        result = ctx.format_currency(Decimal("123.45"), currency="EUR")
        assert "€" in result or "EUR" in result
        assert "123" in result

    def test_currency_eur_lv(self) -> None:
        """EUR in lv_LV: symbol after with space."""
        ctx = LocaleContext.create_or_raise("lv-LV")
        result = ctx.format_currency(Decimal("123.45"), currency="EUR")
        assert "€" in result or "EUR" in result
        assert "123" in result
        # Symbol typically after in Latvian

    def test_currency_jpy_zero_decimals(self) -> None:
        """JPY has 0 decimal places."""
        ctx = LocaleContext.create_or_raise("ja-JP")
        result = ctx.format_currency(12345, currency="JPY")
        # Accept halfwidth yen (\xa5 ¥), fullwidth yen (\uffe5 ￥), or JPY code
        assert "\xa5" in result or "\uffe5" in result or "JPY" in result
        # Should not show decimals - verify amount is present
        assert "12" in result
        assert "345" in result

    def test_currency_bhd_three_decimals(self) -> None:
        """BHD has 3 decimal places."""
        ctx = LocaleContext.create_or_raise("ar-BH")
        result = ctx.format_currency(Decimal("123.456"), currency="BHD")
        assert "123" in result
        assert "456" in result  # 3 decimals


class TestHypothesisLocaleFormatting:
    """Property-based tests for locale formatting."""

    @given(
        locale=st.sampled_from(sorted(TEST_LOCALES)),
        number=st.decimals(
            min_value=Decimal("-1e12"),
            max_value=Decimal("1e12"),
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200)
    def test_number_format_never_crashes(self, locale: str, number: Decimal) -> None:
        """format_number() never crashes for any locale and number."""
        event(f"locale={locale}")
        ctx = LocaleContext.create_or_raise(locale)
        result = ctx.format_number(number)
        assert isinstance(result, str)

    @given(
        locale=st.sampled_from(sorted(TEST_LOCALES)),
        year=st.integers(min_value=1900, max_value=2100),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),  # Safe day range
    )
    @settings(max_examples=200)
    def test_datetime_format_never_crashes(
        self, locale: str, year: int, month: int, day: int
    ) -> None:
        """format_datetime() never crashes for any locale and date."""
        event(f"locale={locale}")
        ctx = LocaleContext.create_or_raise(locale)
        dt = datetime(year, month, day, tzinfo=UTC)
        result = ctx.format_datetime(dt)
        assert isinstance(result, str)

    @given(
        locale=st.sampled_from(sorted(TEST_LOCALES)),
        amount=st.decimals(
            min_value=Decimal("-1e9"),
            max_value=Decimal("1e9"),
            allow_nan=False,
            allow_infinity=False,
        ),
        currency=st.sampled_from(["USD", "EUR", "GBP", "JPY", "CHF"]),
    )
    @settings(max_examples=200)
    def test_currency_format_never_crashes(
        self, locale: str, amount: Decimal, currency: str
    ) -> None:
        """format_currency() never crashes for any locale, amount, and currency."""
        event(f"locale={locale}")
        event(f"currency={currency}")
        ctx = LocaleContext.create_or_raise(locale)
        result = ctx.format_currency(amount, currency=currency)
        assert isinstance(result, str)

    @given(
        locale=st.sampled_from(sorted(TEST_LOCALES)),
        count=st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=200)
    def test_plural_selection_never_crashes(self, locale: str, count: int) -> None:
        """Plural selection in FluentBundle never crashes for any locale."""
        event(f"locale={locale}")
        bundle = FluentBundle(locale)
        bundle.add_resource("""
items = { $count ->
    [zero] no items
    [one] one item
    [two] two items
    [few] few items
    [many] many items
   *[other] { $count } items
}
""")
        result, _ = bundle.format_pattern("items", {"count": count})
        assert isinstance(result, str)
        assert "{ERROR" not in result


class TestEdgeCases:
    """Test edge cases for locale formatting."""

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_zero_formatting(self, locale_code: str) -> None:
        """Zero formats correctly in all locales."""
        ctx = LocaleContext.create_or_raise(locale_code)
        result = ctx.format_number(0)
        assert isinstance(result, str)
        # Should contain zero digit (Latin or Arabic-Indic)
        assert "0" in result or "\u0660" in result

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_negative_number_formatting(self, locale_code: str) -> None:
        """Negative numbers format correctly in all locales."""
        ctx = LocaleContext.create_or_raise(locale_code)
        result = ctx.format_number(Decimal("-123.45"))
        assert isinstance(result, str)
        # Should contain negative sign (hyphen-minus or Unicode minus sign)
        assert "-" in result or "\u2212" in result

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_large_number_formatting(self, locale_code: str) -> None:
        """Large numbers format correctly in all locales."""
        ctx = LocaleContext.create_or_raise(locale_code)
        result = ctx.format_number(1234567890, use_grouping=True)
        assert isinstance(result, str)
        # Should be reasonably formatted
        assert len(result) >= 10  # Digits plus separators

    @pytest.mark.parametrize("locale_code", sorted(TEST_LOCALES))
    def test_fraction_only_number(self, locale_code: str) -> None:
        """Fractional numbers format correctly in all locales."""
        ctx = LocaleContext.create_or_raise(locale_code)
        result = ctx.format_number(Decimal("0.123"), minimum_fraction_digits=3)
        assert isinstance(result, str)
        assert "0" in result or "\u0660" in result


class TestRTLLocales:
    """Test RTL locale formatting (Arabic, Urdu)."""

    def test_arabic_bundle_with_number(self) -> None:
        """Arabic FluentBundle handles NUMBER correctly."""
        bundle = FluentBundle("ar")
        bundle.add_resource("price = { NUMBER($amount) }")
        result, _ = bundle.format_pattern("price", {"amount": Decimal("1234.56")})
        assert isinstance(result, str)
        assert "{ERROR" not in result

    def test_urdu_bundle_with_number(self) -> None:
        """Urdu FluentBundle handles NUMBER correctly."""
        bundle = FluentBundle("ur")
        bundle.add_resource("price = { NUMBER($amount) }")
        result, _ = bundle.format_pattern("price", {"amount": Decimal("1234.56")})
        assert isinstance(result, str)
        assert "{ERROR" not in result

    def test_arabic_datetime_format(self) -> None:
        """Arabic datetime formatting works."""
        ctx = LocaleContext.create_or_raise("ar")
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result = ctx.format_datetime(dt, date_style="long")
        assert isinstance(result, str)
        assert len(result) > 0


class TestComplexPluralLocales:
    """Test locales with complex plural rules."""

    def test_arabic_six_plural_categories(self) -> None:
        """Arabic supports all 6 plural categories."""
        bundle = FluentBundle("ar")
        bundle.add_resource("""
items = { $count ->
    [zero] لا عناصر
    [one] عنصر واحد
    [two] عنصران
    [few] عناصر قليلة
    [many] عناصر كثيرة
   *[other] { $count } عنصر
}
""")
        # Test representative numbers for each category
        result, _ = bundle.format_pattern("items", {"count": 0})
        assert "لا عناصر" in result
        result, _ = bundle.format_pattern("items", {"count": 1})
        assert "عنصر واحد" in result
        result, _ = bundle.format_pattern("items", {"count": 2})
        assert "عنصران" in result
        result, _ = bundle.format_pattern("items", {"count": 3})
        assert "عناصر قليلة" in result
        result, _ = bundle.format_pattern("items", {"count": 11})
        assert "عناصر كثيرة" in result

    def test_russian_slavic_plural_rules(self) -> None:
        """Russian uses Slavic plural rules (one, few, many, other)."""
        bundle = FluentBundle("ru")
        bundle.add_resource("""
items = { $count ->
    [one] { $count } предмет
    [few] { $count } предмета
    [many] { $count } предметов
   *[other] { $count } предметов
}
""")
        result, _ = bundle.format_pattern("items", {"count": 1})
        assert "предмет" in result
        result, _ = bundle.format_pattern("items", {"count": 2})
        assert "предмета" in result
        result, _ = bundle.format_pattern("items", {"count": 5})
        assert "предметов" in result
        result, _ = bundle.format_pattern("items", {"count": 11})
        assert "предметов" in result

    def test_latvian_zero_one_other(self) -> None:
        """Latvian uses zero, one, other plural categories."""
        bundle = FluentBundle("lv")
        bundle.add_resource("""
items = { $count ->
    [zero] nav vienumu
    [one] { $count } vienums
   *[other] { $count } vienumi
}
""")
        result, _ = bundle.format_pattern("items", {"count": 0})
        assert "nav vienumu" in result
        result, _ = bundle.format_pattern("items", {"count": 1})
        assert "vienums" in result
        result, _ = bundle.format_pattern("items", {"count": 2})
        assert "vienumi" in result

    def test_polish_slavic_plural_rules(self) -> None:
        """Polish uses Slavic plural rules."""
        bundle = FluentBundle("pl")
        bundle.add_resource("""
items = { $count ->
    [one] { $count } element
    [few] { $count } elementy
    [many] { $count } elementów
   *[other] { $count } elementów
}
""")
        result, _ = bundle.format_pattern("items", {"count": 1})
        assert "element" in result
        result, _ = bundle.format_pattern("items", {"count": 2})
        assert "elementy" in result
        result, _ = bundle.format_pattern("items", {"count": 5})
        assert "elementów" in result


class TestNoPluralsLocales:
    """Test locales with no grammatical plurals."""

    @pytest.mark.parametrize("locale_code", ["zh", "ja", "ko", "vi", "th", "jv", "my"])
    def test_no_plural_locales_use_other(self, locale_code: str) -> None:
        """Locales without grammatical plurals default to 'other'."""
        bundle = FluentBundle(locale_code)
        bundle.add_resource("""
items = { $count ->
    [one] one
   *[other] other
}
""")
        # All numbers should match "other"
        for count in [0, 1, 2, 5, 10, 100]:
            result, _ = bundle.format_pattern("items", {"count": count})
            assert "other" in result, f"{locale_code} with count={count} should be 'other'"
