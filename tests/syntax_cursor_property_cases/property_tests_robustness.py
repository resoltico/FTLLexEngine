# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor_property.py."""

from tests.syntax_cursor_property_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PROPERTY TESTS - ROBUSTNESS
# ============================================================================


class TestCursorRobustness:
    """Test cursor robustness with edge cases."""

    @given(source=source_text)
    @settings(max_examples=100)
    def test_empty_source_is_eof(self, source: str) -> None:
        """PROPERTY: Empty source is always EOF."""
        event(f"source_len={len(source)}")
        if len(source) == 0:
            cursor = Cursor(source, 0)
            assert cursor.is_eof is True

    @given(source=source_text)
    @settings(max_examples=100)
    def test_position_at_end_is_eof(self, source: str) -> None:
        """PROPERTY: pos == len(source) is the canonical EOF position."""
        event(f"source_len={len(source)}")
        cursor = Cursor(source, len(source))
        assert cursor.is_eof is True

    @given(source=source_text, pos=st.integers(min_value=1, max_value=1000))
    @settings(max_examples=100)
    def test_position_strictly_beyond_end_raises(self, source: str, pos: int) -> None:
        """PROPERTY: pos > len(source) raises ValueError at construction.

        advance() always clamps to len(source), so positions strictly beyond
        the source length cannot arise through normal cursor navigation and
        indicate a construction error.
        """
        assume(pos > len(source))
        event(f"excess={pos - len(source)}")
        with pytest.raises(ValueError, match="exceeds source length"):
            Cursor(source, pos)

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=50)
    def test_advance_at_eof_stays_at_eof(self, source: str) -> None:
        """PROPERTY: Advancing at EOF stays at EOF."""
        event(f"source_len={len(source)}")
        cursor = Cursor(source, len(source))
        assert cursor.is_eof is True

        # Advance should keep us at or past EOF
        new_cursor = cursor.advance()
        assert new_cursor.is_eof is True

    @given(
        source=source_text.filter(lambda s: len(s) > 0),
        offset=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100)
    def test_peek_beyond_eof_returns_none(self, source: str, offset: int) -> None:
        """PROPERTY: peek(offset) returns None when offset >= remaining chars."""
        event(f"offset={offset}")
        cursor = Cursor(source, 0)

        if offset >= len(source):
            result = cursor.peek(offset)
            assert result is None

    @given(source=source_text, count=st.integers(min_value=1, max_value=1000))
    @settings(max_examples=100)
    def test_advance_clamps_at_eof(self, source: str, count: int) -> None:
        """PROPERTY: advance(count) clamps position at source length."""
        event(f"advance_count={count}")
        cursor = Cursor(source, 0)

        new_cursor = cursor.advance(count)

        # Position should not exceed source length
        assert new_cursor.pos <= len(source)
