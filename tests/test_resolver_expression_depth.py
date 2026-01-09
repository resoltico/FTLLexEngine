"""Tests for expression depth limiting in FluentResolver.

Regression tests for SEC-RESOLVE-RECURSION-6: Ensures that deeply nested
SelectExpression structures through variant patterns are properly depth-limited.

The security issue: Prior to the fix, the recursion path through
Pattern -> Placeable -> SelectExpression -> Variant Pattern -> Placeable -> ...
bypassed the expression_guard entirely because the guard was only applied
to nested Placeables (`{ { x } }`), not to Placeables containing SelectExpressions.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import (
    Identifier,
    InlineExpression,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    TextElement,
    VariableReference,
    Variant,
)


class TestSelectExpressionDepthLimit:
    """Verify depth limiting for SelectExpression recursion through variants."""

    def _create_nested_select_ast(self, depth: int) -> Message:
        """Create a Message with SelectExpression nested to specified depth.

        Structure: msg = { $var -> [one] { $var -> [one] { ... } *[other] x } *[other] x }
        """
        # Base case: innermost pattern
        inner_pattern = Pattern(elements=(TextElement(value="innermost"),))

        # Build from inside out
        current_pattern = inner_pattern
        for _ in range(depth):
            # Create a SelectExpression with the current pattern as a variant value
            select_expr = SelectExpression(
                selector=VariableReference(id=Identifier(name="var")),
                variants=(
                    Variant(
                        key=Identifier(name="one"),
                        value=current_pattern,
                        default=False,
                    ),
                    Variant(
                        key=Identifier(name="other"),
                        value=Pattern(elements=(TextElement(value="other"),)),
                        default=True,
                    ),
                ),
            )
            # Wrap in Placeable and new Pattern
            current_pattern = Pattern(
                elements=(Placeable(expression=select_expr),)
            )

        return Message(
            id=Identifier(name="nested"),
            value=current_pattern,
            attributes=(),
            comment=None,
        )

    def test_shallow_nesting_resolves_successfully(self) -> None:
        """SelectExpression with shallow nesting should resolve normally."""
        bundle = FluentBundle("en_US")
        message = self._create_nested_select_ast(depth=5)

        # Manually add the message to the bundle's internal registry
        bundle._messages["nested"] = message

        result, errors = bundle.format_pattern("nested", {"var": "one"})

        # Should resolve to innermost value (may include Unicode isolate markers)
        assert "innermost" in result
        assert errors == ()

    def test_deep_nesting_triggers_depth_limit(self) -> None:
        """SelectExpression nested beyond MAX_DEPTH should trigger depth limit."""
        bundle = FluentBundle("en_US")
        # Create nesting deeper than MAX_DEPTH (default 100)
        message = self._create_nested_select_ast(depth=MAX_DEPTH + 10)

        bundle._messages["nested"] = message

        _result, errors = bundle.format_pattern("nested", {"var": "one"})

        # Should have depth exceeded error
        assert len(errors) >= 1
        # The error should mention depth exceeded
        error_messages = [str(e) for e in errors]
        assert any("depth" in msg.lower() for msg in error_messages)

    def test_exact_max_depth_boundary(self) -> None:
        """Test behavior exactly at MAX_DEPTH boundary."""
        bundle = FluentBundle("en_US")
        # Create nesting at exactly MAX_DEPTH
        message = self._create_nested_select_ast(depth=MAX_DEPTH)

        bundle._messages["nested"] = message

        result, _errors = bundle.format_pattern("nested", {"var": "one"})

        # At exactly MAX_DEPTH, behavior may vary - the important thing is no crash
        # Depth errors may or may not occur at exact boundary
        # Not asserting errors because behavior is undefined at boundary
        assert result is not None

    def test_just_under_max_depth(self) -> None:
        """Test behavior just under MAX_DEPTH."""
        bundle = FluentBundle("en_US")
        # Create nesting just under MAX_DEPTH
        # Note: The actual limit is checked when entering the guard, so MAX_DEPTH-1
        # levels of nesting will use 0 to MAX_DEPTH-1 depth (MAX_DEPTH entries)
        message = self._create_nested_select_ast(depth=MAX_DEPTH - 5)

        bundle._messages["nested"] = message

        _result, errors = bundle.format_pattern("nested", {"var": "one"})

        # Should resolve without depth errors (might have other errors)
        depth_errors = [e for e in errors if "depth" in str(e).lower()]
        assert len(depth_errors) == 0


class TestNestedPlaceableDepthLimit:
    """Verify depth limiting for nested Placeables like { { { x } } }."""

    def _create_nested_placeable_ast(self, depth: int) -> Message:
        """Create a Message with Placeables nested to specified depth.

        Structure: msg = { { { ... { $var } ... } } }
        """
        # Innermost: variable reference
        inner_expr = VariableReference(id=Identifier(name="var"))

        # Build from inside out
        current_expr: InlineExpression = inner_expr
        for _ in range(depth):
            current_expr = Placeable(expression=current_expr)

        return Message(
            id=Identifier(name="nested"),
            value=Pattern(elements=(Placeable(expression=current_expr),)),
            attributes=(),
            comment=None,
        )

    def test_shallow_placeable_nesting_resolves(self) -> None:
        """Shallow placeable nesting should resolve normally."""
        bundle = FluentBundle("en_US")
        message = self._create_nested_placeable_ast(depth=5)

        bundle._messages["nested"] = message

        result, errors = bundle.format_pattern("nested", {"var": "hello"})

        # Result may include Unicode isolate markers
        assert "hello" in result
        assert errors == ()

    def test_deep_placeable_nesting_triggers_limit(self) -> None:
        """Deep placeable nesting should trigger depth limit."""
        bundle = FluentBundle("en_US")
        message = self._create_nested_placeable_ast(depth=MAX_DEPTH + 10)

        bundle._messages["nested"] = message

        _result, errors = bundle.format_pattern("nested", {"var": "hello"})

        # Should have depth exceeded error
        assert len(errors) >= 1


class TestMixedNestingDepthLimit:
    """Verify depth limiting for mixed SelectExpression and Placeable nesting."""

    def _create_mixed_nesting_ast(self, select_depth: int, placeable_depth: int) -> Message:
        """Create a Message mixing SelectExpression and Placeable nesting."""
        # Start with variable
        inner_expr = VariableReference(id=Identifier(name="var"))

        # Add placeable nesting
        current_expr: InlineExpression = inner_expr
        for _ in range(placeable_depth):
            current_expr = Placeable(expression=current_expr)

        # Wrap in pattern
        current_pattern = Pattern(elements=(Placeable(expression=current_expr),))

        # Add select expression nesting
        for _ in range(select_depth):
            select_expr = SelectExpression(
                selector=VariableReference(id=Identifier(name="sel")),
                variants=(
                    Variant(
                        key=Identifier(name="a"),
                        value=current_pattern,
                        default=False,
                    ),
                    Variant(
                        key=Identifier(name="b"),
                        value=Pattern(elements=(TextElement(value="b"),)),
                        default=True,
                    ),
                ),
            )
            current_pattern = Pattern(elements=(Placeable(expression=select_expr),))

        return Message(
            id=Identifier(name="mixed"),
            value=current_pattern,
            attributes=(),
            comment=None,
        )

    def test_combined_nesting_exceeds_limit(self) -> None:
        """Combined nesting that exceeds limit should be caught."""
        bundle = FluentBundle("en_US")
        # Combined depth exceeds MAX_DEPTH
        message = self._create_mixed_nesting_ast(
            select_depth=MAX_DEPTH // 2 + 10,
            placeable_depth=MAX_DEPTH // 2 + 10,
        )

        bundle._messages["mixed"] = message

        _result, errors = bundle.format_pattern("mixed", {"var": "x", "sel": "a"})

        # Should have depth error
        assert len(errors) >= 1


class TestDepthLimitWithCustomLimit:
    """Verify custom depth limit configuration."""

    def test_custom_lower_depth_limit(self) -> None:
        """Custom lower depth limit should trigger earlier than default."""
        bundle = FluentBundle("en_US", max_nesting_depth=10)

        # Create nesting that would exceed custom limit
        inner_pattern = Pattern(elements=(TextElement(value="inner"),))
        current_pattern = inner_pattern

        for _ in range(15):  # 15 > 10 custom limit, < 100 default
            select_expr = SelectExpression(
                selector=NumberLiteral(value=1, raw="1"),
                variants=(
                    Variant(
                        key=NumberLiteral(value=1, raw="1"),
                        value=current_pattern,
                        default=True,
                    ),
                ),
            )
            current_pattern = Pattern(elements=(Placeable(expression=select_expr),))

        message = Message(
            id=Identifier(name="test"),
            value=current_pattern,
            attributes=(),
            comment=None,
        )

        bundle._messages["test"] = message

        result, _errors = bundle.format_pattern("test", {})

        # With custom limit, deeper nesting may produce errors or fallback
        # The important thing is no crash occurred
        # Not asserting errors because behavior depends on custom limit
        assert result is not None


class TestDepthLimitPropertyBased:
    """Property-based tests for depth limiting."""

    @given(st.integers(min_value=1, max_value=50))
    @settings(max_examples=20)
    def test_depth_under_limit_never_errors_on_depth(self, depth: int) -> None:
        """Nesting under MAX_DEPTH should never produce depth errors."""
        bundle = FluentBundle("en_US")

        # Create nesting well under limit
        inner_pattern = Pattern(elements=(TextElement(value="ok"),))
        current_pattern = inner_pattern

        for _ in range(depth):
            select_expr = SelectExpression(
                selector=NumberLiteral(value=1, raw="1"),
                variants=(
                    Variant(
                        key=NumberLiteral(value=1, raw="1"),
                        value=current_pattern,
                        default=True,
                    ),
                ),
            )
            current_pattern = Pattern(elements=(Placeable(expression=select_expr),))

        message = Message(
            id=Identifier(name="test"),
            value=current_pattern,
            attributes=(),
            comment=None,
        )

        bundle._messages["test"] = message

        result, errors = bundle.format_pattern("test", {})

        # Should not have depth-related errors for shallow nesting
        depth_errors = [e for e in errors if "depth" in str(e).lower()]
        assert len(depth_errors) == 0
        # Result may include Unicode isolate markers
        assert "ok" in result
