# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor_property.py."""

from tests.syntax_cursor_property_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PROPERTY TESTS - NAVIGATION
# ============================================================================


class TestCursorNavigation:
    """Test cursor navigation properties."""

    @given(source=source_text, pos=positions)
    @settings(max_examples=200)
    def test_current_returns_char_at_position(self, source: str, pos: int) -> None:
        """PROPERTY: current returns character at pos."""
        assume(pos < len(source))
        event(f"pos={pos}")

        cursor = Cursor(source, pos)

        if not cursor.is_eof:
            assert cursor.current == source[pos]

    @given(
        source=source_text.filter(lambda s: len(s) > 1),
        n=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    def test_advance_count_moves_by_count(self, source: str, n: int) -> None:
        """PROPERTY: advance(k) moves position by k."""
        event(f"advance_count={n}")
        cursor = Cursor(source, 0)
        n_safe = min(n, len(source))

        new_cursor = cursor.advance(n_safe)

        assert new_cursor.pos == cursor.pos + n_safe

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=100)
    def test_advance_once_equals_advance_one(self, source: str) -> None:
        """PROPERTY: advance() == advance(1)."""
        event(f"source_len={len(source)}")
        cursor = Cursor(source, 0)

        cursor1 = cursor.advance()
        cursor2 = cursor.advance(1)

        assert cursor1.pos == cursor2.pos

    @given(
        source=source_text.filter(lambda s: len(s) > 2),
        offset=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=100)
    def test_peek_reads_ahead_without_advancing(self, source: str, offset: int) -> None:
        """PROPERTY: peek(offset) reads ahead without changing position."""
        event(f"offset={offset}")
        cursor = Cursor(source, 0)

        if offset < len(source):
            peeked = cursor.peek(offset)
            pos_after_peek = cursor.pos

            # Peek should not change position
            assert pos_after_peek == 0
            # Peek should return correct character
            assert peeked == source[offset]

    @given(
        source=source_text.filter(lambda s: len(s) > 0),
        start_pos=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100)
    def test_slice_to_extracts_substring(self, source: str, start_pos: int) -> None:
        """PROPERTY: slice_to(end) extracts source[pos:end]."""
        event(f"source_len={len(source)}")
        start_pos = min(start_pos, len(source) - 1)
        cursor = Cursor(source, start_pos)

        end_pos = min(start_pos + 5, len(source))
        extracted = cursor.slice_to(end_pos)

        assert extracted == source[start_pos:end_pos]
