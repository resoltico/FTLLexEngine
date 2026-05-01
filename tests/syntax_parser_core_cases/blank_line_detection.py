# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_core.py."""

from tests.syntax_parser_core_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TestBlankLineDetection
# ============================================================================


class TestBlankLineDetection:
    """Direct tests for ``_has_blank_line_between``.

    The function checks whether a region of the source string contains
    at least one newline character. After parse_comment consumes the
    trailing newline, any remaining newline in the gap indicates a
    blank line was present between comments.
    """

    # -- Positive: regions containing newlines ----------------------------

    def test_empty_region_has_no_blank_line(self) -> None:
        """Empty region (start == end) contains no newline."""
        source = "content"
        assert _has_blank_line_between(source, 0, 0) is False

    def test_consecutive_newlines(self) -> None:
        """Two consecutive newlines in region are detected."""
        source = "\n\n"
        assert _has_blank_line_between(source, 0, len(source)) is True

    def test_single_newline_in_region(self) -> None:
        """Single newline indicates blank line (trailing LF already consumed)."""
        source = "line1\nline2"
        assert _has_blank_line_between(source, 0, len(source)) is True

    def test_newline_space_newline(self) -> None:
        """Newline-space-newline sequence contains a newline."""
        source = "line1\n \nline2"
        assert _has_blank_line_between(source, 0, len(source)) is True

    def test_multiple_spaces_between_newlines(self) -> None:
        """Multiple spaces between newlines still contains newlines."""
        source = "start\n     \nend"
        assert _has_blank_line_between(source, 0, len(source)) is True

    def test_consecutive_newlines_at_start(self) -> None:
        """Consecutive newlines at start of region."""
        source = "\n\ncontent"
        assert _has_blank_line_between(source, 0, len(source)) is True

    def test_newline_at_end_only(self) -> None:
        """Single newline at end of content is detected."""
        source = "content\n"
        assert _has_blank_line_between(source, 0, len(source)) is True

    def test_alternating_newlines_and_spaces(self) -> None:
        """Alternating pattern of newlines and spaces."""
        source = "\n \n \n"
        assert _has_blank_line_between(source, 0, len(source)) is True

    def test_content_between_newlines(self) -> None:
        """Content between newlines does not prevent newline detection."""
        source = "\nX\n"
        assert _has_blank_line_between(source, 0, len(source)) is True

    def test_tab_between_newlines(self) -> None:
        """Tab between newlines does not prevent newline detection."""
        source = "\n\t\n"
        assert _has_blank_line_between(source, 0, len(source)) is True

    # -- Negative: regions without newlines --------------------------------

    def test_spaces_only_no_newlines(self) -> None:
        """Region with only spaces has no newline."""
        source = "content     content"
        assert _has_blank_line_between(source, 7, 12) is False

    def test_no_newline_ascii_content(self) -> None:
        """Plain ASCII content without newlines."""
        source = "abcdefghijklmnop"
        assert _has_blank_line_between(source, 0, len(source)) is False

    def test_mixed_whitespace_no_newline(self) -> None:
        """Mixed spaces without newline in subregion."""
        source = "start    end"
        assert _has_blank_line_between(source, 5, 9) is False

    # -- Region boundary handling ------------------------------------------

    def test_blank_line_partially_in_region(self) -> None:
        """Region containing newlines is detected."""
        source = "prefix\n\nsuffix"
        assert _has_blank_line_between(source, 6, 8) is True

    def test_blank_line_before_region(self) -> None:
        """Newlines before region are not detected."""
        source = "\n\ncontent"
        assert _has_blank_line_between(source, 2, len(source)) is False

    def test_blank_line_after_region(self) -> None:
        """Newlines after region are not detected."""
        source = "content\n\n"
        assert _has_blank_line_between(source, 0, 7) is False

    # -- Comment merging gap scenarios -------------------------------------

    def test_comment_gap_two_newlines(self) -> None:
        """Two newlines in a row create a blank line gap."""
        source = "\n\n"
        assert _has_blank_line_between(source, 0, len(source)) is True

    def test_comment_gap_empty(self) -> None:
        """Zero-length gap between consecutive comments has no blank line."""
        comment1_end = len("# Comment1\n")
        source = "# Comment1\n# Comment2\n"
        assert _has_blank_line_between(
            source, comment1_end, comment1_end
        ) is False

    def test_comment_gap_whitespace_only_line(self) -> None:
        """Whitespace-only line between newlines is a blank line."""
        source = "\n  \n"
        assert _has_blank_line_between(source, 0, len(source)) is True
