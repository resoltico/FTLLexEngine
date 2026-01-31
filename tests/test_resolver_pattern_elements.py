"""Final tests to achieve 100% branch coverage for resolver.py.

Targets the last 2 uncovered branches:
- 390->386: Pattern loop continuation after non-exception Placeable
- 616->611: NumberLiteral variant key with non-numeric selector
"""

from datetime import date

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


class TestPatternLoopContinuation:
    """Coverage for pattern loop continuation (line 390->386)."""

    def test_empty_pattern_no_elements(self) -> None:
        """Pattern with no elements exits loop immediately."""
        pattern = Pattern(elements=())
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {})
        assert result == ""
        assert errors == ()

    def test_pattern_text_then_placeable_then_text(self) -> None:
        """Pattern with alternating Text/Placeable/Text elements."""
        # Pattern structure: text, placeable, text
        pattern = Pattern(
            elements=(
                TextElement(value="Start "),
                Placeable(expression=VariableReference(id=Identifier("var"))),
                TextElement(value=" End"),
            )
        )
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"var": "X"})
        assert result == "Start X End"
        assert errors == ()

    def test_pattern_only_text_elements(self) -> None:
        """Pattern with only TextElements (no Placeables)."""
        pattern = Pattern(
            elements=(
                TextElement(value="First "),
                TextElement(value="Second "),
                TextElement(value="Third"),
            )
        )
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {})
        assert result == "First Second Third"
        assert errors == ()


class TestNumberLiteralVariantWithNonNumericSelector:
    """Coverage for NumberLiteral variant key with non-numeric selector (line 616->611)."""

    def test_number_literal_variant_with_string_selector(self) -> None:
        """SelectExpression with NumberLiteral variant but string selector value."""
        # Create select with number literal variants but pass a string selector
        # This exercises the branch where numeric_for_match is None
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

        # Pass a string value - this should not match number literal variants
        # and fall through to the default "other" variant
        result, errors = resolver.resolve_message(message, {"val": "not_a_number"})
        assert result == "fallback"
        assert errors == ()

    def test_number_literal_variant_with_none_selector(self) -> None:
        """SelectExpression with NumberLiteral variant but None selector value."""
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

        # Pass None - should not match number literal and fall to default
        result, errors = resolver.resolve_message(message, {"val": None})
        assert result == "default"
        assert errors == ()

    def test_number_literal_variant_with_bool_selector(self) -> None:
        """SelectExpression with NumberLiteral variant but bool selector value.

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

        # Pass True (bool) - should match "true" identifier, not number 1
        result, errors = resolver.resolve_message(message, {"val": True})
        assert result == "bool_true"
        assert errors == ()

    def test_number_literal_variants_with_dict_selector(self) -> None:
        """SelectExpression with NumberLiteral variants but dict-like selector value."""
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

        # Pass a date object - should not match number literal
        result, errors = resolver.resolve_message(
            message, {"val": date(2024, 1, 1)}
        )
        assert result == "not_numeric"
        assert errors == ()
