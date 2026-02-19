"""Tests for the Cursor and LineOffsetCache infrastructure.

Tests:
- LineOffsetCache.__init__: offset table construction for various source shapes
- LineOffsetCache.get_line_col: binary search over offset table, clamping, edge cases
- Cursor.skip_line_end: recognition of LF line endings, unchanged behavior at non-endings
"""

from __future__ import annotations

from ftllexengine.syntax.cursor import Cursor, LineOffsetCache


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
