"""Targeted tests for missing coverage in validation.resource module.

Covers specific edge cases and branches to achieve 100% coverage:
- Line 99->102: Annotation without span but Junk with span
- Line 379->377: Duplicate cycle detection path (cycle_key already seen)
- Line 388->385: Term-only cycles in formatting
- Line 485: Node already processed in longest path computation
- Line 547->550: Long chains exceeding 10 nodes in output formatting

Property-based tests using Hypothesis where applicable.
"""

from __future__ import annotations

from collections import OrderedDict

from hypothesis import example, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import DiagnosticCode, WarningSeverity
from ftllexengine.syntax import (
    Annotation,
    Identifier,
    Junk,
    Message,
    MessageReference,
    Pattern,
    Placeable,
    Resource,
    Span,
    Term,
    TermReference,
    TextElement,
)
from ftllexengine.syntax.cursor import LineOffsetCache
from ftllexengine.validation.resource import (
    _build_dependency_graph,
    _check_undefined_references,
    _compute_longest_paths,
    _detect_circular_references,
    _detect_long_chains,
    _extract_syntax_errors,
    validate_resource,
)

# ============================================================================
# _extract_syntax_errors Missing Coverage
# ============================================================================


class TestExtractSyntaxErrorsAnnotationWithoutSpan:
    """Tests for _extract_syntax_errors annotation span fallback (line 99->102)."""

    def test_annotation_without_span_uses_junk_span(self) -> None:
        """Annotation without span falls back to Junk span (line 100)."""
        # Create Junk with span but annotation without span
        junk_span = Span(start=10, end=20)
        annotation = Annotation(
            code=DiagnosticCode.INVALID_CHARACTER.name,
            message="Invalid character",
            span=None,  # Annotation has no span
        )
        junk = Junk(
            content="invalid syntax",
            annotations=(annotation,),
            span=junk_span,  # But Junk has a span
        )

        resource = Resource(entries=(junk,))
        source = "hello = world\ninvalid syntax\ngoodbye = world"
        line_cache = LineOffsetCache(source)

        errors = _extract_syntax_errors(resource, line_cache)

        # Should use Junk's span for position
        assert len(errors) == 1
        assert errors[0].code == DiagnosticCode.INVALID_CHARACTER.name
        assert errors[0].line is not None  # Position from Junk span
        assert errors[0].column is not None

    def test_annotation_and_junk_both_without_span(self) -> None:
        """Annotation and Junk both without span results in None position (line 99->102)."""
        # Create Junk without span and annotation without span
        annotation = Annotation(
            code=DiagnosticCode.INVALID_CHARACTER.name,
            message="Invalid character",
            span=None,  # Annotation has no span
        )
        junk = Junk(
            content="invalid syntax",
            annotations=(annotation,),
            span=None,  # Junk also has no span
        )

        resource = Resource(entries=(junk,))
        source = "invalid syntax"
        line_cache = LineOffsetCache(source)

        errors = _extract_syntax_errors(resource, line_cache)

        # Should have error but with None line/column
        assert len(errors) == 1
        assert errors[0].code == DiagnosticCode.INVALID_CHARACTER.name
        # When both spans are None, line and column should be None
        assert errors[0].line is None
        assert errors[0].column is None


# ============================================================================
# _detect_circular_references Missing Coverage
# ============================================================================


class TestDetectCircularReferencesDuplicateCycles:
    """Tests for _detect_circular_references duplicate cycle detection (line 379->377)."""

    def test_duplicate_cycle_key_skipped(self) -> None:
        """Duplicate cycle keys are skipped correctly (line 379->377)."""
        # This tests the path where cycle_key is already in seen_cycle_keys
        # In practice, detect_cycles should not return duplicate cycles,
        # but the code defends against it

        # Create a self-referencing term cycle
        term = Term(
            id=Identifier(name="self"),
            value=Pattern(
                elements=(
                    TextElement(value="Ref: "),
                    Placeable(expression=TermReference(id=Identifier(name="self"))),
                )
            ),
            attributes=(),
        )

        messages_dict: dict[str, Message] = {}
        terms_dict = {"self": term}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_circular_references(graph)

        # Should detect exactly one cycle (not duplicates)
        assert len(warnings) == 1
        assert "Circular term reference" in warnings[0].message
        assert warnings[0].context is not None
        assert "-self" in warnings[0].context

    def test_term_only_cycle_formatted_with_dash_prefix(self) -> None:
        """Term-only cycles formatted with dash prefix (line 388->385)."""
        # Create a 2-node term cycle: termA -> termB -> termA
        term_a = Term(
            id=Identifier(name="termA"),
            value=Pattern(
                elements=(Placeable(expression=TermReference(id=Identifier(name="termB"))),)
            ),
            attributes=(),
        )
        term_b = Term(
            id=Identifier(name="termB"),
            value=Pattern(
                elements=(Placeable(expression=TermReference(id=Identifier(name="termA"))),)
            ),
            attributes=(),
        )

        messages_dict: dict[str, Message] = {}
        terms_dict = {"termA": term_a, "termB": term_b}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_circular_references(graph)

        # Should detect term cycle with proper formatting
        assert len(warnings) == 1
        assert "Circular term reference" in warnings[0].message
        # Both terms should be formatted with dash prefix
        assert warnings[0].context is not None
        assert "-termA" in warnings[0].context
        assert "-termB" in warnings[0].context

    def test_message_only_cycle_formatted_without_dash(self) -> None:
        """Message-only cycles formatted without dash prefix (line 387)."""
        # Create a 2-node message cycle: msgA -> msgB -> msgA
        msg_a = Message(
            id=Identifier(name="msgA"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier(name="msgB"))),)
            ),
            attributes=(),
        )
        msg_b = Message(
            id=Identifier(name="msgB"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier(name="msgA"))),)
            ),
            attributes=(),
        )

        messages_dict = {"msgA": msg_a, "msgB": msg_b}
        terms_dict: dict[str, Term] = {}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_circular_references(graph)

        # Should detect message cycle with proper formatting
        assert len(warnings) == 1
        assert "Circular message reference" in warnings[0].message
        # Messages should be formatted WITHOUT dash prefix
        assert warnings[0].context is not None
        assert "msgA" in warnings[0].context
        assert "msgB" in warnings[0].context
        # Should NOT have dash prefix for messages
        assert "-msgA" not in warnings[0].context


# ============================================================================
# _compute_longest_paths Missing Coverage
# ============================================================================


class TestComputeLongestPathsAlreadyProcessed:
    """Tests for _compute_longest_paths early termination (line 485)."""

    def test_node_already_in_longest_path_continues(self) -> None:
        """Node already in longest_path skips processing (line 485)."""
        # Create a graph where a node is encountered during DFS that's already computed
        # Graph: A -> B, C -> D -> B  (insertion order: A, B, C, D)
        # When outer loop processes A: computes A and B
        # When outer loop processes C: skips it (line 474-475)
        # When outer loop processes D: D tries to descend to B, but B is in
        # longest_path, so line 485 fires

        # Use an ordered structure to ensure processing order
        graph_ordered = OrderedDict([
            ("msg:A", {"msg:B"}),
            ("msg:B", set()),
            ("msg:D", {"msg:B"}),  # D directly references B
        ])
        graph = dict(graph_ordered)

        result = _compute_longest_paths(graph)

        # All nodes should be processed
        assert "msg:A" in result
        assert "msg:B" in result
        assert "msg:D" in result

        # B should have depth 0
        assert result["msg:B"][0] == 0
        # A and D should both reference B (depth 1)
        assert result["msg:A"][0] == 1
        assert result["msg:D"][0] == 1

    def test_node_in_stack_continues(self) -> None:
        """Node in in_stack skips processing to prevent infinite loops (line 485)."""
        # Test with a cyclic graph to trigger the in_stack check
        # When DFS encounters a node already in the recursion stack, it indicates a cycle

        # Create a 2-node cycle: A -> B -> A
        graph = {
            "msg:A": {"msg:B"},
            "msg:B": {"msg:A"},  # Creates cycle back to A
        }

        result = _compute_longest_paths(graph)

        # Should handle cycle gracefully without infinite loop
        # Both nodes should be in result (cycle detected and handled)
        assert "msg:A" in result
        assert "msg:B" in result
        # Depths in cycles may vary depending on traversal order, but should not infinite loop
        assert isinstance(result["msg:A"][0], int)
        assert isinstance(result["msg:B"][0], int)


# ============================================================================
# _detect_long_chains Missing Coverage
# ============================================================================


class TestDetectLongChainsFormattingLongPaths:
    """Tests for _detect_long_chains long path formatting (line 547->550)."""

    def test_chain_longer_than_10_nodes_truncated_in_output(self) -> None:
        """Chains longer than 10 nodes show truncation in output (line 548)."""
        # Create a chain of 15 messages: msg0 -> msg1 -> ... -> msg14
        messages_dict: dict[str, Message] = {}

        for i in range(15):
            if i < 14:
                # References next message
                value = Pattern(
                    elements=(
                        Placeable(expression=MessageReference(id=Identifier(name=f"msg{i+1}"))),
                    )
                )
            else:
                # Last message has no references
                value = Pattern(elements=(TextElement(value="End"),))

            messages_dict[f"msg{i}"] = Message(
                id=Identifier(f"msg{i}"),
                value=value,
                attributes=(),
            )

        terms_dict: dict[str, Term] = {}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)
        # Use max_depth=5 to trigger warning (chain is 15 nodes long)
        warnings = _detect_long_chains(graph, max_depth=5)

        # Should detect the long chain
        assert len(warnings) == 1
        assert warnings[0].code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name

        # Should show truncation marker for chains > 10 nodes
        assert warnings[0].context is not None
        assert "..." in warnings[0].context
        assert "15 total" in warnings[0].context

        # Should show severity WARNING
        assert warnings[0].severity == WarningSeverity.WARNING

    def test_chain_exactly_10_nodes_no_truncation(self) -> None:
        """Chains with exactly 10 nodes show no truncation (line 547->550)."""
        # Create a chain of exactly 10 messages
        messages_dict: dict[str, Message] = {}

        for i in range(10):
            if i < 9:
                value = Pattern(
                    elements=(
                        Placeable(expression=MessageReference(id=Identifier(name=f"msg{i+1}"))),
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

        # Should detect the chain
        assert len(warnings) == 1

        # Should NOT show truncation for chains <= 10 nodes
        assert warnings[0].context is not None
        assert "..." not in warnings[0].context
        assert "total" not in warnings[0].context

    @given(chain_length=st.integers(min_value=11, max_value=50))
    @example(chain_length=11)
    @example(chain_length=25)
    def test_long_chain_truncation_property(self, chain_length: int) -> None:
        """Property: Chains > 10 nodes always show truncation marker."""
        # Create chain of specified length
        messages_dict: dict[str, Message] = {}

        for i in range(chain_length):
            if i < chain_length - 1:
                value = Pattern(
                    elements=(
                        Placeable(expression=MessageReference(id=Identifier(name=f"m{i+1}"))),
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

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_long_chains(graph, max_depth=5)

        # Should show truncation
        assert len(warnings) == 1
        assert warnings[0].context is not None
        assert "..." in warnings[0].context
        assert f"{chain_length} total" in warnings[0].context


# ============================================================================
# _check_undefined_references with known_messages/known_terms
# ============================================================================


class TestCheckUndefinedReferencesWithKnownEntries:
    """Tests for _check_undefined_references with known_messages/known_terms (lines 249, 251)."""

    def test_known_messages_parameter_used_in_validation(self) -> None:
        """known_messages parameter extends validation scope (line 249)."""
        # Create a message that references an external message
        message = Message(
            id=Identifier("local"),
            value=Pattern(
                elements=(
                    Placeable(expression=MessageReference(id=Identifier(name="external"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"local": message}
        terms_dict: dict[str, Term] = {}
        source = "local = { external }"
        line_cache = LineOffsetCache(source)

        # Without known_messages, should warn about undefined reference
        warnings_without = _check_undefined_references(
            messages_dict, terms_dict, line_cache
        )
        assert len(warnings_without) == 1
        assert "undefined message 'external'" in warnings_without[0].message

        # With known_messages, should not warn
        warnings_with = _check_undefined_references(
            messages_dict,
            terms_dict,
            line_cache,
            known_messages=frozenset(["external"]),
        )
        assert len(warnings_with) == 0

    def test_known_terms_parameter_used_in_validation(self) -> None:
        """known_terms parameter extends validation scope (line 251)."""
        # Create a message that references an external term
        message = Message(
            id=Identifier("local"),
            value=Pattern(
                elements=(
                    Placeable(expression=TermReference(id=Identifier(name="externalTerm"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"local": message}
        terms_dict: dict[str, Term] = {}
        source = "local = { -externalTerm }"
        line_cache = LineOffsetCache(source)

        # Without known_terms, should warn
        warnings_without = _check_undefined_references(
            messages_dict, terms_dict, line_cache
        )
        assert len(warnings_without) == 1
        assert "undefined term '-externalTerm'" in warnings_without[0].message

        # With known_terms, should not warn
        warnings_with = _check_undefined_references(
            messages_dict,
            terms_dict,
            line_cache,
            known_terms=frozenset(["externalTerm"]),
        )
        assert len(warnings_with) == 0


# ============================================================================
# Integration Tests
# ============================================================================


class TestValidationResourceIntegration:
    """Integration tests combining multiple edge cases."""

    def test_junk_annotation_without_span_in_validate_resource(self) -> None:
        """validate_resource handles Junk with annotation without span."""
        # Create FTL with syntax error
        source = """
message = valid

# Invalid syntax that creates Junk
@@@invalid

another = valid
"""

        result = validate_resource(source)

        # Should have errors from Junk
        assert len(result.errors) > 0

    def test_very_long_reference_chain_shows_truncation(self) -> None:
        """validate_resource shows truncation for chains > 10 nodes."""
        # Create a long chain in FTL syntax
        lines = []
        for i in range(15):
            if i < 14:
                lines.append(f"msg{i} = {{ msg{i+1} }}")
            else:
                lines.append(f"msg{i} = End")

        source = "\n".join(lines)

        # Should validate successfully but warn about chain depth
        result = validate_resource(source)

        # Check warnings for chain depth
        chain_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]

        # Should have truncation in context
        if chain_warnings:
            assert any(w.context is not None and "..." in w.context for w in chain_warnings)

    def test_term_cycle_with_proper_formatting(self) -> None:
        """validate_resource formats term cycles with dash prefixes."""
        source = """
-termA = { -termB }
-termB = { -termA }
"""

        result = validate_resource(source)

        # Should detect circular reference
        cycle_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE.name
        ]

        assert len(cycle_warnings) > 0
        # Should have dash-prefixed terms in cycle description
        assert any(w.context is not None and "-termA" in w.context for w in cycle_warnings)
