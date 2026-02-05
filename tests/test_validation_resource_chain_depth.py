"""Tests for reference chain depth validation and formatting.

Covers:
- Long reference chains exceeding MAX_DEPTH
- Chain path truncation for chains > 10 nodes
- Chain formatting with message and term prefixes

Uses Hypothesis for property-based testing where applicable.
"""

from __future__ import annotations

from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.diagnostics import DiagnosticCode, WarningSeverity
from ftllexengine.syntax import (
    Identifier,
    Message,
    MessageReference,
    Pattern,
    Placeable,
    Term,
    TextElement,
)
from ftllexengine.validation.resource import (
    _build_dependency_graph,
    _detect_long_chains,
    validate_resource,
)

# ============================================================================
# Long Chain Detection
# ============================================================================


class TestLongChainDetection:
    """Test detection of reference chains exceeding MAX_DEPTH."""

    def test_chain_exceeding_max_depth_produces_warning(self) -> None:
        """Reference chain longer than MAX_DEPTH produces warning."""
        # Create chain: msg0 -> msg1 -> msg2 -> ... -> msgN
        # where N > MAX_DEPTH
        chain_length = MAX_DEPTH + 5
        lines = []
        for i in range(chain_length):
            if i < chain_length - 1:
                lines.append(f"msg{i} = {{ msg{i+1} }}")
            else:
                lines.append(f"msg{i} = End")

        ftl = "\n".join(lines)
        result = validate_resource(ftl)

        # Should have chain depth warning
        chain_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]
        assert len(chain_warnings) > 0
        assert chain_warnings[0].severity == WarningSeverity.WARNING

    def test_chain_within_max_depth_no_warning(self) -> None:
        """Reference chain within MAX_DEPTH produces no warning."""
        # Create chain shorter than MAX_DEPTH
        chain_length = MAX_DEPTH - 2
        lines = []
        for i in range(chain_length):
            if i < chain_length - 1:
                lines.append(f"msg{i} = {{ msg{i+1} }}")
            else:
                lines.append(f"msg{i} = End")

        ftl = "\n".join(lines)
        result = validate_resource(ftl)

        # Should have no chain depth warning
        chain_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]
        assert len(chain_warnings) == 0

    def test_chain_exactly_max_depth_no_warning(self) -> None:
        """Reference chain exactly at MAX_DEPTH produces no warning."""
        chain_length = MAX_DEPTH
        lines = []
        for i in range(chain_length):
            if i < chain_length - 1:
                lines.append(f"msg{i} = {{ msg{i+1} }}")
            else:
                lines.append(f"msg{i} = End")

        ftl = "\n".join(lines)
        result = validate_resource(ftl)

        chain_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]
        assert len(chain_warnings) == 0


# ============================================================================
# Chain Path Truncation
# ============================================================================


class TestChainPathTruncation:
    """Test truncation of long chain paths in warning messages."""

    def test_chain_longer_than_10_nodes_shows_truncation(self) -> None:
        """Chains longer than 10 nodes show truncation marker in context."""
        # Create 15-node chain
        chain_length = 15
        messages_dict: dict[str, Message] = {}

        for i in range(chain_length):
            if i < chain_length - 1:
                value = Pattern(
                    elements=(
                        Placeable(
                            expression=MessageReference(id=Identifier(name=f"msg{i+1}"))
                        ),
                    )
                )
            else:
                value = Pattern(elements=(TextElement(value="End"),))

            messages_dict[f"msg{i}"] = Message(
                id=Identifier(f"msg{i}"),
                value=value,
                attributes=(),
            )

        terms_dict: dict[str, Term] = {}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)
        # Use max_depth=5 to trigger warning
        warnings = _detect_long_chains(graph, max_depth=5)

        # VAL-REDUNDANT-REPORTS-001: Reports ALL chains exceeding max_depth
        # With 15 nodes and max_depth=5, chains from msg0-msg8 all exceed the limit
        assert len(warnings) >= 1
        assert warnings[0].code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name

        # First warning (deepest chain) should show truncation marker
        assert warnings[0].context is not None
        assert "..." in warnings[0].context
        assert "15 total" in warnings[0].context

    def test_chain_exactly_10_nodes_no_truncation(self) -> None:
        """Chains with exactly 10 nodes show no truncation marker."""
        chain_length = 10
        messages_dict: dict[str, Message] = {}

        for i in range(chain_length):
            if i < chain_length - 1:
                value = Pattern(
                    elements=(
                        Placeable(
                            expression=MessageReference(id=Identifier(name=f"msg{i+1}"))
                        ),
                    )
                )
            else:
                value = Pattern(elements=(TextElement(value="End"),))

            messages_dict[f"msg{i}"] = Message(
                id=Identifier(f"msg{i}"),
                value=value,
                attributes=(),
            )

        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(messages_dict, terms_dict)
        # Use max_depth=5 to trigger warning
        warnings = _detect_long_chains(graph, max_depth=5)

        # VAL-REDUNDANT-REPORTS-001: Reports ALL chains exceeding max_depth
        assert len(warnings) >= 1

        # First warning (deepest chain = 10 nodes) should NOT show truncation
        assert warnings[0].context is not None
        assert "..." not in warnings[0].context
        assert "total" not in warnings[0].context

    def test_chain_less_than_10_nodes_no_truncation(self) -> None:
        """Chains with < 10 nodes show no truncation marker."""
        chain_length = 7
        messages_dict: dict[str, Message] = {}

        for i in range(chain_length):
            if i < chain_length - 1:
                value = Pattern(
                    elements=(
                        Placeable(
                            expression=MessageReference(id=Identifier(name=f"msg{i+1}"))
                        ),
                    )
                )
            else:
                value = Pattern(elements=(TextElement(value="End"),))

            messages_dict[f"msg{i}"] = Message(
                id=Identifier(f"msg{i}"),
                value=value,
                attributes=(),
            )

        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_long_chains(graph, max_depth=3)

        # VAL-REDUNDANT-REPORTS-001: Reports ALL chains exceeding max_depth
        assert len(warnings) >= 1
        # First warning (deepest chain) should not show truncation for < 10 nodes
        assert warnings[0].context is not None
        assert "..." not in warnings[0].context

    @given(chain_length=st.integers(min_value=11, max_value=50))
    @example(chain_length=11)
    @example(chain_length=25)
    @example(chain_length=50)
    def test_long_chain_truncation_property(self, chain_length: int) -> None:
        """Property: Chains > 10 nodes always show truncation marker.

        Events emitted:
        - chain_length_bucket={bucket}: Chain length category
        """
        # Emit event for chain length buckets
        if chain_length <= 15:
            event("chain_length_bucket=11-15")
        elif chain_length <= 25:
            event("chain_length_bucket=16-25")
        elif chain_length <= 35:
            event("chain_length_bucket=26-35")
        else:
            event("chain_length_bucket=36-50")

        messages_dict: dict[str, Message] = {}

        for i in range(chain_length):
            if i < chain_length - 1:
                value = Pattern(
                    elements=(
                        Placeable(
                            expression=MessageReference(id=Identifier(name=f"m{i+1}"))
                        ),
                    )
                )
            else:
                value = Pattern(elements=(TextElement(value="End"),))

            messages_dict[f"m{i}"] = Message(
                id=Identifier(f"m{i}"),
                value=value,
                attributes=(),
            )

        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_long_chains(graph, max_depth=5)

        # VAL-REDUNDANT-REPORTS-001: Reports ALL chains exceeding max_depth
        # First warning (deepest chain) should show truncation for > 10 nodes
        assert len(warnings) >= 1
        assert warnings[0].context is not None
        assert "..." in warnings[0].context
        assert f"{chain_length} total" in warnings[0].context


# ============================================================================
# Chain Formatting
# ============================================================================


class TestChainFormatting:
    """Test formatting of chain paths with message/term prefixes."""

    def test_message_chain_formatted_without_dash_prefix(self) -> None:
        """Message-only chain formatted without dash prefixes."""
        ftl = """
msg0 = { msg1 }
msg1 = { msg2 }
msg2 = { msg3 }
msg3 = End
"""

        result = validate_resource(ftl)

        # If chain exceeds default max_depth, check formatting
        # (Depends on MAX_DEPTH constant; may not trigger with only 4 nodes)
        chain_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]

        # If warning exists, check formatting
        if chain_warnings:
            assert chain_warnings[0].context is not None
            context = chain_warnings[0].context
            # Messages should be formatted without dash
            assert "msg0" in context or "msg1" in context
            # Should NOT have dash prefix for messages
            assert "-msg0" not in context

    def test_term_chain_formatted_with_dash_prefix(self) -> None:
        """Term-only chain formatted with dash prefixes."""
        # Create chain long enough to exceed max_depth
        chain_length = MAX_DEPTH + 5
        lines = []
        for i in range(chain_length):
            if i < chain_length - 1:
                lines.append(f"-term{i} = {{ -term{i+1} }}")
            else:
                lines.append(f"-term{i} = End")

        ftl = "\n".join(lines)
        result = validate_resource(ftl)

        chain_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]

        assert len(chain_warnings) > 0
        assert chain_warnings[0].context is not None
        # Terms should be formatted with dash prefix
        # Check that context contains "-term" pattern
        context = chain_warnings[0].context
        assert "-term" in context

    def test_mixed_message_term_chain_formatted_correctly(self) -> None:
        """Mixed message/term chain formatted with appropriate prefixes."""
        # Create mixed chain: msg0 -> term1 -> msg2 -> term3 -> ...
        chain_length = MAX_DEPTH + 5
        lines = []
        for i in range(chain_length):
            if i % 2 == 0:
                # Even indices are messages
                if i < chain_length - 1:
                    next_ref = f"-term{i+1}" if (i + 1) % 2 == 1 else f"msg{i+1}"
                    lines.append(f"msg{i} = {{ {next_ref} }}")
                else:
                    lines.append(f"msg{i} = End")
            # Odd indices are terms
            elif i < chain_length - 1:
                next_ref = f"-term{i+1}" if (i + 1) % 2 == 1 else f"msg{i+1}"
                lines.append(f"-term{i} = {{ {next_ref} }}")
            else:
                lines.append(f"-term{i} = End")

        ftl = "\n".join(lines)
        result = validate_resource(ftl)

        chain_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]

        assert len(chain_warnings) > 0
        assert chain_warnings[0].context is not None


# ============================================================================
# Integration Tests
# ============================================================================


class TestChainDepthIntegration:
    """Integration tests for chain depth validation."""

    def test_validate_resource_detects_long_chain(self) -> None:
        """validate_resource detects and warns about long chains."""
        chain_length = MAX_DEPTH + 10
        lines = []
        for i in range(chain_length):
            if i < chain_length - 1:
                lines.append(f"msg{i} = {{ msg{i+1} }}")
            else:
                lines.append(f"msg{i} = End")

        ftl = "\n".join(lines)
        result = validate_resource(ftl)

        # Should have chain depth warning
        chain_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]
        assert len(chain_warnings) > 0

        # Warning should mention the chain depth
        warning = chain_warnings[0]
        assert f"{chain_length}" in warning.message or f"{chain_length}" in (
            warning.context or ""
        )

    def test_empty_graph_no_chain_warnings(self) -> None:
        """Empty dependency graph produces no chain warnings."""
        graph: dict[str, set[str]] = {}
        warnings = _detect_long_chains(graph)

        assert len(warnings) == 0

    def test_single_node_no_chain_warnings(self) -> None:
        """Single node with no dependencies produces no chain warnings."""
        graph: dict[str, set[str]] = {"msg:single": set()}
        warnings = _detect_long_chains(graph)

        assert len(warnings) == 0

    def test_independent_short_chains_no_warning(self) -> None:
        """Multiple independent short chains produce no warnings."""
        # Create two independent chains, each below MAX_DEPTH
        ftl = """
chain1_0 = { chain1_1 }
chain1_1 = { chain1_2 }
chain1_2 = End

chain2_0 = { chain2_1 }
chain2_1 = { chain2_2 }
chain2_2 = End
"""

        result = validate_resource(ftl)

        chain_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]
        # Short chains should not trigger warnings
        assert len(chain_warnings) == 0

    def test_diamond_dag_pattern_memoization(self) -> None:
        """Diamond DAG pattern exercises memoization in longest path computation.

        Creates a diamond structure where multiple paths converge on shared nodes.
        This triggers the memoization path in _compute_longest_paths where a node
        is already computed when encountered via a different path.

        Graph structure:
            top -> {left, right}
            left -> bottom
            right -> bottom
            bottom -> end
        """
        ftl = """
top = { left } { right }
left = { bottom }
right = { bottom }
bottom = { end }
end = Final
"""

        result = validate_resource(ftl)

        # Diamond structure itself shouldn't produce chain warnings (depth is 4)
        # The test verifies the memoization code path is exercised correctly
        chain_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]
        assert len(chain_warnings) == 0

    def test_complex_dag_with_shared_subgraphs(self) -> None:
        """Complex DAG with multiple shared subgraphs exercises full memoization.

        Creates a more complex DAG where multiple branches share common subgraphs,
        ensuring the memoization optimization in _compute_longest_paths is fully
        exercised across different entry points.
        """
        ftl = """
a = { b } { c }
b = { d }
c = { d }
d = { e } { f }
e = { g }
f = { g }
g = Terminal
"""

        result = validate_resource(ftl)

        # Verify no errors and structure is valid
        assert result.is_valid
        # DAG depth is only 6, shouldn't exceed MAX_DEPTH
        chain_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]
        assert len(chain_warnings) == 0
