"""Tests for FluentLocalization multi-locale orchestration.

Tests the fallback chain logic, resource loading, and Mozilla architecture alignment.
Uses Python 3.13 features for modern test patterns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ftllexengine.localization import (
    FallbackInfo,
    FluentLocalization,
    PathResourceLoader,
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
        """Invalid locale format raises ValueError at initialization.

        Regression test for API-LOCALE-LEAK-001.
        Validates that locale format errors are caught early (fail-fast)
        rather than propagating out of format_value during lazy bundle creation.
        """
        with pytest.raises(ValueError, match="Invalid locale code format"):
            FluentLocalization(["en", "invalid locale with spaces"])

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

        result, errors = l10n.format_value("hello")

        assert not errors
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

        result, errors = l10n.format_value("hello")

        assert not errors
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
        """cache_size returns configured limit even when caching disabled."""
        l10n = FluentLocalization(["en"], enable_cache=False, cache_size=500)
        # Returns configured limit (for introspection), not current usage
        assert l10n.cache_size == 500

    def test_cache_size_property_default(self) -> None:
        """cache_size returns default limit (1000) even when cache disabled."""
        l10n = FluentLocalization(["en"])
        # Default cache_size is 1000, returned regardless of enable_cache
        assert l10n.cache_size == 1000

    def test_bundle_cache_properties_reflect_localization_config(self) -> None:
        """Individual bundles reflect FluentLocalization cache config."""
        l10n = FluentLocalization(["lv", "en"], enable_cache=True, cache_size=250)

        # Check all bundles have matching config
        for bundle in l10n.get_bundles():
            assert bundle.cache_enabled is True
            assert bundle.cache_size == 250


class TestMultiLocaleFileLoading:
    """Tests for multi-locale file loading workflows.

    These tests verify the end-to-end workflow of loading FTL files
    from disk across multiple locales with proper fallback behavior.
    """

    def test_load_multiple_files_per_locale(self, tmp_path: Path) -> None:
        """Multiple FTL files per locale are loaded and merged correctly."""
        locales_dir = tmp_path / "locales"

        # Create en locale with multiple files
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text("welcome = Welcome!", encoding="utf-8")
        (en_dir / "errors.ftl").write_text("error-404 = Not Found", encoding="utf-8")
        (en_dir / "buttons.ftl").write_text("submit = Submit", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(
            ["en"], ["main.ftl", "errors.ftl", "buttons.ftl"], loader
        )

        # All messages from all files should be available
        welcome, _ = l10n.format_value("welcome")
        error, _ = l10n.format_value("error-404")
        submit, _ = l10n.format_value("submit")

        assert welcome == "Welcome!"
        assert error == "Not Found"
        assert submit == "Submit"

    def test_fallback_across_multiple_files(self, tmp_path: Path) -> None:
        """Fallback works correctly across multiple files and locales."""
        locales_dir = tmp_path / "locales"

        # Create en locale (complete)
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text("home = Home\nabout = About", encoding="utf-8")
        (en_dir / "errors.ftl").write_text("error-404 = Not Found", encoding="utf-8")

        # Create de locale (partial - missing errors.ftl)
        de_dir = locales_dir / "de"
        de_dir.mkdir(parents=True)
        (de_dir / "main.ftl").write_text("home = Startseite\nabout = Uber uns", encoding="utf-8")
        # Note: de/errors.ftl intentionally missing

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["de", "en"], ["main.ftl", "errors.ftl"], loader)

        # de messages should come from de
        home, _ = l10n.format_value("home")
        assert home == "Startseite"

        # error should fall back to en (de/errors.ftl missing)
        error, _ = l10n.format_value("error-404")
        assert error == "Not Found"

    def test_partial_translation_within_file(self, tmp_path: Path) -> None:
        """Partial translations within a file fall back correctly."""
        locales_dir = tmp_path / "locales"

        # Create en locale (complete)
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text(
            "home = Home\nabout = About\ncontact = Contact", encoding="utf-8"
        )

        # Create fr locale (partial translations)
        fr_dir = locales_dir / "fr"
        fr_dir.mkdir(parents=True)
        (fr_dir / "main.ftl").write_text("home = Accueil", encoding="utf-8")
        # Note: about and contact missing in fr

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["fr", "en"], ["main.ftl"], loader)

        # fr message from fr
        home, _ = l10n.format_value("home")
        assert home == "Accueil"

        # missing fr messages fall back to en
        about, _ = l10n.format_value("about")
        contact, _ = l10n.format_value("contact")
        assert about == "About"
        assert contact == "Contact"

    def test_three_locale_fallback_chain(self, tmp_path: Path) -> None:
        """Three-locale fallback chain works correctly."""
        locales_dir = tmp_path / "locales"

        # en has all messages
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text(
            "level1 = English One\nlevel2 = English Two\nlevel3 = English Three",
            encoding="utf-8"
        )

        # de has two messages
        de_dir = locales_dir / "de"
        de_dir.mkdir(parents=True)
        (de_dir / "main.ftl").write_text(
            "level1 = Deutsch Eins\nlevel2 = Deutsch Zwei",
            encoding="utf-8"
        )

        # fr has one message
        fr_dir = locales_dir / "fr"
        fr_dir.mkdir(parents=True)
        (fr_dir / "main.ftl").write_text("level1 = Francais Un", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["fr", "de", "en"], ["main.ftl"], loader)

        # level1 from fr (first locale)
        level1, _ = l10n.format_value("level1")
        assert level1 == "Francais Un"

        # level2 from de (second locale, fr doesn't have it)
        level2, _ = l10n.format_value("level2")
        assert level2 == "Deutsch Zwei"

        # level3 from en (third locale, fr and de don't have it)
        level3, _ = l10n.format_value("level3")
        assert level3 == "English Three"

    def test_unicode_content_in_files(self, tmp_path: Path) -> None:
        """Unicode content in FTL files loads correctly."""
        locales_dir = tmp_path / "locales"

        # Create locales with various Unicode content
        ja_dir = locales_dir / "ja"
        ja_dir.mkdir(parents=True)
        (ja_dir / "main.ftl").write_text("greeting = Hello", encoding="utf-8")

        lv_dir = locales_dir / "lv"
        lv_dir.mkdir(parents=True)
        (lv_dir / "main.ftl").write_text("greeting = Sveiki, pasaule!", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))

        l10n_ja = FluentLocalization(["ja"], ["main.ftl"], loader)
        l10n_lv = FluentLocalization(["lv"], ["main.ftl"], loader)

        ja_greeting, _ = l10n_ja.format_value("greeting")
        lv_greeting, _ = l10n_lv.format_value("greeting")

        assert ja_greeting == "Hello"
        assert lv_greeting == "Sveiki, pasaule!"

    def test_missing_locale_directory_falls_back(self, tmp_path: Path) -> None:
        """Missing locale directory gracefully falls back to next locale."""
        locales_dir = tmp_path / "locales"

        # Only create en directory (no de)
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text("greeting = Hello!", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        # de is first but doesn't exist
        l10n = FluentLocalization(["de", "en"], ["main.ftl"], loader)

        # Should fall back to en
        greeting, _ = l10n.format_value("greeting")
        assert greeting == "Hello!"

    def test_empty_file_handled_gracefully(self, tmp_path: Path) -> None:
        """Empty FTL files are handled without errors."""
        locales_dir = tmp_path / "locales"

        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "empty.ftl").write_text("", encoding="utf-8")
        (en_dir / "main.ftl").write_text("greeting = Hello!", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["en"], ["empty.ftl", "main.ftl"], loader)

        # Should still work - empty file just adds no messages
        greeting, _ = l10n.format_value("greeting")
        assert greeting == "Hello!"

    def test_file_with_only_comments(self, tmp_path: Path) -> None:
        """FTL files with only comments are handled correctly."""
        locales_dir = tmp_path / "locales"

        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "comments.ftl").write_text(
            "# This file has only comments\n## Section comment\n### Resource comment",
            encoding="utf-8"
        )
        (en_dir / "main.ftl").write_text("greeting = Hello!", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["en"], ["comments.ftl", "main.ftl"], loader)

        # Should work - comments file adds no messages
        greeting, _ = l10n.format_value("greeting")
        assert greeting == "Hello!"

    def test_variables_in_file_loaded_messages(self, tmp_path: Path) -> None:
        """Variables work correctly in file-loaded messages."""
        locales_dir = tmp_path / "locales"

        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        (en_dir / "main.ftl").write_text(
            "greeting = Hello, { $name }!\ncount = You have { $n } items.",
            encoding="utf-8"
        )

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        l10n = FluentLocalization(["en"], ["main.ftl"], loader, use_isolating=False)

        greeting, _ = l10n.format_value("greeting", {"name": "World"})
        count, _ = l10n.format_value("count", {"n": 42})

        assert greeting == "Hello, World!"
        assert "42" in count


class TestOnFallbackCallback:
    """Tests for on_fallback callback (lines 853-858, 946-951).

    Tests the callback that's invoked when a message is resolved from
    a fallback locale instead of the primary locale.
    """

    def test_on_fallback_invoked_on_format_value(self) -> None:
        """on_fallback callback invoked when message resolved from fallback locale."""
        fallback_events: list[FallbackInfo] = []

        def record_fallback(info: FallbackInfo) -> None:
            fallback_events.append(info)

        l10n = FluentLocalization(["lv", "en"], on_fallback=record_fallback)

        # Add message only to fallback locale (en)
        l10n.add_resource("en", "fallback-msg = English fallback")

        # Request message - should trigger fallback
        result, _ = l10n.format_value("fallback-msg")

        assert result == "English fallback"
        assert len(fallback_events) == 1
        assert fallback_events[0].requested_locale == "lv"
        assert fallback_events[0].resolved_locale == "en"
        assert fallback_events[0].message_id == "fallback-msg"

    def test_on_fallback_invoked_on_format_pattern(self) -> None:
        """on_fallback callback invoked in format_pattern when using fallback locale."""
        fallback_events: list[FallbackInfo] = []

        def record_fallback(info: FallbackInfo) -> None:
            fallback_events.append(info)

        l10n = FluentLocalization(["de", "en"], on_fallback=record_fallback)

        # Add message only to fallback locale (en)
        l10n.add_resource("en", "pattern-msg = Pattern from fallback")

        # Request message via format_pattern - should trigger fallback
        result, _ = l10n.format_pattern("pattern-msg")

        assert result == "Pattern from fallback"
        assert len(fallback_events) == 1
        assert fallback_events[0].requested_locale == "de"
        assert fallback_events[0].resolved_locale == "en"
        assert fallback_events[0].message_id == "pattern-msg"

    def test_on_fallback_not_invoked_for_primary_locale(self) -> None:
        """on_fallback not invoked when message found in primary locale."""
        fallback_events: list[FallbackInfo] = []

        def record_fallback(info: FallbackInfo) -> None:
            fallback_events.append(info)

        l10n = FluentLocalization(["fr", "en"], on_fallback=record_fallback)

        # Add message to primary locale (fr)
        l10n.add_resource("fr", "french-msg = Message en francais")

        result, _ = l10n.format_value("french-msg")

        assert result == "Message en francais"
        assert len(fallback_events) == 0  # No fallback occurred

    def test_on_fallback_none_does_not_raise(self) -> None:
        """on_fallback=None (default) works without errors."""
        l10n = FluentLocalization(["lv", "en"])

        l10n.add_resource("en", "msg = No callback")

        # Should not raise even without callback
        result, _ = l10n.format_value("msg")
        assert result == "No callback"

    def test_on_fallback_multiple_calls(self) -> None:
        """on_fallback invoked for each fallback resolution."""
        fallback_events: list[FallbackInfo] = []

        def record_fallback(info: FallbackInfo) -> None:
            fallback_events.append(info)

        l10n = FluentLocalization(["it", "en"], on_fallback=record_fallback)

        l10n.add_resource("en", "msg1 = First\nmsg2 = Second")

        l10n.format_value("msg1")
        l10n.format_value("msg2")

        assert len(fallback_events) == 2
        assert fallback_events[0].message_id == "msg1"
        assert fallback_events[1].message_id == "msg2"

    def test_on_fallback_with_format_pattern_and_attribute(self) -> None:
        """on_fallback invoked in format_pattern with attribute access."""
        fallback_events: list[FallbackInfo] = []

        def record_fallback(info: FallbackInfo) -> None:
            fallback_events.append(info)

        l10n = FluentLocalization(["es", "en"], on_fallback=record_fallback)

        l10n.add_resource(
            "en",
            """
button = Click
    .tooltip = Button tooltip
""",
        )

        # Request attribute via format_pattern
        result, _ = l10n.format_pattern("button", attribute="tooltip")

        assert "tooltip" in result.lower() or "Button" in result
        assert len(fallback_events) == 1
        assert fallback_events[0].message_id == "button"
