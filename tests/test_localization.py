"""Tests for FluentLocalization multi-locale orchestration.

Tests the fallback chain logic, resource loading, and Mozilla architecture alignment.
Uses Python 3.13 features for modern test patterns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ftllexengine.localization import FluentLocalization, PathResourceLoader


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

        result, _errors = l10n.format_value("hello")
        assert result == "Hello, World!"

    def test_add_resource_multiple_locales(self) -> None:
        """Add different resources to different locales."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("lv", "hello = Sveiki, pasaule!")
        l10n.add_resource("en", "hello = Hello, World!")

        result, _errors = l10n.format_value("hello")
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

        result, _errors = l10n.format_value("greeting")
        assert result == "Hello!"

    def test_fallback_to_third_locale(self) -> None:
        """Falls back through chain to third locale."""
        l10n = FluentLocalization(["lv", "en", "lt"])
        # Add message only to Lithuanian
        l10n.add_resource("lt", "welcome = Labas!")

        result, _errors = l10n.format_value("welcome")
        assert result == "Labas!"

    def test_first_locale_takes_precedence(self) -> None:
        """First locale in chain takes precedence over later locales."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("lv", "msg = Latvian version")
        l10n.add_resource("en", "msg = English version")

        result, _errors = l10n.format_value("msg")
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
        l10n = FluentLocalization(["lv", "en"])
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

        result, _errors = l10n.format_value("greeting", {"name": "Anna"})

        assert result == "Hello, Anna!"

    def test_format_message_with_multiple_variables(self) -> None:
        """Format message with multiple variables."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "user-info = { $firstName } { $lastName } (Age: { $age })")

        result, _errors = l10n.format_value(
            "user-info", {"firstName": "John", "lastName": "Doe", "age": 30}
        )

        assert "John" in result
        assert "Doe" in result
        assert "30" in result

    def test_format_propagates_bundle_errors(self) -> None:
        """Format propagates errors from FluentBundle."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "msg = Hello, { $name }!")

        # Missing required variable
        result, errors = l10n.format_value("msg")

        assert "Hello" in result
        assert len(errors) > 0  # Bundle should report missing variable

    def test_empty_message_id_returns_fallback(self) -> None:
        """Empty message ID returns graceful fallback."""
        l10n = FluentLocalization(["en"])
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

        result, _errors = l10n.format_value("msg", {"name": "Anna"})

        # Should contain Unicode bidi isolation marks
        assert "\u2068" in result  # FSI (First Strong Isolate)
        assert "\u2069" in result  # PDI (Pop Directional Isolate)

    def test_use_isolating_false(self) -> None:
        """use_isolating=False does not wrap placeables."""
        l10n = FluentLocalization(["en"], use_isolating=False)
        l10n.add_resource("en", "msg = Hello, { $name }!")

        result, _errors = l10n.format_value("msg", {"name": "Anna"})

        # Should NOT contain isolation marks
        assert "\u2068" not in result
        assert "\u2069" not in result


class TestPathResourceLoader:
    """Test PathResourceLoader implementation."""

    def test_path_resource_loader_load(self, tmp_path: Path) -> None:
        """PathResourceLoader loads FTL files from disk."""
        # Create test FTL files
        locales_dir = tmp_path / "locales"
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)

        main_ftl = en_dir / "main.ftl"
        main_ftl.write_text("hello = Hello, World!", encoding="utf-8")

        # Load resource
        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        ftl_source = loader.load("en", "main.ftl")

        assert ftl_source == "hello = Hello, World!"

    def test_path_resource_loader_file_not_found(self, tmp_path: Path) -> None:
        """PathResourceLoader raises FileNotFoundError for missing files."""
        loader = PathResourceLoader(str(tmp_path / "{locale}"))

        with pytest.raises(FileNotFoundError):
            loader.load("en", "nonexistent.ftl")

    def test_path_resource_loader_with_localization(self, tmp_path: Path) -> None:
        """PathResourceLoader integrates with FluentLocalization."""
        # Create test structure: locales/en/main.ftl, locales/lv/main.ftl
        locales_dir = tmp_path / "locales"

        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text("hello = Hello!", encoding="utf-8")

        lv_dir = locales_dir / "lv"
        lv_dir.mkdir(parents=True)
        (lv_dir / "main.ftl").write_text("hello = Sveiki!", encoding="utf-8")

        # Create localization with loader
        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["lv", "en"], ["main.ftl"], loader)

        result, _errors = l10n.format_value("hello")
        assert result == "Sveiki!"  # From lv

    def test_path_resource_loader_missing_locale_file_uses_fallback(
        self, tmp_path: Path
    ) -> None:
        """Missing locale file falls back to next locale."""
        # Create only English file (no Latvian)
        locales_dir = tmp_path / "locales"
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text("hello = Hello!", encoding="utf-8")

        # Latvian directory doesn't exist - will fall back to English
        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["lv", "en"], ["main.ftl"], loader)

        result, _errors = l10n.format_value("hello")
        assert result == "Hello!"  # Fell back to English


class TestRealWorldScenarios:
    """Test real-world usage patterns."""

    def test_e_commerce_site_partial_translations(self) -> None:
        """E-commerce site with partial Latvian translations."""
        l10n = FluentLocalization(["lv", "en"], use_isolating=False)

        # Latvian has only some translations
        l10n.add_resource(
            "lv",
            """
welcome = Sveiki, { $name }!
cart = Grozs
""",
        )

        # English has full translations
        l10n.add_resource(
            "en",
            """
welcome = Hello, { $name }!
cart = Cart
checkout = Checkout
payment-error = Payment failed: { $reason }
""",
        )

        # Messages in Latvian use lv
        welcome, _ = l10n.format_value("welcome", {"name": "Anna"})
        assert welcome == "Sveiki, Anna!"

        cart, _ = l10n.format_value("cart")
        assert cart == "Grozs"

        # Missing messages fall back to English
        checkout, _ = l10n.format_value("checkout")
        assert checkout == "Checkout"

        payment, _ = l10n.format_value("payment-error", {"reason": "Invalid card"})
        assert payment == "Payment failed: Invalid card"

    def test_fallback_chain_three_locales(self) -> None:
        """Complex fallback: lv → en → lt."""
        l10n = FluentLocalization(["lv", "en", "lt"])

        l10n.add_resource("lv", "home = Mājas")
        l10n.add_resource("en", "home = Home\nabout = About")
        l10n.add_resource("lt", "home = Namai\nabout = Apie\ncontact = Kontaktai")

        home, _ = l10n.format_value("home")
        assert home == "Mājas"  # From lv

        about, _ = l10n.format_value("about")
        assert about == "About"  # Falls back to en (skips lv)

        contact, _ = l10n.format_value("contact")
        assert contact == "Kontaktai"  # Falls back to lt (skips lv, en)

    def test_multiple_resource_files(self, tmp_path: Path) -> None:
        """Multiple FTL files per locale (ui.ftl, errors.ftl)."""
        # Create directory structure
        locales_dir = tmp_path / "locales"
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)

        (en_dir / "ui.ftl").write_text("hello = Hello!\nwelcome = Welcome!", encoding="utf-8")
        (en_dir / "errors.ftl").write_text("error-404 = Page not found", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["en"], ["ui.ftl", "errors.ftl"], loader)

        # Should load from both files
        hello, _ = l10n.format_value("hello")
        error, _ = l10n.format_value("error-404")

        assert hello == "Hello!"
        assert error == "Page not found"


class TestCacheConfiguration:
    """Test cache configuration in FluentLocalization."""

    def test_cache_disabled_by_default(self) -> None:
        """Cache is disabled by default."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "msg = Hello")

        # Format twice
        l10n.format_value("msg")
        l10n.format_value("msg")

        # Get stats from first bundle
        bundles = list(l10n.get_bundles())
        stats = bundles[0].get_cache_stats()

        # Cache disabled - stats should be None
        assert stats is None

    def test_cache_enabled_with_parameter(self) -> None:
        """Cache can be enabled via constructor parameter."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello")

        # Format twice - should hit cache on second call
        l10n.format_value("msg")
        l10n.format_value("msg")

        # Get stats from first bundle
        bundles = list(l10n.get_bundles())
        stats = bundles[0].get_cache_stats()

        # Cache enabled - should have stats
        assert stats is not None
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_cache_size_configurable(self) -> None:
        """Cache size can be configured via constructor parameter."""
        l10n = FluentLocalization(["en"], enable_cache=True, cache_size=500)
        l10n.add_resource("en", "msg = Hello")

        # Format message
        l10n.format_value("msg")

        # Verify cache is enabled (size configuration is internal)
        bundles = list(l10n.get_bundles())
        stats = bundles[0].get_cache_stats()
        assert stats is not None

    def test_cache_works_across_multiple_locales(self) -> None:
        """Cache enabled for all bundles in multi-locale setup."""
        l10n = FluentLocalization(["lv", "en"], enable_cache=True)
        l10n.add_resource("lv", "msg = Sveiki")
        l10n.add_resource("en", "msg = Hello")

        # Format from primary locale (lv)
        l10n.format_value("msg")
        l10n.format_value("msg")

        # Verify lv bundle has cache hits
        bundles = list(l10n.get_bundles())
        lv_stats = bundles[0].get_cache_stats()
        assert lv_stats is not None
        assert lv_stats["hits"] == 1

    def test_clear_cache_on_all_bundles(self) -> None:
        """clear_cache() clears cache on all bundles."""
        l10n = FluentLocalization(["lv", "en"], enable_cache=True)
        l10n.add_resource("lv", "msg = Sveiki")
        l10n.add_resource("en", "msg = Hello")

        # Format messages to populate cache
        l10n.format_value("msg")
        l10n.format_value("msg")

        # Clear cache
        l10n.clear_cache()

        # Format again - should be cache miss
        l10n.format_value("msg")

        # Verify cache was cleared (only 1 miss after clear)
        bundles = list(l10n.get_bundles())
        lv_stats = bundles[0].get_cache_stats()
        assert lv_stats is not None
        assert lv_stats["misses"] == 1  # Only the post-clear miss


class TestCacheIntrospection:
    """Test cache introspection properties."""

    def test_cache_enabled_property_when_enabled(self) -> None:
        """cache_enabled property returns True when caching enabled."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        assert l10n.cache_enabled is True

    def test_cache_enabled_property_when_disabled(self) -> None:
        """cache_enabled property returns False when caching disabled."""
        l10n = FluentLocalization(["en"], enable_cache=False)
        assert l10n.cache_enabled is False

    def test_cache_enabled_property_default(self) -> None:
        """cache_enabled property returns False by default."""
        l10n = FluentLocalization(["en"])
        assert l10n.cache_enabled is False

    def test_cache_size_property_when_enabled(self) -> None:
        """cache_size property returns configured size when caching enabled."""
        l10n = FluentLocalization(["en"], enable_cache=True, cache_size=500)
        assert l10n.cache_size == 500

    def test_cache_size_property_when_disabled(self) -> None:
        """cache_size property returns 0 when caching disabled."""
        l10n = FluentLocalization(["en"], enable_cache=False, cache_size=500)
        assert l10n.cache_size == 0

    def test_cache_size_property_default(self) -> None:
        """cache_size property returns 0 by default (cache disabled)."""
        l10n = FluentLocalization(["en"])
        assert l10n.cache_size == 0

    def test_bundle_cache_properties_reflect_localization_config(self) -> None:
        """Individual bundles reflect FluentLocalization cache config."""
        l10n = FluentLocalization(["lv", "en"], enable_cache=True, cache_size=250)

        # Check all bundles have matching config
        for bundle in l10n.get_bundles():
            assert bundle.cache_enabled is True
            assert bundle.cache_size == 250
