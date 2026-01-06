"""Coverage tests for babel_compat module and Babel-dependent code paths.

This file provides coverage for:
1. babel_compat.py: require_babel() raise path, helper functions
2. dates.py: _strip_era() word boundary logic, _is_word_boundary()
3. Babel integration: Locale class, UnknownLocaleError, module accessors

Note: BabelImportError raise paths in parsing modules cannot be easily tested
without subprocess isolation since Babel is installed in the test environment
and Python caches imports at multiple levels.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from babel import Locale
from babel.core import UnknownLocaleError

from ftllexengine.core.babel_compat import (
    BabelImportError,
    _check_babel_available,
    get_babel_dates,
    get_babel_numbers,
    get_locale_class,
    get_unknown_locale_error,
    require_babel,
)
from ftllexengine.parsing.dates import _is_word_boundary, _strip_era

# ============================================================================
# babel_compat.py coverage: lines 61-62 (_check_babel_available ImportError)
# ============================================================================


class TestCheckBabelAvailableImportError:
    """Test _check_babel_available() ImportError path (lines 61-62)."""

    def test_check_babel_available_handles_import_error(self) -> None:
        """_check_babel_available returns False when import fails (lines 61-62)."""
        # Clear the lru_cache to force function re-execution
        _check_babel_available.cache_clear()

        # Temporarily hide babel from sys.modules to trigger ImportError
        babel_module = sys.modules.pop("babel", None)
        babel_core = sys.modules.pop("babel.core", None)
        babel_dates = sys.modules.pop("babel.dates", None)
        babel_numbers = sys.modules.pop("babel.numbers", None)

        try:
            # Patch sys.modules to prevent babel import
            with patch.dict(sys.modules, {"babel": None}):
                # Mock the import to raise ImportError
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
                    return original_import(name, globals_dict, locals_dict, fromlist, level)

                with patch("builtins.__import__", side_effect=mock_import_babel):
                    result = _check_babel_available()
                    assert result is False
        finally:
            # Restore babel modules
            if babel_module is not None:
                sys.modules["babel"] = babel_module
            if babel_core is not None:
                sys.modules["babel.core"] = babel_core
            if babel_dates is not None:
                sys.modules["babel.dates"] = babel_dates
            if babel_numbers is not None:
                sys.modules["babel.numbers"] = babel_numbers

            # Restore cache for subsequent tests
            _check_babel_available.cache_clear()
            # Verify Babel is actually available after mock
            assert _check_babel_available() is True


# ============================================================================
# babel_compat.py coverage: line 124 (require_babel raise)
# ============================================================================


class TestBabelCompatRequireBabelRaise:
    """Test require_babel() raises when Babel is unavailable (line 124)."""

    def test_require_babel_raises_when_check_returns_false(self) -> None:
        """require_babel raises BabelImportError when _check_babel_available returns False."""
        # Patch the cached check to return False
        with patch(
            "ftllexengine.core.babel_compat._check_babel_available", return_value=False
        ):
            with pytest.raises(BabelImportError) as exc_info:
                require_babel("test_feature")

            assert exc_info.value.feature == "test_feature"
            assert "pip install ftllexengine[babel]" in str(exc_info.value)

    def test_require_babel_raises_with_different_feature_names(self) -> None:
        """require_babel includes feature name in error message."""
        with patch(
            "ftllexengine.core.babel_compat._check_babel_available", return_value=False
        ):
            features = ["parse_date", "format_currency", "LocaleContext.create"]
            for feature in features:
                with pytest.raises(BabelImportError) as exc_info:
                    require_babel(feature)
                assert exc_info.value.feature == feature
                assert feature in str(exc_info.value)


# ============================================================================
# dates.py coverage: line 689->681 (era stripping loop continuation)
# ============================================================================


class TestDatesEraStrippingBranches:
    """Test _strip_era() branch coverage for dates.py line 689->681.

    The branch 689->681 is hit when:
    1. An era string is found in the input (line 686 condition True)
    2. BUT it's not at a word boundary (line 689 condition False)
    3. So the loop continues to check the next era (goto line 681)
    """

    def test_era_not_at_word_boundary_continues_loop(self) -> None:
        """Era found but not at word boundary continues to next era (689->681).

        "ADVERT" contains "AD" at index 0, but 'V' is alphanumeric so it's not
        at a word boundary. The loop should continue without stripping.
        """
        # "AD" is found but followed by alphanumeric char
        result = _strip_era("ADVERT 2025")
        assert result == "ADVERT 2025"

    def test_era_in_middle_of_word_not_stripped(self) -> None:
        """Era embedded in word is not stripped."""
        # "BCE" is found but preceded by alphanumeric char
        result = _strip_era("OBCEAN 2025")
        assert "BCE" in result  # BCE should NOT be stripped

    def test_era_at_word_boundary_is_stripped(self) -> None:
        """Era at word boundary IS stripped."""
        # "AD" at word boundary should be stripped
        result = _strip_era("AD 2025")
        assert "AD" not in result
        assert "2025" in result

        # "BCE" at word boundary should be stripped
        result = _strip_era("100 BCE")
        assert "BCE" not in result
        assert "100" in result

    def test_no_era_in_input(self) -> None:
        """Input without era returns unchanged (modulo whitespace normalization)."""
        result = _strip_era("2025-01-28")
        assert result == "2025-01-28"

    def test_multiple_eras_partial_match(self) -> None:
        """Multiple era substrings but none at word boundaries."""
        # Contains "AD" and "BCE" but neither at word boundary
        result = _strip_era("CADASTRAL OBCEAN")
        assert result == "CADASTRAL OBCEAN"

    def test_era_case_insensitive_matching(self) -> None:
        """Era matching is case insensitive."""
        # Lowercase "ad" at word boundary
        result = _strip_era("ad 2025")
        assert "ad" not in result.lower() or result == "2025"

        # Mixed case
        result = _strip_era("Ad 2025")
        assert "2025" in result

    def test_whitespace_normalization(self) -> None:
        """Multiple spaces are collapsed to single space."""
        result = _strip_era("AD   2025   January")
        # AD stripped, multiple spaces collapsed
        assert "  " not in result


# ============================================================================
# Additional edge case tests for better coverage
# ============================================================================


class TestDatesWordBoundaryFunction:
    """Test _is_word_boundary helper function edge cases."""

    def test_word_boundary_at_start(self) -> None:
        """Word boundary detection at string start."""
        # Start of string is always a word boundary
        assert _is_word_boundary("AD 2025", 0, is_start=True)

    def test_word_boundary_at_end(self) -> None:
        """Word boundary detection at string end."""
        text = "2025 AD"
        # End position (past last char) is a word boundary
        assert _is_word_boundary(text, len(text), is_start=False)

    def test_word_boundary_after_space(self) -> None:
        """Word boundary after space character."""
        # Position after space (index 5) is a word boundary for start
        assert _is_word_boundary("2025 AD", 5, is_start=True)

    def test_not_word_boundary_in_middle_of_word(self) -> None:
        """Not a word boundary in middle of word."""
        # Position 2 in "ADVERT" is not a word boundary
        assert not _is_word_boundary("ADVERT", 2, is_start=True)
        assert not _is_word_boundary("ADVERT", 2, is_start=False)


class TestBabelCompatHelpers:
    """Test babel_compat.py helper functions that ARE testable."""

    def test_get_locale_class_returns_babel_locale(self) -> None:
        """get_locale_class returns the Babel Locale class."""
        result = get_locale_class()
        assert result is Locale

    def test_get_unknown_locale_error_returns_exception_class(self) -> None:
        """get_unknown_locale_error returns the UnknownLocaleError class."""
        result = get_unknown_locale_error()
        assert result is UnknownLocaleError

    def test_get_babel_numbers_returns_module(self) -> None:
        """get_babel_numbers returns the babel.numbers module."""
        result = get_babel_numbers()
        assert hasattr(result, "format_decimal")
        assert hasattr(result, "parse_decimal")

    def test_get_babel_dates_returns_module(self) -> None:
        """get_babel_dates returns the babel.dates module."""
        result = get_babel_dates()
        assert hasattr(result, "format_date")
        assert hasattr(result, "format_datetime")
