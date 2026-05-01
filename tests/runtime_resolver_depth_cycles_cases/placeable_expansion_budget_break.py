# mypy: ignore-errors
"""Split test cases from tests/test_runtime_resolver_depth_cycles.py."""

from tests.runtime_resolver_depth_cycles_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Placeable Expansion Budget Break
# ============================================================================


class TestPlaceableExpansionBudgetBreak:
    """Tests for Placeable exception handler break on expansion budget error."""

    def test_placeable_expansion_budget_breaks_pattern_loop(self) -> None:
        """Expansion budget error from Placeable breaks pattern resolution."""
        outer_pattern = Pattern(
            elements=(
                TextElement(value="Before"),
                Placeable(
                    expression=VariableReference(id=Identifier(name="big_value"))
                ),
                TextElement(value="After"),  # Must not be processed.
            )
        )
        outer_message = Message(
            id=Identifier(name="outer"), value=outer_pattern, attributes=()
        )
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={"outer": outer_message},
            terms={},
            function_registry=registry,
            max_expansion_size=50,
        )

        result, errors = resolver.resolve_message(
            outer_message, args={"big_value": "Z" * 100}
        )

        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_budget_error
        assert "After" not in result

    def test_placeable_budget_error_via_select_expression(self) -> None:
        """Expansion budget error from SelectExpression in Placeable breaks loop."""
        variants = (
            Variant(
                key=NumberLiteral(value=1, raw="1"),
                value=Pattern(elements=(TextElement(value="A" * 60),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")), variants=variants
        )
        pattern = Pattern(
            elements=(
                TextElement(value="Start"),
                Placeable(expression=select_expr),
                TextElement(value="End"),  # Must not be processed.
            )
        )
        message = Message(id=Identifier(name="select"), value=pattern, attributes=())
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={"select": message},
            terms={},
            function_registry=registry,
            max_expansion_size=40,
        )

        result, errors = resolver.resolve_message(message, args={"count": 1})

        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_budget_error
        assert "End" not in result

    def test_placeable_budget_error_via_function_call(self) -> None:
        """Expansion budget error from function result in Placeable breaks loop."""
        def large_output() -> str:
            return "LARGE" * 100

        registry = FunctionRegistry()
        registry.register(large_output, ftl_name="BIGFUNC")

        func_call = FunctionReference(
            id=Identifier(name="BIGFUNC"),
            arguments=CallArguments(positional=(), named=()),
        )
        pattern = Pattern(
            elements=(
                TextElement(value="Prefix"),
                Placeable(expression=func_call),
                TextElement(value="Suffix"),  # Must not be processed.
            )
        )
        message = Message(id=Identifier(name="func"), value=pattern, attributes=())
        resolver = FluentResolver(
            locale="en_US",
            messages={"func": message},
            terms={},
            function_registry=registry,
            max_expansion_size=100,
        )

        result, errors = resolver.resolve_message(message, args={})

        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_budget_error
        assert "Suffix" not in result

    @given(
        variant_size=st.integers(min_value=50, max_value=200),
        budget=st.integers(min_value=10, max_value=100),
    )
    @settings(max_examples=30)
    def test_placeable_budget_break_property(
        self, variant_size: int, budget: int
    ) -> None:
        """Property: Placeable budget errors always break pattern loop."""
        event(f"variant_size={variant_size}")
        event(f"budget={budget}")

        if variant_size <= budget:
            event("skip=variant_fits_budget")
            return

        variants = (
            Variant(
                key=Identifier(name="key"),
                value=Pattern(elements=(TextElement(value="X" * variant_size),)),
                default=True,
            ),
        )
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="var")), variants=variants
        )
        pattern = Pattern(
            elements=(
                Placeable(expression=select),
                TextElement(value="Marker"),  # Must not appear.
            )
        )
        message = Message(id=Identifier(name="test"), value=pattern, attributes=())
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={"test": message},
            terms={},
            function_registry=registry,
            max_expansion_size=budget,
        )

        result, errors = resolver.resolve_message(message, args={"var": "key"})

        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        if has_budget_error:
            event("error_path=budget_break")
            assert "Marker" not in result
            event("result_type=partial")


class TestExpansionBudgetIntegration:
    """Integration tests for expansion budget across resolver components."""

    def test_expansion_budget_with_isolating_marks(self) -> None:
        """Expansion budget accounts for Unicode isolating marks."""
        pattern = Pattern(
            elements=(
                Placeable(expression=VariableReference(id=Identifier(name="v1"))),
                Placeable(expression=VariableReference(id=Identifier(name="v2"))),
            )
        )
        message = Message(id=Identifier(name="iso"), value=pattern, attributes=())
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={"iso": message},
            terms={},
            function_registry=registry,
            use_isolating=True,
            max_expansion_size=15,
        )

        # Each variable: 5 chars content + 2 chars marks (FSI + PDI) = 7 chars
        # Total: 14 chars (just under budget of 15)
        _result, errors = resolver.resolve_message(
            message, args={"v1": "AAAAA", "v2": "BBBBB"}
        )
        assert len(errors) == 0

        # 8-char values: 10 + 10 = 20 > 15
        _result2, errors2 = resolver.resolve_message(
            message,
            args={"v1": "AAAAAAAA", "v2": "BBBBBBBB"},
        )
        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors2
        )
        assert has_budget_error

    def test_expansion_budget_error_diagnostic_includes_counts(self) -> None:
        """Expansion budget error diagnostic includes actual and limit values."""
        pattern = Pattern(elements=(TextElement(value="X" * 100),))
        message = Message(id=Identifier(name="err"), value=pattern, attributes=())
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={"err": message},
            terms={},
            function_registry=registry,
            max_expansion_size=50,
        )

        _result, errors = resolver.resolve_message(message, args={})

        assert len(errors) > 0
        budget_error = next(
            e
            for e in errors
            if e.diagnostic and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
        )
        assert budget_error.diagnostic is not None
        diagnostic_str = str(budget_error.diagnostic)
        assert "50" in diagnostic_str
        assert "100" in diagnostic_str or "exceeded" in diagnostic_str.lower()
