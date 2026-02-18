"""Resolver expansion budget coverage tests.

Targets specific code paths for 100% coverage of expansion budget DoS protection
in resolver.py. Tests the three expansion budget enforcement points:

1. ResolutionContext.track_expansion() raising exception (lines 239-242)
2. Pattern loop early-exit check (lines 444-450)
3. Placeable exception handler break on expansion budget error (lines 484-485)

These tests complement test_security_expansion_budget.py by directly testing
resolver-level behavior rather than going through FluentBundle.
"""

from __future__ import annotations

import sys

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

sys.path.insert(0, "src")

from ftllexengine.diagnostics import DiagnosticCode, ErrorCategory, FrozenFluentError
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolution_context import ResolutionContext
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax import (
    CallArguments,
    FunctionReference,
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


class TestResolutionContextTrackExpansion:
    """Direct tests for ResolutionContext.track_expansion() exception path.

    Targets lines 239-242 in resolver.py where track_expansion() raises
    FrozenFluentError when budget is exceeded.
    """

    def test_track_expansion_raises_when_budget_exceeded(self) -> None:
        """track_expansion() raises FrozenFluentError when budget exceeded."""
        context = ResolutionContext(max_expansion_size=100)

        # Fill budget to just under limit
        context.track_expansion(99)
        assert context.total_chars == 99

        # Exceed budget with next call
        with pytest.raises(FrozenFluentError) as exc_info:  # FrozenFluentError
            context.track_expansion(2)

        # Verify error structure
        error = exc_info.value
        assert error.category == ErrorCategory.RESOLUTION
        assert error.diagnostic is not None
        assert error.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED

    def test_track_expansion_exact_budget_limit_allowed(self) -> None:
        """track_expansion() allows reaching exact budget limit."""
        context = ResolutionContext(max_expansion_size=100)

        # Reach exact limit
        context.track_expansion(100)
        assert context.total_chars == 100

        # Next character exceeds
        with pytest.raises(FrozenFluentError) as exc_info:  # FrozenFluentError
            context.track_expansion(1)

        error = exc_info.value
        assert error.diagnostic is not None
        assert error.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED

    @given(
        budget=st.integers(min_value=1, max_value=1000),
        first_chunk=st.integers(min_value=0, max_value=500),
    )
    @settings(max_examples=50)
    def test_track_expansion_property_never_exceeds_without_error(
        self, budget: int, first_chunk: int
    ) -> None:
        """Property: track_expansion() never allows exceeding budget silently.

        Events emitted:
        - boundary=under_budget: First chunk fits within budget
        - boundary=at_or_over_budget: First chunk at or over budget
        - error_path=budget_exceeded: Exception raised as expected
        """
        context = ResolutionContext(max_expansion_size=budget)

        if first_chunk <= budget:
            event("boundary=under_budget")
            context.track_expansion(first_chunk)
            # Verify internal state
            assert context.total_chars == first_chunk

            # Try to exceed
            excess = budget - first_chunk + 1
            if excess > 0:
                with pytest.raises(FrozenFluentError):  # FrozenFluentError
                    context.track_expansion(excess)
                event("error_path=budget_exceeded")
        else:
            event("boundary=at_or_over_budget")
            # First chunk already exceeds budget
            with pytest.raises(FrozenFluentError):  # FrozenFluentError
                context.track_expansion(first_chunk)
            event("error_path=budget_exceeded")


class TestPatternLoopEarlyExit:
    """Tests for pattern loop early-exit when budget exceeded (lines 444-450).

    The pattern loop checks context.total_chars BEFORE processing each element.
    This catches the case where budget was exceeded during previous element
    processing but the error wasn't raised (e.g., the element itself didn't
    call track_expansion).
    """

    def test_pattern_loop_defensive_check_with_context_over_budget(self) -> None:
        """Pattern loop defensive check triggers when total_chars > budget.

        Tests the defensive check that guards against total_chars exceeding
        the budget without raising an exception. Belt-and-suspenders check
        that ensures robustness.
        """
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

        # Create a custom context with _total_chars already over budget
        # This simulates a scenario where budget was exceeded elsewhere
        context = ResolutionContext(max_expansion_size=50)
        context._total_chars = 60  # Directly set over budget to trigger defensive check

        # Use resolve_message with the manipulated context
        # The pattern loop should detect budget exceeded and break immediately
        result, errors = resolver.resolve_message(message, args={}, context=context)

        # Verify the defensive check triggered
        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_budget_error

        # Result should be empty (no elements processed)
        assert len(result) == 0 or result == "{test}"  # Fallback message ID

    def test_pattern_loop_exits_when_budget_already_exceeded(self) -> None:
        """Pattern loop exits early if budget already exceeded before next element.

        Tests the pattern loop check where it inspects context.total_chars
        before processing the next element.
        """
        # Create a pattern with multiple text elements
        pattern = Pattern(
            elements=(
                TextElement(value="A" * 50),  # First element: 50 chars
                TextElement(value="B" * 50),  # Second element: 50 chars
                TextElement(value="C" * 50),  # Third element: won't be processed
            )
        )

        # Create message with this pattern
        message = Message(id=Identifier(name="test"), value=pattern, attributes=())

        # Create resolver with very small expansion budget
        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={"test": message},
            terms={},
            function_registry=registry,
            max_expansion_size=75,  # Budget: only enough for first 2 elements
        )

        result, errors = resolver.resolve_message(message, args={})

        # Verify early exit occurred
        # Result should contain only first element (50 A's) before budget exceeded
        # The second element causes budget to be exceeded during its processing
        assert len(errors) > 0
        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_budget_error

        # Result is partial - not all elements processed
        assert "C" not in result  # Third element never processed

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

        # Budget exactly matches first element
        resolver = FluentResolver(
            locale="en_US",
            messages={"boundary": message},
            terms={},
            function_registry=registry,
            max_expansion_size=10,
        )

        _result, errors = resolver.resolve_message(message, args={})

        # First element (10 X's) fills budget exactly
        # Loop check before second element detects budget exceeded
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
        """Property: Pattern loop always exits when budget exceeded.

        Events emitted:
        - element_count={n}: Number of text elements in pattern
        - budget_scenario=exceeded: Budget set to trigger early exit
        - error_path=early_exit_detected: Early exit occurred as expected
        """
        event(f"element_count={element_count}")

        # Create pattern with multiple text elements
        elements = tuple(
            TextElement(value=f"{chr(65 + i)}" * chars_per_element)
            for i in range(element_count)
        )
        pattern = Pattern(elements=elements)
        message = Message(id=Identifier(name="prop"), value=pattern, attributes=())

        # Set budget to allow only half the elements
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

        # Verify error was collected
        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )

        if has_budget_error:
            event("error_path=early_exit_detected")
            # Result should be partial
            assert len(result) < total_chars
            event("result_type=partial")


class TestPlaceableExpansionBudgetBreak:
    """Tests for Placeable exception handler break (lines 484-485).

    When a Placeable raises an expansion budget error during resolution,
    the exception handler must detect this specific error type and break
    the pattern loop (rather than just collecting the error and continuing).
    """

    def test_placeable_expansion_budget_breaks_pattern_loop(self) -> None:
        """Expansion budget error from Placeable breaks pattern resolution.

        This tests lines 484-485 where the exception handler checks for
        DiagnosticCode.EXPANSION_BUDGET_EXCEEDED and breaks the loop.
        """
        # Create a message reference that will cause expansion budget exceeded
        # when resolved as a Placeable
        inner_pattern = Pattern(elements=(TextElement(value="X" * 100),))
        inner_message = Message(
            id=Identifier(name="inner"), value=inner_pattern, attributes=()
        )

        # Outer pattern has Placeable that references inner message
        outer_pattern = Pattern(
            elements=(
                TextElement(value="Before"),
                Placeable(
                    expression=VariableReference(id=Identifier(name="big_value"))
                ),
                TextElement(value="After"),  # Should not be processed
            )
        )
        outer_message = Message(
            id=Identifier(name="outer"), value=outer_pattern, attributes=()
        )

        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={"outer": outer_message, "inner": inner_message},
            terms={},
            function_registry=registry,
            max_expansion_size=50,  # Budget exceeded by variable expansion
        )

        # Provide a very long string as variable value
        result, errors = resolver.resolve_message(
            outer_message, args={"big_value": "Z" * 100}
        )

        # Verify expansion budget error was collected
        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_budget_error

        # Verify "After" text was not appended (loop broke)
        assert "After" not in result

    def test_placeable_budget_error_via_select_expression(self) -> None:
        """Expansion budget error from SelectExpression in Placeable breaks loop."""
        # Create a select expression with large variant values
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
                TextElement(value="End"),  # Should not be processed
            )
        )
        message = Message(id=Identifier(name="select"), value=pattern, attributes=())

        registry = FunctionRegistry()
        resolver = FluentResolver(
            locale="en_US",
            messages={"select": message},
            terms={},
            function_registry=registry,
            max_expansion_size=40,  # "Start" (5) + "A"*60 exceeds budget
        )

        result, errors = resolver.resolve_message(message, args={"count": 1})

        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_budget_error

        # "End" should not appear (loop broke after Placeable error)
        assert "End" not in result

    def test_placeable_budget_error_via_function_call(self) -> None:
        """Expansion budget error from function result in Placeable breaks loop."""

        # Register a custom function that returns a large string
        def large_output() -> str:
            return "LARGE" * 100

        registry = FunctionRegistry()
        registry.register(large_output, ftl_name="BIGFUNC")

        # Pattern with function call Placeable
        func_call = FunctionReference(
            id=Identifier(name="BIGFUNC"),
            arguments=CallArguments(positional=(), named=()),
        )
        pattern = Pattern(
            elements=(
                TextElement(value="Prefix"),
                Placeable(expression=func_call),
                TextElement(value="Suffix"),  # Should not be processed
            )
        )
        message = Message(id=Identifier(name="func"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en_US",
            messages={"func": message},
            terms={},
            function_registry=registry,
            max_expansion_size=100,  # Exceeded by function output
        )

        result, errors = resolver.resolve_message(message, args={})

        has_budget_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_budget_error

        # "Suffix" should not appear (loop broke)
        assert "Suffix" not in result

    @given(
        variant_size=st.integers(min_value=50, max_value=200),
        budget=st.integers(min_value=10, max_value=100),
    )
    @settings(max_examples=30)
    def test_placeable_budget_break_property(
        self, variant_size: int, budget: int
    ) -> None:
        """Property: Placeable budget errors always break pattern loop.

        Events emitted:
        - variant_size={n}: Size of variant value
        - budget={n}: Expansion budget
        - error_path=budget_break: Break occurred as expected
        """
        event(f"variant_size={variant_size}")
        event(f"budget={budget}")

        if variant_size <= budget:
            # Skip cases where variant fits in budget
            event("skip=variant_fits_budget")
            return

        # Create select with large variant
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
                TextElement(value="Marker"),  # Should not appear
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
            # "Marker" should not appear in result
            assert "Marker" not in result
            event("result_type=partial")


class TestExpansionBudgetIntegration:
    """Integration tests for expansion budget across resolver components."""

    def test_expansion_budget_with_isolating_marks(self) -> None:
        """Expansion budget accounts for Unicode isolating marks."""
        # FSI + content + PDI = 3 extra characters per placeable
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
            use_isolating=True,  # Adds FSI/PDI marks
            max_expansion_size=15,
        )

        # Each variable: 5 chars content + 2 chars marks (FSI + PDI) = 7 chars
        # Total: 14 chars (just under budget of 15)
        _result, errors = resolver.resolve_message(
            message, args={"v1": "AAAAA", "v2": "BBBBB"}
        )

        # Should succeed (14 <= 15)
        assert len(errors) == 0

        # Now exceed budget with 8 char values
        _result2, errors2 = resolver.resolve_message(
            message,
            args={
                "v1": "AAAAAAAA",  # 8 chars + 2 marks = 10
                "v2": "BBBBBBBB",  # 8 chars + 2 marks = 10, total = 20 > 15
            },
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
            if e.diagnostic
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
        )

        # Verify diagnostic contains useful information
        assert budget_error.diagnostic is not None
        diagnostic_str = str(budget_error.diagnostic)
        assert "50" in diagnostic_str  # Budget limit
        assert "100" in diagnostic_str or "exceeded" in diagnostic_str.lower()
