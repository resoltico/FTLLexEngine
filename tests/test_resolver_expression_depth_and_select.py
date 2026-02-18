"""Tests for ResolutionContext expression depth and select expression edge cases.

Python 3.13+.
"""

from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolution_context import ResolutionContext
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax import NumberLiteral, Pattern, SelectExpression, TextElement, Variant


class TestResolutionContextExpressionDepth:
    """Test ResolutionContext.expression_depth property."""

    def test_expression_depth_property_initial(self) -> None:
        """expression_depth property returns 0 initially."""
        context = ResolutionContext()

        assert context.expression_depth == 0

    def test_expression_depth_property_after_increment(self) -> None:
        """expression_depth property reflects guard depth after increment."""
        context = ResolutionContext()

        # Use expression guard to increment depth
        with context.expression_guard:
            assert context.expression_depth == 1
            with context.expression_guard:
                assert context.expression_depth == 2

        assert context.expression_depth == 0


class TestSelectExpressionEdgeCases:
    """Test edge case branches in select expression resolution."""

    def test_select_variant_loop_with_no_match_on_identifier(self) -> None:
        """Select expression where identifier doesn't match continues loop."""
        # This tests the branch from line 438 (NumberLiteral case) back to line 433 (loop)
        # when the number doesn't match
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Create select with multiple variants including NumberLiteral that won't match
        selector = NumberLiteral(value=5, raw="5")
        variants = (
            Variant(
                key=NumberLiteral(value=1, raw="1"),
                value=Pattern(elements=()),
                default=False,
            ),
            Variant(
                key=NumberLiteral(value=2, raw="2"),
                value=Pattern(elements=()),
                default=False,
            ),
            Variant(
                key=NumberLiteral(value=3, raw="3"),
                value=Pattern(elements=()),
                default=True,  # This should match as default
            ),
        )

        select_expr = SelectExpression(selector=selector, variants=variants)

        # Resolve - should hit the loop continuation branch for non-matching numbers
        context = ResolutionContext()
        result = resolver._resolve_select_expression(select_expr, {}, [], context)

        # Should fall through to default variant (empty pattern)
        assert result == ""

    def test_pattern_elements_loop_with_textonly(self) -> None:
        """Pattern resolution with only TextElement tests loop continuation."""
        # This ensures we hit the branch from line 278 (Placeable case) back to 274
        # by having a pattern with multiple text elements
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        pattern = Pattern(
            elements=(
                TextElement(value="Hello "),
                TextElement(value="World"),
                TextElement(value="!"),
            )
        )

        context = ResolutionContext()
        result = resolver._resolve_pattern(pattern, {}, [], context)

        assert result == "Hello World!"
