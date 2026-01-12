"""Tests for ftllexengine.analysis.graph module.

Comprehensive tests for graph algorithms used in dependency analysis:
- canonicalize_cycle: Cycle path normalization
- make_cycle_key: Canonical key generation for deduplication
- detect_cycles: Iterative DFS cycle detection
- build_dependency_graph: Dependency graph construction

Python 3.13+.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.analysis.graph import (
    build_dependency_graph,
    canonicalize_cycle,
    detect_cycles,
    make_cycle_key,
)

# ============================================================================
# UNIT TESTS - canonicalize_cycle
# ============================================================================


class TestCanonicalizeCycle:
    """Tests for canonicalize_cycle function."""

    def test_empty_cycle_returns_empty_tuple(self) -> None:
        """Empty sequence returns empty tuple."""
        result = canonicalize_cycle([])
        assert result == ()

    def test_single_element_returns_single_tuple(self) -> None:
        """Single element returns tuple with that element."""
        result = canonicalize_cycle(["A"])
        assert result == ("A",)

    def test_two_element_self_closing_cycle(self) -> None:
        """Two-element cycle ["A", "A"] returns ("A", "A")."""
        result = canonicalize_cycle(["A", "A"])
        assert result == ("A", "A")

    def test_rotation_to_smallest_element(self) -> None:
        """Cycle rotates to start with lexicographically smallest element."""
        result = canonicalize_cycle(["B", "C", "A", "B"])
        assert result == ("A", "B", "C", "A")

    def test_rotation_preserves_direction(self) -> None:
        """Different directions produce different canonical forms."""
        # A -> B -> C -> A
        forward = canonicalize_cycle(["A", "B", "C", "A"])
        # A -> C -> B -> A (reverse direction)
        reverse = canonicalize_cycle(["A", "C", "B", "A"])

        assert forward == ("A", "B", "C", "A")
        assert reverse == ("A", "C", "B", "A")
        assert forward != reverse

    def test_already_canonical_unchanged(self) -> None:
        """Already canonical cycle remains unchanged."""
        result = canonicalize_cycle(["A", "B", "C", "A"])
        assert result == ("A", "B", "C", "A")

    def test_rotation_from_middle(self) -> None:
        """Cycle starting from middle element rotates correctly."""
        result = canonicalize_cycle(["C", "B", "A", "C"])
        assert result == ("A", "C", "B", "A")

    def test_numeric_string_ordering(self) -> None:
        """Numeric strings use lexicographic ordering."""
        # "10" < "2" lexicographically
        result = canonicalize_cycle(["2", "10", "3", "2"])
        assert result == ("10", "3", "2", "10")


# ============================================================================
# UNIT TESTS - make_cycle_key
# ============================================================================


class TestMakeCycleKey:
    """Tests for make_cycle_key function."""

    def test_simple_cycle_key(self) -> None:
        """Simple cycle produces arrow-separated key."""
        key = make_cycle_key(["A", "B", "C", "A"])
        assert key == "A -> B -> C -> A"

    def test_cycle_key_canonical(self) -> None:
        """Key is canonical regardless of start position."""
        key1 = make_cycle_key(["A", "B", "C", "A"])
        key2 = make_cycle_key(["B", "C", "A", "B"])
        key3 = make_cycle_key(["C", "A", "B", "C"])

        assert key1 == key2 == key3

    def test_different_directions_different_keys(self) -> None:
        """Different directions produce different keys."""
        forward = make_cycle_key(["A", "B", "C", "A"])
        reverse = make_cycle_key(["A", "C", "B", "A"])

        assert forward != reverse

    def test_empty_cycle_key(self) -> None:
        """Empty cycle produces empty key."""
        key = make_cycle_key([])
        assert key == ""

    def test_single_element_key(self) -> None:
        """Single element produces simple key."""
        key = make_cycle_key(["A"])
        assert key == "A"


# ============================================================================
# UNIT TESTS - detect_cycles
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

    def test_overlapping_cycles_unique_keys(self) -> None:
        """Graph with overlapping cycles reports each unique cycle once."""
        deps = {
            "A": {"B", "C"},
            "B": {"A", "C"},
            "C": {"A", "B"},
        }
        cycles = detect_cycles(deps)

        # All cycles should be unique (no duplicates)
        cycle_keys = [make_cycle_key(cycle) for cycle in cycles]
        assert len(cycle_keys) == len(set(cycle_keys))


class TestDetectCyclesSharedNodes:
    """Tests for graphs with shared nodes between components."""

    def test_node_visited_in_previous_component(self) -> None:
        """Node encountered again after being fully processed is skipped.

        Create a graph with disconnected components that share a node:
        - Component 1: A -> B
        - Component 2: C -> B

        When DFS starts from A, it visits B and marks it as visited.
        When DFS starts from C, it encounters B again but B is already visited.
        """
        deps = {
            "A": {"B"},  # A references B
            "B": set(),  # B has no dependencies
            "C": {"B"},  # C also references B
        }
        cycles = detect_cycles(deps)
        assert len(cycles) == 0

    def test_diamond_shared_destination(self) -> None:
        """Diamond-shaped graph where node is reached via multiple paths.

        Graph: A -> B -> D
               A -> C -> D

        When exploring from A, we visit D through one path, then encounter
        it again through another path.
        """
        deps = {
            "A": {"B", "C"},
            "B": {"D"},
            "C": {"D"},
            "D": set(),
        }
        cycles = detect_cycles(deps)
        assert len(cycles) == 0

    def test_complex_shared_subgraph(self) -> None:
        """Complex graph with shared subgraph and separate component."""
        deps = {
            "A": {"B"},
            "B": {"C", "D"},
            "C": {"E"},
            "D": {"E"},  # Both C and D reference E
            "E": set(),
            "F": {"E"},  # F also references E (separate entry point)
        }
        cycles = detect_cycles(deps)
        assert len(cycles) == 0


class TestDetectCyclesComplexGraphs:
    """Tests for complex graph structures."""

    def test_large_graph_multiple_components(self) -> None:
        """Large graph with multiple disconnected components and cycles."""
        deps = {
            # Component 1: Linear chain (no cycle)
            "A": {"B"},
            "B": {"C"},
            "C": set(),
            # Component 2: Cycle D -> E -> F -> D
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

    def test_cycle_with_branch(self) -> None:
        """Cycle with additional non-cyclic branch."""
        deps = {
            "A": {"B", "C"},
            "B": {"D"},
            "C": {"D"},
            "D": {"A"},  # Creates cycle A -> ... -> D -> A
            "E": {"D"},  # Branch that joins the cycle
        }
        cycles = detect_cycles(deps)
        assert len(cycles) >= 1


# ============================================================================
# UNIT TESTS - build_dependency_graph
# ============================================================================


class TestBuildDependencyGraph:
    """Tests for build_dependency_graph function."""

    def test_empty_entries(self) -> None:
        """Empty entries produce empty graphs."""
        message_entries: dict[str, tuple[set[str], set[str]]] = {}
        msg_deps, term_deps = build_dependency_graph(message_entries)
        assert msg_deps == {}
        assert term_deps == {}

    def test_single_entry_with_message_ref(self) -> None:
        """Single message entry with message reference."""
        message_entries: dict[str, tuple[set[str], set[str]]] = {
            "welcome": ({"greeting"}, set())
        }
        msg_deps, term_deps = build_dependency_graph(message_entries)
        assert msg_deps == {"welcome": {"greeting"}}
        assert term_deps == {"msg:welcome": set()}

    def test_single_entry_with_term_ref(self) -> None:
        """Single message entry with term reference."""
        message_entries: dict[str, tuple[set[str], set[str]]] = {
            "welcome": (set(), {"brand"})
        }
        msg_deps, term_deps = build_dependency_graph(message_entries)
        assert msg_deps == {"welcome": set()}
        assert term_deps == {"msg:welcome": {"term:brand"}}

    def test_multiple_entries_mixed_refs(self) -> None:
        """Multiple entries with mixed references."""
        message_entries: dict[str, tuple[set[str], set[str]]] = {
            "msg1": ({"msg2"}, {"term1"}),
            "msg2": (set(), set()),
        }
        term_entries: dict[str, tuple[set[str], set[str]]] = {
            "term1": (set(), {"term2"}),
        }
        msg_deps, term_deps = build_dependency_graph(message_entries, term_entries)
        assert msg_deps["msg1"] == {"msg2"}
        assert msg_deps["msg2"] == set()
        assert term_deps["msg:msg1"] == {"term:term1"}
        assert term_deps["term:term1"] == {"term:term2"}

    def test_refs_are_copied(self) -> None:
        """Returned refs are copies, not original sets."""
        original_msg_refs: set[str] = {"greeting"}
        original_term_refs: set[str] = {"brand"}
        message_entries = {"welcome": (original_msg_refs, original_term_refs)}

        msg_deps, term_deps = build_dependency_graph(message_entries)

        # Modify returned sets
        msg_deps["welcome"].add("new_msg")
        term_deps["msg:welcome"].add("new_term")

        # Original sets should be unchanged
        assert "new_msg" not in original_msg_refs
        assert "new_term" not in original_term_refs

    def test_namespace_separation(self) -> None:
        """Messages and terms with same ID are handled correctly.

        Tests the fix for namespace collision where a resource has both a
        message and term with the same identifier (e.g., "brand" message
        and "-brand" term).
        """
        # Message "brand" references message "name"
        message_entries: dict[str, tuple[set[str], set[str]]] = {
            "brand": ({"name"}, set()),
            "name": (set(), set()),
        }
        # Term "brand" references term "company"
        term_entries: dict[str, tuple[set[str], set[str]]] = {
            "brand": (set(), {"company"}),
            "company": (set(), set()),
        }

        msg_deps, term_deps = build_dependency_graph(message_entries, term_entries)

        # Message "brand" appears in message_deps only
        assert "brand" in msg_deps
        assert msg_deps["brand"] == {"name"}

        # Message "brand" term refs appear with "msg:" prefix
        assert "msg:brand" in term_deps
        assert term_deps["msg:brand"] == set()

        # Term "brand" appears in term_deps with "term:" prefix
        assert "term:brand" in term_deps
        assert term_deps["term:brand"] == {"term:company"}

        # Both namespaces are distinct - no collision
        assert "name" in msg_deps
        assert "msg:name" in term_deps
        assert "term:company" in term_deps

    def test_term_cycle_detection(self) -> None:
        """Term-to-term cycles are detected when term IDs are prefixed correctly.

        Tests the fix for LOGIC-GRAPH-DEPENDENCY-001 where term references
        in dependency graph values must be prefixed with "term:" to match
        the key format for cycle detection.
        """
        # Create a term cycle: A -> B -> A
        term_entries: dict[str, tuple[set[str], set[str]]] = {
            "termA": (set(), {"termB"}),
            "termB": (set(), {"termA"}),
        }

        _msg_deps, term_deps = build_dependency_graph({}, term_entries)

        # Verify term dependencies are prefixed correctly
        assert term_deps["term:termA"] == {"term:termB"}
        assert term_deps["term:termB"] == {"term:termA"}

        # Verify detect_cycles can find the term cycle
        cycles = detect_cycles(term_deps)
        assert len(cycles) == 1

        # Cycle should involve both terms with "term:" prefix
        cycle_path = cycles[0]
        assert "term:termA" in cycle_path
        assert "term:termB" in cycle_path

    def test_cross_type_cycle_msg_term_term_msg(self) -> None:
        """Cross-type cycles (msg->term->term->msg) are detected with prefixing.

        Tests the fix for LOGIC-GRAPH-DEPENDENCY-001 where term references
        must be prefixed to enable cross-namespace cycle detection.
        """
        # Create a cross-type cycle: msg1 -> term1 -> term2 (which somehow back to msg1)
        # Note: In reality terms can't directly reference messages, but we can test
        # the graph structure. Let's test a more realistic pattern:
        # msg1 -> term1 -> term2, and msg2 -> term2 -> term1 (creating term cycle)
        message_entries: dict[str, tuple[set[str], set[str]]] = {
            "msg1": (set(), {"term1"}),
            "msg2": (set(), {"term2"}),
        }
        term_entries: dict[str, tuple[set[str], set[str]]] = {
            "term1": (set(), {"term2"}),
            "term2": (set(), {"term1"}),
        }

        _msg_deps, term_deps = build_dependency_graph(message_entries, term_entries)

        # Verify all term references are prefixed
        assert term_deps["msg:msg1"] == {"term:term1"}
        assert term_deps["msg:msg2"] == {"term:term2"}
        assert term_deps["term:term1"] == {"term:term2"}
        assert term_deps["term:term2"] == {"term:term1"}

        # Verify detect_cycles finds the term cycle
        cycles = detect_cycles(term_deps)
        assert len(cycles) == 1

        # The cycle should be between term1 and term2 with prefixes
        cycle_path = cycles[0]
        assert "term:term1" in cycle_path
        assert "term:term2" in cycle_path


# ============================================================================
# PROPERTY-BASED TESTS
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


class TestCanonicalizeCycleProperties:
    """Property-based tests for canonicalize_cycle."""

    @given(
        nodes=st.lists(
            st.text(alphabet="ABC", min_size=1, max_size=2),
            min_size=2,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_canonical_starts_with_minimum(self, nodes: list[str]) -> None:
        """PROPERTY: Canonical cycle starts with lexicographically smallest."""
        # Create a cycle: nodes + [nodes[0]]
        cycle = [*nodes, nodes[0]]
        canonical = canonicalize_cycle(cycle)

        if len(canonical) > 1:
            # First element (excluding closing repeat) should be minimum
            cycle_body = canonical[:-1]
            assert canonical[0] == min(cycle_body)

    @given(
        nodes=st.lists(
            st.text(alphabet="ABC", min_size=1, max_size=2),
            min_size=2,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_canonical_is_idempotent(self, nodes: list[str]) -> None:
        """PROPERTY: Canonicalizing twice gives same result."""
        cycle = [*nodes, nodes[0]]
        once = canonicalize_cycle(cycle)
        twice = canonicalize_cycle(once)

        assert once == twice

    @given(
        nodes=st.lists(
            st.text(alphabet="ABC", min_size=1, max_size=2),
            min_size=2,
            max_size=5,
            unique=True,
        ),
        rotation=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=100)
    def test_all_rotations_same_canonical(self, nodes: list[str], rotation: int) -> None:
        """PROPERTY: All rotations of same cycle produce same canonical form."""
        # Rotate the cycle
        rotation = rotation % len(nodes)
        rotated_nodes = nodes[rotation:] + nodes[:rotation]

        original_cycle = [*nodes, nodes[0]]
        rotated_cycle = [*rotated_nodes, rotated_nodes[0]]

        canonical_original = canonicalize_cycle(original_cycle)
        canonical_rotated = canonicalize_cycle(rotated_cycle)

        assert canonical_original == canonical_rotated
