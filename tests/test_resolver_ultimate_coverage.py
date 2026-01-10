"""Ultimate coverage tests for the last 2 uncovered branches in resolver.py.

Branches:
- 390->386: Placeable case with FormattingError exception
- 616->611: NumberLiteral case with non-matching numeric value (fall-through)
"""

from decimal import Decimal

from ftllexengine.core.errors import FormattingError
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax.ast import (
    CallArguments,
    FunctionReference,
    Identifier,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    StringLiteral,
    TextElement,
    VariableReference,
    Variant,
)


class TestPlaceableWithFormattingError:
    """Coverage for Placeable exception path with FormattingError (line 390->386)."""

    def test_placeable_formatting_error_with_fallback(self) -> None:
        """Placeable that raises FormattingError uses fallback value."""
        # Create a message with a placeable that will trigger FormattingError
        # This tests the exception path: case FormattingError(fallback_value=fallback)

        # To trigger FormattingError, we need a function that raises it
        # Let's register a custom function that raises FormattingError
        def raise_formatting_error(_value: str) -> str:
            msg = "Custom formatting error"
            raise FormattingError(
                msg,
                fallback_value="FALLBACK",
            )

        registry = FunctionRegistry()
        registry.register(raise_formatting_error, ftl_name="ERROR_FUNC")

        func_call = FunctionReference(
            id=Identifier("ERROR_FUNC"),
            arguments=CallArguments(
                positional=(StringLiteral(value="test"),),
                named=(),
            ),
        )

        pattern = Pattern(
            elements=(
                TextElement(value="Before "),
                Placeable(expression=func_call),
                TextElement(value=" After"),
            )
        )
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})

        # FormattingError should be caught, fallback value used
        assert result == "Before FALLBACK After"
        assert len(errors) == 1
        assert isinstance(errors[0], FormattingError)


class TestNumberLiteralNonMatchingValue:
    """Coverage for NumberLiteral with non-matching value (line 616->611)."""

    def test_number_literal_variants_first_no_match_second_matches(self) -> None:
        """Multiple NumberLiteral variants where first doesn't match."""
        # Create select with multiple number literal variants
        # Pass a value that doesn't match the first variant but matches the second
        # This tests the fall-through path from NumberLiteral case when no match
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

        # Pass 2 - should skip variant [1], match variant [2]
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

        # Pass 5 - doesn't match 10 or 20, use default
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

        # Pass Decimal that doesn't match any variant
        result, errors = resolver.resolve_message(
            message, {"amount": Decimal("150.50")}
        )
        assert result == "other_amount"
        assert errors == ()

    def test_number_literal_float_no_exact_match(self) -> None:
        """NumberLiteral variants with float that doesn't exactly match."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("val")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1.0, raw="1.0"),
                    value=Pattern(elements=(TextElement(value="one_point_oh"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=2.5, raw="2.5"),
                    value=Pattern(elements=(TextElement(value="two_point_five"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="other_float"),)),
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

        # Pass float that doesn't match any variant
        result, errors = resolver.resolve_message(message, {"val": 3.7})
        assert result == "other_float"
        assert errors == ()
