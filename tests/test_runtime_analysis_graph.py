"""Property-based and unit tests for ``ftllexengine.analysis.graph``.

Covers the public API surface:
- ``entry_dependency_set``: Namespace-prefixed dependency construction
- ``make_cycle_key``: Canonical cycle display key
- ``detect_cycles``: Iterative DFS cycle detection

Python 3.13+.
"""

from __future__ import annotations

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.analysis.graph import (
    detect_cycles,
    entry_dependency_set,
    make_cycle_key,
)
from tests.strategies.graph import (
    cycle_paths,
    dependency_graphs,
    namespace_ref_pairs,
    node_names,
)

# ============================================================================
# entry_dependency_set
# ============================================================================


class TestEntryDependencySet:
    """Tests for entry_dependency_set namespace prefixing."""

    def test_empty_refs_yield_empty_frozenset(self) -> None:
        """No references produce an empty frozenset."""
        result = entry_dependency_set(frozenset(), frozenset())
        assert result == frozenset()
        assert isinstance(result, frozenset)

    def test_message_refs_prefixed_with_msg(self) -> None:
        """Message references receive ``msg:`` prefix."""
        result = entry_dependency_set(frozenset({"welcome"}), frozenset())
        assert result == frozenset({"msg:welcome"})

    def test_term_refs_prefixed_with_term(self) -> None:
        """Term references receive ``term:`` prefix."""
        result = entry_dependency_set(frozenset(), frozenset({"brand"}))
        assert result == frozenset({"term:brand"})

    def test_mixed_refs_combined(self) -> None:
        """Both namespaces combine into single frozenset."""
        result = entry_dependency_set(
            frozenset({"greeting"}), frozenset({"brand"})
        )
        assert result == frozenset({"msg:greeting", "term:brand"})

    def test_multiple_refs_per_namespace(self) -> None:
        """Multiple references per namespace all get prefixed."""
        result = entry_dependency_set(
            frozenset({"a", "b"}), frozenset({"x", "y"})
        )
        assert result == frozenset({"msg:a", "msg:b", "term:x", "term:y"})

    @given(refs=namespace_ref_pairs())
    @settings(max_examples=200)
    def test_property_output_count_equals_input_count(
        self, refs: tuple[frozenset[str], frozenset[str]]
    ) -> None:
        """PROPERTY: Output size equals sum of input sizes."""
        msg_refs, term_refs = refs
        event(f"msg_count={len(msg_refs)}")
        event(f"term_count={len(term_refs)}")

        result = entry_dependency_set(msg_refs, term_refs)
        assert len(result) == len(msg_refs) + len(term_refs)

    @given(refs=namespace_ref_pairs())
    @settings(max_examples=200)
    def test_property_all_elements_prefixed(
        self, refs: tuple[frozenset[str], frozenset[str]]
    ) -> None:
        """PROPERTY: Every element starts with ``msg:`` or ``term:``."""
        msg_refs, term_refs = refs
        event(f"total_refs={len(msg_refs) + len(term_refs)}")

        result = entry_dependency_set(msg_refs, term_refs)
        for dep in result:
            assert dep.startswith(("msg:", "term:"))

    @given(refs=namespace_ref_pairs())
    @settings(max_examples=200)
    def test_property_returns_frozenset(
        self, refs: tuple[frozenset[str], frozenset[str]]
    ) -> None:
        """PROPERTY: Return type is always frozenset (immutable)."""
        msg_refs, term_refs = refs
        event(f"total_refs={len(msg_refs) + len(term_refs)}")
        result = entry_dependency_set(msg_refs, term_refs)
        assert isinstance(result, frozenset)

    @given(refs=namespace_ref_pairs())
    @settings(max_examples=200)
    def test_property_prefix_preserves_identity(
        self, refs: tuple[frozenset[str], frozenset[str]]
    ) -> None:
        """PROPERTY: Stripping prefix recovers original refs."""
        msg_refs, term_refs = refs
        result = entry_dependency_set(msg_refs, term_refs)

        recovered_msgs = frozenset(
            d.removeprefix("msg:") for d in result if d.startswith("msg:")
        )
        recovered_terms = frozenset(
            d.removeprefix("term:") for d in result if d.startswith("term:")
        )
        event(f"recovered_msgs={len(recovered_msgs)}")
        event(f"recovered_terms={len(recovered_terms)}")
        assert recovered_msgs == msg_refs
        assert recovered_terms == term_refs


# ============================================================================
# make_cycle_key
# ============================================================================


class TestMakeCycleKey:
    """Tests for make_cycle_key canonical display format."""

    def test_empty_cycle_yields_empty_string(self) -> None:
        """Empty input produces empty key."""
        assert make_cycle_key([]) == ""

    def test_single_element_key(self) -> None:
        """Single-element input produces that element as key."""
        assert make_cycle_key(["A"]) == "A"

    def test_self_loop_key(self) -> None:
        """Self-loop ``[A, A]`` produces ``A -> A``."""
        assert make_cycle_key(["A", "A"]) == "A -> A"

    def test_simple_cycle_arrow_format(self) -> None:
        """Three-node cycle produces arrow-separated key."""
        assert make_cycle_key(["A", "B", "C", "A"]) == "A -> B -> C -> A"

    def test_canonical_across_rotations(self) -> None:
        """All rotations of same cycle produce identical key."""
        key1 = make_cycle_key(["A", "B", "C", "A"])
        key2 = make_cycle_key(["B", "C", "A", "B"])
        key3 = make_cycle_key(["C", "A", "B", "C"])
        assert key1 == key2 == key3

    def test_direction_preserved(self) -> None:
        """Different traversal directions produce different keys."""
        forward = make_cycle_key(["A", "B", "C", "A"])
        reverse = make_cycle_key(["A", "C", "B", "A"])
        assert forward != reverse

    @given(path=cycle_paths())
    @settings(max_examples=200)
    def test_property_key_is_idempotent_through_format(
        self, path: list[str]
    ) -> None:
        """PROPERTY: Same cycle always produces same key."""
        event(f"cycle_len={len(path)}")
        key1 = make_cycle_key(path)
        key2 = make_cycle_key(path)
        assert key1 == key2

    @given(
        nodes=st.lists(node_names, min_size=2, max_size=5, unique=True),
        rotation=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=200)
    def test_property_rotation_invariance(
        self, nodes: list[str], rotation: int
    ) -> None:
        """PROPERTY: All rotations of same cycle yield same key."""
        rotation = rotation % len(nodes)
        rotated = nodes[rotation:] + nodes[:rotation]
        event(f"rotation={rotation}")
        event(f"node_count={len(nodes)}")

        key_original = make_cycle_key([*nodes, nodes[0]])
        key_rotated = make_cycle_key([*rotated, rotated[0]])
        assert key_original == key_rotated

    @given(path=cycle_paths())
    @settings(max_examples=200)
    def test_property_key_starts_with_smallest_node(
        self, path: list[str]
    ) -> None:
        """PROPERTY: Canonical key starts with lexicographically smallest."""
        event(f"cycle_len={len(path)}")
        key = make_cycle_key(path)
        if len(path) >= 2:
            body = path[:-1]
            smallest = min(body)
            assert key.startswith(smallest)


# ============================================================================
# detect_cycles
# ============================================================================


class TestDetectCyclesUnit:
    """Unit tests for detect_cycles covering specific topologies."""

    def test_empty_graph(self) -> None:
        """Empty graph has no cycles."""
        assert detect_cycles({}) == []

    def test_single_node_no_edges(self) -> None:
        """Isolated node has no cycles."""
        assert detect_cycles({"a": set()}) == []

    def test_self_loop(self) -> None:
        """Self-referencing node is a cycle."""
        cycles = detect_cycles({"a": {"a"}})
        assert len(cycles) == 1
        assert "a" in cycles[0]

    def test_two_node_mutual(self) -> None:
        """Mutual reference forms a cycle."""
        cycles = detect_cycles({"a": {"b"}, "b": {"a"}})
        assert len(cycles) == 1
        assert set(cycles[0][:-1]) == {"a", "b"}

    def test_three_node_ring(self) -> None:
        """A -> B -> C -> A forms exactly one cycle."""
        cycles = detect_cycles({"a": {"b"}, "b": {"c"}, "c": {"a"}})
        assert len(cycles) == 1
        assert {"a", "b", "c"} <= set(cycles[0])

    def test_linear_chain_no_cycle(self) -> None:
        """A -> B -> C (no back-edge) has no cycles."""
        assert detect_cycles({"a": {"b"}, "b": {"c"}, "c": set()}) == []

    def test_diamond_no_cycle(self) -> None:
        """Diamond DAG has no cycles."""
        deps = {"a": {"b", "c"}, "b": {"d"}, "c": {"d"}, "d": set()}
        assert detect_cycles(deps) == []

    def test_independent_cycles_both_detected(self) -> None:
        """Two disjoint cycles are both found."""
        deps = {
            "a": {"b"}, "b": {"a"},
            "x": {"y"}, "y": {"z"}, "z": {"x"},
        }
        cycles = detect_cycles(deps)
        assert len(cycles) == 2

    def test_reference_to_undefined_node(self) -> None:
        """Edge to non-existent node does not crash."""
        assert detect_cycles({"a": {"missing"}}) == []

    def test_cycle_deduplication(self) -> None:
        """Same cycle reachable from multiple starts is reported once."""
        deps = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
        cycles = detect_cycles(deps)
        assert len(cycles) == 1

    def test_shared_sink_no_false_positive(self) -> None:
        """Multiple paths to shared sink do not produce false cycles."""
        deps = {
            "A": {"B"}, "B": set(),
            "C": {"B"},
        }
        assert detect_cycles(deps) == []

    def test_complex_multi_component(self) -> None:
        """Mixed graph with cycles, chains, and isolated nodes."""
        deps = {
            "A": {"B"}, "B": {"C"}, "C": set(),
            "D": {"E"}, "E": {"F"}, "F": {"D"},
            "G": {"C"},
            "H": {"H"},
        }
        cycles = detect_cycles(deps)
        assert len(cycles) >= 2

    def test_namespace_prefixed_term_cycle(self) -> None:
        """Prefixed term keys produce detectable cycles."""
        deps = {
            "term:a": {"term:b"},
            "term:b": {"term:a"},
        }
        cycles = detect_cycles(deps)
        assert len(cycles) == 1
        assert "term:a" in cycles[0]
        assert "term:b" in cycles[0]

    def test_cross_namespace_chain_no_cycle(self) -> None:
        """msg -> term chain without back-edge has no cycle."""
        deps = {
            "msg:welcome": {"term:brand"},
            "term:brand": set(),
        }
        assert detect_cycles(deps) == []

    def test_overlapping_cycles_all_unique(self) -> None:
        """Fully connected graph reports each unique cycle once."""
        deps = {
            "A": {"B", "C"},
            "B": {"A", "C"},
            "C": {"A", "B"},
        }
        cycles = detect_cycles(deps)
        keys = [make_cycle_key(c) for c in cycles]
        assert len(keys) == len(set(keys))


class TestDetectCyclesProperties:
    """Property-based tests for detect_cycles."""

    @given(graph=dependency_graphs(allow_cycles=False))
    @settings(max_examples=200)
    def test_acyclic_graph_no_cycles(
        self, graph: dict[str, set[str]]
    ) -> None:
        """PROPERTY: Acyclic graphs produce no cycles."""
        event(f"node_count={len(graph)}")
        edge_count = sum(len(v) for v in graph.values())
        event(f"edge_count={edge_count}")
        cycles = detect_cycles(graph)
        assert cycles == []

    @given(ring=st.lists(node_names, min_size=2, max_size=6, unique=True))
    @settings(max_examples=200)
    def test_ring_has_exactly_one_cycle(self, ring: list[str]) -> None:
        """PROPERTY: Ring topology produces exactly one cycle."""
        event(f"ring_size={len(ring)}")
        deps: dict[str, set[str]] = {}
        for i, node in enumerate(ring):
            deps[node] = {ring[(i + 1) % len(ring)]}

        cycles = detect_cycles(deps)
        assert len(cycles) == 1
        assert set(ring) <= set(cycles[0])

    @given(graph=dependency_graphs())
    @settings(max_examples=300)
    def test_cycles_are_unique(self, graph: dict[str, set[str]]) -> None:
        """PROPERTY: No duplicate cycles in output."""
        event(f"node_count={len(graph)}")
        cycles = detect_cycles(graph)
        keys = [make_cycle_key(c) for c in cycles]
        event(f"cycle_count={len(cycles)}")
        assert len(keys) == len(set(keys))

    @given(graph=dependency_graphs())
    @settings(max_examples=300)
    def test_cycle_nodes_exist_in_graph(
        self, graph: dict[str, set[str]]
    ) -> None:
        """PROPERTY: Every node in a cycle is reachable from the graph."""
        event(f"node_count={len(graph)}")
        cycles = detect_cycles(graph)
        all_nodes = set(graph.keys())
        for neighbor_set in graph.values():
            all_nodes |= neighbor_set
        for cycle in cycles:
            for node in cycle:
                assert node in all_nodes

    @given(graph=dependency_graphs())
    @settings(max_examples=300)
    def test_cycles_are_closed(self, graph: dict[str, set[str]]) -> None:
        """PROPERTY: Each cycle's last element equals its first."""
        event(f"node_count={len(graph)}")
        cycles = detect_cycles(graph)
        event(f"cycle_count={len(cycles)}")
        for cycle in cycles:
            assert len(cycle) >= 2
            assert cycle[0] == cycle[-1]

    @given(
        nodes=st.lists(node_names, min_size=1, max_size=5, unique=True),
    )
    @settings(max_examples=200)
    def test_edgeless_graph_no_cycles(self, nodes: list[str]) -> None:
        """PROPERTY: Graph with no edges has no cycles."""
        event(f"node_count={len(nodes)}")
        deps: dict[str, set[str]] = {n: set() for n in nodes}
        assert detect_cycles(deps) == []

    @given(
        chain=st.lists(node_names, min_size=2, max_size=6, unique=True),
    )
    @settings(max_examples=200)
    def test_linear_chain_property(self, chain: list[str]) -> None:
        """PROPERTY: Linear chain (DAG) has no cycles."""
        event(f"chain_length={len(chain)}")
        deps: dict[str, set[str]] = {}
        for i, node in enumerate(chain[:-1]):
            deps[node] = {chain[i + 1]}
        deps[chain[-1]] = set()
        assert detect_cycles(deps) == []
