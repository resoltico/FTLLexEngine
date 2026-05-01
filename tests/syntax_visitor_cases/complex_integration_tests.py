# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor.py."""

from tests.syntax_visitor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# COMPLEX INTEGRATION TESTS
# ============================================================================


class TestVisitorIntegration:
    """Test visitor with complex AST structures."""

    def test_visit_complex_message_with_select(self) -> None:
        """Visit message with select expression and multiple variants."""
        visitor = CountingVisitor()
        msg = Message(
            id=Identifier(name="emails"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="count")),
                            variants=(
                                Variant(
                                    key=Identifier(name="one"),
                                    value=Pattern(
                                        elements=(TextElement(value="one email"),)
                                    ),
                                    default=False,
                                ),
                                Variant(
                                    key=Identifier(name="other"),
                                    value=Pattern(
                                        elements=(
                                            Placeable(
                                                expression=VariableReference(
                                                    id=Identifier(name="count")
                                                )
                                            ),
                                            TextElement(value=" emails"),
                                        )
                                    ),
                                    default=True,
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        visitor.visit(msg)

        assert visitor.counts["Message"] == 1
        assert visitor.counts["SelectExpression"] == 1
        assert visitor.counts["Variant"] == 2
        assert visitor.counts["VariableReference"] == 2  # selector + in variant

    def test_visit_message_with_function_call(self) -> None:
        """Visit message with function call."""
        visitor = CountingVisitor()
        msg = Message(
            id=Identifier(name="price"),
            value=Pattern(
                elements=(
                    TextElement(value="Price: "),
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="NUMBER"),
                            arguments=CallArguments(
                                positional=(
                                    VariableReference(id=Identifier(name="value")),
                                ),
                                named=(
                                    NamedArgument(
                                        name=Identifier(name="minimumFractionDigits"),
                                        value=NumberLiteral(value=2, raw="2"),
                                    ),
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        visitor.visit(msg)

        assert visitor.counts["Message"] == 1
        assert visitor.counts["FunctionReference"] == 1
        assert visitor.counts["CallArguments"] == 1
        assert visitor.counts["NamedArgument"] == 1

    def test_visit_resource_with_mixed_entries(self) -> None:
        """Visit resource with messages, terms, comments, and junk."""
        visitor = CountingVisitor()
        resource = Resource(
            entries=(
                Comment(content="Header comment", type=CommentType.COMMENT),
                Message(
                    id=Identifier(name="hello"),
                    value=Pattern(elements=(TextElement(value="Hello"),)),
                    attributes=(),
                ),
                Term(
                    id=Identifier(name="brand"),
                    value=Pattern(elements=(TextElement(value="Firefox"),)),
                    attributes=(),
                ),
                Junk(content="invalid syntax"),
            )
        )

        visitor.visit(resource)

        assert visitor.counts["Resource"] == 1
        assert visitor.counts["Comment"] == 1
        assert visitor.counts["Message"] == 1
        assert visitor.counts["Term"] == 1
        assert visitor.counts["Junk"] == 1
