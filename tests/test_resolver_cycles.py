"""Resolver cycle detection tests.

Tests for cycle detection in message resolution:
- Direct cycles: a -> a
- Indirect cycles: a -> b -> a
- Deep cycles: a -> b -> c -> ... -> a
- Term cycles
- Mixed message/term cycles

Note: This file is marked with pytest.mark.fuzz and is excluded from normal
test runs. Run via: ./scripts/fuzz.sh or pytest -m fuzz
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.diagnostics import FluentCyclicReferenceError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.resolver import ResolutionContext

# Mark all tests in this file as fuzzing tests
pytestmark = pytest.mark.fuzz


# -----------------------------------------------------------------------------
# Unit Tests: Known Cycle Patterns
# -----------------------------------------------------------------------------


class TestDirectCycles:
    """Tests for direct self-referential cycles."""

    def test_message_references_itself(self) -> None:
        """Direct cycle: message references itself."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("self = { self }")

        result, errors = bundle.format_pattern("self")

        assert isinstance(result, str)
        assert len(errors) > 0
        assert any(isinstance(e, FluentCyclicReferenceError) for e in errors)

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
        assert any(isinstance(e, FluentCyclicReferenceError) for e in errors)

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
        # Should detect the cycle or depth limit


class TestDeepChains:
    """Tests for deep non-cyclic chains."""

    def test_chain_at_depth_limit(self) -> None:
        """Chain exactly at MAX_DEPTH should work."""
        # Create chain shorter than limit
        depth = min(MAX_DEPTH - 1, 50)
        messages = []
        for i in range(depth):
            if i < depth - 1:
                messages.append(f"msg{i} = {{ msg{i + 1} }}")
            else:
                messages.append(f"msg{i} = End")

        ftl = "\n".join(messages)
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg0")

        assert isinstance(result, str)
        assert "End" in result

    def test_chain_exceeding_depth_limit(self) -> None:
        """Chain exceeding MAX_DEPTH should produce error."""
        # Create chain longer than limit
        depth = MAX_DEPTH + 10
        messages = []
        for i in range(depth):
            if i < depth - 1:
                messages.append(f"msg{i} = {{ msg{i + 1} }}")
            else:
                messages.append(f"msg{i} = End")

        ftl = "\n".join(messages)
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        result, errors = bundle.format_pattern("msg0")

        assert isinstance(result, str)
        # Should have error about depth exceeded
        assert len(errors) > 0


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

        # Push many items
        for i in range(100):
            ctx.push(f"msg{i}")

        # Contains check should be fast
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


# -----------------------------------------------------------------------------
# Property Tests: Cycle Detection
# -----------------------------------------------------------------------------


class TestCycleDetectionProperties:
    """Property-based tests for cycle detection."""

    @given(st.integers(min_value=2, max_value=20))
    @settings(max_examples=50, deadline=None)
    def test_generated_cycle_detected(self, cycle_length: int) -> None:
        """Property: Generated cycles of any length are detected."""
        # Create a cycle of specified length
        messages = []
        for i in range(cycle_length):
            next_idx = (i + 1) % cycle_length
            messages.append(f"msg{i} = {{ msg{next_idx} }}")

        ftl = "\n".join(messages)
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        # Should not crash, should detect cycle
        result, errors = bundle.format_pattern("msg0")

        assert isinstance(result, str)
        assert len(errors) > 0

    @given(st.integers(min_value=2, max_value=10), st.integers(min_value=0, max_value=5))
    @settings(max_examples=50, deadline=None)
    def test_partial_cycle_detected(self, chain_length: int, cycle_entry: int) -> None:
        """Property: Cycles entered partway through resolution are detected."""
        cycle_entry = min(cycle_entry, chain_length - 1)

        # Create: msg0 -> msg1 -> ... -> msgN -> msg(cycle_entry)
        messages = []
        for i in range(chain_length):
            if i < chain_length - 1:
                messages.append(f"msg{i} = {{ msg{i + 1} }}")
            else:
                messages.append(f"msg{i} = {{ msg{cycle_entry} }}")

        ftl = "\n".join(messages)
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        result, errors = bundle.format_pattern("msg0")

        assert isinstance(result, str)
        assert len(errors) > 0

    @given(
        st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
            min_size=3,
            max_size=10,
            unique=True,
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_non_cyclic_chain_resolves(self, ids: list[str]) -> None:
        """Property: Non-cyclic chains resolve without errors."""
        # Create a linear chain: id0 -> id1 -> ... -> idN (no cycle)
        messages = []
        for i, msg_id in enumerate(ids):
            if i < len(ids) - 1:
                messages.append(f"{msg_id} = {{ {ids[i + 1]} }}")
            else:
                messages.append(f"{msg_id} = Final value")

        ftl = "\n".join(messages)
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        result, errors = bundle.format_pattern(ids[0])

        assert isinstance(result, str)
        assert "Final value" in result
        # Should have no cycle errors
        assert not any(isinstance(e, FluentCyclicReferenceError) for e in errors)


class TestComplexCyclePatterns:
    """Tests for complex cycle patterns."""

    def test_diamond_with_cycle(self) -> None:
        """Diamond pattern where branches meet at cycle point."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(
            """
top = { left } and { right }
left = { bottom }
right = { bottom }
bottom = { top }
"""
        )

        result, errors = bundle.format_pattern("top")

        assert isinstance(result, str)
        assert len(errors) > 0

    def test_multiple_independent_cycles(self) -> None:
        """Multiple independent cycles in same resource."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(
            """
cycle1-a = { cycle1-b }
cycle1-b = { cycle1-a }

cycle2-a = { cycle2-b }
cycle2-b = { cycle2-c }
cycle2-c = { cycle2-a }

safe = No cycle here
"""
        )

        # Each cycle should be detected independently
        _, errors1 = bundle.format_pattern("cycle1-a")
        _, errors2 = bundle.format_pattern("cycle2-a")
        result3, errors3 = bundle.format_pattern("safe")

        assert len(errors1) > 0
        assert len(errors2) > 0
        assert len(errors3) == 0
        assert result3 == "No cycle here"

    def test_cycle_in_select_branch(self) -> None:
        """Cycle only triggered in specific select branch."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(
            """
branched = { $type ->
    [safe] Safe path
   *[cycle] { cyclic }
}
cyclic = { branched }
"""
        )

        # Safe branch should work
        result_safe, errors_safe = bundle.format_pattern("branched", {"type": "safe"})
        assert "Safe path" in result_safe
        assert len(errors_safe) == 0

        # Cycle branch should detect cycle
        _, errors_cycle = bundle.format_pattern("branched", {"type": "cycle"})
        assert len(errors_cycle) > 0

    def test_cycle_in_attribute(self) -> None:
        """Cycle through attribute reference."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(
            """
msg = Value
    .attr = { msg.attr }
"""
        )

        result, _ = bundle.format_pattern("msg.attr")

        assert isinstance(result, str)
        # Should detect the self-referential attribute
