# mypy: ignore-errors
"""Split test cases from tests/test_validation_resource.py."""

from tests.validation_resource_cases import *  # noqa: F403 - shared split test support

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
            assert warnings[0].code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE

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
            if w.code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE
        ]
        assert len(cycle_warnings) == 1
