"""Tests for plural_rules.py - CLDR plural category selection using Babel.

Comprehensive property-based tests ensuring plural rule correctness across all locales
and number ranges. Critical for multilingual applications with proper pluralization.

Property-Based Testing Strategy:
    Uses Hypothesis to verify mathematical properties and CLDR compliance across
    locale families (Germanic, Slavic, Romance, Semitic, etc.).

Coverage:
    - All CLDR plural categories (zero, one, two, few, many, other)
    - 30+ representative locales across language families
    - Edge cases (unknown locales, large numbers, decimals)
    - Babel ImportError path for parser-only installations
"""

from __future__ import annotations

import math
import sys
from decimal import Decimal
from unittest.mock import patch

import pytest
from babel.core import UnknownLocaleError
from hypothesis import assume, example, given
from hypothesis import strategies as st

from ftllexengine.runtime.plural_rules import select_plural_category

# ============================================================================
# Hypothesis Strategies
# ============================================================================

# Valid locale codes across language families
LOCALE_CODES = st.sampled_from([
    "en", "en_US", "en_GB",
    "lv", "lv_LV",
    "de", "de_DE",
    "pl", "pl_PL",
    "ru", "ru_RU",
    "ar", "ar_SA",
    "fr", "fr_FR",
    "es", "es_ES",
    "it", "it_IT",
    "pt", "pt_PT", "pt_BR",
    "zh", "zh_CN",
    "ja", "ja_JP",
    "ko", "ko_KR",
    "hi", "hi_IN",
    "bn", "bn_BD",
    "vi", "vi_VN",
    "tr", "tr_TR",
    "th", "th_TH",
    "uk", "uk_UA",
])

# Numbers strategy (integers and floats)
NUMBERS = st.one_of(
    st.integers(min_value=0, max_value=1000000),
    st.floats(min_value=0.0, max_value=1000000.0, allow_nan=False, allow_infinity=False),
)

# ============================================================================
# Babel ImportError Tests (lines 67-70)
# ============================================================================


class TestPluralRulesBabelImportError:
    """Test ImportError path when Babel is not installed (lines 67-70)."""

    def test_select_plural_category_raises_babel_import_error_when_babel_unavailable(
        self,
    ) -> None:
        """select_plural_category raises BabelImportError when Babel unavailable (lines 67-70)."""
        from ftllexengine.core.babel_compat import (  # noqa: PLC0415 - test assertion
            BabelImportError,
        )

        # Temporarily hide babel from sys.modules
        babel_module = sys.modules.pop("babel", None)
        babel_core = sys.modules.pop("babel.core", None)
        babel_dates = sys.modules.pop("babel.dates", None)
        babel_numbers = sys.modules.pop("babel.numbers", None)

        try:
            with patch.dict(sys.modules, {"babel": None, "babel.core": None}):
                original_import = __import__

                def mock_import_babel(
                    name: str,
                    globals_dict: dict[str, object] | None = None,
                    locals_dict: dict[str, object] | None = None,
                    fromlist: tuple[str, ...] = (),
                    level: int = 0,
                ) -> object:
                    if name == "babel" or name.startswith("babel."):
                        msg = "Mocked: Babel not installed"
                        raise ImportError(msg)
                    return original_import(name, globals_dict, locals_dict, fromlist, level)

                with patch("builtins.__import__", side_effect=mock_import_babel):
                    with pytest.raises(BabelImportError) as exc_info:
                        select_plural_category(42, "en-US")

                    assert "select_plural_category" in str(exc_info.value)
        finally:
            # Restore babel modules
            if babel_module is not None:
                sys.modules["babel"] = babel_module
            if babel_core is not None:
                sys.modules["babel.core"] = babel_core
            if babel_dates is not None:
                sys.modules["babel.dates"] = babel_dates
            if babel_numbers is not None:
                sys.modules["babel.numbers"] = babel_numbers


# ============================================================================
# Property Tests - Invariants
# ============================================================================


class TestPluralRuleInvariants:
    """Property-based tests for invariants that must hold for all plural rules."""

    @given(n=NUMBERS, locale=LOCALE_CODES)
    @example(n=0, locale="en_US")
    @example(n=1, locale="en_US")
    @example(n=2, locale="ar_SA")
    def test_always_returns_valid_category(self, n: int | float, locale: str) -> None:
        """Plural selection always returns valid CLDR category.

        Property: For all n and locale, result ∈ {zero, one, two, few, many, other}
        """
        assume(not (isinstance(n, float) and math.isnan(n)))

        result = select_plural_category(n, locale)

        valid_categories = {"zero", "one", "two", "few", "many", "other"}
        assert result in valid_categories

    @given(n=NUMBERS, locale=LOCALE_CODES)
    @example(n=42, locale="lv_LV")
    def test_never_returns_none(self, n: int | float, locale: str) -> None:
        """Plural selection never returns None.

        Property: For all n and locale, result is not None
        """
        assume(not (isinstance(n, float) and math.isnan(n)))

        result = select_plural_category(n, locale)

        assert result is not None

    @given(n=st.integers(min_value=0, max_value=1000), locale=LOCALE_CODES)
    @example(n=1, locale="en_US")
    @example(n=5, locale="ru_RU")
    def test_integer_consistency(self, n: int, locale: str) -> None:
        """Same integer always returns same category for same locale.

        Property: f(n, locale) = f(n, locale) (idempotence)
        """
        result1 = select_plural_category(n, locale)
        result2 = select_plural_category(n, locale)

        assert result1 == result2

    @given(n=NUMBERS)
    @example(n=0)
    @example(n=1)
    @example(n=42)
    def test_unknown_locale_defaults_to_cldr_root(self, n: int | float) -> None:
        """Unknown locale uses CLDR root rules (always 'other').

        Property: For all n, select_plural_category(n, unknown) = "other"
        """
        assume(not (isinstance(n, float) and math.isnan(n)))

        result = select_plural_category(n, "xx_XX")

        assert result == "other"


# ============================================================================
# Property Tests - Locale-Specific Rules
# ============================================================================


class TestEnglishPluralRules:
    """Property-based tests for English plural rules (one/other)."""

    @given(n=st.integers(min_value=2, max_value=1000))
    @example(n=2)
    @example(n=100)
    def test_integers_not_one_are_other(self, n: int) -> None:
        """English: integers != 1 are 'other'.

        Property: For all n in Z where n != 1, category = "other"
        """
        assume(n != 1)

        result = select_plural_category(n, "en")

        assert result == "other"

    def test_one_is_one(self) -> None:
        """English: 1 is 'one'."""
        assert select_plural_category(1, "en") == "one"

    def test_zero_is_other(self) -> None:
        """English: 0 is 'other'."""
        assert select_plural_category(0, "en") == "other"

    @given(n=st.floats(min_value=0.1, max_value=1000.0, allow_nan=False))
    @example(n=0.5)
    @example(n=2.5)
    def test_floats_are_other(self, n: float) -> None:
        """English: all floats are 'other' (unless exactly 1.0).

        Property: For all n in R where n != 1.0, category = "other"
        """
        assume(n != 1.0)

        result = select_plural_category(n, "en")

        assert result == "other"


class TestLatvianPluralRules:
    """Property-based tests for Latvian plural rules (zero/one/other)."""

    def test_zero_is_zero(self) -> None:
        """Latvian: 0 is 'zero'."""
        assert select_plural_category(0, "lv") == "zero"

    @given(n=st.integers(min_value=1, max_value=1000))
    @example(n=1)
    @example(n=21)
    @example(n=11)
    def test_rules_consistency(self, n: int) -> None:
        """Latvian: rules are consistent with CLDR.

        Property: Category determined by modulo operations per CLDR spec
        """
        result = select_plural_category(n, "lv")

        i_mod_10 = n % 10
        i_mod_100 = n % 100

        if i_mod_10 == 0:
            assert result in {"zero", "other"}
        elif i_mod_10 == 1 and i_mod_100 != 11:
            assert result == "one"
        else:
            assert result in {"zero", "other"}


class TestSlavicPluralRules:
    """Property-based tests for Slavic languages (Russian, Polish)."""

    @given(n=st.integers(min_value=1, max_value=1000))
    @example(n=1)
    @example(n=21)
    @example(n=11)
    def test_one_rule(self, n: int) -> None:
        """Slavic: numbers ending in 1 (but not 11) are 'one'.

        Property: n % 10 = 1 AND n % 100 ≠ 11 => category = "one"
        """
        i_mod_10 = n % 10
        i_mod_100 = n % 100

        result = select_plural_category(n, "ru")

        if i_mod_10 == 1 and i_mod_100 != 11:
            assert result == "one"

    @given(n=st.integers(min_value=2, max_value=1000))
    @example(n=2)
    @example(n=22)
    @example(n=12)
    def test_few_rule(self, n: int) -> None:
        """Slavic: numbers ending in 2-4 (but not 12-14) are 'few'.

        Property: 2 ≤ n % 10 ≤ 4 AND NOT 12 ≤ n % 100 ≤ 14 => category = "few"
        """
        i_mod_10 = n % 10
        i_mod_100 = n % 100

        result = select_plural_category(n, "ru")

        if 2 <= i_mod_10 <= 4 and not 12 <= i_mod_100 <= 14:
            assert result == "few"

    @given(n=st.integers(min_value=5, max_value=1000))
    @example(n=5)
    @example(n=15)
    @example(n=100)
    def test_many_rule(self, n: int) -> None:
        """Slavic: specific patterns are 'many'.

        Property: (n % 10 = 0) OR (5 ≤ n % 10 ≤ 9) OR (11 ≤ n % 100 ≤ 14) => category = "many"
        """
        i_mod_10 = n % 10
        i_mod_100 = n % 100

        result = select_plural_category(n, "ru")

        if i_mod_10 == 0 or 5 <= i_mod_10 <= 9 or 11 <= i_mod_100 <= 14:
            assert result == "many"

    @given(
        fraction=st.floats(
            min_value=0.01, max_value=999.99, allow_nan=False, allow_infinity=False
        )
    )
    @example(fraction=0.5)
    @example(fraction=1.5)
    def test_fractional_numbers_return_other(self, fraction: float) -> None:
        """Slavic: fractional numbers return 'other'.

        Property: For all n in R where n not in Z, category = "other"
        """
        assume(not fraction.is_integer())

        category = select_plural_category(fraction, "ru_RU")

        assert category == "other"


class TestArabicPluralRules:
    """Property-based tests for Arabic plural rules (all 6 categories)."""

    def test_zero_is_zero(self) -> None:
        """Arabic: 0 is 'zero'."""
        assert select_plural_category(0, "ar") == "zero"

    def test_one_is_one(self) -> None:
        """Arabic: 1 is 'one'."""
        assert select_plural_category(1, "ar") == "one"

    def test_two_is_two(self) -> None:
        """Arabic: 2 is 'two'."""
        assert select_plural_category(2, "ar") == "two"

    @given(n=st.integers(min_value=3, max_value=10))
    @example(n=3)
    @example(n=10)
    def test_three_to_ten_are_few(self, n: int) -> None:
        """Arabic: 3-10 are 'few'.

        Property: 3 ≤ n ≤ 10 => category = "few"
        """
        result = select_plural_category(n, "ar")
        assert result == "few"

    @given(n=st.integers(min_value=11, max_value=99))
    @example(n=11)
    @example(n=99)
    def test_eleven_to_ninetynine_are_many(self, n: int) -> None:
        """Arabic: 11-99 are 'many'.

        Property: 11 ≤ n ≤ 99 => category = "many"
        """
        result = select_plural_category(n, "ar")
        assert result == "many"

    @given(n=st.integers(min_value=100, max_value=1000))
    @example(n=100)
    @example(n=500)
    def test_hundreds_valid_category(self, n: int) -> None:
        """Arabic: 100+ return valid category based on remainder.

        Property: For all n ≥ 100, category ∈ valid_categories
        """
        result = select_plural_category(n, "ar")
        assert result in {"zero", "one", "two", "few", "many", "other"}


# ============================================================================
# Property Tests - Edge Cases
# ============================================================================


class TestPluralRuleEdgeCases:
    """Property-based tests for edge cases."""

    @given(locale=st.text(min_size=1, max_size=10))
    @example(locale="invalid")
    @example(locale="xx_YY")
    def test_arbitrary_locale_never_crashes(self, locale: str) -> None:
        """Arbitrary locale never crashes.

        Property: For all locale strings, select_plural_category does not raise
        """
        result = select_plural_category(42, locale)
        assert isinstance(result, str)

    @given(n=st.floats(min_value=-1000.0, max_value=0.0, allow_nan=False))
    @example(n=-1.0)
    @example(n=-100.0)
    def test_negative_numbers_return_valid_category(self, n: float) -> None:
        """Negative numbers return valid category.

        Property: For all n < 0, category ∈ valid_categories
        """
        result = select_plural_category(n, "en")
        assert result in {"zero", "one", "two", "few", "many", "other"}

    @given(locale=LOCALE_CODES)
    @example(locale="en_US")
    @example(locale="ru_RU")
    def test_very_large_numbers(self, locale: str) -> None:
        """Very large numbers work correctly.

        Property: For all locales, large numbers return valid category
        """
        result = select_plural_category(10**9, locale)
        assert result in {"zero", "one", "two", "few", "many", "other"}


# ============================================================================
# Property Tests - Metamorphic Properties
# ============================================================================


class TestPluralRuleMetamorphic:
    """Metamorphic property tests."""

    @given(
        n=st.integers(min_value=0, max_value=1000),
        locale=st.sampled_from(["fr_FR", "it_IT", "pt_PT", "pt_BR"]),
    )
    @example(n=1, locale="fr_FR")
    @example(n=50, locale="it_IT")
    def test_adding_hundred_preserves_validity_for_romance(
        self, n: int, locale: str
    ) -> None:
        """For Romance languages, adding 100 preserves category validity.

        Metamorphic property: If f(n) is valid, then f(n+100) is also valid
        """
        result1 = select_plural_category(n, locale)
        result2 = select_plural_category(n + 100, locale)

        valid = {"zero", "one", "two", "few", "many", "other"}
        assert result1 in valid
        assert result2 in valid

    @given(n=st.integers(min_value=1, max_value=100))
    @example(n=1)
    @example(n=50)
    def test_english_german_similarity_for_small_numbers(self, n: int) -> None:
        """English and German have similar rules for small numbers.

        Metamorphic property: Both use only one/other categories
        """
        en_result = select_plural_category(n, "en")
        de_result = select_plural_category(n, "de")

        assert en_result in {"one", "other"}
        assert de_result in {"one", "other"}

        if n == 1:
            assert en_result == de_result == "one"


# ============================================================================
# Decimal Support Tests
# ============================================================================


class TestDecimalSupport:
    """Test Decimal type support in plural category selection."""

    @given(n=st.integers(min_value=0, max_value=1000))
    @example(n=0)
    @example(n=1)
    @example(n=5)
    def test_decimal_matches_integer(self, n: int) -> None:
        """Decimal and integer with same value produce same category.

        Property: For all n in Z, f(n) = f(Decimal(n))
        """
        int_result = select_plural_category(n, "en_US")
        decimal_result = select_plural_category(Decimal(n), "en_US")

        assert int_result == decimal_result

    def test_decimal_one_is_one(self) -> None:
        """Decimal(1) matches 'one' category in English."""
        result = select_plural_category(Decimal("1"), "en_US")
        assert result == "one"

    def test_decimal_zero_is_other(self) -> None:
        """Decimal(0) matches 'other' category in English."""
        result = select_plural_category(Decimal("0"), "en_US")
        assert result == "other"

    def test_decimal_fractional_is_other(self) -> None:
        """Decimal fractional values match 'other' category in English."""
        result = select_plural_category(Decimal("1.5"), "en_US")
        assert result == "other"


# ============================================================================
# Ultimate Fallback Tests
# ============================================================================


class TestUltimateFallback:
    """Test ultimate fallback when both locale and root fail."""

    def test_ultimate_fallback_when_root_locale_also_fails(self) -> None:
        """Return 'other' when even root locale loading fails (lines 83-87).

        This is defensive programming - should never happen with valid Babel installation.
        """
        with patch("ftllexengine.locale_utils.get_babel_locale") as mock_get:
            mock_get.side_effect = UnknownLocaleError("mocked failure")

            result = select_plural_category(42, "completely_invalid_locale")
            assert result == "other"

    def test_ultimate_fallback_with_value_error(self) -> None:
        """Return 'other' when get_babel_locale raises ValueError (lines 83-87)."""
        with patch("ftllexengine.locale_utils.get_babel_locale") as mock_get:
            mock_get.side_effect = ValueError("mocked failure")

            result = select_plural_category(1, "invalid")
            assert result == "other"

            result = select_plural_category(0, "invalid")
            assert result == "other"

            result = select_plural_category(100, "invalid")
            assert result == "other"


# ============================================================================
# Locale Format Tests
# ============================================================================


class TestLocaleFormats:
    """Test various locale code formats."""

    def test_locale_case_insensitive(self) -> None:
        """Locale code is case-insensitive."""
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
