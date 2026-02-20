"""Tests for syntax.cursor: Cursor, ParseError, ParseResult, LineOffsetCache.

Validates the immutable cursor pattern for type-safe parsing, line/column
computation, and the LineOffsetCache binary-search infrastructure.
"""

from __future__ import annotations

import pytest

from ftllexengine.syntax.cursor import Cursor, LineOffsetCache, ParseError, ParseResult

# ============================================================================
# CURSOR BASIC TESTS
# ============================================================================


class TestCursorBasic:
    """Test basic cursor functionality."""

    def test_create_cursor(self) -> None:
        """Create cursor at position 0."""
        cursor = Cursor("hello", 0)

        assert cursor.source == "hello"
        assert cursor.pos == 0
        assert not cursor.is_eof

    def test_create_cursor_at_middle(self) -> None:
        """Create cursor at middle of source."""
        cursor = Cursor("hello", 2)

        assert cursor.pos == 2
        assert cursor.current == "l"

    def test_cursor_immutability(self) -> None:
        """Cursor is immutable (frozen dataclass)."""
        cursor = Cursor("hello", 0)

        with pytest.raises(AttributeError):
            cursor.pos = 5  # type: ignore[misc]


# ============================================================================
# EOF DETECTION
# ============================================================================


class TestCursorEOF:
    """Test EOF detection."""

    def test_is_eof_false_at_start(self) -> None:
        """is_eof is False at start of source."""
        cursor = Cursor("hello", 0)

        assert not cursor.is_eof

    def test_is_eof_false_in_middle(self) -> None:
        """is_eof is False in middle of source."""
        cursor = Cursor("hello", 2)

        assert not cursor.is_eof

    def test_is_eof_true_at_end(self) -> None:
        """is_eof is True at end of source."""
        cursor = Cursor("hello", 5)

        assert cursor.is_eof

    def test_is_eof_true_beyond_end(self) -> None:
        """is_eof is True beyond end of source."""
        cursor = Cursor("hello", 10)

        assert cursor.is_eof

    def test_is_eof_true_for_empty_source(self) -> None:
        """is_eof is True for empty source at position 0."""
        cursor = Cursor("", 0)

        assert cursor.is_eof


# ============================================================================
# CURRENT CHARACTER ACCESS
# ============================================================================


class TestCursorCurrent:
    """Test current character access."""

    def test_current_at_start(self) -> None:
        """Get current character at start."""
        cursor = Cursor("hello", 0)

        assert cursor.current == "h"

    def test_current_in_middle(self) -> None:
        """Get current character in middle."""
        cursor = Cursor("hello", 2)

        assert cursor.current == "l"

    def test_current_at_last_char(self) -> None:
        """Get current character at last position."""
        cursor = Cursor("hello", 4)

        assert cursor.current == "o"

    def test_current_raises_eof_error_at_end(self) -> None:
        """Accessing current at EOF raises EOFError."""
        cursor = Cursor("hello", 5)

        with pytest.raises(EOFError, match="Unexpected EOF"):
            _ = cursor.current

    def test_current_raises_eof_error_beyond_end(self) -> None:
        """Accessing current beyond EOF raises EOFError."""
        cursor = Cursor("hello", 10)

        with pytest.raises(EOFError, match="Unexpected EOF"):
            _ = cursor.current

    def test_current_with_unicode(self) -> None:
        """Get current character with Unicode."""
        cursor = Cursor("привет", 0)

        assert cursor.current == "п"

    def test_current_with_emoji(self) -> None:
        """Get current character with emoji."""
        cursor = Cursor("hello 👋 world", 6)

        assert cursor.current == "👋"


# ============================================================================
# PEEK OPERATIONS
# ============================================================================


class TestCursorPeek:
    """Test peek operations."""

    def test_peek_current(self) -> None:
        """Peek at current position (offset 0)."""
        cursor = Cursor("hello", 0)

        assert cursor.peek(0) == "h"

    def test_peek_next(self) -> None:
        """Peek at next position (offset 1)."""
        cursor = Cursor("hello", 0)

        assert cursor.peek(1) == "e"

    def test_peek_multiple_ahead(self) -> None:
        """Peek multiple positions ahead."""
        cursor = Cursor("hello", 0)

        assert cursor.peek(2) == "l"
        assert cursor.peek(3) == "l"
        assert cursor.peek(4) == "o"

    def test_peek_at_eof_returns_none(self) -> None:
        """Peek at EOF returns None."""
        cursor = Cursor("hello", 5)

        assert cursor.peek(0) is None

    def test_peek_beyond_eof_returns_none(self) -> None:
        """Peek beyond EOF returns None."""
        cursor = Cursor("hello", 3)

        assert cursor.peek(5) is None

    def test_peek_does_not_modify_cursor(self) -> None:
        """Peek does not modify cursor position."""
        cursor = Cursor("hello", 0)

        _ = cursor.peek(3)
        assert cursor.pos == 0
        assert cursor.current == "h"


# ============================================================================
# ADVANCE OPERATIONS
# ============================================================================


class TestCursorAdvance:
    """Test cursor advancement."""

    def test_advance_single_position(self) -> None:
        """Advance cursor by 1 position."""
        cursor = Cursor("hello", 0)

        new_cursor = cursor.advance()

        assert new_cursor.pos == 1
        assert new_cursor.current == "e"
        # Original unchanged
        assert cursor.pos == 0

    def test_advance_multiple_positions(self) -> None:
        """Advance cursor by multiple positions."""
        cursor = Cursor("hello", 0)

        new_cursor = cursor.advance(3)

        assert new_cursor.pos == 3
        assert new_cursor.current == "l"

    def test_advance_to_eof(self) -> None:
        """Advance cursor to EOF."""
        cursor = Cursor("hello", 0)

        new_cursor = cursor.advance(5)

        assert new_cursor.pos == 5
        assert new_cursor.is_eof

    def test_advance_beyond_eof_clamps_to_length(self) -> None:
        """Advance beyond EOF clamps to source length."""
        cursor = Cursor("hello", 0)

        new_cursor = cursor.advance(100)

        assert new_cursor.pos == 5
        assert new_cursor.is_eof

    def test_advance_preserves_immutability(self) -> None:
        """Advance creates new cursor, original unchanged."""
        cursor = Cursor("hello", 2)

        new_cursor = cursor.advance()

        assert cursor.pos == 2
        assert new_cursor.pos == 3
        assert cursor is not new_cursor

    def test_advance_zero_positions(self) -> None:
        """Advance by 0 creates new cursor at same position."""
        cursor = Cursor("hello", 2)

        new_cursor = cursor.advance(0)

        assert new_cursor.pos == 2
        assert cursor.source == new_cursor.source


# ============================================================================
# SLICE OPERATIONS
# ============================================================================


class TestCursorSlice:
    """Test cursor slice operations."""

    def test_slice_to_from_start(self) -> None:
        """Slice from start to middle."""
        cursor = Cursor("hello world", 0)

        text = cursor.slice_to(5)

        assert text == "hello"

    def test_slice_to_from_middle(self) -> None:
        """Slice from middle position."""
        cursor = Cursor("hello world", 6)

        text = cursor.slice_to(11)

        assert text == "world"

    def test_slice_to_empty(self) -> None:
        """Slice with same start and end returns empty string."""
        cursor = Cursor("hello", 2)

        text = cursor.slice_to(2)

        assert text == ""

    def test_slice_to_single_char(self) -> None:
        """Slice single character."""
        cursor = Cursor("hello", 1)

        text = cursor.slice_to(2)

        assert text == "e"

    def test_slice_to_entire_source(self) -> None:
        """Slice entire source from position 0."""
        cursor = Cursor("hello", 0)

        text = cursor.slice_to(5)

        assert text == "hello"

    def test_slice_to_with_unicode(self) -> None:
        """Slice with Unicode characters."""
        cursor = Cursor("привет мир", 0)

        text = cursor.slice_to(6)

        assert text == "привет"


# ============================================================================
# LINE AND COLUMN COMPUTATION
# ============================================================================


class TestCursorLineCol:
    """Test line and column computation."""

    def test_compute_line_col_at_start(self) -> None:
        """Compute line:col at start of source."""
        cursor = Cursor("hello", 0)

        line, col = cursor.compute_line_col()

        assert line == 1
        assert col == 1

    def test_compute_line_col_in_first_line(self) -> None:
        """Compute line:col in middle of first line."""
        cursor = Cursor("hello world", 6)

        line, col = cursor.compute_line_col()

        assert line == 1
        assert col == 7

    def test_compute_line_col_at_newline(self) -> None:
        """Compute line:col at newline character."""
        cursor = Cursor("hello\nworld", 5)

        line, col = cursor.compute_line_col()

        assert line == 1
        assert col == 6

    def test_compute_line_col_after_newline(self) -> None:
        """Compute line:col after newline (start of line 2)."""
        cursor = Cursor("hello\nworld", 6)

        line, col = cursor.compute_line_col()

        assert line == 2
        assert col == 1

    def test_compute_line_col_in_second_line(self) -> None:
        """Compute line:col in middle of second line."""
        cursor = Cursor("hello\nworld", 9)

        line, col = cursor.compute_line_col()

        assert line == 2
        assert col == 4

    def test_compute_line_col_multiple_lines(self) -> None:
        """Compute line:col across multiple lines."""
        source = "line1\nline2\nline3\nline4"
        cursor = Cursor(source, 12)  # Start of line3

        line, col = cursor.compute_line_col()

        assert line == 3
        assert col == 1

    def test_compute_line_col_at_eof(self) -> None:
        """Compute line:col at EOF."""
        cursor = Cursor("hello\nworld", 11)

        line, col = cursor.compute_line_col()

        assert line == 2
        assert col == 6

    def test_line_col_property(self) -> None:
        """Test line_col property convenience wrapper."""
        cursor = Cursor("hello\nworld", 9)

        line, col = cursor.compute_line_col()

        assert line == 2
        assert col == 4


# ============================================================================
# PARSE RESULT TESTS
# ============================================================================


class TestParseResult:
    """Test ParseResult container."""

    def test_create_parse_result(self) -> None:
        """Create ParseResult with value and cursor."""
        cursor = Cursor("hello", 0)
        result = ParseResult("h", cursor.advance())

        assert result.value == "h"
        assert result.cursor.pos == 1

    def test_parse_result_immutability(self) -> None:
        """ParseResult is immutable."""
        cursor = Cursor("hello", 0)
        result = ParseResult("test", cursor)

        with pytest.raises(AttributeError):
            result.value = "new"  # type: ignore[misc]

    def test_parse_result_with_complex_value(self) -> None:
        """ParseResult can hold complex types."""
        cursor = Cursor("hello", 3)
        value = {"key": "value", "list": [1, 2, 3]}
        result = ParseResult(value, cursor)

        assert result.value == {"key": "value", "list": [1, 2, 3]}
        assert result.cursor.pos == 3


# ============================================================================
# PARSE ERROR TESTS
# ============================================================================


class TestParseError:
    """Test ParseError functionality."""

    def test_create_parse_error(self) -> None:
        """Create ParseError with message and cursor."""
        cursor = Cursor("hello", 2)
        error = ParseError("Expected '}'", cursor)

        assert error.message == "Expected '}'"
        assert error.cursor.pos == 2
        assert error.expected == ()

    def test_create_parse_error_with_expected(self) -> None:
        """Create ParseError with expected tokens."""
        cursor = Cursor("hello", 2)
        error = ParseError("Unexpected", cursor, expected=("}", "]"))

        assert error.expected == ("}", "]")

    def test_parse_error_immutability(self) -> None:
        """ParseError is immutable."""
        cursor = Cursor("hello", 2)
        error = ParseError("Error", cursor)

        with pytest.raises(AttributeError):
            error.message = "New error"  # type: ignore[misc]

    def test_format_error_simple(self) -> None:
        """Format error without expected tokens."""
        cursor = Cursor("hello", 2)
        error = ParseError("Expected '}'", cursor)

        formatted = error.format_error()

        assert "1:3:" in formatted
        assert "Expected '}'" in formatted

    def test_format_error_with_expected(self) -> None:
        """Format error with expected tokens."""
        cursor = Cursor("hello", 2)
        error = ParseError("Unexpected token", cursor, expected=("}",  "]"))

        formatted = error.format_error()

        assert "1:3:" in formatted
        assert "Unexpected token" in formatted
        assert "expected:" in formatted
        assert "'}'" in formatted
        assert "']'" in formatted

    def test_format_error_multiline_source(self) -> None:
        """Format error with multiline source."""
        source = "line1\nline2\nline3"
        cursor = Cursor(source, 8)  # Middle of line2
        error = ParseError("Error here", cursor)

        formatted = error.format_error()

        assert "2:3:" in formatted

    def test_format_with_context_single_line(self) -> None:
        """Format error with context for single line."""
        cursor = Cursor("hello world", 6)
        error = ParseError("Expected '}'", cursor)

        formatted = error.format_with_context()

        assert "1:7:" in formatted
        assert "hello world" in formatted
        assert "^" in formatted

    def test_format_with_context_multiline(self) -> None:
        """Format error with context showing multiple lines."""
        source = "line1\nline2\nline3\nline4"
        cursor = Cursor(source, 8)  # Middle of line2
        error = ParseError("Error", cursor)

        formatted = error.format_with_context()

        assert "2:3:" in formatted
        assert "line1" in formatted
        assert "line2" in formatted
        assert "line3" in formatted
        assert "^" in formatted

    def test_format_with_context_custom_context_lines(self) -> None:
        """Format error with custom context line count."""
        source = "line1\nline2\nline3\nline4\nline5"
        cursor = Cursor(source, 12)  # Start of line3
        error = ParseError("Error", cursor)

        formatted = error.format_with_context(context_lines=1)

        assert "line2" in formatted
        assert "line3" in formatted
        assert "line4" in formatted

    def test_format_with_context_at_start(self) -> None:
        """Format error with context at start of file."""
        source = "line1\nline2\nline3"
        cursor = Cursor(source, 0)
        error = ParseError("Error at start", cursor)

        formatted = error.format_with_context()

        assert "1:1:" in formatted
        assert "line1" in formatted
        assert "^" in formatted

    def test_format_with_context_at_end(self) -> None:
        """Format error with context at end of file."""
        source = "line1\nline2\nline3"
        cursor = Cursor(source, 17)  # End of line3
        error = ParseError("Error at end", cursor)

        formatted = error.format_with_context()

        assert "line3" in formatted
        assert "^" in formatted


# ============================================================================
# EDGE CASES
# ============================================================================


class TestCursorEdgeCases:
    """Test cursor edge cases."""

    def test_empty_source(self) -> None:
        """Handle empty source string."""
        cursor = Cursor("", 0)

        assert cursor.is_eof
        assert cursor.source == ""

    def test_single_character_source(self) -> None:
        """Handle single character source."""
        cursor = Cursor("x", 0)

        assert cursor.current == "x"
        assert not cursor.is_eof

    def test_cursor_with_only_newlines(self) -> None:
        """Handle source with only newlines."""
        cursor = Cursor("\n\n\n", 0)

        assert cursor.current == "\n"
        line, _ = cursor.compute_line_col()
        assert line == 1

    def test_cursor_with_tabs(self) -> None:
        """Handle source with tabs."""
        cursor = Cursor("hello\tworld", 5)

        assert cursor.current == "\t"

    def test_cursor_with_mixed_whitespace(self) -> None:
        """Handle source with mixed whitespace."""
        source = "  \t\n  \t\n"
        cursor = Cursor(source, 4)

        line, col = cursor.compute_line_col()
        assert line == 2
        assert col == 1


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestCursorIntegration:
    """Test cursor in realistic parsing scenarios."""

    def test_parse_identifier_pattern(self) -> None:
        """Simulate parsing an identifier."""
        cursor = Cursor("hello_world = value", 0)
        start_pos = cursor.pos

        # Advance while identifier characters
        while (not cursor.is_eof and cursor.current.isalnum()) or cursor.current == "_":
            cursor = cursor.advance()

        identifier = Cursor("hello_world = value", start_pos).slice_to(cursor.pos)

        assert identifier == "hello_world"
        assert cursor.current == " "

    def test_parse_quoted_string_pattern(self) -> None:
        """Simulate parsing a quoted string."""
        cursor = Cursor('"hello world"', 0)

        # Skip opening quote
        cursor = cursor.advance()
        start_pos = cursor.pos

        # Advance until closing quote
        while not cursor.is_eof and cursor.current != '"':
            cursor = cursor.advance()

        content = Cursor('"hello world"', start_pos).slice_to(cursor.pos)

        assert content == "hello world"

    def test_skip_whitespace_pattern(self) -> None:
        """Simulate skipping whitespace."""
        cursor = Cursor("   hello", 0)

        # Skip whitespace
        while not cursor.is_eof and cursor.current in " \t\n":
            cursor = cursor.advance()

        assert cursor.current == "h"
        assert cursor.pos == 3

    def test_lookahead_pattern(self) -> None:
        """Simulate lookahead for parser decision."""
        cursor = Cursor("hello = value", 5)

        # Check if next char is '='
        if cursor.peek(1) == "=":
            cursor = cursor.advance(2)  # Skip ' ='

        assert cursor.current == " "
        assert cursor.pos == 7

    def test_error_reporting_pattern(self) -> None:
        """Simulate error reporting with line:col."""
        source = "line1\nline2 { $var\nline3"
        cursor = Cursor(source, 18)  # After $var

        error = ParseError("Expected '}'", cursor, expected=("}", ))
        formatted = error.format_with_context()

        assert "2:13:" in formatted
        assert "line2 { $var" in formatted
        assert "^" in formatted


# ============================================================================
# LINE OFFSET CACHE TESTS (from test_cursor_infrastructure.py)
# ============================================================================


class TestLineOffsetCacheInit:
    """LineOffsetCache builds the offset table correctly during initialization."""

    def test_init_empty_source(self) -> None:
        """Empty source produces a single-element offset table [(0,)]."""
        cache = LineOffsetCache("")

        assert cache._source_len == 0  # pylint: disable=protected-access
        assert cache._offsets == (0,)  # pylint: disable=protected-access

    def test_init_single_line(self) -> None:
        """Single-line source with no newlines produces offset table [(0,)]."""
        cache = LineOffsetCache("hello world")

        assert cache._source_len == 11  # pylint: disable=protected-access
        assert cache._offsets == (0,)  # pylint: disable=protected-access

    def test_init_multiple_lines(self) -> None:
        """Three-line source produces offsets at the start of each line."""
        cache = LineOffsetCache("line1\nline2\nline3")

        assert cache._source_len == 17  # pylint: disable=protected-access
        assert cache._offsets == (0, 6, 12)  # pylint: disable=protected-access

    def test_init_trailing_newline(self) -> None:
        """Trailing newline produces a third entry for the (empty) final line."""
        cache = LineOffsetCache("line1\nline2\n")

        assert cache._source_len == 12  # pylint: disable=protected-access
        assert cache._offsets == (0, 6, 12)  # pylint: disable=protected-access

    def test_init_consecutive_newlines(self) -> None:
        """Consecutive newlines create entries for each empty line."""
        cache = LineOffsetCache("a\n\nb")

        assert cache._source_len == 4  # pylint: disable=protected-access
        assert cache._offsets == (0, 2, 3)  # pylint: disable=protected-access

    def test_init_only_newlines(self) -> None:
        """Source with only newlines creates an entry after each one."""
        cache = LineOffsetCache("\n\n\n")

        assert cache._source_len == 3  # pylint: disable=protected-access
        assert cache._offsets == (0, 1, 2, 3)  # pylint: disable=protected-access


class TestLineOffsetCacheGetLineCol:
    """LineOffsetCache.get_line_col maps byte offsets to (line, column) pairs."""

    def test_get_line_col_first_position(self) -> None:
        """Position 0 maps to line 1, column 1."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(0)

        assert line == 1
        assert col == 1

    def test_get_line_col_middle_of_first_line(self) -> None:
        """Position 2 on first line maps to line 1, column 3."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(2)

        assert line == 1
        assert col == 3

    def test_get_line_col_start_of_second_line(self) -> None:
        """First position of second line maps to line 2, column 1."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(6)

        assert line == 2
        assert col == 1

    def test_get_line_col_middle_of_second_line(self) -> None:
        """Middle of second line maps to the correct column."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(8)

        assert line == 2
        assert col == 3

    def test_get_line_col_at_newline(self) -> None:
        """Position at the newline character maps to the end of that line."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(5)

        assert line == 1
        assert col == 6

    def test_get_line_col_at_end(self) -> None:
        """Position at source length maps to the final line end position."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(11)

        assert line == 2
        assert col == 6

    def test_get_line_col_negative_position(self) -> None:
        """Negative position is clamped to 0 (line 1, column 1)."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(-5)

        assert line == 1
        assert col == 1

    def test_get_line_col_position_beyond_source(self) -> None:
        """Position beyond source length is clamped to source length."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(100)

        assert line == 2
        assert col == 6

    def test_get_line_col_empty_source(self) -> None:
        """Position 0 in empty source maps to line 1, column 1."""
        cache = LineOffsetCache("")

        line, col = cache.get_line_col(0)

        assert line == 1
        assert col == 1

    def test_get_line_col_third_line(self) -> None:
        """Position at the start of the third line maps correctly."""
        cache = LineOffsetCache("a\nb\nc\nd")

        line, col = cache.get_line_col(4)

        assert line == 3
        assert col == 1

    def test_get_line_col_many_lines_binary_search(self) -> None:
        """Binary search finds correct line across many lines."""
        source = "\n".join(f"line{i}" for i in range(10))
        cache = LineOffsetCache(source)

        assert cache.get_line_col(0) == (1, 1)
        assert cache.get_line_col(24) == (5, 1)
        assert cache.get_line_col(42) == (8, 1)
        assert cache.get_line_col(54) == (10, 1)

    def test_get_line_col_long_lines(self) -> None:
        """Long lines with many characters compute column correctly."""
        cache = LineOffsetCache("a" * 100 + "\n" + "b" * 50)

        line, col = cache.get_line_col(110)

        assert line == 2
        assert col == 10

    def test_get_line_col_position_exactly_at_source_len(self) -> None:
        """Position equal to source length maps to just past the last character."""
        source = "abc"
        cache = LineOffsetCache(source)

        line, col = cache.get_line_col(3)

        assert line == 1
        assert col == 4

    def test_get_line_col_consecutive_calls(self) -> None:
        """Multiple consecutive calls all return correct values."""
        cache = LineOffsetCache("hello\nworld\n!")

        assert cache.get_line_col(0) == (1, 1)
        assert cache.get_line_col(5) == (1, 6)
        assert cache.get_line_col(6) == (2, 1)
        assert cache.get_line_col(11) == (2, 6)
        assert cache.get_line_col(12) == (3, 1)


class TestCursorSkipLineEnd:
    """Cursor.skip_line_end recognizes LF as the only line-ending character."""

    def test_skip_line_end_at_regular_char(self) -> None:
        """At a regular character, skip_line_end returns self unchanged."""
        cursor = Cursor("hello\nworld", 0)

        result = cursor.skip_line_end()

        assert result.pos == 0
        assert result is cursor

    def test_skip_line_end_at_middle_char(self) -> None:
        """At a middle character, skip_line_end returns self unchanged."""
        cursor = Cursor("hello\nworld", 2)

        result = cursor.skip_line_end()

        assert result.pos == 2
        assert result is cursor

    def test_skip_line_end_at_lf(self) -> None:
        """At LF, skip_line_end advances past the newline."""
        cursor = Cursor("hello\nworld", 5)

        result = cursor.skip_line_end()

        assert result.pos == 6

    def test_skip_line_end_cr_not_recognized(self) -> None:
        """CR alone is not a recognized line ending; cursor stays put.

        Cursor expects LF-normalized input. CR must be converted before
        creating a Cursor. FluentParserV1.parse() handles normalization.
        """
        cursor = Cursor("hello\rworld", 5)

        result = cursor.skip_line_end()

        assert result.pos == 5
        assert result is cursor

    def test_skip_line_end_at_crlf_cr_position(self) -> None:
        """At CR within CRLF, skip_line_end does not advance (CR not recognized).

        For proper handling, normalize input to LF before creating a Cursor.
        """
        cursor = Cursor("hello\r\nworld", 5)

        result = cursor.skip_line_end()

        assert result.pos == 5
        assert result is cursor

    def test_skip_line_end_at_crlf_lf_position(self) -> None:
        """At LF within CRLF, skip_line_end advances past the LF."""
        cursor = Cursor("hello\r\nworld", 6)

        result = cursor.skip_line_end()

        assert result.pos == 7

    def test_skip_line_end_at_eof(self) -> None:
        """At EOF, skip_line_end returns self unchanged."""
        cursor = Cursor("hello", 5)

        result = cursor.skip_line_end()

        assert result.pos == 5
        assert result is cursor
