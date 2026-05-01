# mypy: ignore-errors
# mypy: ignore-errors
from __future__ import annotations

from decimal import Decimal

from hypothesis import event, given
from hypothesis import strategies as st

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



class TestNumberLiteralVariantWithNonNumericSelector:
    """Coverage for NumberLiteral variant key with non-numeric selector (line 616->611)."""

    def test_number_literal_variant_with_string_selector(self) -> None:
        """SelectExpression with NumberLiteral variants but string selector falls to default."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("val")),
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

        result, errors = resolver.resolve_message(message, {"val": "not_a_number"})
        assert result == "fallback"
        assert errors == ()

    def test_number_literal_variant_with_none_selector(self) -> None:
        """SelectExpression with NumberLiteral variant but None selector falls to default."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("val")),
            variants=(
                Variant(
                    key=NumberLiteral(value=42, raw="42"),
                    value=Pattern(elements=(TextElement(value="forty-two"),)),
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

        result, errors = resolver.resolve_message(message, {"val": None})
        assert result == "default"
        assert errors == ()

    def test_number_literal_variant_with_bool_selector(self) -> None:
        """Bool selector matches identifier variant, not NumberLiteral.

        Booleans are excluded from numeric matching (even though isinstance(True, int))
        because they should match [true]/[false] identifier variants, not number literals.
        """
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("val")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="number_one"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("true"),
                    value=Pattern(elements=(TextElement(value="bool_true"),)),
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

        result, errors = resolver.resolve_message(message, {"val": True})
        assert result == "bool_true"
        assert errors == ()

    def test_number_literal_variants_with_date_selector(self) -> None:
        """SelectExpression with NumberLiteral variants but date selector falls to default."""
        from datetime import date

        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("val")),
            variants=(
                Variant(
                    key=NumberLiteral(value=3, raw="3"),
                    value=Pattern(elements=(TextElement(value="three"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="not_numeric"),)),
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

        result, errors = resolver.resolve_message(message, {"val": date(2024, 1, 1)})
        assert result == "not_numeric"
        assert errors == ()

class TestVariantMatchingBranches:
    """Test variant matching loop continuation branches."""

    def test_select_with_non_matching_number_literals_covers_loop_continuation(
        self,
    ) -> None:
        """SelectExpression with non-matching NumberLiterals covers 634->629."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("num")),
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

        result, errors = resolver.resolve_message(message, {"num": 99})
        assert result == "default"
        assert errors == ()

    def test_select_with_string_matching_identifier_after_number_literals(self) -> None:
        """String selector skips NumberLiteral variants to match Identifier (634->629)."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("status")),
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
                    key=Identifier("active"),
                    value=Pattern(elements=(TextElement(value="Active"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="Other"),)),
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

        result, errors = resolver.resolve_message(message, {"status": "active"})
        assert result == "Active"
        assert errors == ()

    def test_select_with_bool_selector_skips_number_literals(self) -> None:
        """Bool selector skips NumberLiterals, matches Identifier (634->629)."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("flag")),
            variants=(
                Variant(
                    key=NumberLiteral(value=0, raw="0"),
                    value=Pattern(elements=(TextElement(value="zero"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="one"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("true"),
                    value=Pattern(elements=(TextElement(value="yes"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("false"),
                    value=Pattern(elements=(TextElement(value="no"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="unknown"),)),
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

        result, errors = resolver.resolve_message(message, {"flag": True})
        assert result == "yes"
        assert errors == ()

class TestVariantNumericMatching:
    """Numeric variant matching (line 479->474 coverage)."""

    def test_exact_number_literal_match(self) -> None:
        """Exact number match with NumberLiteral variant key."""
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
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"count": 0})
        assert not errors
        assert "zero items" in result

        result, errors = resolver.resolve_message(message, {"count": 1})
        assert not errors
        assert "one item" in result

    def test_decimal_exact_match_in_variant(self) -> None:
        """Decimal value matches NumberLiteral variant key."""
        selector = VariableReference(id=Identifier("amount"))
        variants = (
            Variant(
                key=NumberLiteral(value=Decimal("1.5"), raw="1.5"),
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
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"amount": Decimal("1.5")})
        assert not errors
        assert "exact match" in result

    def test_float_exact_match_in_variant(self) -> None:
        """Float value matches NumberLiteral variant key."""
        selector = VariableReference(id=Identifier("price"))
        variants = (
            Variant(
                key=NumberLiteral(value=Decimal("9.99"), raw="9.99"),
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
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"price": Decimal("9.99")})
        assert not errors
        assert "special price" in result

    @given(number=st.integers(min_value=-100, max_value=100))
    def test_integer_exact_matching_property(self, number: int) -> None:
        """Property: Integer selectors match NumberLiteral variants exactly."""
        event(f"number={number}")
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
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"n": number})
        assert not errors
        assert "matched" in result
