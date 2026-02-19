"""Error path coverage for __init__.py module.

This module tests:
- Lazy import handlers for Babel-dependent components
- Exception handlers for package metadata and import failures
- Unknown attribute access handling

These are edge cases that rarely occur in production but must be tested
to achieve 100% coverage.
"""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from ftllexengine.runtime.function_bridge import FluentValue


class TestLazyImportCacheConfig:
    """Tests for CacheConfig lazy import (lines 105-108 in _load_babel_independent)."""

    def test_cache_config_lazy_import(self) -> None:
        """CacheConfig is lazily imported from runtime.cache_config."""
        import ftllexengine

        # Access CacheConfig via __getattr__ (lazy load path)
        if "CacheConfig" in ftllexengine._lazy_cache:  # type: ignore[attr-defined]
            del ftllexengine._lazy_cache["CacheConfig"]  # type: ignore[attr-defined]

        cache_config_cls = ftllexengine.CacheConfig

        assert cache_config_cls is not None
        from ftllexengine.runtime.cache_config import CacheConfig as Direct

        assert cache_config_cls is Direct

    def test_cache_config_cached_on_second_access(self) -> None:
        """CacheConfig is cached after first access."""
        import ftllexengine

        if "CacheConfig" in ftllexengine._lazy_cache:  # type: ignore[attr-defined]
            del ftllexengine._lazy_cache["CacheConfig"]  # type: ignore[attr-defined]

        first = ftllexengine.CacheConfig
        second = ftllexengine.CacheConfig
        assert first is second
        assert "CacheConfig" in ftllexengine._lazy_cache  # type: ignore[attr-defined]


class TestLoadBabelIndependentAssertionError:
    """Tests for the AssertionError branch in _load_babel_independent (lines 117-118)."""

    def test_unknown_babel_independent_name_raises_assertion_error(self) -> None:
        """_load_babel_independent raises AssertionError for unknown names."""
        # Call internal function directly with an unknown name
        # This exercises the unreachable AssertionError branch (defensive coding)
        from ftllexengine import _load_babel_independent  # type: ignore[attr-defined]

        with pytest.raises(AssertionError, match="unhandled Babel-independent attribute"):
            _load_babel_independent("UnknownBabelIndependentName")


class TestLazyImportFluentLocalization:
    """Tests for FluentLocalization lazy import (lines 148-152 in __getattr__)."""

    def test_fluent_localization_lazy_import(self) -> None:
        """FluentLocalization is lazily imported from localization module."""
        import ftllexengine

        if "FluentLocalization" in ftllexengine._lazy_cache:  # type: ignore[attr-defined]
            del ftllexengine._lazy_cache["FluentLocalization"]  # type: ignore[attr-defined]

        localization_cls = ftllexengine.FluentLocalization

        assert localization_cls is not None
        from ftllexengine.localization import FluentLocalization as Direct

        assert localization_cls is Direct

    def test_fluent_localization_cached_on_second_access(self) -> None:
        """FluentLocalization is cached after first access."""
        import ftllexengine

        if "FluentLocalization" in ftllexengine._lazy_cache:  # type: ignore[attr-defined]
            del ftllexengine._lazy_cache["FluentLocalization"]  # type: ignore[attr-defined]

        first = ftllexengine.FluentLocalization
        second = ftllexengine.FluentLocalization
        assert first is second
        assert "FluentLocalization" in ftllexengine._lazy_cache  # type: ignore[attr-defined]


class TestBabelRequiredCacheHit:
    """Tests for cache hit path in __getattr__ for Babel-required attrs (line 140)."""

    def test_fluent_bundle_cache_hit_returns_same_object(self) -> None:
        """Second access to FluentBundle returns cached object (line 140)."""
        import ftllexengine

        # Ensure FluentBundle is loaded first
        first = ftllexengine.FluentBundle
        # Second access exercises the cache-hit branch (line 140)
        second = ftllexengine.FluentBundle
        assert first is second

    def test_fluent_localization_cache_hit_returns_same_object(self) -> None:
        """Second access to FluentLocalization returns cached object (line 140)."""
        import ftllexengine

        first = ftllexengine.FluentLocalization
        second = ftllexengine.FluentLocalization
        assert first is second

    def test_babel_required_unhandled_attr_raises_assertion_error(self) -> None:
        """Attr in _BABEL_REQUIRED_ATTRS with no match/case arm raises AssertionError.

        This covers the exhaustive case _: branch in the match/case dispatch inside
        __getattr__. A name registered in _BABEL_REQUIRED_ATTRS without a corresponding
        case arm is an internal invariant violation, not a legitimate attribute error.
        AssertionError distinguishes this from AttributeError at the API boundary.
        """
        import ftllexengine

        original_attrs = ftllexengine._BABEL_REQUIRED_ATTRS  # type: ignore[attr-defined]
        # Temporarily extend to include a fake Babel-required attribute
        ftllexengine._BABEL_REQUIRED_ATTRS = frozenset(  # type: ignore[attr-defined]
            {"FluentBundle", "FluentLocalization", "_FakeBabelRequiredAttr"}
        )
        try:
            # _FakeBabelRequiredAttr is in _BABEL_REQUIRED_ATTRS but has no case arm
            # -> hits case _: raise AssertionError (internal invariant violation)
            with pytest.raises(AssertionError, match="unhandled Babel-required attribute"):
                _ = ftllexengine._FakeBabelRequiredAttr  # type: ignore[attr-defined]
        finally:
            ftllexengine._BABEL_REQUIRED_ATTRS = original_attrs  # type: ignore[attr-defined]


class TestLazyImportFluentValue:
    """Tests for FluentValue lazy import (lines 90-93)."""

    def test_fluent_value_lazy_import(self) -> None:
        """FluentValue is lazily imported from function_bridge."""
        import ftllexengine

        # Access FluentValue via __getattr__
        fluent_value_type = ftllexengine.FluentValue

        # Verify it's the correct type alias
        assert fluent_value_type is not None
        # FluentValue is a type alias, we can verify it's importable
        from ftllexengine.runtime.function_bridge import FluentValue as Direct

        assert fluent_value_type is Direct

    def test_fluent_value_cached_on_second_access(self) -> None:
        """FluentValue is cached after first access."""
        import ftllexengine

        # Clear cache to test fresh import (testing internal API)
        if "FluentValue" in ftllexengine._lazy_cache:  # type: ignore[attr-defined]
            del ftllexengine._lazy_cache["FluentValue"]  # type: ignore[attr-defined]

        # First access
        first = ftllexengine.FluentValue
        # Second access should use cache
        second = ftllexengine.FluentValue

        assert first is second
        assert "FluentValue" in ftllexengine._lazy_cache  # type: ignore[attr-defined]


class TestLazyImportFluentFunction:
    """Tests for fluent_function lazy import (lines 94-97)."""

    def test_fluent_function_lazy_import(self) -> None:
        """fluent_function is lazily imported from function_bridge."""
        import ftllexengine

        # Access fluent_function via __getattr__
        decorator = ftllexengine.fluent_function

        # Verify it's the correct decorator
        assert callable(decorator)
        from ftllexengine.runtime.function_bridge import (
            fluent_function as fluent_func_ref,
        )

        assert decorator is fluent_func_ref

    def test_fluent_function_cached_on_second_access(self) -> None:
        """fluent_function is cached after first access."""
        import ftllexengine

        # Clear cache to test fresh import (testing internal API)
        if "fluent_function" in ftllexengine._lazy_cache:  # type: ignore[attr-defined]
            del ftllexengine._lazy_cache["fluent_function"]  # type: ignore[attr-defined]

        # First access
        first = ftllexengine.fluent_function
        # Second access should use cache
        second = ftllexengine.fluent_function

        assert first is second
        assert "fluent_function" in ftllexengine._lazy_cache  # type: ignore[attr-defined]


class TestUnknownAttributeError:
    """Tests for unknown attribute access (lines 110-111)."""

    def test_unknown_attribute_raises_attribute_error(self) -> None:
        """Accessing unknown attribute raises AttributeError with clear message."""
        import ftllexengine

        with pytest.raises(
            AttributeError,
            match=r"module 'ftllexengine' has no attribute 'NonExistentAttribute'",
        ):
            _ = ftllexengine.NonExistentAttribute  # type: ignore[attr-defined]

    def test_unknown_attribute_not_in_babel_required(self) -> None:
        """Unknown attributes not in BABEL_REQUIRED_ATTRS raise AttributeError."""
        import ftllexengine

        # These are not Babel-required, should raise AttributeError directly
        with pytest.raises(AttributeError):
            _ = ftllexengine.some_random_name  # type: ignore[attr-defined]

        with pytest.raises(AttributeError):
            _ = ftllexengine._private_attr  # type: ignore[attr-defined]

        with pytest.raises(AttributeError):
            _ = ftllexengine.UNKNOWN_CONSTANT  # type: ignore[attr-defined]


class TestBabelImportErrorPath:
    """Tests for Babel import error handling (lines 98-108).

    Note: These tests simulate Babel being unavailable by mocking the import.
    In a real scenario without Babel, the error message guides users to install it.
    """

    def test_babel_import_error_message_for_fluent_bundle(self) -> None:
        """ImportError for FluentBundle provides helpful message."""
        saved_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "ftllexengine" or name.startswith("ftllexengine.")
        }

        try:
            # Remove ftllexengine modules
            for module_name in list(saved_modules.keys()):
                if module_name in sys.modules:
                    del sys.modules[module_name]

            # Clear the lazy cache by reimporting
            import importlib

            # We need to mock the runtime import to fail with babel error
            # Note: Relative imports use level>0, so "from .runtime" passes name="runtime"
            def mock_import(name, globs=None, locs=None, fromlist=(), level=0):
                # Handle both absolute and relative imports to runtime
                is_runtime_import = (
                    name == "ftllexengine.runtime"
                    or (name.startswith("ftllexengine") and "runtime" in name)
                    or (level > 0 and "runtime" in name)
                )
                if is_runtime_import:
                    raise ImportError("No module named 'babel'")
                return original_import(name, globs, locs, fromlist, level)

            import builtins

            original_import = builtins.__import__

            # Import ftllexengine first (this works since core imports don't need Babel)
            ftllexengine = importlib.import_module("ftllexengine")
            ftllexengine._lazy_cache.clear()

            builtins.__import__ = mock_import
            try:
                with pytest.raises(
                    ImportError,
                    match=r"FluentBundle requires Babel.*pip install ftllexengine\[babel\]",
                ):
                    _ = ftllexengine.FluentBundle
            finally:
                builtins.__import__ = original_import

        finally:
            # Cleanup
            all_ftl_modules = [
                n for n in sys.modules if n == "ftllexengine" or n.startswith("ftllexengine.")
            ]
            for m in all_ftl_modules:
                del sys.modules[m]
            sys.modules.update(saved_modules)

    def test_non_babel_import_error_is_reraised(self) -> None:
        """Non-Babel ImportErrors are re-raised unchanged (line 108)."""
        saved_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "ftllexengine" or name.startswith("ftllexengine.")
        }

        try:
            # Remove ftllexengine modules
            for module_name in list(saved_modules.keys()):
                if module_name in sys.modules:
                    del sys.modules[module_name]

            import builtins
            import importlib

            original_import = builtins.__import__

            # Mock to raise a non-Babel ImportError
            # Note: Relative imports use level>0, so "from .runtime" passes name="runtime"
            def mock_import(name, globs=None, locs=None, fromlist=(), level=0):
                is_runtime_import = (
                    name == "ftllexengine.runtime"
                    or (name.startswith("ftllexengine") and "runtime" in name)
                    or (level > 0 and "runtime" in name)
                )
                if is_runtime_import:
                    # Raise error that does NOT mention babel
                    raise ImportError("Circular import detected in some_other_module")
                return original_import(name, globs, locs, fromlist, level)

            # Import ftllexengine first
            ftllexengine = importlib.import_module("ftllexengine")
            ftllexengine._lazy_cache.clear()

            builtins.__import__ = mock_import
            try:
                # Should re-raise the original ImportError (not wrap it)
                with pytest.raises(ImportError, match=r"Circular import"):
                    _ = ftllexengine.FluentBundle
            finally:
                builtins.__import__ = original_import

        finally:
            # Cleanup
            all_ftl_modules = [
                n for n in sys.modules if n == "ftllexengine" or n.startswith("ftllexengine.")
            ]
            for m in all_ftl_modules:
                del sys.modules[m]
            sys.modules.update(saved_modules)


# Note: importlib.metadata availability test removed - Python 3.13+ guarantees it


def test_package_not_found_error():
    """Test PackageNotFoundError handling when package is not installed.

    This tests lines 148-151 in __init__.py.

    Scenario: importlib.metadata.version() raises PackageNotFoundError
    Expected: __version__ defaults to '0.0.0+dev'
    """
    # Save ALL ftllexengine.* modules before manipulation
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "ftllexengine" or name.startswith("ftllexengine.")
    }

    try:
        # Remove all ftllexengine modules to force re-import
        for module_name in list(saved_modules.keys()):
            if module_name in sys.modules:
                del sys.modules[module_name]

        # Mock importlib.metadata.version to raise PackageNotFoundError
        mock_version = MagicMock(side_effect=PackageNotFoundError("ftllexengine"))

        with patch("importlib.metadata.version", mock_version):
            # Import should succeed with fallback version
            import ftllexengine

            assert ftllexengine.__version__ == "0.0.0+dev", (
                "Expected fallback version '0.0.0+dev' when package not found, "
                f"got {ftllexengine.__version__!r}"
            )
    finally:
        # Complete cleanup: remove ALL ftllexengine modules (including any newly created)
        all_ftllexengine_modules = [
            name
            for name in sys.modules
            if name == "ftllexengine" or name.startswith("ftllexengine.")
        ]
        for module_name in all_ftllexengine_modules:
            del sys.modules[module_name]

        # Restore ALL original modules
        sys.modules.update(saved_modules)


def test_package_not_found_hypothesis_strategy():
    """Property-based test: PackageNotFoundError always sets dev version.

    Uses Hypothesis to ensure the fallback version is deterministic
    regardless of package name or error message.

    Note: This test uses a nested @given decorator due to the complex
    sys.modules manipulation required for each example. HypoFuzz cannot
    discover nested @given tests, but the test runs during normal pytest.
    """
    from hypothesis import event, given
    from hypothesis import strategies as st

    # Save ALL ftllexengine.* modules before manipulation
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "ftllexengine" or name.startswith("ftllexengine.")
    }

    try:
        from hypothesis import settings

        @settings(deadline=None)
        @given(package_name=st.text(min_size=1, max_size=50))
        def property_test(package_name):
            name_len = len(package_name)
            event(f"input_len={name_len}")
            # Remove all ftllexengine modules for each test run
            all_ftllexengine_modules = [
                name
                for name in list(sys.modules.keys())
                if name == "ftllexengine" or name.startswith("ftllexengine.")
            ]
            for module_name in all_ftllexengine_modules:
                del sys.modules[module_name]

            # Mock with varying package names
            mock_version = MagicMock(side_effect=PackageNotFoundError(package_name))

            with patch("importlib.metadata.version", mock_version):
                import ftllexengine

                # Invariant: dev version is always '0.0.0+dev'
                assert ftllexengine.__version__ == "0.0.0+dev"

        # Run property test - Hypothesis provides the argument via @given decorator
        property_test()  # pylint: disable=no-value-for-parameter

    finally:
        # Complete cleanup after all Hypothesis runs
        all_ftllexengine_modules = [
            name
            for name in sys.modules
            if name == "ftllexengine" or name.startswith("ftllexengine.")
        ]
        for module_name in all_ftllexengine_modules:
            del sys.modules[module_name]

        # Restore ALL original modules
        sys.modules.update(saved_modules)
