"""Edge case tests for localization.py to achieve 100% coverage.

Tests defensive code paths and edge cases that rarely occur in normal usage.
"""

from pathlib import Path

from ftllexengine.localization import FluentLocalization, PathResourceLoader


class TestPathResourceLoaderEdgeCases:
    """Edge cases for PathResourceLoader."""

    def test_base_path_without_locale_placeholder(self) -> None:
        """Defensive handling when base_path contains no {locale} placeholder.

        This tests line 273 in localization.py - the fallback when split('{locale}')
        returns an empty list (which is actually impossible with Python's split(),
        but the code handles it defensively).

        Since split() always returns at least one element, we test the else branch
        at line 271 when static_prefix is empty string.
        """
        # Create loader with base_path that has empty static prefix
        # e.g., "{locale}" by itself would have "" as prefix after split
        loader = PathResourceLoader("{locale}")

        # The loader should initialize without error
        # root_dir defaults to cwd when static_prefix is empty
        assert loader._resolved_root == Path.cwd().resolve()

    def test_root_dir_with_empty_static_prefix(self) -> None:
        """PathResourceLoader handles edge case of empty static prefix before {locale}."""
        # When base_path is just "{locale}/file.ftl", the static prefix before {locale} is ""
        loader = PathResourceLoader("{locale}/file.ftl")

        # Should default to cwd when static prefix is empty
        assert loader._resolved_root == Path.cwd().resolve()


class TestFluentLocalizationAddFunctionToExistingBundles:
    """Test add_function() applying to already-created bundles."""

    def test_add_function_after_bundle_creation(self) -> None:
        """Custom function added to already-initialized bundles.

        This tests line 895 in localization.py - the loop that applies functions
        to bundles that have already been created (lazy initialization).
        """
        l10n = FluentLocalization(["lv", "en"], use_isolating=False)

        # Add resources which will trigger bundle creation
        l10n.add_resource("lv", "msg = { $text }")
        l10n.add_resource("en", "msg = { $text }")

        # Format to ensure bundles are created
        l10n.format_value("msg", {"text": "hello"})

        # Now add function - should apply to already-created bundles
        def custom_function(value: str) -> str:
            return value.upper()

        l10n.add_function("CUSTOM", custom_function)

        # Update resources to use the function
        l10n.add_resource("lv", "msg2 = { CUSTOM($text) }")
        l10n.add_resource("en", "msg2 = { CUSTOM($text) }")

        # Verify function was added to each bundle individually
        for locale in ["lv", "en"]:
            bundle = l10n._bundles[locale]
            result, errors = bundle.format_pattern("msg2", {"text": "test"})
            assert len(errors) == 0, f"Function not available in {locale} bundle"
            assert result == "TEST", f"Function not working in {locale} bundle"

    def test_add_function_to_multiple_existing_bundles(self) -> None:
        """Function propagates to all existing bundles."""
        l10n = FluentLocalization(["lv", "en", "fr"], use_isolating=False)

        # Create all bundles by adding resources
        for locale in ["lv", "en", "fr"]:
            l10n.add_resource(locale, f"msg = {locale}")
            # Ensure bundle is created
            bundle = l10n._get_or_create_bundle(locale)
            assert bundle is not None

        # Add function to all existing bundles
        def upper_function(value: str) -> str:
            return value.upper()

        l10n.add_function("UPPER", upper_function)

        # Add messages using the function
        for locale in ["lv", "en", "fr"]:
            l10n.add_resource(locale, "test = { UPPER($x) }")

        # Verify function works in each bundle individually
        for locale in ["lv", "en", "fr"]:
            bundle = l10n._bundles[locale]
            result, errors = bundle.format_pattern("test", {"x": "abc"})
            assert len(errors) == 0, f"Function not available in {locale} bundle"
            assert result == "ABC", f"Function not working in {locale} bundle"
