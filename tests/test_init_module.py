"""Tests for the ftllexengine package __init__.py module.

Covers the full lifecycle of the package entry point:
- Direct attribute access across parser-only-safe and Babel-backed exports
- Symbol identity: top-level names alias the same objects as submodule imports
- Babel-optional ImportError with actionable diagnostic message (parser-only install)
- Parser-only installs keep zero-dependency runtime/localization helpers available
- AttributeError for genuinely unknown attributes
- ParseResult is Babel-independent (importable without Babel via diagnostics)
- Fallback version when package metadata is unavailable
- __all__ integrity: every exported name is accessible
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


def _snapshot_ftl_modules() -> dict[str, ModuleType]:
    """Capture loaded ftllexengine modules for later restoration."""
    return {
        name: module
        for name, module in sys.modules.items()
        if name == "ftllexengine" or name.startswith("ftllexengine.")
    }


def _clear_ftl_modules() -> None:
    """Remove loaded ftllexengine modules from sys.modules."""
    for module_name in [
        name for name in sys.modules if name == "ftllexengine" or name.startswith("ftllexengine.")
    ]:
        del sys.modules[module_name]


@contextmanager
def _fresh_ftl_import(
    *,
    block_babel: bool = False,
    blocked_imports: frozenset[str] = frozenset(),
) -> Iterator[ModuleType]:
    """Import a fresh ftllexengine module with optional Babel blocking."""
    import builtins
    import importlib

    saved_modules = _snapshot_ftl_modules()
    original_import = builtins.__import__

    def mock_import(name, globs=None, locs=None, fromlist=(), level=0):
        if block_babel and (name == "babel" or name.startswith("babel.")):
            raise ImportError("No module named 'babel'")
        if name in blocked_imports or any(name.startswith(prefix + ".") for prefix in blocked_imports):
            message = f"blocked import: {name}"
            raise ModuleNotFoundError(message)
        return original_import(name, globs, locs, fromlist, level)

    try:
        _clear_ftl_modules()
        builtins.__import__ = mock_import
        yield importlib.import_module("ftllexengine")
    finally:
        builtins.__import__ = original_import
        _clear_ftl_modules()
        sys.modules.update(saved_modules)


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

    def test_fluent_number_is_accessible(self) -> None:
        """FluentNumber resolves to the class in the runtime package."""
        import ftllexengine

        assert hasattr(ftllexengine, "FluentNumber")
        from ftllexengine.runtime import FluentNumber as Direct

        assert ftllexengine.FluentNumber is Direct

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
            "AsyncFluentBundle",
            "FluentBundle",
            "FluentLocalization",
            "LocalizationBootConfig",
            "LocalizationCacheStats",
        }
        assert expected == ftllexengine._BABEL_OPTIONAL_ATTRS  # type: ignore[attr-defined]


class TestParserOnlyFacadeBehavior:
    """Parser-only installs keep zero-dependency exports while gating Babel-backed facades."""

    def test_direct_optional_attribute_access_provides_install_guidance(self) -> None:
        """Direct optional attribute access raises AttributeError with install guidance."""
        with (
            _fresh_ftl_import(block_babel=True) as ftllexengine,
            pytest.raises(
                AttributeError,
                match=r"FluentBundle requires the full runtime install.*pip install ftllexengine\[babel\]",
            ),
        ):
            _ = ftllexengine.FluentBundle

    def test_zero_dependency_root_symbols_remain_accessible_without_babel(self) -> None:
        """Parser-only installs still expose zero-dependency root helpers."""
        with _fresh_ftl_import(block_babel=True) as ftllexengine:
            assert "FluentBundle" not in vars(ftllexengine)
            assert "FluentBundle" not in ftllexengine.__all__
            assert "FluentLocalization" not in ftllexengine.__all__

            assert "CacheConfig" in vars(ftllexengine)
            assert "FluentNumber" in vars(ftllexengine)
            assert "FluentValue" in vars(ftllexengine)
            assert "LoadSummary" in vars(ftllexengine)
            assert "PathResourceLoader" in vars(ftllexengine)
            assert "fluent_function" in vars(ftllexengine)
            assert "get_cldr_version" in vars(ftllexengine)

    def test_runtime_and_localization_facades_stay_partially_available_without_babel(self) -> None:
        """Parser-only installs keep zero-dependency runtime/localization names visible."""
        with _fresh_ftl_import(block_babel=True):
            from ftllexengine import localization, runtime

            assert "FluentBundle" not in runtime.__all__
            assert "AsyncFluentBundle" not in runtime.__all__
            assert "number_format" not in runtime.__all__
            assert "datetime_format" not in runtime.__all__
            assert "currency_format" not in runtime.__all__
            assert "select_plural_category" not in runtime.__all__
            assert "create_default_registry" not in runtime.__all__
            assert "get_shared_registry" not in runtime.__all__
            assert "CacheConfig" in runtime.__all__
            assert runtime.CacheConfig.__name__ == "CacheConfig"

            assert "FluentLocalization" not in localization.__all__
            assert "LocalizationBootConfig" not in localization.__all__
            assert "CacheAuditLogEntry" in localization.__all__
            assert localization.PathResourceLoader.__name__ == "PathResourceLoader"

    def test_parser_only_feature_probing_treats_optional_names_as_absent(self) -> None:
        """hasattr/getattr(default) treat Babel-backed names as absent in parser-only mode."""
        with _fresh_ftl_import(block_babel=True) as ftllexengine:
            from ftllexengine import localization, runtime

            assert hasattr(ftllexengine, "FluentBundle") is False
            assert getattr(ftllexengine, "FluentBundle", None) is None

            assert hasattr(runtime, "number_format") is False
            assert getattr(runtime, "number_format", None) is None

            assert hasattr(localization, "FluentLocalization") is False
            assert getattr(localization, "FluentLocalization", None) is None

    def test_parser_only_runtime_formatter_access_still_gives_install_hint(self) -> None:
        """Direct runtime formatter access raises AttributeError with install guidance."""
        with _fresh_ftl_import(block_babel=True):
            from ftllexengine import runtime

            with pytest.raises(
                AttributeError,
                match=r"number_format requires the full runtime install.*pip install ftllexengine\[babel\]",
            ):
                _ = runtime.number_format

    def test_internal_runtime_import_failure_is_not_masked_as_missing_babel(self) -> None:
        """A broken runtime import must surface its real error instead of a Babel hint."""
        with (
            pytest.raises(ModuleNotFoundError, match=r"ftllexengine\.runtime\.bundle"),
            _fresh_ftl_import(blocked_imports=frozenset({"ftllexengine.runtime.bundle"})),
        ):
            pass


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


class TestOptionalExportHelper:
    """Direct tests for the optional-export helper branches."""

    def test_helper_without_parser_only_hint_raises_plain_attribute_error(self) -> None:
        """Optional symbols raise AttributeError outside import machinery."""
        from ftllexengine._optional_exports import raise_missing_babel_symbol

        with pytest.raises(
            AttributeError,
            match=r"FluentBundle requires the full runtime install.*pip install ftllexengine\[babel\]",
        ):
            raise_missing_babel_symbol(
                module_name="ftllexengine.runtime",
                name="FluentBundle",
                optional_attrs=frozenset({"FluentBundle"}),
            )


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

        assert len(ftllexengine.__all__) == 60

    def test_babel_optional_exports_are_in_all(self) -> None:
        """Babel-optional symbols (FluentBundle, etc.) are listed in __all__."""
        import ftllexengine

        for name in (
            "AsyncFluentBundle",
            "FluentBundle",
            "FluentNumber",
            "FluentLocalization",
            "CacheConfig",
            "FluentValue",
            "fluent_function",
            "make_fluent_number",
        ):
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

    def test_new_validators_are_in_all(self) -> None:
        """New boundary validators added in this release are in ftllexengine.__all__."""
        import ftllexengine

        for name in (
            "require_date",
            "require_datetime",
            "require_fluent_number",
            "require_currency_code",
            "require_territory_code",
        ):
            assert name in ftllexengine.__all__, f"{name!r} missing from ftllexengine.__all__"

    def test_iso_types_are_in_all(self) -> None:
        """ISO code types and guards are in ftllexengine.__all__."""
        import ftllexengine

        for name in (
            "CurrencyCode",
            "TerritoryCode",
            "is_valid_currency_code",
            "is_valid_territory_code",
            "get_currency_decimal_digits",
        ):
            assert name in ftllexengine.__all__, f"{name!r} missing from ftllexengine.__all__"

    def test_warning_severity_is_in_all(self) -> None:
        """WarningSeverity is promoted to the root facade."""
        import ftllexengine

        assert "WarningSeverity" in ftllexengine.__all__
        assert hasattr(ftllexengine, "WarningSeverity")

    def test_detect_cycles_is_in_all(self) -> None:
        """detect_cycles is promoted to the root facade."""
        import ftllexengine

        assert "detect_cycles" in ftllexengine.__all__
        assert hasattr(ftllexengine, "detect_cycles")


class TestClearModuleCaches:
    """clear_module_caches() with and without component filters."""

    def test_clear_all_caches_no_args(self) -> None:
        """clear_module_caches() with no arguments clears all caches without error."""
        import ftllexengine

        # Should not raise; caches may or may not be populated
        ftllexengine.clear_module_caches()

    def test_clear_all_caches_none_explicit(self) -> None:
        """clear_module_caches(None) is identical to the no-argument form."""
        import ftllexengine

        ftllexengine.clear_module_caches(None)

    def test_clear_single_component_parsing_currency(self) -> None:
        """Passing frozenset({'parsing.currency'}) clears only that cache."""
        import ftllexengine

        ftllexengine.clear_module_caches(frozenset({"parsing.currency"}))

    def test_clear_single_component_parsing_dates(self) -> None:
        """Passing frozenset({'parsing.dates'}) clears only that cache."""
        import ftllexengine

        ftllexengine.clear_module_caches(frozenset({"parsing.dates"}))

    def test_clear_single_component_locale(self) -> None:
        """Passing frozenset({'locale'}) clears only the locale cache."""
        import ftllexengine

        ftllexengine.clear_module_caches(frozenset({"locale"}))

    def test_clear_single_component_runtime_locale_context(self) -> None:
        """Passing frozenset({'runtime.locale_context'}) clears only that cache."""
        import ftllexengine

        ftllexengine.clear_module_caches(frozenset({"runtime.locale_context"}))

    def test_clear_single_component_introspection_message(self) -> None:
        """Passing frozenset({'introspection.message'}) clears only that cache."""
        import ftllexengine

        ftllexengine.clear_module_caches(frozenset({"introspection.message"}))

    def test_clear_single_component_introspection_iso(self) -> None:
        """Passing frozenset({'introspection.iso'}) clears only that cache."""
        import ftllexengine

        ftllexengine.clear_module_caches(frozenset({"introspection.iso"}))

    def test_clear_multiple_components(self) -> None:
        """Passing a frozenset with multiple components clears exactly those caches."""
        import ftllexengine

        ftllexengine.clear_module_caches(
            frozenset({"introspection.iso", "introspection.message"})
        )

    def test_clear_empty_frozenset_clears_nothing(self) -> None:
        """An empty frozenset clears no caches (all _want() calls return False)."""
        import ftllexengine

        # Should not raise; just a no-op
        ftllexengine.clear_module_caches(frozenset())

    def test_clear_unknown_component_raises_value_error(self) -> None:
        """Unknown component names fail fast with ValueError."""
        import ftllexengine

        with pytest.raises(ValueError, match="Unknown cache component selector"):
            ftllexengine.clear_module_caches(frozenset({"nonexistent.component"}))

    def test_clear_module_caches_in_all(self) -> None:
        """clear_module_caches is exported in ftllexengine.__all__."""
        import ftllexengine

        assert "clear_module_caches" in ftllexengine.__all__

    def test_repeated_clear_is_idempotent(self) -> None:
        """Calling clear_module_caches() twice in succession does not raise."""
        import ftllexengine

        ftllexengine.clear_module_caches()
        ftllexengine.clear_module_caches()
