"""Tests for Babel import error handling in currency parsing.

Validates that currency parsing functions handle missing Babel gracefully:
- _build_currency_maps_from_cldr() returns empty maps when Babel not installed
- parse_currency() raises BabelImportError with clear message when Babel missing

These tests use mocking to simulate Babel being unavailable, allowing us to test
the fallback behavior without actually uninstalling Babel.
"""

from __future__ import annotations

import builtins
from unittest.mock import patch

import pytest

# ============================================================================
# LINES 277-279: ImportError in _build_currency_maps_from_cldr()
# ============================================================================


class TestBuildCurrencyMapsImportError:
    """Test _build_currency_maps_from_cldr() ImportError handling (lines 277-279)."""

    def test_build_maps_returns_empty_when_babel_missing(self) -> None:
        """Test _build_currency_maps_from_cldr() returns empty maps when Babel missing.

        Lines 277-279: When ImportError occurs during Babel import, the function
        should return empty maps: ({}, set(), {}, frozenset()).
        """
        from ftllexengine.parsing.currency import _build_currency_maps_from_cldr

        # Clear cache before test
        _build_currency_maps_from_cldr.cache_clear()

        # Mock builtins.__import__ to raise ImportError for babel imports only
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            # Only mock "babel" package, not packages containing "babel" as substring
            if name == "babel" or name.startswith("babel."):
                msg = f"No module named '{name}'"
                raise ImportError(msg)
            return original_import(name, *args, **kwargs)  # type: ignore[arg-type]

        try:
            with patch("builtins.__import__", side_effect=mock_import):
                # Call function - should handle ImportError and return empty maps
                symbol_map, ambiguous, locale_map, valid_codes = _build_currency_maps_from_cldr()

                # Should return empty maps
                assert symbol_map == {}
                assert ambiguous == set()
                assert locale_map == {}
                assert valid_codes == frozenset()
        finally:
            # Clean up cache
            _build_currency_maps_from_cldr.cache_clear()


# ============================================================================
# LINES 690-694: ImportError in parse_currency() (BabelImportError)
# ============================================================================


class TestParseCurrencyImportError:
    """Test parse_currency() ImportError handling (lines 690-694)."""

    def test_parse_currency_raises_babel_import_error_when_babel_missing(self) -> None:
        """Test parse_currency() raises BabelImportError when Babel not installed.

        Lines 690-694: When ImportError occurs during Babel import in parse_currency(),
        the function should raise BabelImportError with a clear message.
        """
        from ftllexengine.core.babel_compat import BabelImportError
        from ftllexengine.parsing.currency import parse_currency

        # Mock builtins.__import__ to raise ImportError for babel imports only
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            # Only mock "babel" package, not packages containing "babel" as substring
            if name == "babel" or name.startswith("babel."):
                msg = f"No module named '{name}'"
                raise ImportError(msg)
            return original_import(name, *args, **kwargs)  # type: ignore[arg-type]

        with patch("builtins.__import__", side_effect=mock_import):
            # Should raise BabelImportError
            with pytest.raises(BabelImportError) as exc_info:
                parse_currency("€100", "en_US")

            # Error message should mention parse_currency
            error_msg = str(exc_info.value)
            assert "parse_currency" in error_msg or "currency" in error_msg.lower()

    def test_parse_currency_babel_import_error_has_feature_name(self) -> None:
        """Test BabelImportError includes feature name in message."""
        from ftllexengine.core.babel_compat import BabelImportError
        from ftllexengine.parsing.currency import parse_currency

        # Mock builtins.__import__ to raise ImportError for babel imports only
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            # Only mock "babel" package, not packages containing "babel" as substring
            if name == "babel" or name.startswith("babel."):
                msg = f"No module named '{name}'"
                raise ImportError(msg)
            return original_import(name, *args, **kwargs)  # type: ignore[arg-type]

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(BabelImportError) as exc_info:
                parse_currency("USD 100", "en_US")

            error_msg = str(exc_info.value)
            # Should mention the feature name
            assert "parse_currency" in error_msg or "currency" in error_msg.lower()


# ============================================================================
# INTEGRATION: Fast tier still works without Babel
# ============================================================================


class TestFastTierWithoutBabel:
    """Test that fast tier currency operations work without Babel."""

    def test_fast_tier_symbols_available_without_babel(self) -> None:
        """Test that fast tier unambiguous symbols work without Babel.

        Even when Babel is not available, the fast tier (hardcoded symbols like €)
        should still be available for pattern matching.
        """
        from ftllexengine.parsing.currency import (
            _FAST_TIER_UNAMBIGUOUS_SYMBOLS,
            _get_currency_maps_fast,
        )

        # Fast tier should always be available
        symbols, _ambiguous, _locales, _codes = _get_currency_maps_fast()

        # Should return fast tier data (not empty)
        assert len(symbols) > 0
        assert "€" in symbols  # Euro should be in fast tier
        assert symbols["€"] == "EUR"

        # Should match the hardcoded constant
        assert symbols == _FAST_TIER_UNAMBIGUOUS_SYMBOLS

    def test_fast_tier_pattern_compiles_without_babel(self) -> None:
        """Test that fast tier regex pattern compiles without Babel."""
        from ftllexengine.parsing.currency import _get_currency_pattern_fast

        # Clear cache
        _get_currency_pattern_fast.cache_clear()

        try:
            # Should compile successfully
            pattern = _get_currency_pattern_fast()
            assert pattern is not None

            # Should match common fast tier symbols
            assert pattern.search("€100") is not None
            assert pattern.search("USD 100") is not None
        finally:
            # Clean up
            _get_currency_pattern_fast.cache_clear()
