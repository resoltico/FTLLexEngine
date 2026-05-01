# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor_property.py."""

from tests.syntax_cursor_property_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PROPERTY TESTS - IMMUTABILITY
# ============================================================================


class TestCursorImmutability:
    """Test cursor immutability properties."""

    @given(source=source_text, pos=positions)
    @settings(max_examples=200)
    def test_cursor_is_immutable(self, source: str, pos: int) -> None:
        """INVARIANT: Cursor is immutable - advance() returns NEW cursor."""
        assume(pos < len(source))  # Valid position
        event(f"text_len={len(source)}")

        cursor = Cursor(source, pos)
        original_pos = cursor.pos

        # Advance cursor
        new_cursor = cursor.advance()

        # Original cursor unchanged
        assert cursor.pos == original_pos
        # New cursor has new position
        assert new_cursor.pos == original_pos + 1

    @given(source=source_text, pos=positions)
    @settings(max_examples=200)
    def test_advance_count_returns_new_cursor(self, source: str, pos: int) -> None:
        """PROPERTY: advance(count) returns new cursor, original unchanged."""
        assume(pos < len(source))
        event(f"pos={pos}")

        cursor = Cursor(source, pos)
        original_pos = cursor.pos

        # Advance by N
        n = min(5, len(source) - pos)
        new_cursor = cursor.advance(n)

        # Original unchanged
        assert cursor.pos == original_pos
        # New cursor advanced by N
        assert new_cursor.pos == original_pos + n

    @given(source=source_text)
    @settings(max_examples=100)
    def test_cursor_advance_preserves_source(self, source: str) -> None:
        """PROPERTY: advance() preserves source string."""
        event(f"text_len={len(source)}")
        cursor = Cursor(source, 0)

        while not cursor.is_eof:
            new_cursor = cursor.advance()
            assert new_cursor.source == source
            cursor = new_cursor
