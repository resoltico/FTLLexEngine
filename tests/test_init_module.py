"""Tests for the ftllexengine package __init__.py module.

Covers the full lifecycle of the package entry point:
- Direct attribute access (Babel-optional via try/except imports)
- Symbol identity: top-level names alias the same objects as submodule imports
- Babel-optional ImportError with actionable diagnostic message (parser-only install)
- AttributeError for genuinely unknown attributes
- ParseResult is Babel-independent (importable without Babel via diagnostics)
- Fallback version when package metadata is unavailable
- __all__ integrity: every exported name is accessible
"""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock, patch

import pytest


class TestBabelOptionalSymbolAccess:
    """Babel-optional symbols (CacheConfig, FluentBundle, etc.) are accessible when installed."""

    def test_cache_config_is_accessible(self) -> None:
        """CacheConfig resolves to the class in runtime.cache_config."""
        import ftllexengine

        assert hasattr(ftllexengine, "CacheConfig")
        from ftllexengine.runtime.cache_config import CacheConfig as Direct

        assert ftllexengine.CacheConfig is Direct

    def test_fluent_value_is_accessible(self) -> None:
        """FluentValue resolves to the type alias in runtime.value_types."""
        import ftllexengine

        assert hasattr(ftllexengine, "FluentValue")
        from ftllexengine.runtime.function_bridge import FluentValue as Direct

        assert ftllexengine.FluentValue is Direct

    def test_fluent_function_is_accessible(self) -> None:
        """fluent_function resolves to the decorator in runtime.function_bridge."""
        import ftllexengine

        assert callable(ftllexengine.fluent_function)
        from ftllexengine.runtime.function_bridge import fluent_function as direct_ref

        assert ftllexengine.fluent_function is direct_ref

    def test_fluent_bundle_is_accessible(self) -> None:
        """FluentBundle resolves to the class in the runtime package."""
        import ftllexengine

        assert hasattr(ftllexengine, "FluentBundle")
        from ftllexengine.runtime import FluentBundle as Direct

        assert ftllexengine.FluentBundle is Direct

    def test_fluent_localization_is_accessible(self) -> None:
        """FluentLocalization resolves to the class in the localization package."""
        import ftllexengine

        assert hasattr(ftllexengine, "FluentLocalization")
        from ftllexengine.localization import FluentLocalization as Direct

        assert ftllexengine.FluentLocalization is Direct

    def test_get_cldr_version_is_callable(self) -> None:
        """get_cldr_version is callable and returns a non-empty string."""
        import ftllexengine

        fn = ftllexengine.get_cldr_version
        assert callable(fn)
        version = fn()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_get_currency_decimal_digits_resolves(self) -> None:
        """get_currency_decimal_digits is callable from the top-level package."""
        import ftllexengine

        fn = ftllexengine.get_currency_decimal_digits
        assert callable(fn)
        assert fn("EUR") == 2
        assert fn("JPY") == 0


class TestParseResultBabelIndependent:
    """ParseResult is defined in diagnostics and importable without Babel."""

    def test_parse_result_accessible_from_top_level(self) -> None:
        """ParseResult is accessible from the top-level package."""
        import ftllexengine

        assert hasattr(ftllexengine, "ParseResult")

    def test_parse_result_identity_with_diagnostics(self) -> None:
        """ftllexengine.ParseResult is the same object as diagnostics.ParseResult."""
        import ftllexengine
        from ftllexengine.diagnostics import ParseResult as DiagnosticsParseResult

        assert ftllexengine.ParseResult is DiagnosticsParseResult

    def test_parse_result_identity_with_parsing(self) -> None:
        """ftllexengine.ParseResult is the same object as parsing.ParseResult."""
        import ftllexengine
        from ftllexengine.parsing import ParseResult as ParsingParseResult

        assert ftllexengine.ParseResult is ParsingParseResult

    def test_parse_result_in_all(self) -> None:
        """ParseResult is listed in ftllexengine.__all__."""
        import ftllexengine

        assert "ParseResult" in ftllexengine.__all__

    def test_parse_result_in_module_dict_immediately(self) -> None:
        """ParseResult is in module dict at import time (not lazy-loaded)."""
        import ftllexengine

        assert "ParseResult" in vars(ftllexengine)


class TestBabelOptionalAttrsSet:
    """_BABEL_OPTIONAL_ATTRS contains exactly the Babel-dependent symbol names."""

    def test_babel_optional_attrs_contains_expected_names(self) -> None:
        """_BABEL_OPTIONAL_ATTRS lists the Babel-dependent symbols."""
        import ftllexengine

        expected = {
            "CacheConfig",
            "FluentBundle",
            "FluentLocalization",
            "FluentValue",
            "fluent_function",
            "get_cldr_version",
            "get_currency_decimal_digits",
        }
        assert expected == ftllexengine._BABEL_OPTIONAL_ATTRS  # type: ignore[attr-defined]


class TestBabelImportErrorPath:
    """Babel import failures produce an actionable error message.

    Simulates Babel unavailability by re-importing ftllexengine in an environment
    where runtime imports fail. In a real parser-only installation the same code
    path is triggered when Babel is not installed.
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
                    or (name.startswith("ftllexengine") and "localization" in name)
                    or (level > 0 and "localization" in name)
                )
                if is_runtime_import:
                    raise ImportError("No module named 'babel'")
                return original_import(name, globs, locs, fromlist, level)

            builtins.__import__ = mock_import
            try:
                ftllexengine = importlib.import_module("ftllexengine")

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

    def test_babel_import_error_message_for_cache_config(self) -> None:
        """ImportError for CacheConfig provides an install-command hint."""
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
                    or (name.startswith("ftllexengine") and "localization" in name)
                    or (level > 0 and "localization" in name)
                )
                if is_runtime_import:
                    raise ImportError("No module named 'babel'")
                return original_import(name, globs, locs, fromlist, level)

            builtins.__import__ = mock_import
            try:
                ftllexengine = importlib.import_module("ftllexengine")

                with pytest.raises(
                    ImportError,
                    match=r"CacheConfig requires Babel.*pip install ftllexengine\[babel\]",
                ):
                    _ = ftllexengine.CacheConfig
            finally:
                builtins.__import__ = original_import

        finally:
            all_ftl_modules = [
                n for n in sys.modules if n == "ftllexengine" or n.startswith("ftllexengine.")
            ]
            for m in all_ftl_modules:
                del sys.modules[m]
            sys.modules.update(saved_modules)


class TestUnknownAttributeError:
    """Accessing attributes not in _BABEL_OPTIONAL_ATTRS raises AttributeError."""

    def test_unknown_attribute_raises_attribute_error(self) -> None:
        """Accessing an unknown attribute raises AttributeError with a clear message."""
        import ftllexengine

        with pytest.raises(
            AttributeError,
            match=r"module 'ftllexengine' has no attribute 'NonExistentAttribute'",
        ):
            _ = ftllexengine.NonExistentAttribute  # type: ignore[attr-defined]

    def test_unknown_attribute_not_in_optional_attrs(self) -> None:
        """Attributes outside _BABEL_OPTIONAL_ATTRS raise AttributeError directly."""
        import ftllexengine

        with pytest.raises(AttributeError):
            _ = ftllexengine.some_random_name  # type: ignore[attr-defined]

        with pytest.raises(AttributeError):
            _ = ftllexengine._private_attr  # type: ignore[attr-defined]

        with pytest.raises(AttributeError):
            _ = ftllexengine.UNKNOWN_CONSTANT  # type: ignore[attr-defined]


class TestDirectImportIntrospectionSymbols:
    """MessageVariableValidationResult and validate_message_variables imported directly."""

    def test_message_variable_validation_result_importable(self) -> None:
        """MessageVariableValidationResult is accessible from the top-level package."""
        import ftllexengine

        assert hasattr(ftllexengine, "MessageVariableValidationResult")
        assert "MessageVariableValidationResult" in ftllexengine.__all__

    def test_validate_message_variables_importable(self) -> None:
        """validate_message_variables is accessible from the top-level package."""
        import ftllexengine

        assert hasattr(ftllexengine, "validate_message_variables")
        assert callable(ftllexengine.validate_message_variables)
        assert "validate_message_variables" in ftllexengine.__all__


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

        assert len(ftllexengine.__all__) == 39

    def test_babel_optional_exports_are_in_all(self) -> None:
        """Babel-optional symbols (FluentBundle, etc.) are listed in __all__."""
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
