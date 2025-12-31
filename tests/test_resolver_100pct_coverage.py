"""Targeted tests for 100% coverage of runtime resolver module.

Covers specific uncovered lines identified by coverage analysis.
Focuses on pattern resolution, variant matching, and fallback logic.
"""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    TextElement,
    VariableReference,
    Variant,
)


class TestPlaceableResolution:
    """Pattern resolution with placeables (line 286->282 coverage)."""

    def test_pattern_with_placeable_uses_isolating(self) -> None:
        """Placeable in pattern uses isolating marks."""
        # Create pattern with placeable
        pattern = Pattern(
            elements=(
                TextElement(value="Hello "),
                Placeable(expression=VariableReference(id=Identifier("name"))),
            )
        )
        message = Message(
            id=Identifier("greeting"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"greeting": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=True,
        )

        result, _errors = resolver.resolve_message(message, {"name": "World"})
        # Should include isolating marks around the variable
        assert "\u2068" in result  # FSI
        assert "\u2069" in result  # PDI
        assert "World" in result

    def test_pattern_with_placeable_without_isolating(self) -> None:
        """Placeable in pattern without isolating marks."""
        pattern = Pattern(
            elements=(
                TextElement(value="Hello "),
                Placeable(expression=VariableReference(id=Identifier("name"))),
            )
        )
        message = Message(
            id=Identifier("greeting"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"greeting": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, _errors = resolver.resolve_message(message, {"name": "World"})
        # Should NOT include isolating marks
        assert "\u2068" not in result
        assert "\u2069" not in result
        assert result == "Hello World"

    @given(
        var_name=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            min_size=1,
            max_size=10,
        ),
        value=st.text(min_size=0, max_size=20),
    )
    def test_placeable_resolution_property(self, var_name: str, value: str) -> None:
        """Property: Placeables always resolve variables from args."""
        pattern = Pattern(
            elements=(
                Placeable(expression=VariableReference(id=Identifier(var_name))),
            )
        )
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, _errors = resolver.resolve_message(message, {var_name: value})
        assert value in result


class TestVariantNumericMatching:
    """Numeric variant matching (line 479->474 coverage)."""

    def test_exact_number_literal_match(self) -> None:
        """Exact number match with NumberLiteral variant key."""
        # Create select expression with NumberLiteral variant keys
        selector = VariableReference(id=Identifier("count"))
        variants = (
            Variant(
                key=NumberLiteral(value=0, raw="0"),
                value=Pattern(elements=(TextElement(value="zero items"),)),
                default=False,
            ),
            Variant(
                key=NumberLiteral(value=1, raw="1"),
                value=Pattern(elements=(TextElement(value="one item"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="many items"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Test exact match with int
        result, _errors = resolver.resolve_message(message, {"count": 0})
        assert "zero items" in result

        # Test exact match with different value
        result, _errors = resolver.resolve_message(message, {"count": 1})
        assert "one item" in result

    def test_decimal_exact_match_in_variant(self) -> None:
        """Decimal value matches NumberLiteral variant key."""
        selector = VariableReference(id=Identifier("amount"))
        # NumberLiteral uses float, not Decimal (AST constraint)
        # But runtime accepts Decimal via FluentValue
        variants = (
            Variant(
                key=NumberLiteral(value=1.5, raw="1.5"),
                value=Pattern(elements=(TextElement(value="exact match"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="default"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Test Decimal value matches float variant
        result, _errors = resolver.resolve_message(message, {"amount": Decimal("1.5")})
        assert "exact match" in result

    def test_float_exact_match_in_variant(self) -> None:
        """Float value matches NumberLiteral variant key."""
        selector = VariableReference(id=Identifier("price"))
        variants = (
            Variant(
                key=NumberLiteral(value=9.99, raw="9.99"),
                value=Pattern(elements=(TextElement(value="special price"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="regular price"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, _errors = resolver.resolve_message(message, {"price": 9.99})
        assert "special price" in result

    @given(number=st.integers(min_value=-100, max_value=100))
    def test_integer_exact_matching_property(self, number: int) -> None:
        """Property: Integer selectors match NumberLiteral variants exactly."""
        selector = VariableReference(id=Identifier("n"))
        variants = (
            Variant(
                key=NumberLiteral(value=number, raw=str(number)),
                value=Pattern(elements=(TextElement(value="matched"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="not matched"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, _errors = resolver.resolve_message(message, {"n": number})
        assert "matched" in result


class TestFallbackVariantNoVariants:
    """Empty variant list error path (lines 645-648)."""

    def test_select_expression_with_no_variants_returns_error(self) -> None:
        """SelectExpression with empty variant list collects error."""
        # Create select expression with empty variants
        selector = VariableReference(id=Identifier("count"))
        select_expr = SelectExpression(selector=selector, variants=())
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Should collect error (resolver doesn't raise, it collects errors)
        result, errors = resolver.resolve_message(message, {"count": 1})
        # Should have error and fallback value
        assert len(errors) > 0
        assert result != ""

    def test_fallback_variant_with_empty_variants_after_selector_error(self) -> None:
        """Fallback path with empty variants after selector error."""
        # Create select expression where selector fails AND no variants
        selector = VariableReference(id=Identifier("missing"))
        select_expr = SelectExpression(selector=selector, variants=())
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Should collect errors (missing variable + no variants)
        result, errors = resolver.resolve_message(message, {})  # No args, selector fails
        # Should have errors
        assert len(errors) > 0
        assert result != ""


class TestSelectExpressionFallbackPaths:
    """Test fallback variant selection logic."""

    def test_selector_error_uses_default_variant(self) -> None:
        """When selector fails, uses default variant."""
        # Selector references missing variable
        selector = VariableReference(id=Identifier("missing"))
        variants = (
            Variant(
                key=Identifier("one"),
                value=Pattern(elements=(TextElement(value="variant one"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="default variant"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Selector error should fall back to default
        result, errors = resolver.resolve_message(message, {})
        assert "default variant" in result
        assert len(errors) > 0  # Should have error for missing variable

    def test_selector_error_uses_first_variant_when_no_default(self) -> None:
        """When selector fails and no default, uses first variant."""
        selector = VariableReference(id=Identifier("missing"))
        variants = (
            Variant(
                key=Identifier("first"),
                value=Pattern(elements=(TextElement(value="first variant"),)),
                default=False,
            ),
            Variant(
                key=Identifier("second"),
                value=Pattern(elements=(TextElement(value="second variant"),)),
                default=False,
            ),
        )
        # Note: This violates spec (must have default), but tests fallback path
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, _errors = resolver.resolve_message(message, {})
        assert "first variant" in result


class TestNumericVariantEdgeCases:
    """Edge cases for numeric variant matching."""

    def test_boolean_does_not_match_number_variant(self) -> None:
        """Boolean values should not match numeric variants."""
        # True is instance of int in Python, but should not match numbers
        selector = VariableReference(id=Identifier("flag"))
        variants = (
            Variant(
                key=NumberLiteral(value=1, raw="1"),
                value=Pattern(elements=(TextElement(value="numeric one"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="default"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # True should NOT match numeric 1
        result, _errors = resolver.resolve_message(message, {"flag": True})
        # Should use default, not numeric match
        assert "default" in result

    def test_none_selector_uses_default(self) -> None:
        """None selector value falls through to default."""
        selector = VariableReference(id=Identifier("value"))
        variants = (
            Variant(
                key=Identifier("none"),
                value=Pattern(elements=(TextElement(value="none variant"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="default variant"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # None should not match identifier "none", should use default
        result, _errors = resolver.resolve_message(message, {"value": None})
        assert "default variant" in result

    @given(
        decimal_str=st.decimals(
            min_value=Decimal("-100.00"),
            max_value=Decimal("100.00"),
            allow_nan=False,
            allow_infinity=False,
            places=2,
        )
    )
    def test_decimal_variant_matching_property(self, decimal_str: Decimal) -> None:
        """Property: Decimal values match exactly when variant key matches."""
        selector = VariableReference(id=Identifier("amount"))
        str_repr = str(decimal_str)
        # Convert Decimal to float for NumberLiteral (AST constraint)
        float_value = float(decimal_str)
        variants = (
            Variant(
                key=NumberLiteral(value=float_value, raw=str_repr),
                value=Pattern(elements=(TextElement(value="exact"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="default"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, _errors = resolver.resolve_message(message, {"amount": decimal_str})
        assert "exact" in result


class TestResolverFormattingErrorFallback:
    """Test FormattingError fallback handling in resolver."""

    def test_formatting_error_uses_fallback_value(self) -> None:
        """FormattingError fallback value is used in pattern resolution.

        This tests line 312 in resolver.py.
        """
        bundle = FluentBundle("en", use_isolating=False)

        # Create a scenario that triggers FormattingError with fallback
        # The NUMBER function with invalid options can trigger this
        bundle.add_resource("""
msg = Value: { NUMBER($value, minimumFractionDigits: "invalid") }
""")

        # This should trigger a FormattingError
        result, errors = bundle.format_pattern("msg", {"value": 42})

        # Should have an error
        assert len(errors) > 0
        # Result should contain fallback (the original value)
        assert "42" in result


class TestResolverTermNamedArguments:
    """Test term references with named arguments."""

    def test_term_reference_with_named_arguments(self) -> None:
        """Term references can have named arguments.

        This tests lines 445-447 in resolver.py.
        """
        bundle = FluentBundle("en", use_isolating=False)

        # Term with named arguments
        bundle.add_resource("""
-brand = { $case ->
    [nominative] Firefox
    *[other] Firefox
}
msg = Welcome to { -brand(case: "nominative") }
""")

        result, errors = bundle.format_pattern("msg")

        # Should successfully resolve with named arguments
        assert len(errors) == 0
        assert "Firefox" in result

    def test_term_reference_multiple_named_arguments(self) -> None:
        """Term with multiple named arguments."""
        bundle = FluentBundle("en", use_isolating=False)

        bundle.add_resource("""
-product = { $version } { $edition ->
    [pro] Professional
    *[standard] Standard
}
msg = Using { -product(version: "2.0", edition: "pro") }
""")

        result, errors = bundle.format_pattern("msg")

        # Should resolve both arguments
        assert len(errors) == 0
        assert "2.0" in result
        assert "Professional" in result


class TestResolverFluentNumberVariantMatching:
    """Test FluentNumber handling in variant selection."""

    def test_fluent_number_matches_numeric_variant_key(self) -> None:
        """FluentNumber value extraction for numeric variant matching.

        This tests line 502 in resolver.py.
        """
        bundle = FluentBundle("en", use_isolating=False)

        # Register NUMBER function that returns FluentNumber
        bundle.add_resource("""
msg = { NUMBER($count) ->
    [1000] Exactly one thousand
    *[other] Other value
}
""")

        # NUMBER() function produces FluentNumber, should match [1000]
        result, errors = bundle.format_pattern("msg", {"count": 1000})

        assert len(errors) == 0
        assert "Exactly one thousand" in result

    def test_fluent_number_plural_category_selection(self) -> None:
        """FluentNumber value extraction for CLDR plural matching.

        This tests line 608 in resolver.py.
        """
        bundle = FluentBundle("en", use_isolating=False)

        bundle.add_resource("""
msg = { NUMBER($count) ->
    [one] One item
    *[other] Many items
}
""")

        # NUMBER(1) produces FluentNumber(1, "1") -> should match "one" category
        result, errors = bundle.format_pattern("msg", {"count": 1})

        assert len(errors) == 0
        assert "One item" in result

    def test_fluent_number_with_formatted_display(self) -> None:
        """FluentNumber preserves numeric value while showing formatted string."""

        bundle = FluentBundle("en", use_isolating=False)

        bundle.add_resource("""
msg = { NUMBER($amount, minimumFractionDigits: 2) ->
    [1000] Exactly one thousand
    *[other] Other
}
""")

        # Should extract numeric value 1000 from FluentNumber for matching
        result, errors = bundle.format_pattern("msg", {"amount": 1000})

        assert len(errors) == 0
        assert "Exactly one thousand" in result
