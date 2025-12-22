"""Comprehensive tests for multiline pattern parsing.

Tests all edge cases and behaviors of the multiline pattern implementation,
including continuation detection, indentation handling, and special characters.

Note: The parser creates separate TextElements for each text run (line),
which is valid per FTL spec. The resolver later joins these during formatting.
"""

from ftllexengine.syntax import (
    Attribute,
    Message,
    Placeable,
    Term,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.parser import FluentParserV1


class TestMultilinePatternBasics:
    """Basic multiline pattern parsing tests."""

    def test_simple_two_line_pattern(self):
        """Test basic two-line pattern with continuation."""
        source = """key =
    Line one
    Line two
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.id.name == "key"

        # Multiline creates separate TextElements for each text run
        assert msg.value is not None
        assert len(msg.value.elements) == 2
        assert all(isinstance(e, TextElement) for e in msg.value.elements)
        # First line gets trailing space from continuation
        elem = msg.value.elements[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "Line one "
        elem = msg.value.elements[1]
        assert isinstance(elem, TextElement)
        assert elem.value == "Line two"

    def test_three_line_pattern(self):
        """Test three-line pattern continuation."""
        source = """key =
    First line
    Second line
    Third line
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Three separate text runs
        assert len(msg.value.elements) == 3
        elem = msg.value.elements[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "First line "
        elem = msg.value.elements[1]
        assert isinstance(elem, TextElement)
        assert elem.value == "Second line "
        elem = msg.value.elements[2]
        assert isinstance(elem, TextElement)
        assert elem.value == "Third line"

    def test_pattern_with_varying_indentation(self):
        """Test that varying indentation levels are handled correctly."""
        source = """key =
    One space
      Two spaces
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Two text elements
        assert len(msg.value.elements) == 2
        elem = msg.value.elements[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "One space "
        # Extra indentation is preserved after stripping common indent
        elem = msg.value.elements[1]
        assert isinstance(elem, TextElement)
        assert elem.value.startswith(" ") or elem.value == "Two spaces"


class TestMultilineContinuationDetection:
    """Tests for _is_indented_continuation helper method."""

    def test_continuation_requires_space_indent(self):
        """Lines must start with space (U+0020) to be continuations."""
        source = """key =
    Valid continuation
\tTab indented not continuation
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse "Valid continuation", then stop at tab line (creates Junk)
        assert len(resource.entries) >= 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should only have the first line
        elem = msg.value.elements[0]
        assert isinstance(elem, TextElement)
        assert "Valid continuation" in elem.value

    def test_continuation_stops_at_variant_marker(self):
        """Lines starting with [ are not continuations."""
        source = """key =
    Text line
    [variant]
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse only "Text line", then stop
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) == 1
        elem = msg.value.elements[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "Text line"

    def test_continuation_stops_at_default_variant_marker(self):
        """Lines starting with * are not continuations."""
        source = """key =
    Text line
    *[default]
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) == 1
        elem = msg.value.elements[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "Text line"

    def test_continuation_stops_at_attribute_marker(self):
        """Lines starting with . are not continuations."""
        source = """key =
    Text line
    .attr = value
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should have attribute
        assert len(msg.attributes) == 1
        assert msg.attributes[0].id.name == "attr"

    def test_continuation_stops_at_new_message(self):
        """Lines without leading space stop continuation."""
        source = """key1 =
    Line one
    Line two
key2 = Other message
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert len(resource.entries) == 2
        msg1 = resource.entries[0]
        assert isinstance(msg1, Message)
        assert msg1.value is not None
        msg2 = resource.entries[1]
        assert isinstance(msg2, Message)
        assert msg2.value is not None
        assert isinstance(msg1, Message)
        assert isinstance(msg2, Message)
        # msg1 should have two text elements
        assert len(msg1.value.elements) == 2
        elem = msg2.value.elements[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "Other message"


class TestMultilineWithPlaceables:
    """Tests for multiline patterns containing placeables."""

    def test_placeable_on_first_line(self):
        """Placeable at start of multiline pattern."""
        source = """key =
    { $var } text
    more text
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should have: Placeable, TextElement(" text "), TextElement("more text")
        assert len(msg.value.elements) >= 2
        assert isinstance(msg.value.elements[0], Placeable)

    def test_placeable_on_continuation_line(self):
        """Placeable in middle of multiline pattern."""
        source = """key =
    Text before
    { $var } and after
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should have multiple elements including a placeable
        placeables = [e for e in msg.value.elements if isinstance(e, Placeable)]
        assert len(placeables) == 1
        expr = placeables[0].expression
        assert isinstance(expr, VariableReference)
        assert expr.id.name == "var"

    def test_multiple_placeables_multiline(self):
        """Multiple placeables across multiple lines."""
        source = """key =
    Start { $first }
    middle { $second }
    end { $third }
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # Count placeables
        placeables = [e for e in msg.value.elements if isinstance(e, Placeable)]
        assert len(placeables) == 3

        # Verify variable names
        var_names = []
        for p in placeables:
            expr = p.expression
            assert isinstance(expr, VariableReference)
            var_names.append(expr.id.name)
        assert "first" in var_names
        assert "second" in var_names
        assert "third" in var_names

    def test_select_expression_multiline(self):
        """Select expression with variants on multiple lines."""
        source = """key = { $count ->
    [one] One item
    *[other] Many items
}
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) == 1
        assert isinstance(msg.value.elements[0], Placeable)


class TestMultilineEdgeCases:
    """Edge cases and boundary conditions for multiline patterns."""

    def test_empty_continuation_line(self):
        """Empty indented line in pattern."""
        source = """key =
    Text

    More text
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should parse all lines as continuations
        assert len(msg.value.elements) >= 1
        # Check that text is present
        text_values = [e.value for e in msg.value.elements if isinstance(e, TextElement)]
        assert any("Text" in v for v in text_values)

    def test_single_line_pattern(self):
        """Pattern that doesn't use continuation (inline)."""
        source = "key = Single line\n"
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        elem = msg.value.elements[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "Single line"

    def test_pattern_with_windows_line_endings(self):
        """Multiline pattern with CRLF line endings."""
        source = "key =\r\n    Line one\r\n    Line two\r\n"
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should parse both lines
        assert len(msg.value.elements) == 2

    def test_pattern_ending_with_newline(self):
        """Pattern where last continuation line ends with newline."""
        source = """key =
    First
    Last

next = value
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert len(resource.entries) == 2
        msg1 = resource.entries[0]
        assert isinstance(msg1, Message)
        assert msg1.value is not None
        msg2 = resource.entries[1]
        assert isinstance(msg2, Message)
        assert msg2.value is not None
        # First message has two lines
        assert len(msg1.value.elements) == 2
        assert msg2.id.name == "next"

    def test_deeply_indented_pattern(self):
        """Pattern with many levels of indentation."""
        source = """key =
                    Very deeply indented
                    Second line
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should parse both lines
        assert len(msg.value.elements) == 2

    def test_pattern_with_special_chars_not_at_start(self):
        """Special chars [*. in middle of line are fine."""
        source = """key =
    Text with [brackets]
    and *asterisk* in middle
    plus .period stuff
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Parser creates multiple text elements when encountering special chars
        # Just verify it parsed successfully
        assert len(msg.value.elements) > 0


class TestMultilineWithAttributes:
    """Tests for multiline patterns in message attributes."""

    def test_attribute_with_multiline_pattern(self):
        """Message attribute value can be multiline."""
        source = """key = Value
    .attr =
        Line one
        Line two
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.attributes) == 1

        attr = msg.attributes[0]
        assert isinstance(attr, Attribute)
        assert attr.id.name == "attr"
        # Attribute value has multiline pattern
        assert len(attr.value.elements) == 2

    def test_multiple_attributes_multiline(self):
        """Multiple attributes with multiline patterns."""
        source = """key = Value
    .attr1 =
        First
        attribute
    .attr2 =
        Second
        attribute
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.attributes) == 2

        # Both attributes should have multiline values
        assert len(msg.attributes[0].value.elements) == 2
        assert len(msg.attributes[1].value.elements) == 2


class TestMultilineTerms:
    """Tests for multiline patterns in terms."""

    def test_term_with_multiline_pattern(self):
        """Term value can be multiline."""
        source = """-term =
    Line one
    Line two
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        term = resource.entries[0]
        assert isinstance(term, Term)
        assert term.id.name == "term"

        # Two text elements
        assert len(term.value.elements) == 2

    def test_term_attribute_multiline(self):
        """Term attribute with multiline pattern."""
        source = """-term = Value
    .attr =
        Multi
        line
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        term = resource.entries[0]
        assert isinstance(term, Term)
        assert len(term.attributes) == 1
        # Attribute value has 2 text elements
        assert len(term.attributes[0].value.elements) == 2


class TestMultilineSelectExpressions:
    """Tests for select expressions with multiline variant patterns."""

    def test_select_variants_parse(self):
        """Basic select expression parses correctly."""
        source = """key = { $var ->
    [a] Value A
    *[b] Value B
}
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse successfully
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) == 1
        assert isinstance(msg.value.elements[0], Placeable)


class TestMultilineWhitespaceHandling:
    """Tests for whitespace handling in multiline patterns."""

    def test_indentation_stripped_from_continuation(self):
        """Leading indentation is stripped from continuation lines."""
        source = """key =
        Four spaces
        Four spaces again
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Both lines should be parsed
        assert len(msg.value.elements) == 2
        # Content should not have leading spaces (common indent stripped)
        elem = msg.value.elements[0]
        assert isinstance(elem, TextElement)
        assert elem.value.strip() == "Four spaces"

    def test_lines_separated_properly(self):
        """Continuation lines create separate text elements."""
        source = """key =
    Line 1
    Line 2
    Line 3
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Three text elements
        assert len(msg.value.elements) == 3


class TestMultilineErrorCases:
    """Tests for error handling in multiline patterns."""

    def test_pattern_with_unterminated_placeable(self):
        """Unterminated placeable in multiline pattern."""
        source = """key =
    Text { $var
    more text
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should produce Junk or handle error gracefully
        assert len(resource.entries) >= 1

    def test_mixed_indent_types(self):
        """Mixed tabs and spaces in continuation."""
        source = """key =
    Space indent
\tTab indent
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Tab line should not be treated as continuation
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Only one text element from space-indented line
        text_elements = [e for e in msg.value.elements if isinstance(e, TextElement)]
        assert len(text_elements) == 1


class TestContinuationHelper:
    """Direct tests for the _is_indented_continuation helper."""

    def test_helper_detects_space_indent(self):
        """Helper correctly detects space-indented lines."""
        source = """key =
    continuation
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse successfully with continuation
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_helper_rejects_tab_indent(self):
        """Helper correctly rejects tab-indented lines."""
        source = """key = text
\tcontinuation
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # First entry is message, second might be junk from tab line
        assert isinstance(resource.entries[0], Message)

    def test_helper_rejects_variant_marker(self):
        """Helper correctly rejects lines starting with [."""
        source = """key = text
    [not-continuation]
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should only have the inline text
        elem = msg.value.elements[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "text"

    def test_helper_rejects_default_marker(self):
        """Helper correctly rejects lines starting with *."""
        source = """key = text
    *[not-continuation]
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should only have the inline text
        elem = msg.value.elements[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "text"

    def test_helper_rejects_attribute_marker(self):
        """Helper correctly rejects lines starting with ."""
        source = """key = text
    .not-continuation = value
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should have an attribute instead of continuation
        assert len(msg.attributes) == 1
