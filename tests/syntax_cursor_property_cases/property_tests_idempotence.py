# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor_property.py."""

from tests.syntax_cursor_property_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PROPERTY TESTS - IDEMPOTENCE
# ============================================================================


class TestCursorIdempotence:
    """Test idempotent cursor operations."""

    @given(source=source_text, pos=positions)
    @settings(max_examples=100)
    def test_is_eof_is_idempotent(self, source: str, pos: int) -> None:
        """PROPERTY: Multiple is_eof calls return same value."""
        event(f"source_len={len(source)}")
        # Clamp pos to the valid range [0, len(source)]
        pos = min(pos, len(source))
        cursor = Cursor(source, pos)

        result1 = cursor.is_eof
        result2 = cursor.is_eof
        result3 = cursor.is_eof

        assert result1 == result2 == result3

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=100)
    def test_current_is_idempotent(self, source: str) -> None:
        """PROPERTY: Multiple current accesses return same character."""
        event(f"source_len={len(source)}")
        cursor = Cursor(source, 0)

        if not cursor.is_eof:
            char1 = cursor.current
            char2 = cursor.current
            char3 = cursor.current

            assert char1 == char2 == char3

    @given(
        source=source_text.filter(lambda s: len(s) > 2),
        offset=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=100)
    def test_peek_is_idempotent(self, source: str, offset: int) -> None:
        """PROPERTY: Multiple peek calls return same result."""
        event(f"offset={offset}")
        cursor = Cursor(source, 0)

        peek1 = cursor.peek(offset)
        peek2 = cursor.peek(offset)
        peek3 = cursor.peek(offset)

        assert peek1 == peek2 == peek3

    @given(source=source_text, pos=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100)
    def test_line_col_is_idempotent(self, source: str, pos: int) -> None:
        """PROPERTY: Multiple line_col accesses return same value."""
        event(f"source_len={len(source)}")
        pos = min(pos, len(source))
        cursor = Cursor(source, pos)

        lc1 = cursor.compute_line_col()
        lc2 = cursor.compute_line_col()
        lc3 = cursor.compute_line_col()

        assert lc1 == lc2 == lc3
