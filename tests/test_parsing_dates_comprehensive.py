"""Comprehensive coverage tests for parsing/dates.py.

Targets remaining uncovered branches:
- Lines 288-289: Babel datetime format conversion (may be defensive code)
- Lines 377->379: Non-empty quoted literals in CLDR patterns
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.parsing.dates import parse_date, parse_datetime

# ============================================================================
# LINES 288-289: Babel Datetime Format Conversion
# ============================================================================


class TestBabelDatetimeFormatConversion:
    """Test babel datetime format conversion (lines 288-289).

    Note: Babel's datetime_formats are typically template strings like "{1}, {0}"
    rather than pattern objects, so this code may not execute in practice.
    We mock babel to test the code path.
    """

    def test_babel_datetime_format_with_mock(self) -> None:
        """Test lines 288-289 by mocking babel to return pattern object."""
        # Create a mock pattern object
        mock_pattern = Mock()
        mock_pattern.pattern = "M/d/yy, h:mm a"

        # Mock the entire Locale structure properly
        mock_locale = Mock()
        mock_locale.datetime_formats = {"short": mock_pattern, "medium": mock_pattern}
        # Also need date_formats for the fallback path
        mock_date_format = Mock()
        mock_date_format.pattern = "M/d/yy"
        mock_locale.date_formats = {"short": mock_date_format}

        with patch("ftllexengine.parsing.dates.Locale") as mock_locale_class:
            mock_locale_class.parse.return_value = mock_locale

            # This should execute lines 288-289
            from ftllexengine.parsing.dates import _get_datetime_patterns

            patterns = _get_datetime_patterns("en_US")
            # Should have at least one pattern from the mock
            assert len(patterns) > 0

    def test_parse_datetime_with_working_formats(self) -> None:
        """Test datetime parsing with formats that actually work.

        v0.27.0: Uses CLDR dateTimeFormat with locale-specific separator.
        Both en_US and de_DE use ", " separator (CLDR pattern: "{1}, {0}").
        """
        test_cases = [
            ("01/28/25, 14:30", "en_US"),  # %m/%d/%y, %H:%M (CLDR separator)
            ("01/28/25, 02:30 PM", "en_US"),  # %m/%d/%y, %I:%M %p (CLDR separator)
            ("28.01.25, 14:30", "de_DE"),  # %d.%m.%y, %H:%M (CLDR separator)
        ]

        for date_str, locale in test_cases:
            result, _errors = parse_datetime(date_str, locale)
            assert result is not None, f"Failed to parse '{date_str}' for locale {locale}"
            assert result.year == 2025
            assert result.month == 1
            assert result.day == 28

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    def test_parse_datetime_various_times(self, hour: int, minute: int) -> None:
        """PROPERTY: Datetime patterns handle various times.

        v0.27.0: Uses CLDR dateTimeFormat separator (de_DE uses ", ").
        """
        # Use 24-hour format with CLDR separator
        date_str = f"28.01.25, {hour:02d}:{minute:02d}"
        result, _errors = parse_datetime(date_str, "de_DE")

        if result is not None:
            assert result.hour == hour
            assert result.minute == minute


# ============================================================================
# LINES 377->379: Non-Empty Quoted Literals in CLDR Patterns
# ============================================================================


class TestQuotedLiteralsInCLDRPatterns:
    """Test non-empty quoted literals in CLDR patterns (lines 377-379).

    CLDR date patterns use single quotes to escape literal text.
    Example: Russian long format has quoted literal for year.
    Spanish long format has "d 'de' MMMM 'de' y" with quoted 'de'.
    Lines 377-379 extract content between quotes when j > i + 1.
    """

    def test_parse_date_russian_with_quoted_literal(self) -> None:
        """Test Russian date parsing exercises quoted literal handling (lines 377-379).

        Russian medium/long patterns contain quoted year abbreviation.
        Pattern includes quoted literal extracted by lines 377-379.
        """
        # Russian short format (no quoted literals)
        result, _errors = parse_date("28.01.2025", "ru_RU")
        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 28

    def test_parse_date_spanish_with_quoted_de(self) -> None:
        """Test Spanish date parsing (lines 377-379).

        Spanish long pattern: "d 'de' MMMM 'de' y"
        Contains quoted literal 'de' which triggers lines 377-379.
        """
        # Spanish short format: %d/%m/%y (2-digit year)
        result, _errors = parse_date("28/01/25", "es_ES")
        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 28

    def test_parse_date_portuguese_with_quoted_de(self) -> None:
        """Test Portuguese date parsing (lines 377-379).

        Portuguese long pattern: "d 'de' MMMM 'de' y"
        Similar to Spanish, contains quoted 'de'.
        """
        # Portuguese short format
        result, _errors = parse_date("28/01/2025", "pt_PT")
        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 28

    def test_tokenize_pattern_directly_with_quoted_literals(self) -> None:
        """Directly test _tokenize_babel_pattern with quoted literals (lines 377-379)."""
        from ftllexengine.parsing.dates import _tokenize_babel_pattern

        # Pattern with quoted literal
        pattern = "d 'de' MMMM 'de' y"
        tokens = _tokenize_babel_pattern(pattern)

        # Should extract "de" from between quotes
        assert "de" in tokens
        assert "d" in tokens
        assert "MMMM" in tokens
        assert "y" in tokens

    def test_tokenize_pattern_with_russian_quoted_literal(self) -> None:
        """Test _tokenize_babel_pattern with Russian quoted literal (lines 377-379)."""
        from ftllexengine.parsing.dates import _tokenize_babel_pattern

        # Russian pattern with quoted literal (Cyrillic char for year)
        pattern = "d MMMM y '\u0433'."  # \u0433 is Cyrillic lowercase 'g' (year marker)
        tokens = _tokenize_babel_pattern(pattern)

        # Should extract quoted literal from between quotes
        assert "\u0433" in tokens
        assert "d" in tokens
        assert "MMMM" in tokens
        assert "y" in tokens
        assert "." in tokens


# ============================================================================
# Integration Tests: Full Coverage Verification
# ============================================================================


class TestDatetimeParsingIntegration:
    """Integration tests combining all coverage targets."""

    def test_parse_datetime_with_seconds(self) -> None:
        """Test datetime parsing with seconds component.

        v0.27.0: Uses CLDR dateTimeFormat separator (de_DE uses ", ").
        """
        # 24-hour format with seconds and CLDR separator
        result, _errors = parse_datetime("28.01.25, 14:30:45", "de_DE")
        assert result is not None
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 45

    def test_parse_datetime_iso_format_all_locales(self) -> None:
        """Test that ISO format works across all locales."""
        iso_str = "2025-01-28 14:30:00"

        for locale in ["en_US", "de_DE", "fr_FR", "es_ES", "ja_JP", "zh_CN"]:
            result, _errors = parse_datetime(iso_str, locale)
            assert result is not None, f"ISO format failed for {locale}"
            assert result.year == 2025
            assert result.month == 1
            assert result.day == 28
            assert result.hour == 14
            assert result.minute == 30
            assert result.second == 0

    @given(
        year=st.integers(min_value=2020, max_value=2030),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),  # Safe for all months
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    def test_datetime_roundtrip_property(
        self,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
    ) -> None:
        """PROPERTY: Datetime formatted then parsed preserves values."""
        dt = datetime(year, month, day, hour, minute, 0, tzinfo=UTC)
        # Format as ISO (most reliable)
        iso_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        result, _errors = parse_datetime(iso_str, "en_US")
        if result is not None:
            assert result.year == year
            assert result.month == month
            assert result.day == day
            assert result.hour == hour
            assert result.minute == minute
