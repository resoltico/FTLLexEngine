# mypy: ignore-errors
"""Split test cases from tests/test_runtime_plural_rules.py."""

from tests.runtime_plural_rules_cases import *  # noqa: F403 - shared split test support

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
        min_value=Decimal("0.1"), max_value=Decimal(1000),
        allow_nan=False, allow_infinity=False,
    ))
    @example(n=Decimal("0.5"))
    @example(n=Decimal("2.5"))
    def test_decimals_are_other(self, n: Decimal) -> None:
        """English: Decimals not equal to 1 are 'other'.

        Property: For all n in Q where n != 1, category = "other"
        """
        assume(n != Decimal(1))

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

        event(f"category={result}")
        event(f"n_mod_10={i_mod_10}")
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

        event(f"category={result}")
        event(f"n_mod_10={i_mod_10}")
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

        event(f"category={result}")
        event(f"n_mod_10={i_mod_10}")
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

        event(f"category={result}")
        event(f"n_mod_10={i_mod_10}")
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

        event(f"category={category}")
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
        event(f"n={n}")
        assert result == "few"

    @given(n=st.integers(min_value=11, max_value=99))
    @example(n=11)
    @example(n=99)
    def test_eleven_to_ninetynine_are_many(self, n: int) -> None:
        """Arabic: 11-99 are 'many'.

        Property: 11 ≤ n ≤ 99 => category = "many"
        """
        result = select_plural_category(n, "ar")
        event(f"n={n}")
        assert result == "many"

    @given(n=st.integers(min_value=100, max_value=1000))
    @example(n=100)
    @example(n=500)
    def test_hundreds_valid_category(self, n: int) -> None:
        """Arabic: 100+ return valid category based on remainder.

        Property: For all n ≥ 100, category ∈ valid_categories
        """
        result = select_plural_category(n, "ar")
        event(f"category={result}")
        assert result in {"zero", "one", "two", "few", "many", "other"}
