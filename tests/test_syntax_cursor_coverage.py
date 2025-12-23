"""Coverage tests for syntax/cursor.py edge cases.

Targets uncovered lines:
- Lines 354-360: LineOffsetCache.__init__
- Lines 382-401: LineOffsetCache.get_line_col (including edge cases)

Python 3.13+.
"""

from __future__ import annotations

from ftllexengine.syntax.cursor import LineOffsetCache

# ============================================================================
# LineOffsetCache.__init__ - Lines 354-360
# ============================================================================


class TestLineOffsetCacheInit:
    """Test LineOffsetCache initialization (lines 354-360)."""

    def test_init_empty_source(self) -> None:
        """Test cache initialization with empty source."""
        cache = LineOffsetCache("")

        # Empty source still has line 1 starting at offset 0
        assert cache._source_len == 0
        assert cache._offsets == (0,)

    def test_init_single_line(self) -> None:
        """Test cache initialization with single line (no newlines)."""
        cache = LineOffsetCache("hello world")

        assert cache._source_len == 11
        assert cache._offsets == (0,)  # Only line 1

    def test_init_multiple_lines(self) -> None:
        """Test cache initialization with multiple lines."""
        cache = LineOffsetCache("line1\nline2\nline3")

        assert cache._source_len == 17
        # Line 1 at 0, line 2 at 6, line 3 at 12
        assert cache._offsets == (0, 6, 12)

    def test_init_trailing_newline(self) -> None:
        """Test cache initialization with trailing newline."""
        cache = LineOffsetCache("line1\nline2\n")

        assert cache._source_len == 12
        # Line 1 at 0, line 2 at 6, line 3 at 12 (empty line after trailing newline)
        assert cache._offsets == (0, 6, 12)

    def test_init_consecutive_newlines(self) -> None:
        """Test cache initialization with consecutive newlines (empty lines)."""
        cache = LineOffsetCache("a\n\nb")

        assert cache._source_len == 4
        # Line 1 at 0, line 2 at 2, line 3 at 3
        assert cache._offsets == (0, 2, 3)

    def test_init_only_newlines(self) -> None:
        """Test cache initialization with only newlines."""
        cache = LineOffsetCache("\n\n\n")

        assert cache._source_len == 3
        # Line 1 at 0, line 2 at 1, line 3 at 2, line 4 at 3
        assert cache._offsets == (0, 1, 2, 3)


# ============================================================================
# LineOffsetCache.get_line_col - Lines 382-401
# ============================================================================


class TestLineOffsetCacheGetLineCol:
    """Test LineOffsetCache.get_line_col method (lines 382-401)."""

    def test_get_line_col_first_position(self) -> None:
        """Test line/col for position 0 (first character)."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(0)

        assert line == 1
        assert col == 1

    def test_get_line_col_middle_of_first_line(self) -> None:
        """Test line/col for middle of first line."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(2)

        assert line == 1
        assert col == 3

    def test_get_line_col_start_of_second_line(self) -> None:
        """Test line/col for start of second line."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(6)

        assert line == 2
        assert col == 1

    def test_get_line_col_middle_of_second_line(self) -> None:
        """Test line/col for middle of second line."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(8)

        assert line == 2
        assert col == 3

    def test_get_line_col_at_newline(self) -> None:
        """Test line/col for position at newline character."""
        cache = LineOffsetCache("hello\nworld")

        # Position 5 is the newline itself
        line, col = cache.get_line_col(5)

        assert line == 1
        assert col == 6

    def test_get_line_col_at_end(self) -> None:
        """Test line/col for position at end of source."""
        cache = LineOffsetCache("hello\nworld")

        line, col = cache.get_line_col(11)  # Length of source

        assert line == 2
        assert col == 6

    def test_get_line_col_negative_position(self) -> None:
        """Test line/col with negative position (line 382-383)."""
        cache = LineOffsetCache("hello\nworld")

        # Negative position should clamp to 0
        line, col = cache.get_line_col(-5)

        assert line == 1
        assert col == 1

    def test_get_line_col_position_beyond_source(self) -> None:
        """Test line/col with position beyond source length (line 384-385)."""
        cache = LineOffsetCache("hello\nworld")

        # Position beyond source should clamp to source length
        line, col = cache.get_line_col(100)

        assert line == 2
        assert col == 6

    def test_get_line_col_empty_source(self) -> None:
        """Test line/col for empty source."""
        cache = LineOffsetCache("")

        # Position 0 in empty source
        line, col = cache.get_line_col(0)

        assert line == 1
        assert col == 1

    def test_get_line_col_third_line(self) -> None:
        """Test line/col for third line (binary search coverage)."""
        cache = LineOffsetCache("a\nb\nc\nd")

        # Position 4 is 'c'
        line, col = cache.get_line_col(4)

        assert line == 3
        assert col == 1

    def test_get_line_col_many_lines_binary_search(self) -> None:
        """Test line/col with many lines to exercise binary search (lines 389-395)."""
        # Create source with 10 lines
        source = "\n".join(f"line{i}" for i in range(10))
        cache = LineOffsetCache(source)

        # Test various positions across lines
        # Line 1 starts at 0
        assert cache.get_line_col(0) == (1, 1)

        # Line 5 - testing binary search middle case
        # Each line is "line0\n", "line1\n", etc. - 6 chars each
        assert cache.get_line_col(24) == (5, 1)

        # Line 8
        assert cache.get_line_col(42) == (8, 1)

        # Line 10 (last line)
        assert cache.get_line_col(54) == (10, 1)

    def test_get_line_col_long_lines(self) -> None:
        """Test line/col with long lines."""
        cache = LineOffsetCache("a" * 100 + "\n" + "b" * 50)

        # Position in second line
        line, col = cache.get_line_col(110)

        assert line == 2
        assert col == 10  # 110 - 101 + 1 = 10

    def test_get_line_col_position_exactly_at_source_len(self) -> None:
        """Test line/col at exactly source length (boundary case)."""
        source = "abc"
        cache = LineOffsetCache(source)

        # Position 3 == len(source)
        line, col = cache.get_line_col(3)

        assert line == 1
        assert col == 4

    def test_get_line_col_consecutive_calls(self) -> None:
        """Test that get_line_col works correctly with consecutive calls."""
        cache = LineOffsetCache("hello\nworld\n!")

        # Multiple consecutive calls should all work correctly
        assert cache.get_line_col(0) == (1, 1)
        assert cache.get_line_col(5) == (1, 6)
        assert cache.get_line_col(6) == (2, 1)
        assert cache.get_line_col(11) == (2, 6)
        assert cache.get_line_col(12) == (3, 1)
