# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor.py."""

from tests.syntax_cursor_cases import *  # noqa: F403 - shared split test support

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
