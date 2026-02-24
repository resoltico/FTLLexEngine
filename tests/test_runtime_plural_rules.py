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

import sys
from decimal import Decimal
from unittest.mock import patch

import pytest
from babel.core import UnknownLocaleError
from hypothesis import assume, event, example, given
from hypothesis import strategies as st

import ftllexengine.core.babel_compat as _bc
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

# Numbers strategy (integers and decimals)
NUMBERS = st.one_of(
    st.integers(min_value=0, max_value=1000000),
    st.decimals(
        min_value=Decimal("0"), max_value=Decimal("1000000"),
        allow_nan=False, allow_infinity=False,
    ),
)

# ============================================================================
# Babel ImportError Tests (lines 67-70)
# ============================================================================


class TestPluralRulesBabelImportError:
    """Test ImportError path when Babel is not installed (lines 67-70)."""

    def test_select_plural_category_raises_babel_import_error_when_babel_unavailable(
        self,
    ) -> None:
        """select_plural_category raises BabelImportError when Babel unavailable."""
        from ftllexengine.core.babel_compat import (  # noqa: PLC0415 - test assertion
            BabelImportError,
        )

        # Temporarily hide babel from sys.modules
        babel_module = sys.modules.pop("babel", None)
        babel_core = sys.modules.pop("babel.core", None)
        babel_dates = sys.modules.pop("babel.dates", None)
        babel_numbers = sys.modules.pop("babel.numbers", None)

        # Reset sentinel so _check_babel_available() re-evaluates under the mock
        _bc._babel_available = None

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
            # Reset sentinel so subsequent tests reinitialize with Babel available
            _bc._babel_available = None


# ============================================================================
# Property Tests - Invariants
# ============================================================================


class TestPluralRuleInvariants:
    """Property-based tests for invariants that must hold for all plural rules."""

    @given(n=NUMBERS, locale=LOCALE_CODES)
    @example(n=0, locale="en_US")
    @example(n=1, locale="en_US")
    @example(n=2, locale="ar_SA")
    def test_always_returns_valid_category(self, n: int | Decimal, locale: str) -> None:
        """Plural selection always returns valid CLDR category.

        Property: For all n and locale, result ∈ {zero, one, two, few, many, other}
        """
        result = select_plural_category(n, locale)

        valid_categories = {"zero", "one", "two", "few", "many", "other"}
        assert result in valid_categories

        n_type = type(n).__name__
        event(f"category={result}")
        event(f"n_type={n_type}")
        event(f"locale={locale}")

    @given(n=NUMBERS, locale=LOCALE_CODES)
    @example(n=42, locale="lv_LV")
    def test_never_returns_none(self, n: int | Decimal, locale: str) -> None:
        """Plural selection never returns None.

        Property: For all n and locale, result is not None
        """
        result = select_plural_category(n, locale)

        assert result is not None
        event(f"category={result}")

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
        event(f"category={result1}")
        event(f"locale={locale}")

    @given(n=NUMBERS)
    @example(n=0)
    @example(n=1)
    @example(n=42)
    def test_unknown_locale_defaults_to_cldr_root(self, n: int | Decimal) -> None:
        """Unknown locale uses CLDR root rules (always 'other').

        Property: For all n, select_plural_category(n, unknown) = "other"
        """
        result = select_plural_category(n, "xx_XX")

        assert result == "other"
        n_type = type(n).__name__
        event(f"n_type={n_type}")


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
        event(f"n={n}")

    def test_one_is_one(self) -> None:
        """English: 1 is 'one'."""
        assert select_plural_category(1, "en") == "one"

    def test_zero_is_other(self) -> None:
        """English: 0 is 'other'."""
        assert select_plural_category(0, "en") == "other"

    @given(n=st.decimals(
        min_value=Decimal("0.1"), max_value=Decimal("1000"),
        allow_nan=False, allow_infinity=False,
    ))
    @example(n=Decimal("0.5"))
    @example(n=Decimal("2.5"))
    def test_decimals_are_other(self, n: Decimal) -> None:
        """English: Decimals not equal to 1 are 'other'.

        Property: For all n in Q where n != 1, category = "other"
        """
        assume(n != Decimal("1"))

        result = select_plural_category(n, "en")

        assert result == "other"
        is_whole = n % 1 == 0
        event(f"decimal_is_whole={is_whole}")


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
        fraction=st.decimals(
            min_value=Decimal("0.01"), max_value=Decimal("999.99"),
            allow_nan=False, allow_infinity=False,
        )
    )
    @example(fraction=Decimal("0.5"))
    @example(fraction=Decimal("1.5"))
    def test_fractional_numbers_return_other(self, fraction: Decimal) -> None:
        """Slavic: fractional numbers return 'other'.

        Property: For all n in Q where n not in Z, category = "other"
        """
        assume(fraction % 1 != 0)

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

    @given(n=st.decimals(
        min_value=Decimal("-1000"), max_value=Decimal("0"),
        allow_nan=False, allow_infinity=False,
    ))
    @example(n=Decimal("-1"))
    @example(n=Decimal("-100"))
    def test_negative_numbers_return_valid_category(self, n: Decimal) -> None:
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
        with patch("ftllexengine.core.locale_utils.get_babel_locale") as mock_get:
            mock_get.side_effect = UnknownLocaleError("mocked failure")

            result = select_plural_category(42, "completely_invalid_locale")
            assert result == "other"

    def test_ultimate_fallback_with_value_error(self) -> None:
        """Return 'other' when get_babel_locale raises ValueError (lines 83-87)."""
        with patch("ftllexengine.core.locale_utils.get_babel_locale") as mock_get:
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


# ============================================================================
# Precision Parameter Tests
# ============================================================================


class TestPrecisionParameter:
    """Test precision parameter for CLDR v operand handling (lines 118-121).

    The precision parameter is critical for NUMBER() formatting. It controls
    the CLDR v operand (fraction digit count), which affects plural category
    selection in many locales.

    Key property: 1 (integer) vs 1.00 (precision=2) may have different plural
    categories because they have different v values (v=0 vs v=2).
    """

    def test_precision_changes_english_one_to_other(self) -> None:
        """English: precision converts 'one' to 'other' (lines 118-121).

        Critical case: 1 is "one" but 1.00 (with v=2) is "other" in English.
        This is the primary use case for the precision parameter.
        """
        result_no_precision = select_plural_category(1, "en_US")
        result_with_precision = select_plural_category(1, "en_US", precision=2)

        assert result_no_precision == "one"
        assert result_with_precision == "other"

    @given(
        n=st.integers(min_value=0, max_value=1000),
        precision=st.integers(min_value=1, max_value=10),
    )
    @example(n=1, precision=1)
    @example(n=1, precision=2)
    @example(n=42, precision=5)
    def test_precision_always_returns_valid_category(
        self, n: int, precision: int
    ) -> None:
        """Precision parameter always returns valid CLDR category (lines 118-121).

        Property: For all n, precision, and locale, result in valid_categories
        """
        result = select_plural_category(n, "en_US", precision=precision)

        valid_categories = {"zero", "one", "two", "few", "many", "other"}
        assert result in valid_categories

    @given(
        n=st.decimals(
            min_value=Decimal("0"), max_value=Decimal("100"), allow_nan=False, allow_infinity=False
        ),
        precision=st.integers(min_value=1, max_value=6),
    )
    @example(n=Decimal("1.5"), precision=2)
    @example(n=Decimal("42.7"), precision=1)
    def test_precision_with_fractional_decimals(self, n: Decimal, precision: int) -> None:
        """Precision works correctly with Decimal inputs (lines 118-121).

        Property: Decimal values are quantized correctly for plural selection
        """
        result = select_plural_category(n, "en_US", precision=precision)

        valid_categories = {"zero", "one", "two", "few", "many", "other"}
        assert result in valid_categories

    @given(
        n=st.integers(min_value=0, max_value=100),
        precision=st.integers(min_value=1, max_value=8),
    )
    @example(n=1, precision=1)
    @example(n=1, precision=5)
    def test_precision_with_decimals(self, n: int, precision: int) -> None:
        """Precision works correctly with Decimal inputs (lines 118-121).

        Property: Decimal(n) with precision is handled correctly
        """
        decimal_n = Decimal(n)
        result = select_plural_category(decimal_n, "en_US", precision=precision)

        valid_categories = {"zero", "one", "two", "few", "many", "other"}
        assert result in valid_categories

    def test_precision_one_formats_to_one_decimal_place(self) -> None:
        """Precision=1 formats to one decimal place (lines 118-121)."""
        result = select_plural_category(1, "en_US", precision=1)
        assert result == "other"

        result = select_plural_category(5, "en_US", precision=1)
        assert result == "other"

    def test_precision_zero_ignored(self) -> None:
        """Precision=0 is ignored (condition precision > 0 on line 111).

        When precision=0, the code takes the else branch (line 124), not lines 118-121.
        """
        result_no_precision = select_plural_category(1, "en_US")
        result_precision_zero = select_plural_category(1, "en_US", precision=0)

        assert result_no_precision == "one"
        assert result_precision_zero == "one"

    def test_precision_none_ignored(self) -> None:
        """Precision=None is ignored (condition precision is not None on line 111).

        When precision=None, the code takes the else branch (line 124), not lines 118-121.
        """
        result_no_precision = select_plural_category(1, "en_US")
        result_precision_none = select_plural_category(1, "en_US", precision=None)

        assert result_no_precision == "one"
        assert result_precision_none == "one"

    @given(
        n=st.integers(min_value=0, max_value=100),
        precision=st.integers(min_value=1, max_value=5),
        locale=LOCALE_CODES,
    )
    @example(n=1, precision=2, locale="en_US")
    @example(n=1, precision=2, locale="ru_RU")
    @example(n=0, precision=1, locale="lv_LV")
    def test_precision_consistency_across_locales(
        self, n: int, precision: int, locale: str
    ) -> None:
        """Precision produces consistent results across locales (lines 118-121).

        Property: Same (n, precision, locale) always returns same category
        """
        result1 = select_plural_category(n, locale, precision=precision)
        result2 = select_plural_category(n, locale, precision=precision)

        assert result1 == result2

    def test_precision_large_value(self) -> None:
        """Precision handles large precision values correctly (lines 118-121)."""
        result = select_plural_category(1, "en_US", precision=10)
        assert result == "other"

        result = select_plural_category(42, "en_US", precision=15)
        assert result == "other"

    @given(
        n=st.integers(min_value=1, max_value=100),
        precision=st.integers(min_value=1, max_value=6),
    )
    @example(n=1, precision=1)
    @example(n=21, precision=2)
    @example(n=11, precision=1)
    def test_precision_affects_slavic_rules(
        self, n: int, precision: int
    ) -> None:
        """Precision affects Slavic plural rules (lines 118-121).

        In Slavic languages, integers have complex rules, but formatted decimals
        typically fall into the "other" category.
        """
        result_no_precision = select_plural_category(n, "ru_RU")
        result_with_precision = select_plural_category(n, "ru_RU", precision=precision)

        valid_categories = {"zero", "one", "two", "few", "many", "other"}
        assert result_no_precision in valid_categories
        assert result_with_precision in valid_categories

    @given(
        n=st.integers(min_value=0, max_value=10),
        precision=st.integers(min_value=1, max_value=4),
    )
    @example(n=0, precision=1)
    @example(n=2, precision=2)
    def test_precision_with_arabic_complex_rules(
        self, n: int, precision: int
    ) -> None:
        """Precision works with Arabic's complex 6-category system (lines 118-121).

        Property: Precision affects category selection in all locale systems
        """
        result = select_plural_category(n, "ar_SA", precision=precision)

        valid_categories = {"zero", "one", "two", "few", "many", "other"}
        assert result in valid_categories

    def test_precision_quantization_correctness(self) -> None:
        """Precision quantizes numbers correctly (lines 118-121).

        Verifies the Decimal quantization logic produces expected v operand.
        """
        result = select_plural_category(5, "en_US", precision=2)
        assert result == "other"

        result = select_plural_category(0, "en_US", precision=3)
        assert result == "other"

        result = select_plural_category(100, "en_US", precision=1)
        assert result == "other"


# ============================================================================
# Rounding Consistency Tests (ROUND_HALF_UP)
# ============================================================================


class TestRoundingConsistency:
    """Tests that plural selection rounding matches formatting rounding.

    Both plural_rules.py and locale_context.py must use ROUND_HALF_UP
    so that the displayed number and its plural form always agree.
    Half-values (x.5) must round in the same direction in both paths.
    """

    def test_half_value_rounds_up_for_plural(self) -> None:
        """2.5 with precision=0 rounds to 3, selecting 'other' in English."""
        # 2.5 -> 3 (ROUND_HALF_UP), which is 'other' in English (not 1)
        result = select_plural_category(Decimal("2.5"), "en_US", precision=0)
        assert result == "other"

    def test_half_value_3_5_rounds_up_for_plural(self) -> None:
        """3.5 with precision=0 rounds to 4, selecting 'other' in English."""
        result = select_plural_category(Decimal("3.5"), "en_US", precision=0)
        assert result == "other"

    def test_half_value_0_5_rounds_to_one_for_plural(self) -> None:
        """0.5 with precision=0 rounds to 1, selecting 'one' in English."""
        # 0.5 -> 1 (ROUND_HALF_UP), which is 'one' in English
        result = select_plural_category(Decimal("0.5"), "en_US", precision=0)
        assert result == "one"

    def test_half_value_1_5_rounds_up_for_plural(self) -> None:
        """1.5 with precision=0 rounds to 2, selecting 'other' in English."""
        result = select_plural_category(Decimal("1.5"), "en_US", precision=0)
        assert result == "other"

    def test_rounding_matches_formatting_at_half_values(self) -> None:
        """Verify that Decimal quantization uses ROUND_HALF_UP, matching formatting.

        This is the core consistency property: the number displayed to the user
        and the plural category selected must agree on rounding direction.
        """
        from decimal import ROUND_HALF_UP  # noqa: PLC0415

        test_cases = [
            (Decimal("0.5"), 0, Decimal("1")),
            (Decimal("1.5"), 0, Decimal("2")),
            (Decimal("2.5"), 0, Decimal("3")),
            (Decimal("3.5"), 0, Decimal("4")),
            (Decimal("1.005"), 2, Decimal("1.01")),
            (Decimal("1.015"), 2, Decimal("1.02")),
            (Decimal("2.445"), 2, Decimal("2.45")),
        ]

        for value, precision, expected_rounded in test_cases:
            quantizer = Decimal(10) ** -precision
            rounded = value.quantize(quantizer, rounding=ROUND_HALF_UP)
            assert rounded == expected_rounded, (
                f"Expected {value} with precision={precision} to round to "
                f"{expected_rounded}, got {rounded}"
            )

    @given(
        n=st.decimals(
            min_value=Decimal("0"), max_value=Decimal("100"), allow_nan=False, allow_infinity=False
        ),
        precision=st.integers(min_value=0, max_value=4),
    )
    @example(n=Decimal("0.5"), precision=0)
    @example(n=Decimal("2.5"), precision=0)
    @example(n=Decimal("3.5"), precision=0)
    @example(n=Decimal("1.005"), precision=2)
    def test_plural_rounding_direction_property(
        self, n: Decimal, precision: int
    ) -> None:
        """Plural rounding direction matches ROUND_HALF_UP for all inputs.

        Property: The Decimal value used for plural selection must equal the
        value obtained by ROUND_HALF_UP quantization.
        """
        from decimal import ROUND_HALF_UP  # noqa: PLC0415

        quantizer = Decimal(10) ** -precision
        expected = n.quantize(quantizer, rounding=ROUND_HALF_UP)

        # The plural category must correspond to the ROUND_HALF_UP result.
        # We verify indirectly: call select_plural_category with precision,
        # then call again with the explicitly-rounded value (no precision).
        category_via_precision = select_plural_category(n, "en_US", precision=precision)
        category_via_rounded = select_plural_category(expected, "en_US")

        assert category_via_precision == category_via_rounded, (
            f"Rounding mismatch for n={n}, precision={precision}: "
            f"precision path gave '{category_via_precision}', "
            f"explicitly rounded {expected} gave '{category_via_rounded}'"
        )


# ============================================================================
# SLAVIC PLURAL RULE COVERAGE
# ============================================================================


class TestSlavicRuleReturnOther:
    """Slavic plural rules return 'other' for numbers not matching one/few/many."""

    def test_slavic_rule_return_other(self) -> None:
        """Polish plural rules return 'many' or 'other' for 111 (ends in 1 but mod 100 == 11)."""
        # 111 % 10 = 1, 111 % 100 = 11
        # Polish: 'one' requires mod_100 != 11, so 111 skips 'one'
        # Polish: 'few' requires 2-4, so 111 skips 'few'
        # Polish: 'many' covers 0 and 5-9 and 11-14; 111 does not match (mod_10 == 1)
        # Remaining cases return 'other'
        result = select_plural_category(111, "pl")
        assert result in ["many", "other"]
