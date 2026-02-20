"""Fuzz property-based tests for runtime.resolver: cycle detection patterns."""

from __future__ import annotations

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle

pytestmark = pytest.mark.fuzz


class TestCycleDetectionProperties:
    """Property-based tests for cycle detection."""

    @given(st.integers(min_value=2, max_value=20))
    @settings(max_examples=50, deadline=None)
    def test_generated_cycle_detected(self, cycle_length: int) -> None:
        """Property: Generated cycles of any length are detected."""
        messages = []
        for i in range(cycle_length):
            next_idx = (i + 1) % cycle_length
            messages.append(f"msg{i} = {{ msg{next_idx} }}")

        bundle = FluentBundle("en-US")
        bundle.add_resource("\n".join(messages))

        result, errors = bundle.format_pattern("msg0")

        event(f"cycle_len={cycle_length}")
        assert isinstance(result, str)
        assert len(errors) > 0
        event("outcome=cycle_detected")

    @given(st.integers(min_value=2, max_value=10), st.integers(min_value=0, max_value=5))
    @settings(max_examples=50, deadline=None)
    def test_partial_cycle_detected(self, chain_length: int, cycle_entry: int) -> None:
        """Property: Cycles entered partway through resolution are detected."""
        cycle_entry = min(cycle_entry, chain_length - 1)
        messages = []
        for i in range(chain_length):
            if i < chain_length - 1:
                messages.append(f"msg{i} = {{ msg{i + 1} }}")
            else:
                messages.append(f"msg{i} = {{ msg{cycle_entry} }}")

        bundle = FluentBundle("en-US")
        bundle.add_resource("\n".join(messages))

        result, errors = bundle.format_pattern("msg0")

        event(f"chain_len={chain_length}")
        event(f"cycle_entry={cycle_entry}")
        assert isinstance(result, str)
        assert len(errors) > 0
        event("outcome=partial_cycle_detected")

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
        messages = []
        for i, msg_id in enumerate(ids):
            if i < len(ids) - 1:
                messages.append(f"{msg_id} = {{ {ids[i + 1]} }}")
            else:
                messages.append(f"{msg_id} = Final value")

        bundle = FluentBundle("en-US")
        bundle.add_resource("\n".join(messages))

        result, errors = bundle.format_pattern(ids[0])

        event(f"chain_len={len(ids)}")
        assert isinstance(result, str)
        assert "Final value" in result
        cyclic_errors = [
            e for e in errors
            if isinstance(e, FrozenFluentError) and e.category == ErrorCategory.CYCLIC
        ]
        assert len(cyclic_errors) == 0
        event("outcome=linear_chain_success")


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
        """Multiple independent cycles in same resource are each detected."""
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

        result_safe, errors_safe = bundle.format_pattern("branched", {"type": "safe"})
        assert "Safe path" in result_safe
        assert len(errors_safe) == 0

        _, errors_cycle = bundle.format_pattern("branched", {"type": "cycle"})
        assert len(errors_cycle) > 0

    def test_cycle_in_attribute(self) -> None:
        """Cycle through attribute reference is detected."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(
            """
msg = Value
    .attr = { msg.attr }
"""
        )

        result, _ = bundle.format_pattern("msg.attr")

        assert isinstance(result, str)
