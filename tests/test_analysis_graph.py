"""Tests for analysis.graph module cycle detection.

Tests cycle detection algorithms for message/term dependency validation.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.analysis.graph import build_dependency_graph, detect_cycles

# ============================================================================
# UNIT TESTS - CYCLE DETECTION
# ============================================================================


class TestDetectCyclesBasic:
    """Basic unit tests for detect_cycles function."""

    def test_empty_graph_no_cycles(self) -> None:
        """Empty graph has no cycles."""
        deps: dict[str, set[str]] = {}
        cycles = detect_cycles(deps)
        assert cycles == []

    def test_single_node_no_deps_no_cycles(self) -> None:
        """Single node with no dependencies has no cycles."""
        deps: dict[str, set[str]] = {"a": set()}
        cycles = detect_cycles(deps)
        assert cycles == []

    def test_self_referencing_node_is_cycle(self) -> None:
        """Node referencing itself is a cycle."""
        deps = {"a": {"a"}}
        cycles = detect_cycles(deps)
        assert len(cycles) == 1
        assert "a" in cycles[0]

    def test_two_node_cycle(self) -> None:
        """Two nodes referencing each other form a cycle."""
        deps = {"a": {"b"}, "b": {"a"}}
        cycles = detect_cycles(deps)
        assert len(cycles) == 1
        assert "a" in cycles[0]
        assert "b" in cycles[0]

    def test_three_node_cycle(self) -> None:
        """Three nodes A -> B -> C -> A form a cycle."""
        deps = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
        cycles = detect_cycles(deps)
        assert len(cycles) == 1
        assert "a" in cycles[0]
        assert "b" in cycles[0]
        assert "c" in cycles[0]

    def test_linear_chain_no_cycle(self) -> None:
        """Linear chain A -> B -> C has no cycles."""
        deps = {"a": {"b"}, "b": {"c"}, "c": set()}
        cycles = detect_cycles(deps)
        assert cycles == []

    def test_diamond_no_cycle(self) -> None:
        """Diamond pattern A -> B, A -> C, B -> D, C -> D has no cycles."""
        deps = {"a": {"b", "c"}, "b": {"d"}, "c": {"d"}, "d": set()}
        cycles = detect_cycles(deps)
        assert cycles == []

    def test_multiple_independent_cycles(self) -> None:
        """Multiple independent cycles are all detected."""
        deps = {
            "a": {"b"},
            "b": {"a"},  # Cycle 1: a <-> b
            "x": {"y"},
            "y": {"z"},
            "z": {"x"},  # Cycle 2: x -> y -> z -> x
        }
        cycles = detect_cycles(deps)
        assert len(cycles) == 2

    def test_node_with_missing_target_no_crash(self) -> None:
        """References to undefined nodes don't crash."""
        deps = {"a": {"undefined"}}
        cycles = detect_cycles(deps)
        assert cycles == []


class TestDetectCyclesDeduplication:
    """Tests for cycle deduplication behavior."""

    def test_cycle_not_duplicated_from_different_start(self) -> None:
        """Same cycle detected from different start nodes is deduplicated."""
        deps = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
        cycles = detect_cycles(deps)
        # Should only report cycle once, not three times (once per start node)
        assert len(cycles) == 1


# ============================================================================
# UNIT TESTS - DEPENDENCY GRAPH BUILDING
# ============================================================================


class TestBuildDependencyGraph:
    """Tests for build_dependency_graph function."""

    def test_empty_entries(self) -> None:
        """Empty entries produce empty graphs."""
        entries: dict[str, tuple[set[str], set[str]]] = {}
        msg_deps, term_deps = build_dependency_graph(entries)
        assert msg_deps == {}
        assert term_deps == {}

    def test_single_entry_with_message_ref(self) -> None:
        """Single entry with message reference."""
        entries: dict[str, tuple[set[str], set[str]]] = {"welcome": ({"greeting"}, set())}
        msg_deps, term_deps = build_dependency_graph(entries)
        assert msg_deps == {"welcome": {"greeting"}}
        assert term_deps == {"welcome": set()}

    def test_single_entry_with_term_ref(self) -> None:
        """Single entry with term reference."""
        entries: dict[str, tuple[set[str], set[str]]] = {"welcome": (set(), {"brand"})}
        msg_deps, term_deps = build_dependency_graph(entries)
        assert msg_deps == {"welcome": set()}
        assert term_deps == {"welcome": {"brand"}}

    def test_multiple_entries_mixed_refs(self) -> None:
        """Multiple entries with mixed references."""
        entries = {
            "msg1": ({"msg2"}, {"term1"}),
            "msg2": (set(), set()),
            "term1": (set(), {"term2"}),
        }
        msg_deps, term_deps = build_dependency_graph(entries)
        assert msg_deps["msg1"] == {"msg2"}
        assert msg_deps["msg2"] == set()
        assert term_deps["msg1"] == {"term1"}
        assert term_deps["term1"] == {"term2"}


# ============================================================================
# PROPERTY TESTS - CYCLE DETECTION
# ============================================================================


# Strategy for generating node names
node_names = st.text(
    alphabet=st.sampled_from("abcdefghij"),
    min_size=1,
    max_size=3,
)


class TestDetectCyclesProperties:
    """Property-based tests for detect_cycles."""

    @given(
        nodes=st.lists(node_names, min_size=1, max_size=5, unique=True),
    )
    @settings(max_examples=100)
    def test_no_edges_no_cycles(self, nodes: list[str]) -> None:
        """PROPERTY: Graph with no edges has no cycles."""
        deps: dict[str, set[str]] = {node: set() for node in nodes}
        cycles = detect_cycles(deps)
        assert cycles == []

    @given(
        chain=st.lists(node_names, min_size=2, max_size=6, unique=True),
    )
    @settings(max_examples=100)
    def test_linear_chain_no_cycles(self, chain: list[str]) -> None:
        """PROPERTY: Linear chain has no cycles."""
        deps: dict[str, set[str]] = {}
        for i, node in enumerate(chain[:-1]):
            deps[node] = {chain[i + 1]}
        deps[chain[-1]] = set()  # Last node has no deps

        cycles = detect_cycles(deps)
        assert cycles == []

    @given(
        ring=st.lists(node_names, min_size=2, max_size=6, unique=True),
    )
    @settings(max_examples=100)
    def test_ring_has_one_cycle(self, ring: list[str]) -> None:
        """PROPERTY: Ring topology has exactly one cycle."""
        deps: dict[str, set[str]] = {}
        for i, node in enumerate(ring):
            next_node = ring[(i + 1) % len(ring)]
            deps[node] = {next_node}

        cycles = detect_cycles(deps)
        assert len(cycles) == 1
        # All nodes in the ring should be in the cycle
        cycle_nodes = set(cycles[0])
        for node in ring:
            assert node in cycle_nodes
