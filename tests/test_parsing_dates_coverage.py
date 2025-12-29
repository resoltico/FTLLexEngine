"""Coverage tests for parsing/dates.py edge cases.

Targets uncovered lines:
- Lines 102-111: Unknown locale in parse_date
- Lines 207-216: Unknown locale in parse_datetime
- Lines 270-271, 275-276: Exception handling in _get_date_patterns
- Lines 298, 312, 321-322, 327-330: _extract_datetime_separator edge cases
- Lines 359-360, 381-382: Exception handling in _get_datetime_patterns
- Lines 481->483: Tokenizer continuation

Python 3.13+.
"""

from __future__ import annotations

from ftllexengine.parsing.dates import (
    _babel_to_strptime,
    _extract_datetime_separator,
    _get_date_patterns,
    _get_datetime_patterns,
    _preprocess_datetime_input,
    _tokenize_babel_pattern,
    parse_date,
    parse_datetime,
)

# ============================================================================
# parse_date Unknown Locale - Lines 102-111
# ============================================================================


class TestParseDateUnknownLocale:
    """Test parse_date with unknown locale (lines 102-111)."""

    def test_parse_date_unknown_locale_returns_error(self) -> None:
        """Test parse_date returns error for unknown locale."""
        result, errors = parse_date("2025-01-01", "xx-INVALID")

        # Should fail since locale is unknown and value is ISO format
        # ISO format should still work even with unknown locale
        # Actually, ISO 8601 is tried first, so this should succeed
        assert result is not None
        assert len(errors) == 0

    def test_parse_date_unknown_locale_non_iso_format(self) -> None:
        """Test parse_date with unknown locale and non-ISO format returns error."""
        result, errors = parse_date("01/28/2025", "xx-INVALID")

        # ISO format doesn't match, and locale is unknown
        assert result is None
        assert len(errors) == 1
        assert errors[0].parse_type == "date"

    def test_parse_date_malformed_locale(self) -> None:
        """Test parse_date with malformed locale returns error for non-ISO."""
        result, errors = parse_date("28.01.2025", "not-a-valid-locale-format")

        # Non-ISO format with invalid locale
        assert result is None
        assert len(errors) == 1


# ============================================================================
# parse_datetime Unknown Locale - Lines 207-216
# ============================================================================


class TestParseDatetimeUnknownLocale:
    """Test parse_datetime with unknown locale (lines 207-216)."""

    def test_parse_datetime_unknown_locale_iso_format(self) -> None:
        """Test parse_datetime with unknown locale and ISO format succeeds."""
        result, errors = parse_datetime("2025-01-28T14:30:00", "xx-INVALID")

        # ISO format is tried first, should succeed
        assert result is not None
        assert len(errors) == 0

    def test_parse_datetime_unknown_locale_non_iso_format(self) -> None:
        """Test parse_datetime with unknown locale and non-ISO format fails."""
        result, errors = parse_datetime("01/28/2025 2:30 PM", "xx-INVALID")

        # ISO format doesn't match, locale is unknown
        assert result is None
        assert len(errors) == 1
        assert errors[0].parse_type == "datetime"


# ============================================================================
# _get_date_patterns Exception Handling - Lines 270-271, 275-276
# ============================================================================


class TestGetDatePatternsExceptions:
    """Test _get_date_patterns exception handling (lines 270-276)."""

    def test_get_date_patterns_unknown_locale_returns_empty(self) -> None:
        """Test _get_date_patterns returns empty tuple for unknown locale."""
        # Clear cache to ensure fresh execution
        _get_date_patterns.cache_clear()

        patterns = _get_date_patterns("xx-UNKNOWN")

        assert patterns == ()

    def test_get_date_patterns_invalid_format_returns_empty(self) -> None:
        """Test _get_date_patterns returns empty for invalid format."""
        _get_date_patterns.cache_clear()

        patterns = _get_date_patterns("not-valid-at-all-xyz-123")

        assert patterns == ()

    def test_get_date_patterns_valid_locale_returns_patterns(self) -> None:
        """Test _get_date_patterns returns patterns for valid locale."""
        _get_date_patterns.cache_clear()

        patterns = _get_date_patterns("en-US")

        assert len(patterns) > 0

    def test_get_date_patterns_attribute_error_in_pattern(self) -> None:
        """Test lines 270-271: AttributeError when accessing date_formats.

        This tests the inner try/except that catches AttributeError/KeyError
        when accessing locale.date_formats[style].pattern.
        """
        from unittest.mock import MagicMock, patch

        from babel import Locale

        _get_date_patterns.cache_clear()

        # Create a mock locale that raises AttributeError for pattern
        mock_format = MagicMock()
        del mock_format.pattern  # Remove pattern attribute to cause AttributeError

        with patch.object(Locale, "parse") as mock_parse:
            mock_locale = MagicMock()
            mock_locale.date_formats = {
                "short": mock_format,
                "medium": mock_format,
                "long": mock_format,
            }
            mock_parse.return_value = mock_locale

            # Clear cache and call with a unique key to avoid cached results
            _get_date_patterns.cache_clear()
            patterns = _get_date_patterns("mock-locale-attr-err")

        # Should return empty tuple since all patterns failed
        assert patterns == ()


# ============================================================================
# _extract_datetime_separator Edge Cases - Lines 298, 312, 321-322, 327-330
# ============================================================================


class TestExtractDatetimeSeparator:
    """Test _extract_datetime_separator edge cases."""

    def test_extract_separator_normal_order(self) -> None:
        """Test separator extraction with normal order {1} before {0}."""
        from babel import Locale

        locale = Locale.parse("en_US")
        separator = _extract_datetime_separator(locale)

        # Should return a string separator
        assert isinstance(separator, str)

    def test_extract_separator_fallback_on_missing(self) -> None:
        """Test separator returns fallback when datetime_format missing."""
        from unittest.mock import MagicMock

        mock_locale = MagicMock()
        mock_locale.datetime_formats.get.return_value = None

        separator = _extract_datetime_separator(mock_locale)

        # Should return fallback space
        assert separator == " "

    def test_extract_separator_missing_placeholders(self) -> None:
        """Test separator returns fallback when placeholders missing (line 312)."""
        from unittest.mock import MagicMock

        mock_locale = MagicMock()
        # Pattern without {0} or {1}
        mock_locale.datetime_formats.get.return_value = "no placeholders here"

        separator = _extract_datetime_separator(mock_locale)

        assert separator == " "

    def test_extract_separator_reversed_order(self) -> None:
        """Test separator extraction with reversed order {0} before {1} (lines 321-322)."""
        from unittest.mock import MagicMock

        mock_locale = MagicMock()
        # Pattern with {0} before {1}: time first, then date
        mock_locale.datetime_formats.get.return_value = "{0} at {1}"

        separator = _extract_datetime_separator(mock_locale)

        # Should extract " at " as separator
        assert separator == " at "

    def test_extract_separator_adjacent_placeholders(self) -> None:
        """Test separator returns fallback when placeholders adjacent (line 327)."""
        from unittest.mock import MagicMock

        mock_locale = MagicMock()
        # Pattern with adjacent placeholders (sep_start >= sep_end)
        mock_locale.datetime_formats.get.return_value = "{1}{0}"

        separator = _extract_datetime_separator(mock_locale)

        # sep_start == sep_end, returns fallback
        assert separator == " "

    def test_extract_separator_exception_handling(self) -> None:
        """Test separator returns fallback on exception (lines 329-330)."""
        from unittest.mock import MagicMock

        mock_locale = MagicMock()
        mock_locale.datetime_formats.get.side_effect = AttributeError("mock error")

        separator = _extract_datetime_separator(mock_locale)

        assert separator == " "


# ============================================================================
# _get_datetime_patterns Exception Handling - Lines 359-360, 381-382
# ============================================================================


class TestGetDatetimePatternsExceptions:
    """Test _get_datetime_patterns exception handling (lines 359-360, 381-382)."""

    def test_get_datetime_patterns_unknown_locale_returns_empty(self) -> None:
        """Test _get_datetime_patterns returns empty for unknown locale."""
        _get_datetime_patterns.cache_clear()

        patterns = _get_datetime_patterns("xx-UNKNOWN")

        assert patterns == ()

    def test_get_datetime_patterns_invalid_format_returns_empty(self) -> None:
        """Test _get_datetime_patterns returns empty for invalid format."""
        _get_datetime_patterns.cache_clear()

        patterns = _get_datetime_patterns("invalid-locale-format-xyz")

        assert patterns == ()

    def test_get_datetime_patterns_valid_locale_returns_patterns(self) -> None:
        """Test _get_datetime_patterns returns patterns for valid locale.

        Note: For valid locales, datetime_formats returns template strings
        like '{1}, {0}' not DateTimePattern objects, so the CLDR datetime
        pattern extraction (lines 358-360) won't work directly. Patterns
        come from the date_patterns + time suffixes combination instead.
        """
        _get_datetime_patterns.cache_clear()

        patterns = _get_datetime_patterns("en-US")

        # Patterns come from date_patterns + time combinations, not CLDR datetime
        assert len(patterns) > 0

    def test_get_datetime_patterns_cldr_pattern_success_path(self) -> None:
        """Test lines 359-360: successful CLDR datetime pattern extraction.

        Babel's datetime_formats returns template strings, not DateTimePattern
        objects. To cover lines 359-360 (the success path), we must mock
        the locale to return objects with .pattern attributes.
        """
        from unittest.mock import MagicMock, patch

        from babel import Locale

        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()

        # Create mock format objects that return valid Babel patterns
        class MockDateTimeFormat:
            def __init__(self, pattern_str: str) -> None:
                self._pattern = pattern_str

            @property
            def pattern(self) -> str:
                return self._pattern

        mock_short = MockDateTimeFormat("M/d/yy, h:mm a")
        mock_medium = MockDateTimeFormat("MMM d, yyyy, h:mm:ss a")
        mock_long = MockDateTimeFormat("MMMM d, yyyy 'at' h:mm:ss a")

        with patch.object(Locale, "parse") as mock_parse:
            mock_locale = MagicMock()

            # datetime_formats returns objects with .pattern attribute
            mock_datetime_formats = MagicMock()
            mock_datetime_formats.__getitem__ = MagicMock(
                side_effect=lambda k: {
                    "short": mock_short,
                    "medium": mock_medium,
                    "long": mock_long,
                }.get(k, mock_short)
            )
            mock_datetime_formats.get = MagicMock(return_value="{1}, {0}")
            mock_locale.datetime_formats = mock_datetime_formats

            # date_formats also needs to work
            mock_date_format = MockDateTimeFormat("M/d/yy")
            mock_date_formats = MagicMock()
            mock_date_formats.__getitem__ = MagicMock(return_value=mock_date_format)
            mock_locale.date_formats = mock_date_formats

            mock_parse.return_value = mock_locale

            _get_datetime_patterns.cache_clear()
            _get_date_patterns.cache_clear()
            patterns = _get_datetime_patterns("mock-cldr-success-v1")

        # Should have patterns from both CLDR datetime formats AND date+time combinations
        assert len(patterns) > 0
        # Verify the CLDR patterns were converted (lines 359-360 executed)
        # The patterns should contain strptime directives
        # patterns is now tuple of (pattern_str, has_era) tuples
        pattern_str = " ".join(p[0] for p in patterns)
        assert "%" in pattern_str  # Contains strptime directives

    def test_get_datetime_patterns_attribute_error_in_pattern(self) -> None:
        """Test lines 359-360: AttributeError when accessing datetime_formats.

        This tests the inner try/except that catches AttributeError/KeyError
        when accessing locale.datetime_formats[style].pattern.

        Note: This exception path is difficult to trigger because the code
        iterates through styles and catches exceptions per-style. We test
        that the function handles the case gracefully.
        """
        from unittest.mock import MagicMock, patch

        from babel import Locale

        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()

        # Create a mock format that raises AttributeError when accessing pattern
        class RaisingFormat:
            @property
            def pattern(self) -> str:
                msg = "no pattern attribute"
                raise AttributeError(msg)

        mock_format = RaisingFormat()

        with patch.object(Locale, "parse") as mock_parse:
            mock_locale = MagicMock()
            # Use MagicMock for datetime_formats to allow .get assignment
            mock_datetime_formats = MagicMock()
            mock_datetime_formats.__getitem__ = MagicMock(return_value=mock_format)
            mock_datetime_formats.get = MagicMock(return_value=None)  # For separator extraction
            mock_locale.datetime_formats = mock_datetime_formats
            # date_formats also needs to raise AttributeError
            mock_date_formats = MagicMock()
            mock_date_formats.__getitem__ = MagicMock(return_value=mock_format)
            mock_locale.date_formats = mock_date_formats
            mock_parse.return_value = mock_locale

            _get_datetime_patterns.cache_clear()
            _get_date_patterns.cache_clear()
            patterns = _get_datetime_patterns("mock-locale-datetime-attr-err-v3")

        # Should return empty tuple since all patterns failed
        assert patterns == ()

    def test_get_datetime_patterns_key_error_via_missing_key(self) -> None:
        """Test lines 359-360: KeyError when accessing datetime_formats style."""
        from unittest.mock import MagicMock, patch

        from babel import Locale

        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()

        with patch.object(Locale, "parse") as mock_parse:
            mock_locale = MagicMock()
            # Use MagicMock that raises KeyError on item access
            mock_datetime_formats = MagicMock()
            mock_datetime_formats.__getitem__ = MagicMock(
                side_effect=KeyError("No format")
            )
            mock_datetime_formats.get = MagicMock(return_value=None)
            mock_locale.datetime_formats = mock_datetime_formats
            # date_formats also raises KeyError
            mock_date_formats = MagicMock()
            mock_date_formats.__getitem__ = MagicMock(
                side_effect=KeyError("No format")
            )
            mock_locale.date_formats = mock_date_formats
            mock_parse.return_value = mock_locale

            _get_datetime_patterns.cache_clear()
            _get_date_patterns.cache_clear()
            patterns = _get_datetime_patterns("mock-locale-keyerror-v2")

        # Should return empty tuple since no patterns could be extracted
        assert patterns == ()


# ============================================================================
# _tokenize_babel_pattern Edge Cases - Lines 481->483
# ============================================================================


class TestTokenizeBabelPattern:
    """Test _tokenize_babel_pattern edge cases."""

    def test_tokenize_empty_pattern(self) -> None:
        """Test tokenization of empty pattern."""
        tokens = _tokenize_babel_pattern("")

        assert tokens == []

    def test_tokenize_quoted_literals(self) -> None:
        """Test tokenization with quoted literals."""
        # Pattern with quoted literal 'at'
        tokens = _tokenize_babel_pattern("h 'at' mm")

        assert "at" in tokens
        assert "h" in tokens
        assert "mm" in tokens

    def test_tokenize_escaped_quote(self) -> None:
        """Test tokenization with escaped single quote ''."""
        # Two single quotes produce a literal single quote
        tokens = _tokenize_babel_pattern("h''mm")

        assert "'" in tokens
        assert "h" in tokens
        assert "mm" in tokens

    def test_tokenize_quoted_with_escaped_quote(self) -> None:
        """Test tokenization with escaped quote inside quoted section."""
        # Pattern "h 'o''clock' a" should produce "o'clock"
        tokens = _tokenize_babel_pattern("h 'o''clock' a")

        assert "o'clock" in tokens

    def test_tokenize_unclosed_quote(self) -> None:
        """Test tokenization with unclosed quote at end."""
        # Pattern with unclosed quote - should handle gracefully
        tokens = _tokenize_babel_pattern("h 'unclosed")

        # Should still produce tokens
        assert "h" in tokens
        assert "unclosed" in tokens

    def test_tokenize_empty_quoted_section(self) -> None:
        """Test tokenization with empty quoted section '' (line 481->483)."""
        # Empty quotes: '' produces single quote, not empty token
        tokens = _tokenize_babel_pattern("a''b")

        assert "'" in tokens
        assert "a" in tokens
        assert "b" in tokens

    def test_tokenize_adjacent_quoted_sections(self) -> None:
        """Test tokenization with adjacent empty quoted sections."""
        # Multiple adjacent quotes
        tokens = _tokenize_babel_pattern("''''")  # Four quotes = two literal quotes

        assert tokens.count("'") == 2

    def test_tokenize_empty_quoted_string(self) -> None:
        """Test tokenization with empty quoted string '' (lines 481->483).

        An empty quoted section '' outside of a quote context produces a single quote.
        But an empty quoted section as literal (like just '') should not add anything
        to the tokens if literal_chars is empty after processing.
        """
        # Just two quotes - produces single quote (not empty string)
        tokens = _tokenize_babel_pattern("''")
        assert "'" in tokens

        # Three quotes - first two produce single quote, third starts quote section
        tokens = _tokenize_babel_pattern("'''")
        assert "'" in tokens

    def test_tokenize_real_world_patterns(self) -> None:
        """Test tokenization with real-world CLDR patterns."""
        # German pattern with quoted literal
        tokens = _tokenize_babel_pattern("d. MMMM yyyy 'um' HH:mm")
        assert "um" in tokens
        assert "d" in tokens
        assert "MMMM" in tokens
        assert "yyyy" in tokens

        # Pattern with 'at' literal
        tokens = _tokenize_babel_pattern("EEEE, MMMM d, y 'at' h:mm a")
        assert "at" in tokens

    def test_tokenize_pattern_ending_in_quote(self) -> None:
        """Test pattern that ends with unclosed quote."""
        # This tests the continuation when we hit EOF while in quoted section
        tokens = _tokenize_babel_pattern("yyyy 'test")
        assert "yyyy" in tokens
        assert "test" in tokens


# ============================================================================
# _preprocess_datetime_input - Line 657
# ============================================================================


class TestPreprocessDatetimeInput:
    """Test _preprocess_datetime_input function (line 657)."""

    def test_preprocess_with_has_era_true(self) -> None:
        """Test _preprocess_datetime_input with has_era=True.

        This directly tests the _strip_era branch.
        """
        value = "28 Jan 2025 AD"

        result = _preprocess_datetime_input(value, has_era=True)

        # Should strip era text
        assert "AD" not in result
        assert result == "28 Jan 2025"

    def test_preprocess_with_has_era_false(self) -> None:
        """Test _preprocess_datetime_input with has_era=False."""
        value = "2025-01-28 14:30:00"

        result = _preprocess_datetime_input(value, has_era=False)

        # Should return unchanged
        assert result == value

    def test_preprocess_with_era_and_timezone_in_value(self) -> None:
        """Test _preprocess_datetime_input preserves timezone in input."""
        value = "28 Jan 2025 AD PST"

        result = _preprocess_datetime_input(value, has_era=True)

        # Era is stripped, timezone preserved in output
        assert "AD" not in result
        assert "PST" in result


# ============================================================================
# _babel_to_strptime timezone token - Branch 811->803
# ============================================================================


class TestBabelToStrptimeTimezoneToken:
    """Test _babel_to_strptime timezone token handling (branch 811->803)."""

    def test_babel_to_strptime_with_timezone_z(self) -> None:
        """Test _babel_to_strptime with timezone token 'z'."""
        pattern = "d MMM y HH:mm z"

        strptime_pattern, has_era, has_timezone = _babel_to_strptime(pattern)

        # Should mark has_timezone as True
        assert has_timezone is True
        assert has_era is False
        # Timezone token should be removed
        assert "z" not in strptime_pattern

    def test_babel_to_strptime_with_timezone_zzzz(self) -> None:
        """Test _babel_to_strptime with timezone token 'zzzz'."""
        pattern = "MMMM d, y 'at' h:mm a zzzz"

        strptime_pattern, has_era, has_timezone = _babel_to_strptime(pattern)

        assert has_timezone is True
        assert has_era is False
        assert "zzzz" not in strptime_pattern

    def test_babel_to_strptime_with_timezone_v(self) -> None:
        """Test _babel_to_strptime with timezone token 'v'."""
        pattern = "d MMM y HH:mm v"

        _strptime_pattern, _has_era, has_timezone = _babel_to_strptime(pattern)

        assert has_timezone is True

    def test_babel_to_strptime_with_timezone_vvvv(self) -> None:
        """Test _babel_to_strptime with timezone token 'vvvv'."""
        pattern = "d MMM y HH:mm vvvv"

        _strptime_pattern, _has_era, has_timezone = _babel_to_strptime(pattern)

        assert has_timezone is True

    def test_babel_to_strptime_with_timezone_o(self) -> None:
        """Test _babel_to_strptime with timezone token 'O'."""
        pattern = "d MMM y HH:mm O"

        _strptime_pattern, _has_era, has_timezone = _babel_to_strptime(pattern)

        assert has_timezone is True

    def test_babel_to_strptime_with_both_era_and_timezone(self) -> None:
        """Test _babel_to_strptime with both era and timezone tokens."""
        pattern = "d MMM y G HH:mm z"

        strptime_pattern, has_era, has_timezone = _babel_to_strptime(pattern)

        # Both should be True
        assert has_era is True
        assert has_timezone is True
        # Both tokens should be removed
        assert "G" not in strptime_pattern
        assert "z" not in strptime_pattern

    def test_babel_to_strptime_none_token_fallthrough(self) -> None:
        """Test _babel_to_strptime with None-mapped token that doesn't match era/timezone.

        This tests the defensive code path (branch 811->803) where a token
        maps to None but doesn't start with 'G' (era) or timezone prefixes.

        Currently, all None-mapped tokens in _BABEL_TOKEN_MAP match one of these
        conditions, but the code is defensive for future additions.
        """
        from unittest.mock import patch

        from ftllexengine.parsing import dates as dates_module

        # Create modified _BABEL_TOKEN_MAP with a None-mapped token that
        # doesn't match era or timezone prefixes
        original_map = dates_module._BABEL_TOKEN_MAP.copy()
        modified_map = original_map.copy()
        modified_map["QQQ"] = None  # Fictional token that maps to None

        with patch.object(dates_module, "_BABEL_TOKEN_MAP", modified_map):
            # Pattern with the fictional token
            pattern = "d MMM y QQQ HH:mm"

            strptime_pattern, has_era, has_timezone = _babel_to_strptime(pattern)

            # Neither era nor timezone should be True
            assert has_era is False
            assert has_timezone is False
            # The token should have been silently dropped (no output)
            assert "QQQ" not in strptime_pattern
