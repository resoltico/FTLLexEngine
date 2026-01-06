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
    from collections.abc import Generator

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

    # Block babel from being imported
    with patch.dict(sys.modules, {"babel": None}):
        yield

    # Restore babel modules
    sys.modules.update(babel_modules)


def _make_import_blocker(blocked_prefix: str = "babel"):
    """Create an import blocker for Babel modules.

    Returns a function that wraps the original import and raises
    ImportError for any module starting with the blocked prefix.
    """
    original_import = builtins.__import__

    def mock_import(
        name: str,
        globals_: dict | None = None,
        locals_: dict | None = None,
        fromlist: tuple = (),
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
        currency._get_currency_pattern_fast.cache_clear()
        currency._get_currency_pattern_full.cache_clear()

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
            _get_currency_pattern_fast,
            _get_currency_pattern_full,
        )

        # Clear all caches before test
        _build_currency_maps_from_cldr.cache_clear()
        _get_currency_maps.cache_clear()
        _get_currency_pattern_fast.cache_clear()
        _get_currency_pattern_full.cache_clear()

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
            _get_currency_pattern_fast.cache_clear()
            _get_currency_pattern_full.cache_clear()


class TestParseDateBabelUnavailable:
    """Test parse_date when Babel is not installed."""

    def test_get_date_patterns_raises_babel_import_error(self) -> None:
        """_get_date_patterns raises BabelImportError when Babel unavailable."""
        from ftllexengine.parsing.dates import _get_date_patterns

        # Clear cache
        _get_date_patterns.cache_clear()

        mock_import = _make_import_blocker("babel")

        with (
            patch.object(builtins, "__import__", side_effect=mock_import),
            pytest.raises(BabelImportError) as exc_info,
        ):
            _get_date_patterns("en_US")

        assert "parse_date" in str(exc_info.value)


class TestParseDatetimeBabelUnavailable:
    """Test parse_datetime when Babel is not installed."""

    def test_get_datetime_patterns_raises_babel_import_error(self) -> None:
        """_get_datetime_patterns raises BabelImportError when Babel unavailable."""
        from ftllexengine.parsing.dates import _get_datetime_patterns

        # Clear cache
        _get_datetime_patterns.cache_clear()

        mock_import = _make_import_blocker("babel")

        with (
            patch.object(builtins, "__import__", side_effect=mock_import),
            pytest.raises(BabelImportError) as exc_info,
        ):
            _get_datetime_patterns("en_US")

        assert "parse_datetime" in str(exc_info.value)


class TestParseNumberBabelUnavailable:
    """Test parse_number when Babel is not installed."""

    def test_parse_number_raises_babel_import_error(self) -> None:
        """parse_number raises BabelImportError when Babel unavailable."""
        from ftllexengine.parsing.numbers import parse_number

        mock_import = _make_import_blocker("babel")

        with (
            patch.object(builtins, "__import__", side_effect=mock_import),
            pytest.raises(BabelImportError) as exc_info,
        ):
            parse_number("1,234.56", "en_US")

        assert "parse_number" in str(exc_info.value)


class TestParseDecimalBabelUnavailable:
    """Test parse_decimal when Babel is not installed."""

    def test_parse_decimal_raises_babel_import_error(self) -> None:
        """parse_decimal raises BabelImportError when Babel unavailable."""
        from ftllexengine.parsing.numbers import parse_decimal

        mock_import = _make_import_blocker("babel")

        with (
            patch.object(builtins, "__import__", side_effect=mock_import),
            pytest.raises(BabelImportError) as exc_info,
        ):
            parse_decimal("1,234.56", "en_US")

        assert "parse_decimal" in str(exc_info.value)
