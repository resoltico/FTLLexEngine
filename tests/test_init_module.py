"""Tests for the ftllexengine package __init__.py module.

Covers the full lifecycle of the package entry point:
- Lazy attribute loading (Babel-independent and Babel-required)
- Module-level cache behavior (hit/miss/population)
- Exhaustiveness guards for unregistered attribute names
- AttributeError for genuinely unknown attributes
- Babel ImportError with actionable diagnostic message
- Fallback version when package metadata is unavailable
- __all__ integrity: every exported name is accessible
"""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    pass


class TestLazyImportCacheConfig:
    """CacheConfig is lazily imported from runtime.cache_config."""

    def test_cache_config_lazy_import(self) -> None:
        """CacheConfig resolves to the class in runtime.cache_config."""
        import ftllexengine

        # Remove from module dict to force fresh lazy load via __getattr__
        ftllexengine.__dict__.pop("CacheConfig", None)

        cache_config_cls = ftllexengine.CacheConfig

        assert cache_config_cls is not None
        from ftllexengine.runtime.cache_config import CacheConfig as Direct

        assert cache_config_cls is Direct

    def test_cache_config_cached_on_second_access(self) -> None:
        """CacheConfig is cached after first access; subsequent accesses return the same object."""
        import ftllexengine

        # Remove from module dict to force fresh lazy load via __getattr__
        ftllexengine.__dict__.pop("CacheConfig", None)

        first = ftllexengine.CacheConfig
        second = ftllexengine.CacheConfig
        assert first is second
        # __getattr__ stores the result in globals() (module dict) on first access
        assert "CacheConfig" in vars(ftllexengine)


class TestLoadBabelIndependentAssertionError:
    """__getattr__ raises AssertionError for names in _BABEL_INDEPENDENT_ATTRS with no case arm."""

    def test_unknown_babel_independent_name_raises_assertion_error(self) -> None:
        """__getattr__ raises AssertionError for names registered but without a case arm.

        The exhaustiveness guard in the match/case dispatch distinguishes
        an internal invariant violation (frozenset and case arms out of sync)
        from a legitimate caller attribute error.
        """
        import ftllexengine

        original_attrs = ftllexengine._BABEL_INDEPENDENT_ATTRS  # type: ignore[attr-defined]
        ftllexengine._BABEL_INDEPENDENT_ATTRS = frozenset(  # type: ignore[attr-defined]
            {*original_attrs, "UnknownBabelIndependentName"}
        )
        try:
            with pytest.raises(AssertionError, match="unhandled Babel-independent attribute"):
                _ = ftllexengine.UnknownBabelIndependentName  # type: ignore[attr-defined]
        finally:
            ftllexengine._BABEL_INDEPENDENT_ATTRS = original_attrs  # type: ignore[attr-defined]


class TestLazyImportFluentLocalization:
    """FluentLocalization is lazily imported from the localization package."""

    def test_fluent_localization_lazy_import(self) -> None:
        """FluentLocalization resolves to the class in the localization package."""
        import ftllexengine

        # Remove from module dict to force fresh lazy load via __getattr__
        ftllexengine.__dict__.pop("FluentLocalization", None)

        localization_cls = ftllexengine.FluentLocalization

        assert localization_cls is not None
        from ftllexengine.localization import FluentLocalization as Direct

        assert localization_cls is Direct

    def test_fluent_localization_cached_on_second_access(self) -> None:
        """FluentLocalization is cached after first access."""
        import ftllexengine

        # Remove from module dict to force fresh lazy load via __getattr__
        ftllexengine.__dict__.pop("FluentLocalization", None)

        first = ftllexengine.FluentLocalization
        second = ftllexengine.FluentLocalization
        assert first is second
        # __getattr__ stores the result in globals() (module dict) on first access
        assert "FluentLocalization" in vars(ftllexengine)


class TestBabelRequiredCacheHit:
    """Cache hit path for Babel-required attributes returns the cached object."""

    def test_fluent_bundle_cache_hit_returns_same_object(self) -> None:
        """Second access to FluentBundle returns the cached class object."""
        import ftllexengine

        first = ftllexengine.FluentBundle
        second = ftllexengine.FluentBundle
        assert first is second

    def test_fluent_localization_cache_hit_returns_same_object(self) -> None:
        """Second access to FluentLocalization returns the cached class object."""
        import ftllexengine

        first = ftllexengine.FluentLocalization
        second = ftllexengine.FluentLocalization
        assert first is second

    def test_babel_required_unhandled_attr_raises_assertion_error(self) -> None:
        """Attr in _BABEL_REQUIRED_ATTRS with no match/case arm raises AssertionError.

        A name registered in _BABEL_REQUIRED_ATTRS without a corresponding case arm
        is an internal invariant violation. AssertionError distinguishes this from
        AttributeError at the API boundary and makes frozenset/case-arm drift
        immediately visible during development.
        """
        import ftllexengine

        original_attrs = ftllexengine._BABEL_REQUIRED_ATTRS  # type: ignore[attr-defined]
        ftllexengine._BABEL_REQUIRED_ATTRS = frozenset(  # type: ignore[attr-defined]
            {"FluentBundle", "FluentLocalization", "_FakeBabelRequiredAttr"}
        )
        try:
            with pytest.raises(AssertionError, match="unhandled Babel-required attribute"):
                _ = ftllexengine._FakeBabelRequiredAttr  # type: ignore[attr-defined]
        finally:
            ftllexengine._BABEL_REQUIRED_ATTRS = original_attrs  # type: ignore[attr-defined]


class TestLazyImportFluentValue:
    """FluentValue is lazily imported from runtime.value_types."""

    def test_fluent_value_lazy_import(self) -> None:
        """FluentValue resolves to the type alias in runtime.value_types."""
        import ftllexengine

        fluent_value_type = ftllexengine.FluentValue

        assert fluent_value_type is not None
        from ftllexengine.runtime.function_bridge import FluentValue as Direct

        assert fluent_value_type is Direct

    def test_fluent_value_cached_on_second_access(self) -> None:
        """FluentValue is cached after first access."""
        import ftllexengine

        # Remove from module dict to force fresh lazy load via __getattr__
        ftllexengine.__dict__.pop("FluentValue", None)

        first = ftllexengine.FluentValue
        second = ftllexengine.FluentValue

        assert first is second
        # __getattr__ stores the result in globals() (module dict) on first access
        assert "FluentValue" in vars(ftllexengine)


class TestLazyImportFluentFunction:
    """fluent_function is lazily imported from runtime.function_bridge."""

    def test_fluent_function_lazy_import(self) -> None:
        """fluent_function resolves to the decorator in runtime.function_bridge."""
        import ftllexengine

        decorator = ftllexengine.fluent_function

        assert callable(decorator)
        from ftllexengine.runtime.function_bridge import (
            fluent_function as fluent_func_ref,
        )

        assert decorator is fluent_func_ref

    def test_fluent_function_cached_on_second_access(self) -> None:
        """fluent_function is cached after first access."""
        import ftllexengine

        # Remove from module dict to force fresh lazy load via __getattr__
        ftllexengine.__dict__.pop("fluent_function", None)

        first = ftllexengine.fluent_function
        second = ftllexengine.fluent_function

        assert first is second
        # __getattr__ stores the result in globals() (module dict) on first access
        assert "fluent_function" in vars(ftllexengine)


class TestUnknownAttributeError:
    """Accessing attributes not registered in any dispatch table raises AttributeError."""

    def test_unknown_attribute_raises_attribute_error(self) -> None:
        """Accessing an unknown attribute raises AttributeError with a clear message."""
        import ftllexengine

        with pytest.raises(
            AttributeError,
            match=r"module 'ftllexengine' has no attribute 'NonExistentAttribute'",
        ):
            _ = ftllexengine.NonExistentAttribute  # type: ignore[attr-defined]

    def test_unknown_attribute_not_in_babel_required(self) -> None:
        """Attributes outside all dispatch sets raise AttributeError directly."""
        import ftllexengine

        with pytest.raises(AttributeError):
            _ = ftllexengine.some_random_name  # type: ignore[attr-defined]

        with pytest.raises(AttributeError):
            _ = ftllexengine._private_attr  # type: ignore[attr-defined]

        with pytest.raises(AttributeError):
            _ = ftllexengine.UNKNOWN_CONSTANT  # type: ignore[attr-defined]


class TestBabelImportErrorPath:
    """Babel import failures produce an actionable error message.

    Simulates Babel unavailability by mocking builtins.__import__ to raise
    ImportError for runtime imports. In a real parser-only installation the
    same code path is triggered when Babel is not installed.
    """

    def test_babel_import_error_message_for_fluent_bundle(self) -> None:
        """ImportError for FluentBundle provides an install-command hint."""
        saved_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "ftllexengine" or name.startswith("ftllexengine.")
        }

        try:
            for module_name in list(saved_modules.keys()):
                if module_name in sys.modules:
                    del sys.modules[module_name]

            import builtins
            import importlib

            original_import = builtins.__import__

            def mock_import(name, globs=None, locs=None, fromlist=(), level=0):
                is_runtime_import = (
                    name == "ftllexengine.runtime"
                    or (name.startswith("ftllexengine") and "runtime" in name)
                    or (level > 0 and "runtime" in name)
                )
                if is_runtime_import:
                    raise ImportError("No module named 'babel'")
                return original_import(name, globs, locs, fromlist, level)

            ftllexengine = importlib.import_module("ftllexengine")
            # Fresh module import - lazy attrs are not yet populated in module dict

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
            all_ftl_modules = [
                n for n in sys.modules if n == "ftllexengine" or n.startswith("ftllexengine.")
            ]
            for m in all_ftl_modules:
                del sys.modules[m]
            sys.modules.update(saved_modules)

    def test_non_babel_import_error_is_reraised(self) -> None:
        """Non-Babel ImportErrors are re-raised unchanged (not wrapped)."""
        saved_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "ftllexengine" or name.startswith("ftllexengine.")
        }

        try:
            for module_name in list(saved_modules.keys()):
                if module_name in sys.modules:
                    del sys.modules[module_name]

            import builtins
            import importlib

            original_import = builtins.__import__

            def mock_import(name, globs=None, locs=None, fromlist=(), level=0):
                is_runtime_import = (
                    name == "ftllexengine.runtime"
                    or (name.startswith("ftllexengine") and "runtime" in name)
                    or (level > 0 and "runtime" in name)
                )
                if is_runtime_import:
                    raise ImportError("Circular import detected in some_other_module")
                return original_import(name, globs, locs, fromlist, level)

            ftllexengine = importlib.import_module("ftllexengine")
            # Fresh module import - lazy attrs are not yet populated in module dict

            builtins.__import__ = mock_import
            try:
                with pytest.raises(ImportError, match=r"Circular import"):
                    _ = ftllexengine.FluentBundle
            finally:
                builtins.__import__ = original_import

        finally:
            all_ftl_modules = [
                n for n in sys.modules if n == "ftllexengine" or n.startswith("ftllexengine.")
            ]
            for m in all_ftl_modules:
                del sys.modules[m]
            sys.modules.update(saved_modules)


def test_package_not_found_error() -> None:
    """PackageNotFoundError during metadata lookup sets __version__ to the dev fallback.

    Covers the except branch in the version detection block: when
    importlib.metadata.version() raises PackageNotFoundError (e.g. development
    checkout without a pip install), __version__ defaults to '0.0.0+dev'.
    """
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "ftllexengine" or name.startswith("ftllexengine.")
    }

    try:
        for module_name in list(saved_modules.keys()):
            if module_name in sys.modules:
                del sys.modules[module_name]

        mock_version = MagicMock(side_effect=PackageNotFoundError("ftllexengine"))

        with patch("importlib.metadata.version", mock_version):
            import ftllexengine

            assert ftllexengine.__version__ == "0.0.0+dev", (
                "Expected fallback version '0.0.0+dev' when package not found, "
                f"got {ftllexengine.__version__!r}"
            )
    finally:
        all_ftllexengine_modules = [
            name
            for name in sys.modules
            if name == "ftllexengine" or name.startswith("ftllexengine.")
        ]
        for module_name in all_ftllexengine_modules:
            del sys.modules[module_name]

        sys.modules.update(saved_modules)


class TestInitModuleExports:
    """__all__ integrity: every exported name must be accessible from ftllexengine."""

    def test_all_exports_are_accessible(self) -> None:
        """Every name in ftllexengine.__all__ resolves without error."""
        import ftllexengine

        for name in ftllexengine.__all__:
            assert hasattr(ftllexengine, name), (
                f"ftllexengine.__all__ contains {name!r} but "
                f"ftllexengine.{name} raises AttributeError"
            )

    def test_all_exports_count(self) -> None:
        """__all__ contains exactly the expected number of public exports.

        This acts as a tripwire: if a symbol is added or removed from __all__
        without updating this test, the test fails immediately. The count
        must be updated alongside any __all__ change.
        """
        import ftllexengine

        assert len(ftllexengine.__all__) == 33

    def test_lazy_exports_are_in_all(self) -> None:
        """Lazy-loaded symbols (FluentBundle, FluentLocalization, etc.) are in __all__."""
        import ftllexengine

        for name in ("FluentBundle", "FluentLocalization", "CacheConfig", "FluentValue",
                     "fluent_function"):
            assert name in ftllexengine.__all__, f"{name!r} missing from ftllexengine.__all__"

    def test_error_types_are_in_all(self) -> None:
        """Immutable error types are exported from ftllexengine.__all__."""
        import ftllexengine

        for name in ("FrozenFluentError", "ErrorCategory", "FrozenErrorContext"):
            assert name in ftllexengine.__all__, f"{name!r} missing from ftllexengine.__all__"

    def test_integrity_errors_are_in_all(self) -> None:
        """Data integrity error classes are exported from ftllexengine.__all__."""
        import ftllexengine

        for name in (
            "DataIntegrityError",
            "CacheCorruptionError",
            "FormattingIntegrityError",
            "ImmutabilityViolationError",
            "IntegrityCheckFailedError",
            "IntegrityContext",
            "SyntaxIntegrityError",
            "WriteConflictError",
        ):
            assert name in ftllexengine.__all__, f"{name!r} missing from ftllexengine.__all__"

    def test_parsing_api_is_in_all(self) -> None:
        """parse_ftl, serialize_ftl, and validate_resource are in ftllexengine.__all__."""
        import ftllexengine

        for name in ("parse_ftl", "serialize_ftl", "validate_resource"):
            assert name in ftllexengine.__all__, f"{name!r} missing from ftllexengine.__all__"

    def test_metadata_is_in_all(self) -> None:
        """Version and spec metadata symbols are in ftllexengine.__all__."""
        import ftllexengine

        for name in ("__version__", "__fluent_spec_version__", "__spec_url__",
                     "__recommended_encoding__"):
            assert name in ftllexengine.__all__, f"{name!r} missing from ftllexengine.__all__"
