"""Complete coverage tests for syntax/parser/rules.py entry parsing functions.

Tests all remaining uncovered lines and branches to achieve 100% coverage.

Uncovered lines: 33, 145, 161, 205, 212, 231, 270, 277, 285, 309, 316, 328, 345-346, 395
Uncovered branches: 296->307, 299->303, 408->412, 424->430, 426->430
"""

from __future__ import annotations

from unittest.mock import patch

from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser import rules

# ============================================================================
# LINE 33: Message ID Without '='
# ============================================================================


class TestLine33MessageIdWithoutEquals:
    """Test line 33: parse_message_header when '=' is missing."""

    def test_message_id_missing_equals(self) -> None:
        """Test parse_message_header returns None when '=' is missing (line 33)."""
        source = "msgid   "  # ID followed by spaces, no '='
        cursor = Cursor(source, 0)

        result = rules.parse_message_header(cursor)

        # Should return None because '=' is missing
        assert result is None

    def test_message_id_at_eof(self) -> None:
        """Test parse_message_header returns None when EOF after ID (line 33)."""
        source = "msgid"  # ID at EOF
        cursor = Cursor(source, 0)

        result = rules.parse_message_header(cursor)

        # Should return None because EOF (no '=')
        assert result is None

    def test_message_id_followed_by_newline(self) -> None:
        """Test parse_message_header returns None when newline after ID (line 33)."""
        source = "msgid\n"  # ID followed by newline, no '='
        cursor = Cursor(source, 0)

        result = rules.parse_message_header(cursor)

        # Should return None
        assert result is None


# ============================================================================
# LINE 145: Message Pattern Parsing Failure
# ============================================================================


class TestLine145MessagePatternFailure:
    """Test line 145: parse_message when pattern parsing fails."""

    def test_message_pattern_parsing_fails(self) -> None:
        """Test parse_message returns None when parse_pattern fails (line 145)."""
        source = "msg = Value"
        cursor = Cursor(source, 0)

        # Mock parse_pattern where it's imported (in rules module)
        with patch("ftllexengine.syntax.parser.rules.parse_pattern", return_value=None):
            result = rules.parse_message(cursor)

        # Should return None when pattern parsing fails
        assert result is None


# ============================================================================
# LINE 161: Message Validation Failure
# ============================================================================


class TestLine161MessageValidationFailure:
    """Test line 161: parse_message when validation fails."""

    def test_message_validation_fails_no_content(self) -> None:
        """Test parse_message returns None when message has no value or attributes (line 161)."""
        source = "msg = "  # Message with empty pattern
        cursor = Cursor(source, 0)

        # Mock parse_pattern to return empty Pattern
        from ftllexengine.syntax.ast import Pattern
        from ftllexengine.syntax.cursor import ParseResult

        empty_pattern = Pattern(elements=())
        empty_pattern_result = ParseResult(empty_pattern, Cursor(source, len(source)))

        # Mock both parse_pattern (from rules module) and parse_message_attributes
        with (
            patch(
                "ftllexengine.syntax.parser.rules.parse_pattern",
                return_value=empty_pattern_result,
            ),
            patch.object(
                rules,
                "parse_message_attributes",
                return_value=ParseResult([], Cursor(source, len(source))),
            ),
        ):
            result = rules.parse_message(cursor)

        # Should return None when validation fails (no pattern, no attributes)
        assert result is None


# ============================================================================
# LINE 205: Attribute Without '.' Prefix
# ============================================================================


class TestLine205AttributeWithoutDot:
    """Test line 205: parse_attribute when '.' is missing."""

    def test_attribute_without_dot_prefix(self) -> None:
        """Test parse_attribute returns None when '.' is missing (line 205)."""
        source = "attr = Value"  # No '.' prefix
        cursor = Cursor(source, 0)

        result = rules.parse_attribute(cursor)

        # Should return None because '.' is missing
        assert result is None

    def test_attribute_at_eof(self) -> None:
        """Test parse_attribute returns None at EOF (line 205)."""
        source = ""  # EOF
        cursor = Cursor(source, 0)

        result = rules.parse_attribute(cursor)

        # Should return None at EOF
        assert result is None


# ============================================================================
# LINE 212: Attribute With Invalid Identifier
# ============================================================================


class TestLine212AttributeInvalidIdentifier:
    """Test line 212: parse_attribute when identifier parsing fails."""

    def test_attribute_invalid_identifier_after_dot(self) -> None:
        """Test parse_attribute returns None when identifier is invalid (line 212)."""
        source = ".   "  # '.' followed by spaces (no valid identifier)
        cursor = Cursor(source, 0)

        result = rules.parse_attribute(cursor)

        # Should return None because identifier parsing fails
        assert result is None

    def test_attribute_dot_followed_by_number(self) -> None:
        """Test parse_attribute with '.' followed by number (invalid identifier)."""
        source = ".123 = Value"  # Identifier can't start with number
        cursor = Cursor(source, 0)

        result = rules.parse_attribute(cursor)

        # Should return None
        assert result is None


# ============================================================================
# LINE 231: Attribute Pattern Parsing Failure
# ============================================================================


class TestLine231AttributePatternFailure:
    """Test line 231: parse_attribute when pattern parsing fails."""

    def test_attribute_pattern_parsing_fails(self) -> None:
        """Test parse_attribute returns None when pattern fails (line 231)."""
        source = ".attr = "
        cursor = Cursor(source, 0)

        # Mock parse_pattern from rules module
        with patch("ftllexengine.syntax.parser.rules.parse_pattern", return_value=None):
            result = rules.parse_attribute(cursor)

        # Should return None when pattern parsing fails
        assert result is None


# ============================================================================
# LINE 270: Term Without '-' Prefix
# ============================================================================


class TestLine270TermWithoutDash:
    """Test line 270: parse_term when '-' is missing."""

    def test_term_without_dash_prefix(self) -> None:
        """Test parse_term returns None when '-' is missing (line 270)."""
        source = "term = Value"  # No '-' prefix
        cursor = Cursor(source, 0)

        result = rules.parse_term(cursor)

        # Should return None because '-' is missing
        assert result is None

    def test_term_at_eof(self) -> None:
        """Test parse_term returns None at EOF (line 270)."""
        source = ""  # EOF
        cursor = Cursor(source, 0)

        result = rules.parse_term(cursor)

        # Should return None at EOF
        assert result is None


# ============================================================================
# LINE 277: Term With Invalid Identifier
# ============================================================================


class TestLine277TermInvalidIdentifier:
    """Test line 277: parse_term when identifier parsing fails."""

    def test_term_invalid_identifier_after_dash(self) -> None:
        """Test parse_term returns None when identifier is invalid (line 277)."""
        source = "-   "  # '-' followed by spaces (no valid identifier)
        cursor = Cursor(source, 0)

        result = rules.parse_term(cursor)

        # Should return None because identifier parsing fails
        assert result is None

    def test_term_dash_followed_by_number(self) -> None:
        """Test parse_term with '-' followed by number (invalid identifier)."""
        source = "-123 = Value"  # Identifier can't start with number
        cursor = Cursor(source, 0)

        result = rules.parse_term(cursor)

        # Should return None
        assert result is None


# ============================================================================
# LINE 285: Term Without '=' After Identifier
# ============================================================================


class TestLine285TermWithoutEquals:
    """Test line 285: parse_term when '=' is missing after identifier."""

    def test_term_identifier_without_equals(self) -> None:
        """Test parse_term returns None when '=' is missing (line 285)."""
        source = "-term   "  # Term ID followed by spaces, no '='
        cursor = Cursor(source, 0)

        result = rules.parse_term(cursor)

        # Should return None because '=' is missing
        assert result is None

    def test_term_identifier_at_eof(self) -> None:
        """Test parse_term returns None when EOF after ID (line 285)."""
        source = "-term"  # Term ID at EOF
        cursor = Cursor(source, 0)

        result = rules.parse_term(cursor)

        # Should return None because EOF (no '=')
        assert result is None


# ============================================================================
# LINE 309: Term Pattern Parsing Failure
# ============================================================================


class TestLine309TermPatternFailure:
    """Test line 309: parse_term when pattern parsing fails."""

    def test_term_pattern_parsing_fails(self) -> None:
        """Test parse_term returns None when parse_pattern fails (line 309)."""
        source = "-term = Value"
        cursor = Cursor(source, 0)

        # Mock parse_pattern from rules module
        with patch("ftllexengine.syntax.parser.rules.parse_pattern", return_value=None):
            result = rules.parse_term(cursor)

        # Should return None when pattern parsing fails
        assert result is None


# ============================================================================
# LINE 316: Term With Empty Pattern
# ============================================================================


class TestLine316TermEmptyPattern:
    """Test line 316: parse_term when pattern has no elements."""

    def test_term_empty_pattern_validation_fails(self) -> None:
        """Test parse_term returns None when pattern is empty (line 316)."""
        from ftllexengine.syntax.ast import Pattern
        from ftllexengine.syntax.cursor import ParseResult

        source = "-term = "
        cursor = Cursor(source, 0)

        # Mock parse_pattern to return empty Pattern
        empty_pattern = Pattern(elements=())
        empty_pattern_result = ParseResult(empty_pattern, Cursor(source, len(source)))

        with patch(
            "ftllexengine.syntax.parser.rules.parse_pattern",
            return_value=empty_pattern_result,
        ):
            result = rules.parse_term(cursor)

        # Should return None when pattern is empty (line 316)
        assert result is None


# ============================================================================
# LINE 328: Term Attribute Loop Break (No Newline)
# ============================================================================


class TestLine328TermAttributeBreak:
    """Test line 328: break when no newline in term attribute loop."""

    def test_term_value_followed_by_space_triggers_break(self) -> None:
        """Test parse_term breaks at line 328 when cursor after value is on space.

        After parsing term value, if cursor lands on a space (not newline, not EOF),
        the attribute loop enters once, checks if current is newline (it's not),
        and breaks at line 328.
        """
        # Term value followed by space and then content (forces loop to enter and break)
        source = "-term = Value "  # Trailing space, then EOF
        cursor = Cursor(source, 0)

        result = rules.parse_term(cursor)

        # Should parse successfully - breaks at line 328 due to space
        assert result is not None
        assert result.value.id.name == "term"
        # No attributes should be parsed
        assert len(result.value.attributes) == 0

    def test_term_cursor_on_space_after_pattern_line_328(self) -> None:
        """Test parse_term with cursor on space after pattern to hit line 328.

        Mock parse_pattern to position cursor on a SPACE (not newline, not EOF)
        so the attribute loop enters and immediately hits the else: break at line 328.
        """
        from ftllexengine.syntax.ast import Pattern, TextElement
        from ftllexengine.syntax.cursor import ParseResult

        # Source with space after value
        source = "-term = Value  msg"  # Two spaces, then 'msg'
        cursor = Cursor(source, 0)

        # Mock parse_pattern to stop after "Value" and leave cursor on first space
        def mock_parse_pattern(cursor_arg, context=None):  # noqa: ARG001
            # Return pattern and position cursor at the first space after "Value"
            pattern = Pattern(elements=(TextElement("Value"),))
            # Position cursor at the space (position 14: after "Value")
            new_cursor = Cursor(source, 14)  # At first space
            return ParseResult(pattern, new_cursor)

        with patch(
            "ftllexengine.syntax.parser.rules.parse_pattern",
            side_effect=mock_parse_pattern,
        ):
            result = rules.parse_term(cursor)

        # Should complete successfully
        # Attribute loop enters with cursor on ' ', checks if it's newline (no), breaks at 328
        assert result is not None
        assert result.value.id.name == "term"


# ============================================================================
# LINES 345-346: Term With Invalid Attribute Syntax
# ============================================================================


class TestLines345To346TermInvalidAttribute:
    """Test lines 345-346: term attribute parsing fails, restore cursor and break."""

    def test_term_with_invalid_attribute_syntax(self) -> None:
        """Test parse_term handles invalid attribute syntax (lines 345-346)."""
        # Term followed by line starting with '.' but invalid attribute syntax
        source = "-term = Value\n.invalid"  # '.' but no valid attribute after
        cursor = Cursor(source, 0)

        # Mock parse_attribute to return None (simulating parse failure)
        original_parse_attribute = rules.parse_attribute

        def mock_parse_attribute(cursor, context=None):
            # Call original for first call (within parse_term for value)
            # Return None for second call (for the invalid attribute)
            if ".invalid" in cursor.source[cursor.pos :]:
                return None
            return original_parse_attribute(cursor, context)

        with patch.object(rules, "parse_attribute", side_effect=mock_parse_attribute):
            result = rules.parse_term(cursor)

        # Should parse term but stop at invalid attribute (lines 345-346)
        assert result is not None
        assert result.value.id.name == "term"
        assert len(result.value.attributes) == 0  # No attributes parsed


# ============================================================================
# LINE 395: Comment With More Than 3 Hashes
# ============================================================================


class TestLine395CommentTooManyHashes:
    """Test line 395: parse_comment with > 3 hash characters."""

    def test_comment_with_four_hashes(self) -> None:
        """Test parse_comment returns None with 4 hashes (line 395)."""
        source = "#### Invalid comment"
        cursor = Cursor(source, 0)

        result = rules.parse_comment(cursor)

        # Should return None when > 3 hashes
        assert result is None

    def test_comment_with_five_hashes(self) -> None:
        """Test parse_comment returns None with 5 hashes (line 395)."""
        source = "##### Also invalid"
        cursor = Cursor(source, 0)

        result = rules.parse_comment(cursor)

        # Should return None
        assert result is None


# ============================================================================
# BRANCH 296->307: Term Newline But Not Indented
# ============================================================================


class TestBranch296Line307TermNewlineNotIndented:
    """Test branch 296->307: term with newline but not indented continuation."""

    def test_term_newline_not_indented_empty_pattern(self) -> None:
        """Test term with newline after '=' but no indentation (branch 296->307).

        When term has '=' followed by newline, but next line is NOT indented,
        this is the empty pattern case. Branch 296->307 is taken.
        """
        from ftllexengine.syntax.ast import Pattern
        from ftllexengine.syntax.cursor import ParseResult

        source = "-term = \nmsg = Other"  # Newline but not indented
        cursor = Cursor(source, 0)

        # Mock parse_pattern to return empty pattern
        empty_pattern = Pattern(elements=())

        def mock_parse_pattern(cursor, context=None):  # noqa: ARG001
            # Return empty pattern to trigger line 316 check
            return ParseResult(empty_pattern, cursor)

        with patch(
            "ftllexengine.syntax.parser.rules.parse_pattern",
            side_effect=mock_parse_pattern,
        ):
            result = rules.parse_term(cursor)

        # Should return None because empty pattern (line 316)
        assert result is None


# ============================================================================
# BRANCH 299->303: \r At EOF Or Not Followed By \n
# ============================================================================


class TestBranch299Line303CarriageReturnNotFollowedByLF:
    """Test branch 299->303: \\r at EOF or \\r not followed by \\n."""

    def test_term_with_cr_at_eof(self) -> None:
        """Test term pattern with \\r at EOF (branch 299->303 false).

        When term has multiline pattern ending with \\r at EOF,
        the condition 'not cursor.is_eof and cursor.current == "\\n"' is false.
        """
        source = "-term =\r    Value\r"  # \r at EOF
        cursor = Cursor(source, 0)

        result = rules.parse_term(cursor)

        # Should parse successfully
        assert result is not None
        assert result.value.id.name == "term"

    def test_term_with_cr_not_followed_by_lf(self) -> None:
        """Test term with \\r NOT followed by \\n (old Mac line ending).

        Branch 299->303: after \\r, cursor is not at EOF but current != \\n.
        """
        source = "-term =\r    Value\rmsg = Other"  # \r followed by non-\n
        cursor = Cursor(source, 0)

        result = rules.parse_term(cursor)

        # Should parse term successfully
        assert result is not None
        assert result.value.id.name == "term"


# ============================================================================
# BRANCH 408->412: Comment Without Space After '#'
# ============================================================================


class TestBranch408Line412CommentNoSpaceAfterHash:
    """Test branch 408->412: comment without space after '#'."""

    def test_comment_without_space_after_hash(self) -> None:
        """Test parse_comment when no space follows '#' (branch 408->412 false).

        Per spec, space after '#' is optional. If missing, branch 408->412 is not taken.
        """
        source = "#Comment without space\n"
        cursor = Cursor(source, 0)

        result = rules.parse_comment(cursor)

        # Should parse successfully
        assert result is not None
        assert result.value.content == "Comment without space"

    def test_comment_empty_content_no_space(self) -> None:
        """Test comment with just '#' and newline (no space, no content)."""
        source = "#\n"
        cursor = Cursor(source, 0)

        result = rules.parse_comment(cursor)

        # Should parse successfully with empty content
        assert result is not None
        assert result.value.content == ""


# ============================================================================
# BRANCHES 424->430 and 426->430: LF vs CRLF In Comments
# ============================================================================


class TestBranches424And426CommentLineEndings:
    """Test branches 424->430 and 426->430: comment line ending handling."""

    def test_comment_with_lf_only_line_426(self) -> None:
        """Test parse_comment with LF-only ending (line 426, branch 426->430).

        When comment ends with \\n (not \\r), line 426 elif is executed.
        """
        source = "# Comment with LF\nmsg = Value"
        cursor = Cursor(source, 0)

        result = rules.parse_comment(cursor)

        # Should parse successfully
        assert result is not None
        assert "Comment with LF" in result.value.content
        # Cursor should be after \n, positioned at 'm'
        assert cursor.source[result.cursor.pos] == "m"

    def test_comment_lf_explicit_branch_426(self) -> None:
        """Explicit test for branch 426->430: elif cursor.current == '\\n'.

        Ensure cursor is NOT on \\r, so the if at line 421 is False,
        and cursor IS on \\n, so elif at line 426 is True.
        """
        # Simple comment with just LF (no CR anywhere)
        source = "#Test\n"  # No space after #, just content and LF
        cursor = Cursor(source, 0)

        result = rules.parse_comment(cursor)

        # Verify successful parse
        assert result is not None
        assert result.value.content == "Test"
        # Cursor should be positioned after the \n
        assert result.cursor.is_eof or result.cursor.pos == len(source)

    def test_comment_with_cr_only_branch_424_false(self) -> None:
        """Test parse_comment with CR followed by non-LF (branch 424->430 true, 426 not taken).

        When comment ends with \\r not followed by \\n, line 424 condition is True,
        but line 426 elif is not taken.
        """
        source = "# Comment\rmsg = Other"  # \r followed by 'm' (not \n)
        cursor = Cursor(source, 0)

        result = rules.parse_comment(cursor)

        # Should parse successfully
        assert result is not None
        assert result.value.content == "Comment"
        # Cursor should be after \r
        assert cursor.source[result.cursor.pos] == "m"

    def test_comment_at_eof_no_line_ending(self) -> None:
        """Test parse_comment at EOF with no line ending (neither branch 424 nor 426)."""
        source = "# Comment at EOF"  # No line ending
        cursor = Cursor(source, 0)

        result = rules.parse_comment(cursor)

        # Should parse successfully
        assert result is not None
        assert result.value.content == "Comment at EOF"
        # Cursor should be at EOF
        assert result.cursor.is_eof


# ============================================================================
# Integration Test: All Error Paths Combined
# ============================================================================


class TestCompleteErrorPathCoverage:
    """Integration test combining multiple error paths."""

    def test_all_error_paths_covered(self) -> None:
        """Verify all error paths are reachable and testable."""
        # This test documents that we've covered all error paths

        # Line 33: Message without '='
        assert rules.parse_message_header(Cursor("msg", 0)) is None

        # Line 205: Attribute without '.'
        assert rules.parse_attribute(Cursor("attr", 0)) is None

        # Line 270: Term without '-'
        assert rules.parse_term(Cursor("term", 0)) is None

        # Line 395: Comment with > 3 hashes
        assert rules.parse_comment(Cursor("#### too many", 0)) is None
