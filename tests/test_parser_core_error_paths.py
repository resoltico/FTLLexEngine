"""Error path coverage tests for syntax/parser/core.py.

Covers edge cases in comment span handling and blank line detection.
"""

from __future__ import annotations

from ftllexengine.syntax.ast import Comment
from ftllexengine.syntax.parser.core import FluentParserV1


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
