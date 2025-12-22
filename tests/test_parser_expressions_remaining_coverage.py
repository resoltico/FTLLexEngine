"""Additional coverage tests for expressions.py to reach 100%.

Targets remaining uncovered lines through direct API calls and edge cases.
"""

from __future__ import annotations

from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    parse_function_reference,
    parse_placeable,
    parse_term_reference,
    parse_variant,
)

# ============================================================================
# LINES 112-118: Variant Key Starting With Minus
# ============================================================================


class TestVariantKeyMinusPrefix:
    """Test variant key starting with - that becomes identifier."""

    def test_variant_key_as_identifier(self) -> None:
        """Test variant key parsed as identifier (lines 117-118)."""
        source = "[test]"
        cursor = Cursor(source, 1)  # After '['

        from ftllexengine.syntax.parser.rules import parse_variant_key

        result = parse_variant_key(cursor)

        # Should parse as identifier
        assert result is not None


# ============================================================================
# LINE 160: Variant Missing Opening Bracket
# ============================================================================


class TestLine160VariantMissingBracket:
    """Test line 160: variant without '[' returns None."""

    def test_variant_missing_opening_bracket(self) -> None:
        """Test parse_variant returns None when '[' is missing (line 160)."""
        source = "one] Text"  # Missing [
        cursor = Cursor(source, 0)

        result = parse_variant(cursor)

        # Should return None
        assert result is None


# ============================================================================
# Variant and Select Expression Tests Through Integration
# ============================================================================


class TestVariantAndSelectThroughIntegration:
    """Test variant and select expression paths through integration."""

    def test_variant_in_select_expression(self) -> None:
        """Test variant parsing within select expression (via Bundle)."""
        from ftllexengine.runtime.bundle import FluentBundle

        bundle = FluentBundle("en_US")
        # This will exercise variant parsing
        ftl = """msg = {NUMBER(1) ->
    [one] One
    *[other] Other
}"""
        bundle.add_resource(ftl)
        result, _ = bundle.format_pattern("msg")
        # Just verify it parses
        assert result is not None


# ============================================================================
# LINES 367, 378, 383: Term Reference Parsing
# ============================================================================


class TestTermReferenceParsing:
    """Test term reference parsing errors."""

    def test_term_reference_no_identifier_line_367(self) -> None:
        """Test term reference without identifier (line 367)."""
        source = "-  "  # - followed by spaces
        cursor = Cursor(source, 0)

        result = parse_term_reference(cursor)

        # Should return None
        assert result is None

    def test_term_reference_no_closing_brace_parses(self) -> None:
        """Term reference parses without closing brace (braces are for placeables)."""
        source = "-term"  # Term reference without placeable wrapper
        cursor = Cursor(source, 0)

        result = parse_term_reference(cursor)

        # Term reference parser doesn't require closing brace - that's placeable's job
        assert result is not None
        assert result.value.id.name == "term"

    def test_term_attribute_parse_fails_line_383(self) -> None:
        """Test term reference when attribute parsing fails (line 383)."""
        source = "-term."  # Dot without attribute name
        cursor = Cursor(source, 0)

        result = parse_term_reference(cursor)

        # Invalid: dot present but no attribute identifier follows
        assert result is None


# ============================================================================
# LINES 436, 443, 450: Message/Term Reference Through Inline Expression
# ============================================================================


class TestReferenceParsingThroughPlaceable:
    """Test reference parsing through placeable/inline expression."""

    def test_placeable_with_term_reference(self) -> None:
        """Test parsing term reference through placeable."""
        source = "-brand"
        cursor = Cursor(source, 0)

        result = parse_term_reference(cursor)

        # Should parse term reference
        assert result is not None

    def test_term_reference_with_attribute(self) -> None:
        """Test term reference with attribute."""
        source = "-brand.attr"
        cursor = Cursor(source, 0)

        result = parse_term_reference(cursor)

        # Should parse with attribute
        assert result is not None


# ============================================================================
# LINES 491, 498, 510: Attribute Reference Through Term
# ============================================================================


class TestAttributeReferenceThroughTerm:
    """Test attribute reference within term references."""

    def test_term_with_invalid_attribute(self) -> None:
        """Test term reference with invalid attribute (spaces instead of name)."""
        source = "-brand.  "  # Dot followed by spaces (no valid identifier)
        cursor = Cursor(source, 0)

        result = parse_term_reference(cursor)

        # Invalid: dot is followed by whitespace, not an identifier
        assert result is None


# ============================================================================
# LINES 533, 576, 584: Function Reference Parsing
# ============================================================================


class TestFunctionReferenceParsing:
    """Test function reference parsing errors."""

    def test_function_reference_no_identifier_line_533(self) -> None:
        """Test function reference without identifier (line 533)."""
        source = "  "  # No identifier
        cursor = Cursor(source, 0)

        result = parse_function_reference(cursor)

        # Should return None
        assert result is None

    def test_function_reference_no_opening_paren_line_576(self) -> None:
        """Test function reference without ( (line 576)."""
        source = "FUNC "  # No (
        cursor = Cursor(source, 0)

        result = parse_function_reference(cursor)

        # Should return None
        assert result is None

    def test_function_reference_valid(self) -> None:
        """Test valid function reference."""
        source = "NUMBER(42)"
        cursor = Cursor(source, 0)

        result = parse_function_reference(cursor)

        # Should parse successfully
        assert result is not None


# ============================================================================
# LINES 602, 614, 653-661, 672, 685, 740: Through Placeable Integration
# ============================================================================


class TestComplexPlaceableExpressions:
    """Test complex expressions through placeable to hit various paths."""

    def test_placeable_with_function_call_args(self) -> None:
        """Test placeable with function call and arguments."""
        source = 'NUMBER(42, style: "percent")'
        cursor = Cursor(source, 0)

        result = parse_function_reference(cursor)

        # Should parse with arguments
        assert result is not None

    def test_placeable_with_invalid_function(self) -> None:
        """Test placeable with invalid function syntax."""
        source = "NUMBER("  # No closing paren
        cursor = Cursor(source, 0)

        result = parse_function_reference(cursor)

        # Should return None
        assert result is None


# ============================================================================
# LINE 627: Placeable Invalid Content
# ============================================================================


class TestLine627PlaceableInvalidContent:
    """Test placeable with various invalid contents."""

    def test_placeable_unexpected_char(self) -> None:
        """Test placeable with unexpected character (line 627)."""
        source = "{"  # Just opening brace
        cursor = Cursor(source, 1)  # After {

        result = parse_placeable(cursor)

        # Should return None for invalid content
        assert result is None

    def test_placeable_only_whitespace(self) -> None:
        """Test placeable with only whitespace."""
        source = "{   }"
        cursor = Cursor(source, 1)

        result = parse_placeable(cursor)

        # Should return None
        assert result is None


# ============================================================================
# Integration: Multiple Error Paths
# ============================================================================


class TestMultipleErrorPaths:
    """Integration tests covering multiple error paths."""

    def test_nested_invalid_expressions(self) -> None:
        """Test deeply nested invalid expressions."""
        source = "{{{{"  # Multiple nested opening braces
        cursor = Cursor(source, 1)  # Start at second brace

        result = parse_placeable(cursor)

        # Invalid: nested braces without valid expression content
        assert result is None

    def test_complex_invalid_expression(self) -> None:
        """Test parse_inline_expression at position past valid content."""
        source = "$"  # Variable sigil only
        cursor = Cursor(source, 1)  # Position past the $

        from ftllexengine.syntax.parser.rules import parse_inline_expression

        result = parse_inline_expression(cursor)

        # Invalid: cursor positioned at EOF (past the $)
        assert result is None

    def test_function_with_invalid_syntax(self) -> None:
        """Test function reference with multiple consecutive commas."""
        source = "FUNC(,,,)"  # Invalid: empty arguments between commas
        cursor = Cursor(source, 0)

        result = parse_function_reference(cursor)

        # Invalid: commas without arguments between them
        assert result is None
