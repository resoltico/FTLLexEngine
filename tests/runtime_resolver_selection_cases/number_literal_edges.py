# mypy: ignore-errors
from __future__ import annotations

from decimal import Decimal

from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle
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

# ============================================================================
# PATTERN LOOP CONTINUATION
# ============================================================================



class TestNumericVariantEdgeCases:
    """Edge cases for numeric variant matching."""

    def test_boolean_does_not_match_number_variant(self) -> None:
        """Boolean values do not match numeric variants (isinstance guard)."""
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
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"flag": True})
        assert not errors
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
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"value": None})
        assert not errors
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
        sign = "negative" if decimal_str.is_signed() else "positive"
        event(f"decimal_sign={sign}")
        selector = VariableReference(id=Identifier("amount"))
        str_repr = str(decimal_str)
        variants = (
            Variant(
                key=NumberLiteral(value=decimal_str, raw=str_repr),
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
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"amount": decimal_str})
        assert not errors
        assert "exact" in result

class TestNumberLiteralNonMatchingValue:
    """Coverage for NumberLiteral with non-matching value (line 616->611)."""

    def test_number_literal_variants_first_no_match_second_matches(self) -> None:
        """Multiple NumberLiteral variants where first doesn't match, second does."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="one"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=2, raw="2"),
                    value=Pattern(elements=(TextElement(value="two"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=3, raw="3"),
                    value=Pattern(elements=(TextElement(value="three"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="fallback"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"count": 2})
        assert result == "two"
        assert errors == ()

    def test_number_literal_variants_all_no_match_uses_default(self) -> None:
        """NumberLiteral variants all fail to match, use default."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(
                Variant(
                    key=NumberLiteral(value=10, raw="10"),
                    value=Pattern(elements=(TextElement(value="ten"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=20, raw="20"),
                    value=Pattern(elements=(TextElement(value="twenty"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="default"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"count": 5})
        assert result == "default"
        assert errors == ()

    def test_number_literal_with_decimal_no_match(self) -> None:
        """NumberLiteral variants with Decimal selector that doesn't match."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("amount")),
            variants=(
                Variant(
                    key=NumberLiteral(value=100, raw="100"),
                    value=Pattern(elements=(TextElement(value="hundred"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=200, raw="200"),
                    value=Pattern(elements=(TextElement(value="two_hundred"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="other_amount"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"amount": Decimal("150.50")})
        assert result == "other_amount"
        assert errors == ()

    def test_number_literal_decimal_no_exact_match(self) -> None:
        """NumberLiteral variants with Decimal that doesn't exactly match."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("val")),
            variants=(
                Variant(
                    key=NumberLiteral(value=Decimal("1.0"), raw="1.0"),
                    value=Pattern(elements=(TextElement(value="one_point_oh"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=Decimal("2.5"), raw="2.5"),
                    value=Pattern(elements=(TextElement(value="two_point_five"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="other_decimal"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"val": Decimal("3.7")})
        assert result == "other_decimal"
        assert errors == ()

class TestNumberLiteralSelectorCoverage:
    """Test NumberLiteral selector branch in _find_exact_variant (branch 400->395)."""

    def test_number_literal_selector_exact_match(self) -> None:
        """Branch 400->395 - Number literal variant exact matching."""
        bundle = FluentBundle("en_US", use_isolating=False)

        bundle.add_resource(
            """
items = { $count ->
    [0] No items
    [1] One item
    [42] The answer
   *[other] { $count } items
}
"""
        )

        result, _ = bundle.format_pattern("items", {"count": 0})
        assert "No items" in result

        result, _ = bundle.format_pattern("items", {"count": 1})
        assert "One item" in result

        result, _ = bundle.format_pattern("items", {"count": 42})
        assert "The answer" in result

    def test_number_literal_selector_no_match(self) -> None:
        """Branch 400->395 - Number literal no match falls through to default."""
        bundle = FluentBundle("en_US", use_isolating=False)

        bundle.add_resource(
            """
level = { $num ->
    [1] Level 1
    [2] Level 2
   *[other] Level unknown
}
"""
        )

        result, _ = bundle.format_pattern("level", {"num": 99})
        assert "Level unknown" in result

    def test_number_literal_with_float_selector(self) -> None:
        """Branch 400->395 - Float selector matching number literals."""
        bundle = FluentBundle("en_US", use_isolating=False)

        bundle.add_resource(
            """
rating = { $stars ->
    [1] Poor
    [2] Fair
    [3] Good
    [4] Great
    [5] Excellent
   *[other] Unrated
}
"""
        )

        result, _ = bundle.format_pattern("rating", {"stars": Decimal(5)})
        assert "Excellent" in result

        result, _ = bundle.format_pattern("rating", {"stars": Decimal("3.5")})
        assert "Unrated" in result

    def test_number_literal_match_second_key(self) -> None:
        """Branch 400->395 - Number literal match on second+ key (loop continuation)."""
        bundle = FluentBundle("en_US", use_isolating=False)

        bundle.add_resource(
            """
score = { $points ->
    [10] Ten points
    [20] Twenty points
    [30] Thirty points
   *[other] Unknown
}
"""
        )

        result, _ = bundle.format_pattern("score", {"points": 20})
        assert "Twenty points" in result

        result, _ = bundle.format_pattern("score", {"points": 30})
        assert "Thirty points" in result

class TestNumberLiteralVariantMatching:
    """Test exact number literal matching in select expressions."""

    def test_exact_number_literal_match_with_integer(self) -> None:
        """Exact match with integer NumberLiteral (line 479)."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
msg = { $count ->
    [0] zero items
    [1] one item
    [42] exactly forty-two
   *[other] many items
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"count": 42})
        assert result == "exactly forty-two"
        assert errors == ()

    def test_exact_number_literal_match_with_decimal_pi(self) -> None:
        """Exact match with Decimal NumberLiteral value (pi example)."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
msg = { $value ->
    [3.14] pi
    [2.71] euler
   *[other] unknown
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"value": Decimal("3.14")})
        assert result == "pi"
        assert errors == ()

    def test_exact_number_literal_match_with_decimal(self) -> None:
        """Exact match with Decimal NumberLiteral (financial value precision)."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
msg = { $amount ->
    [99.99] special price
   *[other] regular price
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"amount": Decimal("99.99")})
        assert result == "special price"
        assert errors == ()
