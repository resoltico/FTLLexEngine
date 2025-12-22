"""Tests for date and datetime parsing functions.

v0.8.0: Updated for new tuple return type API.
- parse_date() returns tuple[date | None, list[FluentParseError]]
- parse_datetime() returns tuple[datetime | None, list[FluentParseError]]
- Removed strict parameter - functions never raise, errors in list

Validates parse_date() and parse_datetime() across multiple locales.
"""

from datetime import UTC, date, datetime

from ftllexengine.parsing import parse_date, parse_datetime


class TestParseDate:
    """Test parse_date() function."""

    def test_parse_date_us_format(self) -> None:
        """Parse US date format (M/d/yy - CLDR short format)."""
        # v0.8.0: Uses CLDR short format (2-digit year)
        result, errors = parse_date("1/28/25", "en_US")
        assert not errors
        assert result == date(2025, 1, 28)

    def test_parse_date_european_format(self) -> None:
        """Parse European date format (d.M.yy - CLDR short format)."""
        # v0.8.0: Uses CLDR short format (2-digit year)
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
        """Invalid input returns error in list (v0.8.0 - no exceptions)."""
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


class TestParseDatetime:
    """Test parse_datetime() function."""

    def test_parse_datetime_us_format(self) -> None:
        """Parse US datetime format (M/d/yy + time - CLDR)."""
        # v0.27.0: Uses CLDR dateTimeFormat with locale-specific separator
        # en_US: "{1}, {0}" -> "date, time" (comma + space separator)
        result, errors = parse_datetime("1/28/25, 14:30", "en_US")
        assert not errors
        assert result == datetime(2025, 1, 28, 14, 30)

    def test_parse_datetime_european_format(self) -> None:
        """Parse European datetime format (d.M.yy + time - CLDR)."""
        # v0.8.0: Uses CLDR short format (2-digit year) + 24-hour time
        result, errors = parse_datetime("28.1.25 14:30", "lv_LV")
        assert not errors
        assert result == datetime(2025, 1, 28, 14, 30)

    def test_parse_datetime_with_timezone(self) -> None:
        """Parse datetime and apply timezone."""
        result, errors = parse_datetime("2025-01-28 14:30", "en_US", tzinfo=UTC)
        assert not errors
        assert result == datetime(2025, 1, 28, 14, 30, tzinfo=UTC)

    def test_parse_datetime_invalid_returns_error(self) -> None:
        """Invalid input returns error in list (v0.8.0 - no exceptions)."""
        result, errors = parse_datetime("invalid", "en_US")
        assert len(errors) > 0
        assert result is None
        assert errors[0].parse_type == "datetime"

    def test_parse_datetime_empty_returns_error(self) -> None:
        """Empty input returns error in list."""
        result, errors = parse_datetime("", "en_US")
        assert len(errors) > 0
        assert result is None


class TestBabelPatternTokenizer:
    """Test CLDR pattern tokenizer quote handling.

    Regression tests for LOGIC-DATE-012: The tokenizer must correctly handle
    CLDR quote escaping rules:
    - Single quotes delimit literal text: 'at' produces "at"
    - Two consecutive single quotes '' produce a literal single quote
    - '' inside quoted text also produces a literal single quote
    """

    def test_simple_quoted_literal(self) -> None:
        """Simple quoted literal is extracted as single token."""
        # Test internal function directly
        from ftllexengine.parsing.dates import _tokenize_babel_pattern

        tokens = _tokenize_babel_pattern("h 'at' a")
        # Should be: ['h', ' ', 'at', ' ', 'a']
        assert "at" in tokens

    def test_escaped_quote_outside_quoted_section(self) -> None:
        """Two quotes '' outside a quoted section produce literal quote."""
        from ftllexengine.parsing.dates import _tokenize_babel_pattern

        tokens = _tokenize_babel_pattern("h''mm")
        # '' -> single quote character
        assert "'" in tokens

    def test_escaped_quote_inside_quoted_section(self) -> None:
        """Two quotes '' inside quoted text produce literal quote.

        Pattern: h 'o''clock' a
        The '' inside the quoted section should produce a literal single quote,
        resulting in the literal "o'clock".
        """
        from ftllexengine.parsing.dates import _tokenize_babel_pattern

        tokens = _tokenize_babel_pattern("h 'o''clock' a")
        # The quoted literal should be "o'clock" (with embedded quote)
        assert "o'clock" in tokens

    def test_irish_locale_pattern(self) -> None:
        """Irish locale uses patterns with escaped quotes.

        Irish date format might use patterns like "d MMMM 'de' yyyy".
        """
        from ftllexengine.parsing.dates import _tokenize_babel_pattern

        tokens = _tokenize_babel_pattern("d MMMM 'de' yyyy")
        assert "de" in tokens  # Quoted literal
        assert "d" in tokens  # Pattern letter
        assert "yyyy" in tokens  # Pattern letters

    def test_standard_date_pattern_unchanged(self) -> None:
        """Standard patterns without quotes work correctly."""
        from ftllexengine.parsing.dates import _tokenize_babel_pattern

        tokens = _tokenize_babel_pattern("yyyy-MM-dd")
        assert tokens == ["yyyy", "-", "MM", "-", "dd"]

    def test_latvian_pattern(self) -> None:
        """Latvian date pattern d.MM.yyyy."""
        from ftllexengine.parsing.dates import _tokenize_babel_pattern

        tokens = _tokenize_babel_pattern("d.MM.yyyy")
        assert tokens == ["d", ".", "MM", ".", "yyyy"]
