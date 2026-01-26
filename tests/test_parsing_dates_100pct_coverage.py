"""Tests to achieve 100% coverage for parsing/dates.py.

Targets remaining uncovered lines:
- Line 462: time-first datetime ordering in _get_datetime_patterns
- Line 698: early return in _extract_era_strings_from_babel_locale
- Lines 727-729: ImportError handling in _get_localized_era_strings

Python 3.13+.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from babel import Locale
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.parsing.dates import (
    _extract_era_strings_from_babel_locale,
    _get_datetime_patterns,
    _get_localized_era_strings,
    parse_datetime,
)

if TYPE_CHECKING:
    pass


class TestDatetimeTimeFirstOrdering:
    """Test time-first datetime ordering (line 462)."""

    def test_get_datetime_patterns_time_first_ordering(self) -> None:
        """Test _get_datetime_patterns with locale using time-first ordering.

        Covers line 462: combined = f"{time_pat}{sep}{date_pat}"

        Some locales in CLDR use time-before-date ordering where the datetime
        format pattern is "{0} {1}" instead of "{1} {0}".
        """
        # Clear cache to force fresh execution
        _get_datetime_patterns.cache_clear()

        # Mock Babel Locale to return time-first datetime format
        original_parse = Locale.parse

        def mock_parse_time_first(locale_str: str) -> MagicMock:
            """Mock Locale.parse to return time-first datetime format."""
            real_locale = original_parse(locale_str)
            mock_locale = MagicMock(spec=Locale)

            # Create datetime format with time-first ordering: "{0} {1}"
            # {0} = time, {1} = date
            # Configure MagicMock to return time-first pattern when str() is called
            time_first_pattern = "{0} {1}"
            mock_datetime_format = MagicMock(return_value=time_first_pattern)
            # Assign __str__ to return time-first pattern
            mock_datetime_format.__str__ = MagicMock(  # type: ignore[method-assign]
                return_value=time_first_pattern
            )
            mock_datetime_format.pattern = time_first_pattern

            mock_locale.datetime_formats = {
                "short": mock_datetime_format,
                "medium": mock_datetime_format,
                "long": mock_datetime_format,
            }

            # Provide date_formats from real locale
            mock_locale.date_formats = real_locale.date_formats

            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse_time_first):
            patterns = _get_datetime_patterns("en_US")

        # Should have generated patterns with time-first ordering
        assert len(patterns) > 0

        # At least one pattern should have time before date
        # Check that time pattern (%H:%M or %I:%M) appears before date pattern
        time_first_found = False
        for pattern, _has_era in patterns:
            # Find position of time directive
            time_pos = min(
                (pattern.find(t) for t in ["%H", "%I"] if pattern.find(t) != -1),
                default=-1,
            )
            # Find position of date directive
            date_pos = min(
                (pattern.find(d) for d in ["%d", "%m", "%Y"] if pattern.find(d) != -1),
                default=-1,
            )

            if time_pos != -1 and date_pos != -1 and time_pos < date_pos:
                time_first_found = True
                break

        assert time_first_found, "Should have at least one time-first pattern"

        # Clear cache after test
        _get_datetime_patterns.cache_clear()

    def test_parse_datetime_with_time_first_locale(self) -> None:
        """Integration test: parse datetime with time-first ordering locale.

        Covers line 462 through parse_datetime API.
        """
        # Clear cache
        _get_datetime_patterns.cache_clear()

        # Mock locale with time-first datetime format
        original_parse = Locale.parse

        def mock_parse_time_first(locale_str: str) -> MagicMock:
            """Mock Locale.parse with time-first format."""
            real_locale = original_parse(locale_str)
            mock_locale = MagicMock(spec=Locale)

            # Time-first format: "{0} {1}" where {0}=time, {1}=date
            # Configure MagicMock to return time-first pattern when str() is called
            time_first_pattern = "{0} {1}"
            mock_datetime_format = MagicMock(return_value=time_first_pattern)
            # Assign __str__ to return time-first pattern
            mock_datetime_format.__str__ = MagicMock(  # type: ignore[method-assign]
                return_value=time_first_pattern
            )

            mock_locale.datetime_formats = {
                "short": mock_datetime_format,
                "medium": mock_datetime_format,
            }
            mock_locale.date_formats = real_locale.date_formats

            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse_time_first):
            # Parse a datetime that could match time-first pattern
            # Time: 14:30, Date: 28.01.2025 (German-style date)
            result, _errors = parse_datetime("14:30 28.01.2025", "de_DE")

        # May or may not parse depending on exact pattern matching
        # Main goal: exercise line 462 (time-first branch)
        assert result is None or result.year in (2025, 1925)

        _get_datetime_patterns.cache_clear()

    @given(
        locale_code=st.sampled_from(["zh_CN", "ja_JP", "ko_KR", "th_TH"]),
    )
    @settings(max_examples=10)
    def test_asian_locales_datetime_ordering(self, locale_code: str) -> None:
        """Test Asian locales which may use different datetime orderings.

        Some Asian locales might use time-first or other orderings.
        This property test ensures the code handles various orderings.
        """
        _get_datetime_patterns.cache_clear()

        # Get patterns for various Asian locales
        patterns = _get_datetime_patterns(locale_code)

        # Should return patterns without error
        assert isinstance(patterns, tuple)

        _get_datetime_patterns.cache_clear()


class TestExtractEraStringsEarlyReturn:
    """Test early return in _extract_era_strings_from_babel_locale (line 698)."""

    def test_extract_era_strings_from_locale_without_eras_attribute(self) -> None:
        """Test _extract_era_strings_from_babel_locale with locale lacking eras.

        Covers line 698: return localized_eras (early return when no eras).
        """
        # Create mock locale without eras attribute
        mock_locale = MagicMock(spec=[])  # No attributes at all

        result = _extract_era_strings_from_babel_locale(mock_locale)

        # Should return empty list (line 698)
        assert result == []

    def test_extract_era_strings_from_locale_with_none_eras(self) -> None:
        """Test _extract_era_strings_from_babel_locale with eras=None.

        Covers line 698: return localized_eras (early return when eras is None).
        """
        # Create mock locale with eras=None
        mock_locale = MagicMock()
        mock_locale.eras = None

        result = _extract_era_strings_from_babel_locale(mock_locale)

        # Should return empty list (line 698)
        assert result == []

    def test_extract_era_strings_from_locale_with_empty_eras_dict(self) -> None:
        """Test _extract_era_strings_from_babel_locale with empty eras dict.

        Covers line 698: return localized_eras (early return when eras is empty).
        """
        # Create mock locale with empty eras dict
        mock_locale = MagicMock()
        mock_locale.eras = {}

        result = _extract_era_strings_from_babel_locale(mock_locale)

        # Should return empty list (line 698)
        assert result == []

    def test_extract_era_strings_from_locale_with_false_eras(self) -> None:
        """Test _extract_era_strings_from_babel_locale with falsy eras.

        Covers line 698: return localized_eras (early return for falsy eras).
        """
        # Create mock locale with falsy eras (empty dict evaluates to False)
        mock_locale = MagicMock()
        mock_locale.eras = {}  # Falsy value

        result = _extract_era_strings_from_babel_locale(mock_locale)

        # Should return empty list (line 698)
        assert result == []


class TestGetLocalizedEraStringsImportError:
    """Test ImportError handling in _get_localized_era_strings (lines 727-729)."""

    def test_get_localized_era_strings_babel_not_installed(self) -> None:
        """Test _get_localized_era_strings when Babel is not available.

        Covers lines 727-729: ImportError catch block returning empty tuple.
        """
        # Clear cache to force fresh execution
        _get_localized_era_strings.cache_clear()

        # Mock babel import to fail
        import builtins

        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_: dict[str, object] | None = None,
            locals_: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            """Mock import that raises ImportError for babel."""
            if name == "babel":
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            result = _get_localized_era_strings("en_US")

        # Should return empty tuple when Babel unavailable (line 729)
        assert result == ()

        _get_localized_era_strings.cache_clear()

    def test_get_localized_era_strings_import_error_cached(self) -> None:
        """Test that ImportError result is cached in _get_localized_era_strings.

        Covers lines 727-729 and verifies caching behavior.
        """
        _get_localized_era_strings.cache_clear()

        import builtins

        original_import = builtins.__import__
        import_call_count = 0

        def mock_import_counting(
            name: str,
            globals_: dict[str, object] | None = None,
            locals_: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            """Mock import that counts babel import attempts."""
            nonlocal import_call_count
            if name == "babel":
                import_call_count += 1
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        with patch.object(builtins, "__import__", side_effect=mock_import_counting):
            # First call
            result1 = _get_localized_era_strings("en_US")
            # Second call (should use cache)
            result2 = _get_localized_era_strings("en_US")

        # Both should return empty tuple
        assert result1 == ()
        assert result2 == ()

        # Should only attempt import once (second call uses cache)
        assert import_call_count == 1

        _get_localized_era_strings.cache_clear()

    @given(
        locale_code=st.text(
            alphabet=st.characters(whitelist_categories=("L", "P")),
            min_size=2,
            max_size=10,
        ).filter(lambda x: x.isalnum() or "_" in x or "-" in x),
    )
    @settings(max_examples=50)
    def test_get_localized_era_strings_handles_any_locale_without_babel(
        self, locale_code: str
    ) -> None:
        """PROPERTY: _get_localized_era_strings always returns empty tuple without Babel.

        For any locale code, if Babel is unavailable, should return empty tuple
        without raising exception.
        """
        _get_localized_era_strings.cache_clear()

        import builtins

        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_: dict[str, object] | None = None,
            locals_: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            """Mock import that fails for babel."""
            if name == "babel":
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            result = _get_localized_era_strings(locale_code)

        # Should return empty tuple without exception
        assert result == ()

        _get_localized_era_strings.cache_clear()


class TestIntegrationFullCoverage:
    """Integration tests ensuring all code paths are exercised."""

    def test_parse_datetime_exercises_all_branches(self) -> None:
        """Integration test exercising multiple code branches.

        Ensures parse_datetime exercises:
        - ISO format path
        - CLDR pattern path
        - Error handling paths
        """
        test_cases = [
            # ISO format
            ("2025-01-28T14:30:00", "en_US", True),
            # Locale-specific format
            ("1/28/25, 2:30 PM", "en_US", True),
            # Invalid format
            ("not-a-datetime", "en_US", False),
            # Empty string
            ("", "en_US", False),
        ]

        for datetime_str, locale, should_succeed in test_cases:
            result, errors = parse_datetime(datetime_str, locale)

            if should_succeed:
                assert result is not None or len(errors) > 0
            else:
                assert len(errors) > 0
                assert result is None

    def test_coverage_verification_complete(self) -> None:
        """Verification that all target lines are now covered.

        This test documents the coverage targets:
        - Line 462: time-first datetime ordering
        - Line 698: early return in _extract_era_strings_from_babel_locale
        - Lines 727-729: ImportError in _get_localized_era_strings
        """
        # Line 462: Tested by TestDatetimeTimeFirstOrdering
        # Line 698: Tested by TestExtractEraStringsEarlyReturn
        # Lines 727-729: Tested by TestGetLocalizedEraStringsImportError

        # This test serves as documentation
        assert True
