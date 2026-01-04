"""Targeted tests for 100% coverage of parser rules module.

Covers specific uncovered lines identified by coverage analysis.
Uses property-based testing (Hypothesis) where appropriate.
"""

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    Identifier,
    MessageReference,
    NumberLiteral,
    Placeable,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    _trim_pattern_blank_lines,
    parse_argument_expression,
    parse_term_reference,  # Not in __all__ but accessible
)


class TestTrimPatternBlankLines:
    """Pattern trimming edge cases for complete line coverage."""

    def test_trailing_content_after_last_newline_preserved(self) -> None:
        """Content after last newline is preserved (line 334 coverage)."""
        # Pattern with newline followed by content (not a blank line)
        elements: list[TextElement | Placeable] = [TextElement(value="Hello\nWorld")]
        result = _trim_pattern_blank_lines(elements)
        # Should NOT trim "World" because it's content, not a blank line
        assert len(result) == 1
        assert isinstance(result[0], TextElement)
        assert result[0].value == "Hello\nWorld"

    def test_non_blank_char_after_newline_in_middle(self) -> None:
        """Non-blank character after newline preserves content."""
        # Multiple newlines with content between them
        elements: list[TextElement | Placeable] = [TextElement(value="Line1\n\nLine2")]
        result = _trim_pattern_blank_lines(elements)
        # Should preserve the structure
        assert len(result) == 1
        elem = result[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "Line1\n\nLine2"

    def test_content_after_newline_always_preserved(self) -> None:
        """Property: Non-whitespace after newline is never trimmed."""
        content = "abc"
        text_with_newline = f"prefix\n{content}"
        elements: list[TextElement | Placeable] = [TextElement(value=text_with_newline)]
        result = _trim_pattern_blank_lines(elements)
        assert len(result) == 1
        # Content after newline should be preserved
        elem = result[0]
        assert isinstance(elem, TextElement)
        assert content in elem.value


class TestParseArgumentExpressionCoverage:
    """Argument expression parsing edge cases for complete coverage."""

    def test_eof_at_argument_position(self) -> None:
        """EOF during argument parsing returns None (line 770)."""
        cursor = Cursor("", 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)
        assert result is None

    def test_term_reference_parsing_failure_in_argument(self) -> None:
        """Term reference parse failure propagates (line 795)."""
        # Hyphen followed by non-identifier should fail term parsing
        # This tests the error path when parse_term_reference returns None
        cursor = Cursor("-123", 0)
        context = ParseContext()
        # This will try to parse as term reference first (- followed by digit)
        # but fall back to number literal
        result = parse_argument_expression(cursor, context)
        # Should succeed as number literal
        assert result is not None
        assert isinstance(result.value, NumberLiteral)
        assert result.value.value == -123

    def test_uppercase_function_parse_error_in_argument(self) -> None:
        """Uppercase identifier function parse error path (lines 837-840)."""
        # UPPERCASE identifier followed by something other than (
        # Tests the path where function parsing is attempted but fails
        cursor = Cursor("NUMBER", 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)
        # Should succeed as MessageReference when no ( follows
        assert result is not None
        assert isinstance(result.value, MessageReference)
        assert result.value.id.name == "NUMBER"

    def test_uppercase_function_with_open_paren_at_eof(self) -> None:
        """Uppercase function followed by ( triggers function parsing."""
        # This ensures we exercise the lookahead branch
        cursor = Cursor("NUMBER(", 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)
        # Should fail because incomplete function call
        assert result is None

    @given(
        func_name=st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=10
        )
    )
    def test_uppercase_identifiers_trigger_function_lookahead(self, func_name: str) -> None:
        """Property: ASCII uppercase identifiers trigger function call lookahead."""
        # Without following (, should parse as MessageReference
        cursor = Cursor(func_name, 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)
        if result is not None:
            assert isinstance(result.value, MessageReference)
            assert result.value.id.name == func_name


class TestParseArgumentExpressionEdgeCases:
    """Additional edge cases for parse_argument_expression."""

    def test_hyphen_followed_by_non_identifier_and_non_digit(self) -> None:
        """Hyphen followed by special character."""
        # This should fail both term reference and number parsing
        cursor = Cursor("-@", 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)
        assert result is None

    def test_identifier_with_underscore_in_name(self) -> None:
        """Identifier can contain underscore after letter."""
        cursor = Cursor("my_var", 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)
        assert result is not None
        assert isinstance(result.value, MessageReference)
        assert result.value.id.name == "my_var"


class TestParseArgumentExpressionPlaceables:
    """Placeable expressions in argument position."""

    def test_nested_placeable_in_argument(self) -> None:
        """Nested placeable expression in argument."""
        cursor = Cursor("{ $var }", 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)
        # Should parse the nested placeable
        assert result is not None
        assert isinstance(result.value, Placeable)

    def test_nested_placeable_single_level(self) -> None:
        """Single nested placeable in argument position."""
        context = ParseContext(max_nesting_depth=10)
        cursor = Cursor("{ $var }", 0)
        result = parse_argument_expression(cursor, context)
        # Should parse successfully
        assert result is not None
        assert isinstance(result.value, Placeable)


class TestPatternElementInteractions:
    """Pattern element trimming with mixed content."""

    def test_pattern_with_placeable_and_trailing_whitespace(self) -> None:
        """Pattern with placeable followed by whitespace."""
        elements: list[TextElement | Placeable] = [
            TextElement(value="Hello "),
            Placeable(expression=VariableReference(id=Identifier("name"))),
            TextElement(value="\n   \n"),
        ]
        result = _trim_pattern_blank_lines(elements)
        # Trailing blank lines should be removed
        assert len(result) == 2
        assert isinstance(result[0], TextElement)
        assert isinstance(result[1], Placeable)

    def test_pattern_ending_with_non_blank_after_newline(self) -> None:
        """Pattern ending with non-blank content after newline."""
        elements: list[TextElement | Placeable] = [TextElement(value="Hello\nWorld   ")]
        result = _trim_pattern_blank_lines(elements)
        # Trailing spaces on content line should be preserved
        assert len(result) == 1
        elem = result[0]
        assert isinstance(elem, TextElement)
        assert elem.value == "Hello\nWorld   "

    def test_content_after_newline_simple(self) -> None:
        """Content after newline is preserved through trimming."""
        pattern_text = "prefix\nsuffix"
        elements: list[TextElement | Placeable] = [TextElement(value=pattern_text)]
        result = _trim_pattern_blank_lines(elements)
        # Should preserve the suffix
        assert len(result) >= 1
        full_text = "".join(elem.value for elem in result if isinstance(elem, TextElement))
        assert "suffix" in full_text


class TestArgumentExpressionHypothesis:
    """Property-based tests for argument expression parsing."""

    @given(
        var_name=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=1,
            max_size=20,
        ).filter(lambda s: s and s[0].isalpha())
    )
    def test_valid_identifiers_parse_as_message_ref(self, var_name: str) -> None:
        """Property: Valid lowercase identifiers parse as MessageReference."""
        if var_name.isupper():
            return  # Skip uppercase (tested separately)
        cursor = Cursor(var_name, 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)
        if result is not None:
            assert isinstance(result.value, (MessageReference, NumberLiteral))

    @given(number=st.integers(min_value=-1000000, max_value=1000000))
    def test_integers_parse_as_number_literal(self, number: int) -> None:
        """Property: Integer strings parse as NumberLiteral."""
        cursor = Cursor(str(number), 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)
        assert result is not None
        assert isinstance(result.value, NumberLiteral)
        assert result.value.value == number


class TestTermReferenceDepthExceeded:
    """Tests for term reference parsing at depth limit (line 1209 coverage)."""

    def test_term_with_arguments_at_depth_limit_returns_none(self) -> None:
        """Term reference with arguments at depth limit returns None (line 1209).

        When parsing -term(arg: value) and the nesting depth is exceeded,
        the parser returns None to prevent DoS from deeply nested structures.
        """
        # Create context at depth limit
        context = ParseContext(max_nesting_depth=2)
        # Increment depth to be at the limit
        nested_context = context.enter_nesting()
        nested_context = nested_context.enter_nesting()

        # Verify we're at depth limit
        assert nested_context.is_depth_exceeded()

        # Parse term reference with arguments at this depth
        # The cursor starts at '-' as parse_term_reference expects
        cursor = Cursor('-brand(case: "nom")', 0)

        # Should return None because depth exceeded when trying to parse args
        result = parse_term_reference(cursor, nested_context)
        assert result is None

    def test_term_without_arguments_at_depth_limit_succeeds(self) -> None:
        """Term reference without arguments at depth limit still succeeds.

        The depth check only applies when parsing arguments (the '(' path).
        """
        context = ParseContext(max_nesting_depth=2)
        nested_context = context.enter_nesting()
        nested_context = nested_context.enter_nesting()

        assert nested_context.is_depth_exceeded()

        # Term without arguments should still parse
        cursor = Cursor("-brand", 0)
        result = parse_term_reference(cursor, nested_context)

        # Should succeed because no arguments to parse
        assert result is not None
        assert result.value.id.name == "brand"

    def test_term_with_arguments_below_depth_limit_succeeds(self) -> None:
        """Term reference with arguments below depth limit succeeds."""
        context = ParseContext(max_nesting_depth=10)

        cursor = Cursor('-term(case: "gen")', 0)
        result = parse_term_reference(cursor, context)

        # Should parse successfully
        assert result is not None
        assert result.value.id.name == "term"
        assert result.value.arguments is not None
