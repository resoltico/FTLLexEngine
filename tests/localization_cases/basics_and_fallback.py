# mypy: ignore-errors
from __future__ import annotations

import pytest

from ftllexengine.localization import (
    FluentLocalization,
)


class TestFluentLocalizationBasics:
    """Test basic FluentLocalization initialization and API."""

    def test_single_locale_initialization(self) -> None:
        """Initialize with single locale."""
        l10n = FluentLocalization(["en"])

        assert l10n.locales == ("en",)

    def test_multiple_locales_initialization(self) -> None:
        """Initialize with multiple locales in fallback order."""
        l10n = FluentLocalization(["lv", "en", "lt"])

        assert l10n.locales == ("lv", "en", "lt")

    def test_empty_locales_raises_error(self) -> None:
        """Empty locale list raises ValueError."""
        with pytest.raises(ValueError, match="At least one locale is required"):
            FluentLocalization([])

    def test_resource_ids_without_loader_raises_error(self) -> None:
        """Providing resource_ids without loader raises ValueError."""
        with pytest.raises(
            ValueError, match="resource_loader required when resource_ids provided"
        ):
            FluentLocalization(["en"], resource_ids=["main.ftl"])

    def test_invalid_locale_format_rejected_at_init(self) -> None:
        """Invalid locale format raises ValueError at initialization (fail-fast).

        Locale format errors are caught at construction time rather than
        propagating out of format_value during lazy bundle creation.
        """
        with pytest.raises(ValueError, match=r"Invalid locale: 'invalid locale with spaces'"):
            FluentLocalization(["en", "invalid locale with spaces"])

    def test_unknown_locale_rejected_at_init(self) -> None:
        """Unknown but well-formed locales are rejected before localization starts."""
        with pytest.raises(ValueError, match="Unknown locale identifier"):
            FluentLocalization(["en", "xx-UNKNOWN"])

    def test_locales_property_immutable(self) -> None:
        """Locales property returns immutable tuple."""
        l10n = FluentLocalization(["en", "fr"])

        assert isinstance(l10n.locales, tuple)
        assert l10n.locales == ("en", "fr")

class TestAddResource:
    """Test dynamic resource addition."""

    def test_add_resource_single_locale(self) -> None:
        """Add FTL resource to single locale."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "hello = Hello, World!")

        result, errors = l10n.format_value("hello")

        assert not errors
        assert result == "Hello, World!"

    def test_add_resource_multiple_locales(self) -> None:
        """Add different resources to different locales."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("lv", "hello = Sveiki, pasaule!")
        l10n.add_resource("en", "hello = Hello, World!")

        result, errors = l10n.format_value("hello")

        assert not errors
        # Should use first locale (lv)
        assert result == "Sveiki, pasaule!"

    def test_add_resource_invalid_locale_raises_error(self) -> None:
        """Adding resource for locale not in chain raises ValueError."""
        l10n = FluentLocalization(["en"])

        with pytest.raises(ValueError, match="Locale 'fr' not in fallback chain"):
            l10n.add_resource("fr", "hello = Bonjour!")

class TestFallbackChain:
    """Test locale fallback chain logic."""

    def test_fallback_to_second_locale(self) -> None:
        """Falls back to second locale when message missing in first."""
        l10n = FluentLocalization(["lv", "en"])
        # Add message only to English (not Latvian)
        l10n.add_resource("en", "greeting = Hello!")

        result, errors = l10n.format_value("greeting")

        assert not errors
        assert result == "Hello!"

    def test_fallback_to_third_locale(self) -> None:
        """Falls back through chain to third locale."""
        l10n = FluentLocalization(["lv", "en", "lt"])
        # Add message only to Lithuanian
        l10n.add_resource("lt", "welcome = Labas!")

        result, errors = l10n.format_value("welcome")

        assert not errors
        assert result == "Labas!"

    def test_first_locale_takes_precedence(self) -> None:
        """First locale in chain takes precedence over later locales."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("lv", "msg = Latvian version")
        l10n.add_resource("en", "msg = English version")

        result, errors = l10n.format_value("msg")

        assert not errors
        # Should use first locale (lv), not fallback to en
        assert result == "Latvian version"

    def test_partial_translations(self) -> None:
        """Handles partial translations with different messages per locale."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("lv", "home = Mājas")
        l10n.add_resource("en", "home = Home\nabout = About")

        home_result, _ = l10n.format_value("home")
        about_result, _ = l10n.format_value("about")

        assert home_result == "Mājas"  # From lv
        assert about_result == "About"  # Falls back to en

    def test_message_not_found_in_any_locale(self) -> None:
        """Message not found in any locale returns fallback."""
        l10n = FluentLocalization(["lv", "en"], strict=False)
        l10n.add_resource("lv", "hello = Sveiki!")
        l10n.add_resource("en", "hello = Hello!")

        result, errors = l10n.format_value("nonexistent")

        assert result == "{nonexistent}"
        assert len(errors) == 1
        # Check error message contains 'nonexistent'
        assert "nonexistent" in str(errors[0])

class TestFormatValue:
    """Test format_value method."""

    def test_format_simple_message(self) -> None:
        """Format simple message without variables."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "hello = Hello, World!")

        result, errors = l10n.format_value("hello")

        assert result == "Hello, World!"
        assert errors == ()

    def test_format_message_with_variables(self) -> None:
        """Format message with variable interpolation."""
        l10n = FluentLocalization(["en"], use_isolating=False)
        l10n.add_resource("en", "greeting = Hello, { $name }!")

        result, errors = l10n.format_value("greeting", {"name": "Anna"})

        assert not errors

        assert result == "Hello, Anna!"

    def test_format_message_with_multiple_variables(self) -> None:
        """Format message with multiple variables."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "user-info = { $firstName } { $lastName } (Age: { $age })")

        result, errors = l10n.format_value(
            "user-info", {"firstName": "John", "lastName": "Doe", "age": 30}
        )

        assert not errors

        assert "John" in result
        assert "Doe" in result
        assert "30" in result

    def test_format_propagates_bundle_errors(self) -> None:
        """Format propagates errors from FluentBundle."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "msg = Hello, { $name }!")

        # Missing required variable
        result, errors = l10n.format_value("msg")

        assert "Hello" in result
        assert len(errors) > 0  # Bundle should report missing variable

    def test_empty_message_id_returns_fallback(self) -> None:
        """Empty message ID returns graceful fallback."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "hello = Hello!")

        result, errors = l10n.format_value("")

        assert result == "{???}"
        assert len(errors) == 1
        assert "Empty or invalid message ID" in str(errors[0])

class TestHasMessage:
    """Test has_message method."""

    def test_has_message_in_first_locale(self) -> None:
        """Returns True if message in first locale."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("lv", "hello = Sveiki!")

        assert l10n.has_message("hello") is True

    def test_has_message_in_fallback_locale(self) -> None:
        """Returns True if message in fallback locale."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("en", "hello = Hello!")

        assert l10n.has_message("hello") is True

    def test_has_message_not_found(self) -> None:
        """Returns False if message not in any locale."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "hello = Hello!")

        assert l10n.has_message("goodbye") is False

class TestGetBundles:
    """Test get_bundles generator."""

    def test_get_bundles_returns_generator(self) -> None:
        """get_bundles returns a generator."""
        l10n = FluentLocalization(["en", "fr"])

        bundles_gen = l10n.get_bundles()

        # Generator should be iterable
        bundles = list(bundles_gen)
        assert len(bundles) == 2

    def test_get_bundles_respects_locale_order(self) -> None:
        """get_bundles yields bundles in locale priority order."""
        l10n = FluentLocalization(["lv", "en", "lt"])

        bundles = list(l10n.get_bundles())

        assert bundles[0].locale == "lv"
        assert bundles[1].locale == "en"
        assert bundles[2].locale == "lt"

class TestUseIsolating:
    """Test use_isolating parameter."""

    def test_use_isolating_true(self) -> None:
        """use_isolating=True wraps placeables in isolation marks."""
        l10n = FluentLocalization(["en"], use_isolating=True)
        l10n.add_resource("en", "msg = Hello, { $name }!")

        result, errors = l10n.format_value("msg", {"name": "Anna"})

        assert not errors

        # Should contain Unicode bidi isolation marks
        assert "\u2068" in result  # FSI (First Strong Isolate)
        assert "\u2069" in result  # PDI (Pop Directional Isolate)

    def test_use_isolating_false(self) -> None:
        """use_isolating=False does not wrap placeables."""
        l10n = FluentLocalization(["en"], use_isolating=False)
        l10n.add_resource("en", "msg = Hello, { $name }!")

        result, errors = l10n.format_value("msg", {"name": "Anna"})

        assert not errors

        # Should NOT contain isolation marks
        assert "\u2068" not in result
        assert "\u2069" not in result
