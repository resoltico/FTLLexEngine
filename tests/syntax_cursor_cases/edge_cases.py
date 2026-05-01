# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor.py."""

from tests.syntax_cursor_cases import *  # noqa: F403 - shared split test support

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
