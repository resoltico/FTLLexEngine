# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_localization_property.py."""

from tests.fuzz_localization_property_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Terms with Hypothesis strategies
# ---------------------------------------------------------------------------


class TestTermsWithStrategies:
    """Tests using ftl_messages_with_terms strategy."""

    @given(
        locales=locale_chains(min_size=1, max_size=2),
        ftl=ftl_messages_with_terms(),
    )
    def test_terms_parsed_and_resolvable(
        self, locales: list[str], ftl: str,
    ) -> None:
        """Generated terms are parsed without errors."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales, use_isolating=False)
        junk = l10n.add_resource(locales[0], ftl)
        # Should parse without junk
        assert len(junk) == 0
