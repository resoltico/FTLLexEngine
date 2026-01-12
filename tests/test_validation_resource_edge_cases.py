"""Edge case tests for validation.resource module targeting complete coverage.

Tests specific uncovered branches and statements:
- Diamond pattern graph processing in _compute_longest_paths (line 556)
- Duplicate cycle key detection in _detect_circular_references (branch 425)
- Malformed node handling in cycle formatting (branch 434)

Uses Hypothesis for property-based testing where applicable.
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.diagnostics import DiagnosticCode
from ftllexengine.syntax import (
    Identifier,
    Message,
    MessageReference,
    Pattern,
    Placeable,
    Term,
    TermReference,
    TextElement,
)
from ftllexengine.validation.resource import (
    _build_dependency_graph,
    _compute_longest_paths,
    _detect_circular_references,
)

# ============================================================================
# _compute_longest_paths: Diamond Pattern (Line 556)
# ============================================================================


class TestComputeLongestPathsDiamondPattern:
    """Tests for _compute_longest_paths with diamond dependency patterns.

    Targets line 556: continue when node already in longest_path during
    stack processing (not outer loop).
    """

    def test_diamond_pattern_triggers_inner_continue(self) -> None:
        """Diamond pattern: A->B, A->C->B causes B to be encountered twice.

        When DFS processes A:
        1. Descends to B first, computes longest_path[B]
        2. Descends to C, which references B
        3. C tries to process B, but B is already in longest_path
        4. This triggers line 556: continue (inner stack check)

        This is different from outer loop skip (line 545-546).
        """
        # Create diamond: msg_a -> msg_b, msg_a -> msg_c -> msg_b
        graph = {
            "msg:a": {"msg:b", "msg:c"},
            "msg:b": set(),
            "msg:c": {"msg:b"},
        }

        result = _compute_longest_paths(graph)

        # All nodes should be processed
        assert "msg:a" in result
        assert "msg:b" in result
        assert "msg:c" in result

        # msg_b has no dependencies: depth 0
        assert result["msg:b"][0] == 0
        # msg_c depends on msg_b: depth 1
        assert result["msg:c"][0] == 1
        # msg_a has longest path through msg_c: depth 2
        assert result["msg:a"][0] == 2

    def test_multi_level_diamond_pattern(self) -> None:
        """Multi-level diamond: A->B->D, A->C->D ensures deep graph traversal."""
        graph = {
            "msg:a": {"msg:b", "msg:c"},
            "msg:b": {"msg:d"},
            "msg:c": {"msg:d"},
            "msg:d": set(),
        }

        result = _compute_longest_paths(graph)

        # msg_d is leaf: depth 0
        assert result["msg:d"][0] == 0
        # msg_b and msg_c both depend on msg_d: depth 1
        assert result["msg:b"][0] == 1
        assert result["msg:c"][0] == 1
        # msg_a depends on msg_b/msg_c: depth 2
        assert result["msg:a"][0] == 2

    def test_complex_dag_with_shared_nodes(self) -> None:
        """Complex DAG: A->B->E, A->C->E, A->D->E ensures multiple paths converge."""
        graph = {
            "msg:a": {"msg:b", "msg:c", "msg:d"},
            "msg:b": {"msg:e"},
            "msg:c": {"msg:e"},
            "msg:d": {"msg:e"},
            "msg:e": set(),
        }

        result = _compute_longest_paths(graph)

        # msg_e is referenced by 3 nodes
        assert result["msg:e"][0] == 0
        assert result["msg:b"][0] == 1
        assert result["msg:c"][0] == 1
        assert result["msg:d"][0] == 1
        assert result["msg:a"][0] == 2

    @given(
        num_intermediate=st.integers(min_value=2, max_value=5),
    )
    def test_diamond_pattern_property(self, num_intermediate: int) -> None:
        """Property: Diamond with N intermediate nodes all converging to same leaf.

        Pattern: root -> {node1, node2, ..., nodeN} -> leaf
        """
        graph: dict[str, set[str]] = {
            "msg:root": {f"msg:mid{i}" for i in range(num_intermediate)},
            "msg:leaf": set(),
        }
        for i in range(num_intermediate):
            graph[f"msg:mid{i}"] = {"msg:leaf"}

        result = _compute_longest_paths(graph)

        # Leaf has no dependencies
        assert result["msg:leaf"][0] == 0
        # All intermediate nodes have depth 1
        for i in range(num_intermediate):
            assert result[f"msg:mid{i}"][0] == 1
        # Root has depth 2
        assert result["msg:root"][0] == 2


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
        """
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


# ============================================================================
# _detect_circular_references: Duplicate Cycle Keys (Branch 425)
# ============================================================================


class TestDetectCircularReferencesDuplicateCycleKeys:
    """Tests for _detect_circular_references duplicate cycle key handling.

    Targets branch 425->423: if cycle_key not in seen_cycle_keys (false branch).
    """

    def test_duplicate_cycle_from_detect_cycles(self) -> None:
        """Mock detect_cycles to return duplicate cycles for defensive code test."""
        # Create a simple cycle
        graph = {
            "msg:a": {"msg:b"},
            "msg:b": {"msg:a"},
        }

        # Mock detect_cycles to yield the same cycle twice
        with patch("ftllexengine.validation.resource.detect_cycles") as mock_detect:
            # Return same cycle twice to test deduplication logic
            cycle = ["msg:a", "msg:b", "msg:a"]
            mock_detect.return_value = iter([cycle, cycle])

            warnings = _detect_circular_references(graph)

            # Should deduplicate and return only one warning
            assert len(warnings) == 1
            assert warnings[0].code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE.name

    def test_cycle_key_deduplication_with_permutations(self) -> None:
        """Cycle keys should deduplicate permutations (A->B->A == B->A->B)."""
        # This tests the make_cycle_key function indirectly
        # Create a self-referencing cycle to ensure consistent behavior
        graph = {
            "msg:x": {"msg:y"},
            "msg:y": {"msg:z"},
            "msg:z": {"msg:x"},
        }

        warnings = _detect_circular_references(graph)

        # Should detect exactly one cycle (not multiple rotations)
        assert len(warnings) == 1
        cycle_warnings = [
            w for w in warnings
            if w.code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE.name
        ]
        assert len(cycle_warnings) == 1


# ============================================================================
# _detect_circular_references: Malformed Node Formatting (Branch 434)
# ============================================================================


class TestDetectCircularReferencesMalformedNodes:
    """Tests for _detect_circular_references with malformed graph nodes.

    Targets branch 434->431: node doesn't start with "msg:" or "term:".
    """

    def test_malformed_node_in_cycle_skipped_in_formatting(self) -> None:
        """Malformed nodes (no msg:/term: prefix) handled gracefully in formatting."""
        # Directly test with malformed graph (shouldn't happen in practice)
        # This tests defensive programming
        graph = {
            "msg:a": {"malformed_node"},
            "malformed_node": {"msg:a"},
        }

        # Mock detect_cycles to return a cycle with malformed node
        with patch("ftllexengine.validation.resource.detect_cycles") as mock_detect:
            cycle = ["msg:a", "malformed_node", "msg:a"]
            mock_detect.return_value = iter([cycle])

            warnings = _detect_circular_references(graph)

            # Should still create a warning
            assert len(warnings) == 1
            assert warnings[0].code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE.name

            # Context should only contain properly formatted nodes
            # "malformed_node" should be skipped (no prefix match)
            assert warnings[0].context is not None
            # The formatted output should contain "a" but not include malformed_node
            # (since it doesn't match msg: or term: prefixes)
            assert "a" in warnings[0].context

    def test_mixed_valid_and_malformed_nodes_in_cycle(self) -> None:
        """Cycle with mix of valid and malformed nodes formats valid ones only."""
        graph = {
            "msg:valid1": {"term:valid2"},
            "term:valid2": {"bad_node"},
            "bad_node": {"msg:valid1"},
        }

        with patch("ftllexengine.validation.resource.detect_cycles") as mock_detect:
            cycle = ["msg:valid1", "term:valid2", "bad_node", "msg:valid1"]
            mock_detect.return_value = iter([cycle])

            warnings = _detect_circular_references(graph)

            assert len(warnings) == 1
            assert warnings[0].context is not None
            # Should format valid nodes
            assert "valid1" in warnings[0].context
            assert "-valid2" in warnings[0].context
            # bad_node should be skipped in formatting (no prefix)


# ============================================================================
# Integration Tests with Real FTL Structures
# ============================================================================


class TestValidationResourceCompleteIntegration:
    """Integration tests combining edge cases using real FTL AST structures."""

    def test_diamond_dependency_in_real_messages(self) -> None:
        """Diamond pattern with real Message objects."""
        # Create: msgA -> msgB, msgA -> msgC -> msgB
        msg_b = Message(
            id=Identifier("msgB"),
            value=Pattern(elements=(TextElement(value="Base message"),)),
            attributes=(),
        )
        msg_c = Message(
            id=Identifier("msgC"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("msgB"))),)
            ),
            attributes=(),
        )
        msg_a = Message(
            id=Identifier("msgA"),
            value=Pattern(
                elements=(
                    Placeable(expression=MessageReference(id=Identifier("msgB"))),
                    TextElement(value=" and "),
                    Placeable(expression=MessageReference(id=Identifier("msgC"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"msgA": msg_a, "msgB": msg_b, "msgC": msg_c}
        terms_dict: dict[str, Term] = {}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Compute longest paths (exercises diamond pattern)
        result = _compute_longest_paths(graph)

        # msgB is referenced by both msgA and msgC
        assert "msg:msgB" in result
        assert result["msg:msgB"][0] == 0
        assert result["msg:msgC"][0] == 1
        assert result["msg:msgA"][0] == 2

    def test_cross_type_diamond_message_and_term(self) -> None:
        """Diamond with cross-type references: msg -> term, msg -> msg -> term."""
        # Create: msgA -> termB, msgA -> msgC -> termB
        term_b = Term(
            id=Identifier("termB"),
            value=Pattern(elements=(TextElement(value="Term value"),)),
            attributes=(),
        )
        msg_c = Message(
            id=Identifier("msgC"),
            value=Pattern(
                elements=(Placeable(expression=TermReference(id=Identifier("termB"))),)
            ),
            attributes=(),
        )
        msg_a = Message(
            id=Identifier("msgA"),
            value=Pattern(
                elements=(
                    Placeable(expression=TermReference(id=Identifier("termB"))),
                    TextElement(value=" via "),
                    Placeable(expression=MessageReference(id=Identifier("msgC"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"msgA": msg_a, "msgC": msg_c}
        terms_dict = {"termB": term_b}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Compute longest paths
        result = _compute_longest_paths(graph)

        # termB is referenced by both msgA and msgC
        assert "term:termB" in result
        assert result["term:termB"][0] == 0
        assert result["msg:msgC"][0] == 1
        assert result["msg:msgA"][0] == 2

    @given(
        num_messages=st.integers(min_value=3, max_value=8),
    )
    def test_property_complex_dependency_graphs(self, num_messages: int) -> None:
        """Property: Complex dependency graphs always compute without errors."""
        # Create a chain with some cross-references
        messages_dict: dict[str, Message] = {}

        for i in range(num_messages):
            if i == num_messages - 1:
                # Last message has no references
                value = Pattern(elements=(TextElement(value="End"),))
            elif i % 2 == 0:
                # Even messages reference next message
                value = Pattern(
                    elements=(
                        Placeable(
                            expression=MessageReference(id=Identifier(f"msg{i+1}"))
                        ),
                    )
                )
            else:
                # Odd messages reference last message (creates diamond-like structure)
                value = Pattern(
                    elements=(
                        Placeable(
                            expression=MessageReference(
                                id=Identifier(f"msg{num_messages-1}")
                            )
                        ),
                    )
                )

            messages_dict[f"msg{i}"] = Message(
                id=Identifier(f"msg{i}"),
                value=value,
                attributes=(),
            )

        terms_dict: dict[str, Term] = {}

        # Build and compute - should not raise
        graph = _build_dependency_graph(messages_dict, terms_dict)
        result = _compute_longest_paths(graph)

        # All messages should be in result
        assert len(result) >= num_messages
