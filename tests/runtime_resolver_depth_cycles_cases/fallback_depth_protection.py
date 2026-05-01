# mypy: ignore-errors
"""Split test cases from tests/test_runtime_resolver_depth_cycles.py."""

from tests.runtime_resolver_depth_cycles_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Fallback Depth Protection
# ============================================================================


class TestGetFallbackForPlaceableDepthProtection:
    """Coverage for depth protection in _get_fallback_for_placeable."""

    def _make_resolver(self) -> FluentResolver:
        return FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

    def test_fallback_depth_zero_returns_invalid(self) -> None:
        """Fallback with depth=0 returns FALLBACK_INVALID immediately."""
        resolver = self._make_resolver()
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("x")),
            variants=(
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="v"),)),
                    default=True,
                ),
            ),
        )

        result = resolver._get_fallback_for_placeable(select_expr, depth=0)

        assert result == FALLBACK_INVALID

    def test_fallback_negative_depth_returns_invalid(self) -> None:
        """Fallback with negative depth returns FALLBACK_INVALID."""
        resolver = self._make_resolver()

        result = resolver._get_fallback_for_placeable(
            VariableReference(id=Identifier("x")), depth=-1
        )

        assert result == FALLBACK_INVALID

    @given(depth=st.integers(max_value=0))
    def test_fallback_non_positive_depth_property(self, depth: int) -> None:
        """Property: Any non-positive depth returns FALLBACK_INVALID immediately."""
        event(f"depth={depth}")
        resolver = self._make_resolver()

        result = resolver._get_fallback_for_placeable(
            StringLiteral(value="test"), depth=depth
        )

        assert result == FALLBACK_INVALID

    def test_fallback_depth_one_processes_normally(self) -> None:
        """Fallback with depth=1 processes expression normally."""
        resolver = self._make_resolver()

        result = resolver._get_fallback_for_placeable(
            VariableReference(id=Identifier("count")), depth=1
        )

        assert result == "{$count}"

    def test_fallback_select_expression_depth_decremented(self) -> None:
        """SelectExpression fallback decrements depth for recursive call."""
        resolver = self._make_resolver()
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(
                Variant(
                    key=Identifier("x"),
                    value=Pattern(elements=(TextElement(value="variant"),)),
                    default=True,
                ),
            ),
        )

        # depth=1 → outer select processes, recursive selector call uses depth=0
        # which returns FALLBACK_INVALID; result should contain "{???} -> ..."
        result = resolver._get_fallback_for_placeable(select_expr, depth=1)

        assert FALLBACK_INVALID in result
        assert " -> ..." in result
