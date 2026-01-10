"""Tests for cross-resource validation with known_messages and known_terms.

Covers scenarios where validation involves existing bundle entries:
- Shadow warnings when new entries conflict with known entries
- Undefined reference checking with known entries
- Cycle detection spanning known and new entries
- Dependency graph building with known entries

Uses Hypothesis for property-based testing where applicable.
"""

from __future__ import annotations

from hypothesis import example, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import DiagnosticCode, WarningSeverity
from ftllexengine.syntax import (
    Identifier,
    Message,
    MessageReference,
    Pattern,
    Placeable,
    Resource,
    Term,
    TermReference,
    TextElement,
)
from ftllexengine.syntax.cursor import LineOffsetCache
from ftllexengine.validation.resource import (
    _build_dependency_graph,
    _check_undefined_references,
    _collect_entries,
    validate_resource,
)

# ============================================================================
# Shadow Warnings
# ============================================================================


class TestShadowWarnings:
    """Test shadow warnings when new entries conflict with known entries."""

    def test_message_shadows_known_message(self) -> None:
        """Message ID shadows known_messages entry."""
        ftl = "greeting = Hello"

        result = validate_resource(
            ftl,
            known_messages=frozenset(["greeting"]),
        )

        shadow_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
            and "greeting" in w.message.lower()
            and "message" in w.message.lower()
        ]
        assert len(shadow_warnings) > 0
        assert shadow_warnings[0].severity == WarningSeverity.WARNING
        assert "shadows existing message" in shadow_warnings[0].message

    def test_term_shadows_known_term(self) -> None:
        """Term ID shadows known_terms entry."""
        ftl = "-brand = Firefox"

        result = validate_resource(
            ftl,
            known_terms=frozenset(["brand"]),
        )

        shadow_warnings = [
            w
            for w in result.warnings
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

        shadow_warnings = [
            w
            for w in result.warnings
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

        shadow_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        assert len(shadow_warnings) >= 2

    @given(
        num_shadows=st.integers(min_value=1, max_value=10),
    )
    @example(num_shadows=1)
    @example(num_shadows=5)
    def test_shadow_warnings_property(self, num_shadows: int) -> None:
        """Property: Each shadowed entry produces exactly one warning."""
        # Create FTL with N messages
        lines = [f"msg{i} = Value {i}" for i in range(num_shadows)]
        ftl = "\n".join(lines)

        # All messages shadow known entries
        known = frozenset([f"msg{i}" for i in range(num_shadows)])

        result = validate_resource(ftl, known_messages=known)

        shadow_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]

        # Should have exactly num_shadows shadow warnings
        assert len(shadow_warnings) == num_shadows


# ============================================================================
# Undefined References with Known Entries
# ============================================================================


class TestUndefinedReferencesWithKnownEntries:
    """Test undefined reference checking with known_messages/known_terms."""

    def test_known_messages_prevent_undefined_warning(self) -> None:
        """Message referencing known_messages entry produces no warning."""
        # Create message that references external message
        message = Message(
            id=Identifier("local"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=MessageReference(id=Identifier(name="external"))
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {"local": message}
        terms_dict: dict[str, Term] = {}
        source = "local = { external }"
        line_cache = LineOffsetCache(source)

        # Without known_messages, should warn
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

    def test_known_terms_prevent_undefined_warning(self) -> None:
        """Message referencing known_terms entry produces no warning."""
        message = Message(
            id=Identifier("local"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(id=Identifier(name="externalTerm"))
                    ),
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

    def test_cross_resource_reference_validation_integration(self) -> None:
        """Integration test: validate_resource with cross-resource references."""
        ftl = """
local = { external }
term-local = { -term-external }
"""

        # Without known entries, should have undefined reference warnings
        result_without = validate_resource(ftl)
        undef_warnings_without = [
            w
            for w in result_without.warnings
            if w.code == DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE.name
        ]
        assert len(undef_warnings_without) == 2

        # With known entries, should have no undefined reference warnings
        result_with = validate_resource(
            ftl,
            known_messages=frozenset(["external"]),
            known_terms=frozenset(["term-external"]),
        )
        undef_warnings_with = [
            w
            for w in result_with.warnings
            if w.code == DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE.name
        ]
        assert len(undef_warnings_with) == 0


# ============================================================================
# Dependency Graph with Known Entries
# ============================================================================


class TestDependencyGraphWithKnownEntries:
    """Test dependency graph building with known_messages/known_terms."""

    def test_known_messages_added_as_graph_nodes(self) -> None:
        """Known messages are added to graph as nodes with no outgoing edges."""
        messages_dict: dict[str, Message] = {}
        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_messages=frozenset(["known1", "known2"]),
        )

        # Known messages should be in graph
        assert "msg:known1" in graph
        assert "msg:known2" in graph
        # Should have no outgoing edges (we don't have their ASTs)
        assert graph["msg:known1"] == set()
        assert graph["msg:known2"] == set()

    def test_known_terms_added_as_graph_nodes(self) -> None:
        """Known terms are added to graph as nodes with no outgoing edges."""
        messages_dict: dict[str, Message] = {}
        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_terms=frozenset(["known1", "known2"]),
        )

        # Known terms should be in graph
        assert "term:known1" in graph
        assert "term:known2" in graph
        # Should have no outgoing edges
        assert graph["term:known1"] == set()
        assert graph["term:known2"] == set()

    def test_local_entries_reference_known_entries_in_graph(self) -> None:
        """Local entries that reference known entries have edges to them in graph."""
        # Create local message that references known message
        message = Message(
            id=Identifier("local"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=MessageReference(id=Identifier(name="known"))
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {"local": message}
        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_messages=frozenset(["known"]),
        )

        # Graph should have both nodes
        assert "msg:local" in graph
        assert "msg:known" in graph
        # Local should have edge to known
        assert "msg:known" in graph["msg:local"]
        # Known should have no outgoing edges
        assert graph["msg:known"] == set()

    def test_cross_resource_cycle_detection(self) -> None:
        """Cycles can span current resource and known entries."""
        # Create: localA -> knownB -> (back to localA via bundle)
        # Simulate by: localA -> knownB, localB -> localA where localB is "known"
        ftl = "localA = { knownB }"

        # If knownB references localA, there's a cycle
        # We can't test this directly since we don't have knownB's AST,
        # but we can test that the graph structure supports it

        result = validate_resource(
            ftl,
            known_messages=frozenset(["knownB"]),
        )

        # Should validate without error
        # (The actual cycle would only be detected if we had knownB's AST showing
        # it references localA, which we can't provide in this test)
        assert result.is_valid or len(result.errors) == 0


# ============================================================================
# Shadow and Duplicate Interaction
# ============================================================================


class TestShadowAndDuplicateInteraction:
    """Test interaction between shadow warnings and duplicate ID warnings."""

    def test_shadow_and_duplicate_both_trigger(self) -> None:
        """Both shadow and duplicate warnings can occur together."""
        ftl = """
msg = First
msg = Second
"""

        result = validate_resource(
            ftl,
            known_messages=frozenset(["msg"]),
        )

        # Should have both shadow and duplicate warnings
        shadow_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        dup_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ID.name
        ]

        # Both types should be present
        assert len(shadow_warnings) > 0
        assert len(dup_warnings) > 0

    def test_collect_entries_with_known_messages_direct_call(self) -> None:
        """Direct test of _collect_entries with known_messages parameter."""
        # Create duplicate messages
        msg1 = Message(
            id=Identifier("greeting"),
            value=Pattern(elements=(TextElement(value="First"),)),
            attributes=(),
        )
        msg2 = Message(
            id=Identifier("greeting"),
            value=Pattern(elements=(TextElement(value="Second"),)),
            attributes=(),
        )

        resource = Resource(entries=(msg1, msg2))
        source = "greeting = First\ngreeting = Second"
        line_cache = LineOffsetCache(source)

        # Call with known_messages
        _messages_dict, _terms_dict, warnings = _collect_entries(
            resource,
            line_cache,
            known_messages=frozenset(["greeting"]),
        )

        # Should have duplicate warning (same ID appears twice in resource)
        dup_warnings = [
            w
            for w in warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ID.name
        ]
        assert len(dup_warnings) == 1

        # Should have shadow warning (ID shadows known entry)
        shadow_warnings = [
            w
            for w in warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        assert len(shadow_warnings) >= 1

    def test_collect_entries_with_known_terms_direct_call(self) -> None:
        """Direct test of _collect_entries with known_terms parameter."""
        term1 = Term(
            id=Identifier("brand"),
            value=Pattern(elements=(TextElement(value="First"),)),
            attributes=(),
        )
        term2 = Term(
            id=Identifier("brand"),
            value=Pattern(elements=(TextElement(value="Second"),)),
            attributes=(),
        )

        resource = Resource(entries=(term1, term2))
        source = "-brand = First\n-brand = Second"
        line_cache = LineOffsetCache(source)

        _messages_dict, _terms_dict, warnings = _collect_entries(
            resource,
            line_cache,
            known_terms=frozenset(["brand"]),
        )

        # Should have duplicate warning
        dup_warnings = [
            w
            for w in warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ID.name
        ]
        assert len(dup_warnings) == 1

        # Should have shadow warning
        shadow_warnings = [
            w
            for w in warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        assert len(shadow_warnings) >= 1
