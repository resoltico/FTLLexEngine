"""Tests for FluentPluralRules - CLDR plural category selection.

Tests Unicode CLDR plural rules for 30 test locales.
Comprehensive coverage of all plural categories across language families.

Reference: https://www.unicode.org/cldr/charts/47/supplemental/language_plural_rules.html
"""

from ftllexengine.runtime.plural_rules import select_plural_category

# Test locale set - representative sample of supported locales
# Babel supports 200+ locales; these are common ones for testing
TEST_LOCALES: frozenset[str] = frozenset({
    "en", "zh", "hi", "es", "fr", "ar", "bn", "pt", "ru", "ja",
    "de", "jv", "ko", "vi", "te", "tr", "ta", "mr", "ur", "it",
    "th", "gu", "pl", "uk", "kn", "or", "ml", "my", "pa", "lv",
})


class TestSelectPluralCategory:
    """Test main select_plural_category function with locale routing."""

    def test_latvian_locale_routes_to_latvian_rules(self) -> None:
        """Latvian locale code routes to Latvian plural rules."""
        result = select_plural_category(0, "lv_LV")
        assert result == "zero"  # Latvian-specific category

    def test_english_locale_routes_to_english_rules(self) -> None:
        """English locale code routes to English plural rules."""
        result = select_plural_category(1, "en_US")
        assert result == "one"

    def test_german_locale_routes_to_german_rules(self) -> None:
        """German locale code routes to German plural rules."""
        result = select_plural_category(1, "de_DE")
        assert result == "one"

    def test_polish_locale_routes_to_polish_rules(self) -> None:
        """Polish locale code routes to Polish plural rules."""
        result = select_plural_category(2, "pl_PL")
        assert result == "few"  # Polish-specific category

    def test_unknown_locale_falls_back_to_cldr_root(self) -> None:
        """Unknown locale falls back to CLDR root (always 'other')."""
        # CLDR root locale returns "other" for all values - the safest
        # default that makes no language-specific assumptions.
        result = select_plural_category(1, "unknown_UNKNOWN")
        assert result == "other"

        result = select_plural_category(5, "unknown_UNKNOWN")
        assert result == "other"

    def test_locale_case_insensitive(self) -> None:
        """Locale code extraction is case-insensitive."""
        result_upper = select_plural_category(0, "LV_LV")
        result_lower = select_plural_category(0, "lv_lv")
        result_mixed = select_plural_category(0, "Lv_LV")

        assert result_upper == "zero"
        assert result_lower == "zero"
        assert result_mixed == "zero"

    def test_short_locale_code_without_region(self) -> None:
        """Short locale codes (without region) work correctly."""
        result = select_plural_category(0, "lv")
        assert result == "zero"

    def test_bcp47_hyphen_format_supported(self) -> None:
        """BCP-47 format with hyphens (en-US) works correctly."""
        result = select_plural_category(1, "en-US")
        assert result == "one"

        result = select_plural_category(0, "lv-LV")
        assert result == "zero"


class TestLatvianPluralRule:
    """Test Latvian plural rules (3 categories: zero, one, other)."""

    def test_zero_category_for_zero(self) -> None:
        """Zero uses 'zero' category."""
        assert select_plural_category(0, "lv") == "zero"

    def test_zero_category_for_multiples_of_10(self) -> None:
        """Multiples of 10 use 'zero' category."""
        assert select_plural_category(10, "lv") == "zero"
        assert select_plural_category(20, "lv") == "zero"
        assert select_plural_category(30, "lv") == "zero"
        assert select_plural_category(100, "lv") == "zero"
        assert select_plural_category(1000, "lv") == "zero"

    def test_zero_category_for_11_to_19(self) -> None:
        """Numbers 11-19 use 'zero' category."""
        for n in range(11, 20):
            assert select_plural_category(n, "lv") == "zero", f"Failed for {n}"

    def test_zero_category_for_numbers_ending_11_to_19(self) -> None:
        """Numbers ending in 11-19 (like 111, 211, 311) use 'zero'."""
        assert select_plural_category(111, "lv") == "zero"
        assert select_plural_category(112, "lv") == "zero"
        assert select_plural_category(211, "lv") == "zero"
        assert select_plural_category(1011, "lv") == "zero"

    def test_one_category_for_one(self) -> None:
        """One uses 'one' category."""
        assert select_plural_category(1, "lv") == "one"

    def test_one_category_for_numbers_ending_in_1_not_11(self) -> None:
        """Numbers ending in 1 (except 11) use 'one' category."""
        assert select_plural_category(21, "lv") == "one"
        assert select_plural_category(31, "lv") == "one"
        assert select_plural_category(41, "lv") == "one"
        assert select_plural_category(101, "lv") == "one"
        assert select_plural_category(1001, "lv") == "one"

    def test_other_category_for_2_to_9(self) -> None:
        """Numbers 2-9 use 'other' category."""
        for n in range(2, 10):
            assert select_plural_category(n, "lv") == "other", f"Failed for {n}"

    def test_other_category_for_numbers_ending_2_to_9(self) -> None:
        """Numbers ending in 2-9 use 'other' category."""
        assert select_plural_category(22, "lv") == "other"
        assert select_plural_category(23, "lv") == "other"
        assert select_plural_category(102, "lv") == "other"
        assert select_plural_category(1009, "lv") == "other"

    def test_float_non_whole_cldr_rules(self) -> None:
        """Non-whole floats follow CLDR decimal rules (v0.9.0: Babel implementation).

        v0.9.0: Updated to match Babel's CLDR-compliant rules.
        Latvian CLDR rules for decimals are complex and depend on:
        - v (number of visible fraction digits)
        - f (visible fraction digits)
        - The fraction ending pattern

        Examples:
        - 1.5 → 'other' (fraction ends in 5, not 1)
        - 2.3 → 'other' (fraction ends in 3, not 1)
        - 10.1 → 'one' (fraction ends in 1: v not in 2 and f mod 10 in 1)
        """
        assert select_plural_category(1.5, "lv") == "other"
        assert select_plural_category(2.3, "lv") == "other"
        assert select_plural_category(10.1, "lv") == "one"  # CLDR: fraction ends in 1


class TestEnglishPluralRule:
    """Test English plural rules (2 categories: one, other)."""

    def test_one_category_for_integer_one(self) -> None:
        """Integer 1 uses 'one' category."""
        assert select_plural_category(1, "en") == "one"

    def test_other_category_for_zero(self) -> None:
        """Zero uses 'other' category."""
        assert select_plural_category(0, "en") == "other"

    def test_other_category_for_plural_numbers(self) -> None:
        """All numbers except 1 use 'other' category."""
        assert select_plural_category(2, "en") == "other"
        assert select_plural_category(5, "en") == "other"
        assert select_plural_category(100, "en") == "other"
        assert select_plural_category(1000, "en") == "other"

    def test_float_with_decimals_uses_other(self) -> None:
        """1.0 as exact float uses 'other' (has visible decimals), 1 uses 'one'."""
        # Integer-one rule: i=1 and v=0 (no visible decimals)
        assert select_plural_category(1, "en") == "one"
        assert select_plural_category(1.5, "en") == "other"
        assert select_plural_category(2.0, "en") == "other"


class TestGermanPluralRule:
    """Test German plural rules (2 categories: one, other - same as English)."""

    def test_one_category_for_one(self) -> None:
        """One uses 'one' category."""
        assert select_plural_category(1, "de") == "one"

    def test_other_category_for_zero(self) -> None:
        """Zero uses 'other' category."""
        assert select_plural_category(0, "de") == "other"

    def test_other_category_for_plural_numbers(self) -> None:
        """All numbers except 1 use 'other' category."""
        assert select_plural_category(2, "de") == "other"
        assert select_plural_category(5, "de") == "other"
        assert select_plural_category(100, "de") == "other"


class TestPolishPluralRule:
    """Test Polish plural rules (4 categories: one, few, many, other)."""

    def test_one_category_for_one(self) -> None:
        """One uses 'one' category."""
        assert select_plural_category(1, "pl") == "one"

    def test_few_category_for_2_to_4(self) -> None:
        """Numbers 2, 3, 4 use 'few' category."""
        assert select_plural_category(2, "pl") == "few"
        assert select_plural_category(3, "pl") == "few"
        assert select_plural_category(4, "pl") == "few"

    def test_few_category_for_numbers_ending_2_to_4_not_12_to_14(self) -> None:
        """Numbers ending in 2-4 (except 12-14) use 'few' category."""
        assert select_plural_category(22, "pl") == "few"
        assert select_plural_category(23, "pl") == "few"
        assert select_plural_category(24, "pl") == "few"
        assert select_plural_category(32, "pl") == "few"
        assert select_plural_category(102, "pl") == "few"

    def test_many_category_for_zero(self) -> None:
        """Zero uses 'many' category."""
        assert select_plural_category(0, "pl") == "many"

    def test_many_category_for_5_to_9(self) -> None:
        """Numbers 5-9 use 'many' category."""
        for n in range(5, 10):
            assert select_plural_category(n, "pl") == "many", f"Failed for {n}"

    def test_many_category_for_10(self) -> None:
        """Ten uses 'many' category."""
        assert select_plural_category(10, "pl") == "many"

    def test_many_category_for_11_to_14(self) -> None:
        """Numbers 11-14 use 'many' category."""
        assert select_plural_category(11, "pl") == "many"
        assert select_plural_category(12, "pl") == "many"
        assert select_plural_category(13, "pl") == "many"
        assert select_plural_category(14, "pl") == "many"

    def test_many_category_for_numbers_ending_12_to_14(self) -> None:
        """Numbers ending in 12-14 use 'many' category (exception to few rule)."""
        assert select_plural_category(112, "pl") == "many"
        assert select_plural_category(212, "pl") == "many"
        assert select_plural_category(1012, "pl") == "many"

    def test_many_category_for_numbers_ending_5_to_9(self) -> None:
        """Numbers ending in 5-9 use 'many' category."""
        assert select_plural_category(15, "pl") == "many"
        assert select_plural_category(25, "pl") == "many"
        assert select_plural_category(105, "pl") == "many"

    def test_many_category_for_multiples_of_10(self) -> None:
        """Multiples of 10 use 'many' category."""
        assert select_plural_category(20, "pl") == "many"
        assert select_plural_category(100, "pl") == "many"
        assert select_plural_category(1000, "pl") == "many"

    def test_other_category_for_fractions(self) -> None:
        """Fractions use 'other' category."""
        assert select_plural_category(1.5, "pl") == "other"
        assert select_plural_category(2.3, "pl") == "other"
        assert select_plural_category(10.1, "pl") == "other"


class TestRussianPluralRule:
    """Test Russian plural rules (4 categories: one, few, many, other)."""

    def test_one_category_for_numbers_ending_1_not_11(self) -> None:
        """Numbers ending in 1 (except 11) use 'one' category."""
        assert select_plural_category(1, "ru") == "one"
        assert select_plural_category(21, "ru") == "one"
        assert select_plural_category(31, "ru") == "one"
        assert select_plural_category(101, "ru") == "one"

    def test_few_category_for_2_to_4(self) -> None:
        """Numbers ending in 2-4 (except 12-14) use 'few' category."""
        assert select_plural_category(2, "ru") == "few"
        assert select_plural_category(3, "ru") == "few"
        assert select_plural_category(4, "ru") == "few"
        assert select_plural_category(22, "ru") == "few"
        assert select_plural_category(23, "ru") == "few"

    def test_many_category_for_0_5_to_20(self) -> None:
        """0, 5-20 use 'many' category."""
        assert select_plural_category(0, "ru") == "many"
        assert select_plural_category(5, "ru") == "many"
        assert select_plural_category(11, "ru") == "many"
        assert select_plural_category(12, "ru") == "many"
        assert select_plural_category(20, "ru") == "many"

    def test_other_for_fractions(self) -> None:
        """Fractions use 'other' category."""
        assert select_plural_category(1.5, "ru") == "other"


class TestUkrainianPluralRule:
    """Test Ukrainian plural rules (4 categories: one, few, many, other)."""

    def test_one_category(self) -> None:
        """Numbers ending in 1 (except 11) use 'one' category."""
        assert select_plural_category(1, "uk") == "one"
        assert select_plural_category(21, "uk") == "one"
        assert select_plural_category(101, "uk") == "one"

    def test_few_category(self) -> None:
        """Numbers ending in 2-4 (except 12-14) use 'few' category."""
        assert select_plural_category(2, "uk") == "few"
        assert select_plural_category(3, "uk") == "few"
        assert select_plural_category(22, "uk") == "few"

    def test_many_category(self) -> None:
        """0, 5-20, numbers ending in 0/5-9 use 'many' category."""
        assert select_plural_category(0, "uk") == "many"
        assert select_plural_category(5, "uk") == "many"
        assert select_plural_category(11, "uk") == "many"


class TestArabicPluralRule:
    """Test Arabic plural rules (6 categories - most complex)."""

    def test_zero_category(self) -> None:
        """Zero uses 'zero' category."""
        assert select_plural_category(0, "ar") == "zero"

    def test_one_category(self) -> None:
        """One uses 'one' category."""
        assert select_plural_category(1, "ar") == "one"

    def test_two_category(self) -> None:
        """Two uses 'two' category."""
        assert select_plural_category(2, "ar") == "two"

    def test_few_category_for_3_to_10(self) -> None:
        """Numbers 3-10 use 'few' category."""
        for n in range(3, 11):
            assert select_plural_category(n, "ar") == "few", f"Failed for {n}"

    def test_few_category_for_numbers_ending_3_to_10(self) -> None:
        """Numbers ending in 03-10 use 'few' category."""
        assert select_plural_category(103, "ar") == "few"
        assert select_plural_category(110, "ar") == "few"

    def test_many_category_for_11_to_99(self) -> None:
        """Numbers 11-99 use 'many' category."""
        assert select_plural_category(11, "ar") == "many"
        assert select_plural_category(50, "ar") == "many"
        assert select_plural_category(99, "ar") == "many"

    def test_many_category_for_numbers_ending_11_to_99(self) -> None:
        """Numbers ending in 11-99 use 'many' category."""
        assert select_plural_category(111, "ar") == "many"
        assert select_plural_category(199, "ar") == "many"

    def test_other_category_for_100_200_etc(self) -> None:
        """100, 200, etc. use 'other' category."""
        assert select_plural_category(100, "ar") == "other"
        assert select_plural_category(200, "ar") == "other"
        assert select_plural_category(1000, "ar") == "other"


class TestNoPluralLanguages:
    """Test languages with no plural distinctions (always 'other')."""

    def test_chinese_always_other(self) -> None:
        """Chinese (zh) always uses 'other'."""
        assert select_plural_category(0, "zh") == "other"
        assert select_plural_category(1, "zh") == "other"
        assert select_plural_category(2, "zh") == "other"
        assert select_plural_category(100, "zh") == "other"

    def test_japanese_always_other(self) -> None:
        """Japanese (ja) always uses 'other'."""
        assert select_plural_category(0, "ja") == "other"
        assert select_plural_category(1, "ja") == "other"
        assert select_plural_category(100, "ja") == "other"

    def test_korean_always_other(self) -> None:
        """Korean (ko) always uses 'other'."""
        assert select_plural_category(0, "ko") == "other"
        assert select_plural_category(1, "ko") == "other"
        assert select_plural_category(100, "ko") == "other"

    def test_vietnamese_always_other(self) -> None:
        """Vietnamese (vi) always uses 'other'."""
        assert select_plural_category(0, "vi") == "other"
        assert select_plural_category(1, "vi") == "other"

    def test_thai_always_other(self) -> None:
        """Thai (th) always uses 'other'."""
        assert select_plural_category(0, "th") == "other"
        assert select_plural_category(1, "th") == "other"

    def test_burmese_always_other(self) -> None:
        """Burmese (my) always uses 'other'."""
        assert select_plural_category(0, "my") == "other"
        assert select_plural_category(1, "my") == "other"

    def test_javanese_always_other(self) -> None:
        """Javanese (jv) always uses 'other'."""
        assert select_plural_category(0, "jv") == "other"
        assert select_plural_category(1, "jv") == "other"


class TestSimpleOneLanguages:
    """Test languages with simple n=1 rule (Spanish, Telugu, etc.)."""

    def test_spanish_one_other(self) -> None:
        """Spanish uses simple one/other."""
        assert select_plural_category(1, "es") == "one"
        assert select_plural_category(0, "es") == "other"
        assert select_plural_category(2, "es") == "other"

    def test_telugu_one_other(self) -> None:
        """Telugu uses simple one/other."""
        assert select_plural_category(1, "te") == "one"
        assert select_plural_category(0, "te") == "other"
        assert select_plural_category(2, "te") == "other"

    def test_turkish_one_other(self) -> None:
        """Turkish uses simple one/other."""
        assert select_plural_category(1, "tr") == "one"
        assert select_plural_category(0, "tr") == "other"
        assert select_plural_category(2, "tr") == "other"

    def test_tamil_one_other(self) -> None:
        """Tamil uses simple one/other."""
        assert select_plural_category(1, "ta") == "one"
        assert select_plural_category(0, "ta") == "other"

    def test_marathi_one_other(self) -> None:
        """Marathi uses simple one/other."""
        assert select_plural_category(1, "mr") == "one"
        assert select_plural_category(0, "mr") == "other"

    def test_urdu_one_other(self) -> None:
        """Urdu uses simple one/other."""
        assert select_plural_category(1, "ur") == "one"
        assert select_plural_category(0, "ur") == "other"

    def test_malayalam_one_other(self) -> None:
        """Malayalam uses simple one/other."""
        assert select_plural_category(1, "ml") == "one"
        assert select_plural_category(0, "ml") == "other"

    def test_odia_one_other(self) -> None:
        """Odia uses simple one/other."""
        assert select_plural_category(1, "or") == "one"
        assert select_plural_category(0, "or") == "other"


class TestZeroOneLanguages:
    """Test languages where i=0 or n=1 gives 'one' (Hindi, Bengali, etc.)."""

    def test_hindi_zero_or_one(self) -> None:
        """Hindi: 0 and 1 both use 'one', others use 'other'."""
        assert select_plural_category(0, "hi") == "one"
        assert select_plural_category(1, "hi") == "one"
        assert select_plural_category(0.5, "hi") == "one"  # i=0
        assert select_plural_category(2, "hi") == "other"

    def test_bengali_zero_or_one(self) -> None:
        """Bengali: 0 and 1 both use 'one'."""
        assert select_plural_category(0, "bn") == "one"
        assert select_plural_category(1, "bn") == "one"
        assert select_plural_category(2, "bn") == "other"

    def test_gujarati_zero_or_one(self) -> None:
        """Gujarati: 0 and 1 both use 'one'."""
        assert select_plural_category(0, "gu") == "one"
        assert select_plural_category(1, "gu") == "one"
        assert select_plural_category(2, "gu") == "other"

    def test_kannada_zero_or_one(self) -> None:
        """Kannada: 0 and 1 both use 'one'."""
        assert select_plural_category(0, "kn") == "one"
        assert select_plural_category(1, "kn") == "one"
        assert select_plural_category(2, "kn") == "other"


class TestPunjabiPluralRule:
    """Test Punjabi plural rules (one for 0 and 1)."""

    def test_one_for_zero_and_one(self) -> None:
        """Punjabi uses 'one' for both 0 and 1."""
        assert select_plural_category(0, "pa") == "one"
        assert select_plural_category(1, "pa") == "one"

    def test_other_for_larger_numbers(self) -> None:
        """Punjabi uses 'other' for 2+."""
        assert select_plural_category(2, "pa") == "other"
        assert select_plural_category(10, "pa") == "other"


class TestRomanceManyLanguages:
    """Test Romance languages with 'many' category (French, Portuguese, Italian)."""

    def test_french_one_for_0_and_1(self) -> None:
        """French uses 'one' for i=0 or i=1."""
        assert select_plural_category(0, "fr") == "one"
        assert select_plural_category(1, "fr") == "one"
        assert select_plural_category(1.5, "fr") == "one"  # i=1

    def test_french_other_for_most_numbers(self) -> None:
        """French uses 'other' for most numbers."""
        assert select_plural_category(2, "fr") == "other"
        assert select_plural_category(100, "fr") == "other"

    def test_french_many_for_millions(self) -> None:
        """French uses 'many' for exact millions."""
        assert select_plural_category(1_000_000, "fr") == "many"
        assert select_plural_category(2_000_000, "fr") == "many"

    def test_portuguese_one_for_0_and_1(self) -> None:
        """Portuguese uses 'one' for i=0 or i=1."""
        assert select_plural_category(0, "pt") == "one"
        assert select_plural_category(1, "pt") == "one"

    def test_portuguese_many_for_millions(self) -> None:
        """Portuguese uses 'many' for exact millions."""
        assert select_plural_category(1_000_000, "pt") == "many"

    def test_italian_one_for_1(self) -> None:
        """Italian uses 'one' for i=1 and v=0 (v0.9.0: Babel CLDR implementation).

        v0.9.0: Updated to match Babel's CLDR-compliant rules.
        Italian CLDR rule: 'one' applies when i in 1 and v in 0
        This means only integer 1 gets 'one', zero gets 'other'.
        """
        assert select_plural_category(0, "it") == "other"  # CLDR: 0 is not 1
        assert select_plural_category(1, "it") == "one"

    def test_italian_many_for_millions(self) -> None:
        """Italian uses 'many' for exact millions."""
        assert select_plural_category(1_000_000, "it") == "many"


class TestSupportedLocales:
    """Test the TEST_LOCALES constant."""

    def test_supported_locales_count(self) -> None:
        """30 test locales are defined."""
        assert len(TEST_LOCALES) == 30

    def test_all_top_30_languages_supported(self) -> None:
        """All top 30 languages by speakers are in TEST_LOCALES."""
        expected = {
            "en", "zh", "hi", "es", "fr", "ar", "bn", "pt", "ru", "ja",
            "de", "jv", "ko", "vi", "te", "tr", "ta", "mr", "ur", "it",
            "th", "gu", "pl", "uk", "kn", "or", "ml", "my", "pa", "lv",
        }
        assert expected == TEST_LOCALES


class TestPluralRulesIntegration:
    """Integration tests for plural rules across locales."""

    def test_latvian_comprehensive_coverage(self) -> None:
        """Comprehensive test of Latvian rules with representative numbers."""
        # zero category
        zero_numbers = [0, 10, 11, 12, 13, 19, 20, 30, 100, 111, 1000]
        for n in zero_numbers:
            assert select_plural_category(n, "lv") == "zero", f"Failed for {n}"

        # one category
        one_numbers = [1, 21, 31, 41, 51, 101, 1001]
        for n in one_numbers:
            assert select_plural_category(n, "lv") == "one", f"Failed for {n}"

        # other category
        other_numbers = [2, 3, 4, 5, 6, 7, 8, 9, 22, 23, 102]
        for n in other_numbers:
            assert select_plural_category(n, "lv") == "other", f"Failed for {n}"

    def test_polish_comprehensive_coverage(self) -> None:
        """Comprehensive test of Polish rules with representative numbers."""
        # one
        assert select_plural_category(1, "pl") == "one"

        # few
        few_numbers = [2, 3, 4, 22, 23, 24, 32, 102, 104]
        for n in few_numbers:
            assert select_plural_category(n, "pl") == "few", f"Failed for {n}"

        # many
        many_numbers = [0, 5, 6, 7, 11, 12, 13, 14, 15, 20, 25, 100, 112, 1000]
        for n in many_numbers:
            assert select_plural_category(n, "pl") == "many", f"Failed for {n}"

    def test_all_locales_handle_fractions_consistently(self) -> None:
        """All test locales handle fractional numbers without crashing."""
        for locale in TEST_LOCALES:
            result = select_plural_category(1.5, locale)
            assert result in {"zero", "one", "two", "few", "many", "other"}
