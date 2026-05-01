# mypy: ignore-errors
"""Split test cases from tests/test_validation_resource.py."""

from tests.validation_resource_cases import *  # noqa: F403 - shared split test support

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
            assert warnings[0].code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE

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
