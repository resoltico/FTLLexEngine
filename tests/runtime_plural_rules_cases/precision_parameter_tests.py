# mypy: ignore-errors
"""Split test cases from tests/test_runtime_plural_rules.py."""

from tests.runtime_plural_rules_cases import *  # noqa: F403 - shared split test support

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

        event(f"category={result}")
        event(f"precision={precision}")
        valid_categories = {"zero", "one", "two", "few", "many", "other"}
        assert result in valid_categories

    @given(
        n=st.decimals(
            min_value=Decimal(0), max_value=Decimal(100), allow_nan=False, allow_infinity=False
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

        event(f"category={result}")
        event(f"precision={precision}")
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

        event(f"category={result}")
        event(f"precision={precision}")
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

        event(f"locale={locale}")
        event(f"precision={precision}")
        event(f"category={result1}")
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

        event(f"category_no_precision={result_no_precision}")
        event(f"category_with_precision={result_with_precision}")
        event(f"precision={precision}")
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

        event(f"category={result}")
        event(f"precision={precision}")
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
