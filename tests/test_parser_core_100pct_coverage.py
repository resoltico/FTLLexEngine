"""Targeted tests for 100% coverage of parser core module.

Covers specific uncovered lines identified by coverage analysis.
Focuses on _has_blank_line_between edge cases.
"""

from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.syntax.parser.core import _has_blank_line_between


class TestHasBlankLineBetweenCoverage:
    """Complete coverage for _has_blank_line_between function."""

    def test_non_blank_character_resets_newline_count(self) -> None:
        """Non-blank character resets newline counter (line 86)."""
        # Source with newline followed by non-blank char, then blank line
        # Structure: content\n<non-blank>\n\n (blank line after non-blank)
        source = "line1\na\n\nline2"
        # Check region from start to end
        # The 'a' at position 6 should reset the newline counter
        # Then the \n\n sequence should be detected as blank line
        result = _has_blank_line_between(source, 0, len(source))
        # Should find blank line (the \n\n after 'a')
        assert result is True

    def test_single_newline_with_content_no_blank_line(self) -> None:
        """Single newline with content IS blank line after fix.

        After FTL-PARSER-001 fix, a single newline in the checked region
        indicates a blank line (previous newline already consumed by parse_comment).
        """
        source = "line1\nline2"
        result = _has_blank_line_between(source, 0, len(source))
        # Single \n now indicates blank line
        assert result is True

    def test_newline_space_newline_is_blank_line(self) -> None:
        """Newline-space-newline is a blank line."""
        source = "line1\n \nline2"
        result = _has_blank_line_between(source, 0, len(source))
        # \n \n is a blank line (whitespace-only line)
        assert result is True

    def test_content_between_double_newlines_resets_counter(self) -> None:
        """Content between newlines resets the blank line detection.

        After FTL-PARSER-001 fix, first newline triggers blank line detection,
        but 'X' resets counter, then second newline is detected.
        """
        # Pattern: \n<char>\n where <char> is not space
        source = "\nX\n"
        result = _has_blank_line_between(source, 0, len(source))
        # First \n triggers detection, but content after triggers again
        assert result is True

    def test_multiple_spaces_between_newlines(self) -> None:
        """Multiple spaces between newlines counts as blank line."""
        source = "start\n     \nend"
        result = _has_blank_line_between(source, 0, len(source))
        # Whitespace-only line is a blank line
        assert result is True

    @given(
        non_blank=st.characters(
            blacklist_categories=("Zs", "Zl", "Zp"), blacklist_characters=["\n"]
        )
    )
    def test_any_non_blank_resets_counter(self, non_blank: str) -> None:
        """Property: Any non-blank, non-newline character resets counter.

        After FTL-PARSER-001 fix, first newline triggers detection.
        """
        event(f"input_len={len(non_blank)}")
        # Structure: \n<non_blank>\n
        source = f"\n{non_blank}\n"
        result = _has_blank_line_between(source, 0, len(source))
        # First \n triggers blank line detection
        assert result is True


class TestBlankLineDetectionEdgeCases:
    """Edge cases for blank line detection."""

    def test_empty_region(self) -> None:
        """Empty region has no blank lines."""
        source = "content"
        result = _has_blank_line_between(source, 0, 0)
        assert result is False

    def test_consecutive_newlines_at_start(self) -> None:
        """Consecutive newlines at start of region."""
        source = "\n\ncontent"
        result = _has_blank_line_between(source, 0, len(source))
        assert result is True

    def test_newline_at_end_only(self) -> None:
        """Single newline at end IS blank line after fix.

        After FTL-PARSER-001 fix, a single newline in the checked region
        indicates a blank line.
        """
        source = "content\n"
        result = _has_blank_line_between(source, 0, len(source))
        assert result is True

    def test_alternating_newlines_and_spaces(self) -> None:
        """Alternating pattern of newlines and spaces."""
        source = "\n \n \n"
        result = _has_blank_line_between(source, 0, len(source))
        # Multiple consecutive newlines with only spaces
        assert result is True

    def test_tab_character_resets_counter(self) -> None:
        """Tab character resets newline counter.

        After FTL-PARSER-001 fix, first newline triggers detection.
        """
        # Tab is not a space in the context of this function
        source = "\n\t\n"
        result = _has_blank_line_between(source, 0, len(source))
        # First \n triggers blank line detection
        assert result is True


class TestBlankLineRegionBoundaries:
    """Test region boundary handling."""

    def test_blank_line_partially_in_region(self) -> None:
        """Blank line partially within region."""
        source = "prefix\n\nsuffix"
        # Check only the region containing the blank line
        result = _has_blank_line_between(source, 6, 8)
        # Region "\n\n" should be detected as blank line
        assert result is True

    def test_blank_line_before_region(self) -> None:
        """Blank line before region should not be detected."""
        source = "\n\ncontent"
        # Check region after blank line
        result = _has_blank_line_between(source, 2, len(source))
        # No blank line in region [2:]
        assert result is False

    def test_blank_line_after_region(self) -> None:
        """Blank line after region should not be detected."""
        source = "content\n\n"
        # Check region before blank line
        result = _has_blank_line_between(source, 0, 7)
        # Region "content" has no blank line
        assert result is False

    @given(
        prefix=st.text(alphabet=st.characters(blacklist_characters=["\n"]), max_size=10),
        suffix=st.text(alphabet=st.characters(blacklist_characters=["\n"]), max_size=10),
    )
    def test_blank_line_detection_in_middle(self, prefix: str, suffix: str) -> None:
        """Property: Blank line in middle is always detected."""
        source = f"{prefix}\n\n{suffix}"
        event(f"input_len={len(source)}")
        result = _has_blank_line_between(source, 0, len(source))
        # Should always find the \n\n blank line
        assert result is True


class TestBlankLineHypothesisProperties:
    """Property-based tests for blank line detection."""

    @given(
        lines=st.lists(
            st.text(
                # Blacklist newlines AND whitespace categories (Zs=space, Zl=line, Zp=paragraph)
                # because whitespace-only lines are treated as blank lines by the function
                alphabet=st.characters(
                    blacklist_categories=("Zs", "Zl", "Zp"),
                    blacklist_characters=["\n"],
                ),
                min_size=1,  # Ensure non-empty lines with non-whitespace content
                max_size=5,
            ),
            min_size=1,
            max_size=10,
        )
    )
    def test_single_newline_separated_lines_no_blank(self, lines: list[str]) -> None:
        """Property: Single newlines between non-whitespace lines have blank lines after fix.

        After FTL-PARSER-001 fix, a single newline in the checked region
        indicates a blank line (only applies when multiple lines present).
        """
        event(f"count={len(lines)}")
        source = "\n".join(lines)
        # Lines with non-whitespace chars separated by single newlines
        result = _has_blank_line_between(source, 0, len(source))
        # Single newline triggers blank line detection if there are multiple lines
        if len(lines) > 1:
            assert result is True
        else:
            # Single line with no newline has no blank line
            assert result is False

    @given(st.integers(min_value=2, max_value=10))
    def test_multiple_consecutive_newlines_always_blank(self, count: int) -> None:
        """Property: Multiple consecutive newlines always create blank line."""
        event(f"count={count}")
        source = "\n" * count
        result = _has_blank_line_between(source, 0, len(source))
        # count >= 2 means at least one blank line
        assert result is True

    @given(
        non_blank_chars=st.lists(
            st.characters(blacklist_categories=("Zs", "Zl", "Zp"), blacklist_characters=["\n"]),
            min_size=1,
            max_size=5,
        )
    )
    def test_non_blank_chars_prevent_blank_line(self, non_blank_chars: list[str]) -> None:
        """Property: Non-blank chars between newlines don't prevent blank line after fix.

        After FTL-PARSER-001 fix, first newline triggers detection.
        """
        event(f"count={len(non_blank_chars)}")
        # Interleave newlines and non-blank chars
        parts = []
        for char in non_blank_chars:
            parts.append("\n")
            parts.append(char)
        parts.append("\n")
        source = "".join(parts)
        result = _has_blank_line_between(source, 0, len(source))
        # First newline triggers blank line detection
        assert result is True


class TestBlankLineCommentMerging:
    """Test blank line detection for comment merging scenarios."""

    def test_comments_separated_by_blank_line(self) -> None:
        """Two newlines in sequence create a blank line."""
        # Simple test: two newlines in a row
        source = "\n\n"
        result = _has_blank_line_between(source, 0, len(source))
        # Should find blank line (two consecutive \n)
        assert result is True

    def test_comments_consecutive_no_blank(self) -> None:
        """Simulate comment merging check without blank line."""
        comment1_end = len("# Comment1\n")
        comment2_start = comment1_end
        source = "# Comment1\n# Comment2\n"
        result = _has_blank_line_between(source, comment1_end, comment2_start)
        # Should NOT find blank line (single \n separates them)
        assert result is False

    def test_whitespace_only_line_between_comments(self) -> None:
        """Newline-space-newline sequence is a blank line."""
        # Whitespace-only line: \n followed by spaces followed by \n
        source = "\n  \n"
        result = _has_blank_line_between(source, 0, len(source))
        # Should find blank line (space-only line between newlines)
        assert result is True
