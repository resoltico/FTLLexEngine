# mypy: ignore-errors
"""Split test cases from tests/test_runtime_plural_rules.py."""

from tests.runtime_plural_rules_cases import *  # noqa: F403 - shared split test support

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
        event(f"locale_len={len(locale)}")
        event(f"category={result}")
        assert isinstance(result, str)

    @given(n=st.decimals(
        min_value=Decimal(-1000), max_value=Decimal(0),
        allow_nan=False, allow_infinity=False,
    ))
    @example(n=Decimal(-1))
    @example(n=Decimal(-100))
    def test_negative_numbers_return_valid_category(self, n: Decimal) -> None:
        """Negative numbers return valid category.

        Property: For all n < 0, category ∈ valid_categories
        """
        result = select_plural_category(n, "en")
        event(f"category={result}")
        assert result in {"zero", "one", "two", "few", "many", "other"}

    @given(locale=LOCALE_CODES)
    @example(locale="en_US")
    @example(locale="ru_RU")
    def test_very_large_numbers(self, locale: str) -> None:
        """Very large numbers work correctly.

        Property: For all locales, large numbers return valid category
        """
        result = select_plural_category(10**9, locale)
        event(f"locale={locale}")
        event(f"category={result}")
        assert result in {"zero", "one", "two", "few", "many", "other"}
