"""Intensive property-based fuzz tests for ftllexengine.analysis.graph.

Tests detect_cycles(), entry_dependency_set(), and make_cycle_key()
under larger graph inputs with deadline=None for coverage-guided fuzzing.

Target Coverage:
- detect_cycles: adversarial dense/complete graphs terminate and stay bounded
- detect_cycles: cycle count never exceeds MAX_DETECTED_CYCLES
- detect_cycles: acyclic → empty result; graph with cycle → finds cycle(s)
- detect_cycles: deterministic; cycle nodes are valid graph nodes
- entry_dependency_set: correct msg:/term: prefixes; correct size
- make_cycle_key: non-empty string; contains arrow separators and node names
"""

from __future__ import annotations

import pytest
from hypothesis import event, given, settings

from ftllexengine.analysis.graph import detect_cycles, entry_dependency_set, make_cycle_key
from ftllexengine.constants import MAX_DETECTED_CYCLES
from tests.strategies import (
    complete_graphs,
    cycle_paths,
    dependency_graphs,
    namespace_ref_pairs,
)

pytestmark = pytest.mark.fuzz


class TestDetectCyclesAdversarial:
    """Fuzz tests verifying bounded behaviour on adversarial graph inputs."""

    @given(graph=complete_graphs(max_nodes=15))
    @settings(max_examples=200, deadline=None)
    def test_complete_graph_cycle_count_bounded(
        self, graph: dict[str, set[str]]
    ) -> None:
        """Property: Complete K_n graphs (n≤15) terminate and stay bounded."""
        n = len(graph)
        event(f"node_count={n}")
        cycles = detect_cycles(graph)
        event(f"cycle_count={len(cycles)}")
        assert isinstance(cycles, list)
        assert len(cycles) >= 1, f"K_{n} must have cycles"
        assert len(cycles) <= MAX_DETECTED_CYCLES

    @given(graph=dependency_graphs(max_nodes=20))
    @settings(max_examples=300, deadline=None)
    def test_any_graph_cycle_count_bounded(
        self, graph: dict[str, set[str]]
    ) -> None:
        """Property: No generated graph exceeds MAX_DETECTED_CYCLES cycles."""
        node_count = len(graph)
        event(f"node_count={node_count}")
        cycles = detect_cycles(graph)
        has_cycles = len(cycles) > 0
        event(f"has_cycles={has_cycles}")
        event(f"cycle_count={len(cycles)}")
        assert len(cycles) <= MAX_DETECTED_CYCLES

    @given(graph=dependency_graphs(allow_cycles=False))
    @settings(max_examples=200, deadline=None)
    def test_acyclic_graph_produces_no_cycles(
        self, graph: dict[str, set[str]]
    ) -> None:
        """Property: Acyclic graphs produce no cycles."""
        cycles = detect_cycles(graph)
        node_count = len(graph)
        event(f"node_count={node_count}")
        assert isinstance(cycles, list)
        assert len(cycles) == 0

    @given(graph=dependency_graphs())
    @settings(max_examples=300, deadline=None)
    def test_detect_cycles_always_terminates(
        self, graph: dict[str, set[str]]
    ) -> None:
        """Property: detect_cycles() terminates for any graph."""
        cycles = detect_cycles(graph)
        has_cycles = len(cycles) > 0
        event(f"has_cycles={has_cycles}")
        assert isinstance(cycles, list)
        for cycle in cycles:
            assert isinstance(cycle, list)
            assert len(cycle) >= 2

    @given(graph=dependency_graphs())
    @settings(max_examples=300, deadline=None)
    def test_detect_cycles_deterministic(
        self, graph: dict[str, set[str]]
    ) -> None:
        """Property: detect_cycles() is deterministic for the same input."""
        result1 = detect_cycles(graph)
        result2 = detect_cycles(graph)
        event(f"cycle_count={len(result1)}")
        assert len(result1) == len(result2)

    @given(graph=dependency_graphs())
    @settings(max_examples=200, deadline=None)
    def test_cycle_nodes_exist_in_graph(
        self, graph: dict[str, set[str]]
    ) -> None:
        """Property: All nodes in detected cycles exist in the graph."""
        cycles = detect_cycles(graph)
        node_count = len(graph)
        event(f"node_count={node_count}")
        all_nodes = set(graph.keys())
        for neighbor_set in graph.values():
            all_nodes |= neighbor_set
        for cycle in cycles:
            for node in cycle:
                assert node in all_nodes, f"Cycle node {node!r} not in graph"


class TestEntryDependencySetProperties:
    """Property tests for entry_dependency_set()."""

    @given(refs=namespace_ref_pairs())
    @settings(max_examples=300, deadline=None)
    def test_dependency_set_size(
        self, refs: tuple[frozenset[str], frozenset[str]]
    ) -> None:
        """Property: entry_dependency_set() size equals sum of input sizes."""
        msg_refs, term_refs = refs
        result = entry_dependency_set(msg_refs, term_refs)
        total = len(msg_refs) + len(term_refs)
        event(f"total_refs={total}")
        assert isinstance(result, frozenset)
        assert len(result) == total

    @given(refs=namespace_ref_pairs())
    @settings(max_examples=300, deadline=None)
    def test_dependency_set_prefixes(
        self, refs: tuple[frozenset[str], frozenset[str]]
    ) -> None:
        """Property: entry_dependency_set() applies msg: and term: prefixes."""
        msg_refs, term_refs = refs
        result = entry_dependency_set(msg_refs, term_refs)
        event(f"has_msg_refs={len(msg_refs) > 0}")
        for ref in msg_refs:
            assert f"msg:{ref}" in result
        for ref in term_refs:
            assert f"term:{ref}" in result

    @given(refs=namespace_ref_pairs())
    @settings(max_examples=200, deadline=None)
    def test_dependency_set_no_unprefixed_entries(
        self, refs: tuple[frozenset[str], frozenset[str]]
    ) -> None:
        """Property: entry_dependency_set() entries all have namespace prefix."""
        msg_refs, term_refs = refs
        result = entry_dependency_set(msg_refs, term_refs)
        event(f"result_size={len(result)}")
        for entry in result:
            assert entry.startswith(("msg:", "term:"))


class TestMakeCycleKeyProperties:
    """Property tests for make_cycle_key()."""

    @given(path=cycle_paths())
    @settings(max_examples=300, deadline=None)
    def test_cycle_key_non_empty(self, path: list[str]) -> None:
        """Property: make_cycle_key() returns a non-empty string."""
        key = make_cycle_key(path)
        path_len = len(path)
        event(f"path_len={path_len}")
        assert isinstance(key, str)
        assert len(key) > 0

    @given(path=cycle_paths())
    @settings(max_examples=300, deadline=None)
    def test_cycle_key_arrow_separator(self, path: list[str]) -> None:
        """Property: make_cycle_key() uses arrow separator format."""
        key = make_cycle_key(path)
        event(f"has_arrow={' -> ' in key}")
        assert " -> " in key

    @given(path=cycle_paths())
    @settings(max_examples=200, deadline=None)
    def test_cycle_key_contains_nodes(self, path: list[str]) -> None:
        """Property: make_cycle_key() contains all unique path nodes."""
        key = make_cycle_key(path)
        unique_nodes = set(path)
        event(f"unique_node_count={len(unique_nodes)}")
        for node in unique_nodes:
            assert node in key, f"Node {node!r} missing from key {key!r}"
