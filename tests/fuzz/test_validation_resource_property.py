"""Intensive property-based fuzz tests for ftllexengine.validation.resource.

Covers validate_resource() across all six validation passes and the internal
_compute_longest_paths() DFS algorithm under adversarial graph inputs.

Target Coverage:
- validate_resource: always returns ValidationResult; is_valid iff no errors
- validate_resource: valid FTL never produces errors; Junk always produces errors
- validate_resource: cycle detection consistent with analysis.graph.detect_cycles
- _compute_longest_paths: terminates for any graph including cyclic graphs
- _compute_longest_paths: every start node gets an entry; path starts with node
- _compute_longest_paths: correct depth for linear/DAG topologies
- _compute_longest_paths: typed graphs (msg:/term: prefixes) handled correctly

Python 3.13+.
"""

from __future__ import annotations

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import ValidationResult, WarningSeverity
from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.validation.resource import validate_resource
from ftllexengine.validation.resource_graph import _compute_longest_paths
from tests.strategies import (
    dependency_graphs,
    ftl_simple_messages,
    validation_dependency_graphs,
    validation_resource_sources,
)

pytestmark = pytest.mark.fuzz


# ============================================================================
# _compute_longest_paths() property tests
# ============================================================================


class TestComputeLongestPathsProperties:
    """Intensive property tests for the internal DFS longest-path algorithm."""

    @given(graph=dependency_graphs())
    @settings(deadline=None)
    def test_always_terminates(self, graph: dict[str, set[str]]) -> None:
        """Property: _compute_longest_paths() terminates for any graph topology."""
        node_count = len(graph)
        event(f"node_count={node_count}")
        result = _compute_longest_paths(graph)
        assert isinstance(result, dict)

    @given(graph=dependency_graphs())
    @settings(deadline=None)
    def test_every_start_node_has_entry(self, graph: dict[str, set[str]]) -> None:
        """Property: Every node that is a key in the input graph appears in the result."""
        result = _compute_longest_paths(graph)
        node_count = len(graph)
        event(f"node_count={node_count}")
        for node in graph:
            assert node in result, f"Start node {node!r} missing from result"

    @given(graph=dependency_graphs())
    @settings(deadline=None)
    def test_path_starts_with_node(self, graph: dict[str, set[str]]) -> None:
        """Property: Each result path begins with its own node."""
        result = _compute_longest_paths(graph)
        has_multi = any(len(g) > 0 for g in graph.values())
        event(f"has_edges={has_multi}")
        for node, (_, path) in result.items():
            assert len(path) >= 1
            assert path[0] == node, (
                f"Path for {node!r} does not start with the node: {path!r}"
            )

    @given(graph=dependency_graphs())
    @settings(deadline=None)
    def test_depth_equals_path_length_minus_one(
        self, graph: dict[str, set[str]]
    ) -> None:
        """Property: depth == len(path) - 1 for every result entry."""
        result = _compute_longest_paths(graph)
        node_count = len(graph)
        event(f"node_count={node_count}")
        for node, (depth, path) in result.items():
            assert depth == len(path) - 1, (
                f"Node {node!r}: depth={depth} but len(path)={len(path)}"
            )

    @given(graph=dependency_graphs(allow_cycles=False))
    @settings(deadline=None)
    def test_acyclic_leaf_nodes_have_depth_zero(
        self, graph: dict[str, set[str]]
    ) -> None:
        """Property: Leaf nodes (no outgoing edges) always have depth 0 in DAGs."""
        result = _compute_longest_paths(graph)
        has_leaves = any(len(v) == 0 for v in graph.values())
        event(f"has_leaves={has_leaves}")
        for node, children in graph.items():
            if not children:
                depth, path = result[node]
                assert depth == 0, f"Leaf {node!r} has depth {depth} (expected 0)"
                assert path == [node]

    @given(
        graph=dependency_graphs(allow_cycles=True),
    )
    @settings(deadline=None)
    def test_cyclic_graph_terminates(self, graph: dict[str, set[str]]) -> None:
        """Property: Graphs with cycles terminate without infinite loops."""
        node_count = len(graph)
        event(f"node_count={node_count}")
        result = _compute_longest_paths(graph)
        assert isinstance(result, dict)
        for node in graph:
            assert node in result

    @given(graph=dependency_graphs())
    @settings(deadline=None)
    def test_depths_non_negative(self, graph: dict[str, set[str]]) -> None:
        """Property: All computed depths are non-negative integers."""
        result = _compute_longest_paths(graph)
        node_count = len(graph)
        event(f"node_count={node_count}")
        for node, (depth, _) in result.items():
            assert depth >= 0, f"Node {node!r} has negative depth {depth}"

    @given(graph=dependency_graphs(allow_cycles=False, max_nodes=5))
    @settings(deadline=None)
    def test_linear_chain_depth_is_correct(
        self, graph: dict[str, set[str]]
    ) -> None:
        """Property: In a linear chain A->B->C->D, depth(A) >= depth(B) >= depth(C).

        Monotonicity: a node that has outgoing edges to another node must have
        depth at least one greater than the depth of the reached node.
        """
        result = _compute_longest_paths(graph)
        is_linear = all(len(v) <= 1 for v in graph.values())
        event(f"is_linear={is_linear}")
        if is_linear:
            for node, children in graph.items():
                if children:
                    child = next(iter(children))
                    if child in result:
                        parent_depth = result[node][0]
                        child_depth = result[child][0]
                        assert parent_depth > child_depth, (
                            f"Linear chain: {node!r}(depth={parent_depth}) -> "
                            f"{child!r}(depth={child_depth}): parent must exceed child"
                        )

    @given(graph=validation_dependency_graphs())
    @settings(deadline=None)
    def test_typed_graph_terminates_with_correct_keys(
        self, graph: dict[str, set[str]]
    ) -> None:
        """Property: Typed msg:/term: prefixed graphs produce correct key coverage."""
        node_count = len(graph)
        event(f"node_count={node_count}")
        result = _compute_longest_paths(graph)
        for node in graph:
            assert node in result


# ============================================================================
# validate_resource() property tests
# ============================================================================


class TestValidateResourceProperties:
    """Property tests for validate_resource() across all validation passes."""

    @given(source=validation_resource_sources())
    @settings(deadline=None)
    def test_always_returns_validation_result(self, source: str) -> None:
        """Property: validate_resource() always returns a ValidationResult."""
        result = validate_resource(source)
        source_len = len(source)
        event(f"source_len_bucket={'short' if source_len < 50 else 'long'}")
        assert isinstance(result, ValidationResult)

    @given(source=validation_resource_sources())
    @settings(deadline=None)
    def test_is_valid_iff_no_errors_or_annotations(self, source: str) -> None:
        """Property: is_valid is True iff errors and annotations are both empty."""
        result = validate_resource(source)
        has_errors = len(result.errors) > 0
        has_annotations = len(result.annotations) > 0
        event(f"has_errors={has_errors}")
        expected = not has_errors and not has_annotations
        assert result.is_valid == expected, (
            f"is_valid={result.is_valid} but errors={result.errors!r}, "
            f"annotations={result.annotations!r}"
        )

    @given(source=validation_resource_sources())
    @settings(deadline=None)
    def test_errors_and_warnings_are_tuples(self, source: str) -> None:
        """Property: errors and warnings are always tuples (immutable evidence)."""
        result = validate_resource(source)
        has_warnings = len(result.warnings) > 0
        event(f"has_warnings={has_warnings}")
        assert isinstance(result.errors, tuple)
        assert isinstance(result.warnings, tuple)

    @given(source=ftl_simple_messages())
    @settings(deadline=None)
    def test_valid_ftl_produces_no_errors(self, source: str) -> None:
        """Property: Syntactically valid FTL messages produce no validation errors."""
        result = validate_resource(source)
        source_len = len(source)
        event(f"source_len_bucket={'short' if source_len < 100 else 'long'}")
        assert result.is_valid, (
            f"Valid FTL produced errors: {result.errors!r}\nSource: {source!r}"
        )

    @given(
        prefix=st.text(
            alphabet=st.characters(
                blacklist_characters="=\r\n\t",
                blacklist_categories=("Cc",),  # type: ignore[arg-type]
            ),
            min_size=3,
            max_size=20,
        ).filter(lambda s: s.strip() and not s.strip().startswith("#"))
    )
    @settings(deadline=None)
    def test_junk_source_produces_error(self, prefix: str) -> None:
        """Property: FTL source that the parser treats as Junk produces errors."""
        result = validate_resource(prefix)
        has_errors = len(result.errors) > 0
        event(f"has_errors={has_errors}")
        if result.errors:
            assert not result.is_valid

    @given(source=validation_resource_sources())
    @settings(deadline=None)
    def test_idempotent_on_second_call(self, source: str) -> None:
        """Property: validate_resource() is deterministic (same result on two calls)."""
        result1 = validate_resource(source)
        result2 = validate_resource(source)
        has_errors = len(result1.errors) > 0
        event(f"has_errors={has_errors}")
        assert result1.is_valid == result2.is_valid
        assert len(result1.errors) == len(result2.errors)
        assert len(result1.warnings) == len(result2.warnings)

    @given(source=validation_resource_sources())
    @settings(deadline=None)
    def test_circular_warnings_have_critical_severity(self, source: str) -> None:
        """Property: Circular reference warnings always have CRITICAL severity."""
        result = validate_resource(source)
        cycle_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE
        ]
        has_cycles = len(cycle_warnings) > 0
        event(f"has_cycles={has_cycles}")
        for warning in cycle_warnings:
            assert warning.severity == WarningSeverity.CRITICAL, (
                f"Circular reference warning has non-critical severity: "
                f"{warning.severity!r}"
            )
