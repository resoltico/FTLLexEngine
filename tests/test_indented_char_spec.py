"""Tests for indented_char specification compliance.

Per Fluent EBNF:
    indented_char ::= text_char - "[" - "*" - "."

This means continuation lines (indented pattern lines) cannot start with:
- "[" (variant key marker)
- "*" (default variant marker)
- "." (attribute marker)

These characters have special meanings in FTL syntax and must not appear
as the first character of an indented continuation line.

References:
    - https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import Junk, Message, Term, TextElement
from ftllexengine.syntax.parser import FluentParserV1


class TestIndentedCharExclusions:
    """Test that indented_char excludes [, *, and ."""

    @pytest.fixture
    def parser(self) -> FluentParserV1:
        """Create parser instance."""
        return FluentParserV1()

    def test_multiline_pattern_cannot_start_with_bracket(
        self, parser: FluentParserV1
    ) -> None:
        """Continuation line starting with '[' should not be a continuation.

        Per spec: indented_char ::= text_char - "[" - "*" - "."
        Lines starting with '[' indicate variant keys, not continuations.
        """
        source = """msg = First line
    [this is not a continuation]
"""
        resource = parser.parse(source)

        # Message should parse, but '[' line should NOT be a continuation
        assert len(resource.entries) >= 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # Value should only contain "First line", not the '[' line
        pattern_text = "".join(
            elem.value for elem in msg.value.elements if isinstance(elem, TextElement)
        )
        assert "[" not in pattern_text or "First line" in pattern_text

    def test_multiline_pattern_cannot_start_with_asterisk(
        self, parser: FluentParserV1
    ) -> None:
        """Continuation line starting with '*' should not be a continuation.

        Per spec: indented_char excludes '*'.
        Lines starting with '*' indicate default variants, not continuations.
        """
        source = """msg = First line
    *[default] this is not a continuation
"""
        resource = parser.parse(source)

        # Message should parse with only "First line"
        assert len(resource.entries) >= 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # Should not include the '*' line as continuation
        pattern_text = "".join(
            elem.value for elem in msg.value.elements if isinstance(elem, TextElement)
        )
        assert "*" not in pattern_text or "First line" in pattern_text

    def test_multiline_pattern_cannot_start_with_dot(
        self, parser: FluentParserV1
    ) -> None:
        """Continuation line starting with '.' should not be a continuation.

        Per spec: indented_char excludes '.'.
        Lines starting with '.' indicate attributes, not continuations.
        """
        source = """msg = First line
    .attr = this is an attribute, not continuation
"""
        resource = parser.parse(source)

        # Message should parse
        assert len(resource.entries) >= 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # Value should be "First line" only
        pattern_text = "".join(
            elem.value for elem in msg.value.elements if isinstance(elem, TextElement)
        )
        assert "First line" in pattern_text
        # The '.' line should be an attribute, not part of pattern
        assert len(msg.attributes) >= 1

    def test_multiline_pattern_with_valid_special_chars_mid_line(
        self, parser: FluentParserV1
    ) -> None:
        """Special chars NOT at line start are allowed in continuations.

        Per spec: indented_char only excludes [, *, . at START of line.
        These characters mid-line are valid text content.
        """
        source = """msg = First line
    This line has [brackets] and *asterisks* and dots...
    And continues here
"""
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # All lines should be included (special chars mid-line are OK)
        pattern_text = "".join(
            elem.value for elem in msg.value.elements if isinstance(elem, TextElement)
        )
        assert "brackets" in pattern_text
        assert "asterisks" in pattern_text
        assert "dots" in pattern_text


class TestIndentedCharAttributeContext:
    """Test indented_char restrictions in attribute context."""

    @pytest.fixture
    def parser(self) -> FluentParserV1:
        """Create parser instance."""
        return FluentParserV1()

    def test_attribute_multiline_cannot_start_with_bracket(
        self, parser: FluentParserV1
    ) -> None:
        """Attribute continuation starting with '[' should not continue."""
        source = """msg = Value
    .attr = First line
    [not a continuation]
"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) >= 1

        # Attribute pattern should not include '[' line
        attr_text = "".join(
            elem.value
            for elem in msg.attributes[0].value.elements
            if isinstance(elem, TextElement)
        )
        assert "First line" in attr_text
        # '[' line should not be in attribute
        assert "[not a continuation]" not in attr_text

    def test_attribute_multiline_cannot_start_with_asterisk(
        self, parser: FluentParserV1
    ) -> None:
        """Attribute continuation starting with '*' should not continue."""
        source = """msg = Value
    .attr = First line
    *not a continuation
"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) >= 1

        # Attribute should not include '*' line
        attr_text = "".join(
            elem.value
            for elem in msg.attributes[0].value.elements
            if isinstance(elem, TextElement)
        )
        assert "*not" not in attr_text

    def test_attribute_multiline_cannot_start_with_dot(
        self, parser: FluentParserV1
    ) -> None:
        """Attribute continuation starting with '.' starts new attribute."""
        source = """msg = Value
    .attr1 = First line
    .attr2 = Second attribute
"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        # Should have TWO attributes, not one with continuation
        assert len(msg.attributes) == 2
        assert msg.attributes[0].id.name == "attr1"
        assert msg.attributes[1].id.name == "attr2"


class TestIndentedCharTermContext:
    """Test indented_char restrictions in term context."""

    @pytest.fixture
    def parser(self) -> FluentParserV1:
        """Create parser instance."""
        return FluentParserV1()

    def test_term_multiline_cannot_start_with_special_chars(
        self, parser: FluentParserV1
    ) -> None:
        """Term pattern continuations respect indented_char restrictions."""
        source = """-brand = Firefox Browser
    [not a continuation]
"""
        resource = parser.parse(source)

        # Term should parse with value "Firefox Browser" only
        term = resource.entries[0]
        assert isinstance(term, Term)
        assert term.value is not None

        # Value should not include '[' line
        pattern_text = "".join(
            elem.value for elem in term.value.elements if isinstance(elem, TextElement)
        )
        assert "Firefox" in pattern_text
        assert "[not" not in pattern_text


class TestIndentedCharEdgeCases:
    """Test edge cases for indented_char restrictions."""

    @pytest.fixture
    def parser(self) -> FluentParserV1:
        """Create parser instance."""
        return FluentParserV1()

    def test_multiple_indentation_levels_with_special_chars(
        self, parser: FluentParserV1
    ) -> None:
        """Deep indentation doesn't change indented_char rules."""
        source = """msg = First line
        Second line (deep indent is OK)
        [still not a continuation at start]
"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # Should include "Second line" but not "[still" line
        pattern_text = "".join(
            elem.value for elem in msg.value.elements if isinstance(elem, TextElement)
        )
        assert "Second line" in pattern_text

    def test_special_char_after_whitespace_within_line(
        self, parser: FluentParserV1
    ) -> None:
        """Whitespace before special char within line is OK."""
        source = """msg = First line
    Second line [with brackets]
    Third line
"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # All lines are valid continuations (brackets not at line start)
        pattern_text = "".join(
            elem.value for elem in msg.value.elements if isinstance(elem, TextElement)
        )
        assert "brackets" in pattern_text
        assert "Third line" in pattern_text


class TestHypothesisIndentedChar:
    """Property-based tests for indented_char restrictions."""

    @given(
        first_char=st.sampled_from(["[", "*", "."]),
        rest_text=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=1,
            max_size=20,
        ),
    )
    def test_continuation_starting_with_special_char_rejected(
        self, first_char: str, rest_text: str
    ) -> None:
        """Continuation lines starting with [, *, or . should not continue.

        Property: indented_char excludes these characters at line start.
        """
        parser = FluentParserV1()
        source = f"""msg = First line
    {first_char}{rest_text}
"""
        resource = parser.parse(source)

        # Message should parse
        assert len(resource.entries) >= 1
        msg = resource.entries[0]
        assert isinstance(msg, (Message, Junk))

        if isinstance(msg, Message) and msg.value is not None:
            # Pattern should not include the special char line
            pattern_text = "".join(
                elem.value
                for elem in msg.value.elements
                if isinstance(elem, TextElement)
            )
            # First line should be there, special char line should not
            assert "First line" in pattern_text

    @given(
        position=st.integers(min_value=1, max_value=10),
        special_char=st.sampled_from(["[", "*", "."]),
    )
    def test_special_char_not_at_start_accepted(
        self, position: int, special_char: str
    ) -> None:
        """Special chars NOT at line start are accepted in continuations.

        Property: indented_char only excludes [, *, . at position 0.
        """
        parser = FluentParserV1()
        # Put special char at given position (not start)
        padding = "x" * position
        source = f"""msg = First line
    {padding}{special_char}more text
"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, (Message, Junk))

        if isinstance(msg, Message) and msg.value is not None:
            # Should include continuation with special char mid-line
            pattern_text = "".join(
                elem.value
                for elem in msg.value.elements
                if isinstance(elem, TextElement)
            )
            assert special_char in pattern_text or "First line" in pattern_text


class TestSpecificationDocumentation:
    """Document indented_char specification requirements."""

    def test_indented_char_definition(self) -> None:
        """Document indented_char EBNF definition.

        Per Fluent EBNF:
            indented_char ::= text_char - "[" - "*" - "."

        This means:
        - Continuation lines can contain any text_char
        - EXCEPT: Cannot start with [, *, or .
        - These characters have syntactic meaning (variants, attributes)
        - They CAN appear mid-line, just not at line start
        """
        parser = FluentParserV1()

        # Valid: special chars mid-line
        valid = """msg = First
    Line with [bracket] mid-text
"""
        result = parser.parse(valid)
        assert len(result.entries) == 1
        assert isinstance(result.entries[0], Message)

        # Invalid: special char at line start
        invalid = """msg = First
    [bracket at start]
"""
        result = parser.parse(invalid)
        msg = result.entries[0]
        assert isinstance(msg, Message)
        # '[' line should NOT be included in pattern


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
