"""Tests for comment blank line separation logic (FTL-PARSER-001).

Per Fluent specification, adjacent comments should only be joined if there are no
blank lines between them. This module tests the fix for _has_blank_line_between
which incorrectly required two newlines in the checked region instead of one.
"""


from ftllexengine.syntax.ast import Comment, Message
from ftllexengine.syntax.parser import FluentParserV1


class TestCommentBlankLineSeparation:
    """Test comment separation with and without blank lines."""

    def test_adjacent_comments_no_blank_line_merge(self) -> None:
        """Adjacent comments with no blank line should merge into single Comment."""
        parser = FluentParserV1()
        source = "# A\n# B"
        resource = parser.parse(source)

        # Should produce a single merged Comment entry
        comments = [e for e in resource.entries if isinstance(e, Comment)]
        assert len(comments) == 1
        assert comments[0].content == "A\nB"

    def test_comments_with_single_blank_line_separate(self) -> None:
        """Comments separated by single blank line should NOT merge."""
        parser = FluentParserV1()
        source = "# A\n\n# B"
        resource = parser.parse(source)

        # Should produce two separate Comment entries
        comments = [e for e in resource.entries if isinstance(e, Comment)]
        assert len(comments) == 2
        assert comments[0].content == "A"
        assert comments[1].content == "B"

    def test_comments_with_double_blank_line_separate(self) -> None:
        """Comments separated by multiple blank lines should NOT merge."""
        parser = FluentParserV1()
        source = "# A\n\n\n# B"
        resource = parser.parse(source)

        # Should produce two separate Comment entries
        comments = [e for e in resource.entries if isinstance(e, Comment)]
        assert len(comments) == 2
        assert comments[0].content == "A"
        assert comments[1].content == "B"

    def test_three_comments_mixed_separation(self) -> None:
        """Test multiple comments with mixed separation patterns."""
        parser = FluentParserV1()
        # A and B are adjacent (no blank line) -> merge
        # B (merged with A) and C have blank line -> separate
        source = "# A\n# B\n\n# C"
        resource = parser.parse(source)

        # Should produce two Comment entries: (A+B) and C
        comments = [e for e in resource.entries if isinstance(e, Comment)]
        assert len(comments) == 2
        assert comments[0].content == "A\nB"
        assert comments[1].content == "C"

    def test_blank_line_with_spaces_counts_as_blank(self) -> None:
        """Blank line with only spaces should still prevent merging."""
        parser = FluentParserV1()
        source = "# A\n  \n# B"
        resource = parser.parse(source)

        # Should produce two separate Comment entries
        comments = [e for e in resource.entries if isinstance(e, Comment)]
        assert len(comments) == 2
        assert comments[0].content == "A"
        assert comments[1].content == "B"

    def test_comment_attached_to_message_no_blank_line(self) -> None:
        """Comment attached to message with no blank line."""
        parser = FluentParserV1()
        source = "# Comment\nmsg = value"
        resource = parser.parse(source)

        # Should produce one Message with attached comment
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)
        assert resource.entries[0].comment is not None
        assert resource.entries[0].comment.content == "Comment"

    def test_comment_not_attached_to_message_with_blank_line(self) -> None:
        """Comment separated from message by blank line should be standalone."""
        parser = FluentParserV1()
        source = "# Standalone\n\nmsg = value"
        resource = parser.parse(source)

        # Should produce a standalone Comment and a Message
        assert len(resource.entries) == 2
        assert isinstance(resource.entries[0], Comment)
        assert resource.entries[0].content == "Standalone"
        assert isinstance(resource.entries[1], Message)
        assert resource.entries[1].comment is None

    def test_multiple_comments_before_message_no_blank(self) -> None:
        """Multiple adjacent comments before message should all attach."""
        parser = FluentParserV1()
        source = "# Line 1\n# Line 2\n# Line 3\nmsg = value"
        resource = parser.parse(source)

        # Should produce one Message with multi-line attached comment
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)
        assert resource.entries[0].comment is not None
        assert resource.entries[0].comment.content == "Line 1\nLine 2\nLine 3"

    def test_multiple_comments_before_message_with_blank(self) -> None:
        """Comments with blank line before message should separate."""
        parser = FluentParserV1()
        source = "# Standalone 1\n# Standalone 2\n\n# Attached\nmsg = value"
        resource = parser.parse(source)

        # Should produce: merged standalone Comment, Message with attached comment
        assert len(resource.entries) == 2
        # First entry: standalone merged comments
        assert isinstance(resource.entries[0], Comment)
        assert resource.entries[0].content == "Standalone 1\nStandalone 2"
        # Second entry: message with its own comment
        assert isinstance(resource.entries[1], Message)
        assert resource.entries[1].comment is not None
        assert resource.entries[1].comment.content == "Attached"
