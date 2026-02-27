"""Tests for parser entry-level functions.

Tests parse_message, parse_message_header, parse_message_attributes,
parse_attribute, parse_term, parse_comment, and validate_message_content.
Also covers CRLF handling, pattern trimming integration, and
FluentParserV1 entry parsing paths.
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.enums import CommentType
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import (
    Attribute,
    Message,
    Pattern,
    Term,
    TextElement,
)
from ftllexengine.syntax.cursor import Cursor, ParseResult
from ftllexengine.syntax.parser import rules
from ftllexengine.syntax.parser.core import FluentParserV1
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    parse_attribute,
    parse_comment,
    parse_message,
    parse_message_attributes,
    parse_message_header,
    parse_pattern,
    parse_term,
)
from ftllexengine.syntax.parser.whitespace import (
    skip_multiline_pattern_start,
)

# ============================================================================
# PARSE MESSAGE HEADER
# ============================================================================


class TestParseMessageHeader:
    """Tests for parse_message_header paths."""

    def test_missing_equals(self) -> None:
        """Returns None when '=' is missing after ID."""
        assert parse_message_header(Cursor("hello", 0)) is None

    def test_identifier_fails(self) -> None:
        """Returns None when identifier starts with digit."""
        assert parse_message_header(Cursor("123", 0)) is None

    def test_id_followed_by_spaces(self) -> None:
        """Returns None when ID followed by spaces, no '='."""
        assert parse_message_header(Cursor("msgid   ", 0)) is None

    def test_id_at_eof(self) -> None:
        """Returns None at EOF after ID."""
        assert parse_message_header(Cursor("msgid", 0)) is None

    def test_id_followed_by_newline(self) -> None:
        """Returns None when newline after ID, no '='."""
        assert parse_message_header(Cursor("msgid\n", 0)) is None

    def test_valid_header(self) -> None:
        """Parses valid message header."""
        result = parse_message_header(Cursor("hello = value", 0))
        assert result is not None
        name, _end_pos = result.value
        assert name == "hello"


# ============================================================================
# PARSE MESSAGE ATTRIBUTES
# ============================================================================


class TestParseMessageAttributes:
    """Tests for parse_message_attributes paths."""

    def test_no_newline_stops(self) -> None:
        """No newline: done with attributes."""
        result = parse_message_attributes(Cursor("text", 0))
        assert result is not None
        assert len(result.value) == 0

    def test_no_dot_stops(self) -> None:
        """No dot after whitespace stops."""
        result = parse_message_attributes(Cursor("\n  text", 0))
        assert result is not None
        assert len(result.value) == 0

    def test_parse_fails_stops(self) -> None:
        """Attribute parse fails stops iteration."""
        result = parse_message_attributes(Cursor("\n.@", 0))
        assert result is not None
        assert isinstance(result.value, list)

    def test_multiple_attributes(self) -> None:
        """Multiple attributes parsed in loop."""
        text = "hello = value\n.one = 1\n.two = 2"
        cursor = Cursor(text, 0)
        header_result = parse_message_header(cursor)
        assert header_result is not None
        cursor = header_result.cursor
        cursor, initial_indent = skip_multiline_pattern_start(cursor)
        pattern_result = parse_pattern(
            cursor, initial_common_indent=initial_indent
        )
        assert pattern_result is not None
        cursor = pattern_result.cursor
        attr_result = parse_message_attributes(cursor)
        assert attr_result is not None
        assert len(attr_result.value) == 2

    def test_non_newline_char_breaks(self) -> None:
        """Non-newline character triggers immediate break."""
        result = parse_message_attributes(Cursor("x", 0))
        assert result is not None
        assert len(result.value) == 0


# ============================================================================
# PARSE MESSAGE
# ============================================================================


class TestParseMessage:
    """Tests for parse_message paths."""

    def test_header_fails(self) -> None:
        """Returns None when message header fails."""
        assert parse_message(Cursor("123 = value", 0)) is None

    def test_valid_message(self) -> None:
        """Parses valid message."""
        result = parse_message(Cursor("hello = value", 0))
        assert result is not None
        assert isinstance(result.value, Message)
        assert result.value.id.name == "hello"

    def test_empty_pattern_fails_validation(self) -> None:
        """Empty pattern with no attributes fails validation."""
        assert parse_message(Cursor("hello = ", 0)) is None

    def test_attributes_only(self) -> None:
        """Message with attributes but no pattern."""
        result = parse_message(
            Cursor("hello =\n    .attr = val", 0),
            ParseContext(),
        )
        assert result is not None

    def test_pattern_mock_fails(self) -> None:
        """Returns None when parse_pattern returns None."""
        with patch(
            "ftllexengine.syntax.parser.rules.parse_pattern",
            return_value=None,
        ):
            assert parse_message(
                Cursor("msg = Value", 0)
            ) is None

    def test_attributes_mock_fails(self) -> None:
        """Returns None when parse_message_attributes returns None."""
        with patch.object(
            rules, "parse_message_attributes",
            return_value=None,
        ):
            assert rules.parse_message(
                Cursor("msg = Value\n", 0)
            ) is None


# ============================================================================
# PARSE ATTRIBUTE
# ============================================================================


class TestParseAttribute:
    """Tests for parse_attribute paths."""

    def test_missing_dot(self) -> None:
        """Returns None without '.' prefix."""
        assert parse_attribute(Cursor("attr = value", 0)) is None

    def test_at_eof(self) -> None:
        """Returns None at EOF."""
        assert parse_attribute(Cursor("", 0)) is None

    def test_identifier_fails(self) -> None:
        """Returns None when identifier fails after dot."""
        assert parse_attribute(Cursor(".123", 0)) is None

    def test_identifier_spaces_fails(self) -> None:
        """Returns None with spaces after dot."""
        assert parse_attribute(Cursor(".   ", 0)) is None

    def test_missing_equals(self) -> None:
        """Returns None when '=' missing after identifier."""
        assert parse_attribute(Cursor(".attr", 0)) is None

    def test_valid_attribute(self) -> None:
        """Parses valid attribute."""
        result = parse_attribute(Cursor(".attr = value", 0))
        assert result is not None
        assert isinstance(result.value, Attribute)
        assert result.value.id.name == "attr"

    def test_pattern_mock_fails(self) -> None:
        """Returns None when parse_pattern returns None."""
        with patch(
            "ftllexengine.syntax.parser.rules.parse_pattern",
            return_value=None,
        ):
            assert parse_attribute(
                Cursor(".attr = ", 0)
            ) is None

    def test_empty_pattern_succeeds(self) -> None:
        """Attribute with empty pattern returns result."""
        result = parse_attribute(Cursor(".attr = ", 0))
        assert result is not None

    def test_attribute_with_continuation(self) -> None:
        """Attribute with continuation spacing patterns."""
        source = (
            "    .tooltip = \n"
            "        Line 1\n"
            "            \n"
            "            Line 2\n"
            "              "
        )
        result = parse_attribute(Cursor(source, 0), ParseContext())
        assert result is not None
        assert isinstance(result.value, Attribute)
        assert result.value.value is not None


# ============================================================================
# PARSE TERM
# ============================================================================


class TestParseTerm:
    """Tests for parse_term paths."""

    def test_missing_hyphen(self) -> None:
        """Returns None without '-' prefix."""
        assert parse_term(Cursor("brand = value", 0)) is None

    def test_at_eof(self) -> None:
        """Returns None at EOF."""
        assert parse_term(Cursor("", 0)) is None

    def test_identifier_fails(self) -> None:
        """Returns None when identifier fails after hyphen."""
        assert parse_term(Cursor("-123", 0)) is None

    def test_identifier_spaces_fails(self) -> None:
        """Returns None with spaces after hyphen."""
        assert parse_term(Cursor("-   ", 0)) is None

    def test_missing_equals(self) -> None:
        """Returns None when '=' missing."""
        assert parse_term(Cursor("-brand", 0)) is None

    def test_missing_equals_with_spaces(self) -> None:
        """Returns None with spaces after ID, no '='."""
        assert parse_term(Cursor("-term   ", 0)) is None

    def test_empty_value_fails(self) -> None:
        """Term with empty pattern fails."""
        assert parse_term(Cursor("-brand = ", 0)) is None

    def test_valid_term(self) -> None:
        """Parses valid term."""
        result = parse_term(Cursor("-brand = value", 0))
        assert result is not None
        assert isinstance(result.value, Term)
        assert result.value.id.name == "brand"

    def test_multiline_indented(self) -> None:
        """Term with indented continuation."""
        result = parse_term(Cursor("-brand =\n    Firefox", 0))
        assert result is not None
        assert result.value.value.elements

    def test_newline_not_indented(self) -> None:
        """Newline without indented continuation fails."""
        assert parse_term(Cursor("-brand =\nvalue", 0)) is None

    def test_attributes(self) -> None:
        """Term with attributes."""
        result = parse_term(
            Cursor("-brand = value", 0)
        )
        assert result is not None

    def test_no_trailing_newline(self) -> None:
        """Term at EOF with no trailing newline."""
        result = parse_term(Cursor("-term = Value", 0))
        assert result is not None
        assert result.value.id.name == "term"
        assert len(result.value.attributes) == 0

    def test_trailing_space_breaks_attr_loop(self) -> None:
        """Trailing space after value triggers attribute loop break."""
        result = parse_term(Cursor("-term = Value ", 0))
        assert result is not None
        assert len(result.value.attributes) == 0

    def test_pattern_mock_fails(self) -> None:
        """Returns None when parse_pattern returns None."""
        with patch(
            "ftllexengine.syntax.parser.rules.parse_pattern",
            return_value=None,
        ):
            assert parse_term(
                Cursor("-term = Value", 0)
            ) is None

    def test_empty_pattern_mock_fails_validation(self) -> None:
        """Returns None when pattern is empty."""
        empty_pattern = Pattern(elements=())
        source = "-term = "

        def mock_parse_pattern(
            cursor, context=None, *,  # noqa: ARG001
            initial_common_indent=None,  # noqa: ARG001
        ):
            return ParseResult(empty_pattern, cursor)

        with patch(
            "ftllexengine.syntax.parser.rules.parse_pattern",
            side_effect=mock_parse_pattern,
        ):
            assert parse_term(Cursor(source, 0)) is None

    def test_cursor_on_space_after_pattern(self) -> None:
        """Cursor on space after pattern triggers attr loop break."""
        source = "-term = Value  msg"

        def mock_parse_pattern(
            cursor_arg, context=None, *,  # noqa: ARG001
            initial_common_indent=None,  # noqa: ARG001
        ):
            pattern = Pattern(elements=(TextElement("Value"),))
            return ParseResult(pattern, Cursor(source, 14))

        with patch(
            "ftllexengine.syntax.parser.rules.parse_pattern",
            side_effect=mock_parse_pattern,
        ):
            result = parse_term(Cursor(source, 0))
        assert result is not None
        assert result.value.id.name == "term"

    def test_invalid_attribute_syntax(self) -> None:
        """Invalid attribute syntax restores cursor and breaks."""
        source = "-term = Value\n.invalid"
        original = rules.parse_attribute

        def mock_attr(cursor, context=None):
            if ".invalid" in cursor.source[cursor.pos:]:
                return None
            return original(cursor, context)

        with patch.object(
            rules, "parse_attribute", side_effect=mock_attr
        ):
            result = parse_term(Cursor(source, 0))
        assert result is not None
        assert len(result.value.attributes) == 0

    def test_continuation_blank_lines_and_spacing(self) -> None:
        """Complex continuation patterns in term."""
        source = (
            "-brand = \n"
            "    Firefox\n"
            "    \n"
            "        {$version}\n"
            "          "
        )
        result = parse_term(Cursor(source, 0), ParseContext())
        assert result is not None
        assert isinstance(result.value, Term)
        assert result.value.value is not None


# ============================================================================
# PARSE TERM CRLF & LINE ENDINGS
# ============================================================================


class TestTermCRLFHandling:
    """Tests for CRLF handling in term parsing."""

    def test_cr_at_eof(self) -> None:
        """Term pattern with CR at EOF."""
        result = parse_term(
            Cursor("-term =\r    Value\r", 0)
        )
        assert result is not None
        assert result.value.id.name == "term"

    def test_cr_not_followed_by_lf(self) -> None:
        """Term with CR NOT followed by LF (old Mac style)."""
        result = parse_term(
            Cursor("-term =\r    Value\rmsg = Other", 0)
        )
        assert result is not None
        assert result.value.id.name == "term"

    def test_newline_not_indented_empty_pattern(self) -> None:
        """Newline but no indentation gives empty pattern."""
        source = "-term = \nmsg = Other"

        def mock_parse_pattern(
            cursor, context=None, *,  # noqa: ARG001
            initial_common_indent=None,  # noqa: ARG001
        ):
            return ParseResult(Pattern(elements=()), cursor)

        with patch(
            "ftllexengine.syntax.parser.rules.parse_pattern",
            side_effect=mock_parse_pattern,
        ):
            assert parse_term(Cursor(source, 0)) is None


# ============================================================================
# PARSE COMMENT
# ============================================================================


class TestParseComment:
    """Tests for parse_comment paths."""

    def test_single_hash(self) -> None:
        """Single hash comment."""
        result = parse_comment(Cursor("# Comment\n", 0))
        assert result is not None
        assert result.value.type == CommentType.COMMENT

    def test_double_hash(self) -> None:
        """Double hash group comment."""
        result = parse_comment(Cursor("## Group\n", 0))
        assert result is not None
        assert result.value.type == CommentType.GROUP

    def test_triple_hash(self) -> None:
        """Triple hash resource comment."""
        result = parse_comment(Cursor("### Resource\n", 0))
        assert result is not None
        assert result.value.type == CommentType.RESOURCE

    def test_too_many_hashes(self) -> None:
        """More than 3 hashes returns None."""
        assert parse_comment(Cursor("#### Invalid\n", 0)) is None

    def test_five_hashes(self) -> None:
        """Five hashes returns None."""
        assert parse_comment(Cursor("##### Also\n", 0)) is None

    def test_space_after_hash(self) -> None:
        """Space after hash is optional."""
        result = parse_comment(Cursor("# Comment text\n", 0))
        assert result is not None
        assert result.value.content == "Comment text"

    def test_no_space_after_hash(self) -> None:
        """No space after hash parses content directly."""
        result = parse_comment(Cursor("#CommentText\n", 0))
        assert result is not None
        assert result.value.content == "CommentText"

    def test_empty_content(self) -> None:
        """Just '#' and newline gives empty content."""
        result = parse_comment(Cursor("#\n", 0))
        assert result is not None
        assert result.value.content == ""

    def test_at_eof_no_newline(self) -> None:
        """Comment at EOF with no line ending."""
        result = parse_comment(Cursor("# Comment at EOF", 0))
        assert result is not None
        assert result.value.content == "Comment at EOF"
        assert result.cursor.is_eof

    def test_lf_line_ending(self) -> None:
        """Comment with LF ending."""
        result = parse_comment(
            Cursor("# Comment with LF\nmsg = Value", 0)
        )
        assert result is not None
        assert "Comment with LF" in result.value.content
        assert result.cursor.source[result.cursor.pos] == "m"

    def test_lf_only_explicit(self) -> None:
        """LF-only comment without space after hash."""
        result = parse_comment(Cursor("#Test\n", 0))
        assert result is not None
        assert result.value.content == "Test"
        assert (
            result.cursor.is_eof
            or result.cursor.pos == len("#Test\n")
        )

    def test_cr_only_not_line_end(self) -> None:
        """CR-only is NOT a line ending (requires normalization)."""
        result = parse_comment(
            Cursor("# Comment\rmsg = Other", 0)
        )
        assert result is not None
        assert result.value.content == "Comment\rmsg = Other"
        assert result.cursor.is_eof

    @given(st.text(min_size=0, max_size=100))
    def test_arbitrary_content_property(
        self, content: str
    ) -> None:
        """Comment with arbitrary content parses correctly."""
        clean = content.replace("\n", "").replace("\r", "")
        event(f"content_len={len(clean)}")
        text = f"# {clean}\n"
        result = parse_comment(Cursor(text, 0))
        if result is not None:
            assert result.value.content == clean


# ============================================================================
# COMMENT CRLF (via FluentBundle)
# ============================================================================


class TestCommentCRLFViaBundle:
    """Tests for CRLF handling in comments via FluentBundle."""

    def test_comment_with_crlf(self) -> None:
        """Comment with CRLF line ending."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("# Comment\r\nmsg = Value")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "Value" in result

    def test_standalone_comment_crlf(self) -> None:
        """Standalone comment with CRLF."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "### Resource Comment\r\n\r\nmsg = Value"
        )
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "Value" in result

    def test_mixed_line_endings(self) -> None:
        """Multiple comments with mixed LF and CRLF."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "# Comment 1\n# Comment 2\r\n"
            "# Comment 3\nmsg = Value"
        )
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "Value" in result


# ============================================================================
# ENTRY INTEGRATION VIA FLUENTBUNDLE
# ============================================================================


class TestEntryIntegrationViaBundle:
    """Integration tests for entry parsing via FluentBundle."""

    def test_message_attribute_no_trailing_newline(self) -> None:
        """Message with attribute, no trailing newline."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "msg = Value\n    .attr = Attribute"
        )
        result, errors = bundle.format_pattern(
            "msg", attribute="attr"
        )
        assert not errors
        assert "Attribute" in result

    def test_malformed_attribute(self) -> None:
        """Message with malformed attribute uses soft-error recovery (strict=False)."""
        bundle = FluentBundle("en_US", strict=False)
        bundle.add_resource(
            "\nmsg = Value\n    .attr Missing equals sign\n"
        )
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert result is not None

    def test_term_crlf(self) -> None:
        """Term with CRLF line ending."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("-term = Value\r\n")
        bundle.add_resource("msg = { -term }")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "Value" in result

    def test_term_multiline_crlf(self) -> None:
        """Term with indented continuation using CRLF."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "-term =\r\n    Multiline\r\n    Value"
        )
        bundle.add_resource("msg = { -term }")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "Multiline" in result or "Value" in result

    def test_term_attribute_no_trailing_newline(self) -> None:
        """Term with attribute, no trailing newline."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "-term = Value\n    .attr = Attribute"
        )
        bundle.add_resource("msg = { -term.attr }")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "Attribute" in result

    def test_complex_message_crlf(self) -> None:
        """Complex message structure with CRLF."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "# Comment\r\nmsg = Value\r\n"
            "    .attr1 = Attr1\r\n    .attr2 = Attr2\r\n"
        )
        r1, _ = bundle.format_pattern("msg")
        r2, _ = bundle.format_pattern("msg", attribute="attr1")
        r3, _ = bundle.format_pattern("msg", attribute="attr2")
        assert "Value" in r1
        assert "Attr1" in r2
        assert "Attr2" in r3

    def test_term_with_attributes_crlf(self) -> None:
        """Term with attributes using CRLF."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "-term = Base\r\n    .attr = Value\r\n"
        )
        bundle.add_resource("msg = { -term.attr }")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "Value" in result


# ============================================================================
# ENTRY PARSING VIA FLUENTPARSERV1
# ============================================================================


class TestEntryViaParser:
    """Tests for entry parsing via FluentParserV1."""

    def test_message_no_trailing_newline(self) -> None:
        """Message without trailing newline."""
        parser = FluentParserV1()
        resource = parser.parse("key = value")
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        elem = msg.value.elements[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "value"

    def test_term_parsed_as_message(self) -> None:
        """Identifier without '-' parsed as message, not term."""
        parser = FluentParserV1()
        resource = parser.parse("term = value")
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.id.name == "term"

    def test_pattern_trimming_preserves_content(self) -> None:
        """Pattern trimming preserves content after newline."""
        parser = FluentParserV1()
        resource = parser.parse(
            "\nmsg = Line one\n    Line two with spaces\n"
        )
        message = resource.entries[0]
        assert isinstance(message, Message)
        assert message.value is not None
        text = "".join(
            e.value
            for e in message.value.elements
            if isinstance(e, TextElement)
        )
        assert "Line one" in text
        assert "Line two with spaces" in text

    def test_trailing_spaces_preserved(self) -> None:
        """Trailing spaces on content line preserved."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Hello World   ")
        message = resource.entries[0]
        assert isinstance(message, Message)
        assert message.value is not None
        elem = message.value.elements[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "Hello World   "

    def test_trailing_blank_lines_trimmed(self) -> None:
        """Trailing blank lines removed."""
        parser = FluentParserV1()
        resource = parser.parse(
            "\nmsg = Content here\n    More content\n\n"
        )
        message = resource.entries[0]
        assert isinstance(message, Message)
        assert message.value is not None
        text = "".join(
            e.value
            for e in message.value.elements
            if isinstance(e, TextElement)
        )
        assert "Content here" in text
        assert "More content" in text
        assert not text.endswith("\n   ")

    def test_multiline_non_blank_final(self) -> None:
        """Multiline pattern with non-blank final line."""
        parser = FluentParserV1()
        resource = parser.parse(
            "\nmsg = First\n    Second\n    Third\n"
        )
        message = resource.entries[0]
        assert isinstance(message, Message)
        assert message.value is not None
        text = "".join(
            e.value
            for e in message.value.elements
            if isinstance(e, TextElement)
        )
        assert "First" in text
        assert "Third" in text

    def test_whitespace_elements_removed(self) -> None:
        """All-whitespace pattern elements removed."""
        parser = FluentParserV1()
        resource = parser.parse("\nmsg =\n\n    value\n\n")
        messages = [
            e for e in resource.entries if hasattr(e, "id")
        ]
        assert len(messages) > 0

    def test_pattern_trimming_various_cases(self) -> None:
        """Pattern trimming across various content patterns."""
        parser = FluentParserV1()
        cases = [
            "msg = Content",
            "msg = Content\n    ",
            "msg = Line1\n    Line2",
            "msg = A\n    B\n    C",
            "msg = Text   ",
        ]
        for ftl_source in cases:
            resource = parser.parse(ftl_source)
            if not resource.entries:
                continue
            message = resource.entries[0]
            if not isinstance(message, Message):
                continue
            if message.value is None:
                continue
            assert len(message.value.elements) > 0
            text_elems = [
                e
                for e in message.value.elements
                if isinstance(e, TextElement)
            ]
            assert any(e.value.strip() for e in text_elems)


# ============================================================================
# PATTERN CONTINUATION IN ENTRIES
# ============================================================================


class TestPatternContinuationInEntries:
    """Tests for pattern continuation through entry parsing."""

    def test_consecutive_blank_lines(self) -> None:
        """Multiple consecutive newlines in continuation."""
        source = "hello = text\n    \n    \n    continued"
        result = parse_message(
            Cursor(source, 0), ParseContext()
        )
        assert result is not None
        msg = result.value
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_extra_indentation(self) -> None:
        """Extra indentation beyond common indent."""
        source = "hello = line1\n    line2\n        line3"
        result = parse_message(
            Cursor(source, 0), ParseContext()
        )
        assert result is not None
        assert isinstance(result.value, Message)
        assert result.value.value is not None

    def test_extra_spaces_before_placeable(self) -> None:
        """Extra indent before placeable in pattern."""
        source = "hello = \n    line1\n        {$var}"
        result = parse_message(
            Cursor(source, 0), ParseContext()
        )
        assert result is not None
        assert result.value.value is not None
        assert len(result.value.value.elements) >= 2

    def test_accumulated_text_prepended(self) -> None:
        """Accumulated extra spaces prepended to new text."""
        source = "hello = \n    line1\n        line2"
        result = parse_message(
            Cursor(source, 0), ParseContext()
        )
        assert result is not None
        assert isinstance(result.value, Message)
        assert result.value.value is not None

    def test_trailing_spaces(self) -> None:
        """Trailing extra-indented spaces."""
        source = "hello = \n    text\n          "
        result = parse_message(
            Cursor(source, 0), ParseContext()
        )
        assert result is not None
        assert isinstance(result.value, Message)

    def test_all_continuation_edge_cases(self) -> None:
        """Message exercising all continuation edge cases."""
        source = (
            "msg =\n"
            "    Line 1\n"
            "\n"
            "        Line 2\n"
            "            {$var1}\n"
            "                Text after\n"
            "                    {$var2}\n"
            "              "
        )
        result = parse_message(
            Cursor(source, 0), ParseContext()
        )
        assert result is not None
        assert isinstance(result.value, Message)
        assert result.value.value is not None
        assert len(result.value.value.elements) >= 4
