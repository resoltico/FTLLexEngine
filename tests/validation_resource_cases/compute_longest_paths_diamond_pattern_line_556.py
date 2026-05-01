# mypy: ignore-errors
"""Split test cases from tests/test_validation_resource.py."""

from tests.validation_resource_cases import *  # noqa: F403 - shared split test support

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

        Events emitted:
        - num_intermediate={n}: Number of intermediate nodes
        """
        # Emit event for fuzzer guidance
        event(f"num_intermediate={num_intermediate}")

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
