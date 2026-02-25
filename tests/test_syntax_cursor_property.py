"""Hypothesis property-based tests for syntax.cursor module.

Tests cursor immutability, EOF handling, navigation, and ParseResult/ParseError
properties. Combines targeted property tests with comprehensive contract verification.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.cursor import Cursor, ParseError, ParseResult

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


# ============================================================================
# PROPERTY TESTS - EOF HANDLING
# ============================================================================


class TestCursorEOF:
    """Test EOF (End Of File) detection properties."""

    @given(source=source_text)
    @settings(max_examples=200)
    def test_is_eof_true_at_end(self, source: str) -> None:
        """PROPERTY: is_eof is True when pos >= len(source)."""
        event(f"text_len={len(source)}")
        cursor = Cursor(source, len(source))
        assert cursor.is_eof is True

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=200)
    def test_is_eof_false_before_end(self, source: str) -> None:
        """PROPERTY: is_eof is False when pos < len(source)."""
        event(f"text_len={len(source)}")
        cursor = Cursor(source, 0)
        assert cursor.is_eof is False

    @given(source=source_text)
    @settings(max_examples=100)
    def test_current_raises_eoferror_at_eof(self, source: str) -> None:
        """PROPERTY: current raises EOFError when is_eof is True."""
        event(f"text_len={len(source)}")
        cursor = Cursor(source, len(source))

        if cursor.is_eof:
            with pytest.raises(EOFError):
                _ = cursor.current

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=100)
    def test_current_succeeds_before_eof(self, source: str) -> None:
        """PROPERTY: current succeeds when is_eof is False."""
        event(f"text_len={len(source)}")
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
        event(f"text_len={len(source)}")
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

    @given(source=source_text, count=st.integers(min_value=1, max_value=1000))
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


# ============================================================================
# CONTRACT TESTS (from test_cursor_comprehensive.py)
# ============================================================================


class TestCursorImmutabilityContracts:
    """Contract-level tests for Cursor immutability."""

    def test_cursor_frozen(self) -> None:
        """Property: Cursor instances are immutable (frozen)."""
        cursor = Cursor(source="hello", pos=0)

        with pytest.raises((AttributeError, TypeError)):
            cursor.pos = 1  # type: ignore[misc]

    @given(st.text(), st.integers(min_value=0, max_value=1000))
    def test_cursor_construction(self, source: str, pos: int) -> None:
        """Property: Cursor can be constructed with any valid source and position."""
        event(f"input_len={len(source)}")
        # Clamp position to valid range
        pos = min(pos, len(source))
        cursor = Cursor(source=source, pos=pos)
        assert cursor.source == source
        assert cursor.pos == pos


class TestCursorEOFProperty:
    """Property-based tests for Cursor.is_eof property."""

    def test_is_eof_at_start_of_nonempty_string(self) -> None:
        """Verify is_eof is False at start of non-empty string."""
        cursor = Cursor(source="hello", pos=0)
        assert cursor.is_eof is False

    def test_is_eof_at_end_of_string(self) -> None:
        """Verify is_eof is True at end of string."""
        cursor = Cursor(source="hello", pos=5)
        assert cursor.is_eof is True

    def test_construction_beyond_end_raises(self) -> None:
        """Verify constructing cursor with pos > len(source) raises ValueError."""
        with pytest.raises(ValueError, match="exceeds source length"):
            Cursor(source="hello", pos=10)

    def test_is_eof_empty_string(self) -> None:
        """Verify is_eof is True for empty string at position 0."""
        cursor = Cursor(source="", pos=0)
        assert cursor.is_eof is True

    @given(st.text(min_size=1))
    def test_is_eof_middle_of_string(self, source: str) -> None:
        """Property: is_eof is False in middle of string."""
        event(f"input_len={len(source)}")
        mid_pos = len(source) // 2
        cursor = Cursor(source=source, pos=mid_pos)
        if mid_pos < len(source):
            assert cursor.is_eof is False


class TestCursorCurrentProperty:
    """Property-based tests for Cursor.current property."""

    def test_current_at_start(self) -> None:
        """Verify current returns first character at position 0."""
        cursor = Cursor(source="hello", pos=0)
        assert cursor.current == "h"

    def test_current_in_middle(self) -> None:
        """Verify current returns character at current position."""
        cursor = Cursor(source="hello", pos=2)
        assert cursor.current == "l"

    def test_current_raises_at_eof(self) -> None:
        """Verify current raises EOFError at EOF."""
        cursor = Cursor(source="hello", pos=5)
        with pytest.raises(EOFError, match="EOF"):
            _ = cursor.current

    def test_construction_beyond_eof_raises(self) -> None:
        """Verify construction with pos beyond source length raises ValueError.

        The valid range for pos is [0, len(source)]. Positions strictly greater
        than len(source) are rejected at construction time.
        """
        with pytest.raises(ValueError, match="exceeds source length"):
            Cursor(source="hello", pos=10)

    @given(
        st.text(min_size=1).flatmap(
            lambda s: st.tuples(st.just(s), st.integers(min_value=0, max_value=len(s) - 1))
        )
    )
    def test_current_returns_correct_character(self, source_pos: tuple[str, int]) -> None:
        """Property: current returns character at position if valid."""
        source, pos = source_pos
        event(f"input_len={len(source)}")
        event(f"offset={pos}")
        cursor = Cursor(source=source, pos=pos)
        assert cursor.current == source[pos]


class TestCursorPeekMethod:
    """Property-based tests for Cursor.peek() method."""

    def test_peek_at_current_position(self) -> None:
        """Verify peek(0) returns current character."""
        cursor = Cursor(source="hello", pos=0)
        assert cursor.peek(0) == "h"

    def test_peek_ahead_one(self) -> None:
        """Verify peek(1) returns next character."""
        cursor = Cursor(source="hello", pos=0)
        assert cursor.peek(1) == "e"

    def test_peek_beyond_eof_returns_none(self) -> None:
        """Verify peek() returns None when peeking beyond EOF."""
        cursor = Cursor(source="hello", pos=4)
        assert cursor.peek(1) is None

    def test_peek_at_eof_returns_none(self) -> None:
        """Verify peek() returns None at EOF."""
        cursor = Cursor(source="hello", pos=5)
        assert cursor.peek(0) is None

    @given(st.text(min_size=2), st.integers(min_value=0, max_value=10))
    def test_peek_with_various_offsets(self, source: str, offset: int) -> None:
        """Property: peek(offset) returns correct character or None."""
        event(f"input_len={len(source)}")
        event(f"offset={offset}")
        cursor = Cursor(source=source, pos=0)
        result = cursor.peek(offset)

        in_bounds = offset < len(source)
        event(f"valid={in_bounds}")
        if in_bounds:
            assert result == source[offset]
        else:
            assert result is None

    @given(
        source=st.text(min_size=1),
        pos=st.integers(min_value=0, max_value=20),
        offset=st.integers(min_value=-50, max_value=-1),
    )
    def test_peek_negative_offset_always_returns_none_or_valid(
        self, source: str, pos: int, offset: int
    ) -> None:
        """Property: peek(offset) with negative offset returns None or in-bounds char.

        Verifies the target_pos < 0 guard: negative offsets whose magnitude
        exceeds pos must return None, never a character from the END of the source
        (Python negative indexing trap).
        """
        pos = min(pos, len(source))
        cursor = Cursor(source=source, pos=pos)
        target_pos = pos + offset
        result = cursor.peek(offset)

        if target_pos < 0:
            event("outcome=negative_target_returns_none")
            # Without the guard this would silently return source[target_pos]
            # (a character from the END of source). Must be None.
            assert result is None
        elif target_pos >= len(source):
            event("outcome=beyond_eof_returns_none")
            assert result is None
        else:
            event("outcome=in_bounds_lookbehind")
            assert result == source[target_pos]


class TestCursorAdvanceMethod:
    """Property-based tests for Cursor.advance() method."""

    def test_advance_single_position(self) -> None:
        """Verify advance() moves cursor by 1 position."""
        cursor = Cursor(source="hello", pos=0)
        new_cursor = cursor.advance()
        assert new_cursor.pos == 1
        assert cursor.pos == 0  # Original unchanged

    def test_advance_multiple_positions(self) -> None:
        """Verify advance(count) moves cursor by count positions."""
        cursor = Cursor(source="hello", pos=0)
        new_cursor = cursor.advance(3)
        assert new_cursor.pos == 3

    def test_advance_clamped_at_eof(self) -> None:
        """Verify advance() clamps position at EOF."""
        cursor = Cursor(source="hello", pos=3)
        new_cursor = cursor.advance(10)
        assert new_cursor.pos == 5  # Clamped to len(source)

    def test_advance_from_eof_stays_at_eof(self) -> None:
        """Verify advance() from EOF stays at EOF."""
        cursor = Cursor(source="hello", pos=5)
        new_cursor = cursor.advance()
        assert new_cursor.pos == 5

    @given(
        st.text(),
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=1, max_value=10),
    )
    def test_advance_returns_new_cursor(self, source: str, pos: int, count: int) -> None:
        """Property: advance() returns new cursor, original unchanged."""
        event(f"input_len={len(source)}")
        event(f"offset={pos}")
        pos = min(pos, len(source))
        cursor = Cursor(source=source, pos=pos)
        new_cursor = cursor.advance(count)

        # Original unchanged
        assert cursor.pos == pos
        # New cursor advanced (clamped at len(source))
        expected_pos = min(pos + count, len(source))
        assert new_cursor.pos == expected_pos


class TestCursorSliceToMethod:
    """Property-based tests for Cursor.slice_to() method."""

    def test_slice_to_simple_range(self) -> None:
        """Verify slice_to() extracts substring."""
        cursor = Cursor(source="hello world", pos=0)
        text = cursor.slice_to(5)
        assert text == "hello"

    def test_slice_to_from_middle(self) -> None:
        """Verify slice_to() works from middle position."""
        cursor = Cursor(source="hello world", pos=6)
        text = cursor.slice_to(11)
        assert text == "world"

    def test_slice_to_empty_range(self) -> None:
        """Verify slice_to() returns empty string for empty range."""
        cursor = Cursor(source="hello", pos=2)
        text = cursor.slice_to(2)
        assert text == ""

    @given(st.text(min_size=1))
    def test_slice_to_full_string(self, source: str) -> None:
        """Property: slice_to(len(source)) from pos=0 returns full string."""
        event(f"input_len={len(source)}")
        cursor = Cursor(source=source, pos=0)
        text = cursor.slice_to(len(source))
        assert text == source


class TestCursorSkipSpacesMethod:
    """Property-based tests for Cursor.skip_spaces() method."""

    def test_skip_spaces_no_spaces(self) -> None:
        """Verify skip_spaces() returns same cursor when no spaces."""
        cursor = Cursor(source="hello", pos=0)
        new_cursor = cursor.skip_spaces()
        assert new_cursor.pos == 0

    def test_skip_spaces_leading_spaces(self) -> None:
        """Verify skip_spaces() skips leading spaces."""
        cursor = Cursor(source="   hello", pos=0)
        new_cursor = cursor.skip_spaces()
        assert new_cursor.pos == 3
        assert new_cursor.current == "h"

    def test_skip_spaces_all_spaces(self) -> None:
        """Verify skip_spaces() handles all-space string."""
        cursor = Cursor(source="     ", pos=0)
        new_cursor = cursor.skip_spaces()
        assert new_cursor.is_eof is True

    def test_skip_spaces_only_space_not_tab(self) -> None:
        """Verify skip_spaces() only skips space (U+0020), not tab."""
        cursor = Cursor(source="  \thello", pos=0)
        new_cursor = cursor.skip_spaces()
        assert new_cursor.pos == 2
        assert new_cursor.current == "\t"

    def test_skip_spaces_not_newline(self) -> None:
        """Verify skip_spaces() does not skip newlines."""
        cursor = Cursor(source="  \nhello", pos=0)
        new_cursor = cursor.skip_spaces()
        assert new_cursor.pos == 2
        assert new_cursor.current == "\n"


class TestCursorSkipWhitespaceMethod:
    """Property-based tests for Cursor.skip_whitespace() method."""

    def test_skip_whitespace_no_whitespace(self) -> None:
        """Verify skip_whitespace() returns same cursor when no whitespace."""
        cursor = Cursor(source="hello", pos=0)
        new_cursor = cursor.skip_whitespace()
        assert new_cursor.pos == 0

    def test_skip_whitespace_mixed_whitespace(self) -> None:
        """Verify skip_whitespace() skips space and newline.

        Note: CR is normalized to LF at parser entry, so skip_whitespace
        only needs to handle space and LF.
        """
        cursor = Cursor(source="  \n  hello", pos=0)
        new_cursor = cursor.skip_whitespace()
        assert new_cursor.pos == 5
        assert new_cursor.current == "h"

    def test_skip_whitespace_all_whitespace(self) -> None:
        """Verify skip_whitespace() handles all-whitespace string."""
        cursor = Cursor(source=" \n ", pos=0)
        new_cursor = cursor.skip_whitespace()
        assert new_cursor.is_eof is True

    def test_skip_whitespace_not_tab(self) -> None:
        """Verify skip_whitespace() does not skip tab."""
        cursor = Cursor(source=" \n\thello", pos=0)
        new_cursor = cursor.skip_whitespace()
        assert new_cursor.pos == 2
        assert new_cursor.current == "\t"


class TestCursorExpectMethod:
    """Property-based tests for Cursor.expect() method."""

    def test_expect_match(self) -> None:
        """Verify expect() returns new cursor when character matches."""
        cursor = Cursor(source="hello", pos=0)
        new_cursor = cursor.expect("h")
        assert new_cursor is not None
        assert new_cursor.pos == 1

    def test_expect_no_match(self) -> None:
        """Verify expect() returns None when character does not match."""
        cursor = Cursor(source="hello", pos=0)
        result = cursor.expect("x")
        assert result is None

    def test_expect_at_eof(self) -> None:
        """Verify expect() returns None at EOF."""
        cursor = Cursor(source="hello", pos=5)
        result = cursor.expect("h")
        assert result is None

    @given(st.text(min_size=1), st.characters())
    def test_expect_various_characters(self, source: str, char: str) -> None:
        """Property: expect() behavior depends on current character."""
        event(f"input_len={len(source)}")
        cursor = Cursor(source=source, pos=0)
        result = cursor.expect(char)

        matched = source[0] == char
        event(f"valid={matched}")
        if matched:
            assert result is not None
            assert result.pos == 1
        else:
            assert result is None


class TestCursorComputeLineColMethod:
    """Property-based tests for Cursor.compute_line_col() method."""

    def test_compute_line_col_first_line_first_col(self) -> None:
        """Verify compute_line_col() returns (1, 1) at position 0."""
        cursor = Cursor(source="hello", pos=0)
        line, col = cursor.compute_line_col()
        assert line == 1
        assert col == 1

    def test_compute_line_col_first_line_later_col(self) -> None:
        """Verify compute_line_col() returns correct column on first line."""
        cursor = Cursor(source="hello", pos=2)
        line, col = cursor.compute_line_col()
        assert line == 1
        assert col == 3

    def test_compute_line_col_second_line(self) -> None:
        """Verify compute_line_col() returns (2, 1) at start of second line."""
        cursor = Cursor(source="line1\nline2", pos=6)
        line, col = cursor.compute_line_col()
        assert line == 2
        assert col == 1

    def test_compute_line_col_second_line_middle(self) -> None:
        """Verify compute_line_col() returns correct position on second line."""
        cursor = Cursor(source="line1\nline2", pos=8)
        line, col = cursor.compute_line_col()
        assert line == 2
        assert col == 3

    def test_compute_line_col_multiple_lines(self) -> None:
        """Verify compute_line_col() handles multiple newlines."""
        cursor = Cursor(source="a\nb\nc\nd", pos=6)  # Position at 'd'
        line, col = cursor.compute_line_col()
        assert line == 4
        assert col == 1


class TestParseResultDataclass:
    """Property-based tests for ParseResult dataclass."""

    def test_parse_result_frozen(self) -> None:
        """Property: ParseResult instances are immutable (frozen)."""
        cursor = Cursor(source="test", pos=0)
        result: ParseResult[str] = ParseResult(value="parsed", cursor=cursor)

        with pytest.raises((AttributeError, TypeError)):
            result.value = "changed"  # type: ignore[misc]

    @given(st.text(), st.text(), st.integers(min_value=0, max_value=100))
    def test_parse_result_construction_string(
        self, value: str, source: str, pos: int
    ) -> None:
        """Property: ParseResult can be constructed with string values."""
        event(f"input_len={len(source)}")
        event(f"offset={pos}")
        pos = min(pos, len(source))
        cursor = Cursor(source=source, pos=pos)
        result: ParseResult[str] = ParseResult(value=value, cursor=cursor)
        assert result.value == value
        assert result.cursor is cursor

    @given(st.integers())
    def test_parse_result_construction_int(self, value: int) -> None:
        """Property: ParseResult can be constructed with int values."""
        event(f"value={value}")
        cursor = Cursor(source="test", pos=0)
        result: ParseResult[int] = ParseResult(value=value, cursor=cursor)
        assert result.value == value

    def test_parse_result_generic_type(self) -> None:
        """Verify ParseResult works with various types."""
        cursor = Cursor(source="test", pos=0)

        # String type
        str_result: ParseResult[str] = ParseResult(value="hello", cursor=cursor)
        assert str_result.value == "hello"

        # List type
        list_result: ParseResult[list[int]] = ParseResult(value=[1, 2, 3], cursor=cursor)
        assert list_result.value == [1, 2, 3]

        # Tuple type
        tuple_result: ParseResult[tuple[str, int]] = ParseResult(
            value=("test", 42), cursor=cursor
        )
        assert tuple_result.value == ("test", 42)


class TestParseErrorDataclass:
    """Property-based tests for ParseError dataclass."""

    def test_parse_error_frozen(self) -> None:
        """Property: ParseError instances are immutable (frozen)."""
        cursor = Cursor(source="test", pos=0)
        error = ParseError(message="error", cursor=cursor)

        with pytest.raises((AttributeError, TypeError)):
            error.message = "changed"  # type: ignore[misc]

    @given(st.text(), st.text())
    def test_parse_error_construction_minimal(self, message: str, source: str) -> None:
        """Property: ParseError can be constructed with message and cursor only."""
        event(f"input_len={len(source)}")
        cursor = Cursor(source=source, pos=0)
        error = ParseError(message=message, cursor=cursor)
        assert error.message == message
        assert error.cursor is cursor
        assert error.expected == ()

    def test_parse_error_construction_with_expected(self) -> None:
        """Verify ParseError can be constructed with expected tokens."""
        cursor = Cursor(source="test", pos=0)
        error = ParseError(message="error", cursor=cursor, expected=("}", "]"))
        assert error.expected == ("}", "]")


class TestParseErrorFormatError:
    """Property-based tests for ParseError.format_error() method."""

    def test_format_error_simple(self) -> None:
        """Verify format_error() returns formatted error string."""
        cursor = Cursor(source="hello", pos=2)
        error = ParseError(message="Test error", cursor=cursor)
        formatted = error.format_error()
        assert "1:3:" in formatted
        assert "Test error" in formatted

    def test_format_error_with_expected(self) -> None:
        """Verify format_error() includes expected tokens."""
        cursor = Cursor(source="hello", pos=0)
        error = ParseError(message="Unexpected", cursor=cursor, expected=("}", "]"))
        formatted = error.format_error()
        assert "expected:" in formatted
        assert "'}'" in formatted
        assert "']'" in formatted

    def test_format_error_multiline_source(self) -> None:
        """Verify format_error() shows correct line number for multiline source."""
        cursor = Cursor(source="line1\nline2\nline3", pos=6)  # Start of line2
        error = ParseError(message="Error on line 2", cursor=cursor)
        formatted = error.format_error()
        assert "2:1:" in formatted


class TestParseErrorFormatWithContext:
    """Property-based tests for ParseError.format_with_context() method."""

    def test_format_with_context_simple(self) -> None:
        """Verify format_with_context() shows source context."""
        cursor = Cursor(source="hello world", pos=6)
        error = ParseError(message="Test error", cursor=cursor)
        formatted = error.format_with_context()

        assert "1:7: Test error" in formatted
        assert "hello world" in formatted
        assert "^" in formatted  # Pointer

    def test_format_with_context_multiline(self) -> None:
        """Verify format_with_context() shows multiple lines."""
        source = "line1\nline2\nline3"
        cursor = Cursor(source=source, pos=6)  # Start of line2
        error = ParseError(message="Error", cursor=cursor)
        formatted = error.format_with_context()

        assert "line1" in formatted
        assert "line2" in formatted
        assert "line3" in formatted
        assert "^" in formatted

    def test_format_with_context_custom_context_lines(self) -> None:
        """Verify format_with_context() respects context_lines parameter."""
        source = "line1\nline2\nline3\nline4\nline5"
        cursor = Cursor(source=source, pos=12)  # Line 3
        error = ParseError(message="Error", cursor=cursor)

        # With context_lines=1, should show lines 2-4
        formatted = error.format_with_context(context_lines=1)
        assert "line2" in formatted
        assert "line3" in formatted
        assert "line4" in formatted

    def test_format_with_context_pointer_alignment(self) -> None:
        """Verify format_with_context() aligns pointer correctly."""
        cursor = Cursor(source="hello", pos=2)
        error = ParseError(message="Error", cursor=cursor)
        formatted = error.format_with_context()

        lines = formatted.split("\n")
        # Find the line with hello and the pointer line
        for i, line in enumerate(lines):
            if "hello" in line and i + 1 < len(lines):
                # Next line should have pointer at correct position
                pointer_line = lines[i + 1]
                # The pointer should be at column 3 (accounting for line number prefix)
                assert "^" in pointer_line


class TestCursorIntegrationContracts:
    """Integration contract tests for Cursor methods working together."""

    def test_cursor_parse_word(self) -> None:
        """Integration: Use cursor to parse a word."""
        cursor = Cursor(source="hello world", pos=0)
        start_pos = cursor.pos

        # Advance until space
        while not cursor.is_eof and cursor.current != " ":
            cursor = cursor.advance()

        # Extract word
        word = Cursor(source="hello world", pos=start_pos).slice_to(cursor.pos)
        assert word == "hello"

    def test_cursor_skip_and_parse(self) -> None:
        """Integration: Skip whitespace then parse."""
        cursor = Cursor(source="   hello", pos=0)

        # Skip spaces
        cursor = cursor.skip_spaces()

        # Parse word
        start_pos = cursor.pos
        while not cursor.is_eof and cursor.current.isalpha():
            cursor = cursor.advance()

        word = Cursor(source="   hello", pos=start_pos).slice_to(cursor.pos)
        assert word == "hello"

    def test_cursor_peek_and_expect(self) -> None:
        """Integration: Use peek to look ahead, then expect."""
        cursor = Cursor(source="hello", pos=0)

        # Peek ahead
        assert cursor.peek(0) == "h"
        assert cursor.peek(1) == "e"

        # Expect and advance
        new_cursor = cursor.expect("h")
        assert new_cursor is not None
        assert new_cursor.current == "e"
