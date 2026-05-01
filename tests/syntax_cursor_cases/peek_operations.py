# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor.py."""

from tests.syntax_cursor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PEEK OPERATIONS
# ============================================================================


class TestCursorPeek:
    """Test peek operations."""

    def test_peek_current(self) -> None:
        """Peek at current position (offset 0)."""
        cursor = Cursor("hello", 0)

        assert cursor.peek(0) == "h"

    def test_peek_next(self) -> None:
        """Peek at next position (offset 1)."""
        cursor = Cursor("hello", 0)

        assert cursor.peek(1) == "e"

    def test_peek_multiple_ahead(self) -> None:
        """Peek multiple positions ahead."""
        cursor = Cursor("hello", 0)

        assert cursor.peek(2) == "l"
        assert cursor.peek(3) == "l"
        assert cursor.peek(4) == "o"

    def test_peek_at_eof_returns_none(self) -> None:
        """Peek at EOF returns None."""
        cursor = Cursor("hello", 5)

        assert cursor.peek(0) is None

    def test_peek_beyond_eof_returns_none(self) -> None:
        """Peek beyond EOF returns None."""
        cursor = Cursor("hello", 3)

        assert cursor.peek(5) is None

    def test_peek_does_not_modify_cursor(self) -> None:
        """Peek does not modify cursor position."""
        cursor = Cursor("hello", 0)

        _ = cursor.peek(3)
        assert cursor.pos == 0
        assert cursor.current == "h"

    def test_peek_negative_offset_returns_none(self) -> None:
        """Negative offset returns None.

        Without the target_pos < 0 guard, peek(-1) at pos=0 would compute
        target_pos=-1, skip the >=len(source) check (since -1 < 5), and
        return source[-1]="o" via Python negative indexing — a silent wrong
        read. The guard makes look-behind attempts safe-but-unproductive.
        """
        cursor = Cursor("hello", 0)

        assert cursor.peek(-1) is None
        assert cursor.peek(-5) is None

    def test_peek_negative_offset_at_mid_source_returns_none(self) -> None:
        """Negative offset whose magnitude exceeds pos returns None.

        At pos=2, peek(-3) yields target_pos=-1 < 0. Without the guard this
        would silently return source[-1] ("o") instead of None.
        """
        cursor = Cursor("hello", 2)

        # offset that undershoots the start of the source
        assert cursor.peek(-3) is None

    def test_peek_negative_offset_exactly_at_start_returns_none(self) -> None:
        """Negative offset equal to pos yields target_pos=0, which is valid.

        peek(-2) at pos=2 yields target_pos=0 which is within bounds and
        returns the first character. Only offsets that produce negative
        target_pos return None.
        """
        cursor = Cursor("hello", 2)

        # target_pos = 0 — within bounds, returns first char
        assert cursor.peek(-2) == "h"
        # target_pos = -1 — before start, returns None
        assert cursor.peek(-3) is None
