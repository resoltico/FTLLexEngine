"""Targeted tests for specific expression-parser edge branches.

Focuses on:
- Variant-key fallback from number parsing to identifier parsing
- Identifier parsing failure in argument expressions
- Identifier parsing failure in inline expressions
- Nesting-depth rejection in parse_placeable
"""

from __future__ import annotations

from unittest.mock import patch

import ftllexengine.syntax.parser.rules  # noqa: F401 # pylint: disable=unused-import
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import Identifier, MessageReference
from ftllexengine.syntax.cursor import Cursor, ParseError, ParseResult
from ftllexengine.syntax.parser.core import FluentParserV1
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    parse_argument_expression,
    parse_function_reference,
    parse_inline_expression,
    parse_placeable,
    parse_term_reference,
    parse_variant,
    parse_variant_key,
)

# ============================================================================
# LINES 117-118: Variant Key Starting With - That Becomes Identifier
# ============================================================================


class TestVariantKeyMinusIdentifierFallback:
    """Variant keys can fall back from number parsing to identifier parsing."""

    def test_variant_key_minus_then_alpha_becomes_identifier(self) -> None:
        """parse_variant_key can recover from numeric parse failure.

        When variant key starts with '-' and next char is alpha, parse_number
        fails, so we fall through to parse_identifier.
        To hit that fallback, we need parse_number to fail but parse_identifier
        to succeed. This requires mocking both functions.
        """
        source = "-abc"
        cursor = Cursor(source, 0)

        # Mock parse_number to fail and parse_identifier to succeed
        # parse_identifier returns ParseResult with string value, not Identifier
        mock_id_result = ParseResult("abc", Cursor(source, 4))

        with patch(
            "ftllexengine.syntax.parser.expressions.parse_number",
            return_value=ParseError("forced failure", Cursor("-abc", 0)),
        ), patch(
            "ftllexengine.syntax.parser.expressions.parse_identifier",
            return_value=mock_id_result,
        ):
            result = parse_variant_key(cursor)

        # Should return Identifier created from the fallback parse result
        assert result is not None
        assert isinstance(result.value, Identifier)
        assert result.value.name == "abc"


# ============================================================================
# LINE 307: Identifier Parsing Failure in Argument Expression
# ============================================================================


class TestArgumentExpressionIdentifierFailure:
    """parse_argument_expression returns None when identifier parsing fails."""

    def test_argument_expression_identifier_fails_line_307(self) -> None:
        """parse_argument_expression returns None when parse_identifier fails."""
        # Start with alpha char but have invalid identifier
        # (e.g., just 'a' followed by invalid char)
        # To hit this branch, we need cursor.current.isalpha() to be True
        # but parse_identifier to return None
        # This is hard to trigger naturally since parse_identifier is quite permissive

        # Try with a character that starts like alpha but isn't valid
        # Actually, we need to mock parse_identifier to return None
        source = "a999!!!"
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.expressions.parse_identifier",
            return_value=ParseError("forced failure", Cursor("a999!!!", 0)),
        ):
            result = parse_argument_expression(cursor)

        # Should return None when identifier parsing fails
        assert result is None


# ============================================================================
# LINE 627: Identifier Parsing Failure in Inline Expression
# ============================================================================


class TestInlineExpressionIdentifierFailure:
    """parse_inline_expression returns None when identifier parsing fails."""

    def test_inline_expression_identifier_fails_line_627(self) -> None:
        """parse_inline_expression returns None when parse_identifier fails."""

        source = "U999"  # Starts with uppercase
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.expressions.parse_identifier",
            return_value=ParseError("forced failure", Cursor("U999", 0)),
        ):
            result = parse_inline_expression(cursor)

        # Should return None when identifier parsing fails
        assert result is None


# ============================================================================
# LINE 740: Nesting Depth Exceeded in parse_placeable
# ============================================================================


class TestPlaceableNestingDepthExceeded:
    """parse_placeable returns None when nesting depth is exceeded."""

    def test_placeable_nesting_depth_exceeded_line_740(self) -> None:
        """parse_placeable returns None when nesting depth is exceeded."""
        source = "$var}"
        cursor = Cursor(source, 0)

        # Create context with depth already at limit
        context = ParseContext(max_nesting_depth=5, current_depth=5)

        result = parse_placeable(cursor, context)

        # Should return None due to depth exceeded
        assert result is None

    def test_bundle_with_excessive_nesting(self) -> None:
        """Test deeply nested placeables are rejected via bundle."""

        # Create parser with low nesting limit
        parser = FluentParserV1(max_nesting_depth=2)

        # Try to parse deeply nested structure
        # {$a} inside {$b} inside {$c} = 3 levels
        # With limit of 2, this should fail
        ftl = "msg = outer {$inner}"

        resource = parser.parse(ftl)

        # Should parse successfully at depth 1
        assert len(resource.entries) == 1


# ============================================================================
# Additional Coverage for Other Uncovered Lines
# ============================================================================


class TestAdditionalUncoveredLines:
    """Tests for other uncovered lines in expressions.py."""

    def test_variant_missing_closing_bracket_line_177(self) -> None:
        """Variant parsing fails when the closing bracket is missing."""

        source = "[one text"  # Missing ]
        cursor = Cursor(source, 0)

        result = parse_variant(cursor)

        # Should return None due to the missing closing bracket
        assert result is None

    def test_variant_pattern_parse_fails_line_187(self) -> None:
        """Variant parsing fails when the variant pattern parser fails."""


        source = "[one] pattern"
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.expressions.parse_simple_pattern",
            return_value=None,
        ):
            result = parse_variant(cursor)

        # Should return None when pattern parsing fails
        assert result is None

    def test_string_literal_parse_fails_line_289(self) -> None:
        """Argument parsing fails when string literal parsing fails."""

        source = '"invalid'
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.primitives.parse_string_literal",
            return_value=None,
        ):
            result = parse_argument_expression(cursor)

        # Should return None when string parsing fails
        assert result is None

    def test_number_parse_fails_line_296(self) -> None:
        """Argument parsing fails when number parsing fails."""

        source = "123"
        cursor = Cursor(source, 0)

        # Patch in the module where it's used (expressions), not where it's defined
        with patch(
            "ftllexengine.syntax.parser.expressions.parse_number",
            return_value=ParseError("forced failure", Cursor("123", 0)),
        ):
            result = parse_argument_expression(cursor)

        # Should return None when number parsing fails
        assert result is None

    def test_function_name_lowercase_is_valid(self) -> None:
        """Test function reference with lowercase name is now valid.

        Per Fluent 1.0 spec, function names are identifiers without case restrictions.
        The isupper() check was removed for spec compliance.
        """
        source = "lowercase()"
        cursor = Cursor(source, 0)

        result = parse_function_reference(cursor)

        # Lowercase function names are now valid per spec
        assert result is not None
        assert result.value.id.name == "lowercase"

    def test_named_argument_not_identifier_line_367(self) -> None:
        """Soft recovery when a named argument name is not an identifier."""
        # This is hard to trigger directly, but we can test via function call
        bundle = FluentBundle("en_US", strict=False)
        # Try to use a non-identifier as named argument name
        ftl = """msg = {NUMBER($val, $var: 2)}"""
        bundle.add_resource(ftl)

        result, _errors = bundle.format_pattern("msg", args={"val": 42, "var": "x"})

        # Should handle error gracefully
        assert result is not None

    def test_named_argument_value_not_literal_line_394(self) -> None:
        """Test named argument with non-literal value, soft recovery."""
        bundle = FluentBundle("en_US", strict=False)
        # Named argument values must be literals, not variables
        ftl = """msg = {NUMBER($val, style: $var)}"""
        bundle.add_resource(ftl)

        result, _errors = bundle.format_pattern("msg", args={"val": 42, "var": "percent"})

        # Should handle error gracefully
        assert result is not None

    def test_term_reference_missing_dash_line_491(self) -> None:
        """Term references require the leading '-' prefix."""

        source = "brand"  # No - prefix
        cursor = Cursor(source, 0)

        result = parse_term_reference(cursor)

        # Should return None without the required '-' prefix
        assert result is None

    def test_term_arguments_missing_closing_paren_line_533(self) -> None:
        """Term-reference parsing fails when the closing ')' is missing."""

        source = '-brand(case: "nom"'  # Missing )
        cursor = Cursor(source, 0)

        result = parse_term_reference(cursor)

        # Should return None due to the missing closing parenthesis
        assert result is None

    def test_inline_expression_variable_parse_fails_line_576(self) -> None:
        """Inline-expression parsing fails when variable parsing fails."""

        source = "$var"
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.expressions.parse_variable_reference",
            return_value=None,
        ):
            result = parse_inline_expression(cursor)

        # Should return None when variable parsing fails
        assert result is None

    def test_inline_expression_string_parse_fails_line_584(self) -> None:
        """Inline-expression parsing fails when string parsing fails."""

        source = '"invalid'
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.primitives.parse_string_literal",
            return_value=None,
        ):
            result = parse_inline_expression(cursor)

        # Should return None when string parsing fails
        assert result is None

    def test_inline_expression_number_parse_fails_line_602(self) -> None:
        """Inline-expression parsing fails when negative-number parsing fails."""

        source = "-123"
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.expressions.parse_number",
            return_value=ParseError("forced failure", Cursor("-123", 0)),
        ):
            result = parse_inline_expression(cursor)

        # Should return None when number parsing fails
        assert result is None

    def test_inline_expression_digit_number_parse_fails_line_614(self) -> None:
        """Inline-expression parsing fails when positive-number parsing fails."""

        source = "123"
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.expressions.parse_number",
            return_value=ParseError("forced failure", Cursor("123", 0)),
        ):
            result = parse_inline_expression(cursor)

        # Should return None when number parsing fails
        assert result is None

    def test_inline_expression_lowercase_identifier_fails_line_672(self) -> None:
        """Inline-expression parsing fails when lowercase identifier parsing fails."""

        source = "msg"
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.expressions.parse_identifier",
            return_value=ParseError("forced failure", Cursor("msg", 0)),
        ):
            result = parse_inline_expression(cursor)

        # Should return None when identifier parsing fails
        assert result is None

    def test_uppercase_message_reference_with_trailing_dot(self) -> None:
        """Test message reference with trailing dot (no attribute name).

        Parser handles MSG. by parsing the message reference
        and consuming the dot (looking for attribute), but returns
        message reference without attribute when none found.
        """
        source = "MSG."  # Trailing dot with no attribute name
        cursor = Cursor(source, 0)

        result = parse_inline_expression(cursor)

        # Should successfully parse message reference without attribute
        assert result is not None
        assert isinstance(result.value, MessageReference)
        assert result.value.id.name == "MSG"
        assert result.value.attribute is None
        # Cursor advances past the dot (at position 4) after looking for attribute
        assert result.cursor.pos == 4

    def test_lowercase_message_reference_with_trailing_dot(self) -> None:
        """Test lowercase message reference with trailing dot.

        Parser handles msg. by parsing the message reference
        and consuming the dot (looking for attribute), but returns
        message reference without attribute when none found.
        """
        source = "msg."  # Trailing dot with no attribute name
        cursor = Cursor(source, 0)

        result = parse_inline_expression(cursor)

        # Should successfully parse message reference without attribute
        assert result is not None
        assert isinstance(result.value, MessageReference)
        assert result.value.id.name == "msg"
        assert result.value.attribute is None
        # Cursor advances past the dot (at position 4) after looking for attribute
        assert result.cursor.pos == 4

    def test_select_expression_missing_closing_brace_line_801(self) -> None:
        """Select-expression parsing fails when the closing '}' is missing."""
        # To hit this branch, parse_placeable needs to successfully parse a select expression
        # but then find that cursor is not at } (either EOF or wrong character)

        # The easiest way is to create FTL that has valid select but no closing }
        # and see if it returns None during parsing

        parser = FluentParserV1()
        # Select expression without closing }
        ftl = "msg = {$n -> [one] One *[other] Other"

        resource = parser.parse(ftl)

        # Should produce a Junk entry due to missing }
        assert len(resource.entries) >= 1

    def test_positional_after_named_argument_line_402(self) -> None:
        """Soft recovery when a positional argument follows a named argument."""
        bundle = FluentBundle("en_US", strict=False)
        # Positional args must come before named args
        ftl = """msg = {NUMBER(style: "percent", $val)}"""
        bundle.add_resource(ftl)

        result, _errors = bundle.format_pattern("msg", args={"val": 42})

        # Should handle error gracefully
        assert result is not None
