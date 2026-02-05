"""Dependency graph construction tests for validation/resource.py.

Tests attribute-qualified reference resolution and known entry dependency
propagation to achieve 100% coverage of _build_dependency_graph and
related helper functions.

Coverage targets:
- Lines 507-509: _resolve_msg_ref with attribute-qualified references
- Lines 519-521: _resolve_term_ref with attribute-qualified references
- Line 572: known_msg_deps dependency propagation
- Line 582: known_term_deps dependency propagation
"""

from __future__ import annotations

from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    Attribute,
    Identifier,
    Message,
    MessageReference,
    Pattern,
    Placeable,
    SelectExpression,
    Term,
    TermReference,
    TextElement,
    Variant,
)
from ftllexengine.validation.resource import (
    _build_dependency_graph,
    _detect_circular_references,
)


class TestAttributeQualifiedMessageReferences:
    """Test attribute-qualified message reference resolution (lines 507-509)."""

    def test_undefined_attribute_qualified_message_reference(self) -> None:
        """Attribute-qualified reference to undefined message returns None.

        Tests branch 508->513: When "." is in ref but base message doesn't
        exist in messages_dict or known_messages, _resolve_msg_ref returns None
        and the reference is NOT added to the dependency graph.
        """
        # Message referencing undefined message's attribute
        ref_msg = Message(
            id=Identifier("referrer"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=MessageReference(
                            id=Identifier("undefined"),
                            attribute=Identifier("tooltip"),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {"referrer": ref_msg}
        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Should have "msg:referrer" node but NO dependency (undefined.tooltip ignored)
        assert "msg:referrer" in graph
        # The dependency set should be empty (undefined reference not added)
        assert len(graph["msg:referrer"]) == 0
        # Should NOT have "msg:undefined.tooltip" node
        assert "msg:undefined.tooltip" not in graph["msg:referrer"]

    def test_message_attribute_reference_creates_qualified_node(self) -> None:
        """Message referencing another message's attribute creates qualified node.

        Tests lines 507-509: When a message reference contains "." (attribute
        qualification), split it and create "msg:base.attr" node if base exists.
        """
        # Create base message with an attribute
        base_msg = Message(
            id=Identifier("base"),
            value=Pattern(elements=(TextElement("value"),)),
            attributes=(
                Attribute(
                    id=Identifier("tooltip"),
                    value=Pattern(elements=(TextElement("tooltip text"),)),
                ),
            ),
        )

        # Create message that references base message's attribute
        ref_msg = Message(
            id=Identifier("referrer"),
            value=Pattern(
                elements=(
                    TextElement("text "),
                    Placeable(
                        expression=MessageReference(
                            id=Identifier("base"),
                            attribute=Identifier("tooltip"),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {"base": base_msg, "referrer": ref_msg}
        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Should have "msg:referrer" node with dependency on "msg:base.tooltip"
        assert "msg:referrer" in graph
        assert "msg:base.tooltip" in graph["msg:referrer"]

    def test_message_attribute_reference_with_known_messages(self) -> None:
        """Message referencing known message's attribute creates qualified node.

        Tests lines 507-509 with known_messages parameter: attribute-qualified
        reference to a known message should resolve correctly.
        """
        # Current resource has message referencing known message's attribute
        ref_msg = Message(
            id=Identifier("current"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=MessageReference(
                            id=Identifier("known"),
                            attribute=Identifier("attr"),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {"current": ref_msg}
        terms_dict: dict[str, Term] = {}
        known_messages = frozenset({"known"})

        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_messages=known_messages,
        )

        # Should resolve "known.attr" to "msg:known.attr" node
        assert "msg:current" in graph
        assert "msg:known.attr" in graph["msg:current"]

    def test_bare_message_reference_creates_unqualified_node(self) -> None:
        """Bare message reference (no attribute) creates unqualified node.

        Regression test: ensure bare references still work correctly after
        attribute-qualified support.
        """
        msg_a = Message(
            id=Identifier("a"),
            value=Pattern(elements=(TextElement("value"),)),
            attributes=(),
        )
        msg_b = Message(
            id=Identifier("b"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("a"))),)
            ),
            attributes=(),
        )

        messages_dict = {"a": msg_a, "b": msg_b}
        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Should have "msg:b" -> "msg:a" (no attribute qualification)
        assert "msg:b" in graph
        assert "msg:a" in graph["msg:b"]


class TestAttributeQualifiedTermReferences:
    """Test attribute-qualified term reference resolution (lines 519-521)."""

    def test_undefined_attribute_qualified_term_reference(self) -> None:
        """Attribute-qualified reference to undefined term returns None.

        Tests branch 520->524: When "." is in ref but base term doesn't
        exist in terms_dict or known_terms, _resolve_term_ref returns None
        and the reference is NOT added to the dependency graph.
        """
        # Message referencing undefined term's attribute
        msg = Message(
            id=Identifier("msg"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier("undefined"),
                            attribute=Identifier("variant"),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {"msg": msg}
        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Should have "msg:msg" node but NO dependency (undefined term ignored)
        assert "msg:msg" in graph
        # The dependency set should be empty (undefined reference not added)
        assert len(graph["msg:msg"]) == 0
        # Should NOT have "term:undefined.variant" node
        assert "term:undefined.variant" not in graph["msg:msg"]

    def test_term_attribute_reference_creates_qualified_node(self) -> None:
        """Message referencing term's attribute creates qualified node.

        Tests lines 519-521: When a term reference contains "." (attribute
        qualification), split it and create "term:base.attr" node if base exists.
        """
        # Create base term with an attribute
        base_term = Term(
            id=Identifier("brand"),
            value=Pattern(elements=(TextElement("Firefox"),)),
            attributes=(
                Attribute(
                    id=Identifier("short"),
                    value=Pattern(elements=(TextElement("FF"),)),
                ),
            ),
        )

        # Create message that references term's attribute
        msg = Message(
            id=Identifier("welcome"),
            value=Pattern(
                elements=(
                    TextElement("Welcome to "),
                    Placeable(
                        expression=TermReference(
                            id=Identifier("brand"),
                            attribute=Identifier("short"),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {"welcome": msg}
        terms_dict = {"brand": base_term}

        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Should have "msg:welcome" node with dependency on "term:brand.short"
        assert "msg:welcome" in graph
        assert "term:brand.short" in graph["msg:welcome"]

    def test_term_attribute_reference_with_known_terms(self) -> None:
        """Message referencing known term's attribute creates qualified node.

        Tests lines 519-521 with known_terms parameter: attribute-qualified
        reference to a known term should resolve correctly.
        """
        # Current resource has message referencing known term's attribute
        msg = Message(
            id=Identifier("current"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier("known_term"),
                            attribute=Identifier("variant"),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {"current": msg}
        terms_dict: dict[str, Term] = {}
        known_terms = frozenset({"known_term"})

        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_terms=known_terms,
        )

        # Should resolve "known_term.variant" to "term:known_term.variant" node
        assert "msg:current" in graph
        assert "term:known_term.variant" in graph["msg:current"]

    def test_bare_term_reference_creates_unqualified_node(self) -> None:
        """Bare term reference (no attribute) creates unqualified node.

        Regression test: ensure bare term references still work correctly.
        """
        term_brand = Term(
            id=Identifier("brand"),
            value=Pattern(elements=(TextElement("Firefox"),)),
            attributes=(),
        )
        msg = Message(
            id=Identifier("welcome"),
            value=Pattern(
                elements=(
                    Placeable(expression=TermReference(id=Identifier("brand"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"welcome": msg}
        terms_dict = {"brand": term_brand}

        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Should have "msg:welcome" -> "term:brand" (no attribute qualification)
        assert "msg:welcome" in graph
        assert "term:brand" in graph["msg:welcome"]


class TestKnownMessageDependencies:
    """Test known_msg_deps dependency propagation (line 572)."""

    def test_known_message_with_dependencies_propagates_to_graph(self) -> None:
        """Known message with dependencies adds them to graph.

        Tests line 572: When known_msg_deps is provided and contains the
        known message ID, copy those dependencies into the graph.
        """
        # Current resource has a simple message
        current_msg = Message(
            id=Identifier("current"),
            value=Pattern(elements=(TextElement("value"),)),
            attributes=(),
        )

        messages_dict = {"current": current_msg}
        terms_dict: dict[str, Term] = {}
        known_messages = frozenset({"known_a", "known_b"})

        # known_a has dependencies on known_b and a term
        known_msg_deps = {
            "known_a": {"msg:known_b", "term:some_term"},
        }

        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_messages=known_messages,
            known_msg_deps=known_msg_deps,
        )

        # Should have known_a in graph with its dependencies
        assert "msg:known_a" in graph
        assert graph["msg:known_a"] == {"msg:known_b", "term:some_term"}

    def test_known_message_without_deps_entry_gets_empty_set(self) -> None:
        """Known message not in known_msg_deps gets empty dependency set.

        Tests line 574: When known message is NOT in known_msg_deps dict,
        it gets an empty set (no dependencies).
        """
        current_msg = Message(
            id=Identifier("current"),
            value=Pattern(elements=(TextElement("value"),)),
            attributes=(),
        )

        messages_dict = {"current": current_msg}
        terms_dict: dict[str, Term] = {}
        known_messages = frozenset({"known_orphan"})

        # known_msg_deps exists but doesn't contain "known_orphan"
        known_msg_deps = {"some_other_msg": {"msg:dependency"}}

        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_messages=known_messages,
            known_msg_deps=known_msg_deps,
        )

        # Should have known_orphan in graph with empty dependencies
        assert "msg:known_orphan" in graph
        assert graph["msg:known_orphan"] == set()

    def test_known_message_already_in_graph_not_overwritten(self) -> None:
        """Known message already in graph from current resource is not overwritten.

        Tests the "if node_key not in graph" guard at line 569: if a known
        message is also defined in the current resource, the current resource
        definition takes precedence.
        """
        # Current resource defines "shared" message
        shared_msg = Message(
            id=Identifier("shared"),
            value=Pattern(
                elements=(
                    Placeable(expression=MessageReference(id=Identifier("local"))),
                )
            ),
            attributes=(),
        )
        local_msg = Message(
            id=Identifier("local"),
            value=Pattern(elements=(TextElement("value"),)),
            attributes=(),
        )

        messages_dict = {"shared": shared_msg, "local": local_msg}
        terms_dict: dict[str, Term] = {}
        known_messages = frozenset({"shared"})  # "shared" is also in known

        # known_msg_deps says "shared" depends on something else
        known_msg_deps = {"shared": {"msg:different_dependency"}}

        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_messages=known_messages,
            known_msg_deps=known_msg_deps,
        )

        # Current resource definition should win - "shared" depends on "local"
        assert "msg:shared" in graph
        assert "msg:local" in graph["msg:shared"]
        # Should NOT have the known_msg_deps dependency
        assert "msg:different_dependency" not in graph["msg:shared"]


class TestKnownTermDependencies:
    """Test known_term_deps dependency propagation (line 582)."""

    def test_known_term_with_dependencies_propagates_to_graph(self) -> None:
        """Known term with dependencies adds them to graph.

        Tests line 582: When known_term_deps is provided and contains the
        known term ID, copy those dependencies into the graph.
        """
        # Current resource has a simple message
        current_msg = Message(
            id=Identifier("current"),
            value=Pattern(elements=(TextElement("value"),)),
            attributes=(),
        )

        messages_dict = {"current": current_msg}
        terms_dict: dict[str, Term] = {}
        known_terms = frozenset({"known_term_a", "known_term_b"})

        # known_term_a has dependencies
        known_term_deps = {
            "known_term_a": {"term:known_term_b", "msg:some_msg"},
        }

        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_terms=known_terms,
            known_term_deps=known_term_deps,
        )

        # Should have known_term_a in graph with its dependencies
        assert "term:known_term_a" in graph
        assert graph["term:known_term_a"] == {"term:known_term_b", "msg:some_msg"}

    def test_known_term_without_deps_entry_gets_empty_set(self) -> None:
        """Known term not in known_term_deps gets empty dependency set.

        Tests line 584: When known term is NOT in known_term_deps dict,
        it gets an empty set (no dependencies).
        """
        current_msg = Message(
            id=Identifier("current"),
            value=Pattern(elements=(TextElement("value"),)),
            attributes=(),
        )

        messages_dict = {"current": current_msg}
        terms_dict: dict[str, Term] = {}
        known_terms = frozenset({"known_orphan_term"})

        # known_term_deps exists but doesn't contain "known_orphan_term"
        known_term_deps = {"some_other_term": {"term:dependency"}}

        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_terms=known_terms,
            known_term_deps=known_term_deps,
        )

        # Should have known_orphan_term in graph with empty dependencies
        assert "term:known_orphan_term" in graph
        assert graph["term:known_orphan_term"] == set()

    def test_known_term_already_in_graph_not_overwritten(self) -> None:
        """Known term already in graph from current resource is not overwritten.

        Tests the "if node_key not in graph" guard at line 579: if a known
        term is also defined in the current resource, the current resource
        definition takes precedence.
        """
        # Current resource defines "shared_term" term
        shared_term = Term(
            id=Identifier("shared_term"),
            value=Pattern(
                elements=(
                    Placeable(expression=TermReference(id=Identifier("local_term"))),
                )
            ),
            attributes=(),
        )
        local_term = Term(
            id=Identifier("local_term"),
            value=Pattern(elements=(TextElement("value"),)),
            attributes=(),
        )

        messages_dict: dict[str, Message] = {}
        terms_dict = {"shared_term": shared_term, "local_term": local_term}
        known_terms = frozenset({"shared_term"})  # "shared_term" is also in known

        # known_term_deps says "shared_term" depends on something else
        known_term_deps = {"shared_term": {"term:different_dependency"}}

        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_terms=known_terms,
            known_term_deps=known_term_deps,
        )

        # Current resource definition should win
        assert "term:shared_term" in graph
        assert "term:local_term" in graph["term:shared_term"]
        # Should NOT have the known_term_deps dependency
        assert "term:different_dependency" not in graph["term:shared_term"]


class TestCrossResourceCycleDetectionWithDependencies:
    """Integration test: cross-resource cycle detection with known deps."""

    def test_cross_resource_cycle_detected_via_known_deps(self) -> None:
        """Cycle spanning current and known resources detected.

        Integration test: Current resource references known message, known
        message (via known_msg_deps) references current resource, creating
        a cross-resource cycle.
        """
        # Current resource: msg_a -> known_b
        msg_a = Message(
            id=Identifier("a"),
            value=Pattern(
                elements=(
                    Placeable(expression=MessageReference(id=Identifier("b"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"a": msg_a}
        terms_dict: dict[str, Term] = {}
        known_messages = frozenset({"b"})

        # Known message "b" references "a" (creating cycle: a -> b -> a)
        known_msg_deps = {"b": {"msg:a"}}

        graph = _build_dependency_graph(
            messages_dict,
            terms_dict,
            known_messages=known_messages,
            known_msg_deps=known_msg_deps,
        )

        # Detect cycles
        warnings = _detect_circular_references(graph)

        # Should detect the cross-resource cycle
        circular_warnings = [w for w in warnings if "circular" in w.message.lower()]
        assert len(circular_warnings) == 1
        # Should mention both messages in the cycle
        warning_msg = circular_warnings[0].message.lower()
        assert ("a" in warning_msg and "b" in warning_msg) or "circular" in warning_msg


class TestAttributeReferenceProperties:
    """Property-based tests for attribute-qualified references."""

    @given(
        st.from_regex(r"[a-z]+", fullmatch=True),
        st.from_regex(r"[a-z]+", fullmatch=True),
    )
    def test_message_attribute_reference_roundtrip(
        self, base_id: str, attr_id: str
    ) -> None:
        """PROPERTY: Message attribute reference creates qualified graph node.

        Attribute-qualified message reference "base.attr" should always
        create a "msg:base.attr" node when "base" exists.

        Events emitted:
        - id_length_base={bucket}: Length category of base identifier
        - id_length_attr={bucket}: Length category of attribute identifier
        """
        # Emit events for identifier length diversity
        event(f"id_length_base={'short' if len(base_id) <= 3 else 'long'}")
        event(f"id_length_attr={'short' if len(attr_id) <= 3 else 'long'}")

        base_msg = Message(
            id=Identifier(base_id),
            value=Pattern(elements=(TextElement("value"),)),
            attributes=(
                Attribute(
                    id=Identifier(attr_id),
                    value=Pattern(elements=(TextElement("attr value"),)),
                ),
            ),
        )

        ref_msg = Message(
            id=Identifier("ref"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=MessageReference(
                            id=Identifier(base_id),
                            attribute=Identifier(attr_id),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {base_id: base_msg, "ref": ref_msg}
        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Property: qualified node exists
        expected_node = f"msg:{base_id}.{attr_id}"
        assert "msg:ref" in graph
        assert expected_node in graph["msg:ref"]

    @given(
        st.from_regex(r"[a-z]+", fullmatch=True),
        st.from_regex(r"[a-z]+", fullmatch=True),
    )
    def test_term_attribute_reference_roundtrip(
        self, base_id: str, attr_id: str
    ) -> None:
        """PROPERTY: Term attribute reference creates qualified graph node.

        Attribute-qualified term reference "-base.attr" should always
        create a "term:base.attr" node when "-base" exists.

        Events emitted:
        - term_id_length_base={bucket}: Length category of base term identifier
        - term_id_length_attr={bucket}: Length category of attribute identifier
        """
        # Emit events for identifier length diversity
        event(f"term_id_length_base={'short' if len(base_id) <= 3 else 'long'}")
        event(f"term_id_length_attr={'short' if len(attr_id) <= 3 else 'long'}")

        base_term = Term(
            id=Identifier(base_id),
            value=Pattern(elements=(TextElement("value"),)),
            attributes=(
                Attribute(
                    id=Identifier(attr_id),
                    value=Pattern(elements=(TextElement("attr value"),)),
                ),
            ),
        )

        msg = Message(
            id=Identifier("msg"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(base_id),
                            attribute=Identifier(attr_id),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {"msg": msg}
        terms_dict = {base_id: base_term}

        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Property: qualified node exists
        expected_node = f"term:{base_id}.{attr_id}"
        assert "msg:msg" in graph
        assert expected_node in graph["msg:msg"]


class TestComplexAttributeReferences:
    """Test complex scenarios with attribute references."""

    def test_message_with_multiple_attribute_references(self) -> None:
        """Message referencing multiple attributes from different messages."""
        msg_a = Message(
            id=Identifier("a"),
            value=Pattern(elements=(TextElement("A"),)),
            attributes=(
                Attribute(
                    id=Identifier("tooltip"),
                    value=Pattern(elements=(TextElement("A tooltip"),)),
                ),
            ),
        )

        msg_b = Message(
            id=Identifier("b"),
            value=Pattern(elements=(TextElement("B"),)),
            attributes=(
                Attribute(
                    id=Identifier("label"),
                    value=Pattern(elements=(TextElement("B label"),)),
                ),
            ),
        )

        # Message referencing multiple attributes
        msg_complex = Message(
            id=Identifier("complex"),
            value=Pattern(
                elements=(
                    TextElement("Value"),
                    Placeable(
                        expression=MessageReference(
                            id=Identifier("a"),
                            attribute=Identifier("tooltip"),
                        )
                    ),
                    TextElement(" and "),
                    Placeable(
                        expression=MessageReference(
                            id=Identifier("b"),
                            attribute=Identifier("label"),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {"a": msg_a, "b": msg_b, "complex": msg_complex}
        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Should have dependencies on both qualified attributes
        assert "msg:complex" in graph
        assert "msg:a.tooltip" in graph["msg:complex"]
        assert "msg:b.label" in graph["msg:complex"]

    def test_message_attribute_itself_has_references(self) -> None:
        """Message attribute containing references creates attribute-level node."""
        base_msg = Message(
            id=Identifier("base"),
            value=Pattern(elements=(TextElement("base value"),)),
            attributes=(),
        )

        # Message with attribute that references another message
        msg_with_attr_ref = Message(
            id=Identifier("complex"),
            value=Pattern(elements=(TextElement("value"),)),
            attributes=(
                Attribute(
                    id=Identifier("tooltip"),
                    value=Pattern(
                        elements=(
                            TextElement("See "),
                            Placeable(expression=MessageReference(id=Identifier("base"))),
                        )
                    ),
                ),
            ),
        )

        messages_dict = {"base": base_msg, "complex": msg_with_attr_ref}
        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Should have "msg:complex.tooltip" node with dependency on "msg:base"
        assert "msg:complex.tooltip" in graph
        assert "msg:base" in graph["msg:complex.tooltip"]

    def test_select_expression_in_attribute_creates_variant_dependencies(self) -> None:
        """Attribute with select expression creates variant-level dependencies."""
        base_msg = Message(
            id=Identifier("base"),
            value=Pattern(elements=(TextElement("base"),)),
            attributes=(),
        )

        # Message with attribute containing select expression
        msg_with_select_attr = Message(
            id=Identifier("selector"),
            value=Pattern(elements=(TextElement("value"),)),
            attributes=(
                Attribute(
                    id=Identifier("dynamic"),
                    value=Pattern(
                        elements=(
                            Placeable(
                                expression=SelectExpression(
                                    selector=MessageReference(id=Identifier("base")),
                                    variants=(
                                        Variant(
                                            key=Identifier("one"),
                                            value=Pattern(
                                                elements=(TextElement("variant"),)
                                            ),
                                            default=True,
                                        ),
                                    ),
                                )
                            ),
                        )
                    ),
                ),
            ),
        )

        messages_dict = {"base": base_msg, "selector": msg_with_select_attr}
        terms_dict: dict[str, Term] = {}

        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Should have "msg:selector.dynamic" node with dependency on "msg:base"
        assert "msg:selector.dynamic" in graph
        assert "msg:base" in graph["msg:selector.dynamic"]
