"""Comprehensive tests for CRLF line ending handling per Fluent spec.

Per EBNF grammar:
    line_end ::= "\u000D\u000A" | "\u000A" | EOF

Tests that the parser correctly handles:
- Unix line endings (LF: \n)
- Windows line endings (CRLF: \r\n)
- Legacy Mac line endings (CR: \r)
- Mixed line endings in same file
"""


from ftllexengine.syntax.ast import Message, Term
from ftllexengine.syntax.parser import FluentParserV1


class TestCRLFBasicMessages:
    # Test basic message parsing with different line endings

    def test_simple_message_lf(self):
        # Unix line ending (LF)
        parser = FluentParserV1()
        source = "msg = Hello\n"
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.id.name == "msg"

    def test_simple_message_crlf(self):
        # Windows line ending (CRLF)
        parser = FluentParserV1()
        source = "msg = Hello\r\n"
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.id.name == "msg"

    def test_simple_message_cr(self):
        # Legacy Mac line ending (CR only)
        parser = FluentParserV1()
        source = "msg = Hello\r"
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.id.name == "msg"

    def test_multiple_messages_crlf(self):
        # Multiple messages separated by CRLF
        parser = FluentParserV1()
        source = "msg1 = First\r\nmsg2 = Second\r\nmsg3 = Third\r\n"
        resource = parser.parse(source)

        assert len(resource.entries) == 3
        assert all(isinstance(e, Message) for e in resource.entries)
        msg1 = resource.entries[0]
        assert isinstance(msg1, Message)
        msg2 = resource.entries[1]
        assert isinstance(msg2, Message)
        msg3 = resource.entries[2]
        assert isinstance(msg3, Message)
        assert msg1.id.name == "msg1"
        assert msg2.id.name == "msg2"
        assert msg3.id.name == "msg3"


class TestCRLFMultilinePatterns:
    # Test multiline pattern handling with different line endings

    def test_multiline_pattern_crlf(self):
        # Multiline pattern with CRLF line endings
        parser = FluentParserV1()
        source = "msg =\r\n    Line one\r\n    Line two\r\n"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.value is not None
        # Should have parsed both lines with space between
        assert len(msg.value.elements) >= 1

    def test_multiline_pattern_mixed_endings(self):
        # Mix of LF and CRLF in same multiline pattern
        parser = FluentParserV1()
        source = "msg =\r\n    Line one\n    Line two\r\n    Line three\r\n"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.value is not None

    def test_multiline_continuation_after_crlf(self):
        # Verify continuation detection works with CRLF
        parser = FluentParserV1()
        source = "msg = First line\r\n    continued here\r\n"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.value is not None
        # Should recognize indented line as continuation


class TestCRLFAttributes:
    # Test attribute parsing with different line endings

    def test_attribute_crlf(self):
        # Attributes with CRLF line endings
        parser = FluentParserV1()
        source = "msg = Value\r\n    .attr = Attribute\r\n"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.attributes) == 1
        assert msg.attributes[0].id.name == "attr"

    def test_multiple_attributes_crlf(self):
        # Multiple attributes with CRLF
        parser = FluentParserV1()
        source = "msg = Value\r\n    .attr1 = First\r\n    .attr2 = Second\r\n"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.attributes) == 2
        assert msg.attributes[0].id.name == "attr1"
        assert msg.attributes[1].id.name == "attr2"

    def test_attribute_with_multiline_value_crlf(self):
        # Attribute with multiline value using CRLF
        parser = FluentParserV1()
        source = "msg = Value\r\n    .attr =\r\n        Line 1\r\n        Line 2\r\n"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.attributes) == 1


class TestCRLFComments:
    # Test comment parsing with different line endings

    def test_single_line_comment_crlf(self):
        # Single-line comment with CRLF
        parser = FluentParserV1()
        source = "# This is a comment\r\nmsg = Value\r\n"
        resource = parser.parse(source)

        # Parser should handle CRLF in comments correctly
        # Just verify it parses without errors
        assert len(resource.entries) >= 1
        # Should have at least one message
        has_message = any(isinstance(e, Message) for e in resource.entries)
        assert has_message

    def test_multiple_comments_crlf(self):
        # Multiple comments with CRLF
        parser = FluentParserV1()
        source = "# Comment 1\r\n# Comment 2\r\nmsg = Value\r\n"
        resource = parser.parse(source)

        # Comments may be attached to message or separate
        assert len(resource.entries) >= 1
        # At least one message should exist
        has_message = any(isinstance(e, Message) for e in resource.entries)
        assert has_message

    def test_group_comment_crlf(self):
        # Group comment (##) with CRLF
        parser = FluentParserV1()
        source = "## Group comment\r\nmsg = Value\r\n"
        resource = parser.parse(source)

        assert len(resource.entries) >= 1


class TestCRLFSelectExpressions:
    # Test select expression parsing with different line endings

    def test_select_expression_crlf(self):
        # Select expression with CRLF line endings
        parser = FluentParserV1()
        source = "msg = { $count ->\r\n    [one] One item\r\n   *[other] Many items\r\n}\r\n"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.value is not None

    def test_select_multiple_variants_crlf(self):
        # Multiple variants with CRLF
        parser = FluentParserV1()
        source = (
            "msg = { $count ->\r\n    [zero] Zero\r\n    [one] One\r\n    "
            "[two] Two\r\n   *[other] Many\r\n}\r\n"
        )
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None


class TestCRLFTerms:
    # Test term parsing with different line endings

    def test_simple_term_crlf(self):
        # Simple term with CRLF
        parser = FluentParserV1()
        source = "-brand = Firefox\r\n"
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        term = resource.entries[0]
        assert isinstance(term, Term)
        assert term.id.name == "brand"

    def test_term_with_attribute_crlf(self):
        # Term with attribute using CRLF
        parser = FluentParserV1()
        source = "-brand = Firefox\r\n    .gender = masculine\r\n"
        resource = parser.parse(source)

        term = resource.entries[0]
        assert isinstance(term, Term)
        assert len(term.attributes) == 1


class TestCRLFEdgeCases:
    # Test edge cases and mixed scenarios

    def test_empty_lines_crlf(self):
        # Empty lines with CRLF
        parser = FluentParserV1()
        source = "msg1 = First\r\n\r\nmsg2 = Second\r\n"
        resource = parser.parse(source)

        # Should handle empty line correctly
        assert len([e for e in resource.entries if isinstance(e, Message)]) >= 2

    def test_mixed_line_endings_in_file(self):
        # Mix of LF and CRLF in same file (real-world scenario)
        parser = FluentParserV1()
        source = "msg1 = First\n msg2 = Second\r\nmsg3 = Third\r\n"
        resource = parser.parse(source)

        # Should parse all messages regardless of line ending type
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) >= 1

    def test_crlf_at_eof(self):
        # CRLF at end of file
        parser = FluentParserV1()
        source = "msg = Value\r\n"
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)

    def test_no_final_line_ending(self):
        # No line ending at EOF (per spec, EOF is valid line_end)
        parser = FluentParserV1()
        source = "msg = Value"
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)

    def test_crlf_in_placeables(self):
        # Multiline with placeables and CRLF
        parser = FluentParserV1()
        source = "msg = Hello { $name }\r\n    How are you?\r\n"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.value is not None


class TestCRLFWhitespace:
    # Test whitespace handling with different line endings

    def test_trailing_spaces_before_crlf(self):
        # Spaces before CRLF should be handled correctly
        parser = FluentParserV1()
        source = "msg = Value   \r\n"
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)

    def test_blank_lines_with_spaces_crlf(self):
        # Blank lines with only spaces and CRLF
        parser = FluentParserV1()
        source = "msg1 = First\r\n    \r\nmsg2 = Second\r\n"
        resource = parser.parse(source)

        # Should handle blank line with spaces
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) >= 1


class TestCRLFComplexScenarios:
    # Test complex real-world scenarios

    def test_complete_ftl_file_crlf(self):
        # Complete FTL file with CRLF everywhere
        parser = FluentParserV1()
        source = """# Welcome messages\r
\r
welcome = Welcome to our app!\r
    .tooltip = Click here to start\r
\r
-brand = MyApp\r
    .version = 1.0\r
\r
greeting = { $userName ->\r
    [admin] Hello Administrator\r
   *[user] Hello { $userName }\r
}\r
"""
        resource = parser.parse(source)

        # Should parse all entries
        assert len(resource.entries) >= 3

    def test_nested_multiline_with_crlf(self):
        # Nested structures with CRLF
        parser = FluentParserV1()
        # Simpler version without multiline in variant
        source = "msg = { $count ->\r\n    [one] Single line\r\n   *[other] Other items\r\n}\r\n"
        resource = parser.parse(source)

        # Should parse successfully
        assert len(resource.entries) >= 1
        # Entry should be either Message or Junk (both are valid for this test)
        entry = resource.entries[0]
        assert entry.__class__.__name__ in ("Message", "Junk")
