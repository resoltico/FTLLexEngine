"""Final coverage tests for validation/resource.py to achieve 100%.

Targets specific uncovered lines:
- Lines 191-192: Shadow warnings for known messages
- Lines 210-211: Duplicate attribute warnings for messages
- Lines 262-263: Shadow warnings for known terms
- Lines 280-295: Duplicate attribute warnings for terms
- Lines 425->423, 434->431: Branch coverage in _detect_circular_references
- Lines 516-519, 522-525: known_messages/known_terms in graph building
- Line 556: in_stack check in _compute_longest_paths

Uses Hypothesis for property-based testing where applicable per CLAUDE.md.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.diagnostics import DiagnosticCode, WarningSeverity
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
    validate_resource,
)


class TestShadowWarnings:
    """Test shadow warnings when new entries conflict with known entries."""

    def test_message_shadows_known_message(self) -> None:
        """Message ID shadows known_messages entry (lines 191-192)."""
        ftl = "greeting = Hello"

        # Validate with known_messages containing "greeting"
        result = validate_resource(
            ftl,
            known_messages=frozenset(["greeting"]),
        )

        # Should have shadow warning
        shadow_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
            and "greeting" in w.message.lower()
            and "message" in w.message.lower()
        ]
        assert len(shadow_warnings) > 0
        assert shadow_warnings[0].severity == WarningSeverity.WARNING
        assert "shadows existing message" in shadow_warnings[0].message

    def test_term_shadows_known_term(self) -> None:
        """Term ID shadows known_terms entry (lines 262-263)."""
        ftl = "-brand = Firefox"

        # Validate with known_terms containing "brand"
        result = validate_resource(
            ftl,
            known_terms=frozenset(["brand"]),
        )

        # Should have shadow warning
        shadow_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
            and "brand" in w.message.lower()
            and "term" in w.message.lower()
        ]
        assert len(shadow_warnings) > 0
        assert shadow_warnings[0].severity == WarningSeverity.WARNING
        assert "shadows existing term" in shadow_warnings[0].message

    def test_multiple_messages_shadow_known_entries(self) -> None:
        """Multiple messages can shadow known entries simultaneously."""
        ftl = """
greeting = Hello
farewell = Goodbye
"""

        result = validate_resource(
            ftl,
            known_messages=frozenset(["greeting", "farewell"]),
        )

        # Should have shadow warnings for both
        shadow_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        assert len(shadow_warnings) >= 2

    def test_multiple_terms_shadow_known_entries(self) -> None:
        """Multiple terms can shadow known entries simultaneously."""
        ftl = """
-brand = Firefox
-org = Mozilla
"""

        result = validate_resource(
            ftl,
            known_terms=frozenset(["brand", "org"]),
        )

        # Should have shadow warnings for both
        shadow_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        assert len(shadow_warnings) >= 2


class TestDuplicateAttributes:
    """Test duplicate attribute detection in messages and terms."""

    def test_message_duplicate_attribute_warning(self) -> None:
        """Message with duplicate attributes produces warning (lines 210-211)."""
        ftl = """
msg =
    .attr = First value
    .attr = Second value
"""

        result = validate_resource(ftl)

        # Should have duplicate attribute warning
        dup_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
            and "msg" in w.message
            and "attr" in w.message
        ]
        assert len(dup_warnings) > 0
        assert "duplicate attribute" in dup_warnings[0].message.lower()
        assert dup_warnings[0].context == "msg.attr"

    def test_term_duplicate_attribute_warning(self) -> None:
        """Term with duplicate attributes produces warning (lines 280-295)."""
        ftl = """
-term = value
    .attr = First value
    .attr = Second value
"""

        result = validate_resource(ftl)

        # Should have duplicate attribute warning
        dup_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
            and "term" in w.message
            and "attr" in w.message
        ]
        assert len(dup_warnings) > 0
        assert "duplicate attribute" in dup_warnings[0].message.lower()
        assert dup_warnings[0].context == "term.attr"

    def test_message_multiple_duplicate_attributes(self) -> None:
        """Message with multiple duplicate attribute sets."""
        ftl = """
msg = value
    .x = First
    .x = Second
    .y = First
    .y = Second
"""

        result = validate_resource(ftl)

        # Should have warnings for both attributes
        dup_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]
        assert len(dup_warnings) >= 2

    def test_term_multiple_duplicate_attributes(self) -> None:
        """Term with multiple duplicate attribute sets (tests full lines 280-295 block)."""
        ftl = """
-term = value
    .x = First
    .x = Second
    .y = First
    .y = Second
    .z = First
    .z = Second
"""

        result = validate_resource(ftl)

        # Should have warnings for all duplicate attributes
        dup_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
            and "term" in w.message.lower()
        ]
        assert len(dup_warnings) >= 3  # x, y, z

    @given(
        attr_name=st.text(
            min_size=1,
            max_size=10,
            alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        )
    )
    def test_duplicate_attribute_property(self, attr_name: str) -> None:
        """PROPERTY: Duplicate attributes always trigger warnings."""
        ftl = f"""
msg = value
    .{attr_name} = First
    .{attr_name} = Second
"""

        result = validate_resource(ftl)

        # Should have duplicate attribute warning
        dup_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]
        assert len(dup_warnings) > 0


class TestCircularReferenceBranches:
    """Test branch coverage in _detect_circular_references."""

    def test_message_only_cycle_formatting(self) -> None:
        """Message-only cycle uses message-only formatting (line 448 - else branch)."""
        ftl = """
msgA = { msgB }
msgB = { msgC }
msgC = { msgA }
"""

        result = validate_resource(ftl)

        # Should detect message-only circular reference
        cycle_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE.name
        ]
        assert len(cycle_warnings) > 0
        # Should identify as message reference (not cross or term)
        assert "Circular message reference" in cycle_warnings[0].message
        # Should not have cross-reference or term reference
        assert "cross" not in cycle_warnings[0].message.lower()

    def test_cross_type_cycle_message_and_term(self) -> None:
        """Cross-type cycle triggers cross-reference branch (line 444)."""
        ftl = """
msg = { -term }
-term = { msg }
"""

        result = validate_resource(ftl)

        # Should detect cross-type circular reference
        cycle_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE.name
        ]
        assert len(cycle_warnings) > 0
        # Should identify as cross-reference (not message-only or term-only)
        assert "cross-reference" in cycle_warnings[0].message.lower()

    def test_mixed_cycle_with_multiple_types(self) -> None:
        """Complex cycle with both messages and terms."""
        # Create a cycle: msg1 -> term1 -> msg2 -> term2 -> msg1
        msg1 = Message(
            id=Identifier(name="msg1"),
            value=Pattern(
                elements=(Placeable(expression=TermReference(id=Identifier(name="term1"))),)
            ),
            attributes=(),
        )
        term1 = Term(
            id=Identifier(name="term1"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier(name="msg2"))),)
            ),
            attributes=(),
        )
        msg2 = Message(
            id=Identifier(name="msg2"),
            value=Pattern(
                elements=(Placeable(expression=TermReference(id=Identifier(name="term2"))),)
            ),
            attributes=(),
        )
        term2 = Term(
            id=Identifier(name="term2"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier(name="msg1"))),)
            ),
            attributes=(),
        )

        messages_dict = {"msg1": msg1, "msg2": msg2}
        terms_dict = {"term1": term1, "term2": term2}

        # Build graph and detect cycles
        graph = _build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_circular_references(graph)

        # Should detect cross-type cycle
        assert len(warnings) > 0
        assert any("cross-reference" in w.message.lower() for w in warnings)


class TestKnownEntriesInGraph:
    """Test known_messages/known_terms handling in graph building."""

    def test_known_messages_added_as_graph_nodes(self) -> None:
        """known_messages are added as nodes in dependency graph (lines 516-519)."""
        # Create a message that references a known message
        msg = Message(
            id=Identifier(name="local"),
            value=Pattern(
                elements=(
                    Placeable(expression=MessageReference(id=Identifier(name="external"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"local": msg}
        terms_dict: dict[str, Term] = {}

        # Build graph with known_messages
        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_messages=frozenset(["external", "other"]),
        )

        # Graph should contain nodes for both local and known messages
        assert "msg:local" in graph
        assert "msg:external" in graph  # Known message should be in graph
        assert "msg:other" in graph  # Another known message

        # local should reference external
        assert "msg:external" in graph["msg:local"]

        # Known messages have empty dependency sets (we don't have their ASTs)
        assert len(graph["msg:external"]) == 0
        assert len(graph["msg:other"]) == 0

    def test_known_terms_added_as_graph_nodes(self) -> None:
        """known_terms are added as nodes in dependency graph (lines 522-525)."""
        # Create a message that references a known term
        msg = Message(
            id=Identifier(name="local"),
            value=Pattern(
                elements=(
                    Placeable(expression=TermReference(id=Identifier(name="externalTerm"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"local": msg}
        terms_dict: dict[str, Term] = {}

        # Build graph with known_terms
        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_terms=frozenset(["externalTerm", "otherTerm"]),
        )

        # Graph should contain nodes for known terms
        assert "term:externalTerm" in graph
        assert "term:otherTerm" in graph

        # local should reference externalTerm
        assert "term:externalTerm" in graph["msg:local"]

        # Known terms have empty dependency sets
        assert len(graph["term:externalTerm"]) == 0
        assert len(graph["term:otherTerm"]) == 0

    def test_known_entries_and_local_entries_coexist(self) -> None:
        """Known entries and local entries can coexist in the graph."""
        # Local message references known message and local term
        local_msg = Message(
            id=Identifier(name="local"),
            value=Pattern(
                elements=(
                    TextElement(value="Ref: "),
                    Placeable(expression=MessageReference(id=Identifier(name="knownMsg"))),
                    TextElement(value=" "),
                    Placeable(expression=TermReference(id=Identifier(name="localTerm"))),
                )
            ),
            attributes=(),
        )

        # Local term exists
        local_term = Term(
            id=Identifier(name="localTerm"),
            value=Pattern(elements=(TextElement(value="Value"),)),
            attributes=(),
        )

        messages_dict = {"local": local_msg}
        terms_dict = {"localTerm": local_term}

        # Build graph with known entries
        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_messages=frozenset(["knownMsg"]),
            known_terms=frozenset(["knownTerm"]),
        )

        # All nodes should be present
        assert "msg:local" in graph
        assert "msg:knownMsg" in graph
        assert "term:localTerm" in graph
        assert "term:knownTerm" in graph

        # Dependencies should be correct
        assert "msg:knownMsg" in graph["msg:local"]
        assert "term:localTerm" in graph["msg:local"]


class TestComputeLongestPathsInStack:
    """Test in_stack check in _compute_longest_paths (line 556)."""

    def test_node_already_in_longest_path_skips_processing(self) -> None:
        """Node already computed in longest_path is skipped (line 556 - first part of OR)."""
        # Create a diamond-shaped graph:
        #     A
        #    / \
        #   B   C
        #    \ /
        #     D
        # When processing A, it computes B and D (via B).
        # When it later tries to process C, it descends to D, but D is already in longest_path.
        graph = {
            "msg:A": {"msg:B", "msg:C"},
            "msg:B": {"msg:D"},
            "msg:C": {"msg:D"},
            "msg:D": set(),
        }

        result = _compute_longest_paths(graph)

        # All nodes should be processed
        assert "msg:A" in result
        assert "msg:B" in result
        assert "msg:C" in result
        assert "msg:D" in result

        # D should have depth 0, B and C depth 1, A depth 2
        assert result["msg:D"][0] == 0
        assert result["msg:B"][0] == 1
        assert result["msg:C"][0] == 1
        assert result["msg:A"][0] == 2

    def test_in_stack_prevents_infinite_recursion(self) -> None:
        """Nodes in recursion stack are skipped to prevent infinite loops (line 556)."""
        # Create a cycle that will trigger the in_stack check during DFS
        # When processing node A in phase 0, it adds itself to in_stack,
        # then descends to B. If B tries to reference A, A is already in_stack.

        # Simple 2-node cycle
        graph = {
            "msg:A": {"msg:B"},
            "msg:B": {"msg:A"},
        }

        # Should complete without infinite recursion
        result = _compute_longest_paths(graph)

        # Both nodes should be processed
        assert "msg:A" in result
        assert "msg:B" in result

        # Neither should have failed (no exceptions)
        assert isinstance(result["msg:A"], tuple)
        assert isinstance(result["msg:B"], tuple)

    def test_complex_cycle_with_in_stack_check(self) -> None:
        """Complex graph with cycles triggers in_stack checks."""
        # Create a more complex graph with multiple cycles
        # A -> B -> C -> A (cycle)
        # D -> E -> A (connects to cycle)
        graph = {
            "msg:A": {"msg:B"},
            "msg:B": {"msg:C"},
            "msg:C": {"msg:A"},  # Cycle back to A
            "msg:D": {"msg:E"},
            "msg:E": {"msg:A"},  # Connects to cycle
        }

        result = _compute_longest_paths(graph)

        # All nodes should be processed despite cycles
        assert "msg:A" in result
        assert "msg:B" in result
        assert "msg:C" in result
        assert "msg:D" in result
        assert "msg:E" in result

    def test_self_referencing_node_in_stack(self) -> None:
        """Self-referencing node triggers in_stack check."""
        # Node that references itself
        graph = {
            "msg:self": {"msg:self"},
        }

        result = _compute_longest_paths(graph)

        # Should handle self-reference without infinite loop
        assert "msg:self" in result
        # Depth should be 0 (can't extend path through cycle)
        depth, path = result["msg:self"]
        assert isinstance(depth, int)
        assert "msg:self" in path


class TestIntegrationEdgeCases:
    """Integration tests combining multiple edge cases."""

    def test_shadow_and_duplicate_attributes_together(self) -> None:
        """Shadow warnings and duplicate attributes can occur together."""
        ftl = """
msg = value
    .attr = First
    .attr = Second
"""

        result = validate_resource(
            ftl,
            known_messages=frozenset(["msg"]),
        )

        # Should have both shadow and duplicate attribute warnings
        shadow_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        dup_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]

        assert len(shadow_warnings) > 0
        assert len(dup_warnings) > 0

    def test_cross_resource_cycle_with_known_entries(self) -> None:
        """Cycles spanning current resource and known entries."""
        # Current resource has msg1 -> knownMsg
        # If knownMsg -> msg1, creates cross-resource cycle
        # We can't test this directly since we don't have known entry ASTs,
        # but we can verify the graph structure supports it

        msg1 = Message(
            id=Identifier(name="msg1"),
            value=Pattern(
                elements=(
                    Placeable(expression=MessageReference(id=Identifier(name="knownMsg"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"msg1": msg1}
        terms_dict: dict[str, Term] = {}

        # Build graph with known message
        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_messages=frozenset(["knownMsg"]),
        )

        # Graph should support detecting cycles through known entries
        assert "msg:msg1" in graph
        assert "msg:knownMsg" in graph
        assert "msg:knownMsg" in graph["msg:msg1"]

        # If knownMsg had a dependency back to msg1, cycle detection would find it
        # Simulate this by manually adding the back-edge for testing
        graph["msg:knownMsg"] = {"msg:msg1"}

        # Should detect the cycle
        warnings = _detect_circular_references(graph)
        assert len(warnings) > 0

    @given(
        msg_count=st.integers(min_value=2, max_value=5),
        term_count=st.integers(min_value=2, max_value=5),
    )
    def test_shadow_warnings_property(self, msg_count: int, term_count: int) -> None:
        """PROPERTY: Shadow warnings scale with number of shadowed entries."""
        # Create messages that shadow known entries
        msg_lines = [f"msg{i} = Value {i}" for i in range(msg_count)]
        term_lines = [f"-term{i} = Value {i}" for i in range(term_count)]

        ftl = "\n".join(msg_lines + term_lines)

        known_msgs = frozenset([f"msg{i}" for i in range(msg_count)])
        known_terms = frozenset([f"term{i}" for i in range(term_count)])

        result = validate_resource(
            ftl,
            known_messages=known_msgs,
            known_terms=known_terms,
        )

        # Should have shadow warnings for all entries
        shadow_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        assert len(shadow_warnings) == msg_count + term_count
