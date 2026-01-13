"""Final 12 lines for 100% coverage of parser rules.

These tests target the last remaining uncovered lines, including defensive code
that requires mocking to reach.
"""

from unittest.mock import patch

from ftllexengine.syntax.cursor import Cursor, ParseResult
from ftllexengine.syntax.parser.rules import (
    _parse_inline_hyphen,
    parse_argument_expression,
    parse_attribute,
    parse_message,
    parse_pattern,
    parse_placeable,
    parse_term,
    parse_variant_key,
)


class TestParsePatternLine691:
    """Target line 691: Continuation as new element in parse_pattern."""

    def test_pattern_placeable_then_continuation_then_text(self) -> None:
        """Line 691: placeable, continuation with text."""
        # Pattern where after placeable, we have continuation with text
        # Need accumulated text_acc when about to append new text
        # Last element is Placeable, so line 691 executes
        text = "{$x}\n    more"
        cursor = Cursor(text, 0)
        result = parse_pattern(cursor)
        assert result is not None


class TestParseVariantKeyLinesSevenEightEightToSevenEightNine:
    """Lines 788-789: Unreachable fallback path."""

    def test_variant_key_defensive_path(self) -> None:
        """Lines 788-789: Number fails, identifier succeeds (defensive/unreachable)."""
        # This path is structurally unreachable:
        # - If cursor starts with '-', parse_number fails, parse_identifier also fails
        # - If cursor starts with digit, parse_number should succeed
        # This is defensive code for unexpected parse_number failures

        # Mock parse_number to fail and parse_identifier to succeed
        with (
            patch("ftllexengine.syntax.parser.rules.parse_number") as mock_num,
            patch("ftllexengine.syntax.parser.rules.parse_identifier") as mock_id,
        ):
            mock_num.return_value = None  # parse_number fails
            mock_id.return_value = ParseResult("test", Cursor("test", 4))  # identifier succeeds

            cursor = Cursor("-test", 0)
            result = parse_variant_key(cursor)
            # Should hit lines 788-789
            assert result is not None


class TestParseArgumentExpressionLine990:
    """Line 990: Term reference parse fails."""

    def test_argument_term_ref_fails(self) -> None:
        """Line 990: parse_term_reference returns None."""
        # Hyphen with nothing after or invalid
        cursor = Cursor("-)", 0)
        result = parse_argument_expression(cursor)
        assert result is None


class TestParseArgumentExpressionLine1005:
    """Line 1005: Number parse fails on digit start (defensive)."""

    def test_argument_number_fails_defensive(self) -> None:
        """Line 1005: parse_number returns None on digit start (defensive)."""
        # Mock parse_number to fail even though cursor starts with digit
        with patch("ftllexengine.syntax.parser.rules.parse_number") as mock_num:
            mock_num.return_value = None
            cursor = Cursor("9)", 0)
            result = parse_argument_expression(cursor)
            # Should hit line 1005 and return None
            assert result is None


class TestParseArgumentExpressionLine1024:
    """Line 1024: Identifier parse fails."""

    def test_argument_identifier_fails(self) -> None:
        """Line 1024: parse_identifier returns None."""
        cursor = Cursor("@)", 0)
        result = parse_argument_expression(cursor)
        assert result is None


class TestParseArgumentExpressionLine1035:
    """Line 1035: Function reference parse fails."""

    def test_argument_function_ref_fails(self) -> None:
        """Line 1035: parse_function_reference returns None."""
        # Identifier followed by '(' but function parsing fails
        cursor = Cursor("FUNC(@)", 0)
        result = parse_argument_expression(cursor)
        assert result is None


class TestInlineHyphenLine1365:
    """Line 1365: Inline hyphen number parse fails."""

    def test_inline_hyphen_all_fail(self) -> None:
        """Line 1365: Both term and number parsing fail."""
        cursor = Cursor("-", 0)
        result = _parse_inline_hyphen(cursor)
        assert result is None


class TestParsePlaceableLine1585:
    """Line 1585->1608: Selector branch coverage."""

    def test_placeable_valid_selector_with_arrow(self) -> None:
        """Line 1585->1608: Valid selector with select expression."""
        # Ensure we test the branch where is_valid_selector returns True
        cursor = Cursor("$count -> [one] item *[other] items}", 0)
        result = parse_placeable(cursor)
        assert result is not None


class TestDefensiveNoneChecksWithMocking:
    """Lines 1744, 1818, 1891, 1903: Defensive None checks using mocks."""

    def test_parse_message_attributes_returns_none_line_1744(self) -> None:
        """Line 1744: parse_message_attributes returns None (defensive)."""
        # Mock parse_message_attributes to return None
        with patch("ftllexengine.syntax.parser.rules.parse_message_attributes") as mock_attrs:
            mock_attrs.return_value = None
            cursor = Cursor("hello = value", 0)
            result = parse_message(cursor)
            # Should handle None and fail gracefully
            assert result is None

    def test_parse_attribute_pattern_returns_none_line_1818(self) -> None:
        """Line 1818: parse_pattern returns None in parse_attribute (defensive)."""
        # Mock parse_pattern to return None
        with patch("ftllexengine.syntax.parser.rules.parse_pattern") as mock_pattern:
            mock_pattern.return_value = None
            cursor = Cursor(".attr = value", 0)
            result = parse_attribute(cursor)
            # Should handle None
            assert result is None

    def test_parse_term_pattern_returns_none_line_1891(self) -> None:
        """Line 1891: parse_pattern returns None in parse_term (defensive)."""
        # Mock parse_pattern to return None
        with patch("ftllexengine.syntax.parser.rules.parse_pattern") as mock_pattern:
            mock_pattern.return_value = None
            cursor = Cursor("-brand = value", 0)
            result = parse_term(cursor)
            # Should handle None
            assert result is None

    def test_parse_term_attributes_returns_none_line_1903(self) -> None:
        """Line 1903: parse_message_attributes returns None in parse_term (defensive)."""
        # Mock parse_message_attributes to return None
        with patch("ftllexengine.syntax.parser.rules.parse_message_attributes") as mock_attrs:
            mock_attrs.return_value = None
            cursor = Cursor("-brand = value", 0)
            result = parse_term(cursor)
            # Should handle None
            assert result is None


class TestAllRemainingLines:
    """Comprehensive test for all remaining uncovered lines."""

    def test_coverage_complete(self) -> None:
        """Ensure all edge cases are covered."""
        # Line 691: parse_pattern continuation
        result1 = parse_pattern(Cursor("{$x}\n    text", 0))
        assert result1 is not None

        # Lines 788-789: Tested with mocking above

        # Line 990: Term ref fails
        result2 = parse_argument_expression(Cursor("-)", 0))
        assert result2 is None

        # Line 1005: Tested with mocking above

        # Line 1024: Identifier fails
        result3 = parse_argument_expression(Cursor("@)", 0))
        assert result3 is None

        # Line 1035: Function ref fails
        result4 = parse_argument_expression(Cursor("FUNC(@)", 0))
        assert result4 is None

        # Line 1365: Inline hyphen fails
        result5 = _parse_inline_hyphen(Cursor("-", 0))
        assert result5 is None

        # Line 1585: Valid selector
        result6 = parse_placeable(Cursor("$x -> [a] A *[b] B}", 0))
        assert result6 is not None

        # Lines 1744, 1818, 1891, 1903: Tested with mocking above
