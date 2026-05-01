# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_localization_property.py."""

from tests.fuzz_localization_property_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Fallback callback
# ---------------------------------------------------------------------------


class TestFallbackCallback:
    """Tests for on_fallback callback with property-based inputs."""

    @given(
        locales=locale_chains(min_size=2, max_size=4),
        mid=message_ids(),
    )
    def test_fallback_callback_invoked_for_non_primary(
        self, locales: list[str], mid: str,
    ) -> None:
        """on_fallback invoked when message resolved from non-primary."""
        event(f"locale_count={len(locales)}")
        from ftllexengine.localization import FallbackInfo
        events: list[FallbackInfo] = []
        l10n = FluentLocalization(
            locales, on_fallback=events.append,
        )
        # Only add to last locale
        l10n.add_resource(locales[-1], f"{mid} = fallback\n")
        l10n.format_value(mid)
        if len(locales) > 1:
            assert len(events) == 1
            assert events[0].requested_locale == normalize_locale(locales[0])
            assert events[0].resolved_locale == normalize_locale(locales[-1])
            assert events[0].message_id == mid

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        mid=message_ids(),
    )
    def test_no_fallback_when_primary_has_message(
        self, locales: list[str], mid: str,
    ) -> None:
        """on_fallback not invoked when primary locale has message."""
        event("outcome=no_fallback")
        from ftllexengine.localization import FallbackInfo
        events: list[FallbackInfo] = []
        l10n = FluentLocalization(
            locales, on_fallback=events.append,
        )
        l10n.add_resource(locales[0], f"{mid} = primary\n")
        l10n.format_value(mid)
        assert len(events) == 0
