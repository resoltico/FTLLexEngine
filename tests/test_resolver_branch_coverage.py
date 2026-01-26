"""Branch coverage tests for resolver.py to achieve 100% coverage.

Tests specifically designed to cover uncovered branches:
- 404->400: Loop continuation after TextElement in _resolve_pattern
- 634->629: Loop continuation in _find_exact_variant for NumberLiteral case
"""

from __future__ import annotations

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


class TestPatternResolutionBranches:
    """Test pattern resolution loop continuation branches."""

    def test_pattern_with_multiple_text_elements_covers_loop_continuation(
        self,
    ) -> None:
        """Pattern with TextElement followed by another TextElement covers 404->400.

        This tests the loop continuation branch when iterating over pattern
        elements. After matching TextElement, the loop continues to the next
        element, hitting the 404->400 branch.
        """
        # Create pattern: "Hello" + "World"
        pattern = Pattern(
            elements=(
                TextElement(value="Hello "),
                TextElement(value="World"),
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

        result, errors = resolver.resolve_message(message, {})

        assert result == "Hello World"
        assert errors == ()

    def test_pattern_text_then_placeable_covers_loop_continuation(self) -> None:
        """Pattern with TextElement followed by Placeable covers 404->400.

        TextElement -> Placeable sequence ensures loop continues from
        TextElement case to process the next element.
        """
        pattern = Pattern(
            elements=(
                TextElement(value="Value: "),
                Placeable(expression=VariableReference(id=Identifier("x"))),
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

        result, errors = resolver.resolve_message(message, {"x": "42"})

        assert "Value: " in result
        assert "42" in result
        assert errors == ()

    def test_pattern_three_elements_ensures_multiple_loop_iterations(self) -> None:
        """Pattern with three elements ensures loop continuation branch is hit.

        Multiple iterations guarantee the 404->400 branch (loop continuation
        after TextElement) is exercised.
        """
        ftl = """msg = Start { $var } End"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg", {"var": "middle"})

        assert result == "Start middle End"


class TestVariantMatchingBranches:
    """Test variant matching loop continuation branches."""

    def test_select_with_non_matching_number_literals_covers_loop_continuation(
        self,
    ) -> None:
        """SelectExpression with non-matching NumberLiterals covers 634->629.

        When _find_exact_variant iterates through variants and encounters
        NumberLiteral keys that don't match, it continues to the next variant.
        This hits the 634->629 branch.
        """
        # Create select with 3 NumberLiteral variants, none matching
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

        # Pass value that doesn't match any NumberLiteral (forces iteration)
        result, errors = resolver.resolve_message(message, {"num": 99})

        # Should use default variant after iterating through all NumberLiterals
        assert result == "default"
        assert errors == ()

    def test_select_with_string_matching_identifier_after_number_literals(
        self,
    ) -> None:
        """SelectExpression with string selector after NumberLiterals covers 634->629.

        When selector is a string, _find_exact_variant enters the NumberLiteral
        case but numeric_for_match is None, causing it to continue the loop
        without returning. This covers the 634->629 continuation branch.
        """
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

        # String selector - will skip NumberLiteral variants, match Identifier
        result, errors = resolver.resolve_message(message, {"status": "active"})

        assert result == "Active"
        assert errors == ()

    def test_select_with_bool_selector_skips_number_literals(self) -> None:
        """SelectExpression with bool selector skips NumberLiterals (634->629).

        Boolean values are excluded from numeric matching (isinstance check
        filters them out) so they cause the loop to continue past NumberLiteral
        variants, covering the 634->629 branch.
        """
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

        # Boolean True - skips NumberLiterals, matches Identifier "true"
        result, errors = resolver.resolve_message(message, {"flag": True})

        assert result == "yes"
        assert errors == ()
