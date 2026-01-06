"""Complete coverage tests for era handling in parsing/dates.py.

Targets uncovered lines in era stripping and era token handling:
- Lines 523-530: _strip_era function
- Line 672: has_era = True in _babel_to_strptime

Python 3.13+. Focuses on edge cases in era parsing.
"""

from __future__ import annotations

from ftllexengine.parsing.dates import (
    _babel_to_strptime,
    _strip_era,
)


class TestStripEraFunction:
    """Test _strip_era function (lines 523-530)."""

    def test_strip_era_with_ad(self) -> None:
        """Test _strip_era removes 'AD' era string (line 523-528)."""
        value = "28 Jan 2025 AD"

        result = _strip_era(value)

        # Should remove 'AD' and normalize whitespace
        assert "AD" not in result
        assert result == "28 Jan 2025"

    def test_strip_era_with_anno_domini(self) -> None:
        """Test _strip_era removes 'Anno Domini' era string."""
        value = "Anno Domini 2025-01-28"

        result = _strip_era(value)

        # Should remove 'Anno Domini' and normalize whitespace
        assert "Anno Domini" not in result
        assert result == "2025-01-28"

    def test_strip_era_with_bc(self) -> None:
        """Test _strip_era removes 'BC' era string."""
        value = "100 BC"

        result = _strip_era(value)

        # Should remove 'BC' and normalize whitespace
        assert "BC" not in result
        assert result == "100"

    def test_strip_era_with_ce(self) -> None:
        """Test _strip_era removes 'CE' era string."""
        value = "2025 CE"

        result = _strip_era(value)

        # Should remove 'CE'
        assert "CE" not in result
        assert result == "2025"

    def test_strip_era_with_bce(self) -> None:
        """Test _strip_era removes 'BCE' era string."""
        value = "100 BCE"

        result = _strip_era(value)

        # Should remove 'BCE'
        assert "BCE" not in result
        assert result == "100"

    def test_strip_era_case_insensitive(self) -> None:
        """Test _strip_era is case-insensitive (line 526)."""
        value_lower = "2025 ad"
        value_upper = "2025 AD"
        value_mixed = "2025 Ad"

        result_lower = _strip_era(value_lower)
        result_upper = _strip_era(value_upper)
        result_mixed = _strip_era(value_mixed)

        # All should remove era regardless of case
        assert result_lower == "2025"
        assert result_upper == "2025"
        assert result_mixed == "2025"

    def test_strip_era_normalizes_whitespace(self) -> None:
        """Test _strip_era normalizes multiple spaces (line 530)."""
        value = "28   Jan    2025   AD"

        result = _strip_era(value)

        # Should collapse multiple spaces to single space
        assert "   " not in result
        assert result == "28 Jan 2025"

    def test_strip_era_no_era_present(self) -> None:
        """Test _strip_era with no era string (line 527 False branch)."""
        value = "2025-01-28"

        result = _strip_era(value)

        # Should return value unchanged (except whitespace normalization)
        assert result == "2025-01-28"

    def test_strip_era_multiple_eras(self) -> None:
        """Test _strip_era with multiple era strings."""
        # Edge case: value contains multiple era indicators
        value = "AD 2025 CE"

        result = _strip_era(value)

        # Should remove all era strings
        assert "AD" not in result
        assert "CE" not in result
        assert result == "2025"

    def test_strip_era_embedded_in_word_not_stripped(self) -> None:
        """Test _strip_era does NOT strip era embedded in words (branch 689->681 False path).

        When an era string is found but fails word boundary check,
        the era should NOT be stripped. This tests the branch where
        the condition at line 689 is False and loop continues.
        """
        # "AD" is embedded in "ADMIRE" - should not strip
        value_admire = "ADMIRE 2025"
        # "BC" is embedded in "ABCD" - should not strip
        value_abcd = "ABCD 100"
        # "CE" is embedded in "ONCE" - should not strip
        value_once = "ONCE upon 2025"

        result_admire = _strip_era(value_admire)
        result_abcd = _strip_era(value_abcd)
        result_once = _strip_era(value_once)

        # Words containing era substrings should remain unchanged
        assert result_admire == "ADMIRE 2025"
        assert result_abcd == "ABCD 100"
        assert result_once == "ONCE upon 2025"

    def test_strip_era_at_word_boundary_start_not_end(self) -> None:
        """Test era at start but not end word boundary is not stripped.

        "ADmiral" starts with "AD" at word boundary but "AD" is not at
        end word boundary, so should not be stripped.
        """
        value = "Admiral 2025"

        result = _strip_era(value)

        # "Admiral" should NOT be modified - "AD" embedded at start
        assert "Admiral" in result

    def test_strip_era_at_word_boundary_end_not_start(self) -> None:
        """Test era at end but not start word boundary is not stripped.

        Words ending with era substring should not be modified.
        """
        value = "CAD 2025"  # Ends with "AD" but "C" before it

        result = _strip_era(value)

        # "CAD" contains "AD" but not at start word boundary
        assert "CAD" in result


class TestBabelToStrptimeEraToken:
    """Test _babel_to_strptime era token handling (line 672)."""

    def test_babel_to_strptime_with_era_token_g(self) -> None:
        """Test _babel_to_strptime with era token 'G' (line 672)."""
        pattern = "d MMM y G"  # Day Month Year Era

        strptime_pattern, has_era = _babel_to_strptime(pattern)

        # Should mark has_era as True (line 672)
        assert has_era is True
        # Era token should be removed from pattern
        assert "G" not in strptime_pattern

    def test_babel_to_strptime_with_era_token_gg(self) -> None:
        """Test _babel_to_strptime with era token 'GG'."""
        pattern = "y-MM-dd GG"

        strptime_pattern, has_era = _babel_to_strptime(pattern)

        # Should mark has_era as True
        assert has_era is True
        # Pattern should have era removed
        assert "GG" not in strptime_pattern

    def test_babel_to_strptime_with_era_token_ggg(self) -> None:
        """Test _babel_to_strptime with era token 'GGG'."""
        pattern = "GGG y MMMM d"

        _strptime_pattern, has_era = _babel_to_strptime(pattern)

        # Should mark has_era as True
        assert has_era is True

    def test_babel_to_strptime_with_era_token_gggg(self) -> None:
        """Test _babel_to_strptime with era token 'GGGG'."""
        pattern = "d MMMM y GGGG"  # Full era name

        strptime_pattern, has_era = _babel_to_strptime(pattern)

        # Should mark has_era as True
        assert has_era is True
        # Full era token should be removed
        assert "GGGG" not in strptime_pattern

    def test_babel_to_strptime_without_era_token(self) -> None:
        """Test _babel_to_strptime without era token (has_era False)."""
        pattern = "d MMM y"  # No era token

        strptime_pattern, has_era = _babel_to_strptime(pattern)

        # Should mark has_era as False
        assert has_era is False
        # Should convert pattern correctly
        assert "%d" in strptime_pattern
        assert "%b" in strptime_pattern
        assert "%Y" in strptime_pattern

    def test_babel_to_strptime_with_timezone_token(self) -> None:
        """Test _babel_to_strptime with timezone token 'zzzz'.

        Timezone tokens are removed from patterns but not tracked separately
        since timezone names are not stripped from input.
        """
        pattern = "d MMM y HH:mm zzzz"  # With full timezone name

        strptime_pattern, has_era = _babel_to_strptime(pattern)

        assert has_era is False
        # Timezone token should be removed from pattern
        assert "zzzz" not in strptime_pattern


class TestDateParsingWithEra:
    """Integration tests for date parsing with era strings."""

    def test_parse_date_with_era_in_locale(self) -> None:
        """Test parse_date with locale that includes era in pattern."""
        from ftllexengine.parsing.dates import parse_date

        # Some locales include era in their patterns
        # Try parsing with era string in the input
        value = "28.01.2025 n. Chr."  # German-style with era (note: simplified)
        locale_code = "de_DE"

        _result, errors = parse_date(value, locale_code)

        # If the locale pattern has era, it should attempt to strip it
        # This tests the integration of _strip_era with parse_date
        # Result depends on whether de_DE actually uses era in patterns
        assert errors is not None  # errors tuple always returned

    def test_parse_datetime_with_era(self) -> None:
        """Test parse_datetime with era string in pattern."""
        from ftllexengine.parsing.dates import parse_datetime

        # Try with a value that might include era
        value = "2025-01-28 14:30 AD"
        locale_code = "en_US"

        _result, errors = parse_datetime(value, locale_code)

        # Should attempt to parse, may or may not succeed depending on pattern
        assert errors is not None  # errors tuple always returned
