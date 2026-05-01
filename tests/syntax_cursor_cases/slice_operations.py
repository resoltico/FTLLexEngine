# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor.py."""

from tests.syntax_cursor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SLICE OPERATIONS
# ============================================================================


class TestCursorSlice:
    """Test cursor slice operations."""

    def test_slice_to_from_start(self) -> None:
        """Slice from start to middle."""
        cursor = Cursor("hello world", 0)

        text = cursor.slice_to(5)

        assert text == "hello"

    def test_slice_to_from_middle(self) -> None:
        """Slice from middle position."""
        cursor = Cursor("hello world", 6)

        text = cursor.slice_to(11)

        assert text == "world"

    def test_slice_to_empty(self) -> None:
        """Slice with same start and end returns empty string."""
        cursor = Cursor("hello", 2)

        text = cursor.slice_to(2)

        assert text == ""

    def test_slice_to_single_char(self) -> None:
        """Slice single character."""
        cursor = Cursor("hello", 1)

        text = cursor.slice_to(2)

        assert text == "e"

    def test_slice_to_entire_source(self) -> None:
        """Slice entire source from position 0."""
        cursor = Cursor("hello", 0)

        text = cursor.slice_to(5)

        assert text == "hello"

    def test_slice_to_with_unicode(self) -> None:
        """Slice with Unicode characters."""
        cursor = Cursor("привет мир", 0)

        text = cursor.slice_to(6)

        assert text == "привет"
