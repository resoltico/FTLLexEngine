# mypy: ignore-errors
"""Split test cases from tests/test_runtime_plural_rules.py."""

from tests.runtime_plural_rules_cases import *  # noqa: F403 - shared split test support

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

        event(f"locale={locale}")
        event(f"category_n={result1}")
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

        event(f"category_en={en_result}")
        assert en_result in {"one", "other"}
        assert de_result in {"one", "other"}

        if n == 1:
            assert en_result == de_result == "one"
