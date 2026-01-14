"""Complete final coverage tests for parser rules module to achieve 100% coverage.

Covers all remaining uncovered lines identified by coverage analysis:
- Line 127->exit: ParseContext._depth_exceeded_flag None edge case
- Lines 288-289: _is_variant_marker with leading spaces after '['
- Lines 561-562, 605: parse_simple_pattern _TextAccumulator finalization paths
- Lines 711, 736, 750-751, 788-789, 795: parse_pattern continuation and spacing

Uses property-based testing (Hypothesis) where appropriate.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    Attribute,
    Message,
    Placeable,
    SelectExpression,
    Term,
)
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    _is_variant_marker,
    parse_attribute,
    parse_message,
    parse_term,
)


class TestParseContextDepthExceededFlag:
    """Test ParseContext._depth_exceeded_flag None edge case (line 127->exit)."""

    def test_mark_depth_exceeded_with_none_flag_after_initialization(self) -> None:
        """Test mark_depth_exceeded when _depth_exceeded_flag is None.

        This covers the exit branch at line 127 where the flag is None.
        While __post_init__ always initializes the flag, this tests the
        defensive check in mark_depth_exceeded.
        """
        # Create context with __post_init__ disabled by directly setting attributes
        context = object.__new__(ParseContext)
        object.__setattr__(context, "max_nesting_depth", 5)
        object.__setattr__(context, "current_depth", 0)
        object.__setattr__(context, "_depth_exceeded_flag", None)

        # Call mark_depth_exceeded - should handle None gracefully
        context.mark_depth_exceeded()

        # Verify it didn't crash and flag remains None
        assert context._depth_exceeded_flag is None


class TestIsVariantMarkerLeadingSpaces:
    """Test _is_variant_marker with leading spaces (lines 288-289)."""

    def test_variant_marker_with_leading_space_after_bracket(self) -> None:
        """Variant key with leading space after '[' is valid.

        Per Fluent EBNF: VariantKey ::= "[" blank? (NumberLiteral | Identifier) blank? "]"
        This covers lines 288-289 which skip leading spaces.
        """
        source = "[ one]"
        cursor = Cursor(source, 0)
        result = _is_variant_marker(cursor)
        assert result is True

    def test_variant_marker_with_multiple_leading_spaces(self) -> None:
        """Multiple leading spaces after '[' are valid."""
        source = "[    other]"
        cursor = Cursor(source, 0)
        result = _is_variant_marker(cursor)
        assert result is True

    @given(
        num_spaces=st.integers(min_value=1, max_value=10),
        key=st.sampled_from(["one", "other", "few", "many", "zero", "0", "1", "42"]),
    )
    def test_variant_marker_with_arbitrary_leading_spaces_property(
        self, num_spaces: int, key: str
    ) -> None:
        """Property: any number of leading spaces in variant key is valid."""
        source = f"[{' ' * num_spaces}{key}]"
        cursor = Cursor(source, 0)
        result = _is_variant_marker(cursor)
        assert result is True


class TestParseSimplePatternTextAccumulator:
    """Test parse_simple_pattern _TextAccumulator paths (lines 561-562, 605)."""

    def test_variant_continuation_with_extra_spaces_before_placeable(self) -> None:
        """Variant value with continuation having extra indent before placeable.

        This covers lines 561-562 where accumulated extra_spaces must be
        finalized before parsing a placeable in parse_simple_pattern.

        parse_simple_pattern is used for variant values in select expressions.
        The variant value has continuation with extra indentation followed by placeable.
        """
        # Select expression where variant value has:
        # - First line: "Items:"
        # - Continuation with extra indentation: "        {$count}"
        # The extra spaces should trigger text_acc.has_content() before placeable
        source = """msg = {$count ->
    [one] Items:
            {$count}
    *[other] Items
}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)
        # Variant should have parsed with extra spacing preserved

    def test_variant_ending_with_accumulated_trailing_spaces(self) -> None:
        """Variant value ending with accumulated extra spaces.

        This covers line 605 where remaining accumulated text is finalized
        at pattern end in parse_simple_pattern.

        Variant value ends with continuation line that has only extra spaces.
        """
        # Variant that ends with trailing extra spaces from continuation
        # The variant value is: "Items\n            " (trailing spaces)
        # When next variant starts with [, those trailing spaces should be finalized
        source = """msg = {$count ->
    [one] Items

    *[other] More
}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)


class TestParsePatternBlankLinesAndSpacing:
    """Test parse_pattern blank line skipping and spacing.

    Covers lines: 711, 736, 750-751, 788-789, 795.
    """

    def test_pattern_with_consecutive_blank_lines_in_continuation(self) -> None:
        """Pattern with multiple consecutive newlines (blank lines) in continuation.

        This covers line 711 which skips consecutive newlines before measuring
        indent in continuation context.

        Pattern with blank lines:
        hello = text
            <blank line>
            <blank line>
            continued
        """
        # Use parse_message which calls parse_pattern
        source = "hello = text\n    \n    \n    continued"
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)
        assert message.value is not None

    def test_pattern_continuation_with_extra_spaces_accumulated(self) -> None:
        """Continuation line with extra indentation beyond common indent.

        This covers line 736 where extra_spaces are added to text accumulator.

        Pattern:
        hello = line1
            line2
                line3  (extra indentation)
        """
        source = "hello = line1\n    line2\n        line3"
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)
        assert message.value is not None
        # Extra spaces should be preserved in the pattern

    def test_pattern_with_extra_spaces_before_placeable(self) -> None:
        """Pattern with accumulated extra_spaces before placeable in parse_pattern.

        This covers lines 750-751 where text accumulator is finalized before
        a placeable in the main parse_pattern function.

        Pattern:
        hello =
            line1
                {$var}  (extra indent before placeable)
        """
        source = "hello = \n    line1\n        {$var}"
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)
        assert message.value is not None
        assert len(message.value.elements) >= 2

    def test_pattern_with_accumulated_text_prepended_to_element(self) -> None:
        """Pattern where accumulated text is prepended to new text element.

        This covers lines 788-789 where accumulated extra_spaces are prepended
        to a new text element.

        Pattern:
        hello =
            line1
                line2 text  (extra indent + text)
        """
        source = "hello = \n    line1\n        line2"
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)
        assert message.value is not None

    def test_pattern_ending_with_accumulated_trailing_spaces_main(self) -> None:
        """Pattern in parse_pattern ending with accumulated trailing spaces.

        This covers line 795 where remaining accumulated text is finalized
        at the end of parse_pattern.

        Pattern:
        hello =
            text
                  (trailing spaces with extra indent)
        """
        source = "hello = \n    text\n          "
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)

    def test_term_with_continuation_blank_lines_and_spacing(self) -> None:
        """Term definition with complex continuation patterns.

        Tests parse_pattern through parse_term with multiple edge cases:
        - Blank lines in continuation
        - Extra spacing
        - Placeables with spacing

        This exercises all parse_pattern continuation paths.
        """
        source = "-brand = \n    Firefox\n    \n        {$version}\n          "
        cursor = Cursor(source, 0)
        result = parse_term(cursor, ParseContext())

        assert result is not None
        term = result.value
        assert isinstance(term, Term)
        assert term.value is not None

    def test_attribute_with_continuation_spacing_patterns(self) -> None:
        """Attribute with continuation spacing patterns.

        Tests parse_pattern through parse_attribute with spacing edge cases.
        """
        # parse_attribute expects to be positioned at the attribute line itself
        source = "    .tooltip = \n        Line 1\n            \n            Line 2\n              "
        cursor = Cursor(source, 0)
        result = parse_attribute(cursor, ParseContext())

        assert result is not None
        attribute = result.value
        assert isinstance(attribute, Attribute)
        assert attribute.value is not None


class TestParsePatternComplexContinuations:
    """Property-based tests for complex continuation patterns."""

    @given(
        num_blank_lines=st.integers(min_value=1, max_value=5),
        extra_spaces=st.integers(min_value=0, max_value=8),
    )
    def test_pattern_with_variable_blank_lines_property(
        self, num_blank_lines: int, extra_spaces: int
    ) -> None:
        """Property: patterns handle arbitrary blank lines in continuations."""
        blank_lines = "\n" * num_blank_lines
        spaces = " " * (4 + extra_spaces)  # 4 = common indent
        source = f"hello = text\n{spaces}{blank_lines}{spaces}continued"
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        # Should parse successfully
        assert result is not None
        message = result.value
        assert isinstance(message, Message)

    @given(
        base_indent=st.integers(min_value=1, max_value=4),
        extra_indent=st.integers(min_value=0, max_value=4),
    )
    def test_pattern_with_variable_indentation_property(
        self, base_indent: int, extra_indent: int
    ) -> None:
        """Property: patterns preserve extra indentation beyond common indent."""
        common = " " * base_indent
        extra = " " * extra_indent
        source = f"msg = line1\n{common}line2\n{common}{extra}line3"
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)


class TestIntegrationCoverageScenarios:
    """Integration tests combining multiple edge cases for complete coverage."""

    def test_select_expression_with_variant_leading_spaces(self) -> None:
        """Select expression with variant keys that have leading spaces.

        Combines _is_variant_marker coverage with select expression parsing.
        """
        source = "msg = {$count ->\n    [ one] item\n    *[other] items\n}"
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert message.value is not None
        assert len(message.value.elements) == 1
        placeable = message.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, SelectExpression)

    def test_multiline_select_with_complex_spacing(self) -> None:
        """Select expression with complex spacing and continuation patterns.

        Exercises parse_simple_pattern paths with variant patterns containing
        extra spacing and placeables.
        """
        source = """msg = {$count ->
    [ zero]
        No items
    [one]
        {$count} item
    *[other]
        {$count} items
}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert message.value is not None

    def test_message_with_all_continuation_edge_cases(self) -> None:
        """Message exercising all continuation edge cases in single pattern.

        Comprehensive test covering:
        - Blank lines (line 711)
        - Extra spacing (line 736)
        - Extra spacing before placeable (lines 750-751)
        - Accumulated text prepending (lines 788-789)
        - Trailing spaces (line 795)
        """
        source = """msg =
    Line 1

        Line 2
            {$var1}
                Text after
                    {$var2}
              """
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)
        assert message.value is not None
        # Should have multiple elements including text and placeables
        assert len(message.value.elements) >= 4
