"""Hypothesis property-based tests for Cursor.

Tests cursor immutability, EOF handling, and navigation properties.
Complements test_cursor.py with property-based testing.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.cursor import Cursor

# ============================================================================
# HYPOTHESIS STRATEGIES
# ============================================================================


# Strategy for source text - keep max_size for performance
source_text = st.text(
    alphabet=st.characters(blacklist_categories=["Cc"], blacklist_characters=["\x00"]),
    min_size=0,
    max_size=200,  # Keep practical bound for performance
)

# Strategy for positions (will be constrained by source length)
positions = st.integers(min_value=0, max_value=500)


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
        cursor = Cursor(source, 0)

        while not cursor.is_eof:
            new_cursor = cursor.advance()
            assert new_cursor.source == source
            cursor = new_cursor


# ============================================================================
# PROPERTY TESTS - EOF HANDLING
# ============================================================================


class TestCursorEOF:
    """Test EOF (End Of File) detection properties."""

    @given(source=source_text)
    @settings(max_examples=200)
    def test_is_eof_true_at_end(self, source: str) -> None:
        """PROPERTY: is_eof is True when pos >= len(source)."""
        cursor = Cursor(source, len(source))
        assert cursor.is_eof is True

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=200)
    def test_is_eof_false_before_end(self, source: str) -> None:
        """PROPERTY: is_eof is False when pos < len(source)."""
        cursor = Cursor(source, 0)
        assert cursor.is_eof is False

    @given(source=source_text)
    @settings(max_examples=100)
    def test_current_raises_eoferror_at_eof(self, source: str) -> None:
        """PROPERTY: current raises EOFError when is_eof is True."""
        cursor = Cursor(source, len(source))

        if cursor.is_eof:
            with pytest.raises(EOFError):
                _ = cursor.current

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=100)
    def test_current_succeeds_before_eof(self, source: str) -> None:
        """PROPERTY: current succeeds when is_eof is False."""
        cursor = Cursor(source, 0)

        if not cursor.is_eof:
            # Should not raise
            char = cursor.current
            assert isinstance(char, str)
            assert len(char) == 1

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=100)
    def test_advance_until_eof_reaches_end(self, source: str) -> None:
        """PROPERTY: Advancing through source eventually reaches EOF."""
        cursor = Cursor(source, 0)

        # Advance until EOF
        for _ in range(len(source) + 1):
            if cursor.is_eof:
                break
            cursor = cursor.advance()

        # Should be at EOF
        assert cursor.is_eof is True
        assert cursor.pos >= len(source)


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
        cursor = Cursor(source, 0)
        n_safe = min(n, len(source))

        new_cursor = cursor.advance(n_safe)

        assert new_cursor.pos == cursor.pos + n_safe

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=100)
    def test_advance_once_equals_advance_one(self, source: str) -> None:
        """PROPERTY: advance() == advance(1)."""
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
        start_pos = min(start_pos, len(source) - 1)
        cursor = Cursor(source, start_pos)

        end_pos = min(start_pos + 5, len(source))
        extracted = cursor.slice_to(end_pos)

        assert extracted == source[start_pos:end_pos]


# ============================================================================
# PROPERTY TESTS - LINE/COLUMN TRACKING
# ============================================================================


class TestCursorLineColumn:
    """Test line and column tracking properties."""

    @given(source=source_text)
    @settings(max_examples=100)
    def test_line_starts_at_one(self, source: str) -> None:
        """PROPERTY: Line numbers start at 1."""
        cursor = Cursor(source, 0)
        line, _ = cursor.compute_line_col()

        assert line >= 1

    @given(source=source_text)
    @settings(max_examples=100)
    def test_column_starts_at_one(self, source: str) -> None:
        """PROPERTY: Column numbers start at 1."""
        cursor = Cursor(source, 0)
        _, column = cursor.compute_line_col()

        assert column >= 1

    @given(lines=st.lists(st.text(), min_size=1, max_size=10))  # Keep list bound for performance
    @settings(max_examples=50)
    def test_newline_increments_line_number(self, lines: list[str]) -> None:
        """PROPERTY: Newlines increment line number."""
        source = "\n".join(lines)

        # Count newlines
        newline_count = source.count("\n")

        # Advance to end
        cursor_end = Cursor(source, len(source))
        line_end, _ = cursor_end.compute_line_col()

        # Line number should be newline_count + 1
        assert line_end == newline_count + 1

    @given(source=source_text)
    @settings(max_examples=50)
    def test_compute_line_col_equals_property(self, source: str) -> None:
        """PROPERTY: compute_line_col() returns same as line_col property."""
        cursor = Cursor(source, min(len(source), 10))

        result1 = cursor.compute_line_col()
        result2 = cursor.compute_line_col()

        assert result1 == result2


# ============================================================================
# PROPERTY TESTS - ROBUSTNESS
# ============================================================================


class TestCursorRobustness:
    """Test cursor robustness with edge cases."""

    @given(source=source_text)
    @settings(max_examples=100)
    def test_empty_source_is_eof(self, source: str) -> None:
        """PROPERTY: Empty source is always EOF."""
        if len(source) == 0:
            cursor = Cursor(source, 0)
            assert cursor.is_eof is True

    @given(source=source_text, pos=st.integers(min_value=0, max_value=1000))
    @settings(max_examples=100)
    def test_position_beyond_end_is_eof(self, source: str, pos: int) -> None:
        """PROPERTY: Position beyond end is EOF."""
        if pos >= len(source):
            cursor = Cursor(source, pos)
            assert cursor.is_eof is True

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=50)
    def test_advance_at_eof_stays_at_eof(self, source: str) -> None:
        """PROPERTY: Advancing at EOF stays at EOF."""
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
        cursor = Cursor(source, 0)

        if offset >= len(source):
            result = cursor.peek(offset)
            assert result is None

    @given(source=source_text, count=st.integers(min_value=0, max_value=1000))
    @settings(max_examples=100)
    def test_advance_clamps_at_eof(self, source: str, count: int) -> None:
        """PROPERTY: advance(count) clamps position at source length."""
        cursor = Cursor(source, 0)

        new_cursor = cursor.advance(count)

        # Position should not exceed source length
        assert new_cursor.pos <= len(source)


# ============================================================================
# PROPERTY TESTS - IDEMPOTENCE
# ============================================================================


class TestCursorIdempotence:
    """Test idempotent cursor operations."""

    @given(source=source_text, pos=positions)
    @settings(max_examples=100)
    def test_is_eof_is_idempotent(self, source: str, pos: int) -> None:
        """PROPERTY: Multiple is_eof calls return same value."""
        cursor = Cursor(source, pos)

        result1 = cursor.is_eof
        result2 = cursor.is_eof
        result3 = cursor.is_eof

        assert result1 == result2 == result3

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=100)
    def test_current_is_idempotent(self, source: str) -> None:
        """PROPERTY: Multiple current accesses return same character."""
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
        cursor = Cursor(source, 0)

        peek1 = cursor.peek(offset)
        peek2 = cursor.peek(offset)
        peek3 = cursor.peek(offset)

        assert peek1 == peek2 == peek3

    @given(source=source_text, pos=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100)
    def test_line_col_is_idempotent(self, source: str, pos: int) -> None:
        """PROPERTY: Multiple line_col accesses return same value."""
        pos = min(pos, len(source))
        cursor = Cursor(source, pos)

        lc1 = cursor.compute_line_col()
        lc2 = cursor.compute_line_col()
        lc3 = cursor.compute_line_col()

        assert lc1 == lc2 == lc3
