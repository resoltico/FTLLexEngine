# mypy: ignore-errors
"""Split test cases from tests/test_validation_resource_dependency_graph.py."""

from tests.validation_resource_dependency_graph_cases import *  # noqa: F403 - shared split test support


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

        graph = build_dependency_graph(messages_dict, terms_dict)

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

        graph = build_dependency_graph(messages_dict, terms_dict)

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

        graph = build_dependency_graph(messages_dict, terms_dict)

        # Should have "msg:selector.dynamic" node with dependency on "msg:base"
        assert "msg:selector.dynamic" in graph
        assert "msg:base" in graph["msg:selector.dynamic"]
