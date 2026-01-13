"""Ultra-targeted tests for final 100% coverage of parser rules.

These tests target the last remaining uncovered lines with surgical precision.
"""

from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    _parse_inline_hyphen,
    parse_argument_expression,
    parse_pattern,
    parse_placeable,
    parse_simple_pattern,
    parse_term_reference,
)


class TestParseSimplePatternLinesFiveZeroFive:
    """Target lines 505-510: Continuation text before placeable."""

    def test_accumulated_text_before_placeable_prepend_to_existing(self) -> None:
        """Lines 505-507: Accumulated text merged with last non-placeable."""
        # We need: elements with text, accumulated continuation, then placeable
        # Start with text, newline, indented continuation, then placeable
        text = "First\n    continued{$var}"
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None

    def test_accumulated_text_before_placeable_new_element(self) -> None:
        """Lines 508-510: Accumulated text as new element before placeable."""
        # We need: either no elements OR last element is Placeable
        # Scenario: Start with newline + indented text, then placeable
        text = "\n    start{$var}"
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None


class TestParseSimplePatternLinesFiveFiveNine:
    """Target lines 559-563: Finalize accumulated text at end."""

    def test_finalize_accumulated_merged_with_existing(self) -> None:
        """Lines 559-561: Finalize accumulated text merged with last non-placeable."""
        # Pattern ending with continuation text, last element is not placeable
        text = "Text\n    more continuation"
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None

    def test_finalize_accumulated_new_element(self) -> None:
        """Lines 562-563: Finalize accumulated text as new element."""
        # Pattern ending with continuation, but last element is Placeable or no elements
        # Scenario: placeable, then indented text at end
        text = "{$var}\n    ending text"
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None


class TestParsePatternLineSixNineOne:
    """Target line 691: Continuation text as new element."""

    def test_accumulated_as_new_element_in_pattern(self) -> None:
        """Line 691: Accumulated continuation becomes new element."""
        # In parse_pattern, when we have accumulated text and are about to add new text
        # If no prior elements or last is Placeable, append as new element
        text = "{$x}\n    text after placeable"
        cursor = Cursor(text, 0)
        result = parse_pattern(cursor)
        assert result is not None


class TestParsePatternLinesSevenFourTwo:
    """Target lines 742-746: Finalize accumulated in parse_pattern."""

    def test_finalize_merged_in_pattern(self) -> None:
        """Lines 742-744: Finalize merged with existing element."""
        text = "Text\n    final continuation"
        cursor = Cursor(text, 0)
        result = parse_pattern(cursor)
        assert result is not None

    def test_finalize_new_element_in_pattern(self) -> None:
        """Lines 745-746: Finalize as new element."""
        text = "{$x}\n    final"
        cursor = Cursor(text, 0)
        result = parse_pattern(cursor)
        assert result is not None


class TestParseArgumentExpressionLineNineNineZero:
    """Target line 990: Term reference parse fails."""

    def test_term_ref_fails_in_argument(self) -> None:
        """Line 990: parse_term_reference returns None."""
        # Hyphen alone
        cursor = Cursor("-)", 0)
        result = parse_argument_expression(cursor)
        # Term parsing fails, then number parsing attempted
        assert result is None


class TestParseArgumentExpressionLineOneZeroZeroFive:
    """Target line 1005: Number parse fails after digit start."""

    def test_number_fails_defensive(self) -> None:
        """Line 1005: parse_number returns None (defensive)."""
        # This is very hard to reach - digits should parse as numbers
        # parse_number is quite robust
        # This line is likely defensive code for unexpected failures
        # Try edge case: just a digit
        cursor = Cursor("0)", 0)
        result = parse_argument_expression(cursor)
        # Should succeed as number
        assert result is not None


class TestParseArgumentExpressionLineOneTwoFour:
    """Target line 1024: Identifier parse fails."""

    def test_identifier_fails_in_argument(self) -> None:
        """Line 1024: parse_identifier returns None."""
        # Non-identifier start character
        cursor = Cursor("@)", 0)
        result = parse_argument_expression(cursor)
        assert result is None


class TestParseArgumentExpressionLineOneThreeFive:
    """Target line 1035: Function reference parse fails."""

    def test_function_ref_fails_in_argument(self) -> None:
        """Line 1035: parse_function_reference returns None."""
        # Identifier followed by '(' but function parsing fails
        cursor = Cursor("FUNC(@)", 0)
        result = parse_argument_expression(cursor)
        assert result is None


class TestParseTermReferenceClosingParen:
    """Target lines 1319-1320: Term arguments missing closing paren."""

    def test_term_args_no_closing_paren(self) -> None:
        """Lines 1319-1320: Expected ')' after term arguments."""
        # Term with arguments but missing closing paren
        cursor = Cursor("-brand(case: 'nom'", 0)
        result = parse_term_reference(cursor)
        assert result is None


class TestInlineHyphenLineOneFourSixFive:
    """Target line 1365: Inline hyphen number parse fails."""

    def test_inline_hyphen_number_fails(self) -> None:
        """Line 1365: parse_number returns None after hyphen."""
        # Hyphen alone - term fails, number fails
        cursor = Cursor("-", 0)
        result = _parse_inline_hyphen(cursor)
        assert result is None


class TestParsePlaceableLineOneFiveEightFive:
    """Target line 1585->1608: Select with valid selector."""

    def test_select_with_valid_selector(self) -> None:
        """Line 1585->1608: Selector is valid for select expression."""
        # Branch coverage: the branch where is_valid_selector is True
        cursor = Cursor("$x -> [one] 1 *[other] N}", 0)
        result = parse_placeable(cursor)
        assert result is not None
