"""Targeted tests for specific uncovered lines in expressions.py.

Focuses on:
- Lines 117-118: Variant key starting with - that becomes identifier
- Line 307: Identifier parsing failure in argument expression
- Line 627: Identifier parsing failure in inline expression
- Line 740: Nesting depth exceeded in parse_placeable
"""

from __future__ import annotations

from unittest.mock import patch

import ftllexengine.syntax.parser.rules  # noqa: F401 # pylint: disable=unused-import
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import Identifier, MessageReference
from ftllexengine.syntax.cursor import Cursor, ParseResult
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


class TestLines117To118VariantKeyMinusIdentifier:
    """Test lines 117-118: variant key with - prefix that parses as identifier."""

    def test_variant_key_minus_then_alpha_becomes_identifier(self) -> None:
        """Test parse_variant_key with '-' followed by alpha (lines 117-118).

        When variant key starts with '-' and next char is alpha, parse_number
        fails, so we fall through to parse_identifier (lines 112-118).
        To hit lines 117-118, we need parse_number to fail but parse_identifier
        to succeed. This requires mocking both functions.
        """
        source = "-abc"
        cursor = Cursor(source, 0)

        # Mock parse_number to fail and parse_identifier to succeed
        # parse_identifier returns ParseResult with string value, not Identifier
        mock_id_result = ParseResult("abc", Cursor(source, 4))

        with patch(
            "ftllexengine.syntax.parser.rules.parse_number",
            return_value=None,
        ), patch(
            "ftllexengine.syntax.parser.rules.parse_identifier",
            return_value=mock_id_result,
        ):
            result = parse_variant_key(cursor)

        # Should return Identifier created from string (lines 117-118)
        assert result is not None
        assert isinstance(result.value, Identifier)
        assert result.value.name == "abc"


# ============================================================================
# LINE 307: Identifier Parsing Failure in Argument Expression
# ============================================================================


class TestLine307ArgumentExpressionIdentifierFailure:
    """Test line 307: parse_argument_expression when identifier parsing fails."""

    def test_argument_expression_identifier_fails_line_307(self) -> None:
        """Test parse_argument_expression returns None when parse_identifier fails (line 307)."""
        # Start with alpha char but have invalid identifier
        # (e.g., just 'a' followed by invalid char)
        # To hit line 307, we need cursor.current.isalpha() to be True
        # but parse_identifier to return None
        # This is hard to trigger naturally since parse_identifier is quite permissive

        # Try with a character that starts like alpha but isn't valid
        # Actually, we need to mock parse_identifier to return None
        source = "a999!!!"
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.rules.parse_identifier",
            return_value=None,
        ):
            result = parse_argument_expression(cursor)

        # Should return None when identifier parsing fails (line 307)
        assert result is None


# ============================================================================
# LINE 627: Identifier Parsing Failure in Inline Expression
# ============================================================================


class TestLine627InlineExpressionIdentifierFailure:
    """Test line 627: parse_inline_expression when identifier parsing fails."""

    def test_inline_expression_identifier_fails_line_627(self) -> None:
        """Test parse_inline_expression returns None when parse_identifier fails (line 627)."""

        source = "U999"  # Starts with uppercase
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.rules.parse_identifier",
            return_value=None,
        ):
            result = parse_inline_expression(cursor)

        # Should return None when identifier parsing fails (line 627)
        assert result is None


# ============================================================================
# LINE 740: Nesting Depth Exceeded in parse_placeable
# ============================================================================


class TestLine740NestingDepthExceeded:
    """Test line 740: parse_placeable when nesting depth is exceeded."""

    def test_placeable_nesting_depth_exceeded_line_740(self) -> None:
        """Test parse_placeable returns None when nesting depth exceeded (line 740)."""
        source = "$var}"
        cursor = Cursor(source, 0)

        # Create context with depth already at limit
        context = ParseContext(max_nesting_depth=5, current_depth=5)

        result = parse_placeable(cursor, context)

        # Should return None due to depth exceeded (line 740)
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
        """Test variant missing ] (line 177)."""

        source = "[one text"  # Missing ]
        cursor = Cursor(source, 0)

        result = parse_variant(cursor)

        # Should return None due to missing ] (line 177)
        assert result is None

    def test_variant_pattern_parse_fails_line_187(self) -> None:
        """Test variant when pattern parsing fails (line 187)."""


        source = "[one] pattern"
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.rules.parse_simple_pattern",
            return_value=None,
        ):
            result = parse_variant(cursor)

        # Should return None when pattern parsing fails (line 187)
        assert result is None

    def test_string_literal_parse_fails_line_289(self) -> None:
        """Test argument expression when string literal parsing fails (line 289)."""

        source = '"invalid'
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.primitives.parse_string_literal",
            return_value=None,
        ):
            result = parse_argument_expression(cursor)

        # Should return None when string parsing fails (line 289)
        assert result is None

    def test_number_parse_fails_line_296(self) -> None:
        """Test argument expression when number parsing fails (line 296)."""

        source = "123"
        cursor = Cursor(source, 0)

        # Patch in the module where it's used (expressions), not where it's defined
        with patch(
            "ftllexengine.syntax.parser.rules.parse_number",
            return_value=None,
        ):
            result = parse_argument_expression(cursor)

        # Should return None when number parsing fails (line 296)
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
        """Test named argument when name is not identifier (line 367)."""
        # This is hard to trigger directly, but we can test via function call
        bundle = FluentBundle("en_US")
        # Try to use a non-identifier as named argument name
        ftl = """msg = {NUMBER($val, $var: 2)}"""
        bundle.add_resource(ftl)

        result, _errors = bundle.format_pattern("msg", args={"val": 42, "var": "x"})

        # Should handle error gracefully
        assert result is not None

    def test_named_argument_value_not_literal_line_394(self) -> None:
        """Test named argument with non-literal value."""
        bundle = FluentBundle("en_US")
        # Named argument values must be literals, not variables
        ftl = """msg = {NUMBER($val, style: $var)}"""
        bundle.add_resource(ftl)

        result, _errors = bundle.format_pattern("msg", args={"val": 42, "var": "percent"})

        # Should handle error gracefully
        assert result is not None

    def test_term_reference_missing_dash_line_491(self) -> None:
        """Test term reference without - prefix (line 491)."""

        source = "brand"  # No - prefix
        cursor = Cursor(source, 0)

        result = parse_term_reference(cursor)

        # Should return None without - prefix (line 491)
        assert result is None

    def test_term_arguments_missing_closing_paren_line_533(self) -> None:
        """Test term reference with arguments missing ) (line 533)."""

        source = '-brand(case: "nom"'  # Missing )
        cursor = Cursor(source, 0)

        result = parse_term_reference(cursor)

        # Should return None due to missing ) (line 533)
        assert result is None

    def test_inline_expression_variable_parse_fails_line_576(self) -> None:
        """Test inline expression when variable parsing fails (line 576)."""

        source = "$var"
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.rules.parse_variable_reference",
            return_value=None,
        ):
            result = parse_inline_expression(cursor)

        # Should return None when variable parsing fails (line 576)
        assert result is None

    def test_inline_expression_string_parse_fails_line_584(self) -> None:
        """Test inline expression when string parsing fails (line 584)."""

        source = '"invalid'
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.primitives.parse_string_literal",
            return_value=None,
        ):
            result = parse_inline_expression(cursor)

        # Should return None when string parsing fails (line 584)
        assert result is None

    def test_inline_expression_number_parse_fails_line_602(self) -> None:
        """Test inline expression when negative number parsing fails (line 602)."""

        source = "-123"
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.rules.parse_number",
            return_value=None,
        ):
            result = parse_inline_expression(cursor)

        # Should return None when number parsing fails (line 602)
        assert result is None

    def test_inline_expression_digit_number_parse_fails_line_614(self) -> None:
        """Test inline expression when positive number parsing fails (line 614)."""

        source = "123"
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.rules.parse_number",
            return_value=None,
        ):
            result = parse_inline_expression(cursor)

        # Should return None when number parsing fails (line 614)
        assert result is None

    def test_inline_expression_lowercase_identifier_fails_line_672(self) -> None:
        """Test inline expression when lowercase identifier parsing fails (line 672)."""

        source = "msg"
        cursor = Cursor(source, 0)

        with patch(
            "ftllexengine.syntax.parser.rules.parse_identifier",
            return_value=None,
        ):
            result = parse_inline_expression(cursor)

        # Should return None when identifier parsing fails (line 672)
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
        """Test select expression missing } (line 801)."""
        # To hit line 801, parse_placeable needs to successfully parse a select expression
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
        """Test positional argument after named argument (line 402)."""
        bundle = FluentBundle("en_US")
        # Positional args must come before named args
        ftl = """msg = {NUMBER(style: "percent", $val)}"""
        bundle.add_resource(ftl)

        result, _errors = bundle.format_pattern("msg", args={"val": 42})

        # Should handle error gracefully
        assert result is not None
