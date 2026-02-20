"""Tests for Fluent parser line ending handling per FTL EBNF specification.

Per EBNF grammar:
    line_end ::= "\u000D\u000A" | "\u000A" | EOF

The parser must correctly handle:
- Unix line endings (LF: \\n)
- Windows line endings (CRLF: \\r\\n)
- Legacy Mac line endings (CR: \\r)
- Mixed line endings in the same file

The reference implementation normalizes all line endings to LF before parsing.
This file verifies the behavioral contract across all line ending variants.

Python 3.13+.
"""

from __future__ import annotations

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.ast import Message, Term
from ftllexengine.syntax.parser import FluentParserV1

from .strategies import mixed_line_endings_text


class TestSimpleMessageLineEndings:
    """Single-line simple messages are parsed correctly with all line ending variants."""

    def test_lf_ending(self) -> None:
        """Unix LF line ending produces a valid Message."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Hello\n")
        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.id.name == "msg"
        assert msg.value is not None

    def test_crlf_ending(self) -> None:
        """Windows CRLF line ending produces a valid Message."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Hello\r\n")
        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.id.name == "msg"
        assert msg.value is not None

    def test_cr_ending(self) -> None:
        """Legacy Mac CR-only line ending produces a valid Message."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Hello\r")
        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.id.name == "msg"

    def test_multiple_messages_crlf(self) -> None:
        """Multiple messages separated by CRLF are all parsed."""
        parser = FluentParserV1()
        source = "msg1 = First\r\nmsg2 = Second\r\nmsg3 = Third\r\n"
        resource = parser.parse(source)
        assert len(resource.entries) == 3
        assert all(isinstance(e, Message) for e in resource.entries)
        names = [e.id.name for e in resource.entries if isinstance(e, Message)]
        assert names == ["msg1", "msg2", "msg3"]

    def test_no_final_line_ending(self) -> None:
        """EOF is a valid line_end per spec: message without trailing newline parses."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Value")
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)

    def test_crlf_at_eof(self) -> None:
        """CRLF at end of file is handled correctly."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Value\r\n")
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)


class TestMultilinePatternLineEndings:
    """Multiline pattern continuation lines work with all line ending variants."""

    def test_multiline_crlf(self) -> None:
        """Multiline pattern with CRLF continuation lines is parsed."""
        parser = FluentParserV1()
        source = "msg =\r\n    Line one\r\n    Line two\r\n"
        resource = parser.parse(source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) >= 1

    def test_multiline_mixed_endings(self) -> None:
        """Multiline pattern with mixed LF and CRLF continuation lines is parsed."""
        parser = FluentParserV1()
        source = "msg =\r\n    Line one\n    Line two\r\n    Line three\r\n"
        resource = parser.parse(source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_continuation_after_crlf(self) -> None:
        """Indented continuation line after CRLF is recognized as part of the message."""
        parser = FluentParserV1()
        source = "msg = First line\r\n    continued here\r\n"
        resource = parser.parse(source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_crlf_in_placeables(self) -> None:
        """Message with placeables on multiple CRLF lines is parsed."""
        parser = FluentParserV1()
        source = "msg = Hello { $name }\r\n    How are you?\r\n"
        resource = parser.parse(source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None


class TestAttributeLineEndings:
    """Attribute definitions are parsed correctly with all line ending variants."""

    def test_single_attribute_crlf(self) -> None:
        """Single attribute on CRLF line is parsed."""
        parser = FluentParserV1()
        source = "msg = Value\r\n    .attr = Attribute\r\n"
        resource = parser.parse(source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.attributes) == 1
        assert msg.attributes[0].id.name == "attr"

    def test_multiple_attributes_crlf(self) -> None:
        """Multiple attributes on CRLF lines are all parsed."""
        parser = FluentParserV1()
        source = "msg = Value\r\n    .attr1 = First\r\n    .attr2 = Second\r\n"
        resource = parser.parse(source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) == 2
        assert msg.attributes[0].id.name == "attr1"
        assert msg.attributes[1].id.name == "attr2"

    def test_attribute_with_multiline_value_crlf(self) -> None:
        """Attribute with multiline value using CRLF is parsed."""
        parser = FluentParserV1()
        source = "msg = Value\r\n    .attr =\r\n        Line 1\r\n        Line 2\r\n"
        resource = parser.parse(source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) == 1


class TestCommentLineEndings:
    """Comments are parsed correctly with CRLF line endings."""

    def test_single_line_comment_crlf(self) -> None:
        """Single-line comment with CRLF is followed by a parseable message."""
        parser = FluentParserV1()
        source = "# This is a comment\r\nmsg = Value\r\n"
        resource = parser.parse(source)
        assert any(isinstance(e, Message) for e in resource.entries)

    def test_multiple_comments_crlf(self) -> None:
        """Multiple comments with CRLF are followed by a parseable message."""
        parser = FluentParserV1()
        source = "# Comment 1\r\n# Comment 2\r\nmsg = Value\r\n"
        resource = parser.parse(source)
        assert any(isinstance(e, Message) for e in resource.entries)

    def test_group_comment_crlf(self) -> None:
        """Group comment (##) with CRLF is parsed."""
        parser = FluentParserV1()
        source = "## Group comment\r\nmsg = Value\r\n"
        resource = parser.parse(source)
        assert len(resource.entries) >= 1


class TestSelectExpressionLineEndings:
    """Select expressions are parsed correctly with CRLF line endings."""

    def test_select_crlf(self) -> None:
        """Select expression with CRLF variant lines is parsed."""
        parser = FluentParserV1()
        source = "msg = { $count ->\r\n    [one] One item\r\n   *[other] Many items\r\n}\r\n"
        resource = parser.parse(source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_select_multiple_variants_crlf(self) -> None:
        """Select expression with multiple CRLF variants is parsed."""
        parser = FluentParserV1()
        source = (
            "msg = { $count ->\r\n"
            "    [zero] Zero\r\n"
            "    [one] One\r\n"
            "    [two] Two\r\n"
            "   *[other] Many\r\n"
            "}\r\n"
        )
        resource = parser.parse(source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None


class TestTermLineEndings:
    """Term definitions are parsed correctly with CRLF line endings."""

    def test_simple_term_crlf(self) -> None:
        """Simple term with CRLF is parsed."""
        parser = FluentParserV1()
        resource = parser.parse("-brand = Firefox\r\n")
        assert len(resource.entries) == 1
        term = resource.entries[0]
        assert isinstance(term, Term)
        assert term.id.name == "brand"

    def test_term_with_attribute_crlf(self) -> None:
        """Term with attribute using CRLF is parsed."""
        parser = FluentParserV1()
        source = "-brand = Firefox\r\n    .gender = masculine\r\n"
        resource = parser.parse(source)
        term = resource.entries[0]
        assert isinstance(term, Term)
        assert len(term.attributes) == 1


class TestWhitespaceLineEndings:
    """Whitespace handling interacts correctly with CRLF line endings."""

    def test_trailing_spaces_before_crlf(self) -> None:
        """Trailing spaces before CRLF do not affect parsing."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Value   \r\n")
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)

    def test_empty_lines_crlf(self) -> None:
        """Empty lines with CRLF between messages are handled correctly."""
        parser = FluentParserV1()
        source = "msg1 = First\r\n\r\nmsg2 = Second\r\n"
        resource = parser.parse(source)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) >= 2

    def test_blank_line_with_spaces_crlf(self) -> None:
        """Blank lines containing only spaces and CRLF between messages are handled."""
        parser = FluentParserV1()
        source = "msg1 = First\r\n    \r\nmsg2 = Second\r\n"
        resource = parser.parse(source)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) >= 1

    def test_mixed_line_endings_in_file(self) -> None:
        """Parser handles files with both LF and CRLF line endings."""
        parser = FluentParserV1()
        source = "msg1 = First\nmsg2 = Second\r\nmsg3 = Third\r\n"
        resource = parser.parse(source)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) >= 1


class TestLineEndingHypothesisProperties:
    """Property-based verification of line ending handling invariants."""

    @given(line_ending=st.sampled_from(["\n", "\r\n", "\r"]))
    @settings(max_examples=20)
    def test_simple_message_any_line_ending(self, line_ending: str) -> None:
        """Property: A simple message parses with any valid FTL line ending."""
        _ending_names = {"\n": "LF", "\r\n": "CRLF", "\r": "CR"}
        event(f"line_ending={_ending_names.get(line_ending, 'unknown')}")
        parser = FluentParserV1()
        source = f"msg = Hello{line_ending}"
        resource = parser.parse(source)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert messages[0].id.name == "msg"

    @given(source=mixed_line_endings_text())
    @settings(max_examples=50)
    def test_mixed_endings_never_crash(self, source: str) -> None:
        """Property: Parser never crashes on any mixed-line-ending input."""
        event(f"has_crlf={'crlf' if chr(13) in source else 'lf_only'}")
        parser = FluentParserV1()
        # Must not raise any exception
        resource = parser.parse(source)
        assert resource is not None

    @given(
        n_messages=st.integers(min_value=1, max_value=10),
        line_ending=st.sampled_from(["\n", "\r\n"]),
    )
    @settings(max_examples=30)
    def test_multiple_messages_count_preserved(self, n_messages: int, line_ending: str) -> None:
        """Property: N valid messages separated by any line ending all parse."""
        ending_name = "CRLF" if line_ending == "\r\n" else "LF"
        event(f"n_messages={n_messages}")
        event(f"line_ending={ending_name}")
        parser = FluentParserV1()
        lines = [f"msg{i} = Value {i}" for i in range(n_messages)]
        source = line_ending.join(lines) + line_ending
        resource = parser.parse(source)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == n_messages
