# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor.py."""

from tests.syntax_cursor_cases import *  # noqa: F403 - shared split test support

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

    def test_advance_zero_positions_raises(self) -> None:
        """Advance by 0 raises ValueError — zero advance is a no-op and always a bug."""
        cursor = Cursor("hello", 2)

        with pytest.raises(ValueError, match="advance\\(\\) count must be >= 1, got 0"):
            cursor.advance(0)

    def test_advance_negative_positions_raises(self) -> None:
        """Advance by negative count raises ValueError.

        Negative advance is always a programming error: cursor.advance(-1) at
        pos=0 would create Cursor(source, -1) which makes .current return
        source[-1] (the last character), silently corrupting parser state.
        """
        cursor = Cursor("hello", 2)

        with pytest.raises(ValueError, match="advance\\(\\) count must be >= 1, got -1"):
            cursor.advance(-1)

    def test_advance_large_negative_positions_raises(self) -> None:
        """Advance by large negative count raises ValueError."""
        cursor = Cursor("hello", 4)

        with pytest.raises(ValueError, match="advance\\(\\) count must be >= 1, got -100"):
            cursor.advance(-100)
