# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_core.py."""

from tests.syntax_parser_core_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TestCommentMerging
# ============================================================================


class TestCommentMerging:
    """Comment merging via ``FluentParserV1`` and ``_CommentAccumulator``.

    Adjacent single-hash comments without blank lines between them are
    merged into a single Comment node. Different comment types (``#``,
    ``##``, ``###``) are never merged. Blank lines separate comment groups.
    """

    # -- Parser-level merging ----------------------------------------------

    def test_adjacent_comments_merge(self) -> None:
        """Adjacent single-hash comments merge into one."""
        parser = FluentParserV1()
        resource = parser.parse("# Line 1\n# Line 2\n# Line 3\n")
        assert len(resource.entries) == 1
        comment = resource.entries[0]
        assert isinstance(comment, Comment)
        assert "Line 1" in comment.content
        assert "Line 2" in comment.content
        assert "Line 3" in comment.content

    def test_different_comment_types_dont_merge(self) -> None:
        """Comments of different types are not merged."""
        parser = FluentParserV1()
        resource = parser.parse("\n# Single\n## Group\n")
        assert len(resource.entries) == 2
        c1 = resource.entries[0]
        c2 = resource.entries[1]
        assert isinstance(c1, Comment)
        assert isinstance(c2, Comment)
        assert c1.type == CommentType.COMMENT
        assert c2.type == CommentType.GROUP

    def test_comments_separated_by_multiple_blank_lines(self) -> None:
        """Multiple blank lines prevent merging."""
        parser = FluentParserV1()
        resource = parser.parse("\n# First\n\n\n# Second\n")
        comments = [
            e for e in resource.entries if isinstance(e, Comment)
        ]
        assert len(comments) == 2

    def test_comments_separated_by_content(self) -> None:
        """Non-comment content between comments prevents merging."""
        parser = FluentParserV1()
        resource = parser.parse(
            "\n# First comment\ntext\n# Second comment\n"
        )
        comments = [
            e for e in resource.entries if isinstance(e, Comment)
        ]
        assert len(comments) == 2

    def test_content_between_comments_separates(self) -> None:
        """Text content between comments causes separation."""
        parser = FluentParserV1()
        resource = parser.parse("# Comment1\ntext content here\n# Comment2")
        comments = [
            e for e in resource.entries if isinstance(e, Comment)
        ]
        assert len(comments) == 2

    def test_multiple_newlines_with_content(self) -> None:
        """Multiple newlines with interspersed content separates."""
        parser = FluentParserV1()
        resource = parser.parse("\n# First\n\n\nx\n# Second")
        comments = [
            e for e in resource.entries if isinstance(e, Comment)
        ]
        assert len(comments) == 2

    def test_newline_content_newline_pattern(self) -> None:
        """Pattern: newline, content, newline separates comments."""
        parser = FluentParserV1()
        resource = parser.parse("# First\nx\n\n# Second")
        comments = [
            e for e in resource.entries if isinstance(e, Comment)
        ]
        assert len(comments) == 2

    def test_merged_comment_span_covers_all(self) -> None:
        """Merged comment span starts at first and ends at last."""
        parser = FluentParserV1()
        resource = parser.parse("# Line 1\n# Line 2\n# Line 3")
        comments = [
            e for e in resource.entries if isinstance(e, Comment)
        ]
        assert len(comments) == 1
        merged = comments[0]
        assert merged.span is not None
        assert merged.span.start == 0

    def test_blank_line_with_spaces_between_comments(self) -> None:
        """Comments with single blank line (containing spaces)."""
        parser = FluentParserV1()
        resource = parser.parse("# First\n\n# Second")
        comments = [
            e for e in resource.entries if isinstance(e, Comment)
        ]
        assert len(comments) >= 1

    # -- _CommentAccumulator span edge cases -------------------------------

    def test_accumulator_finalize_last_span_only(self) -> None:
        """Finalize when first_span is None but last_span is not."""
        first = Comment(
            content="First", type=CommentType.COMMENT, span=None,
        )
        acc = _CommentAccumulator(first)
        second = Comment(
            content="Second",
            type=CommentType.COMMENT,
            span=Span(start=10, end=30),
        )
        acc.add(second)
        result = acc.finalize()
        assert result.content == "First\nSecond"
        assert result.span is not None
        assert result.span.start == 10
        assert result.span.end == 30

    def test_accumulator_finalize_neither_span(self) -> None:
        """Finalize when both spans are None."""
        first = Comment(
            content="No span 1", type=CommentType.GROUP, span=None,
        )
        acc = _CommentAccumulator(first)
        second = Comment(
            content="No span 2", type=CommentType.GROUP, span=None,
        )
        acc.add(second)
        result = acc.finalize()
        assert result.content == "No span 1\nNo span 2"
        assert result.type == CommentType.GROUP
        assert result.span is None

    def test_accumulator_finalize_both_spans(self) -> None:
        """Finalize when both first and last have spans."""
        first = Comment(
            content="A",
            type=CommentType.COMMENT,
            span=Span(start=0, end=5),
        )
        acc = _CommentAccumulator(first)
        second = Comment(
            content="B",
            type=CommentType.COMMENT,
            span=Span(start=6, end=11),
        )
        acc.add(second)
        result = acc.finalize()
        assert result.content == "A\nB"
        assert result.span is not None
        assert result.span.start == 0
        assert result.span.end == 11

    # -- Comment attachment to terms ---------------------------------------

    def test_single_hash_comment_attached_to_term(self) -> None:
        """Single-hash comment immediately before term is attached."""
        parser = FluentParserV1()
        resource = parser.parse(
            "# This comment should attach\n-my-term = Term Value\n"
        )
        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert isinstance(entry, Term)
        assert entry.id.name == "my-term"
        assert entry.comment is not None
        assert isinstance(entry.comment, Comment)
        assert entry.comment.type == CommentType.COMMENT
        assert "This comment should attach" in entry.comment.content

    def test_multiple_comments_attached_to_term(self) -> None:
        """Multiple adjacent comments merge and attach to term."""
        parser = FluentParserV1()
        source = (
            "# Comment line 1\n# Comment line 2\n"
            "# Comment line 3\n-my-term = Value\n"
        )
        resource = parser.parse(source)
        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert isinstance(entry, Term)
        assert entry.comment is not None
        assert "Comment line 1" in entry.comment.content
        assert "Comment line 2" in entry.comment.content
        assert "Comment line 3" in entry.comment.content

    def test_group_comment_before_term_not_attached(self) -> None:
        """Group comment (##) before term is not attached."""
        parser = FluentParserV1()
        resource = parser.parse("## Group comment\n-my-term = Value\n")
        assert len(resource.entries) == 2
        comment = resource.entries[0]
        term = resource.entries[1]
        assert isinstance(comment, Comment)
        assert comment.type == CommentType.GROUP
        assert isinstance(term, Term)
        assert term.comment is None

    def test_comment_with_blank_lines_before_term_not_attached(self) -> None:
        """Blank lines between comment and term prevent attachment."""
        parser = FluentParserV1()
        resource = parser.parse("# Comment\n\n\n-my-term = Value\n")
        assert len(resource.entries) == 2
        comment = resource.entries[0]
        term = resource.entries[1]
        assert isinstance(comment, Comment)
        assert isinstance(term, Term)
        assert term.comment is None

    # -- CRLF handling in comment merging ----------------------------------

    def test_crlf_comments(self) -> None:
        """Parser handles CRLF line endings in comment regions."""
        parser = FluentParserV1()
        resource = parser.parse("# Comment 1\r\n\r\n# Comment 2")
        assert resource is not None
        comments = [
            e for e in resource.entries if isinstance(e, Comment)
        ]
        assert len(comments) >= 1

    def test_cr_only_comments(self) -> None:
        """Parser handles CR-only line endings in comment regions."""
        parser = FluentParserV1()
        resource = parser.parse("# Comment 1\r\r# Comment 2")
        assert resource is not None
        comments = [
            e for e in resource.entries if isinstance(e, Comment)
        ]
        assert len(comments) >= 1

    def test_spaces_between_crlf_newlines(self) -> None:
        """Parser handles spaces between CRLF newlines."""
        parser = FluentParserV1()
        resource = parser.parse("# Comment 1\r\n  \r\n# Comment 2")
        assert resource is not None
        comments = [
            e for e in resource.entries if isinstance(e, Comment)
        ]
        assert len(comments) >= 1

    def test_no_blank_line_adjacent_comments_merge(self) -> None:
        """Adjacent comments with no blank line merge into one."""
        parser = FluentParserV1()
        resource = parser.parse("# Comment 1\n# Comment 2")
        comments = [
            e for e in resource.entries if isinstance(e, Comment)
        ]
        assert len(comments) == 1
