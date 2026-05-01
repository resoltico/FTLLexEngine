# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor.py."""

from tests.syntax_cursor_cases import *  # noqa: F403 - shared split test support

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
