# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor.py."""

from tests.syntax_visitor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# VISITOR CUSTOMIZATION
# ============================================================================


class TestVisitorCustomization:
    """Test custom visitor implementations."""

    def test_collecting_visitor(self) -> None:
        """Custom visitor can collect specific data."""
        visitor = CollectingVisitor()
        resource = Resource(
            entries=(
                Message(
                    id=Identifier(name="hello"),
                    value=Pattern(
                        elements=(
                            TextElement(value="Hello, "),
                            Placeable(
                                expression=VariableReference(id=Identifier(name="name"))
                            ),
                        )
                    ),
                    attributes=(),
                ),
                Message(
                    id=Identifier(name="goodbye"),
                    value=Pattern(elements=(TextElement(value="Goodbye"),)),
                    attributes=(),
                ),
            )
        )

        visitor.visit(resource)

        assert "hello" in visitor.identifiers
        assert "goodbye" in visitor.identifiers
        assert "name" in visitor.identifiers

    def test_transforming_visitor(self) -> None:
        """Custom visitor can transform nodes."""
        visitor = TransformingVisitor()
        text = TextElement(value="hello")

        result = visitor.visit(text)

        assert isinstance(result, TextElement)
        assert result.value == "HELLO"
