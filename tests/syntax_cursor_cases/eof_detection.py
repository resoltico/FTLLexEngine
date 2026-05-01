# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor.py."""

from tests.syntax_cursor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# EOF DETECTION
# ============================================================================


class TestCursorEOF:
    """Test EOF detection."""

    def test_is_eof_false_at_start(self) -> None:
        """is_eof is False at start of source."""
        cursor = Cursor("hello", 0)

        assert not cursor.is_eof

    def test_is_eof_false_in_middle(self) -> None:
        """is_eof is False in middle of source."""
        cursor = Cursor("hello", 2)

        assert not cursor.is_eof

    def test_is_eof_true_at_end(self) -> None:
        """is_eof is True at end of source."""
        cursor = Cursor("hello", 5)

        assert cursor.is_eof

    def test_construction_beyond_end_raises(self) -> None:
        """Constructing a cursor with pos > len(source) raises ValueError.

        EOF is represented exclusively by pos == len(source). Positions beyond
        the source length are construction errors: advance() always clamps to
        len(source), so they cannot arise through normal cursor navigation.
        """
        with pytest.raises(ValueError, match="exceeds source length"):
            Cursor("hello", 10)

    def test_is_eof_true_for_empty_source(self) -> None:
        """is_eof is True for empty source at position 0."""
        cursor = Cursor("", 0)

        assert cursor.is_eof
