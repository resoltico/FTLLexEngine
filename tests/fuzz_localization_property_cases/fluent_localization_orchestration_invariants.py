# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_localization_property.py."""

from tests.fuzz_localization_property_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# FluentLocalization orchestration invariants
# ---------------------------------------------------------------------------


class TestFluentLocalizationOrchestration:
    """Property invariants for FluentLocalization fallback behavior."""

    @given(locales=locale_chains(min_size=1, max_size=5))
    def test_deduplication_preserves_order(
        self, locales: list[str],
    ) -> None:
        """Locale deduplication preserves first-occurrence order."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        expected = tuple(dict.fromkeys(normalize_locale(locale) for locale in locales))
        assert l10n.locales == expected

    @given(locales=locale_chains(min_size=1, max_size=3))
    def test_locales_property_returns_same_instance(
        self, locales: list[str],
    ) -> None:
        """locales property is referentially identical across calls."""
        event("outcome=identity_check")
        l10n = FluentLocalization(locales)
        assert l10n.locales is l10n.locales

    @given(
        locales=locale_chains(min_size=2, max_size=4),
        mid=message_ids(),
    )
    def test_primary_locale_takes_precedence(
        self, locales: list[str], mid: str,
    ) -> None:
        """First locale with message wins in fallback chain."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales, use_isolating=False)
        for locale in locales:
            l10n.add_resource(locale, f"{mid} = from-{locale}")
        result, errors = l10n.format_value(mid)
        assert not errors
        assert result == f"from-{locales[0]}"

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        mid=message_ids(),
    )
    def test_has_message_consistent_with_format_value(
        self, locales: list[str], mid: str,
    ) -> None:
        """has_message True iff format_value finds the message."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], f"{mid} = test")
        has = l10n.has_message(mid)
        _, errors = l10n.format_value(mid)
        if has:
            assert not any(
                "not found in any locale" in str(e) for e in errors
            )
        else:
            assert any(
                "not found in any locale" in str(e) for e in errors
            )

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        mid=message_ids(),
    )
    def test_format_value_deterministic(
        self, locales: list[str], mid: str,
    ) -> None:
        """Repeated format_value calls return identical results."""
        event("outcome=determinism")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], f"{mid} = stable")
        r1, _ = l10n.format_value(mid)
        r2, _ = l10n.format_value(mid)
        assert r1 == r2

    @given(mid=message_ids())
    def test_missing_message_returns_braced_id(self, mid: str) -> None:
        """Missing message returns {message_id} per Fluent convention.

        strict=False: missing-message error returned in tuple, not raised.
        """
        event("outcome=missing_message")
        l10n = FluentLocalization(["en"], strict=False)
        result, errors = l10n.format_value(mid)
        assert result == f"{{{mid}}}"
        assert len(errors) == 1

    @given(mid=st.just(""))
    def test_empty_message_id_returns_fallback(self, mid: str) -> None:
        """Empty message ID returns {???} fallback.

        strict=False: invalid-ID error returned in tuple, not raised.
        """
        event("outcome=empty_id")
        l10n = FluentLocalization(["en"], strict=False)
        result, errors = l10n.format_value(mid)
        assert result == "{???}"
        assert len(errors) == 1

    @given(locales=locale_chains(min_size=1, max_size=3))
    def test_repr_contains_locales_and_bundles(
        self, locales: list[str],
    ) -> None:
        """__repr__ always includes locales and bundle count."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        r = repr(l10n)
        assert "FluentLocalization" in r
        assert "locales=" in r
        assert "bundles=" in r
