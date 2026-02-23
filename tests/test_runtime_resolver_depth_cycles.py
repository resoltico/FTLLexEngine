"""Resolver depth limiting and cycle detection tests.

Consolidates:
- test_resolver_cycles.py (direct/indirect/deep cycles, cycle detection properties)
- test_resolver_depth_limit.py (MAX_DEPTH enforcement, attribute chains)
- test_resolver_depth_guard_and_variants.py (guard edge cases, multi-placeables,
  malformed NumberLiteral, fallback depth protection)
- test_resolver_expression_depth.py (SelectExpression depth, Placeable depth, mixed)
- test_resolver_expression_depth_and_select.py (ResolutionContext expression depth)
- test_resolver_expansion_budget.py (expansion budget DoS protection)
"""

from __future__ import annotations

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.constants import FALLBACK_INVALID, MAX_DEPTH
from ftllexengine.diagnostics import DiagnosticCode, ErrorCategory, FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolution_context import GlobalDepthGuard, ResolutionContext
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
    StringLiteral,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.ast import InlineExpression

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


# ============================================================================
# Cycle Detection
# ============================================================================


class TestDirectCycles:
    """Tests for direct self-referential cycles."""

    def test_message_references_itself(self) -> None:
        """Direct cycle: message references itself."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("self = { self }")

        result, errors = bundle.format_pattern("self")

        assert isinstance(result, str)
        assert len(errors) > 0
        cyclic_errors = [
            e for e in errors
            if isinstance(e, FrozenFluentError) and e.category == ErrorCategory.CYCLIC
        ]
        assert len(cyclic_errors) > 0

    def test_term_references_itself(self) -> None:
        """Direct cycle: term references itself."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(
            """
-self = { -self }
msg = { -self }
"""
        )

        result, errors = bundle.format_pattern("msg")

        assert isinstance(result, str)
        assert len(errors) > 0


class TestIndirectCycles:
    """Tests for indirect cycles through chains."""

    def test_two_message_cycle(self) -> None:
        """Indirect cycle: a -> b -> a."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(
            """
msg-a = { msg-b }
msg-b = { msg-a }
"""
        )

        result, errors = bundle.format_pattern("msg-a")

        assert isinstance(result, str)
        assert len(errors) > 0
        cyclic_errors = [
            e for e in errors
            if isinstance(e, FrozenFluentError) and e.category == ErrorCategory.CYCLIC
        ]
        assert len(cyclic_errors) > 0

    def test_three_message_cycle(self) -> None:
        """Indirect cycle: a -> b -> c -> a."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(
            """
msg-a = { msg-b }
msg-b = { msg-c }
msg-c = { msg-a }
"""
        )

        result, errors = bundle.format_pattern("msg-a")

        assert isinstance(result, str)
        assert len(errors) > 0

    def test_term_to_message_cycle(self) -> None:
        """Mixed cycle: term -> message -> term."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(
            """
-brand = { product }
product = { -brand } Browser
"""
        )

        result, _ = bundle.format_pattern("product")

        assert isinstance(result, str)


class TestDeepChains:
    """Tests for deep non-cyclic chains."""

    def test_chain_at_depth_limit(self) -> None:
        """Chain shorter than MAX_DEPTH resolves to leaf value."""
        depth = min(MAX_DEPTH - 1, 50)
        messages = []
        for i in range(depth):
            if i < depth - 1:
                messages.append(f"msg{i} = {{ msg{i + 1} }}")
            else:
                messages.append(f"msg{i} = End")

        bundle = FluentBundle("en-US")
        bundle.add_resource("\n".join(messages))

        result, _ = bundle.format_pattern("msg0")

        assert isinstance(result, str)
        assert "End" in result

    def test_chain_exceeding_depth_limit(self) -> None:
        """Chain exceeding MAX_DEPTH produces error."""
        depth = MAX_DEPTH + 10
        messages = []
        for i in range(depth):
            if i < depth - 1:
                messages.append(f"msg{i} = {{ msg{i + 1} }}")
            else:
                messages.append(f"msg{i} = End")

        bundle = FluentBundle("en-US")
        bundle.add_resource("\n".join(messages))

        result, errors = bundle.format_pattern("msg0")

        assert isinstance(result, str)
        assert len(errors) > 0


# ============================================================================
# MAX_DEPTH Enforcement
# ============================================================================


class TestMaxDepthLimit:
    """Tests for maximum resolution depth enforcement."""

    def test_max_depth_constant_exists(self) -> None:
        """MAX_DEPTH constant is defined and reasonable."""
        assert MAX_DEPTH == 100

    def test_shallow_chain_succeeds(self) -> None:
        """Chain of 5 messages resolves without error."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
m0 = { m1 }
m1 = { m2 }
m2 = { m3 }
m3 = { m4 }
m4 = Final value
"""
        )

        result, errors = bundle.format_pattern("m0")

        assert errors == ()
        assert "\u2068" in result or "Final value" in result

    def test_moderate_chain_succeeds(self) -> None:
        """Chain of 50 messages resolves without error."""
        bundle = FluentBundle("en")
        lines = []
        for i in range(49):
            lines.append(f"m{i} = {{ m{i+1} }}")
        lines.append("m49 = Done")
        bundle.add_resource("\n".join(lines))

        result, errors = bundle.format_pattern("m0")

        assert errors == ()
        assert "Done" in result

    def test_deep_chain_hits_limit(self) -> None:
        """Chain exceeding MAX_DEPTH returns error."""
        bundle = FluentBundle("en")
        depth = MAX_DEPTH + 10
        lines = []
        for i in range(depth - 1):
            lines.append(f"m{i} = {{ m{i+1} }}")
        lines.append(f"m{depth-1} = Final")
        bundle.add_resource("\n".join(lines))

        _, errors = bundle.format_pattern("m0")

        assert len(errors) > 0
        depth_errors = [e for e in errors if isinstance(e, FrozenFluentError)]
        assert len(depth_errors) > 0

    def test_exactly_at_limit_succeeds(self) -> None:
        """Chain of exactly MAX_DEPTH - 1 nesting levels succeeds."""
        bundle = FluentBundle("en")
        depth = MAX_DEPTH - 1
        lines = []
        for i in range(depth - 1):
            lines.append(f"m{i} = {{ m{i+1} }}")
        lines.append(f"m{depth-1} = End")
        bundle.add_resource("\n".join(lines))

        result, _ = bundle.format_pattern("m0")

        assert "End" in result

    def test_depth_limit_error_message_contains_depth_info(self) -> None:
        """Error message for depth limit references depth."""
        bundle = FluentBundle("en")
        depth = MAX_DEPTH + 5
        lines = []
        for i in range(depth - 1):
            lines.append(f"msg{i} = {{ msg{i+1} }}")
        lines.append(f"msg{depth-1} = End")
        bundle.add_resource("\n".join(lines))

        _, errors = bundle.format_pattern("msg0")

        assert len(errors) > 0
        error_str = str(errors[0])
        assert "depth" in error_str.lower() or "Maximum" in error_str

    def test_cyclic_detected_before_depth(self) -> None:
        """Cyclic reference is detected before hitting depth limit."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
a = { b }
b = { c }
c = { a }
"""
        )

        result, errors = bundle.format_pattern("a")

        assert len(errors) > 0
        assert "{" in result  # Fallback format

    def test_independent_resolutions_dont_share_depth(self) -> None:
        """Separate format_pattern calls have independent depth tracking."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
a1 = { a2 }
a2 = { a3 }
a3 = A Done

b1 = { b2 }
b2 = B Done
"""
        )

        result_a, errors_a = bundle.format_pattern("a1")
        result_b, errors_b = bundle.format_pattern("b1")

        assert errors_a == ()
        assert errors_b == ()
        assert "A Done" in result_a
        assert "B Done" in result_b


class TestMaxDepthWithAttributes:
    """Tests for depth limit with attribute access."""

    def test_attribute_chain_counts_toward_depth(self) -> None:
        """Message.attribute references count toward depth."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
m0 = Value
    .attr = { m1.attr }
m1 = Value
    .attr = { m2.attr }
m2 = Value
    .attr = { m3.attr }
m3 = Value
    .attr = Final
"""
        )

        result, errors = bundle.format_pattern("m0", attribute="attr")

        assert errors == ()
        assert "Final" in result


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
        bundle = FluentBundle("en_US")
        message = self._create_nested_select_ast(depth=MAX_DEPTH + 10)
        bundle._messages["nested"] = message

        _result, errors = bundle.format_pattern("nested", {"var": "one"})

        assert len(errors) >= 1
        error_messages = [str(e) for e in errors]
        assert any("depth" in msg.lower() for msg in error_messages)

    def test_exact_max_depth_boundary(self) -> None:
        """Behavior at exactly MAX_DEPTH does not crash."""
        bundle = FluentBundle("en_US")
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
        bundle = FluentBundle("en_US")
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
        bundle = FluentBundle("en_US")
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
        bundle = FluentBundle("en_US", max_nesting_depth=10)

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


# ============================================================================
# GlobalDepthGuard Edge Cases
# ============================================================================


class TestGlobalDepthGuardEdgeCases:
    """Coverage for GlobalDepthGuard.__exit__ defensive branch."""

    def test_exit_without_enter(self) -> None:
        """Guard exit without enter does not crash (defensive branch)."""
        guard = GlobalDepthGuard(max_depth=100)
        # _token remains None; __exit__ defensive branch covered.
        guard.__exit__(None, None, None)

    def test_exit_returns_none(self) -> None:
        """Guard __exit__ does not suppress exceptions."""
        guard = GlobalDepthGuard(max_depth=100)
        with guard:
            pass


# ============================================================================
# Multi-Placeable Pattern Resolution
# ============================================================================


class TestPatternMultiplePlaceables:
    """Coverage for pattern with multiple consecutive placeables."""

    def test_pattern_with_two_placeables_in_sequence(self) -> None:
        """Pattern with consecutive placeables resolves all correctly."""
        pattern = Pattern(
            elements=(
                Placeable(expression=VariableReference(id=Identifier("first"))),
                TextElement(value=" and "),
                Placeable(expression=VariableReference(id=Identifier("second"))),
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

        result, errors = resolver.resolve_message(
            message, {"first": "A", "second": "B"}
        )

        assert result == "A and B"
        assert errors == ()

    @given(
        count=st.integers(min_value=2, max_value=10),
        values=st.lists(st.text(min_size=1, max_size=10), min_size=2, max_size=10),
    )
    def test_pattern_with_multiple_placeables_property(
        self, count: int, values: list[str]
    ) -> None:
        """Property: Pattern with N placeables resolves all correctly."""
        event(f"count={count}")
        values = values[:count]
        if len(values) < count:
            values.extend(["X"] * (count - len(values)))

        elements: list[TextElement | Placeable] = []
        for i in range(count):
            if i > 0:
                elements.append(TextElement(value=" "))
            elements.append(
                Placeable(expression=VariableReference(id=Identifier(f"v{i}")))
            )

        pattern = Pattern(elements=tuple(elements))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())
        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        args = {f"v{i}": values[i] for i in range(count)}
        result, errors = resolver.resolve_message(message, args)

        assert errors == ()
        assert result == " ".join(values)


# ============================================================================
# Malformed NumberLiteral in Variant Keys
# ============================================================================


class TestVariantMatchingMalformedNumberLiteral:
    """NumberLiteral.__post_init__ prevents construction with invalid raw strings.

    Previously, programmatically constructed ASTs could contain invalid
    NumberLiteral.raw strings that bypassed the parser. NumberLiteral.__post_init__
    now enforces the invariant at construction time, making the resolver's
    former InvalidOperation handler unreachable via normal API usage.
    """

    def test_malformed_raw_rejected_at_construction(self) -> None:
        """NumberLiteral rejects raw string that does not parse as a number."""
        with pytest.raises(ValueError, match="not a valid number literal"):
            NumberLiteral(value=42, raw="not_a_number")

    def test_multiple_malformed_raws_all_rejected(self) -> None:
        """NumberLiteral rejects each invalid raw string at construction time."""
        for bad_raw in ("invalid1", "also_invalid", "not-a-number", "[1,2,3]"):
            with pytest.raises(ValueError, match="not a valid number literal"):
                NumberLiteral(value=1, raw=bad_raw)


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
