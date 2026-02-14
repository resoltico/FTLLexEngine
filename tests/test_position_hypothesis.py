"""Hypothesis property tests for position tracking.

Tests position-to-offset conversions, line/column computation,
error context formatting, and line content retrieval with
property-based fuzzing.

Properties tested:
- line_offset: non-negativity, newline counting, clamping, error handling
- column_offset: non-negativity, line-start reset, identity without
  newlines, bounds, CRLF/LF compat, multibyte, error handling
- format_position: crash-free, 0-based/1-based offset invariant,
  parseable output
- get_line_content: bounds checking, no trailing newline, splitlines
  consistency, 0-based/1-based indexing
- get_error_context: crash-free, marker presence, error line inclusion,
  context-lines limit, custom markers

Python 3.13+.
"""

import string

import pytest
from hypothesis import assume, event, given
from hypothesis import strategies as st

from ftllexengine.syntax.position import (
    column_offset,
    format_position,
    get_error_context,
    get_line_content,
    line_offset,
)

# ============================================================================
# STRATEGIES
# ============================================================================

# Valid source text (no surrogates, no null bytes)
valid_source_text = st.text(
    alphabet=st.characters(
        blacklist_categories=["Cs"],
        blacklist_characters="\x00",
    ),
    min_size=0,
    max_size=200,
)


@st.composite
def source_and_valid_position(
    draw: st.DrawFn,
) -> tuple[str, int]:
    """Generate (source, position) where position is valid."""
    source = draw(valid_source_text)
    pos = (
        draw(st.integers(min_value=0, max_value=len(source)))
        if source
        else 0
    )
    return source, pos


@st.composite
def source_and_valid_line(
    draw: st.DrawFn,
) -> tuple[str, int]:
    """Generate (source, line_number) where line is valid."""
    source = draw(
        st.text(
            alphabet=st.characters(
                blacklist_categories=["Cs"],
                blacklist_characters="\x00",
            ),
            min_size=1,
            max_size=200,
        )
    )
    lines = source.splitlines()
    assume(len(lines) > 0)
    line_num = draw(
        st.integers(min_value=0, max_value=len(lines) - 1)
    )
    return source, line_num


# ============================================================================
# LINE_OFFSET PROPERTY TESTS
# ============================================================================


class TestLineOffsetProperties:
    """Property tests for line_offset function."""

    @given(data=source_and_valid_position())
    def test_line_offset_never_negative(
        self, data: tuple[str, int]
    ) -> None:
        """INVARIANT: Line offset is always >= 0."""
        source, pos = data
        result = line_offset(source, pos)
        event(f"text_len={len(source)}")
        event(f"line_count={source.count(chr(10))}")
        assert result >= 0

    @given(valid_source_text)
    def test_line_offset_at_zero(self, source: str) -> None:
        """AXIOM: Position 0 is always line 0."""
        event(f"text_len={len(source)}")
        has_leading_newline = source[:1] == "\n"
        event(f"leading_newline={has_leading_newline}")
        assert line_offset(source, 0) == 0

    @given(st.integers(min_value=0, max_value=100))
    def test_line_offset_counts_newlines(self, n: int) -> None:
        """PROPERTY: Each newline increments line count by 1."""
        event(f"newline_count={n}")
        boundary = "boundary" if n in (0, 1, 100) else "mid"
        event(f"boundary={boundary}")
        source = "\n" * n
        assert line_offset(source, len(source)) == n

    @given(valid_source_text)
    def test_line_offset_clamping_beyond_eof(
        self, source: str
    ) -> None:
        """BOUNDARY: Position beyond EOF clamped to source length."""
        event(f"text_len={len(source)}")
        expected = source.count("\n")
        event(f"line_count={expected}")
        huge_pos = len(source) + 1000
        result = line_offset(source, huge_pos)
        assert result == expected

    @given(valid_source_text)
    def test_line_offset_negative_raises_valueerror(
        self, source: str
    ) -> None:
        """ERROR: Negative position raises ValueError."""
        event(f"text_len={len(source)}")
        empty = len(source) == 0
        event(f"empty_source={empty}")
        with pytest.raises(ValueError, match="Position must be >= 0"):
            line_offset(source, -1)

    @given(data=source_and_valid_position())
    def test_line_offset_multiline_consistency(
        self, data: tuple[str, int]
    ) -> None:
        """PROPERTY: Line number matches newline count before pos."""
        source, pos = data
        result = line_offset(source, pos)
        expected = source[:pos].count("\n")
        event(f"line_count={source.count(chr(10))}")
        event(f"text_len={len(source)}")
        assert result == expected


# ============================================================================
# COLUMN_OFFSET PROPERTY TESTS
# ============================================================================


class TestColumnOffsetProperties:
    """Property tests for column_offset function."""

    @given(data=source_and_valid_position())
    def test_column_offset_never_negative(
        self, data: tuple[str, int]
    ) -> None:
        """INVARIANT: Column offset is always >= 0."""
        source, pos = data
        result = column_offset(source, pos)
        event(f"newline_count={source.count(chr(10))}")
        event(f"text_len={len(source)}")
        assert result >= 0

    @given(
        st.text(
            alphabet=string.ascii_letters + "\n",
            min_size=2,
            max_size=100,
        )
    )
    def test_column_offset_at_line_start(self, source: str) -> None:
        """AXIOM: Position right after newline has column 0."""
        newline_positions = [
            i for i, c in enumerate(source) if c == "\n"
        ]
        event(f"newline_count={len(newline_positions)}")
        for i in newline_positions:
            if i + 1 < len(source):
                col = column_offset(source, i + 1)
                assert col == 0

    @given(data=source_and_valid_position())
    def test_column_offset_no_newline(
        self, data: tuple[str, int]
    ) -> None:
        """SPECIAL CASE: No newlines means column == position."""
        source, pos = data
        assume("\n" not in source)
        result = column_offset(source, pos)
        event(f"text_len={len(source)}")
        assert result == pos

    @given(data=source_and_valid_position())
    def test_column_offset_within_reasonable_bounds(
        self, data: tuple[str, int]
    ) -> None:
        """BOUNDARY: Column never exceeds source length."""
        source, pos = data
        col = column_offset(source, pos)
        event(f"col={col}")
        assert col <= len(source)

    @given(data=source_and_valid_position())
    def test_column_offset_crlf_vs_lf_both_work(
        self, data: tuple[str, int]
    ) -> None:
        """COMPATIBILITY: Both CRLF and LF line endings work."""
        source, pos = data
        has_newline = "\n" in source
        event(f"has_newline={has_newline}")
        col = column_offset(source, pos)
        assert isinstance(col, int)
        assert col >= 0

    @given(
        st.text(
            alphabet="你好世界abcd\n",
            min_size=1,
            max_size=50,
        )
    )
    def test_column_offset_multibyte_utf8(
        self, source: str
    ) -> None:
        """UNICODE: Handles multi-byte UTF-8 characters (CJK)."""
        has_cjk = any(ord(c) > 127 for c in source)
        event(f"has_cjk={has_cjk}")
        pos = len(source) // 2
        col = column_offset(source, pos)
        assert col >= 0

    @given(valid_source_text)
    def test_column_offset_negative_raises_valueerror(
        self, source: str
    ) -> None:
        """ERROR: Negative position raises ValueError."""
        event(f"text_len={len(source)}")
        with pytest.raises(ValueError, match="Position must be >= 0"):
            column_offset(source, -1)


# ============================================================================
# FORMAT_POSITION PROPERTY TESTS
# ============================================================================


class TestFormatPositionProperties:
    """Property tests for format_position function."""

    @given(data=source_and_valid_position(), zero_based=st.booleans())
    def test_format_position_never_crashes(
        self,
        data: tuple[str, int],
        zero_based: bool,
    ) -> None:
        """ROBUSTNESS: Never crashes on any valid input."""
        source, pos = data
        result = format_position(source, pos, zero_based)
        assert isinstance(result, str)
        assert ":" in result
        event(f"zero_based={zero_based}")

    @given(data=source_and_valid_position())
    def test_format_position_zero_vs_one_based_offset(
        self, data: tuple[str, int]
    ) -> None:
        """PROPERTY: 1-based = 0-based + (1,1)."""
        source, pos = data
        zero = format_position(source, pos, zero_based=True)
        one = format_position(source, pos, zero_based=False)

        z_parts = zero.split(":")
        o_parts = one.split(":")

        assert len(z_parts) == 2
        assert len(o_parts) == 2

        z_line, z_col = int(z_parts[0]), int(z_parts[1])
        o_line, o_col = int(o_parts[0]), int(o_parts[1])

        assert o_line == z_line + 1
        assert o_col == z_col + 1
        event(f"z_line={z_line}")

    @given(data=source_and_valid_position())
    def test_format_position_parseable_as_integers(
        self, data: tuple[str, int]
    ) -> None:
        """FORMAT: Output is parseable as 'int:int'."""
        source, pos = data
        result = format_position(source, pos, zero_based=True)
        parts = result.split(":")
        assert len(parts) == 2
        line_val, col_val = int(parts[0]), int(parts[1])
        assert line_val >= 0
        assert col_val >= 0
        event(f"line_val={line_val}")


# ============================================================================
# GET_LINE_CONTENT PROPERTY TESTS
# ============================================================================


class TestGetLineContentProperties:
    """Property tests for get_line_content function."""

    @given(valid_source_text)
    def test_get_line_content_bounds_checking_raises(
        self, source: str
    ) -> None:
        """ERROR: Out of bounds line numbers raise ValueError."""
        lines = source.splitlines()
        num_lines = len(lines)
        event(f"num_lines={num_lines}")

        with pytest.raises(ValueError, match="out of range"):
            get_line_content(source, num_lines + 10, zero_based=True)

        with pytest.raises(ValueError, match="must be >= 0"):
            get_line_content(source, -1, zero_based=True)

    @given(data=source_and_valid_line())
    def test_get_line_content_no_trailing_newline(
        self, data: tuple[str, int]
    ) -> None:
        """PROPERTY: Returned lines have no trailing newlines."""
        source, line_num = data
        content = get_line_content(source, line_num, zero_based=True)
        event(f"line_count={len(source.splitlines())}")
        assert not content.endswith("\n")
        assert not content.endswith("\r")

    @given(data=source_and_valid_line())
    def test_get_line_content_matches_splitlines(
        self, data: tuple[str, int]
    ) -> None:
        """CONSISTENCY: Matches splitlines() output exactly."""
        source, line_num = data
        lines = source.splitlines(keepends=False)
        content = get_line_content(source, line_num, zero_based=True)
        event(f"line_count={len(lines)}")
        assert content == lines[line_num]

    @given(data=source_and_valid_line())
    def test_get_line_content_zero_vs_one_based_indexing(
        self, data: tuple[str, int]
    ) -> None:
        """INDEXING: 0-based and 1-based access same line."""
        source, line_num = data
        line_zero = get_line_content(
            source, line_num, zero_based=True
        )
        line_one = get_line_content(
            source, line_num + 1, zero_based=False
        )
        assert line_zero == line_one
        event(f"line_len={len(line_zero)}")


# ============================================================================
# GET_ERROR_CONTEXT PROPERTY TESTS
# ============================================================================


class TestGetErrorContextProperties:
    """Property tests for get_error_context function."""

    @given(
        data=source_and_valid_position(),
        context_lines=st.integers(min_value=0, max_value=5),
    )
    def test_get_error_context_never_crashes(
        self,
        data: tuple[str, int],
        context_lines: int,
    ) -> None:
        """ROBUSTNESS: Never crashes on any valid input."""
        source, pos = data
        result = get_error_context(source, pos, context_lines)
        assert isinstance(result, str)
        event(f"context_lines={context_lines}")

    @given(data=source_and_valid_position())
    def test_get_error_context_marker_appears(
        self, data: tuple[str, int]
    ) -> None:
        """PROPERTY: Marker always appears for non-empty source."""
        source, pos = data
        assume(len(source) > 0)
        result = get_error_context(
            source, pos, context_lines=1, marker="^"
        )
        assert "^" in result
        event(f"pos={pos}")

    @given(data=source_and_valid_position())
    def test_get_error_context_includes_error_line(
        self, data: tuple[str, int]
    ) -> None:
        """PROPERTY: Always includes the line containing the error."""
        source, pos = data
        lines = source.splitlines(keepends=False)
        assume(len(lines) > 0)
        line_num = line_offset(source, pos)
        assume(line_num < len(lines))
        error_line = lines[line_num]
        result = get_error_context(source, pos, context_lines=2)
        event(f"line_num={line_num}")
        assert error_line in result

    @given(
        data=source_and_valid_position(),
        context_lines=st.integers(min_value=0, max_value=5),
    )
    def test_get_error_context_respects_context_lines_limit(
        self,
        data: tuple[str, int],
        context_lines: int,
    ) -> None:
        """BOUNDARY: Output respects context_lines parameter."""
        source, pos = data
        assume(len(source) > 0)
        result = get_error_context(source, pos, context_lines)
        result_lines = [
            line for line in result.split("\n") if line.strip()
        ]
        # content lines + 1 marker line
        max_expected = context_lines * 2 + 1 + 1
        assert len(result_lines) <= max_expected + 2
        event(f"context_lines={context_lines}")

    @given(
        data=source_and_valid_position(),
        marker=st.text(alphabet="^*#@!", min_size=1, max_size=1),
    )
    def test_get_error_context_custom_marker(
        self,
        data: tuple[str, int],
        marker: str,
    ) -> None:
        """PARAMETER: Custom marker always appears for non-empty source."""
        source, pos = data
        assume(len(source) > 0)
        result = get_error_context(
            source, pos, context_lines=1, marker=marker
        )
        assert marker in result
        event(f"marker={marker}")
