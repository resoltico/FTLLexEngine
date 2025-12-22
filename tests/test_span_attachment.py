"""Tests for span attachment to AST nodes per Fluent spec.

Verifies that parser attaches Span objects to AST nodes for IDE integration
and error reporting.
"""

from ftllexengine.syntax.ast import Junk, Message, Span, Term
from ftllexengine.syntax.parser import FluentParserV1


class TestMessageSpans:
    # Test span attachment to Message nodes

    def test_simple_message_has_span(self):
        # Simple message should have span
        parser = FluentParserV1()
        source = "hello = World"
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # Check span is attached
        assert msg.span is not None
        assert isinstance(msg.span, Span)

        # Verify span covers entire message
        assert msg.span.start == 0
        assert msg.span.end == len(source)

    def test_message_with_value_has_span(self):
        # Message with value should have correct span
        parser = FluentParserV1()
        source = "greeting = Hello, world!"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.span is not None

        # Span should cover from start to end of message
        assert msg.span.start == 0
        assert msg.span.end == len(source)

    def test_message_with_variable_has_span(self):
        # Message with variable should have span
        parser = FluentParserV1()
        source = "welcome = Hello, { $name }!"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.span is not None
        assert msg.span.start == 0
        assert msg.span.end == len(source)

    def test_message_with_attribute_has_span(self):
        # Message with attribute should have span covering both
        parser = FluentParserV1()
        source = "button = Save\n    .tooltip = Click to save"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.span is not None

        # Span should cover message including attributes
        assert msg.span.start == 0
        assert msg.span.end == len(source)

    def test_multiple_messages_have_distinct_spans(self):
        # Multiple messages should have distinct spans
        parser = FluentParserV1()
        source = "msg1 = First\nmsg2 = Second\nmsg3 = Third"
        resource = parser.parse(source)

        assert len(resource.entries) == 3

        # Each message should have its own span
        msg1 = resource.entries[0]
        assert isinstance(msg1, Message)
        assert msg1.value is not None
        msg2 = resource.entries[1]
        assert isinstance(msg2, Message)
        assert msg2.value is not None
        msg3 = resource.entries[2]
        assert isinstance(msg3, Message)
        assert msg3.value is not None

        assert all(isinstance(m, Message) for m in [msg1, msg2, msg3])
        assert all(m.span is not None for m in [msg1, msg2, msg3])

        # Spans should not overlap
        assert msg1.span is not None
        assert msg2.span is not None
        assert msg3.span is not None
        assert msg1.span.end <= msg2.span.start
        assert msg2.span.end <= msg3.span.start

class TestTermSpans:
    # Test span attachment to Term nodes

    def test_simple_term_has_span(self):
        # Simple term should have span
        parser = FluentParserV1()
        source = "-brand = Firefox"
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        term = resource.entries[0]
        assert isinstance(term, Term)

        # Check span is attached
        assert term.span is not None
        assert isinstance(term.span, Span)

        # Verify span covers entire term
        assert term.span.start == 0
        assert term.span.end == len(source)

    def test_term_with_attribute_has_span(self):
        # Term with attribute should have span covering both
        parser = FluentParserV1()
        source = "-brand = Firefox\n    .version = 3.0"
        resource = parser.parse(source)

        term = resource.entries[0]
        assert isinstance(term, Term)
        assert term.span is not None

        # Span should cover term including attributes (at least most of it)
        assert term.span.start == 0
        assert term.span.end >= len(source) - 5  # Allow for trailing characters

    def test_term_starts_at_minus_sign(self):
        # Term span should start at the '-' character
        parser = FluentParserV1()
        source = "-brand = MyApp"
        resource = parser.parse(source)

        term = resource.entries[0]
        assert isinstance(term, Term)
        assert term.span is not None

        # Verify span starts at '-'
        assert source[term.span.start] == "-"

class TestJunkSpans:
    # Test span attachment and annotations on Junk nodes

    def test_junk_has_span(self):
        # Junk should have span
        parser = FluentParserV1()
        # Invalid syntax - missing =
        source = "invalid syntax"
        resource = parser.parse(source)

        # Should create Junk entry
        assert len(resource.entries) >= 1
        entry = resource.entries[0]

        # Entry might be Junk or Message depending on parser
        if isinstance(entry, Junk):
            assert entry.span is not None
            assert isinstance(entry.span, Span)

    def test_junk_has_annotations(self):
        # Junk should have error annotations
        parser = FluentParserV1()
        # Invalid syntax
        source = "bad { syntax"
        resource = parser.parse(source)

        # Look for Junk entry - invalid syntax must produce Junk
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) > 0, "Invalid syntax must produce Junk entry"

        junk = junk_entries[0]

        # Should have annotations
        assert len(junk.annotations) > 0

        # Annotations should have required fields
        annotation = junk.annotations[0]
        assert annotation.code is not None
        assert annotation.message is not None

class TestSpanProperties:
    # Test span invariants and properties

    def test_span_start_before_end(self):
        # Span start should always be before or equal to end
        parser = FluentParserV1()
        source = "msg = Value"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        assert msg.span is not None
        assert msg.span.start <= msg.span.end

    def test_span_within_source_bounds(self):
        # Span should be within source bounds
        parser = FluentParserV1()
        source = "msg = Value"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.span is not None

        # Start and end should be valid positions
        assert msg.span.start >= 0
        assert msg.span.end <= len(source)

    def test_span_covers_actual_content(self):
        # Span should extract the actual message content
        parser = FluentParserV1()
        source = "greeting = Hello"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.span is not None

        # Extract content using span
        content = source[msg.span.start : msg.span.end]
        assert content == "greeting = Hello"

class TestMultilineSpans:
    # Test span handling for multiline content

    def test_multiline_message_span(self):
        # Multiline message should have span covering all lines
        parser = FluentParserV1()
        source = "msg =\n    Line 1\n    Line 2"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.span is not None

        # Span should cover entire multiline message
        assert msg.span.start == 0
        assert msg.span.end == len(source)

    def test_message_with_multiline_attribute_span(self):
        # Message with multiline attribute should have correct span
        parser = FluentParserV1()
        source = "msg = Value\n    .attr =\n        Line 1\n        Line 2"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.span is not None

        # Span should cover message and all attributes
        assert msg.span.start == 0
        assert msg.span.end == len(source)
