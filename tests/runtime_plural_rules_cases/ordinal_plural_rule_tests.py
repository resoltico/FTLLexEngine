# mypy: ignore-errors
"""Split test cases from tests/test_runtime_plural_rules.py."""

from tests.runtime_plural_rules_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Ordinal Plural Rule Tests
# ============================================================================


class TestOrdinalPluralRules:
    """Tests for the ordinal=True parameter using CLDR ordinal plural rules.

    Ordinal rules apply to rank/position contexts (1st, 2nd, 3rd, ...).
    English ordinal rules: 1->one (1st), 2->two (2nd), 3->few (3rd),
    4+->other unless ends in 1/2/3 with specific exceptions.
    """

    def test_english_ordinal_one(self) -> None:
        """English ordinal: 1 -> 'one' (1st)."""
        assert select_plural_category(1, "en_US", ordinal=True) == "one"

    def test_english_ordinal_two(self) -> None:
        """English ordinal: 2 -> 'two' (2nd)."""
        assert select_plural_category(2, "en_US", ordinal=True) == "two"

    def test_english_ordinal_few(self) -> None:
        """English ordinal: 3 -> 'few' (3rd)."""
        assert select_plural_category(3, "en_US", ordinal=True) == "few"

    def test_english_ordinal_other(self) -> None:
        """English ordinal: 4+ (no suffix rule) -> 'other' (4th)."""
        assert select_plural_category(4, "en_US", ordinal=True) == "other"

    def test_english_ordinal_eleven(self) -> None:
        """English ordinal: 11 -> 'other' (11th, not 11st)."""
        assert select_plural_category(11, "en_US", ordinal=True) == "other"

    def test_english_ordinal_twelve(self) -> None:
        """English ordinal: 12 -> 'other' (12th, not 12nd)."""
        assert select_plural_category(12, "en_US", ordinal=True) == "other"

    def test_english_ordinal_thirteen(self) -> None:
        """English ordinal: 13 -> 'other' (13th, not 13rd)."""
        assert select_plural_category(13, "en_US", ordinal=True) == "other"

    def test_english_ordinal_twenty_one(self) -> None:
        """English ordinal: 21 -> 'one' (21st)."""
        assert select_plural_category(21, "en_US", ordinal=True) == "one"

    def test_english_ordinal_twenty_two(self) -> None:
        """English ordinal: 22 -> 'two' (22nd)."""
        assert select_plural_category(22, "en_US", ordinal=True) == "two"

    def test_english_ordinal_twenty_three(self) -> None:
        """English ordinal: 23 -> 'few' (23rd)."""
        assert select_plural_category(23, "en_US", ordinal=True) == "few"

    def test_ordinal_false_is_default(self) -> None:
        """ordinal=False (default) uses cardinal rules, same as omitting the parameter."""
        assert (
            select_plural_category(1, "en_US")
            == select_plural_category(1, "en_US", ordinal=False)
        )
        # Ordinal and cardinal differ for n=2 in English:
        # cardinal: 2 -> "other"; ordinal: 2 -> "two"
        assert select_plural_category(2, "en_US") == "other"
        assert select_plural_category(2, "en_US", ordinal=True) == "two"

    @given(n=st.integers(min_value=0, max_value=1000), locale=LOCALE_CODES)
    @example(n=1, locale="en_US")
    @example(n=2, locale="en_US")
    @example(n=3, locale="en_US")
    @example(n=11, locale="en_US")
    def test_ordinal_always_returns_valid_category(
        self, n: int, locale: str
    ) -> None:
        """Ordinal selection always returns a valid CLDR category.

        Property: For all n and locale, ordinal result in valid_categories
        """
        result = select_plural_category(n, locale, ordinal=True)

        valid_categories = {"zero", "one", "two", "few", "many", "other"}
        assert result in valid_categories

        event(f"category={result}")
        event(f"locale={locale}")

    @given(n=st.integers(min_value=0, max_value=1000), locale=LOCALE_CODES)
    def test_ordinal_deterministic(self, n: int, locale: str) -> None:
        """Ordinal selection is deterministic: same inputs produce same result."""
        result1 = select_plural_category(n, locale, ordinal=True)
        result2 = select_plural_category(n, locale, ordinal=True)

        assert result1 == result2
        event(f"category={result1}")

    @given(n=NUMBERS, locale=LOCALE_CODES)
    def test_ordinal_never_crashes(self, n: int | Decimal, locale: str) -> None:
        """Ordinal selection never crashes for any valid n/locale combination."""
        result = select_plural_category(n, locale, ordinal=True)

        assert isinstance(result, str)
        event(f"category={result}")
        event(f"n_type={type(n).__name__}")

    def test_ordinal_unknown_locale_falls_back_to_other(self) -> None:
        """Unknown locale falls back to 'other' for ordinal rules."""
        result = select_plural_category(1, "xx_XX", ordinal=True)
        assert result == "other"

    def test_ordinal_welsh_has_multiple_categories(self) -> None:
        """Welsh (cy) ordinal rules use multiple categories (zero, one, two, few, many, other)."""
        # Welsh ordinals use all 6 categories
        results = {select_plural_category(n, "cy", ordinal=True) for n in range(10)}
        # Welsh ordinals produce at least 2 distinct categories
        assert len(results) >= 2
        valid = {"zero", "one", "two", "few", "many", "other"}
        assert results <= valid
