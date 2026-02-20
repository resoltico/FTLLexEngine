"""Tests for babel_compat Babel-unavailable code paths and dates era stripping.

Tests coverage for:
1. babel_compat.py: _check_babel_available() ImportError path, require_babel() raise
2. dates.py: _strip_era() word boundary logic, _is_word_boundary()

Note: BabelImportError raise paths in parsing modules cannot be easily tested
without subprocess isolation since Babel is installed in the test environment
and Python caches imports at multiple levels.

Python 3.13+.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import patch

import pytest

from ftllexengine.core.babel_compat import (
    BabelImportError,
    require_babel,
)
from ftllexengine.parsing.dates import _is_word_boundary, _strip_era

# ============================================================================
# babel_compat.py: _check_babel_available ImportError path
# ============================================================================


class TestCheckBabelAvailableImportError:
    """Test _check_babel_available() ImportError path."""

    def test_check_babel_available_handles_import_error(self) -> None:
        """_check_babel_available returns False when import fails.

        Resets the module-level sentinel, simulates Babel unavailability,
        then restores state for subsequent tests.
        """
        import ftllexengine.core.babel_compat as bc

        # Save and reset sentinel to force re-evaluation
        original_sentinel = bc._babel_available
        bc._babel_available = None

        # Save Babel modules from sys.modules
        saved_modules: dict[str, types.ModuleType] = {}
        for key in list(sys.modules):
            if key == "babel" or key.startswith("babel."):
                mod = sys.modules.pop(key)
                if mod is not None:
                    saved_modules[key] = mod

        try:
            original_import = __import__

            def mock_import_babel(
                name: str,
                globals_dict: dict[str, object] | None = None,
                locals_dict: dict[str, object] | None = None,
                fromlist: tuple[str, ...] = (),
                level: int = 0,
            ) -> object:
                if name == "babel":
                    msg = "Mocked: Babel not installed"
                    raise ImportError(msg)
                return original_import(
                    name, globals_dict, locals_dict, fromlist, level,
                )

            with patch("builtins.__import__", side_effect=mock_import_babel):
                result = bc._check_babel_available()
                assert result is False
                assert bc._babel_available is False
        finally:
            # Restore Babel modules and sentinel
            sys.modules.update(saved_modules)
            bc._babel_available = original_sentinel


# ============================================================================
# babel_compat.py: require_babel raise path
# ============================================================================


class TestRequireBabelRaise:
    """Test require_babel() raises when Babel is unavailable."""

    def test_require_babel_raises_when_check_returns_false(self) -> None:
        """require_babel raises BabelImportError when check returns False."""
        with patch(
            "ftllexengine.core.babel_compat._check_babel_available",
            return_value=False,
        ):
            with pytest.raises(BabelImportError) as exc_info:
                require_babel("test_feature")

            assert exc_info.value.feature == "test_feature"
            assert "pip install ftllexengine[babel]" in str(exc_info.value)

    def test_require_babel_raises_with_different_feature_names(self) -> None:
        """require_babel includes feature name in error message."""
        with patch(
            "ftllexengine.core.babel_compat._check_babel_available",
            return_value=False,
        ):
            features = [
                "parse_date",
                "format_currency",
                "LocaleContext.create",
            ]
            for feature in features:
                with pytest.raises(BabelImportError) as exc_info:
                    require_babel(feature)
                assert exc_info.value.feature == feature
                assert feature in str(exc_info.value)


# ============================================================================
# dates.py: _strip_era() branch coverage
# ============================================================================


class TestDatesEraStrippingBranches:
    """Test _strip_era() branch coverage for dates.py.

    The key branch is when an era string is found in the input but
    is not at a word boundary, so the loop continues to the next era.
    """

    def test_era_not_at_word_boundary_continues_loop(self) -> None:
        """Era found but not at word boundary continues to next era.

        "ADVERT" contains "AD" at index 0, but 'V' is alphanumeric so
        it is not at a word boundary. The loop continues without stripping.
        """
        result = _strip_era("ADVERT 2025")
        assert result == "ADVERT 2025"

    def test_era_in_middle_of_word_not_stripped(self) -> None:
        """Era embedded in word is not stripped."""
        result = _strip_era("OBCEAN 2025")
        assert "BCE" in result

    def test_era_at_word_boundary_is_stripped(self) -> None:
        """Era at word boundary IS stripped."""
        result = _strip_era("AD 2025")
        assert "AD" not in result
        assert "2025" in result

        result = _strip_era("100 BCE")
        assert "BCE" not in result
        assert "100" in result

    def test_no_era_in_input(self) -> None:
        """Input without era returns unchanged."""
        result = _strip_era("2025-01-28")
        assert result == "2025-01-28"

    def test_multiple_eras_partial_match(self) -> None:
        """Multiple era substrings but none at word boundaries."""
        result = _strip_era("CADASTRAL OBCEAN")
        assert result == "CADASTRAL OBCEAN"

    def test_era_case_insensitive_matching(self) -> None:
        """Era matching is case insensitive."""
        result = _strip_era("ad 2025")
        assert "ad" not in result.lower() or result == "2025"

        result = _strip_era("Ad 2025")
        assert "2025" in result

    def test_whitespace_normalization(self) -> None:
        """Multiple spaces are collapsed to single space."""
        result = _strip_era("AD   2025   January")
        assert "  " not in result


# ============================================================================
# dates.py: _is_word_boundary() edge cases
# ============================================================================


class TestDatesWordBoundaryFunction:
    """Test _is_word_boundary helper function edge cases."""

    def test_word_boundary_at_start(self) -> None:
        """Word boundary detection at string start."""
        assert _is_word_boundary("AD 2025", 0, is_start=True)

    def test_word_boundary_at_end(self) -> None:
        """Word boundary detection at string end."""
        text = "2025 AD"
        assert _is_word_boundary(text, len(text), is_start=False)

    def test_word_boundary_after_space(self) -> None:
        """Word boundary after space character."""
        assert _is_word_boundary("2025 AD", 5, is_start=True)

    def test_not_word_boundary_in_middle_of_word(self) -> None:
        """Not a word boundary in middle of word."""
        assert not _is_word_boundary("ADVERT", 2, is_start=True)
        assert not _is_word_boundary("ADVERT", 2, is_start=False)
