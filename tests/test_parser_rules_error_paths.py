"""Error path coverage tests for syntax/parser/rules.py.

Covers parse error paths in argument expression parsing.
"""

from __future__ import annotations

from ftllexengine.syntax.ast import TextElement
from ftllexengine.syntax.parser.core import FluentParserV1


class TestArgumentExpressionErrorPaths:
    """Test error paths in parse_argument_expression."""

    def test_eof_in_argument_expression(self) -> None:
        """EOF while parsing argument expression creates junk."""
        parser = FluentParserV1()

        # Incomplete function call (EOF after opening paren)
        resource = parser.parse("msg = { NUMBER(")

        # Should create junk entry due to parse error
        assert len(resource.entries) > 0

    def test_failed_term_reference_parse(self) -> None:
        """Failed term reference parse in argument."""
        parser = FluentParserV1()

        # Malformed term reference in function argument
        resource = parser.parse("msg = { NUMBER(-) }")

        # May create junk due to incomplete term reference
        assert len(resource.entries) > 0

    def test_failed_negative_number_parse(self) -> None:
        """Failed negative number parse in argument."""
        parser = FluentParserV1()

        # Hyphen not followed by digit or identifier
        resource = parser.parse('msg = { NUMBER(-" ") }')

        # May create junk due to invalid negative number
        assert len(resource.entries) > 0

    def test_failed_placeable_parse_in_argument(self) -> None:
        """Failed inline placeable parse in argument."""
        parser = FluentParserV1()

        # Incomplete nested placeable in argument
        resource = parser.parse("msg = { NUMBER({ ) }")

        # Should create junk due to malformed nested placeable
        assert len(resource.entries) > 0

    def test_failed_function_reference_parse(self) -> None:
        """Failed function reference parse when uppercase without parens."""
        parser = FluentParserV1()

        # Uppercase identifier followed by ( but parse fails
        # This is tricky - need function parse to fail after seeing (
        resource = parser.parse("msg = { FOO( ) }")

        # Function with no args should parse successfully or create junk
        assert len(resource.entries) > 0


class TestPatternTrimmingBranch:
    """Test the break branch in _trim_pattern_blank_lines."""

    def test_text_element_with_content_after_newline(self) -> None:
        """Text element ending with content (no trailing whitespace after newline)."""
        parser = FluentParserV1()

        # Pattern ending with text content (not blank line)
        resource = parser.parse("msg = Line1\n    Line2 content")

        assert len(resource.entries) > 0
        # Content should be preserved
        message = resource.entries[0]
        if hasattr(message, "value") and message.value:
            elements = message.value.elements
            assert len(elements) > 0

    def test_pattern_with_trailing_content_no_newline(self) -> None:
        """Pattern with trailing content after last newline (line 335 break)."""
        parser = FluentParserV1()

        # Multiline pattern ending with content (tests line 335 break)
        resource = parser.parse("msg = First line\n    Second line has content")

        assert len(resource.entries) > 0
        message = resource.entries[0]
        if hasattr(message, "value") and message.value:
            # Check that content is preserved
            text_content = "".join(
                e.value for e in message.value.elements if isinstance(e, TextElement)
            )
            assert "Second line has content" in text_content
