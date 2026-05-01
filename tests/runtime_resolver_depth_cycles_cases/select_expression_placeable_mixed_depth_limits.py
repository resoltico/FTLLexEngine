# mypy: ignore-errors
"""Split test cases from tests/test_runtime_resolver_depth_cycles.py."""

from tests.runtime_resolver_depth_cycles_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SelectExpression / Placeable / Mixed Depth Limits
# ============================================================================


class TestSelectExpressionDepthLimit:
    """Verify depth limiting for SelectExpression recursion through variants.

    Regression: SEC-RESOLVE-RECURSION-6.
    """

    def _create_nested_select_ast(self, depth: int) -> Message:
        """Create a Message with SelectExpression nested to specified depth."""
        inner_pattern = Pattern(elements=(TextElement(value="innermost"),))
        current_pattern = inner_pattern

        for _ in range(depth):
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
            current_pattern = Pattern(elements=(Placeable(expression=select_expr),))

        return Message(
            id=Identifier(name="nested"),
            value=current_pattern,
            attributes=(),
            comment=None,
        )

    def test_shallow_nesting_resolves_successfully(self) -> None:
        """SelectExpression with shallow nesting resolves normally."""
        bundle = FluentBundle("en_US")
        message = self._create_nested_select_ast(depth=5)
        bundle._messages["nested"] = message

        result, errors = bundle.format_pattern("nested", {"var": "one"})

        assert "innermost" in result
        assert errors == ()

    def test_deep_nesting_triggers_depth_limit(self) -> None:
        """SelectExpression nested beyond MAX_DEPTH triggers depth limit."""
        bundle = FluentBundle("en_US", strict=False)
        message = self._create_nested_select_ast(depth=MAX_DEPTH + 10)
        bundle._messages["nested"] = message

        _result, errors = bundle.format_pattern("nested", {"var": "one"})

        assert len(errors) >= 1
        error_messages = [str(e) for e in errors]
        assert any("depth" in msg.lower() for msg in error_messages)

    def test_exact_max_depth_boundary(self) -> None:
        """Behavior at exactly MAX_DEPTH does not crash."""
        bundle = FluentBundle("en_US", strict=False)
        message = self._create_nested_select_ast(depth=MAX_DEPTH)
        bundle._messages["nested"] = message

        result, _errors = bundle.format_pattern("nested", {"var": "one"})

        assert result is not None

    def test_just_under_max_depth(self) -> None:
        """Nesting just under MAX_DEPTH produces no depth errors."""
        bundle = FluentBundle("en_US")
        message = self._create_nested_select_ast(depth=MAX_DEPTH - 5)
        bundle._messages["nested"] = message

        _result, errors = bundle.format_pattern("nested", {"var": "one"})

        depth_errors = [e for e in errors if "depth" in str(e).lower()]
        assert len(depth_errors) == 0


class TestNestedPlaceableDepthLimit:
    """Verify depth limiting for nested Placeables like { { { x } } }."""

    def _create_nested_placeable_ast(self, depth: int) -> Message:
        """Create a Message with Placeables nested to specified depth."""
        inner_expr: InlineExpression = VariableReference(id=Identifier(name="var"))
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
        """Shallow placeable nesting resolves normally."""
        bundle = FluentBundle("en_US")
        message = self._create_nested_placeable_ast(depth=5)
        bundle._messages["nested"] = message

        result, errors = bundle.format_pattern("nested", {"var": "hello"})

        assert "hello" in result
        assert errors == ()

    def test_deep_placeable_nesting_triggers_limit(self) -> None:
        """Deep placeable nesting triggers depth limit."""
        bundle = FluentBundle("en_US", strict=False)
        message = self._create_nested_placeable_ast(depth=MAX_DEPTH + 10)
        bundle._messages["nested"] = message

        _result, errors = bundle.format_pattern("nested", {"var": "hello"})

        assert len(errors) >= 1


class TestMixedNestingDepthLimit:
    """Verify depth limiting for mixed SelectExpression and Placeable nesting."""

    def _create_mixed_nesting_ast(self, select_depth: int, placeable_depth: int) -> Message:
        """Create a Message mixing SelectExpression and Placeable nesting."""
        inner_expr: InlineExpression = VariableReference(id=Identifier(name="var"))
        current_expr: InlineExpression = inner_expr

        for _ in range(placeable_depth):
            current_expr = Placeable(expression=current_expr)

        current_pattern = Pattern(elements=(Placeable(expression=current_expr),))

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
        """Combined nesting exceeding MAX_DEPTH produces depth error."""
        bundle = FluentBundle("en_US", strict=False)
        message = self._create_mixed_nesting_ast(
            select_depth=MAX_DEPTH // 2 + 10,
            placeable_depth=MAX_DEPTH // 2 + 10,
        )
        bundle._messages["mixed"] = message

        _result, errors = bundle.format_pattern("mixed", {"var": "x", "sel": "a"})

        assert len(errors) >= 1


class TestDepthLimitWithCustomLimit:
    """Verify custom depth limit configuration."""

    def test_custom_lower_depth_limit(self) -> None:
        """Custom lower depth limit triggers earlier than default."""
        bundle = FluentBundle("en_US", max_nesting_depth=10, strict=False)

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

        assert result is not None


class TestDepthLimitPropertyBased:
    """Property-based tests for depth limiting."""

    @given(st.integers(min_value=1, max_value=50))
    @settings(max_examples=20)
    def test_depth_under_limit_never_errors_on_depth(self, depth: int) -> None:
        """Nesting under MAX_DEPTH produces no depth errors."""
        event(f"depth={depth}")
        bundle = FluentBundle("en_US")

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

        depth_errors = [e for e in errors if "depth" in str(e).lower()]
        assert len(depth_errors) == 0
        assert "ok" in result
