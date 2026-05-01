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


class TestResolutionContextTrackExpansion:
    """Direct tests for ResolutionContext.track_expansion() accumulation.

    Targets the expansion budget DoS protection: track_expansion() accumulates
    character counts without raising. Callers check
    ``total_chars > max_expansion_size`` after each call and generate
    FrozenFluentError themselves (separation of state tracking from error policy).
    """

    def test_track_expansion_accumulates_correctly(self) -> None:
        """track_expansion() accumulates total_chars without raising."""
        context = ResolutionContext(max_expansion_size=100)

        context.track_expansion(99)
        assert context.total_chars == 99
        assert context.total_chars <= context.max_expansion_size

        # Exceeding budget is detectable by caller; no exception raised here
        context.track_expansion(2)
        assert context.total_chars == 101
        assert context.total_chars > context.max_expansion_size

    def test_track_expansion_exact_budget_limit_detectable(self) -> None:
        """Exact budget limit is detectable by caller after track_expansion."""
        context = ResolutionContext(max_expansion_size=100)

        context.track_expansion(100)
        assert context.total_chars == 100
        # At exactly the budget: caller may allow or deny based on policy
        assert context.total_chars <= context.max_expansion_size

        # One more char pushes over the limit — caller detects via comparison
        context.track_expansion(1)
        assert context.total_chars == 101
        assert context.total_chars > context.max_expansion_size

    @given(
        budget=st.integers(min_value=1, max_value=1000),
        first_chunk=st.integers(min_value=0, max_value=500),
    )
    @settings(max_examples=50)
    def test_track_expansion_accumulates_accurately(
        self, budget: int, first_chunk: int
    ) -> None:
        """Property: track_expansion() always accumulates total_chars precisely.

        For any budget and chunk sizes, total_chars must equal the exact sum of
        all chunk arguments passed. The caller detects budget exhaustion via
        ``total_chars > max_expansion_size``.
        """
        context = ResolutionContext(max_expansion_size=budget)

        context.track_expansion(first_chunk)
        assert context.total_chars == first_chunk

        over_budget = first_chunk > budget
        event("boundary=at_or_over_budget" if over_budget else "boundary=under_budget")

        # Add one more chunk that guarantees budget is exceeded
        second_chunk = budget - first_chunk + 1
        if second_chunk > 0:
            context.track_expansion(second_chunk)
            assert context.total_chars == first_chunk + second_chunk
            assert context.total_chars > context.max_expansion_size
            event("error_path=budget_exceeded")
