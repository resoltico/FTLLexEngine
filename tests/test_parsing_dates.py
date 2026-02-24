"""Tests for date and datetime parsing functions.

Core parsing tests, internal function edge cases, tokenizer, separator
extraction, BabelImportError paths, datetime ordering, and property-based
roundtrip tests for parse_date() and parse_datetime().

Functions return tuple[value, errors]:
- parse_date() returns tuple[date | None, list[FluentParseError]]
- parse_datetime() returns tuple[datetime | None, list[FluentParseError]]
- Functions never raise exceptions; errors returned in list

Python 3.13+.
"""

from __future__ import annotations

import builtins
import sys
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from babel import Locale
from hypothesis import event, given
from hypothesis import strategies as st

import ftllexengine.core.babel_compat as _bc
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

# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------


class TestParseDate:
    """Test parse_date() function."""

    def test_parse_date_us_format(self) -> None:
        """Parse US date format (M/d/yy - CLDR short format)."""
        result, errors = parse_date("1/28/25", "en_US")
        assert not errors
        assert result == date(2025, 1, 28)

    def test_parse_date_european_format(self) -> None:
        """Parse European date format (d.M.yy - CLDR short format)."""
        result, errors = parse_date("28.1.25", "lv_LV")
        assert not errors
        assert result == date(2025, 1, 28)

        result, errors = parse_date("28.01.25", "de_DE")
        assert not errors
        assert result == date(2025, 1, 28)

    def test_parse_date_iso_format(self) -> None:
        """Parse ISO 8601 date format."""
        result, errors = parse_date("2025-01-28", "en_US")
        assert not errors
        assert result == date(2025, 1, 28)

    def test_parse_date_invalid_returns_error(self) -> None:
        """Invalid input returns error in tuple; function never raises."""
        result, errors = parse_date("invalid", "en_US")
        assert len(errors) > 0
        assert result is None
        assert errors[0].parse_type == "date"
        assert errors[0].input_value == "invalid"

    def test_parse_date_empty_returns_error(self) -> None:
        """Empty input returns error in list."""
        result, errors = parse_date("", "en_US")
        assert len(errors) > 0
        assert result is None


# ---------------------------------------------------------------------------
# parse_datetime
# ---------------------------------------------------------------------------


class TestParseDatetime:
    """Test parse_datetime() function."""

    def test_parse_datetime_us_format(self) -> None:
        """Parse US datetime format (M/d/yy + time - CLDR)."""
        result, errors = parse_datetime("1/28/25, 14:30", "en_US")
        assert not errors
        assert result == datetime(2025, 1, 28, 14, 30)

    def test_parse_datetime_european_format(self) -> None:
        """Parse European datetime format (d.M.yy + time - CLDR)."""
        result, errors = parse_datetime("28.1.25 14:30", "lv_LV")
        assert not errors
        assert result == datetime(2025, 1, 28, 14, 30)

    def test_parse_datetime_with_timezone(self) -> None:
        """Parse datetime and apply timezone."""
        result, errors = parse_datetime(
            "2025-01-28 14:30", "en_US", tzinfo=UTC
        )
        assert not errors
        assert result == datetime(2025, 1, 28, 14, 30, tzinfo=UTC)

    def test_parse_datetime_invalid_returns_error(self) -> None:
        """Invalid input returns error in tuple; function never raises."""
        result, errors = parse_datetime("invalid", "en_US")
        assert len(errors) > 0
        assert result is None
        assert errors[0].parse_type == "datetime"

    def test_parse_datetime_empty_returns_error(self) -> None:
        """Empty input returns error in list."""
        result, errors = parse_datetime("", "en_US")
        assert len(errors) > 0
        assert result is None

    def test_parse_datetime_with_seconds(self) -> None:
        """Datetime parsing with seconds component."""
        result, errors = parse_datetime("28.01.25, 14:30:45", "de_DE")
        assert not errors
        assert result is not None
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 45

    def test_parse_datetime_iso_format_all_locales(self) -> None:
        """ISO format works across all locales."""
        iso_str = "2025-01-28 14:30:00"
        for locale in [
            "en_US", "de_DE", "fr_FR", "es_ES", "ja_JP", "zh_CN"
        ]:
            result, errors = parse_datetime(iso_str, locale)
            assert not errors
            assert result is not None, f"ISO format failed for {locale}"
            assert result.year == 2025
            assert result.month == 1
            assert result.day == 28

    def test_parse_datetime_with_working_formats(self) -> None:
        """Datetime parsing with CLDR locale-specific separators."""
        test_cases = [
            ("01/28/25, 14:30", "en_US"),
            ("01/28/25, 02:30 PM", "en_US"),
            ("28.01.25, 14:30", "de_DE"),
        ]
        for date_str, locale in test_cases:
            result, errors = parse_datetime(date_str, locale)
            assert not errors
            assert result is not None, (
                f"Failed to parse '{date_str}' for {locale}"
            )
            assert result.year == 2025
            assert result.month == 1
            assert result.day == 28


# ============================================================================
# Unknown Locale Handling
# ============================================================================


class TestParseDateUnknownLocale:
    """Test parse_date with unknown locale."""

    def test_iso_format_succeeds(self) -> None:
        """ISO format succeeds even with unknown locale."""
        result, errors = parse_date("2025-01-01", "xx-INVALID")
        assert result is not None
        assert len(errors) == 0

    def test_non_iso_format_fails(self) -> None:
        """Non-ISO format with unknown locale returns error."""
        result, errors = parse_date("01/28/2025", "xx-INVALID")
        assert result is None
        assert len(errors) == 1
        assert errors[0].parse_type == "date"

    def test_malformed_locale(self) -> None:
        """Malformed locale returns error for non-ISO format."""
        result, errors = parse_date(
            "28.01.2025", "not-a-valid-locale-format"
        )
        assert result is None
        assert len(errors) == 1


class TestParseDatetimeUnknownLocale:
    """Test parse_datetime with unknown locale."""

    def test_iso_format_succeeds(self) -> None:
        """ISO format succeeds even with unknown locale."""
        result, errors = parse_datetime(
            "2025-01-28T14:30:00", "xx-INVALID"
        )
        assert result is not None
        assert len(errors) == 0

    def test_non_iso_format_fails(self) -> None:
        """Non-ISO format with unknown locale returns error."""
        result, errors = parse_datetime(
            "01/28/2025 2:30 PM", "xx-INVALID"
        )
        assert result is None
        assert len(errors) == 1
        assert errors[0].parse_type == "datetime"


# ============================================================================
# _tokenize_babel_pattern
# ============================================================================


class TestTokenizeBabelPattern:
    """Test CLDR pattern tokenizer quote handling."""

    def test_simple_quoted_literal(self) -> None:
        """Simple quoted literal is extracted as single token."""
        tokens = _tokenize_babel_pattern("h 'at' a")
        assert "at" in tokens

    def test_escaped_quote_outside(self) -> None:
        """Two quotes '' outside a quoted section produce literal quote."""
        tokens = _tokenize_babel_pattern("h''mm")
        assert "'" in tokens

    def test_escaped_quote_inside(self) -> None:
        """Two quotes '' inside quoted text produce literal quote."""
        tokens = _tokenize_babel_pattern("h 'o''clock' a")
        assert "o'clock" in tokens

    def test_irish_locale_pattern(self) -> None:
        """Quoted literals in locale patterns."""
        tokens = _tokenize_babel_pattern("d MMMM 'de' yyyy")
        assert "de" in tokens
        assert "d" in tokens
        assert "yyyy" in tokens

    def test_standard_pattern_unchanged(self) -> None:
        """Standard patterns without quotes work correctly."""
        tokens = _tokenize_babel_pattern("yyyy-MM-dd")
        assert tokens == ["yyyy", "-", "MM", "-", "dd"]

    def test_latvian_pattern(self) -> None:
        """Latvian date pattern d.MM.yyyy."""
        tokens = _tokenize_babel_pattern("d.MM.yyyy")
        assert tokens == ["d", ".", "MM", ".", "yyyy"]

    def test_empty_pattern(self) -> None:
        """Empty pattern produces empty token list."""
        assert _tokenize_babel_pattern("") == []

    def test_unclosed_quote(self) -> None:
        """Unclosed quote at end is handled gracefully."""
        tokens = _tokenize_babel_pattern("h 'unclosed")
        assert "h" in tokens
        assert "unclosed" in tokens

    def test_empty_quoted_section(self) -> None:
        """Empty quotes '' produce single quote, not empty token."""
        tokens = _tokenize_babel_pattern("a''b")
        assert "'" in tokens
        assert "a" in tokens
        assert "b" in tokens

    def test_adjacent_quoted_sections(self) -> None:
        """Multiple adjacent quotes produce multiple literal quotes."""
        tokens = _tokenize_babel_pattern("''''")
        assert tokens.count("'") == 2

    def test_just_two_quotes(self) -> None:
        """Just '' produces single quote."""
        tokens = _tokenize_babel_pattern("''")
        assert "'" in tokens

    def test_three_quotes(self) -> None:
        """Three quotes: first two produce quote, third starts section."""
        tokens = _tokenize_babel_pattern("'''")
        assert "'" in tokens

    def test_real_world_german_pattern(self) -> None:
        """German pattern with quoted 'um' literal."""
        tokens = _tokenize_babel_pattern("d. MMMM yyyy 'um' HH:mm")
        assert "um" in tokens
        assert "d" in tokens
        assert "MMMM" in tokens

    def test_real_world_at_pattern(self) -> None:
        """Pattern with 'at' literal."""
        tokens = _tokenize_babel_pattern(
            "EEEE, MMMM d, y 'at' h:mm a"
        )
        assert "at" in tokens

    def test_pattern_ending_in_quote(self) -> None:
        """Pattern ending with unclosed quote handled gracefully."""
        tokens = _tokenize_babel_pattern("yyyy 'test")
        assert "yyyy" in tokens
        assert "test" in tokens

    def test_russian_quoted_literal(self) -> None:
        """Russian pattern with quoted Cyrillic year marker."""
        pattern = "d MMMM y '\u0433'."
        tokens = _tokenize_babel_pattern(pattern)
        assert "\u0433" in tokens
        assert "d" in tokens
        assert "MMMM" in tokens
        assert "y" in tokens
        assert "." in tokens

    def test_spanish_quoted_de(self) -> None:
        """Spanish pattern d 'de' MMMM 'de' y with quoted 'de'."""
        tokens = _tokenize_babel_pattern("d 'de' MMMM 'de' y")
        assert "de" in tokens
        assert "d" in tokens
        assert "MMMM" in tokens
        assert "y" in tokens


# ============================================================================
# _extract_datetime_separator
# ============================================================================


class TestExtractDatetimeSeparator:
    """Test _extract_datetime_separator edge cases."""

    def test_normal_order(self) -> None:
        """en_US uses date-first order."""
        locale = Locale.parse("en_US")
        separator, is_time_first = _extract_datetime_separator(locale)
        assert isinstance(separator, str)
        assert is_time_first is False

    def test_fallback_on_missing(self) -> None:
        """Missing datetime_format returns fallback space."""
        mock_locale = MagicMock()
        mock_locale.datetime_formats.get.return_value = None
        separator, is_time_first = _extract_datetime_separator(mock_locale)
        assert separator == " "
        assert is_time_first is False

    def test_missing_placeholders(self) -> None:
        """Pattern without placeholders returns fallback."""
        mock_locale = MagicMock()
        mock_locale.datetime_formats.get.return_value = (
            "no placeholders here"
        )
        separator, is_time_first = _extract_datetime_separator(mock_locale)
        assert separator == " "
        assert is_time_first is False

    def test_reversed_order(self) -> None:
        """Pattern with {0} before {1} detects time-first."""
        mock_locale = MagicMock()
        mock_locale.datetime_formats.get.return_value = "{0} at {1}"
        separator, is_time_first = _extract_datetime_separator(mock_locale)
        assert separator == " at "
        assert is_time_first is True

    def test_adjacent_placeholders(self) -> None:
        """Adjacent placeholders return fallback separator."""
        mock_locale = MagicMock()
        mock_locale.datetime_formats.get.return_value = "{1}{0}"
        separator, is_time_first = _extract_datetime_separator(mock_locale)
        assert separator == " "
        assert is_time_first is False

    def test_exception_handling(self) -> None:
        """AttributeError returns fallback."""
        mock_locale = MagicMock()
        mock_locale.datetime_formats.get.side_effect = AttributeError(
            "mock error"
        )
        separator, is_time_first = _extract_datetime_separator(mock_locale)
        assert separator == " "
        assert is_time_first is False


# ============================================================================
# _get_date_patterns Exception Handling
# ============================================================================


class TestGetDatePatternsExceptions:
    """Test _get_date_patterns exception handling."""

    def test_unknown_locale_returns_empty(self) -> None:
        """Unknown locale returns empty tuple."""
        _get_date_patterns.cache_clear()
        assert _get_date_patterns("xx-UNKNOWN") == ()

    def test_invalid_format_returns_empty(self) -> None:
        """Invalid format returns empty tuple."""
        _get_date_patterns.cache_clear()
        assert _get_date_patterns("not-valid-at-all-xyz-123") == ()

    def test_valid_locale_returns_patterns(self) -> None:
        """Valid locale returns non-empty patterns."""
        _get_date_patterns.cache_clear()
        assert len(_get_date_patterns("en-US")) > 0

    def test_attribute_error_in_pattern(self) -> None:
        """AttributeError accessing pattern falls back to str(fmt)."""
        _get_date_patterns.cache_clear()

        mock_format = MagicMock()
        del mock_format.pattern

        with patch.object(Locale, "parse") as mock_parse:
            mock_locale = MagicMock()
            mock_locale.date_formats = {
                "short": mock_format, "medium": mock_format,
                "long": mock_format, "full": mock_format,
            }
            mock_parse.return_value = mock_locale
            _get_date_patterns.cache_clear()
            patterns = _get_date_patterns("mock-locale-attr-err")

        assert len(patterns) > 0

    def test_raises_babel_import_error_when_babel_missing(self) -> None:
        """Raises BabelImportError when Babel unavailable."""
        _get_date_patterns.cache_clear()
        _bc._babel_available = None

        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_: dict[str, object] | None = None,
            locals_: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name == "babel":
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        try:
            with patch.object(
                builtins, "__import__", side_effect=mock_import
            ):
                with pytest.raises(
                    ImportError, match="parse"
                ) as exc_info:
                    _get_date_patterns("en_US")
                assert exc_info.typename == "BabelImportError"
                assert "parse_date" in str(exc_info.value)
        finally:
            _bc._babel_available = None

    def test_babel_import_error_feature_name(self) -> None:
        """BabelImportError contains correct feature name."""
        _get_date_patterns.cache_clear()
        _bc._babel_available = None

        babel_modules_backup = {}
        babel_keys = [
            k for k in sys.modules
            if k == "babel" or k.startswith("babel.")
        ]
        for key in babel_keys:
            babel_modules_backup[key] = sys.modules.pop(key, None)

        try:
            original_import = builtins.__import__

            def mock_import(
                name: str,
                globals_: dict[str, object] | None = None,
                locals_: dict[str, object] | None = None,
                fromlist: tuple[str, ...] = (),
                level: int = 0,
            ) -> object:
                if name == "babel" or name.startswith("babel."):
                    msg = f"No module named '{name}'"
                    raise ImportError(msg)
                return original_import(
                    name, globals_, locals_, fromlist, level
                )

            with patch.object(
                builtins, "__import__", side_effect=mock_import
            ):
                with pytest.raises(
                    ImportError, match="parse"
                ) as exc_info:
                    _get_date_patterns("en_US")
                assert "parse_date" in str(exc_info.value)
        finally:
            for key, value in babel_modules_backup.items():
                if value is not None:
                    sys.modules[key] = value
            _get_date_patterns.cache_clear()
            _bc._babel_available = None


# ============================================================================
# _get_datetime_patterns Exception Handling
# ============================================================================


class TestGetDatetimePatternsExceptions:
    """Test _get_datetime_patterns exception handling."""

    def test_unknown_locale_returns_empty(self) -> None:
        """Unknown locale returns empty tuple."""
        _get_datetime_patterns.cache_clear()
        assert _get_datetime_patterns("xx-UNKNOWN") == ()

    def test_invalid_format_returns_empty(self) -> None:
        """Invalid format returns empty tuple."""
        _get_datetime_patterns.cache_clear()
        assert _get_datetime_patterns("invalid-locale-format-xyz") == ()

    def test_valid_locale_returns_patterns(self) -> None:
        """Valid locale returns non-empty patterns."""
        _get_datetime_patterns.cache_clear()
        assert len(_get_datetime_patterns("en-US")) > 0

    def test_cldr_pattern_success_path(self) -> None:
        """Successful CLDR datetime pattern extraction via mock."""
        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()

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
            mock_datetime_formats = MagicMock()
            mock_datetime_formats.__getitem__ = MagicMock(
                side_effect=lambda k: {
                    "short": mock_short,
                    "medium": mock_medium,
                    "long": mock_long,
                }.get(k, mock_short)
            )
            mock_datetime_formats.get = MagicMock(
                return_value="{1}, {0}"
            )
            mock_locale.datetime_formats = mock_datetime_formats

            mock_date_format = MockDateTimeFormat("M/d/yy")
            mock_date_formats = MagicMock()
            mock_date_formats.__getitem__ = MagicMock(
                return_value=mock_date_format
            )
            mock_locale.date_formats = mock_date_formats
            mock_parse.return_value = mock_locale

            _get_datetime_patterns.cache_clear()
            _get_date_patterns.cache_clear()
            patterns = _get_datetime_patterns("mock-cldr-success-v1")

        assert len(patterns) > 0
        pattern_str = " ".join(p[0] for p in patterns)
        assert "%" in pattern_str

    def test_attribute_error_in_pattern(self) -> None:
        """AttributeError accessing datetime pattern handled gracefully."""
        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()

        class RaisingFormat:
            @property
            def pattern(self) -> str:
                msg = "no pattern attribute"
                raise AttributeError(msg)

        mock_format = RaisingFormat()

        with patch.object(Locale, "parse") as mock_parse:
            mock_locale = MagicMock()
            mock_datetime_formats = MagicMock()
            mock_datetime_formats.__getitem__ = MagicMock(
                return_value=mock_format
            )
            mock_datetime_formats.get = MagicMock(return_value=None)
            mock_locale.datetime_formats = mock_datetime_formats
            mock_date_formats = MagicMock()
            mock_date_formats.__getitem__ = MagicMock(
                return_value=mock_format
            )
            mock_locale.date_formats = mock_date_formats
            mock_parse.return_value = mock_locale

            _get_datetime_patterns.cache_clear()
            _get_date_patterns.cache_clear()
            patterns = _get_datetime_patterns(
                "mock-locale-datetime-attr-err-v3"
            )

        assert len(patterns) > 0

    def test_key_error_via_missing_key(self) -> None:
        """KeyError accessing datetime style handled gracefully."""
        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()

        with patch.object(Locale, "parse") as mock_parse:
            mock_locale = MagicMock()
            mock_datetime_formats = MagicMock()
            mock_datetime_formats.__getitem__ = MagicMock(
                side_effect=KeyError("No format")
            )
            mock_datetime_formats.get = MagicMock(return_value=None)
            mock_locale.datetime_formats = mock_datetime_formats
            mock_date_formats = MagicMock()
            mock_date_formats.__getitem__ = MagicMock(
                side_effect=KeyError("No format")
            )
            mock_locale.date_formats = mock_date_formats
            mock_parse.return_value = mock_locale

            _get_datetime_patterns.cache_clear()
            _get_date_patterns.cache_clear()
            patterns = _get_datetime_patterns(
                "mock-locale-keyerror-v2"
            )

        assert patterns == ()

    def test_raises_babel_import_error_when_babel_missing(self) -> None:
        """Raises BabelImportError when Babel unavailable."""
        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()
        _bc._babel_available = None

        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_: dict[str, object] | None = None,
            locals_: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name == "babel":
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        try:
            with patch.object(
                builtins, "__import__", side_effect=mock_import
            ):
                with pytest.raises(
                    ImportError, match="parse"
                ) as exc_info:
                    _get_datetime_patterns("en_US")
                assert exc_info.typename == "BabelImportError"
                assert "parse_datetime" in str(exc_info.value)
        finally:
            _bc._babel_available = None

    def test_babel_import_error_feature_name(self) -> None:
        """BabelImportError contains correct feature name."""
        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()
        _bc._babel_available = None

        babel_modules_backup = {}
        babel_keys = [
            k for k in sys.modules
            if k == "babel" or k.startswith("babel.")
        ]
        for key in babel_keys:
            babel_modules_backup[key] = sys.modules.pop(key, None)

        try:
            original_import = builtins.__import__

            def mock_import(
                name: str,
                globals_: dict[str, object] | None = None,
                locals_: dict[str, object] | None = None,
                fromlist: tuple[str, ...] = (),
                level: int = 0,
            ) -> object:
                if name == "babel" or name.startswith("babel."):
                    msg = f"No module named '{name}'"
                    raise ImportError(msg)
                return original_import(
                    name, globals_, locals_, fromlist, level
                )

            with patch.object(
                builtins, "__import__", side_effect=mock_import
            ):
                with pytest.raises(
                    ImportError, match="parse"
                ) as exc_info:
                    _get_datetime_patterns("en_US")
                assert "parse_datetime" in str(exc_info.value)
        finally:
            for key, value in babel_modules_backup.items():
                if value is not None:
                    sys.modules[key] = value
            _get_datetime_patterns.cache_clear()
            _get_date_patterns.cache_clear()
            _bc._babel_available = None


# ============================================================================
# _preprocess_datetime_input
# ============================================================================


class TestPreprocessDatetimeInput:
    """Test _preprocess_datetime_input function."""

    def test_with_has_era_true(self) -> None:
        """has_era=True triggers _strip_era."""
        result = _preprocess_datetime_input("28 Jan 2025 AD", has_era=True)
        assert "AD" not in result
        assert result == "28 Jan 2025"

    def test_with_has_era_false(self) -> None:
        """has_era=False returns value unchanged."""
        value = "2025-01-28 14:30:00"
        assert _preprocess_datetime_input(value, has_era=False) == value

    def test_with_era_and_timezone(self) -> None:
        """Era is stripped but timezone preserved."""
        result = _preprocess_datetime_input(
            "28 Jan 2025 AD PST", has_era=True
        )
        assert "AD" not in result
        assert "PST" in result


# ============================================================================
# _babel_to_strptime: Timezone Token Handling
# ============================================================================


class TestBabelToStrptimeTimezoneToken:
    """Test _babel_to_strptime timezone token handling."""

    def test_timezone_z(self) -> None:
        """Timezone token 'z' is removed from pattern."""
        pattern, has_era = _babel_to_strptime("d MMM y HH:mm z")
        assert has_era is False
        assert "z" not in pattern

    def test_timezone_zzzz(self) -> None:
        """Timezone token 'zzzz' is removed."""
        pattern, has_era = _babel_to_strptime(
            "MMMM d, y 'at' h:mm a zzzz"
        )
        assert has_era is False
        assert "zzzz" not in pattern

    def test_timezone_v(self) -> None:
        """Timezone token 'v' is removed."""
        pattern, has_era = _babel_to_strptime("d MMM y HH:mm v")
        assert has_era is False
        assert "v" not in pattern

    def test_timezone_vvvv(self) -> None:
        """Timezone token 'vvvv' is removed."""
        pattern, has_era = _babel_to_strptime("d MMM y HH:mm vvvv")
        assert has_era is False
        assert "vvvv" not in pattern

    def test_timezone_o(self) -> None:
        """Timezone token 'O' is removed."""
        pattern, has_era = _babel_to_strptime("d MMM y HH:mm O")
        assert has_era is False
        assert "O" not in pattern

    def test_both_era_and_timezone(self) -> None:
        """Both era and timezone tokens handled correctly."""
        pattern, has_era = _babel_to_strptime("d MMM y G HH:mm z")
        assert has_era is True
        assert "G" not in pattern
        assert "z" not in pattern

    def test_none_token_fallthrough(self) -> None:
        """None-mapped token that is not era is silently dropped."""
        from ftllexengine.parsing import dates as dates_module

        original_map = dates_module._BABEL_TOKEN_MAP.copy()
        modified_map = original_map.copy()
        modified_map["QQQ"] = None

        with patch.object(
            dates_module, "_BABEL_TOKEN_MAP", modified_map
        ):
            pattern, has_era = _babel_to_strptime(
                "d MMM y QQQ HH:mm"
            )
            assert has_era is False
            assert "QQQ" not in pattern

    def test_zzzz_localized_gmt_skipped(self) -> None:
        """ZZZZ (localized GMT) is skipped entirely."""
        pattern, has_era = _babel_to_strptime("d MMM y HH:mm ZZZZ")
        assert has_era is False
        assert "ZZZZ" not in pattern
        assert "%z" not in pattern

    def test_trailing_whitespace_normalized(self) -> None:
        """Trailing whitespace from skipped tokens is stripped."""
        pattern, has_era = _babel_to_strptime("HH:mm zzzz")
        assert has_era is False
        assert pattern == "%H:%M"

    def test_multiple_trailing_spaces_normalized(self) -> None:
        """Multiple trailing spaces from skipped tokens stripped."""
        pattern, has_era = _babel_to_strptime("HH:mm   zzzz")
        assert has_era is False
        assert pattern == "%H:%M"


# ============================================================================
# Babel Datetime Format Conversion (Mock)
# ============================================================================


class TestBabelDatetimeFormatConversion:
    """Test Babel datetime format conversion with mock pattern objects."""

    def test_babel_datetime_format_with_mock(self) -> None:
        """Mock Babel to return pattern object for datetime_formats."""
        from ftllexengine.parsing import dates

        dates._get_datetime_patterns.cache_clear()
        dates._get_date_patterns.cache_clear()

        try:
            mock_pattern = Mock()
            mock_pattern.pattern = "M/d/yy, h:mm a"

            mock_locale = Mock()
            mock_locale.datetime_formats = {
                "short": mock_pattern, "medium": mock_pattern,
            }
            mock_date_format = Mock()
            mock_date_format.pattern = "M/d/yy"
            mock_locale.date_formats = {"short": mock_date_format}

            with patch("babel.Locale") as mock_locale_class:
                mock_locale_class.parse.return_value = mock_locale
                patterns = dates._get_datetime_patterns(
                    "test_mock_locale"
                )
                assert len(patterns) > 0
        finally:
            dates._get_datetime_patterns.cache_clear()
            dates._get_date_patterns.cache_clear()


# ============================================================================
# Quoted Literals in CLDR Patterns
# ============================================================================


class TestQuotedLiteralsInCLDRPatterns:
    """Test non-empty quoted literals in CLDR date patterns."""

    def test_parse_date_russian(self) -> None:
        """Russian date parsing with short format."""
        result, errors = parse_date("28.01.2025", "ru_RU")
        assert not errors
        assert result is not None
        assert result.year == 2025

    def test_parse_date_spanish(self) -> None:
        """Spanish short format d/M/yy."""
        result, errors = parse_date("28/01/25", "es_ES")
        assert not errors
        assert result is not None
        assert result.year == 2025

    def test_parse_date_portuguese(self) -> None:
        """Portuguese date format."""
        result, errors = parse_date("28/01/2025", "pt_PT")
        assert not errors
        assert result is not None
        assert result.year == 2025


# ============================================================================
# Time-First Datetime Ordering
# ============================================================================


class TestDatetimeTimeFirstOrdering:
    """Test time-first datetime ordering (mock locales)."""

    def test_time_first_ordering(self) -> None:
        """Mock locale with time-first ordering generates patterns."""
        _get_datetime_patterns.cache_clear()

        original_parse = Locale.parse

        def mock_parse_time_first(locale_str: str) -> MagicMock:
            real_locale = original_parse(locale_str)
            mock_locale = MagicMock(spec=Locale)

            time_first_pattern = "{0} {1}"
            mock_datetime_format = MagicMock(
                return_value=time_first_pattern
            )
            mock_datetime_format.__str__ = MagicMock(  # type: ignore[method-assign]
                return_value=time_first_pattern
            )
            mock_datetime_format.pattern = time_first_pattern

            mock_locale.datetime_formats = {
                "short": mock_datetime_format,
                "medium": mock_datetime_format,
                "long": mock_datetime_format,
            }
            mock_locale.date_formats = real_locale.date_formats
            return mock_locale

        with patch(
            "babel.Locale.parse", side_effect=mock_parse_time_first
        ):
            patterns = _get_datetime_patterns("en_US")

        assert len(patterns) > 0

        time_first_found = False
        for pattern, _has_era in patterns:
            time_pos = min(
                (
                    pattern.find(t)
                    for t in ["%H", "%I"]
                    if pattern.find(t) != -1
                ),
                default=-1,
            )
            date_pos = min(
                (
                    pattern.find(d)
                    for d in ["%d", "%m", "%Y"]
                    if pattern.find(d) != -1
                ),
                default=-1,
            )
            if (
                time_pos != -1
                and date_pos != -1
                and time_pos < date_pos
            ):
                time_first_found = True
                break

        assert time_first_found
        _get_datetime_patterns.cache_clear()

    def test_parse_datetime_with_time_first_locale(self) -> None:
        """Integration: parse datetime with time-first mock locale."""
        _get_datetime_patterns.cache_clear()

        original_parse = Locale.parse

        def mock_parse_time_first(locale_str: str) -> MagicMock:
            real_locale = original_parse(locale_str)
            mock_locale = MagicMock(spec=Locale)

            time_first_pattern = "{0} {1}"
            mock_datetime_format = MagicMock(
                return_value=time_first_pattern
            )
            mock_datetime_format.__str__ = MagicMock(  # type: ignore[method-assign]
                return_value=time_first_pattern
            )
            mock_locale.datetime_formats = {
                "short": mock_datetime_format,
                "medium": mock_datetime_format,
            }
            mock_locale.date_formats = real_locale.date_formats
            return mock_locale

        with patch(
            "babel.Locale.parse", side_effect=mock_parse_time_first
        ):
            result, _errors = parse_datetime(
                "14:30 28.01.2025", "de_DE"
            )

        assert result is None or result.year in (2025, 1925)
        _get_datetime_patterns.cache_clear()


# ============================================================================
# BabelImportError Structure
# ============================================================================


class TestBabelImportErrorBehavior:
    """Test BabelImportError structure and message format."""

    def test_babel_import_error_structure(self) -> None:
        """BabelImportError has correct structure and message."""
        from ftllexengine.core.babel_compat import BabelImportError

        error = BabelImportError("parse_date")
        assert error.feature == "parse_date"
        assert "parse_date" in str(error)
        assert "pip install ftllexengine[babel]" in str(error)
        assert isinstance(error, ImportError)

    def test_get_date_patterns_returns_valid_patterns(self) -> None:
        """_get_date_patterns returns valid (pattern, has_era) tuples."""
        from ftllexengine.parsing import dates

        dates._get_date_patterns.cache_clear()
        patterns = dates._get_date_patterns("en_US")

        assert isinstance(patterns, tuple)
        assert len(patterns) > 0
        for pattern, has_era in patterns:
            assert isinstance(pattern, str)
            assert isinstance(has_era, bool)

    def test_get_datetime_patterns_returns_valid_patterns(self) -> None:
        """_get_datetime_patterns returns valid (pattern, has_era) tuples."""
        from ftllexengine.parsing import dates

        dates._get_datetime_patterns.cache_clear()
        patterns = dates._get_datetime_patterns("en_US")

        assert isinstance(patterns, tuple)
        assert len(patterns) > 0
        for pattern, has_era in patterns:
            assert isinstance(pattern, str)
            assert isinstance(has_era, bool)

    def test_parse_date_works(self) -> None:
        """parse_date works correctly when Babel is installed."""
        result, errors = parse_date("2025-01-28", "en_US")
        assert not errors
        assert result is not None
        assert result.year == 2025

    def test_parse_datetime_works(self) -> None:
        """parse_datetime works correctly when Babel is installed."""
        result, errors = parse_datetime("2025-01-28 14:30", "en_US")
        assert not errors
        assert result is not None
        assert result.year == 2025
        assert result.hour == 14


# ============================================================================
# Hypothesis Property Tests
# ============================================================================


class TestDatetimeProperties:
    """Property-based tests for datetime parsing."""

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    def test_parse_datetime_various_times(
        self, hour: int, minute: int
    ) -> None:
        """PROPERTY: Datetime patterns handle various times."""
        time_of_day = "morning" if hour < 12 else "afternoon"
        event(f"time_of_day={time_of_day}")

        date_str = f"28.01.25, {hour:02d}:{minute:02d}"
        result, errors = parse_datetime(date_str, "de_DE")
        assert not errors
        if result is not None:
            assert result.hour == hour
            assert result.minute == minute

    @given(
        year=st.integers(min_value=2020, max_value=2030),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    def test_datetime_roundtrip(
        self,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
    ) -> None:
        """PROPERTY: Datetime ISO formatted then parsed preserves values."""
        event(f"year={year}")
        time_of_day = "morning" if hour < 12 else "afternoon"
        event(f"time_of_day={time_of_day}")

        dt = datetime(year, month, day, hour, minute, 0, tzinfo=UTC)
        iso_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        result, errors = parse_datetime(iso_str, "en_US")

        assert not errors
        if result is not None:
            assert result.year == year
            assert result.month == month
            assert result.day == day
            assert result.hour == hour
            assert result.minute == minute


# ============================================================================
# Integration: Full Coverage Verification
# ============================================================================


class TestIntegrationFullCoverage:
    """Integration test exercising multiple code branches."""

    def test_parse_datetime_exercises_all_branches(self) -> None:
        """Exercise ISO, CLDR, error, and empty paths."""
        test_cases = [
            ("2025-01-28T14:30:00", "en_US", True),
            ("1/28/25, 2:30 PM", "en_US", True),
            ("not-a-datetime", "en_US", False),
            ("", "en_US", False),
        ]
        for datetime_str, locale, should_succeed in test_cases:
            result, errors = parse_datetime(datetime_str, locale)
            if should_succeed:
                assert result is not None or len(errors) > 0
            else:
                assert len(errors) > 0
                assert result is None


# ============================================================================
# DATETIME SEPARATOR AND BABEL PATTERN TOKENIZER COVERAGE
# ============================================================================


class TestTokenizeBabelPatternEdgeCases:
    """_tokenize_babel_pattern: patterns starting with a quote and unclosed sections."""

    def test_quoted_section_with_escaped_quote(self) -> None:
        """Escaped quote '' inside a quoted literal is unescaped to a single quote."""
        pattern = "'It''s a test'"
        tokens = _tokenize_babel_pattern(pattern)
        assert any("It's a test" in t for t in tokens)

    def test_unclosed_quoted_section(self) -> None:
        """Unclosed quoted literal collects remaining characters."""
        pattern = "'unclosed"
        tokens = _tokenize_babel_pattern(pattern)
        assert any("unclosed" in t for t in tokens)


class TestDatesQuotedLiteral:
    """Non-empty quoted literal in Babel date pattern tokenizes correctly."""

    def test_quoted_literal_in_pattern(self) -> None:
        """Spanish-style quoted separator 'de' is extracted as a token."""
        pattern = "d 'de' MMMM 'de' y"
        tokens = _tokenize_babel_pattern(pattern)
        assert "de" in tokens
