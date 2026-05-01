# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor.py."""

from tests.syntax_cursor_cases import *  # noqa: F403 - shared split test support

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

    def test_current_raises_value_error_beyond_end(self) -> None:
        """Constructing cursor beyond end raises ValueError, not EOFError.

        The valid way to reach EOF is pos == len(source); positions strictly
        greater are rejected at construction time so .current is never reached.
        """
        with pytest.raises(ValueError, match="exceeds source length"):
            Cursor("hello", 10)

    def test_current_with_unicode(self) -> None:
        """Get current character with Unicode."""
        cursor = Cursor("привет", 0)

        assert cursor.current == "п"

    def test_current_with_emoji(self) -> None:
        """Get current character with emoji."""
        cursor = Cursor("hello 👋 world", 6)

        assert cursor.current == "👋"
