# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor.py."""

from tests.syntax_cursor_cases import *  # noqa: F403 - shared split test support

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

    def test_cursor_negative_pos_raises_value_error(self) -> None:
        """Cursor with negative pos raises ValueError (lines 95-96).

        Negative positions silently return characters from the end of the
        source via Python indexing. The guard makes this construction error
        explicit rather than allowing silent wrong-character access.
        """
        with pytest.raises(ValueError, match="must be >= 0"):
            Cursor("hello", -1)

    def test_cursor_pos_beyond_source_raises_value_error(self) -> None:
        """Cursor with pos > len(source) raises ValueError (lines 98-102).

        advance() always clamps to len(source); constructing with a larger
        value indicates a programming error, not a valid EOF position.
        """
        with pytest.raises(ValueError, match="exceeds source length"):
            Cursor("hello", 6)
