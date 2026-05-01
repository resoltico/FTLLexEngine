# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor.py."""

from tests.syntax_cursor_cases import *  # noqa: F403 - shared split test support

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
