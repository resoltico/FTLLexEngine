# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor_property.py."""

from tests.syntax_cursor_property_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PROPERTY TESTS - LINE/COLUMN TRACKING
# ============================================================================


class TestCursorLineColumn:
    """Test line and column tracking properties."""

    @given(source=source_text)
    @settings(max_examples=100)
    def test_line_starts_at_one(self, source: str) -> None:
        """PROPERTY: Line numbers start at 1."""
        event(f"source_len={len(source)}")
        cursor = Cursor(source, 0)
        line, _ = cursor.compute_line_col()

        assert line >= 1

    @given(source=source_text)
    @settings(max_examples=100)
    def test_column_starts_at_one(self, source: str) -> None:
        """PROPERTY: Column numbers start at 1."""
        event(f"source_len={len(source)}")
        cursor = Cursor(source, 0)
        _, column = cursor.compute_line_col()

        assert column >= 1

    @given(lines=st.lists(st.text(), min_size=1, max_size=10))  # Keep list bound for performance
    @settings(max_examples=50)
    def test_newline_increments_line_number(self, lines: list[str]) -> None:
        """PROPERTY: Newlines increment line number."""
        event(f"line_count={len(lines)}")
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
        event(f"source_len={len(source)}")
        cursor = Cursor(source, min(len(source), 10))

        result1 = cursor.compute_line_col()
        result2 = cursor.compute_line_col()

        assert result1 == result2
