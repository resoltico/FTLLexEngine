"""Error path coverage tests for syntax/parser/core.py.

Covers edge cases in comment span handling and blank line detection.
"""

from __future__ import annotations

from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import Comment, Span
from ftllexengine.syntax.parser.core import FluentParserV1, _merge_comments


class TestMergeCommentsSpanEdgeCases:
    """Test comment merging with None span combinations."""

    def test_merge_comments_both_spans_none(self) -> None:
        """Merge comments when both have None spans."""
        # Create comments with None spans
        comment1 = Comment(content="First", type=CommentType.COMMENT, span=None)
        comment2 = Comment(content="Second", type=CommentType.COMMENT, span=None)

        merged = _merge_comments(comment1, comment2)

        # Should merge content correctly
        assert "First" in merged.content
        assert "Second" in merged.content
        # Span should be None when both inputs have None
        assert merged.span is None

    def test_merge_comments_first_span_none_second_has_span(self) -> None:
        """Merge comments when first has None span, second has span."""
        comment1 = Comment(content="First", type=CommentType.COMMENT, span=None)
        comment2 = Comment(
            content="Second",
            type=CommentType.COMMENT,
            span=Span(start=10, end=20),
        )

        merged = _merge_comments(comment1, comment2)

        # Should use second's span
        assert merged.span == Span(start=10, end=20)

    def test_merge_comments_second_span_none_first_has_span(self) -> None:
        """Merge comments when second has None span, first has span."""
        comment1 = Comment(
            content="First",
            type=CommentType.COMMENT,
            span=Span(start=0, end=10),
        )
        comment2 = Comment(content="Second", type=CommentType.COMMENT, span=None)

        merged = _merge_comments(comment1, comment2)

        # Should use first's span
        assert merged.span == Span(start=0, end=10)


class TestBlankLineCounterReset:
    """Test blank line counter reset logic."""

    def test_non_whitespace_char_resets_counter(self) -> None:
        """Non-whitespace character resets blank line counter."""
        parser = FluentParserV1()

        # Content with text between comments (not just whitespace)
        resource = parser.parse("""# Comment1
text content here
# Comment2""")

        # Comments should not merge due to content between them
        comments = [e for e in resource.entries if isinstance(e, Comment)]

        # Should have separate comments (not merged)
        assert len(comments) == 2

    def test_multiple_newlines_with_content(self) -> None:
        """Multiple newlines with interspersed content."""
        parser = FluentParserV1()

        resource = parser.parse("""# First


x
# Second""")

        # Content separates comments
        comments = [e for e in resource.entries if isinstance(e, Comment)]
        assert len(comments) == 2

    def test_newline_content_newline_pattern(self) -> None:
        """Pattern: newline, content, newline resets counter."""
        parser = FluentParserV1()

        # This creates: \n (from #First), then 'x' resets, then \n\n
        resource = parser.parse("""# First
x

# Second""")

        # Content between causes separation
        comments = [e for e in resource.entries if isinstance(e, Comment)]
        assert len(comments) == 2
