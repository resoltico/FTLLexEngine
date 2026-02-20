"""Core parser tests: blank line detection, comment merging, DoS protection, error recovery.

Tests for ``ftllexengine.syntax.parser.core``:

- ``_has_blank_line_between``: Region-based newline detection for comment merging
- ``_CommentAccumulator``: Span handling and content joining for adjacent comments
- ``FluentParserV1``: Comment merging, term/message/junk parsing, DoS limits,
  nesting depth clamping, source size validation, error recovery
"""

from __future__ import annotations

import logging
import sys

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_SOURCE_SIZE
from ftllexengine.diagnostics import DiagnosticCode
from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import Comment, Junk, Message, Span, Term
from ftllexengine.syntax.parser.core import (
    FluentParserV1,
    _CommentAccumulator,
    _has_blank_line_between,
)

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


# ============================================================================
# TestDoSProtection
# ============================================================================


class TestDoSAbortBehavior:
    """DoS abort behavior: max_parse_errors and abort thresholds.

    The parser aborts when the number of Junk entries exceeds
    ``max_parse_errors``, preventing memory exhaustion from
    severely malformed input.
    """

    # -- max_parse_errors: indented junk -----------------------------------

    def test_abort_on_indented_junk(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Parser aborts when indented junk count exceeds limit."""
        parser = FluentParserV1(max_parse_errors=3)
        source = (
            "  indented1\n# comment\n"
            "  indented2\n# comment\n"
            "  indented3\n# comment\n"
            "  indented4\n"
        )
        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 3
        assert any(
            "Parse aborted" in r.message for r in caplog.records
        )
        assert any(
            "exceeded maximum of 3 Junk entries" in r.message
            for r in caplog.records
        )

    # -- max_parse_errors: failed comments ---------------------------------

    def test_abort_on_failed_comments(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Parser aborts when malformed comment count exceeds limit."""
        parser = FluentParserV1(max_parse_errors=2)
        source = "####\n####\n####\n####\n"
        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 2
        assert any(
            "Parse aborted" in r.message for r in caplog.records
        )
        assert any(
            "exceeded maximum of 2 Junk entries" in r.message
            for r in caplog.records
        )

    def test_malformed_comment_creates_junk_with_diagnostic(self) -> None:
        """Malformed comment creates Junk with proper diagnostic."""
        parser = FluentParserV1()
        result = parser.parse("#####\n")
        assert len(result.entries) == 1
        junk_entry = result.entries[0]
        assert isinstance(junk_entry, Junk)
        assert junk_entry.content == "#####"
        assert len(junk_entry.annotations) == 1
        assert (
            junk_entry.annotations[0].code
            == DiagnosticCode.PARSE_JUNK.name
        )
        assert "Invalid comment syntax" in junk_entry.annotations[0].message

    # -- max_parse_errors: message parse failures --------------------------

    def test_abort_on_message_failures(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Parser aborts when message parse failures exceed limit."""
        parser = FluentParserV1(max_parse_errors=3)
        source = "msg1\nmsg2\nmsg3\nmsg4\nmsg5\n"
        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 3
        assert any(
            "Parse aborted" in r.message for r in caplog.records
        )
        assert any(
            "exceeded maximum of 3 Junk entries" in r.message
            for r in caplog.records
        )

    def test_generic_parse_error_annotation(self) -> None:
        """Generic parse error when nesting depth not exceeded."""
        parser = FluentParserV1()
        result = parser.parse("invalid syntax here\n")
        assert len(result.entries) == 1
        junk_entry = result.entries[0]
        assert isinstance(junk_entry, Junk)
        assert len(junk_entry.annotations) == 1
        annotation = junk_entry.annotations[0]
        assert annotation.code == DiagnosticCode.PARSE_JUNK.name
        assert annotation.message == "Parse error"

    # -- max_parse_errors: mixed junk types --------------------------------

    def test_mixed_junk_types_count_toward_limit(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """All junk types count together toward the limit."""
        parser = FluentParserV1(max_parse_errors=4)
        source = (
            "  indented1\nmsg1 = ok\n####\n"
            "invalid\nmsg2 = ok\n  indented2\n####\n"
        )
        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 4
        assert any(
            "Parse aborted" in r.message for r in caplog.records
        )

    def test_depth_exceeded_counts_toward_limit(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Depth exceeded errors count toward max_parse_errors."""
        parser = FluentParserV1(
            max_nesting_depth=1, max_parse_errors=2,
        )
        source = (
            "m1 = { { $x } }\nm2 = { { $y } }\n"
            "m3 = { { $z } }\n"
        )
        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 2
        depth_count = sum(
            1
            for entry in junk
            for ann in entry.annotations
            if ann.code
            == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name
        )
        assert depth_count >= 1

    # -- max_parse_errors: boundary conditions -----------------------------

    def test_disabled_max_parse_errors_never_aborts(self) -> None:
        """Parser with max_parse_errors=0 never aborts."""
        parser = FluentParserV1(max_parse_errors=0)
        source = "####\n" * 200
        result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 200

    def test_exact_boundary(self) -> None:
        """Parser creates exactly max_parse_errors junk entries at limit."""
        parser = FluentParserV1(max_parse_errors=5)
        source = "####\n" * 5
        result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 5

    def test_one_over_boundary(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Parser with 6 errors and limit of 5 aborts at 5."""
        parser = FluentParserV1(max_parse_errors=5)
        source = "####\n" * 6
        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 5
        assert any(
            "Parse aborted" in r.message for r in caplog.records
        )

    # -- Log message content -----------------------------------------------

    def test_log_suggests_fixing_source(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """DoS protection log mentions malformed FTL input."""
        parser = FluentParserV1(max_parse_errors=1)
        source = "####\n####\n"
        with caplog.at_level(logging.WARNING):
            parser.parse(source)
        assert any(
            "severely malformed FTL input" in r.message
            for r in caplog.records
        )

    def test_log_suggests_increasing_limit(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """DoS protection log mentions increasing max_parse_errors."""
        parser = FluentParserV1(max_parse_errors=1)
        source = "####\n####\n"
        with caplog.at_level(logging.WARNING):
            parser.parse(source)
        assert any(
            "increasing max_parse_errors" in r.message
            for r in caplog.records
        )



# ============================================================================
# TestDoSLimitsAndValidation
# ============================================================================


class TestDoSLimitsAndValidation:
    """DoS protection: nesting depth, source size, parameter validation.

    Verifies nesting depth clamping, source size limits, and
    constructor parameter validation.
    """

    # -- Nesting depth exceeded --------------------------------------------

    def test_depth_exceeded_specific_annotation(self) -> None:
        """Nesting depth exceeded produces specific diagnostic."""
        parser = FluentParserV1(max_nesting_depth=1)
        source = "msg = { { $var } }\n"
        result = parser.parse(source)
        assert len(result.entries) == 1
        junk_entry = result.entries[0]
        assert isinstance(junk_entry, Junk)
        assert len(junk_entry.annotations) == 1
        annotation = junk_entry.annotations[0]
        assert (
            annotation.code
            == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name
        )
        assert "Nesting depth limit exceeded" in annotation.message
        assert "max: 1" in annotation.message

    # -- Recursion limit clamping ------------------------------------------

    def test_clamps_excessive_nesting_depth(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Excessive max_nesting_depth is clamped to safe limit."""
        recursion_limit = sys.getrecursionlimit()
        max_safe_depth = recursion_limit - 50
        excessive_depth = recursion_limit + 100
        with caplog.at_level(
            logging.WARNING,
            logger="ftllexengine.syntax.parser.core",
        ):
            parser = FluentParserV1(max_nesting_depth=excessive_depth)
        assert parser.max_nesting_depth == max_safe_depth
        assert parser.max_nesting_depth < excessive_depth
        assert len(caplog.records) == 1
        warning = caplog.records[0]
        assert warning.levelname == "WARNING"
        assert "max_nesting_depth" in warning.message
        assert "exceeds Python recursion limit" in warning.message
        assert "Clamping to" in warning.message

    def test_accepts_depth_within_recursion_limit(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """No warning when nesting depth is within safe limit."""
        with caplog.at_level(
            logging.WARNING,
            logger="ftllexengine.syntax.parser.core",
        ):
            parser = FluentParserV1(max_nesting_depth=50)
        assert parser.max_nesting_depth == 50
        assert len(caplog.records) == 0

    # -- Source size validation --------------------------------------------

    def test_max_source_size_default(self) -> None:
        """Default max_source_size equals MAX_SOURCE_SIZE constant."""
        parser = FluentParserV1()
        assert parser.max_source_size == MAX_SOURCE_SIZE

    def test_max_source_size_custom(self) -> None:
        """Custom max_source_size is stored."""
        parser = FluentParserV1(max_source_size=5000)
        assert parser.max_source_size == 5000

    def test_max_source_size_disabled(self) -> None:
        """max_source_size=0 disables the limit."""
        parser = FluentParserV1(max_source_size=0)
        assert parser.max_source_size == 0

    def test_oversized_source_raises_value_error(self) -> None:
        """parse() raises ValueError when source exceeds limit."""
        parser = FluentParserV1(max_source_size=100)
        oversized = "a" * 101
        with pytest.raises(
            ValueError,
            match=(
                r"Source length \(101 characters\) "
                r"exceeds maximum \(100 characters\)"
            ),
        ):
            parser.parse(oversized)

    def test_oversized_error_includes_config_hint(self) -> None:
        """ValueError includes configuration hint."""
        parser = FluentParserV1(max_source_size=50)
        with pytest.raises(
            ValueError,
            match="Configure max_source_size in FluentParserV1",
        ):
            parser.parse("x" * 51)

    def test_source_at_exact_limit(self) -> None:
        """parse() allows source exactly at size limit."""
        parser = FluentParserV1(max_source_size=100)
        result = parser.parse(("msg = value\n" * 8)[:100])
        assert result is not None

    def test_disabled_limit_accepts_large_source(self) -> None:
        """max_source_size=0 accepts arbitrarily large source."""
        parser = FluentParserV1(max_source_size=0)
        result = parser.parse("msg = " + ("x" * 100000))
        assert result is not None

    def test_none_limit_accepts_large_source(self) -> None:
        """max_source_size=None accepts arbitrarily large source."""
        parser = FluentParserV1(max_source_size=None)
        result = parser.parse("msg = " + ("y" * 100000))
        assert result is not None

    # -- Parameter validation ----------------------------------------------

    def test_rejects_zero_nesting_depth(self) -> None:
        """max_nesting_depth=0 raises ValueError."""
        with pytest.raises(
            ValueError,
            match=r"max_nesting_depth must be positive \(got 0\)",
        ):
            FluentParserV1(max_nesting_depth=0)

    def test_rejects_negative_nesting_depth(self) -> None:
        """max_nesting_depth=-1 raises ValueError."""
        with pytest.raises(
            ValueError,
            match=r"max_nesting_depth must be positive \(got -1\)",
        ):
            FluentParserV1(max_nesting_depth=-1)

    def test_accepts_positive_nesting_depth(self) -> None:
        """Positive max_nesting_depth is accepted."""
        parser = FluentParserV1(max_nesting_depth=50)
        assert parser.max_nesting_depth == 50

    def test_accepts_none_nesting_depth(self) -> None:
        """None max_nesting_depth uses default."""
        parser = FluentParserV1(max_nesting_depth=None)
        assert parser.max_nesting_depth > 0


# ============================================================================
# TestParserErrorRecoveryCore
# ============================================================================


class TestParserCommentRecovery:
    """Parser comment parsing edge cases and comment type handling.

    Verifies comment recovery, comment types (single, group, resource),
    and edge cases like hash-only lines and EOF handling.
    """

    # -- Comment parsing edge cases ----------------------------------------

    def test_comment_without_newline_at_eof(self) -> None:
        """Comment without trailing newline at EOF."""
        parser = FluentParserV1()
        resource = parser.parse("# This is a comment")
        assert resource is not None
        assert len(resource.entries) > 0

    def test_hash_only_at_eof(self) -> None:
        """Single hash at EOF."""
        parser = FluentParserV1()
        resource = parser.parse("#")
        assert resource is not None

    def test_hash_with_newline_at_eof(self) -> None:
        """Hash followed by newline at EOF."""
        parser = FluentParserV1()
        resource = parser.parse("#\n")
        assert resource is not None

    def test_multiple_hashes_at_eof(self) -> None:
        """Multiple hashes (###) at EOF."""
        parser = FluentParserV1()
        resource = parser.parse("###")
        assert resource is not None

    def test_hash_followed_by_valid_message(self) -> None:
        """Recovery from hash-only line then valid message."""
        parser = FluentParserV1()
        resource = parser.parse("#\nmsg = value")
        assert resource is not None
        assert len(resource.entries) > 0

    def test_hash_blank_line_then_message(self) -> None:
        """Recovery from hash, blank line, then message."""
        parser = FluentParserV1()
        resource = parser.parse("#\n\nmsg = value")
        assert resource is not None
        assert len(resource.entries) > 0

    def test_multiple_failed_comment_lines(self) -> None:
        """Recovery from multiple consecutive hash-only lines."""
        parser = FluentParserV1()
        resource = parser.parse("#\n#\n#\nmsg = value")
        assert resource is not None

    # -- Comment types -----------------------------------------------------

    def test_single_line_comment(self) -> None:
        """Single-line comment before message."""
        parser = FluentParserV1()
        resource = parser.parse("# This is a comment\nmsg = value")
        assert resource is not None
        assert len(resource.entries) >= 1

    def test_group_comment(self) -> None:
        """Group comment (##) before message."""
        parser = FluentParserV1()
        resource = parser.parse("## Group comment\nmsg = value")
        assert resource is not None

    def test_resource_comment(self) -> None:
        """Resource comment (###) before message."""
        parser = FluentParserV1()
        resource = parser.parse("### Resource comment\nmsg = value")
        assert resource is not None

    def test_multiple_comment_types(self) -> None:
        """Multiple comment types in one resource."""
        parser = FluentParserV1()
        source = "# Comment 1\n## Comment 2\n### Comment 3\nmsg = value\n"
        resource = parser.parse(source)
        assert resource is not None
        assert len(resource.entries) >= 1



# ============================================================================
# TestParserEntryRecovery
# ============================================================================


class TestParserEntryRecovery:
    """Parser entry recovery: empty input, CRLF, messages, terms, junk.

    Verifies the parser handles empty/whitespace input, CRLF line endings,
    message and term parsing basics, and junk creation for invalid content.
    """

    # -- Empty / whitespace ------------------------------------------------

    def test_empty_source(self) -> None:
        """Empty source produces empty resource."""
        parser = FluentParserV1()
        resource = parser.parse("")
        assert resource is not None
        assert len(resource.entries) == 0

    def test_whitespace_only(self) -> None:
        """Whitespace-only source produces empty resource."""
        parser = FluentParserV1()
        resource = parser.parse("   \n\n    \n")
        assert resource is not None
        assert len(resource.entries) == 0

    # -- CRLF handling -----------------------------------------------------

    def test_crlf_line_endings(self) -> None:
        """Parser handles CRLF line endings."""
        parser = FluentParserV1()
        resource = parser.parse("msg1 = value1\r\nmsg2 = value2\r\n")
        assert resource is not None
        assert len(resource.entries) >= 2

    # -- Message parsing ---------------------------------------------------

    def test_simple_message(self) -> None:
        """Simple message parsing."""
        parser = FluentParserV1()
        resource = parser.parse("msg = value")
        assert resource is not None
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)

    def test_multiple_messages(self) -> None:
        """Multiple messages."""
        parser = FluentParserV1()
        resource = parser.parse(
            "msg1 = value1\nmsg2 = value2\nmsg3 = value3\n"
        )
        assert resource is not None
        assert len(resource.entries) == 3

    # -- Term parsing ------------------------------------------------------

    def test_simple_term(self) -> None:
        """Simple term parsing."""
        parser = FluentParserV1()
        resource = parser.parse("-term = value")
        assert resource is not None
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Term)

    def test_term_with_id(self) -> None:
        """Term preserves identifier."""
        parser = FluentParserV1()
        resource = parser.parse("-my-term = Term Value")
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Term)
        assert resource.entries[0].id.name == "my-term"

    def test_multiple_terms(self) -> None:
        """Multiple terms."""
        parser = FluentParserV1()
        source = "-term1 = Value 1\n-term2 = Value 2\n-term3 = Value 3\n"
        resource = parser.parse(source)
        assert len(resource.entries) == 3
        assert all(isinstance(e, Term) for e in resource.entries)

    def test_term_with_attributes(self) -> None:
        """Term with attributes."""
        parser = FluentParserV1()
        source = "-term = Main Value\n    .attr = Attribute Value\n"
        resource = parser.parse(source)
        assert len(resource.entries) >= 1

    def test_term_and_message_coexist(self) -> None:
        """Terms and messages in same resource."""
        parser = FluentParserV1()
        source = "-term = term value\nmsg = message value\n"
        resource = parser.parse(source)
        assert len(resource.entries) == 2

    def test_failed_term_parsing(self) -> None:
        """Parser handles failed term parsing (dash not followed by valid term)."""
        parser = FluentParserV1()
        result = parser.parse("- invalid\n")
        assert result is not None
        assert len(result.entries) > 0

    # -- Junk handling -----------------------------------------------------

    def test_junk_creates_entry(self) -> None:
        """Unparseable content creates Junk entry."""
        parser = FluentParserV1()
        resource = parser.parse("%%% invalid syntax")
        assert resource is not None
        assert len(resource.entries) > 0
        assert any(isinstance(e, Junk) for e in resource.entries)

    def test_junk_continues_parsing(self) -> None:
        """Parser continues after junk entry."""
        parser = FluentParserV1()
        resource = parser.parse("%%% invalid\nmsg = valid message\n")
        assert resource is not None
        assert len(resource.entries) >= 2

    def test_multiline_junk(self) -> None:
        """Multi-line junk handling."""
        parser = FluentParserV1()
        source = "%%% line 1\n    line 2\n    line 3\nmsg = valid\n"
        resource = parser.parse(source)
        assert resource is not None
        assert len(resource.entries) > 0

    def test_junk_eof_with_trailing_spaces(self) -> None:
        """Junk parsing handles trailing spaces at EOF."""
        parser = FluentParserV1()
        resource = parser.parse("%%% invalid   ")
        assert resource is not None
        assert len(resource.entries) > 0
        assert isinstance(resource.entries[0], Junk)

    def test_junk_trailing_spaces_at_eof(self) -> None:
        """Junk with trailing spaces at EOF."""
        parser = FluentParserV1()
        resource = parser.parse("invalid syntax    ")
        assert resource is not None

    def test_multiline_junk_ends_at_eof(self) -> None:
        """Multiline junk ending at EOF."""
        parser = FluentParserV1()
        source = "invalid line 1\n    invalid line 2\n    "
        resource = parser.parse(source)
        assert resource is not None


# ============================================================================
# TestParserCoreHypothesis
# ============================================================================


class TestParserCoreHypothesis:
    """Property-based tests for parser core components.

    Uses Hypothesis to verify invariants across generated inputs.
    All ``@given`` tests emit ``event()`` calls for HypoFuzz guidance.
    """

    # -- _has_blank_line_between properties --------------------------------

    @given(
        prefix=st.text(
            alphabet=st.characters(blacklist_characters=["\n"]),
            max_size=10,
        ),
        suffix=st.text(
            alphabet=st.characters(blacklist_characters=["\n"]),
            max_size=10,
        ),
    )
    def test_newline_pair_always_detected(
        self, prefix: str, suffix: str,
    ) -> None:
        """Two consecutive newlines in region are always detected."""
        source = f"{prefix}\n\n{suffix}"
        event(f"input_len={len(source)}")
        assert _has_blank_line_between(source, 0, len(source)) is True

    @given(st.integers(min_value=2, max_value=10))
    def test_multiple_newlines_always_detected(
        self, count: int,
    ) -> None:
        """Multiple consecutive newlines always detected."""
        event(f"boundary=newline_count_{count}")
        source = "\n" * count
        assert _has_blank_line_between(source, 0, len(source)) is True

    @given(st.integers(min_value=0, max_value=50))
    def test_spaces_only_never_blank(self, space_count: int) -> None:
        """Spaces without newlines never produce a blank line."""
        event(f"boundary=space_count_{min(space_count, 10)}")
        source = " " * space_count
        assert _has_blank_line_between(source, 0, len(source)) is False

    @given(
        st.text(
            alphabet=st.characters(
                blacklist_characters=["\n", " "],
                min_codepoint=33,
                max_codepoint=126,
            ),
            min_size=1,
            max_size=20,
        )
    )
    def test_ascii_no_newline_no_blank(self, text: str) -> None:
        """ASCII text without newlines or spaces has no blank line."""
        event(f"input_len={len(text)}")
        assert _has_blank_line_between(text, 0, len(text)) is False

    @given(
        non_blank=st.characters(
            blacklist_categories=("Zs", "Zl", "Zp"),
            blacklist_characters=["\n"],
        )
    )
    def test_non_blank_char_with_newlines(
        self, non_blank: str,
    ) -> None:
        """Non-blank char between newlines: first newline is detected."""
        event("outcome=newline_detected")
        source = f"\n{non_blank}\n"
        assert _has_blank_line_between(source, 0, len(source)) is True

    @given(
        lines=st.lists(
            st.text(
                alphabet=st.characters(
                    blacklist_categories=("Zs", "Zl", "Zp"),
                    blacklist_characters=["\n"],
                ),
                min_size=1,
                max_size=5,
            ),
            min_size=1,
            max_size=10,
        )
    )
    def test_joined_lines_blank_iff_multiple(
        self, lines: list[str],
    ) -> None:
        """Single-newline-joined non-ws lines: blank iff >1 line."""
        event(f"boundary=line_count_{len(lines)}")
        source = "\n".join(lines)
        result = _has_blank_line_between(source, 0, len(source))
        if len(lines) > 1:
            assert result is True
        else:
            assert result is False

    @given(
        non_blank_chars=st.lists(
            st.characters(
                blacklist_categories=("Zs", "Zl", "Zp"),
                blacklist_characters=["\n"],
            ),
            min_size=1,
            max_size=5,
        )
    )
    def test_interleaved_newlines_always_detected(
        self, non_blank_chars: list[str],
    ) -> None:
        """Interleaved newlines and non-blank chars: always has newline."""
        event(f"boundary=char_count_{len(non_blank_chars)}")
        parts: list[str] = []
        for char in non_blank_chars:
            parts.append("\n")
            parts.append(char)
        parts.append("\n")
        source = "".join(parts)
        assert _has_blank_line_between(source, 0, len(source)) is True

    # -- Parser hash-combination property ----------------------------------

    @given(
        st.text(
            alphabet="#\n\r \t", min_size=1, max_size=50,
        )
    )
    def test_hash_combinations_no_crash(self, source: str) -> None:
        """Parser handles any combination of hashes and whitespace."""
        event(f"input_len={len(source)}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None
        assert isinstance(resource.entries, tuple)
        has_entries = len(resource.entries) > 0
        event(f"outcome=has_entries_{has_entries}")

    # -- max_parse_errors property -----------------------------------------

    @given(st.integers(min_value=1, max_value=10))
    def test_custom_limit_respected(self, limit: int) -> None:
        """Parser aborts at exactly max_parse_errors limit."""
        event(f"boundary=limit_{limit}")
        parser = FluentParserV1(max_parse_errors=limit)
        source = "####\n" * (limit + 2)
        result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == limit

    # -- Nesting depth property --------------------------------------------

    @given(st.integers(min_value=1, max_value=5))
    def test_depth_exceeded_includes_limit(
        self, depth_limit: int,
    ) -> None:
        """Depth exceeded diagnostic includes the configured limit."""
        event(f"boundary=depth_{depth_limit}")
        parser = FluentParserV1(max_nesting_depth=depth_limit)
        nesting = (
            "{ " * (depth_limit + 1)
            + "$x"
            + " }" * (depth_limit + 1)
        )
        source = f"msg = {nesting}\n"
        result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) >= 1
        for entry in junk:
            for ann in entry.annotations:
                if (
                    ann.code
                    == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name
                ):
                    assert f"max: {depth_limit}" in ann.message
                    return
        pytest.fail(
            "Expected PARSE_NESTING_DEPTH_EXCEEDED annotation"
        )

    # -- Recursion limit clamping property ---------------------------------

    @given(depth_offset=st.integers(min_value=1, max_value=500))
    def test_any_excessive_depth_clamped(
        self, depth_offset: int,
    ) -> None:
        """Any depth exceeding recursion limit is clamped."""
        event(f"boundary=offset_{min(depth_offset, 50)}")
        recursion_limit = sys.getrecursionlimit()
        max_safe = recursion_limit - 50
        excessive = recursion_limit + depth_offset
        parser = FluentParserV1(max_nesting_depth=excessive)
        assert parser.max_nesting_depth == max_safe

    # -- _CommentAccumulator span property ---------------------------------

    @given(
        content1=st.text(min_size=1, max_size=50),
        content2=st.text(min_size=1, max_size=50),
        start=st.integers(min_value=0, max_value=1000),
        end=st.integers(min_value=0, max_value=1000),
    )
    def test_accumulator_span_combinations(
        self,
        content1: str,
        content2: str,
        start: int,
        end: int,
    ) -> None:
        """Accumulator always produces valid Comment for any span config."""
        if end < start:
            start, end = end, start
        span = Span(start=start, end=end)

        for first_has in (True, False):
            for last_has in (True, False):
                event(
                    f"outcome=first_{first_has}_last_{last_has}"
                )
                first = Comment(
                    content=content1,
                    type=CommentType.COMMENT,
                    span=span if first_has else None,
                )
                acc = _CommentAccumulator(first)
                second = Comment(
                    content=content2,
                    type=CommentType.COMMENT,
                    span=span if last_has else None,
                )
                acc.add(second)
                result = acc.finalize()

                assert content1 in result.content
                assert content2 in result.content
                assert "\n" in result.content

                if first_has or last_has:
                    assert result.span is not None
                    if first_has != last_has:
                        assert result.span == span
                else:
                    assert result.span is None

    # -- Comment attachment to term property --------------------------------

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
    def test_comment_attaches_to_adjacent_term(
        self,
        comment_text: str,
        term_name: str,
        term_value: str,
    ) -> None:
        """Single-hash comment immediately before term is attached."""
        event("outcome=term_attachment")
        parser = FluentParserV1()
        source = f"# {comment_text}\n-{term_name} = {term_value}\n"
        resource = parser.parse(source)
        terms = [e for e in resource.entries if isinstance(e, Term)]
        if terms:
            term = terms[0]
            assert term.comment is not None
            assert comment_text in term.comment.content
