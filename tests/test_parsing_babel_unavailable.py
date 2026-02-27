"""Tests for parsing modules when Babel is not installed.

These tests mock the Babel import to simulate parser-only installations
where Babel is not available. All parsing functions that depend on Babel
should raise BabelImportError with a clear message.

Python 3.13+.
"""

from __future__ import annotations

import builtins
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

import ftllexengine.core.babel_compat as _bc
from ftllexengine.core.babel_compat import BabelImportError


@pytest.fixture
def mock_babel_unavailable() -> Generator[None]:
    """Mock Babel as unavailable by removing it from sys.modules temporarily."""
    # Store original modules
    babel_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "babel" or name.startswith("babel.")
    }

    # Remove babel modules
    for name in babel_modules:
        del sys.modules[name]

    # Clear require_babel's availability cache
    _bc._babel_available = None

    # Block babel from being imported
    with patch.dict(sys.modules, {"babel": None}):
        yield

    # Restore babel modules
    sys.modules.update(babel_modules)
    _bc._babel_available = None


def _make_import_blocker(blocked_prefix: str = "babel") -> Callable[..., object]:
    """Create an import blocker for Babel modules.

    Returns a function that wraps the original import and raises
    ImportError for any module starting with the blocked prefix.
    """
    original_import = builtins.__import__

    def mock_import(
        name: str,
        globals_: dict[str, object] | None = None,
        locals_: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == blocked_prefix or name.startswith(f"{blocked_prefix}."):
            msg = f"No module named '{name}'"
            raise ImportError(msg)
        return original_import(name, globals_, locals_, fromlist, level)

    return mock_import


class TestParseCurrencyBabelUnavailable:
    """Test parse_currency when Babel is not installed."""

    def test_parse_currency_raises_babel_import_error(
        self, mock_babel_unavailable: None  # noqa: ARG002
    ) -> None:
        """parse_currency raises BabelImportError when Babel is unavailable."""
        # Import here to get the module with mocked imports
        # Clear any cached functions first
        from ftllexengine.parsing import currency

        currency._build_currency_maps_from_cldr.cache_clear()
        currency._get_currency_maps.cache_clear()
        currency._get_currency_pattern.cache_clear()

        # Force re-import by removing from cache
        if "ftllexengine.parsing.currency" in sys.modules:
            del sys.modules["ftllexengine.parsing.currency"]

        # Now patch the import
        with patch.dict(sys.modules, {"babel": None}):
            # Re-import to get fresh module
            from ftllexengine.parsing.currency import parse_currency

            with pytest.raises(BabelImportError) as exc_info:
                parse_currency("EUR 100", "en_US")

            assert "parse_currency" in str(exc_info.value)


class TestBuildCurrencyMapsBabelUnavailable:
    """Test _build_currency_maps_from_cldr when Babel is not installed."""

    def test_build_maps_returns_empty_when_babel_unavailable(self) -> None:
        """_build_currency_maps_from_cldr returns empty maps without Babel."""
        from ftllexengine.parsing.currency import (
            _build_currency_maps_from_cldr,
            _get_currency_maps,
            _get_currency_pattern,
        )

        # Clear all caches before test
        _build_currency_maps_from_cldr.cache_clear()
        _get_currency_maps.cache_clear()
        _get_currency_pattern.cache_clear()

        # Reset sentinel so is_babel_available() re-evaluates under the mock
        _bc._babel_available = None
        mock_import = _make_import_blocker("babel")

        try:
            with patch.object(builtins, "__import__", side_effect=mock_import):
                # This should return empty maps (lines 277-279)
                result = _build_currency_maps_from_cldr()

            assert result == ({}, set(), {}, frozenset())
        finally:
            # Clear cache after test to prevent pollution
            _build_currency_maps_from_cldr.cache_clear()
            _get_currency_maps.cache_clear()
            _get_currency_pattern.cache_clear()
            # Reset sentinel so subsequent tests reinitialize with Babel available
            _bc._babel_available = None


class TestParseDateBabelUnavailable:
    """Test parse_date when Babel is not installed."""

    def test_get_date_patterns_raises_babel_import_error(self) -> None:
        """_get_date_patterns raises BabelImportError when Babel unavailable."""
        from ftllexengine.parsing.dates import _get_date_patterns

        _get_date_patterns.cache_clear()
        _bc._babel_available = None

        mock_import = _make_import_blocker("babel")

        try:
            with (
                patch.object(builtins, "__import__", side_effect=mock_import),
                pytest.raises(BabelImportError) as exc_info,
            ):
                _get_date_patterns("en_US")

            assert "parse_date" in str(exc_info.value)
        finally:
            _bc._babel_available = None


class TestParseDatetimeBabelUnavailable:
    """Test parse_datetime when Babel is not installed."""

    def test_get_datetime_patterns_raises_babel_import_error(self) -> None:
        """_get_datetime_patterns raises BabelImportError when Babel unavailable."""
        from ftllexengine.parsing.dates import _get_datetime_patterns

        _get_datetime_patterns.cache_clear()
        _bc._babel_available = None

        mock_import = _make_import_blocker("babel")

        try:
            with (
                patch.object(builtins, "__import__", side_effect=mock_import),
                pytest.raises(BabelImportError) as exc_info,
            ):
                _get_datetime_patterns("en_US")

            assert "parse_datetime" in str(exc_info.value)
        finally:
            _bc._babel_available = None


class TestParseDecimalBabelUnavailable:
    """Test parse_decimal when Babel is not installed."""

    def test_parse_decimal_raises_babel_import_error(self) -> None:
        """parse_decimal raises BabelImportError when Babel unavailable."""
        from ftllexengine.parsing.numbers import parse_decimal

        _bc._babel_available = None
        mock_import = _make_import_blocker("babel")

        try:
            with (
                patch.object(builtins, "__import__", side_effect=mock_import),
                pytest.raises(BabelImportError) as exc_info,
            ):
                parse_decimal("1,234.56", "en_US")

            assert "parse_decimal" in str(exc_info.value)
        finally:
            _bc._babel_available = None


class TestResolverPluralBabelUnavailable:
    """Test FluentResolver plural matching when Babel is not installed."""

    def test_plural_matching_collects_error_when_babel_unavailable(self) -> None:
        """Plural matching should collect error when Babel is unavailable.

        Tests that FluentResolver collects a FluentResolutionError with
        PLURAL_SUPPORT_UNAVAILABLE diagnostic code when attempting to resolve
        select expressions with numeric selectors while Babel is not installed.
        """
        from ftllexengine import FluentBundle
        from ftllexengine.diagnostics import DiagnosticCode

        # Clear any caches
        from ftllexengine.runtime import plural_rules

        if hasattr(plural_rules.select_plural_category, "cache_clear"):
            plural_rules.select_plural_category.cache_clear()

        # Create bundle with FTL containing plural select expression
        ftl = """
items = { $count ->
    [one] one item
   *[other] { $count } items
}
"""
        mock_import = _make_import_blocker("babel")

        # Reset sentinel so _check_babel_available() re-evaluates under the mock
        _bc._babel_available = None
        try:
            with patch.object(builtins, "__import__", side_effect=mock_import):
                bundle = FluentBundle("en_US", strict=False)
                bundle.add_resource(ftl)

                # Format with numeric argument (should trigger plural matching)
                result, errors = bundle.format_pattern("items", {"count": 1})

                # Should fall back to default variant due to Babel unavailability
                # Result may contain bidi marks, so just check for key components
                assert "1" in result  # Default variant used
                assert "items" in result

                # Should have collected error about Babel unavailability
                assert len(errors) == 1
                error = errors[0]
                assert hasattr(error, "diagnostic")
                assert error.diagnostic is not None
                assert error.diagnostic.code == DiagnosticCode.PLURAL_SUPPORT_UNAVAILABLE
                assert "Babel not installed" in error.diagnostic.message
                assert "ftllexengine[babel]" in error.diagnostic.message
        finally:
            # Reset sentinel so subsequent tests reinitialize with Babel available
            _bc._babel_available = None
