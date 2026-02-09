"""Comprehensive property-based tests for syntax.cursor module.

Tests immutable cursor infrastructure for type-safe parsing.

"""

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.syntax.cursor import Cursor, ParseError, ParseResult


class TestCursorImmutability:
    """Property-based tests for Cursor immutability."""

    def test_cursor_frozen(self) -> None:
        """Property: Cursor instances are immutable (frozen)."""
        cursor = Cursor(source="hello", pos=0)

        with pytest.raises((AttributeError, TypeError)):
            cursor.pos = 1  # type: ignore[misc]

    @given(st.text(), st.integers(min_value=0, max_value=1000))
    def test_cursor_construction(self, source: str, pos: int) -> None:
        """Property: Cursor can be constructed with any valid source and position."""
        event(f"input_len={len(source)}")
        # Clamp position to valid range
        pos = min(pos, len(source))
        cursor = Cursor(source=source, pos=pos)
        assert cursor.source == source
        assert cursor.pos == pos


class TestCursorEOFProperty:
    """Property-based tests for Cursor.is_eof property."""

    def test_is_eof_at_start_of_nonempty_string(self) -> None:
        """Verify is_eof is False at start of non-empty string."""
        cursor = Cursor(source="hello", pos=0)
        assert cursor.is_eof is False

    def test_is_eof_at_end_of_string(self) -> None:
        """Verify is_eof is True at end of string."""
        cursor = Cursor(source="hello", pos=5)
        assert cursor.is_eof is True

    def test_is_eof_beyond_end_of_string(self) -> None:
        """Verify is_eof is True beyond end of string."""
        cursor = Cursor(source="hello", pos=10)
        assert cursor.is_eof is True

    def test_is_eof_empty_string(self) -> None:
        """Verify is_eof is True for empty string at position 0."""
        cursor = Cursor(source="", pos=0)
        assert cursor.is_eof is True

    @given(st.text(min_size=1))
    def test_is_eof_middle_of_string(self, source: str) -> None:
        """Property: is_eof is False in middle of string."""
        event(f"input_len={len(source)}")
        mid_pos = len(source) // 2
        cursor = Cursor(source=source, pos=mid_pos)
        if mid_pos < len(source):
            assert cursor.is_eof is False


class TestCursorCurrentProperty:
    """Property-based tests for Cursor.current property."""

    def test_current_at_start(self) -> None:
        """Verify current returns first character at position 0."""
        cursor = Cursor(source="hello", pos=0)
        assert cursor.current == "h"

    def test_current_in_middle(self) -> None:
        """Verify current returns character at current position."""
        cursor = Cursor(source="hello", pos=2)
        assert cursor.current == "l"

    def test_current_raises_at_eof(self) -> None:
        """Verify current raises EOFError at EOF."""
        cursor = Cursor(source="hello", pos=5)
        with pytest.raises(EOFError, match="EOF"):
            _ = cursor.current

    def test_current_raises_beyond_eof(self) -> None:
        """Verify current raises EOFError beyond EOF."""
        cursor = Cursor(source="hello", pos=10)
        with pytest.raises(EOFError, match="EOF"):
            _ = cursor.current

    @given(
        st.text(min_size=1).flatmap(
            lambda s: st.tuples(st.just(s), st.integers(min_value=0, max_value=len(s) - 1))
        )
    )
    def test_current_returns_correct_character(self, source_pos: tuple[str, int]) -> None:
        """Property: current returns character at position if valid."""
        source, pos = source_pos
        event(f"input_len={len(source)}")
        event(f"offset={pos}")
        cursor = Cursor(source=source, pos=pos)
        assert cursor.current == source[pos]


class TestCursorPeekMethod:
    """Property-based tests for Cursor.peek() method."""

    def test_peek_at_current_position(self) -> None:
        """Verify peek(0) returns current character."""
        cursor = Cursor(source="hello", pos=0)
        assert cursor.peek(0) == "h"

    def test_peek_ahead_one(self) -> None:
        """Verify peek(1) returns next character."""
        cursor = Cursor(source="hello", pos=0)
        assert cursor.peek(1) == "e"

    def test_peek_beyond_eof_returns_none(self) -> None:
        """Verify peek() returns None when peeking beyond EOF."""
        cursor = Cursor(source="hello", pos=4)
        assert cursor.peek(1) is None

    def test_peek_at_eof_returns_none(self) -> None:
        """Verify peek() returns None at EOF."""
        cursor = Cursor(source="hello", pos=5)
        assert cursor.peek(0) is None

    @given(st.text(min_size=2), st.integers(min_value=0, max_value=10))
    def test_peek_with_various_offsets(self, source: str, offset: int) -> None:
        """Property: peek(offset) returns correct character or None."""
        event(f"input_len={len(source)}")
        event(f"offset={offset}")
        cursor = Cursor(source=source, pos=0)
        result = cursor.peek(offset)

        in_bounds = offset < len(source)
        event(f"valid={in_bounds}")
        if in_bounds:
            assert result == source[offset]
        else:
            assert result is None


class TestCursorAdvanceMethod:
    """Property-based tests for Cursor.advance() method."""

    def test_advance_single_position(self) -> None:
        """Verify advance() moves cursor by 1 position."""
        cursor = Cursor(source="hello", pos=0)
        new_cursor = cursor.advance()
        assert new_cursor.pos == 1
        assert cursor.pos == 0  # Original unchanged

    def test_advance_multiple_positions(self) -> None:
        """Verify advance(count) moves cursor by count positions."""
        cursor = Cursor(source="hello", pos=0)
        new_cursor = cursor.advance(3)
        assert new_cursor.pos == 3

    def test_advance_clamped_at_eof(self) -> None:
        """Verify advance() clamps position at EOF."""
        cursor = Cursor(source="hello", pos=3)
        new_cursor = cursor.advance(10)
        assert new_cursor.pos == 5  # Clamped to len(source)

    def test_advance_from_eof_stays_at_eof(self) -> None:
        """Verify advance() from EOF stays at EOF."""
        cursor = Cursor(source="hello", pos=5)
        new_cursor = cursor.advance()
        assert new_cursor.pos == 5

    @given(
        st.text(),
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=1, max_value=10),
    )
    def test_advance_returns_new_cursor(self, source: str, pos: int, count: int) -> None:
        """Property: advance() returns new cursor, original unchanged."""
        event(f"input_len={len(source)}")
        event(f"offset={pos}")
        pos = min(pos, len(source))
        cursor = Cursor(source=source, pos=pos)
        new_cursor = cursor.advance(count)

        # Original unchanged
        assert cursor.pos == pos
        # New cursor advanced (clamped at len(source))
        expected_pos = min(pos + count, len(source))
        assert new_cursor.pos == expected_pos


class TestCursorSliceToMethod:
    """Property-based tests for Cursor.slice_to() method."""

    def test_slice_to_simple_range(self) -> None:
        """Verify slice_to() extracts substring."""
        cursor = Cursor(source="hello world", pos=0)
        text = cursor.slice_to(5)
        assert text == "hello"

    def test_slice_to_from_middle(self) -> None:
        """Verify slice_to() works from middle position."""
        cursor = Cursor(source="hello world", pos=6)
        text = cursor.slice_to(11)
        assert text == "world"

    def test_slice_to_empty_range(self) -> None:
        """Verify slice_to() returns empty string for empty range."""
        cursor = Cursor(source="hello", pos=2)
        text = cursor.slice_to(2)
        assert text == ""

    @given(st.text(min_size=1))
    def test_slice_to_full_string(self, source: str) -> None:
        """Property: slice_to(len(source)) from pos=0 returns full string."""
        event(f"input_len={len(source)}")
        cursor = Cursor(source=source, pos=0)
        text = cursor.slice_to(len(source))
        assert text == source


class TestCursorSkipSpacesMethod:
    """Property-based tests for Cursor.skip_spaces() method."""

    def test_skip_spaces_no_spaces(self) -> None:
        """Verify skip_spaces() returns same cursor when no spaces."""
        cursor = Cursor(source="hello", pos=0)
        new_cursor = cursor.skip_spaces()
        assert new_cursor.pos == 0

    def test_skip_spaces_leading_spaces(self) -> None:
        """Verify skip_spaces() skips leading spaces."""
        cursor = Cursor(source="   hello", pos=0)
        new_cursor = cursor.skip_spaces()
        assert new_cursor.pos == 3
        assert new_cursor.current == "h"

    def test_skip_spaces_all_spaces(self) -> None:
        """Verify skip_spaces() handles all-space string."""
        cursor = Cursor(source="     ", pos=0)
        new_cursor = cursor.skip_spaces()
        assert new_cursor.is_eof is True

    def test_skip_spaces_only_space_not_tab(self) -> None:
        """Verify skip_spaces() only skips space (U+0020), not tab."""
        cursor = Cursor(source="  \thello", pos=0)
        new_cursor = cursor.skip_spaces()
        assert new_cursor.pos == 2
        assert new_cursor.current == "\t"

    def test_skip_spaces_not_newline(self) -> None:
        """Verify skip_spaces() does not skip newlines."""
        cursor = Cursor(source="  \nhello", pos=0)
        new_cursor = cursor.skip_spaces()
        assert new_cursor.pos == 2
        assert new_cursor.current == "\n"


class TestCursorSkipWhitespaceMethod:
    """Property-based tests for Cursor.skip_whitespace() method."""

    def test_skip_whitespace_no_whitespace(self) -> None:
        """Verify skip_whitespace() returns same cursor when no whitespace."""
        cursor = Cursor(source="hello", pos=0)
        new_cursor = cursor.skip_whitespace()
        assert new_cursor.pos == 0

    def test_skip_whitespace_mixed_whitespace(self) -> None:
        """Verify skip_whitespace() skips space and newline.

        Note: CR is normalized to LF at parser entry, so skip_whitespace
        only needs to handle space and LF.
        """
        cursor = Cursor(source="  \n  hello", pos=0)
        new_cursor = cursor.skip_whitespace()
        assert new_cursor.pos == 5
        assert new_cursor.current == "h"

    def test_skip_whitespace_all_whitespace(self) -> None:
        """Verify skip_whitespace() handles all-whitespace string."""
        cursor = Cursor(source=" \n ", pos=0)
        new_cursor = cursor.skip_whitespace()
        assert new_cursor.is_eof is True

    def test_skip_whitespace_not_tab(self) -> None:
        """Verify skip_whitespace() does not skip tab."""
        cursor = Cursor(source=" \n\thello", pos=0)
        new_cursor = cursor.skip_whitespace()
        assert new_cursor.pos == 2
        assert new_cursor.current == "\t"


class TestCursorExpectMethod:
    """Property-based tests for Cursor.expect() method."""

    def test_expect_match(self) -> None:
        """Verify expect() returns new cursor when character matches."""
        cursor = Cursor(source="hello", pos=0)
        new_cursor = cursor.expect("h")
        assert new_cursor is not None
        assert new_cursor.pos == 1

    def test_expect_no_match(self) -> None:
        """Verify expect() returns None when character does not match."""
        cursor = Cursor(source="hello", pos=0)
        result = cursor.expect("x")
        assert result is None

    def test_expect_at_eof(self) -> None:
        """Verify expect() returns None at EOF."""
        cursor = Cursor(source="hello", pos=5)
        result = cursor.expect("h")
        assert result is None

    @given(st.text(min_size=1), st.characters())
    def test_expect_various_characters(self, source: str, char: str) -> None:
        """Property: expect() behavior depends on current character."""
        event(f"input_len={len(source)}")
        cursor = Cursor(source=source, pos=0)
        result = cursor.expect(char)

        matched = source[0] == char
        event(f"valid={matched}")
        if matched:
            assert result is not None
            assert result.pos == 1
        else:
            assert result is None


class TestCursorComputeLineColMethod:
    """Property-based tests for Cursor.compute_line_col() method."""

    def test_compute_line_col_first_line_first_col(self) -> None:
        """Verify compute_line_col() returns (1, 1) at position 0."""
        cursor = Cursor(source="hello", pos=0)
        line, col = cursor.compute_line_col()
        assert line == 1
        assert col == 1

    def test_compute_line_col_first_line_later_col(self) -> None:
        """Verify compute_line_col() returns correct column on first line."""
        cursor = Cursor(source="hello", pos=2)
        line, col = cursor.compute_line_col()
        assert line == 1
        assert col == 3

    def test_compute_line_col_second_line(self) -> None:
        """Verify compute_line_col() returns (2, 1) at start of second line."""
        cursor = Cursor(source="line1\nline2", pos=6)
        line, col = cursor.compute_line_col()
        assert line == 2
        assert col == 1

    def test_compute_line_col_second_line_middle(self) -> None:
        """Verify compute_line_col() returns correct position on second line."""
        cursor = Cursor(source="line1\nline2", pos=8)
        line, col = cursor.compute_line_col()
        assert line == 2
        assert col == 3

    def test_compute_line_col_multiple_lines(self) -> None:
        """Verify compute_line_col() handles multiple newlines."""
        cursor = Cursor(source="a\nb\nc\nd", pos=6)  # Position at 'd'
        line, col = cursor.compute_line_col()
        assert line == 4
        assert col == 1


class TestParseResultDataclass:
    """Property-based tests for ParseResult dataclass."""

    def test_parse_result_frozen(self) -> None:
        """Property: ParseResult instances are immutable (frozen)."""
        cursor = Cursor(source="test", pos=0)
        result: ParseResult[str] = ParseResult(value="parsed", cursor=cursor)

        with pytest.raises((AttributeError, TypeError)):
            result.value = "changed"  # type: ignore[misc]

    @given(st.text(), st.text(), st.integers(min_value=0, max_value=100))
    def test_parse_result_construction_string(
        self, value: str, source: str, pos: int
    ) -> None:
        """Property: ParseResult can be constructed with string values."""
        event(f"input_len={len(source)}")
        event(f"offset={pos}")
        pos = min(pos, len(source))
        cursor = Cursor(source=source, pos=pos)
        result: ParseResult[str] = ParseResult(value=value, cursor=cursor)
        assert result.value == value
        assert result.cursor is cursor

    @given(st.integers())
    def test_parse_result_construction_int(self, value: int) -> None:
        """Property: ParseResult can be constructed with int values."""
        event(f"value={value}")
        cursor = Cursor(source="test", pos=0)
        result: ParseResult[int] = ParseResult(value=value, cursor=cursor)
        assert result.value == value

    def test_parse_result_generic_type(self) -> None:
        """Verify ParseResult works with various types."""
        cursor = Cursor(source="test", pos=0)

        # String type
        str_result: ParseResult[str] = ParseResult(value="hello", cursor=cursor)
        assert str_result.value == "hello"

        # List type
        list_result: ParseResult[list[int]] = ParseResult(value=[1, 2, 3], cursor=cursor)
        assert list_result.value == [1, 2, 3]

        # Tuple type
        tuple_result: ParseResult[tuple[str, int]] = ParseResult(
            value=("test", 42), cursor=cursor
        )
        assert tuple_result.value == ("test", 42)


class TestParseErrorDataclass:
    """Property-based tests for ParseError dataclass."""

    def test_parse_error_frozen(self) -> None:
        """Property: ParseError instances are immutable (frozen)."""
        cursor = Cursor(source="test", pos=0)
        error = ParseError(message="error", cursor=cursor)

        with pytest.raises((AttributeError, TypeError)):
            error.message = "changed"  # type: ignore[misc]

    @given(st.text(), st.text())
    def test_parse_error_construction_minimal(self, message: str, source: str) -> None:
        """Property: ParseError can be constructed with message and cursor only."""
        event(f"input_len={len(source)}")
        cursor = Cursor(source=source, pos=0)
        error = ParseError(message=message, cursor=cursor)
        assert error.message == message
        assert error.cursor is cursor
        assert error.expected == ()

    def test_parse_error_construction_with_expected(self) -> None:
        """Verify ParseError can be constructed with expected tokens."""
        cursor = Cursor(source="test", pos=0)
        error = ParseError(message="error", cursor=cursor, expected=("}", "]"))
        assert error.expected == ("}", "]")


class TestParseErrorFormatError:
    """Property-based tests for ParseError.format_error() method."""

    def test_format_error_simple(self) -> None:
        """Verify format_error() returns formatted error string."""
        cursor = Cursor(source="hello", pos=2)
        error = ParseError(message="Test error", cursor=cursor)
        formatted = error.format_error()
        assert "1:3:" in formatted
        assert "Test error" in formatted

    def test_format_error_with_expected(self) -> None:
        """Verify format_error() includes expected tokens."""
        cursor = Cursor(source="hello", pos=0)
        error = ParseError(message="Unexpected", cursor=cursor, expected=("}", "]"))
        formatted = error.format_error()
        assert "expected:" in formatted
        assert "'}'" in formatted
        assert "']'" in formatted

    def test_format_error_multiline_source(self) -> None:
        """Verify format_error() shows correct line number for multiline source."""
        cursor = Cursor(source="line1\nline2\nline3", pos=6)  # Start of line2
        error = ParseError(message="Error on line 2", cursor=cursor)
        formatted = error.format_error()
        assert "2:1:" in formatted


class TestParseErrorFormatWithContext:
    """Property-based tests for ParseError.format_with_context() method."""

    def test_format_with_context_simple(self) -> None:
        """Verify format_with_context() shows source context."""
        cursor = Cursor(source="hello world", pos=6)
        error = ParseError(message="Test error", cursor=cursor)
        formatted = error.format_with_context()

        assert "1:7: Test error" in formatted
        assert "hello world" in formatted
        assert "^" in formatted  # Pointer

    def test_format_with_context_multiline(self) -> None:
        """Verify format_with_context() shows multiple lines."""
        source = "line1\nline2\nline3"
        cursor = Cursor(source=source, pos=6)  # Start of line2
        error = ParseError(message="Error", cursor=cursor)
        formatted = error.format_with_context()

        assert "line1" in formatted
        assert "line2" in formatted
        assert "line3" in formatted
        assert "^" in formatted

    def test_format_with_context_custom_context_lines(self) -> None:
        """Verify format_with_context() respects context_lines parameter."""
        source = "line1\nline2\nline3\nline4\nline5"
        cursor = Cursor(source=source, pos=12)  # Line 3
        error = ParseError(message="Error", cursor=cursor)

        # With context_lines=1, should show lines 2-4
        formatted = error.format_with_context(context_lines=1)
        assert "line2" in formatted
        assert "line3" in formatted
        assert "line4" in formatted

    def test_format_with_context_pointer_alignment(self) -> None:
        """Verify format_with_context() aligns pointer correctly."""
        cursor = Cursor(source="hello", pos=2)
        error = ParseError(message="Error", cursor=cursor)
        formatted = error.format_with_context()

        lines = formatted.split("\n")
        # Find the line with hello and the pointer line
        for i, line in enumerate(lines):
            if "hello" in line and i + 1 < len(lines):
                # Next line should have pointer at correct position
                pointer_line = lines[i + 1]
                # The pointer should be at column 3 (accounting for line number prefix)
                assert "^" in pointer_line


class TestCursorIntegration:
    """Integration tests for Cursor methods working together."""

    def test_cursor_parse_word(self) -> None:
        """Integration: Use cursor to parse a word."""
        cursor = Cursor(source="hello world", pos=0)
        start_pos = cursor.pos

        # Advance until space
        while not cursor.is_eof and cursor.current != " ":
            cursor = cursor.advance()

        # Extract word
        word = Cursor(source="hello world", pos=start_pos).slice_to(cursor.pos)
        assert word == "hello"

    def test_cursor_skip_and_parse(self) -> None:
        """Integration: Skip whitespace then parse."""
        cursor = Cursor(source="   hello", pos=0)

        # Skip spaces
        cursor = cursor.skip_spaces()

        # Parse word
        start_pos = cursor.pos
        while not cursor.is_eof and cursor.current.isalpha():
            cursor = cursor.advance()

        word = Cursor(source="   hello", pos=start_pos).slice_to(cursor.pos)
        assert word == "hello"

    def test_cursor_peek_and_expect(self) -> None:
        """Integration: Use peek to look ahead, then expect."""
        cursor = Cursor(source="hello", pos=0)

        # Peek ahead
        assert cursor.peek(0) == "h"
        assert cursor.peek(1) == "e"

        # Expect and advance
        new_cursor = cursor.expect("h")
        assert new_cursor is not None
        assert new_cursor.current == "e"
