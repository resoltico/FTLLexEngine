# mypy: ignore-errors
from __future__ import annotations

from pathlib import Path

import pytest

from ftllexengine.localization import (
    FluentLocalization,
    PathResourceLoader,
    ResourceLoader,
)
from ftllexengine.runtime.cache_config import CacheConfig


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

    def test_path_resource_loader_missing_locale_placeholder_raises(self) -> None:
        """PathResourceLoader raises ValueError when {locale} placeholder is missing."""
        # Fail-fast: Missing placeholder would cause silent data corruption
        # where all locales load from the same static path
        with pytest.raises(ValueError, match=r"must contain '\{locale\}' placeholder"):
            PathResourceLoader("locales/en")  # Missing {locale}

        with pytest.raises(ValueError, match=r"must contain '\{locale\}' placeholder"):
            PathResourceLoader("/absolute/path/to/locales")  # Missing {locale}

        # Valid: Contains {locale} placeholder
        loader = PathResourceLoader("locales/{locale}")  # Should not raise
        assert "{locale}" in loader.base_path

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

    def test_resource_loader_describe_path_default(self) -> None:
        """ResourceLoader.describe_path default returns locale/resource_id."""

        class _MinimalLoader(ResourceLoader):
            def load(self, _locale: str, _resource_id: str) -> str:
                return ""

        loader = _MinimalLoader()
        result = loader.describe_path("en", "main.ftl")
        assert result == "en/main.ftl"

    def test_resource_loader_describe_path_default_no_override(self) -> None:
        """ResourceLoader.describe_path default is used when subclass does not override."""

        class _BareLoader(ResourceLoader):
            def load(self, _locale: str, _resource_id: str) -> str:
                return ""

        loader = _BareLoader()
        assert loader.describe_path("de_DE", "errors.ftl") == "de_DE/errors.ftl"

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
        l10n = FluentLocalization(["en"], cache=CacheConfig())
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
        l10n = FluentLocalization(["en"], cache=CacheConfig(size=500))
        l10n.add_resource("en", "msg = Hello")

        # Format message
        l10n.format_value("msg")

        # Verify cache is enabled (size configuration is internal)
        bundles = list(l10n.get_bundles())
        stats = bundles[0].get_cache_stats()
        assert stats is not None

    def test_cache_works_across_multiple_locales(self) -> None:
        """Cache enabled for all bundles in multi-locale setup."""
        l10n = FluentLocalization(["lv", "en"], cache=CacheConfig())
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
        l10n = FluentLocalization(["lv", "en"], cache=CacheConfig())
        l10n.add_resource("lv", "msg = Sveiki")
        l10n.add_resource("en", "msg = Hello")

        # Format messages to populate cache
        l10n.format_value("msg")
        l10n.format_value("msg")

        # Clear cache
        l10n.clear_cache()

        # Format again - should be cache miss
        l10n.format_value("msg")

        # Verify cache was cleared; metrics are cumulative (not reset on clear).
        # 1 miss before clear + 1 miss after clear = 2 cumulative misses.
        bundles = list(l10n.get_bundles())
        lv_stats = bundles[0].get_cache_stats()
        assert lv_stats is not None
        assert lv_stats["misses"] == 2  # Pre-clear miss + post-clear miss

class TestCacheIntrospection:
    """Test cache introspection properties."""

    def test_cache_enabled_property_when_enabled(self) -> None:
        """cache_enabled property returns True when caching enabled."""
        l10n = FluentLocalization(["en"], cache=CacheConfig())
        assert l10n.cache_enabled is True

    def test_cache_enabled_property_when_disabled(self) -> None:
        """cache_enabled property returns False when no CacheConfig is provided."""
        l10n = FluentLocalization(["en"])
        assert l10n.cache_enabled is False

    def test_cache_config_property_when_enabled(self) -> None:
        """cache_config property returns CacheConfig when caching enabled."""
        l10n = FluentLocalization(["en"], cache=CacheConfig(size=500))
        assert l10n.cache_config is not None
        assert l10n.cache_config.size == 500

    def test_cache_config_property_when_disabled(self) -> None:
        """cache_config returns None when caching disabled."""
        l10n = FluentLocalization(["en"])
        assert l10n.cache_config is None

    def test_bundle_cache_properties_reflect_localization_config(self) -> None:
        """Individual bundles reflect FluentLocalization cache config."""
        l10n = FluentLocalization(["lv", "en"], cache=CacheConfig(size=250))

        # Check all bundles have matching config
        for bundle in l10n.get_bundles():
            assert bundle.cache_enabled is True
            assert bundle.cache_config is not None
            assert bundle.cache_config.size == 250
