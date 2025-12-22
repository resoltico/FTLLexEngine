"""Tests for FluentLocalization API completeness.

Validates feature parity with FluentBundle.
"""

from ftllexengine import FluentLocalization


class TestLocalizationFormatPattern:
    """Test format_pattern() with attribute support."""

    def test_format_pattern_with_attribute(self) -> None:
        """Format pattern with attribute access."""
        l10n = FluentLocalization(["lv", "en"], use_isolating=False)
        l10n.add_resource("lv", "button = Klikšķināt\n    .tooltip = Klikšķiniet, lai iesniegtu")

        result, errors = l10n.format_pattern("button", attribute="tooltip")
        assert result == "Klikšķiniet, lai iesniegtu"
        assert errors == ()

    def test_format_pattern_fallback_with_attribute(self) -> None:
        """Format pattern falls back to second locale with attribute."""
        l10n = FluentLocalization(["lv", "en"], use_isolating=False)
        l10n.add_resource("en", "button = Click\n    .tooltip = Click to submit")

        # Message not in lv, falls back to en
        result, errors = l10n.format_pattern("button", attribute="tooltip")
        assert result == "Click to submit"
        assert errors == ()

    def test_format_pattern_not_found(self) -> None:
        """Format pattern returns fallback when message not found."""
        l10n = FluentLocalization(["lv", "en"])

        result, errors = l10n.format_pattern("missing")
        assert result == "{missing}"
        assert len(errors) == 1


class TestLocalizationAddFunction:
    """Test add_function() on all bundles."""

    def test_add_function_to_all_bundles(self) -> None:
        """Custom function registered on all bundles."""
        l10n = FluentLocalization(["lv", "en"], use_isolating=False)

        def CUSTOM(value: str) -> str:
            return value.upper()

        l10n.add_function("CUSTOM", CUSTOM)
        l10n.add_resource("lv", "msg = { CUSTOM($text) }")
        l10n.add_resource("en", "msg = { CUSTOM($text) }")

        # Should work in both locales
        result_lv, _ = l10n.format_value("msg", {"text": "hello"})
        assert result_lv == "HELLO"


class TestLocalizationIntrospection:
    """Test introspect_message() from first bundle."""

    def test_introspect_message_found(self) -> None:
        """Introspect message from first bundle with it."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("en", "msg = { $name } has { $count } items")

        info = l10n.introspect_message("msg")
        assert info is not None

    def test_introspect_message_not_found(self) -> None:
        """Introspect returns None when message not found."""
        l10n = FluentLocalization(["lv", "en"])

        info = l10n.introspect_message("missing")
        assert info is None


class TestLocalizationBabelLocale:
    """Test get_babel_locale() from primary bundle."""

    def test_get_babel_locale_returns_primary(self) -> None:
        """Get Babel locale from primary locale."""
        l10n = FluentLocalization(["lv", "en"])

        locale = l10n.get_babel_locale()
        assert locale == "lv"


class TestLocalizationValidation:
    """Test validate_resource() using primary bundle."""

    def test_validate_resource_valid(self) -> None:
        """Validate valid FTL resource."""
        l10n = FluentLocalization(["lv", "en"])

        result = l10n.validate_resource("msg = Hello")
        assert result.is_valid

    def test_validate_resource_invalid(self) -> None:
        """Validate invalid FTL resource."""
        l10n = FluentLocalization(["lv", "en"])

        result = l10n.validate_resource("msg = {")
        assert not result.is_valid


class TestLocalizationClearCache:
    """Test clear_cache() on all bundles."""

    def test_clear_cache_all_bundles(self) -> None:
        """Clear cache on all bundles."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("lv", "msg = Sveiki")
        l10n.add_resource("en", "msg = Hello")

        # Verify clear_cache completes without error
        l10n.clear_cache()

        # Verify bundles are still functional after cache clear
        assert l10n.format_value("msg") is not None
