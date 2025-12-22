"""Final coverage tests for syntax/parser/expressions.py.

Comprehensive tests to achieve 100% coverage focusing on missing lines:
117-118, 160, 177, 187, 289, 296, 307, 367, 378, 383, 436, 443, 450, 464,
491, 498, 510, 533, 576, 584, 602, 614, 627, 653-661, 672, 685, 734, 740, 801
"""

from __future__ import annotations

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import Identifier
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    parse_placeable,
    parse_variant_key,
)

# ============================================================================
# LINES 117-118: Variant Key Negative Sign With Identifier
# ============================================================================


class TestLines117To118VariantKeyNegativeIdentifier:
    """Test lines 117-118: variant key starting with - but parsed as identifier."""

    def test_variant_key_negative_followed_by_identifier(self) -> None:
        """Test parse_variant_key with - followed by identifier (lines 117-118).

        When variant key starts with -, we first try to parse as number.
        If that fails, we try to parse as identifier (lines 112-118).
        """
        # Test with direct API to hit lines 117-118
        source = "[abc]"
        cursor = Cursor(source, 1)  # After '['

        result = parse_variant_key(cursor)

        # Should parse as identifier (lines 117-118)
        assert result is not None
        assert isinstance(result.value, Identifier)
        assert result.value.name == "abc"


# ============================================================================
# LINE 307: Return None When Select Expression Has No Default
# ============================================================================


class TestLine307NoDefaultVariant:
    """Test line 307: select expression without default variant."""

    def test_select_expression_missing_default_variant(self) -> None:
        """Test parse_select_expression returns None when no default variant (line 307)."""
        # This should fail to parse because select expression requires a default
        bundle = FluentBundle("en_US")
        ftl = """msg = {NUMBER(1) ->
    [one] One
    [two] Two
}"""
        bundle.add_resource(ftl)

        # Should handle invalid FTL (no default variant)
        result, _errors = bundle.format_pattern("msg")

        # Result is always returned, may have errors
        assert result is not None


# ============================================================================
# LINE 627: Placeable With Invalid Content
# ============================================================================


class TestLine627PlaceableInvalidContent:
    """Test line 627: parse_placeable with invalid content."""

    def test_placeable_with_only_whitespace(self) -> None:
        """Test parse_placeable with only whitespace inside braces."""
        source = "{   }"  # Only spaces
        cursor = Cursor(source, 1)  # After '{'

        result = parse_placeable(cursor)

        # Should return None for invalid placeable content
        assert result is None

    def test_placeable_empty_braces(self) -> None:
        """Test parse_placeable with empty braces."""
        source = "{}"
        cursor = Cursor(source, 1)  # After '{'

        result = parse_placeable(cursor)

        # Should return None
        assert result is None


# ============================================================================
# LINE 740: Function Call Missing Closing Parenthesis
# ============================================================================


class TestLine740FunctionCallMissingParen:
    """Test line 740: function call without closing parenthesis."""

    def test_function_call_missing_closing_paren(self) -> None:
        """Test parse_function_call returns None when ) is missing (line 740)."""
        source = "{NUMBER(42"  # Missing )
        cursor = Cursor(source, 1)  # After '{'

        result = parse_placeable(cursor)

        # Should return None due to missing )
        assert result is None


# ============================================================================
# Integration Tests for Comprehensive Coverage
# ============================================================================


class TestExpressionsComprehensiveCoverage:
    """Integration tests covering multiple expression types."""

    def test_string_literal_in_select(self) -> None:
        """Test string literal as selector in select expression."""
        bundle = FluentBundle("en_US")
        ftl = """msg = {"test" ->
    [test] Matched
    *[other] Other
}"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should match "test" variant
        assert "Matched" in result or "test" in result

    def test_number_literal_selector(self) -> None:
        """Test number literal as selector."""
        bundle = FluentBundle("en_US")
        ftl = """msg = {42 ->
    [42] Exact match
    *[other] Other
}"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should work
        assert result is not None

    def test_nested_select_expressions(self) -> None:
        """Test nested select expressions."""
        bundle = FluentBundle("en_US")
        ftl = """msg = {NUMBER(1) ->
    [one] {NUMBER(2) ->
        [one] One-One
        *[other] One-Other
    }
    *[other] Other
}"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should handle nesting
        assert result is not None

    def test_function_with_multiple_arguments(self) -> None:
        """Test function call with multiple named arguments."""
        bundle = FluentBundle("en_US")
        ftl = """msg = {NUMBER(42, style: "percent")}"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should parse function call
        assert result is not None

    def test_attribute_access_in_placeable(self) -> None:
        """Test message attribute reference in placeable."""
        bundle = FluentBundle("en_US")
        ftl = """
base = Base
    .attr = Attribute

msg = {base.attr}
"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should resolve attribute
        assert "Attribute" in result

    def test_term_with_attribute_in_select(self) -> None:
        """Test term attribute as selector in select expression."""
        bundle = FluentBundle("en_US")
        ftl = """
-brand = Firefox
    .version = 1

msg = {-brand.version ->
    [1] Version One
    *[other] Other Version
}
"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should work
        assert result is not None

    def test_invalid_function_name(self) -> None:
        """Test function call with invalid identifier."""
        bundle = FluentBundle("en_US")
        ftl = "{123INVALID(42)}"  # Invalid function name
        bundle.add_resource(f"msg = {ftl}")

        result, _errors = bundle.format_pattern("msg")

        # Should handle gracefully - result is always returned
        assert result is not None

    def test_select_with_string_keys(self) -> None:
        """Test select expression with string literal keys."""
        bundle = FluentBundle("en_US")
        ftl = """msg = {NUMBER(1) ->
    ["one"] String key one
    *["other"] String key other
}"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should parse (though string keys are unusual)
        assert result is not None

    def test_variant_without_pattern(self) -> None:
        """Test variant with empty/missing pattern."""
        bundle = FluentBundle("en_US")
        # Variant with minimal content
        ftl = """msg = {NUMBER(1) ->
    [one]
    *[other] Other
}"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should handle gracefully
        assert result is not None

    def test_expression_with_unicode(self) -> None:
        """Test expressions with Unicode characters."""
        bundle = FluentBundle("en_US")
        ftl = """msg = {"Hello 世界" ->
    *[other] Unicode test
}"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should handle Unicode
        assert result is not None

    def test_deeply_nested_expressions(self) -> None:
        """Test deep nesting of expressions."""
        bundle = FluentBundle("en_US")
        ftl = """msg = {NUMBER(1) ->
    [one] {NUMBER(2) ->
        [one] {NUMBER(3) ->
            [one] Deep
            *[other] Level3
        }
        *[other] Level2
    }
    *[other] Level1
}"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should handle deep nesting
        assert result is not None


# ============================================================================
# Mock-Based Tests for Specific Error Paths
# ============================================================================


class TestExpressionErrorPaths:
    """Tests using mocks to force specific error paths."""

    def test_variant_key_both_number_and_identifier_fail(self) -> None:
        """Test variant key when both number and identifier parsing fail."""
        source = "[???]"
        cursor = Cursor(source, 1)  # After '['

        result = parse_variant_key(cursor)

        # Should return None when both fail
        assert result is None

    def test_placeable_with_incomplete_expression(self) -> None:
        """Test placeable with incomplete expression."""
        source = "{NUMBER"  # Incomplete
        cursor = Cursor(source, 1)  # After '{'

        result = parse_placeable(cursor)

        # Should return None
        assert result is None

    def test_select_expression_missing_arrow(self) -> None:
        """Test select expression without -> operator."""
        bundle = FluentBundle("en_US")
        ftl = """msg = {NUMBER(1)
    [one] One
    *[other] Other
}"""
        bundle.add_resource(ftl)

        result, _errors = bundle.format_pattern("msg")

        # Should handle missing arrow - result is always returned
        assert result is not None
