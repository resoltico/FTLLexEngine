"""Security: expansion budget and DAG expansion prevention.

Tests for F005 (Billion Laughs resolver DoS) and F006 (cache _make_hashable DAG DoS).
Property-based testing with Hypothesis for budget enforcement invariants.
"""

from __future__ import annotations

import sys

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

sys.path.insert(0, "src")

from ftllexengine.constants import DEFAULT_MAX_EXPANSION_SIZE
from ftllexengine.diagnostics import DiagnosticCode
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.cache import IntegrityCache


class TestBillionLaughsPrevention:
    """F005: Expansion budget prevents exponential expansion in resolver."""

    def test_billion_laughs_25_levels_halted(self) -> None:
        """25-level binary expansion is halted by expansion budget."""
        lines = [f"m{i} = {{m{i + 1}}}{{m{i + 1}}}" for i in range(25)]
        lines.append("m25 = BOOM")
        ftl = "\n".join(lines)

        bundle = FluentBundle("en_US", max_expansion_size=100_000, strict=False)
        bundle.add_resource(ftl)
        _result, errors = bundle.format_pattern("m0")

        # Must complete (not hang) and produce errors
        assert len(errors) > 0
        has_expansion_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_expansion_error

    def test_normal_messages_unaffected(self) -> None:
        """Normal messages resolve without hitting expansion budget."""
        bundle = FluentBundle("en_US", max_expansion_size=1_000_000)
        bundle.add_resource("greeting = Hello { $name }!")
        result, errors = bundle.format_pattern("greeting", {"name": "World"})
        assert result == "Hello \u2068World\u2069!"
        assert len(errors) == 0

    def test_custom_expansion_budget(self) -> None:
        """Custom expansion budget is respected."""
        bundle = FluentBundle("en_US", max_expansion_size=10, strict=False)
        bundle.add_resource("long-msg = This is a long message that exceeds budget")
        _result, errors = bundle.format_pattern("long-msg")
        # The message itself exceeds 10 chars
        has_expansion_error = any(
            e.diagnostic is not None
            and e.diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
            for e in errors
        )
        assert has_expansion_error

    def test_default_expansion_budget(self) -> None:
        """Default expansion budget matches constant."""
        bundle = FluentBundle("en_US")
        assert bundle.max_expansion_size == DEFAULT_MAX_EXPANSION_SIZE

    @given(depth=st.integers(min_value=2, max_value=15))
    @settings(max_examples=10)
    def test_binary_expansion_always_caught(self, depth: int) -> None:
        """Binary expansion at any depth is caught by expansion budget."""
        event(f"depth={depth}")
        lines = [f"m{i} = {{m{i + 1}}}{{m{i + 1}}}" for i in range(depth)]
        lines.append(f"m{depth} = X")
        ftl = "\n".join(lines)

        # Budget smaller than 2^depth
        budget = min(2**depth - 1, 10_000)
        bundle = FluentBundle("en_US", max_expansion_size=budget, strict=False)
        bundle.add_resource(ftl)
        _result, errors = bundle.format_pattern("m0")

        # For small depths, the expansion may fit. For larger depths, budget is exceeded.
        if 2**depth > budget:
            assert len(errors) > 0


class TestDAGExpansionPrevention:
    """F006: Node budget prevents exponential expansion in cache _make_hashable."""

    def test_dag_25_levels_halted(self) -> None:
        """25-level binary DAG is halted by node budget."""
        root: list[object] = [1]
        for _ in range(25):
            root = [root, root]

        with pytest.raises(TypeError, match="Node budget exceeded"):
            IntegrityCache._make_hashable(root)

    def test_normal_structures_unaffected(self) -> None:
        """Normal nested structures hash without hitting node budget."""
        value = {"name": "test", "items": [1, 2, 3], "nested": {"a": True}}
        result = IntegrityCache._make_hashable(value)
        assert result is not None

    @given(depth=st.integers(min_value=1, max_value=20))
    @settings(max_examples=10)
    def test_linear_nesting_within_budget(self, depth: int) -> None:
        """Linear nesting (no sharing) stays within node budget."""
        event(f"depth={depth}")
        value: object = 1
        for _ in range(depth):
            value = [value]
        result = IntegrityCache._make_hashable(value)
        assert result is not None

    def test_dag_10_levels_halted(self) -> None:
        """Even 10-level binary DAG (1024 nodes) is within budget but 15 is not."""
        root: list[object] = [1]
        for _ in range(15):
            root = [root, root]

        with pytest.raises(TypeError, match="Node budget exceeded"):
            IntegrityCache._make_hashable(root)
