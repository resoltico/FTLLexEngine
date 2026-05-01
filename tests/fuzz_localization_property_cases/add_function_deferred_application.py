# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_localization_property.py."""

from tests.fuzz_localization_property_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# add_function deferred application
# ---------------------------------------------------------------------------


class TestAddFunctionDeferred:
    """Tests for add_function deferred/immediate application."""

    @given(locales=locale_chains(min_size=1, max_size=3))
    def test_function_applied_to_existing_bundles(
        self, locales: list[str],
    ) -> None:
        """add_function applies to already-created bundles."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales, use_isolating=False)
        # Create bundles by adding resources
        for locale in locales:
            l10n.add_resource(locale, "msg = { UPPER($x) }\n")

        def upper_fn(value: str) -> str:
            return value.upper()

        l10n.add_function("UPPER", upper_fn)
        result, _ = l10n.format_value("msg", {"x": "test"})
        assert "TEST" in result

    @given(locales=locale_chains(min_size=2, max_size=3))
    def test_function_stored_for_lazy_bundles(
        self, locales: list[str],
    ) -> None:
        """add_function stored for bundles created later."""
        event("outcome=deferred")
        l10n = FluentLocalization(locales, use_isolating=False)

        def lower_fn(value: str) -> str:
            return value.lower()

        l10n.add_function("LOWER", lower_fn)
        # Add resource and format after function registration
        l10n.add_resource(locales[0], "msg = { LOWER($x) }\n")
        result, _ = l10n.format_value("msg", {"x": "HELLO"})
        assert "hello" in result
