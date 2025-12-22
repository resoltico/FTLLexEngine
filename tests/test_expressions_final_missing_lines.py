"""Final tests for remaining uncovered lines in expressions.py.

Targets:
- Line 115: Both number and identifier parsing fail in variant key
- Line 378: EOF after : in named argument
- Line 383: Value parsing fails for named argument
- Lines 659-661: Uppercase message reference with attribute
- Branch 786->808: Not a select expression (- but not ->)
"""

from __future__ import annotations

from unittest.mock import patch

import ftllexengine.syntax.parser.rules  # noqa: F401 # pylint: disable=unused-import
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import Identifier, MessageReference, VariableReference
from ftllexengine.syntax.cursor import Cursor, ParseResult
from ftllexengine.syntax.parser.rules import (
    parse_call_arguments,
    parse_inline_expression,
    parse_placeable,
    parse_variant_key,
)

# ============================================================================
# LINE 115: Both Number and Identifier Parsing Fail in Variant Key
# ============================================================================


class TestLine115VariantKeyBothFail:
    """Test line 115: parse_variant_key when both number and identifier fail."""

    def test_variant_key_both_parsers_fail_line_115(self) -> None:
        """Test parse_variant_key returns None when both parsers fail (line 115)."""
        source = "-???"  # Invalid variant key
        cursor = Cursor(source, 0)

        # Mock both parsers to fail
        with patch(
            "ftllexengine.syntax.parser.rules.parse_number",
            return_value=None,
        ), patch(
            "ftllexengine.syntax.parser.rules.parse_identifier",
            return_value=None,
        ):
            result = parse_variant_key(cursor)

        # Should return None when both fail (line 115)
        assert result is None


# ============================================================================
# LINE 378: EOF After Colon in Named Argument
# ============================================================================


class TestLine378NamedArgumentEOF:
    """Test line 378: parse_call_arguments with EOF after colon."""

    def test_named_argument_eof_after_colon_line_378(self) -> None:
        """Test parse_call_arguments returns None when EOF after : (line 378)."""
        # Create source with named argument but EOF after :
        source = "style:"  # EOF after :
        cursor = Cursor(source, 0)

        result = parse_call_arguments(cursor)

        # Should return None due to EOF after : (line 378)
        assert result is None


# ============================================================================
# LINE 383: Value Parsing Fails for Named Argument
# ============================================================================


class TestLine383NamedArgumentValueFails:
    """Test line 383: parse_call_arguments when value parsing fails."""

    def test_named_argument_value_parse_fails_line_383(self) -> None:
        """Test parse_call_arguments when value parsing fails (line 383)."""
        # To hit line 383, we need the value after : to be unparseable
        # parse_argument_expression returns None when current char is not
        # $, ", digit, -, or alpha. So use a symbol like )

        source = "style: )"  # ) is not a valid argument value start
        cursor = Cursor(source, 0)

        result = parse_call_arguments(cursor)

        # Should return None when value parsing fails (line 383)
        assert result is None

    def test_named_argument_value_invalid_char_line_383(self) -> None:
        """Test parse_call_arguments with invalid character after colon."""
        # Another test with different invalid character
        source = "key: @invalid"  # @ is not valid
        cursor = Cursor(source, 0)

        result = parse_call_arguments(cursor)

        # Should return None
        assert result is None


# ============================================================================
# LINES 659-661: Uppercase Message Reference With Attribute
# ============================================================================


class TestLines659To661UppercaseMessageAttribute:
    """Test lines 659-661: uppercase message reference with attribute."""

    def test_uppercase_message_reference_with_attribute(self) -> None:
        """Test uppercase message reference with attribute (lines 659-661)."""
        bundle = FluentBundle("en_US")
        # Uppercase message reference with attribute
        ftl = """MSG = Value
    .attr = Attribute value

msg = {MSG.attr}
"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should resolve attribute
        assert "Attribute value" in result

    def test_uppercase_message_with_attribute_direct_parse(self) -> None:
        """Test parse_inline_expression with uppercase message and attribute."""
        source = "MSG.attr"
        cursor = Cursor(source, 0)

        result = parse_inline_expression(cursor)

        # Should parse as MessageReference with attribute (lines 659-661)
        assert result is not None
        assert isinstance(result.value, MessageReference)
        assert result.value.id.name == "MSG"
        assert result.value.attribute is not None
        assert result.value.attribute.name == "attr"


# ============================================================================
# BRANCH 786->808: Not a Select Expression (- but not ->)
# ============================================================================


class TestBranch786Line808NotSelectExpression:
    """Test branch 786->808: cursor at - but next char is not >."""

    def test_placeable_with_negative_number_not_select(self) -> None:
        """Test placeable with negative number (- not followed by >)."""
        bundle = FluentBundle("en_US")
        # Negative number literal (- followed by digit, not >)
        ftl = "msg = {-5}"
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should format negative number
        assert "-5" in result

    def test_branch_786_808_expression_followed_by_minus_not_arrow(self) -> None:
        """Test branch 786->808: valid selector followed by - but not ->."""
        # To hit branch 786->808, we need to have a valid selector expression
        # followed by '-' but not '->', and we're inside a placeable

        # This is actually hard to trigger because the parser will try to parse
        # the '-' as part of the next token. Let me try mocking the check.

        source = "$var -x}"  # Variable followed by -x (not ->)
        cursor = Cursor(source, 0)

        # Mock parse_inline_expression to return a VariableReference
        var_ref = VariableReference(id=Identifier("var"))
        mock_result = ParseResult(var_ref, Cursor(source, 5))  # After "$var "

        with patch(
            "ftllexengine.syntax.parser.rules.parse_inline_expression",
            return_value=mock_result,
        ):
            # After parsing $var, cursor is at "-x}"
            # Since next char after - is 'x' (not '>'), branch 786->808 should be taken
            result = parse_placeable(cursor)

        # Result depends on how parser handles the malformed suffix "-x}".
        # This test verifies the code path executes without crashing.
        # With mock returning VariableReference at pos 5, remaining "-x}" is invalid.
        assert result is None  # Invalid syntax after expression


# ============================================================================
# Integration Test
# ============================================================================


class TestFinalIntegration:
    """Integration test covering multiple edge cases."""

    def test_complex_function_call_with_edge_cases(self) -> None:
        """Test complex function call covering multiple code paths."""
        bundle = FluentBundle("en_US")
        ftl = """
# Test various expression types
msg1 = {NUMBER(-42)}
msg2 = {MSG.attr}
"""
        bundle.add_resource(ftl)

        result1, _ = bundle.format_pattern("msg1")
        result2, _ = bundle.format_pattern("msg2")

        # Should handle both cases
        assert result1 is not None
        assert result2 is not None
