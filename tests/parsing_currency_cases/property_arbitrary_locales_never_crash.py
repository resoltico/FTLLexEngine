# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Property: Arbitrary locales never crash
# ---------------------------------------------------------------------------


class TestLocaleResilience:
    """Property-based tests for locale robustness."""

    @given(
        bad_locale=st.text(
            alphabet=st.characters(blacklist_categories=["Cs"]),
            min_size=1,
            max_size=20,
        ).filter(lambda x: x not in ["en", "en_US", "de_DE", "fr_FR"])
    )
    def test_arbitrary_locales_never_crash(
        self, bad_locale: str
    ) -> None:
        """PROPERTY: Invalid locales never crash currency parsing."""
        locale_len = "short" if len(bad_locale) <= 5 else "long"
        event(f"locale_length={locale_len}")
        has_underscore = "_" in bad_locale
        event(f"has_underscore={has_underscore}")

        result, errors = parse_currency("\u20ac50", bad_locale)
        assert result is None or isinstance(result, tuple)
        if result is None:
            assert len(errors) > 0
