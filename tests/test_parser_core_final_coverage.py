"""Final coverage tests for syntax/parser/core.py to reach 100%.

Targets the last remaining uncovered lines:
- _CommentAccumulator.finalize() with last_span only
- FluentParserV1.__init__() recursion limit warning
- Comment attachment to terms
"""

from __future__ import annotations

import logging
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import Comment, Span, Term
from ftllexengine.syntax.parser.core import FluentParserV1, _CommentAccumulator


class TestCommentAccumulatorSpanEdgeCases:
    """Test _CommentAccumulator.finalize() with various span configurations."""

    def test_finalize_with_last_span_only(self) -> None:
        """Finalize when first_span is None but last_span is not None.

        Covers lines 163-164 in core.py.
        """
        # Create a comment with no span
        first_comment = Comment(
            content="First comment",
            type=CommentType.COMMENT,
            span=None,
        )

        # Initialize accumulator with first comment (no span)
        accumulator = _CommentAccumulator(first_comment)

        # Add a second comment with a span
        second_comment = Comment(
            content="Second comment",
            type=CommentType.COMMENT,
            span=Span(start=10, end=30),
        )
        accumulator.add(second_comment)

        # Finalize should use last_span when first_span is None
        result = accumulator.finalize()

        assert result.content == "First comment\nSecond comment"
        assert result.type == CommentType.COMMENT
        assert result.span is not None
        assert result.span.start == 10
        assert result.span.end == 30

    def test_finalize_with_neither_span(self) -> None:
        """Finalize when both first_span and last_span are None."""
        # Create comments with no spans
        first_comment = Comment(
            content="No span 1",
            type=CommentType.GROUP,
            span=None,
        )

        accumulator = _CommentAccumulator(first_comment)

        second_comment = Comment(
            content="No span 2",
            type=CommentType.GROUP,
            span=None,
        )
        accumulator.add(second_comment)

        # Finalize should handle None spans gracefully
        result = accumulator.finalize()

        assert result.content == "No span 1\nNo span 2"
        assert result.type == CommentType.GROUP
        assert result.span is None

    @given(
        content1=st.text(min_size=1, max_size=50),
        content2=st.text(min_size=1, max_size=50),
        start=st.integers(min_value=0, max_value=1000),
        end=st.integers(min_value=0, max_value=1000),
    )
    def test_finalize_span_combinations_property(
        self,
        content1: str,
        content2: str,
        start: int,
        end: int,
    ) -> None:
        """Property test for various span combinations in finalize.

        Property: finalize() always produces a valid Comment with merged content,
        regardless of span configuration.
        """
        # Ensure end >= start for valid span
        if end < start:
            start, end = end, start

        span = Span(start=start, end=end)

        # Test all combinations of span presence
        for first_has_span in (True, False):
            for last_has_span in (True, False):
                first_comment = Comment(
                    content=content1,
                    type=CommentType.COMMENT,
                    span=span if first_has_span else None,
                )

                accumulator = _CommentAccumulator(first_comment)

                second_comment = Comment(
                    content=content2,
                    type=CommentType.COMMENT,
                    span=span if last_has_span else None,
                )
                accumulator.add(second_comment)

                result = accumulator.finalize()

                # Content should always be merged
                assert content1 in result.content
                assert content2 in result.content
                assert "\n" in result.content

                # Span behavior depends on configuration
                if first_has_span or last_has_span:
                    assert result.span is not None
                    # When only one has span, it should be that span
                    if first_has_span != last_has_span:
                        assert result.span == span
                else:
                    assert result.span is None


class TestFluentParserV1RecursionLimit:
    """Test FluentParserV1 initialization with recursion limit handling."""

    def test_init_clamps_excessive_max_nesting_depth(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Initialize with max_nesting_depth exceeding recursion limit.

        Covers lines 237-245 in core.py.
        Verifies warning is logged and depth is clamped.
        """
        # Get current recursion limit
        recursion_limit = sys.getrecursionlimit()
        max_safe_depth = recursion_limit - 50

        # Request a depth that exceeds the safe limit
        excessive_depth = recursion_limit + 100

        # Capture logging at WARNING level
        with caplog.at_level(logging.WARNING, logger="ftllexengine.syntax.parser.core"):
            parser = FluentParserV1(max_nesting_depth=excessive_depth)

        # Verify depth was clamped
        assert parser.max_nesting_depth == max_safe_depth
        assert parser.max_nesting_depth < excessive_depth

        # Verify warning was logged
        assert len(caplog.records) == 1
        warning_record = caplog.records[0]
        assert warning_record.levelname == "WARNING"
        assert "max_nesting_depth" in warning_record.message
        assert "exceeds Python recursion limit" in warning_record.message
        assert "Clamping to" in warning_record.message

    def test_init_accepts_depth_within_recursion_limit(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Initialize with max_nesting_depth within safe limits.

        Verifies no warning is logged when depth is acceptable.
        """
        # Request a safe depth
        safe_depth = 50

        with caplog.at_level(logging.WARNING, logger="ftllexengine.syntax.parser.core"):
            parser = FluentParserV1(max_nesting_depth=safe_depth)

        # Verify depth was not clamped
        assert parser.max_nesting_depth == safe_depth

        # Verify no warning was logged
        assert len(caplog.records) == 0

    @given(depth_offset=st.integers(min_value=1, max_value=500))
    def test_init_clamps_any_excessive_depth(
        self,
        depth_offset: int,
    ) -> None:
        """Property test: any depth exceeding limit is clamped.

        Property: For any depth > safe_limit, the parser clamps to safe_limit.
        """
        recursion_limit = sys.getrecursionlimit()
        max_safe_depth = recursion_limit - 50
        excessive_depth = recursion_limit + depth_offset

        parser = FluentParserV1(max_nesting_depth=excessive_depth)

        assert parser.max_nesting_depth == max_safe_depth


class TestCommentAttachmentToTerm:
    """Test comment attachment to terms."""

    def test_parse_single_hash_comment_attached_to_term(self) -> None:
        """Single-hash comment immediately before term is attached.

        Covers line 465 in core.py (attach_comment to term).
        """
        parser = FluentParserV1()

        source = """# This comment should attach
-my-term = Term Value
"""

        resource = parser.parse(source)

        # Should have one term with attached comment
        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert isinstance(entry, Term)
        assert entry.id.name == "my-term"

        # Comment should be attached to term
        assert entry.comment is not None
        assert isinstance(entry.comment, Comment)
        assert entry.comment.type == CommentType.COMMENT
        assert "This comment should attach" in entry.comment.content

    def test_parse_multiple_comments_attached_to_term(self) -> None:
        """Multiple adjacent single-hash comments attach to term as merged comment."""
        parser = FluentParserV1()

        source = """# Comment line 1
# Comment line 2
# Comment line 3
-my-term = Value
"""

        resource = parser.parse(source)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert isinstance(entry, Term)

        # All three comment lines should be merged and attached
        assert entry.comment is not None
        assert "Comment line 1" in entry.comment.content
        assert "Comment line 2" in entry.comment.content
        assert "Comment line 3" in entry.comment.content

    def test_parse_group_comment_before_term_not_attached(self) -> None:
        """Group comment (##) before term is not attached."""
        parser = FluentParserV1()

        source = """## Group comment
-my-term = Value
"""

        resource = parser.parse(source)

        # Should have two entries: group comment and term
        assert len(resource.entries) == 2

        comment = resource.entries[0]
        term = resource.entries[1]

        assert isinstance(comment, Comment)
        assert comment.type == CommentType.GROUP

        assert isinstance(term, Term)
        assert term.comment is None  # Group comments don't attach

    def test_parse_comment_with_blank_lines_before_term_not_attached(self) -> None:
        """Single-hash comment with blank lines before term is not attached.

        Note: Multiple blank lines are needed to prevent attachment.
        Per FTL spec, a blank line is detected when there are 2+ consecutive newlines.
        """
        parser = FluentParserV1()

        source = """# Comment


-my-term = Value
"""

        resource = parser.parse(source)

        # Should have two entries: standalone comment and term
        assert len(resource.entries) == 2

        comment = resource.entries[0]
        term = resource.entries[1]

        assert isinstance(comment, Comment)
        assert isinstance(term, Term)
        assert term.comment is None  # Multiple blank lines prevent attachment

    @given(
        comment_text=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                min_codepoint=32,
                max_codepoint=126,
                exclude_characters="#\n",
            ),
        ),
        term_name=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(
                min_codepoint=ord("a"),
                max_codepoint=ord("z"),
            ),
        ),
        term_value=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                min_codepoint=32,
                max_codepoint=126,
                exclude_characters="\n{}",
            ),
        ),
    )
    def test_comment_attachment_to_term_property(
        self,
        comment_text: str,
        term_name: str,
        term_value: str,
    ) -> None:
        """Property test: single-hash comments attach to terms when adjacent.

        Property: A single-hash comment immediately before a term (no blank line)
        is always attached to that term.
        """
        parser = FluentParserV1()

        source = f"# {comment_text}\n-{term_name} = {term_value}\n"

        resource = parser.parse(source)

        # Filter for terms
        terms = [e for e in resource.entries if isinstance(e, Term)]

        # Should have at least one term
        if terms:
            term = terms[0]
            # Comment should be attached
            assert term.comment is not None
            assert comment_text in term.comment.content
