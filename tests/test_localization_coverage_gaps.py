"""Tests to achieve 100% coverage for ftllexengine.localization module.

Targets specific uncovered lines identified by coverage analysis.
"""

from ftllexengine.localization import FluentLocalization, ResourceLoader


class CustomResourceLoader(ResourceLoader):
    """Custom resource loader (not PathResourceLoader) for testing line 228."""

    def __init__(self, resources: dict[str, dict[str, str]]) -> None:
        """Initialize with pre-defined resources.

        Args:
            resources: Dict mapping locale -> {resource_id -> ftl_content}
        """
        self.resources = resources

    def load(self, locale: str, resource_id: str) -> str:
        """Load FTL resource for locale.

        Args:
            locale: Locale code
            resource_id: Resource identifier

        Returns:
            FTL source content

        Raises:
            FileNotFoundError: If resource not found
        """
        if locale not in self.resources or resource_id not in self.resources[locale]:
            msg = f"Resource {resource_id} not found for locale {locale}"
            raise FileNotFoundError(msg)
        return self.resources[locale][resource_id]


class TestFluentLocalizationRepr:
    """Tests for FluentLocalization.__repr__ method.

    v0.29.0: Format changed to show initialized/total bundles due to lazy initialization.
    """

    def test_repr_shows_locales_and_bundle_count(self) -> None:
        """Verify __repr__ returns formatted string with locales and bundle count."""
        l10n = FluentLocalization(locales=["lv", "en"])
        repr_str = repr(l10n)

        assert "FluentLocalization" in repr_str
        assert "lv" in repr_str
        assert "en" in repr_str
        # v0.29.0: Lazy init shows initialized/total (0/2 until bundles accessed)
        assert "bundles=0/2" in repr_str

    def test_repr_single_locale(self) -> None:
        """Verify __repr__ works with single locale."""
        l10n = FluentLocalization(locales=["en"])
        repr_str = repr(l10n)

        assert "FluentLocalization" in repr_str
        assert "en" in repr_str
        # v0.29.0: Lazy init shows initialized/total
        assert "bundles=0/1" in repr_str

    def test_repr_after_bundle_access(self) -> None:
        """Verify __repr__ shows initialized bundles after access."""
        l10n = FluentLocalization(locales=["lv", "en"])
        l10n.add_resource("lv", "msg = Sveiki")

        repr_str = repr(l10n)

        # After adding resource, lv bundle is initialized
        assert "bundles=1/2" in repr_str


class TestCustomResourceLoader:
    """Tests for non-PathResourceLoader path (line 228)."""

    def test_custom_resource_loader_source_path(self) -> None:
        """Verify FluentLocalization handles non-PathResourceLoader (line 228)."""
        # Create custom resource loader with test data
        resources = {
            "en": {
                "test.ftl": "greeting = Hello\n"
            },
            "lv": {
                "test.ftl": "greeting = Sveiki\n"
            }
        }
        custom_loader = CustomResourceLoader(resources)

        # Create localization with custom loader
        l10n = FluentLocalization(
            locales=["lv", "en"],
            resource_ids=["test.ftl"],
            resource_loader=custom_loader,
        )

        # Verify it works (this exercises line 228)
        result, errors = l10n.format_value("greeting")
        assert result == "Sveiki"
        assert errors == ()

    def test_custom_resource_loader_fallback(self) -> None:
        """Verify custom loader fallback works."""
        # Resource only exists for fallback locale
        resources = {
            "en": {
                "test.ftl": "greeting = Hello\n"
            }
        }
        custom_loader = CustomResourceLoader(resources)

        # Create localization with lv primary, en fallback
        l10n = FluentLocalization(
            locales=["lv", "en"],
            resource_ids=["test.ftl"],
            resource_loader=custom_loader,
        )

        # Should fall back to English
        result, errors = l10n.format_value("greeting")
        assert result == "Hello"
        assert errors == ()
