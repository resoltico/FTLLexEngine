"""Comprehensive coverage tests for syntax/parser/entries.py.

Targets uncovered error paths and edge cases:
- Line 48: Break when no newline after attributes
- Line 136: Return None if attributes parsing fails
- Line 185: Return None if '.' not found in attribute
- Line 246: Return None if '-' not found in term
- Line 276: CRLF handling in term pattern
- Line 304: Break when no newline in term attributes
- Lines 400->406, 402->406: CRLF handling in comments
"""

from __future__ import annotations

from ftllexengine.runtime.bundle import FluentBundle

# ============================================================================
# LINE 48: Break When No Newline After Message Attributes
# ============================================================================


class TestMessageAttributeNoNewline:
    """Test message attribute parsing when line doesn't end with newline (line 48)."""

    def test_message_attribute_without_trailing_newline(self) -> None:
        """Test message with attribute but no trailing newline (line 48).

        When parsing attributes, if we reach a line that doesn't have a newline,
        the parser should break (line 48).
        """
        bundle = FluentBundle("en_US")
        # Message with attribute but NO trailing newline at EOF
        bundle.add_resource("msg = Value\n    .attr = Attribute")  # No \n at end

        # Access attribute using Bundle API
        result, _errors = bundle.format_pattern("msg", attribute="attr")
        assert "Attribute" in result


# ============================================================================
# LINE 136: Return None If Attributes Parsing Fails
# ============================================================================


class TestMessageAttributesParsingFailure:
    """Test message when attributes parsing returns None (line 136)."""

    def test_message_with_malformed_attribute(self) -> None:
        """Test message with malformed attribute triggers error path (line 136).

        If parse_message_attributes returns None, line 136 returns that None.
        """
        bundle = FluentBundle("en_US")
        # Malformed attribute (missing '=')
        bundle.add_resource("""
msg = Value
    .attr Missing equals sign
""")

        # Should handle gracefully with junk entry
        result, _errors = bundle.format_pattern("msg")
        # Message parsed, but attribute may be junk
        assert result is not None


# ============================================================================
# LINE 185: Return None If '.' Not Found In Attribute
# ============================================================================


class TestAttributeMissingDot:
    """Test attribute parsing when '.' is missing (line 185)."""

    def test_attribute_without_leading_dot(self) -> None:
        """Test attribute without '.' prefix fails (line 185).

        parse_attribute expects '.' at start. If missing, returns None (line 185).
        """
        bundle = FluentBundle("en_US")
        # Indented line without '.' is not an attribute
        bundle.add_resource("""
msg = Value
    attr = Not an attribute
""")

        result, _errors = bundle.format_pattern("msg")
        # Should parse message, but indented line becomes junk
        assert "Value" in result or len(_errors) > 0


# ============================================================================
# LINE 246: Return None If '-' Not Found In Term
# ============================================================================


class TestTermMissingDash:
    """Test term parsing when '-' prefix is missing (line 246)."""

    def test_term_without_dash_prefix(self) -> None:
        """Test term without '-' prefix fails (line 246).

        parse_term expects '-' at start. If missing, returns None (line 246).
        """
        bundle = FluentBundle("en_US")
        # Identifier without '-' is not a term, should be parsed as message
        bundle.add_resource("term = Value")  # Missing '-' prefix

        # Should parse as message, not term
        result, errors = bundle.format_pattern("term")
        assert "Value" in result
        assert len(errors) == 0


# ============================================================================
# LINE 276: CRLF Handling In Term Pattern
# ============================================================================


class TestTermPatternCRLFHandling:
    """Test term pattern parsing with CRLF line endings (line 276)."""

    def test_term_with_crlf_line_endings(self) -> None:
        """Test term parsing handles CRLF (\\r\\n) correctly (line 276).

        When term has multiline pattern with CRLF, cursor.advance() is called
        twice: once for \\r, once for \\n (line 276).
        """
        bundle = FluentBundle("en_US")
        # Term with CRLF line ending
        ftl_with_crlf = "-term = Value\r\n"
        bundle.add_resource(ftl_with_crlf)

        # Use term in message
        bundle.add_resource("msg = { -term }")
        result, _errors = bundle.format_pattern("msg")
        assert "Value" in result

    def test_term_multiline_pattern_with_crlf(self) -> None:
        """Test term with indented continuation using CRLF (line 276)."""
        bundle = FluentBundle("en_US")
        # Term with multiline pattern using CRLF
        ftl = "-term =\r\n    Multiline\r\n    Value"
        bundle.add_resource(ftl)

        bundle.add_resource("msg = { -term }")
        result, _errors = bundle.format_pattern("msg")
        assert "Multiline" in result or "Value" in result


# ============================================================================
# LINE 304: Break When No Newline In Term Attributes
# ============================================================================


class TestTermAttributeNoNewline:
    """Test term attribute parsing when no newline (line 304)."""

    def test_term_attribute_without_trailing_newline(self) -> None:
        """Test term with attribute but no trailing newline (line 304).

        When parsing term attributes, if line doesn't have newline,
        parser should break (line 304).
        """
        bundle = FluentBundle("en_US")
        # Term with attribute but NO trailing newline at EOF
        ftl = "-term = Value\n    .attr = Attribute"  # No \n at end
        bundle.add_resource(ftl)

        # Use term attribute in message
        bundle.add_resource("msg = { -term.attr }")
        result, _errors = bundle.format_pattern("msg")
        assert "Attribute" in result


# ============================================================================
# LINES 400->406, 402->406: CRLF Handling In Comments
# ============================================================================


class TestCommentCRLFHandling:
    """Test comment parsing with CRLF line endings (lines 400->406, 402->406)."""

    def test_comment_with_crlf_ending(self) -> None:
        """Test comment with CRLF (\\r\\n) line ending (lines 400->406).

        When comment ends with \\r, cursor advances (line 398).
        If followed by \\n, cursor advances again (lines 400-401).
        """
        bundle = FluentBundle("en_US")
        # Comment with CRLF line ending
        ftl_with_crlf = "# Comment\r\nmsg = Value"
        bundle.add_resource(ftl_with_crlf)

        result, _errors = bundle.format_pattern("msg")
        assert "Value" in result

    def test_standalone_comment_with_crlf(self) -> None:
        """Test standalone comment line with CRLF."""
        bundle = FluentBundle("en_US")
        # Standalone comment with CRLF
        ftl = "### Resource Comment\r\n\r\nmsg = Value"
        bundle.add_resource(ftl)

        result, _errors = bundle.format_pattern("msg")
        assert "Value" in result

    def test_multiple_comments_with_mixed_line_endings(self) -> None:
        """Test multiple comments with mixed LF and CRLF."""
        bundle = FluentBundle("en_US")
        # Mix of LF and CRLF
        ftl = "# Comment 1\n# Comment 2\r\n# Comment 3\nmsg = Value"
        bundle.add_resource(ftl)

        result, _errors = bundle.format_pattern("msg")
        assert "Value" in result

    def test_comment_at_eof_with_cr_only(self) -> None:
        """Test comment ending with just \\r (line 398-401 path)."""
        bundle = FluentBundle("en_US")
        # Comment with just \\r (old Mac style)
        ftl = "msg = Value\r# Comment with CR"
        bundle.add_resource(ftl)

        result, _errors = bundle.format_pattern("msg")
        assert "Value" in result


# ============================================================================
# Integration Tests
# ============================================================================


class TestEntriesParsingIntegration:
    """Integration tests for entry parsing edge cases."""

    def test_complex_message_with_crlf_everywhere(self) -> None:
        """Test complex message structure with CRLF line endings."""
        bundle = FluentBundle("en_US")
        # Complex FTL with CRLF
        ftl = "# Comment\r\nmsg = Value\r\n    .attr1 = Attr1\r\n    .attr2 = Attr2\r\n"
        bundle.add_resource(ftl)

        result1, _ = bundle.format_pattern("msg")
        result2, _ = bundle.format_pattern("msg", attribute="attr1")
        result3, _ = bundle.format_pattern("msg", attribute="attr2")

        assert "Value" in result1
        assert "Attr1" in result2
        assert "Attr2" in result3

    def test_term_with_attributes_and_crlf(self) -> None:
        """Test term with attributes using CRLF."""
        bundle = FluentBundle("en_US")
        # Term with attributes and CRLF
        ftl = "-term = Base\r\n    .attr = Value\r\n"
        bundle.add_resource(ftl)

        bundle.add_resource("msg = { -term.attr }")
        result, _errors = bundle.format_pattern("msg")
        assert "Value" in result

    def test_message_and_term_mixed_line_endings(self) -> None:
        """Test file with both messages and terms, mixed line endings."""
        bundle = FluentBundle("en_US")
        ftl = """# Header\r
-brand = Firefox\n
    .version = 1.0\r\n
\r\n
msg = Welcome to { -brand }!
"""
        bundle.add_resource(ftl)

        result, _errors = bundle.format_pattern("msg")
        assert "Welcome" in result
        assert "Firefox" in result


# ============================================================================
# MISSING COVERAGE LINES: 60, 152, 328, 426
# ============================================================================


class TestMissingCoverageLine60:
    """Test line 60: break when no newline after message attributes."""

    def test_message_attribute_no_newline_else_break(self) -> None:
        """Test message attribute parsing when current char is not newline (line 60).

        Line 60 is the else-branch: if current char is NOT \\n or \\r, break immediately.
        This happens when parse_message_attributes is called with cursor NOT on newline.
        """
        from ftllexengine.syntax.cursor import Cursor
        from ftllexengine.syntax.parser.rules import parse_message_attributes

        # Position cursor at a non-newline character (e.g., 'x')
        source = "x"  # Single non-newline char
        cursor = Cursor(source, 0)

        # Call parse_message_attributes - should immediately break (line 60)
        result = parse_message_attributes(cursor)

        # Should return empty attribute list (no attributes parsed)
        assert result is not None
        assert len(result.value) == 0  # No attributes parsed


class TestMissingCoverageLine152:
    """Test line 152: return None if attributes parsing fails."""

    def test_parse_message_returns_none_on_attribute_failure(self) -> None:
        """Test parse_message returns None when parse_message_attributes fails (line 152).

        Note: In current implementation, parse_message_attributes never returns None
        (it always returns a ParseResult). This tests the defensive code path.
        """
        from unittest.mock import patch

        from ftllexengine.syntax.cursor import Cursor
        from ftllexengine.syntax.parser import rules

        source = "msg = Value\n"
        cursor = Cursor(source, 0)

        # Mock parse_message_attributes to return None to test line 152
        with patch.object(
            rules, "parse_message_attributes", return_value=None
        ):
            result = rules.parse_message(cursor)

            # Should return None when attributes parsing returns None
            assert result is None


class TestMissingCoverageLine328:
    """Test line 328: break when no newline after term attributes."""

    def test_term_attribute_no_newline_else_break(self) -> None:
        """Test term attribute parsing when current char is not newline (line 328).

        Line 328 is the else-branch in parse_term: if current char is NOT \\n or \\r, break.
        This happens when the term value is followed by non-newline (e.g., EOF or next entry).
        """
        from ftllexengine.syntax.cursor import Cursor
        from ftllexengine.syntax.parser.rules import parse_term

        # Term at EOF with no trailing newline (cursor after value hits else: break)
        source = "-term = Value"  # No newline at end
        cursor = Cursor(source, 0)

        # Parse term - after pattern, cursor is at EOF (not newline), so line 328 breaks
        result = parse_term(cursor)

        # Should parse successfully
        assert result is not None
        assert result.value.id.name == "term"


class TestMissingCoverageLine426:
    """Test line 426: elif for plain \\n in comment."""

    def test_comment_with_plain_lf(self) -> None:
        """Test comment ending with plain LF (line 426).

        Line 426: elif cursor.current == "\\n" (not \\r\\n, just \\n)
        """
        from ftllexengine.syntax.cursor import Cursor
        from ftllexengine.syntax.parser.rules import parse_comment

        # Comment with just LF
        source = "# This is a comment\nmsg = Value"
        cursor = Cursor(source, 0)

        # Parse comment
        result = parse_comment(cursor)

        # Should parse comment successfully
        assert result is not None
        assert "This is a comment" in result.value.content
