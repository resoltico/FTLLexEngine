# mypy: ignore-errors
"""Split test cases from tests/test_runtime_resolver_depth_cycles.py."""

from tests.runtime_resolver_depth_cycles_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Pattern Loop Expansion Budget
# ============================================================================


class TestPatternLoopEarlyExit:
    """Tests for pattern loop early-exit when budget exceeded."""

    def test_pattern_loop_defensive_check_with_context_over_budget(self) -> None:
        """Pattern loop defensive check triggers when total_chars > budget."""
        pattern = Pattern(
            elements=(
                TextElement(value="A" * 10),
                TextElement(value="B" * 10),
            )
        )
        message = Message(id=Identifier(name="test"), value=pattern, attributes=())
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={"test": message},
            terms={},
            function_registry=registry,
            max_expansion_size=50,
        )

        context = ResolutionContext(max_expansion_size=50)
        context._total_chars = 60  # Simulate budget already exceeded

        result, errors = resolver.resolve_message(message, args={}, context=context)

        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_budget_error
        assert len(result) == 0 or result == "{test}"

    def test_pattern_loop_exits_when_budget_already_exceeded(self) -> None:
        """Pattern loop exits early if budget exceeded before next element."""
        pattern = Pattern(
            elements=(
                TextElement(value="A" * 50),
                TextElement(value="B" * 50),
                TextElement(value="C" * 50),
            )
        )
        message = Message(id=Identifier(name="test"), value=pattern, attributes=())
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={"test": message},
            terms={},
            function_registry=registry,
            max_expansion_size=75,
        )

        result, errors = resolver.resolve_message(message, args={})

        assert len(errors) > 0
        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_budget_error
        assert "C" not in result

    def test_pattern_loop_early_exit_on_boundary(self) -> None:
        """Pattern loop exits when total_chars exactly equals budget."""
        pattern = Pattern(
            elements=(
                TextElement(value="X" * 10),
                TextElement(value="Y" * 10),
            )
        )
        message = Message(id=Identifier(name="boundary"), value=pattern, attributes=())
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={"boundary": message},
            terms={},
            function_registry=registry,
            max_expansion_size=10,
        )

        _result, errors = resolver.resolve_message(message, args={})

        assert len(errors) > 0
        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_budget_error

    @given(
        element_count=st.integers(min_value=2, max_value=10),
        chars_per_element=st.integers(min_value=5, max_value=20),
    )
    @settings(max_examples=50)
    def test_pattern_loop_early_exit_property(
        self, element_count: int, chars_per_element: int
    ) -> None:
        """Property: Pattern loop always exits when budget exceeded."""
        event(f"element_count={element_count}")

        elements = tuple(
            TextElement(value=f"{chr(65 + i)}" * chars_per_element)
            for i in range(element_count)
        )
        pattern = Pattern(elements=elements)
        message = Message(id=Identifier(name="prop"), value=pattern, attributes=())

        total_chars = element_count * chars_per_element
        budget = total_chars // 2

        event("budget_scenario=exceeded")
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={"prop": message},
            terms={},
            function_registry=registry,
            max_expansion_size=budget,
        )

        result, errors = resolver.resolve_message(message, args={})

        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        if has_budget_error:
            event("error_path=early_exit_detected")
            assert len(result) < total_chars
            event("result_type=partial")
