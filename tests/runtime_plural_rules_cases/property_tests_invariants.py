# mypy: ignore-errors
"""Split test cases from tests/test_runtime_plural_rules.py."""

from tests.runtime_plural_rules_cases import *  # noqa: F403 - shared split test support

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
