# mypy: ignore-errors
"""Split test cases from tests/test_validation_resource.py."""

from tests.validation_resource_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# _compute_longest_paths: Cycle/Back-Edge Handling (Line 554-555)
# ============================================================================


class TestComputeLongestPathsCycleHandling:
    """Tests for _compute_longest_paths with cycles (back-edge detection).

    Targets line 554-555: continue when node in in_stack (back-edge detection).
    This is different from diamond patterns - actual cycles, not DAGs.
    """

    def test_simple_two_node_cycle(self) -> None:
        """Two-node cycle: A->B->A triggers back-edge detection.

        When DFS processes A:
        1. Push (A, 0), mark A in_stack
        2. Push (B, 0), mark B in_stack
        3. B references A, so push (A, 0)
        4. A is already in in_stack -> triggers line 554 second condition
        """
        graph = {
            "msg:a": {"msg:b"},
            "msg:b": {"msg:a"},
        }

        result = _compute_longest_paths(graph)

        # Both nodes should be processed
        assert "msg:a" in result
        assert "msg:b" in result

        # Cycle is broken by back-edge detection
        # A depends on B (depth 1), B's back-edge to A is skipped (depth 0)
        assert result["msg:a"][0] == 1
        assert result["msg:b"][0] == 0

    def test_three_node_cycle(self) -> None:
        """Three-node cycle: A->B->C->A triggers back-edge on longer path."""
        graph = {
            "msg:a": {"msg:b"},
            "msg:b": {"msg:c"},
            "msg:c": {"msg:a"},
        }

        result = _compute_longest_paths(graph)

        # All nodes processed
        assert "msg:a" in result
        assert "msg:b" in result
        assert "msg:c" in result

        # Cycle is broken at C (back-edge to A skipped)
        # A->B->C, C's back-edge to A is ignored
        assert result["msg:a"][0] == 2
        assert result["msg:b"][0] == 1
        assert result["msg:c"][0] == 0

    def test_self_referencing_node(self) -> None:
        """Self-reference: A->A is simplest cycle case."""
        graph = {
            "msg:a": {"msg:a"},
        }

        result = _compute_longest_paths(graph)

        assert "msg:a" in result
        # Self-reference creates back-edge immediately
        assert result["msg:a"][0] == 0

    def test_cycle_with_tail(self) -> None:
        """Cycle with tail: D->A->B->C->A (D leads into cycle)."""
        graph = {
            "msg:d": {"msg:a"},
            "msg:a": {"msg:b"},
            "msg:b": {"msg:c"},
            "msg:c": {"msg:a"},
        }

        result = _compute_longest_paths(graph)

        # All nodes processed
        assert len(result) == 4

        # D is outside cycle, has longest path through cycle
        assert result["msg:d"][0] >= 3

    @given(
        cycle_size=st.integers(min_value=2, max_value=6),
    )
    def test_cycle_property(self, cycle_size: int) -> None:
        """Property: N-node cycle should not cause infinite loop.

        Creates a cycle: 0->1->2->...->N-1->0

        Events emitted:
        - cycle_size={n}: Size of the cycle
        """
        # Emit event for fuzzer guidance
        event(f"cycle_size={cycle_size}")

        graph: dict[str, set[str]] = {}
        for i in range(cycle_size):
            next_node = (i + 1) % cycle_size
            graph[f"msg:n{i}"] = {f"msg:n{next_node}"}

        result = _compute_longest_paths(graph)

        # All nodes should be processed (no infinite loop)
        assert len(result) == cycle_size

        # Each node should have finite depth
        for i in range(cycle_size):
            depth, _path = result[f"msg:n{i}"]
            assert depth < cycle_size  # Depth bounded by cycle size
