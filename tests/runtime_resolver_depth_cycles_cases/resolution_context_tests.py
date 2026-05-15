# mypy: ignore-errors
"""Split test cases from tests/test_runtime_resolver_depth_cycles.py."""

from tests.runtime_resolver_depth_cycles_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# ResolutionContext Tests
# ============================================================================


class TestResolutionContext:
    """Tests for ResolutionContext cycle detection."""

    def test_push_pop_balance(self) -> None:
        """Context push/pop maintains balanced state."""
        ctx = ResolutionContext()

        ctx.push("a")
        ctx.push("b")
        ctx.push("c")

        assert ctx.depth == 3
        assert ctx.contains("a")
        assert ctx.contains("b")
        assert ctx.contains("c")

        assert ctx.pop() == "c"
        assert ctx.pop() == "b"
        assert ctx.pop() == "a"

        assert ctx.depth == 0
        assert not ctx.contains("a")

    def test_cycle_detection_o1(self) -> None:
        """Cycle detection is O(1) via set."""
        ctx = ResolutionContext()

        for i in range(100):
            ctx.push(f"msg{i}")

        assert ctx.contains("msg0")
        assert ctx.contains("msg50")
        assert ctx.contains("msg99")
        assert not ctx.contains("msg100")

    def test_get_cycle_path(self) -> None:
        """Cycle path includes full resolution stack."""
        ctx = ResolutionContext()

        ctx.push("a")
        ctx.push("b")
        ctx.push("c")

        path = ctx.get_cycle_path("a")

        assert path == ["a", "b", "c", "a"]


class TestResolutionContextExpressionDepth:
    """Test ResolutionContext.expression_depth property."""

    def test_expression_depth_property_initial(self) -> None:
        """expression_depth property returns 0 initially."""
        context = ResolutionContext()

        assert context.expression_depth == 0

    def test_expression_depth_property_after_increment(self) -> None:
        """expression_depth property reflects guard depth after increment."""
        context = ResolutionContext()

        with context.expression_guard:
            assert context.expression_depth == 1
            with context.expression_guard:
                assert context.expression_depth == 2

        assert context.expression_depth == 0

    def test_noncacheable_functions_property_returns_frozen_snapshot(self) -> None:
        """noncacheable_functions exposes the observed function names immutably."""
        context = ResolutionContext()

        context.mark_noncacheable_function("NOW")

        assert context.cacheable_output is False
        assert context.noncacheable_functions == frozenset({"NOW"})


class TestResolutionContextOutputBudget:
    """Direct tests for ResolutionContext.reserve_output().

    Premise:
        The output-budget owner must see the exact rendered fragment before it
        becomes visible to the caller.

    Reason:
        A fail-closed reserve step prevents undercount gaps for isolation marks,
        fallbacks, and nested pattern output.
    """

    def test_reserve_output_accumulates_within_budget(self) -> None:
        """reserve_output() updates total_chars for admitted fragments."""
        context = ResolutionContext(max_expansion_size=100)

        context.reserve_output("x" * 99)
        assert context.total_chars == 99
        assert context.total_chars <= context.max_expansion_size

        context.reserve_output("y")
        assert context.total_chars == 100
        assert context.total_chars == context.max_expansion_size

    def test_reserve_output_rejects_fragment_that_crosses_budget(self) -> None:
        """reserve_output() raises before admitting an over-budget fragment."""
        context = ResolutionContext(max_expansion_size=100)

        context.reserve_output("x" * 100)
        assert context.total_chars == 100

        with pytest.raises(FrozenFluentError) as exc_info:
            context.reserve_output("y")

        assert context.total_chars == 100
        assert exc_info.value.diagnostic is not None
        assert exc_info.value.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED

    @given(
        budget=st.integers(min_value=1, max_value=1000),
        first_chunk=st.integers(min_value=0, max_value=500),
    )
    @settings(max_examples=50)
    def test_reserve_output_preserves_exact_running_total(
        self, budget: int, first_chunk: int
    ) -> None:
        """Property: admitted output updates the running total exactly."""
        context = ResolutionContext(max_expansion_size=budget)

        if first_chunk > budget:
            with pytest.raises(FrozenFluentError):
                context.reserve_output("a" * first_chunk)
            assert context.total_chars == 0
            event("boundary=initial_reject")
            return

        context.reserve_output("a" * first_chunk)
        assert context.total_chars == first_chunk

        hits_boundary = first_chunk == budget
        event("boundary=exact_budget" if hits_boundary else "boundary=under_budget")

        second_chunk = budget - first_chunk + 1
        if second_chunk > 0:
            with pytest.raises(FrozenFluentError):
                context.reserve_output("b" * second_chunk)
            assert context.total_chars == first_chunk
            event("error_path=budget_exceeded")
