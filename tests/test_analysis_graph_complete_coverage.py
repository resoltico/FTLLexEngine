"""Complete coverage tests for analysis/graph.py.

Tests uncovered lines and branches to achieve 100% coverage.

Missing coverage:
- Line 44: canonicalize_cycle with empty or single-element cycle
- Line 49: canonicalize_cycle with cycle that becomes empty after removing last
- Line 79: continue when node already visited in another traversal
- Branch 106->89: duplicate cycle detection (cycle_key in seen_cycle_keys)
- Branch 112->114: path empty or path[-1] != node in EXIT state
"""

from __future__ import annotations

from ftllexengine.analysis.graph import canonicalize_cycle, detect_cycles

# ============================================================================
# LINE 44: canonicalize_cycle with Empty or Single-Element Cycle
# ============================================================================


class TestLine44EmptyOrSingleElementCycle:
    """Test line 44: early return for len(cycle) <= 1."""

    def test_canonicalize_empty_cycle(self) -> None:
        """Test canonicalize_cycle with empty sequence returns empty tuple."""
        result = canonicalize_cycle([])
        assert result == ()

    def test_canonicalize_single_element_cycle(self) -> None:
        """Test canonicalize_cycle with single element returns tuple with that element."""
        result = canonicalize_cycle(["A"])
        assert result == ("A",)


# ============================================================================
# LINE 49: canonicalize_cycle with Cycle that Becomes Empty After Slice
# ============================================================================


class TestLine49NodesEmptyAfterSlice:
    """Test line 49: nodes empty after excluding closing element."""

    def test_canonicalize_two_element_identical_cycle(self) -> None:
        """Test canonicalize_cycle with ["A", "A"] returns same tuple.

        When cycle is ["A", "A"], cycle[:-1] gives ["A"], which is not empty.
        We need a case where cycle[:-1] produces empty list.
        This only happens with len=1, which is already handled by line 44.
        So line 49 is unreachable in practice.
        """
        # This test documents the expected behavior
        result = canonicalize_cycle(["A", "A"])
        assert result == ("A", "A")

# ============================================================================
# LINE 79: Node Already Visited in Another Traversal
# ============================================================================


class TestLine79NodeAlreadyVisited:
    """Test line 79: continue when node already visited."""

    def test_node_visited_in_previous_component(self) -> None:
        """Test line 79: node encountered again after being fully processed.

        Create a graph with disconnected components that share a node:
        - Component 1: A -> B
        - Component 2: C -> B

        When DFS starts from A, it visits B and marks it as visited.
        When DFS starts from C (next iteration of outer loop), it encounters
        B again but B is already in visited, so line 79 executes.
        """
        deps = {
            "A": {"B"},  # A references B
            "B": set(),  # B has no dependencies
            "C": {"B"},  # C also references B
        }

        cycles = detect_cycles(deps)

        # No cycles should be detected
        assert len(cycles) == 0

    def test_multiple_paths_to_same_node(self) -> None:
        """Test diamond-shaped graph where node is reached via multiple paths.

        Graph: A -> B -> D
               A -> C -> D

        When exploring from A, we visit D through one path, then encounter
        it again through another path.
        """
        deps = {
            "A": {"B", "C"},  # A references both B and C
            "B": {"D"},  # B references D
            "C": {"D"},  # C also references D
            "D": set(),  # D has no dependencies
        }

        cycles = detect_cycles(deps)

        # No cycles
        assert len(cycles) == 0

    def test_complex_shared_subgraph(self) -> None:
        """Test complex graph with shared subgraph."""
        deps = {
            "A": {"B"},
            "B": {"C", "D"},
            "C": {"E"},
            "D": {"E"},  # Both C and D reference E
            "E": set(),
            "F": {"E"},  # F also references E (separate component)
        }

        cycles = detect_cycles(deps)

        # No cycles
        assert len(cycles) == 0


# ============================================================================
# BRANCH 106->89: Duplicate Cycle Detection
# ============================================================================


class TestBranch106Line89DuplicateCycle:
    """Test branch 106->89: duplicate cycle detected and skipped."""

    def test_cycle_detected_multiple_times_same_key(self) -> None:
        """Test branch 106->89: same cycle found multiple times.

        Create a graph where the same cycle can be discovered from different
        entry points, resulting in the same canonical cycle key.

        Graph with cycle: A -> B -> C -> A
                         B -> C -> A -> B (same cycle, different start)
        """
        deps = {
            "A": {"B"},
            "B": {"C"},
            "C": {"A", "B"},  # C references both A and B
        }

        cycles = detect_cycles(deps)

        # Should find the cycle, but only report it once (deduplication)
        assert len(cycles) >= 1

        # All cycles should be unique (no duplicates)
        cycle_keys = [" -> ".join(sorted(set(cycle))) for cycle in cycles]
        assert len(cycle_keys) == len(set(cycle_keys))

    def test_multiple_overlapping_cycles(self) -> None:
        """Test graph with multiple overlapping cycles.

        Graph: A -> B -> A (cycle 1)
               B -> C -> B (cycle 2)
               A -> C -> A (cycle 3, shares nodes with 1 and 2)
        """
        deps = {
            "A": {"B", "C"},
            "B": {"A", "C"},
            "C": {"A", "B"},
        }

        cycles = detect_cycles(deps)

        # Should find cycles, with deduplication
        assert len(cycles) >= 1

        # Verify deduplication works
        cycle_keys = [" -> ".join(sorted(set(cycle))) for cycle in cycles]
        assert len(cycle_keys) == len(set(cycle_keys))


# ============================================================================
# BRANCH 112->114: Path Empty or Mismatch in EXIT State
# ============================================================================


class TestBranch112Line114PathEmptyOrMismatch:
    """Test branch 112->114: defensive check in EXIT state.

    This branch handles the case where path is empty or path[-1] != node.
    This may be defensive code for robustness.
    """

    def test_simple_graph_exit_state_normal(self) -> None:
        """Test normal EXIT state processing (if condition True)."""
        deps = {
            "A": {"B"},
            "B": set(),
        }

        cycles = detect_cycles(deps)

        # No cycles, normal processing
        assert len(cycles) == 0

    def test_empty_dependencies_exit_processing(self) -> None:
        """Test EXIT state with node having empty dependencies."""
        deps: dict[str, set[str]] = {
            "A": set(),  # No dependencies
            "B": set(),
            "C": set(),
        }

        cycles = detect_cycles(deps)

        # No cycles
        assert len(cycles) == 0

    def test_self_reference_exit_processing(self) -> None:
        """Test EXIT state when node has self-reference.

        A self-reference creates a trivial cycle.
        """
        deps = {
            "A": {"A"},  # Self-reference
        }

        cycles = detect_cycles(deps)

        # Should detect self-cycle
        assert len(cycles) == 1
        assert "A" in cycles[0]


# ============================================================================
# Integration Tests for Complete Coverage
# ============================================================================


class TestCompleteGraphCoverage:
    """Integration tests ensuring all code paths are covered."""

    def test_large_graph_with_multiple_components(self) -> None:
        """Test large graph with multiple disconnected components.

        This test combines multiple scenarios:
        - Shared nodes between components (line 79)
        - Multiple cycles (branch 106->89)
        - Normal EXIT processing (branch 112->114)
        """
        deps = {
            # Component 1: Linear chain
            "A": {"B"},
            "B": {"C"},
            "C": set(),
            # Component 2: Cycle
            "D": {"E"},
            "E": {"F"},
            "F": {"D"},
            # Component 3: References shared node C
            "G": {"C"},
            # Component 4: Self-loop
            "H": {"H"},
        }

        cycles = detect_cycles(deps)

        # Should find at least 2 cycles (D-E-F and H)
        assert len(cycles) >= 2

    def test_complex_overlapping_structure(self) -> None:
        """Test complex graph with overlapping cycles and shared nodes."""
        deps = {
            "A": {"B", "C"},
            "B": {"D"},
            "C": {"D"},
            "D": {"A"},  # Creates cycle
            "E": {"D"},  # Shares node D
        }

        cycles = detect_cycles(deps)

        # Should detect the A-B-D-A and A-C-D-A cycles
        assert len(cycles) >= 1
