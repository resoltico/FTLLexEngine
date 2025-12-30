"""Comprehensive coverage tests for runtime/resolver.py.

Targets remaining uncovered branches and defensive code paths.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.diagnostics import FluentReferenceError, FluentResolutionError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolver import FluentResolver, ResolutionContext
from ftllexengine.syntax.ast import (
    FunctionReference,
    Identifier,
    MessageReference,
    NumberLiteral,
    Placeable,
    SelectExpression,
    StringLiteral,
    TermReference,
    VariableReference,
)

# ============================================================================
# LINE 208: Nested Placeable in _resolve_expression
# ============================================================================


class TestNestedPlaceableExpression:
    """Test Placeable case in _resolve_expression (line 208).

    While FTL grammar doesn't allow Placeable wrapping Placeable,
    the resolver handles it defensively for programmatic AST construction.
    """

    def test_programmatic_nested_placeable_with_variable(self) -> None:
        """Verify _resolve_expression handles Placeable(VariableReference)."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        # Create nested Placeable programmatically: Placeable(Placeable(VariableReference))
        inner_var = VariableReference(id=Identifier(name="test"))
        inner_placeable = Placeable(expression=inner_var)
        outer_placeable = Placeable(expression=inner_placeable)

        # Resolve outer placeable - should unwrap to inner variable
        args = {"test": "value123"}
        errors: list = []
        context = ResolutionContext()
        result = resolver._resolve_expression(outer_placeable, args, errors, context)
        assert result == "value123"

    def test_programmatic_nested_placeable_with_string_literal(self) -> None:
        """Verify _resolve_expression handles Placeable(StringLiteral)."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        # Placeable wrapping StringLiteral
        string_lit = StringLiteral(value="literal_text")
        placeable = Placeable(expression=string_lit)

        errors: list = []
        context = ResolutionContext()
        result = resolver._resolve_expression(placeable, {}, errors, context)
        assert result == "literal_text"

    def test_programmatic_nested_placeable_with_number_literal(self) -> None:
        """Verify _resolve_expression handles Placeable(NumberLiteral)."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        # Placeable wrapping NumberLiteral
        number_lit = NumberLiteral(value=42.5, raw="42.5")
        placeable = Placeable(expression=number_lit)

        errors: list = []
        context = ResolutionContext()
        result = resolver._resolve_expression(placeable, {}, errors, context)
        assert result == 42.5

    def test_programmatic_deeply_nested_placeables(self) -> None:
        """Verify _resolve_expression handles multiple nesting levels."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        # Triple nested: Placeable(Placeable(Placeable(StringLiteral)))
        string_lit = StringLiteral(value="deep")
        level1 = Placeable(expression=string_lit)
        level2 = Placeable(expression=level1)
        level3 = Placeable(expression=level2)

        errors: list = []
        context = ResolutionContext()
        result = resolver._resolve_expression(level3, {}, errors, context)
        assert result == "deep"


# ============================================================================
# Error Path Coverage: Unknown Expression Type
# ============================================================================


class TestUnknownExpressionType:
    """Test unknown expression type handling in _resolve_expression."""

    def test_unknown_expression_raises_resolution_error(self) -> None:
        """Verify unknown expression type raises FluentResolutionError."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        # Create mock expression with unknown type
        class UnknownExpr:
            """Mock unknown expression type."""

        unknown = UnknownExpr()

        errors: list = []
        context = ResolutionContext()
        with pytest.raises(FluentResolutionError) as exc_info:
            resolver._resolve_expression(unknown, {}, errors, context)  # type: ignore[arg-type]

        error_msg = str(exc_info.value).lower()
        assert "unknown expression" in error_msg or "UnknownExpr" in str(exc_info.value)


# ============================================================================
# Format Value Edge Cases
# ============================================================================


class TestFormatValueComprehensive:
    """Test _format_value with all FluentValue types."""

    def test_format_value_with_string(self) -> None:
        """Verify _format_value handles strings."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )
        assert resolver._format_value("test") == "test"
        assert resolver._format_value("") == ""

    def test_format_value_with_bool_true(self) -> None:
        """Verify _format_value handles True as 'true'."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )
        assert resolver._format_value(True) == "true"

    def test_format_value_with_bool_false(self) -> None:
        """Verify _format_value handles False as 'false'."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )
        assert resolver._format_value(False) == "false"

    def test_format_value_with_int(self) -> None:
        """Verify _format_value handles integers."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )
        assert resolver._format_value(42) == "42"
        assert resolver._format_value(0) == "0"
        assert resolver._format_value(-100) == "-100"

    def test_format_value_with_float(self) -> None:
        """Verify _format_value handles floats."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )
        assert resolver._format_value(3.14) == "3.14"
        assert resolver._format_value(0.0) == "0.0"

    def test_format_value_with_none(self) -> None:
        """Verify _format_value handles None as empty string."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )
        assert resolver._format_value(None) == ""

    def test_format_value_with_decimal(self) -> None:
        """Verify _format_value handles Decimal."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )
        assert resolver._format_value(Decimal("123.45")) == "123.45"

    def test_format_value_with_datetime(self) -> None:
        """Verify _format_value handles datetime via str()."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )
        dt = datetime(2025, 12, 11, 15, 30, 45, tzinfo=UTC)
        result = resolver._format_value(dt)
        assert "2025" in result
        assert "12" in result
        assert "11" in result

    @given(
        value=st.one_of(
            st.text(),
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.booleans(),
            st.none(),
        )
    )
    def test_format_value_never_raises(self, value: str | int | float | bool | None) -> None:
        """PROPERTY: _format_value never raises exceptions."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )
        result = resolver._format_value(value)
        assert isinstance(result, str)


# ============================================================================
# Fallback Generation Edge Cases
# ============================================================================


class TestFallbackGeneration:
    """Test _get_fallback_for_placeable edge cases."""

    def test_fallback_message_reference_with_attribute(self) -> None:
        """Verify fallback for MessageReference with attribute."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        msg_ref = MessageReference(
            id=Identifier(name="greeting"),
            attribute=Identifier(name="formal"),
        )
        fallback = resolver._get_fallback_for_placeable(msg_ref)
        assert fallback == "{greeting.formal}"

    def test_fallback_term_reference_with_attribute(self) -> None:
        """Verify fallback for TermReference with attribute."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        term_ref = TermReference(
            id=Identifier(name="brand"),
            attribute=Identifier(name="gender"),
            arguments=None,
        )
        fallback = resolver._get_fallback_for_placeable(term_ref)
        assert fallback == "{-brand.gender}"

    def test_fallback_function_reference(self) -> None:
        """Verify fallback for FunctionReference shows (...)."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        func_ref = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=Mock(),
        )
        fallback = resolver._get_fallback_for_placeable(func_ref)
        assert fallback == "{!NUMBER}"

    def test_fallback_select_expression(self) -> None:
        """Verify fallback for SelectExpression uses generic {???}."""
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        # SelectExpression with unknown selector type
        select_expr_unknown = SelectExpression(
            selector=Mock(),
            variants=(),
        )
        fallback = resolver._get_fallback_for_placeable(select_expr_unknown)
        assert fallback == "{{???} -> ...}"

        # SelectExpression with VariableReference selector provides context
        var_selector = VariableReference(id=Identifier(name="status"))
        select_expr_var = SelectExpression(
            selector=var_selector,
            variants=(),
        )
        fallback = resolver._get_fallback_for_placeable(select_expr_var)
        assert fallback == "{{$status} -> ...}"


# ============================================================================
# Integration Tests: Full Resolution Paths
# ============================================================================


class TestResolverFullIntegration:
    """Integration tests covering full resolution paths."""

    def test_message_with_variable_and_text_elements(self) -> None:
        """Test pattern with TextElement and Placeable(VariableReference)."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("greeting = Hello, { $name }!")

        result, errors = bundle.format_pattern("greeting", {"name": "Alice"})
        assert result == "Hello, Alice!"
        assert len(errors) == 0

    def test_message_with_multiple_placeables(self) -> None:
        """Test pattern with multiple placeables."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("info = Name: { $name }, Age: { $age }, City: { $city }")

        result, errors = bundle.format_pattern("info", {"name": "Bob", "age": 30, "city": "NYC"})
        assert "Bob" in result
        assert "30" in result
        assert "NYC" in result
        assert len(errors) == 0

    def test_message_with_isolating_enabled(self) -> None:
        """Test placeables with Unicode bidi isolation marks."""
        bundle = FluentBundle("en_US", use_isolating=True)
        bundle.add_resource("rtl = Value: { $text }")

        result, errors = bundle.format_pattern("rtl", {"text": "العربية"})
        # Should contain FSI (U+2068) and PDI (U+2069)
        assert "\u2068" in result
        assert "\u2069" in result
        assert "العربية" in result
        assert len(errors) == 0

    def test_error_in_placeable_produces_fallback(self) -> None:
        """Verify error in placeable resolution produces fallback."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("msg = Start { $missing } End")

        result, errors = bundle.format_pattern("msg")
        # Should have error
        assert len(errors) == 1
        assert isinstance(errors[0], FluentReferenceError)
        # Should have fallback
        assert "Start" in result
        assert "End" in result
        assert "{$missing}" in result

    def test_resolution_with_empty_args(self) -> None:
        """Verify resolution with None args is treated as empty dict."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("simple = Just text")

        result, errors = bundle.format_pattern("simple", None)
        assert result == "Just text"
        assert len(errors) == 0

    @given(
        text=st.text(min_size=0, max_size=100),
        var_value=st.text(min_size=1, max_size=50),
    )
    def test_resolution_with_arbitrary_text(self, text: str, var_value: str) -> None:
        """PROPERTY: Resolver handles arbitrary text and variable values."""
        from hypothesis import assume  # noqa: PLC0415

        # Skip text containing FTL special chars
        assume(not any(c in text for c in "{}[]#.=-*\n\r"))
        assume(text.strip() == text)  # No leading/trailing whitespace

        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(f"msg = {text} {{ $var }}")

        result, _errors = bundle.format_pattern("msg", {"var": var_value})
        assert var_value in result
        if text:
            assert text in result


# ============================================================================
# TextElement Branch Coverage (line 286->282)
# ============================================================================


class TestTextElementBranch:
    """Test TextElement branch in pattern resolution."""

    def test_pattern_with_only_text_no_placeables(self) -> None:
        """Test pattern with only TextElement, no Placeable (line 286->282).

        This tests the case where pattern.elements contains only TextElement
        nodes, ensuring the TextElement branch is taken and not the Placeable branch.
        """
        bundle = FluentBundle("en_US")
        bundle.add_resource("simple = This is plain text with no variables")

        result, errors = bundle.format_pattern("simple")

        assert result == "This is plain text with no variables"
        assert errors == ()


# ============================================================================
# Term Reference with Positional Arguments (line 450)
# ============================================================================


class TestTermReferencePositionalArguments:
    """Test term reference with positional arguments."""

    def test_term_reference_with_positional_args(self) -> None:
        """Test term reference with positional arguments (line 450).

        While term references typically use named arguments, the resolver
        evaluates positional arguments to collect any errors they might produce.
        This tests line 450 where positional args are evaluated.
        """
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
-my-term = Term value
msg = { -my-term($arg1, $arg2) }
""")

        # Provide the variables referenced in positional args
        result, errors = bundle.format_pattern("msg", {"arg1": "val1", "arg2": "val2"})

        # Should resolve successfully
        assert result == "Term value"
        assert errors == ()

    def test_term_reference_positional_args_trigger_errors(self) -> None:
        """Test term reference positional args collect errors when variables missing.

        This ensures line 450 evaluates positional args and collects any
        errors they produce (like missing variables).
        """
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
-my-term = Term value
msg = { -my-term($missing_var) }
""")

        # Don't provide $missing_var - should collect error
        _result, errors = bundle.format_pattern("msg", {})

        # Term reference with missing variable should still resolve the term
        # but collect the error from evaluating the positional arg
        assert len(errors) >= 1


# ============================================================================
# Number Literal Variant Matching (line 479->474)
# ============================================================================


class TestNumberLiteralVariantMatching:
    """Test exact number literal matching in select expressions."""

    def test_exact_number_literal_match_with_integer(self) -> None:
        """Test exact match with integer NumberLiteral (line 479).

        This tests the NumberLiteral case in _find_exact_variant where
        we match numeric selectors against number literal keys.
        """
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
msg = { $count ->
    [0] zero items
    [1] one item
    [42] exactly forty-two
   *[other] many items
}
""")

        # Test exact match with number literal key [42]
        result, errors = bundle.format_pattern("msg", {"count": 42})

        assert result == "exactly forty-two"
        assert errors == ()

    def test_exact_number_literal_match_with_float(self) -> None:
        """Test exact match with float NumberLiteral.

        This tests the Decimal comparison logic for float selectors.
        """
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
msg = { $value ->
    [3.14] pi
    [2.71] euler
   *[other] unknown
}
""")

        # Test exact match with float literal
        result, errors = bundle.format_pattern("msg", {"value": 3.14})

        assert result == "pi"
        assert errors == ()

    def test_exact_number_literal_match_with_decimal(self) -> None:
        """Test exact match with Decimal NumberLiteral.

        This tests the Decimal comparison path for currency/financial values.
        """
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
msg = { $amount ->
    [99.99] special price
   *[other] regular price
}
""")

        # Use Decimal for exact financial value
        result, errors = bundle.format_pattern("msg", {"amount": Decimal("99.99")})

        assert result == "special price"
        assert errors == ()
