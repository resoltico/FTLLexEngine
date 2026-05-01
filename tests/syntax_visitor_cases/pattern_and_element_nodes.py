# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor.py."""

from tests.syntax_visitor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PATTERN AND ELEMENT NODES
# ============================================================================


class TestVisitorPattern:
    """Test visiting Pattern nodes."""

    def test_visit_pattern_with_text(self) -> None:
        """Visit pattern with text elements."""
        visitor = CountingVisitor()
        pattern = Pattern(elements=(TextElement(value="Hello"),))

        visitor.visit(pattern)

        assert visitor.counts["Pattern"] == 1
        assert visitor.counts["TextElement"] == 1

    def test_visit_pattern_with_mixed_elements(self) -> None:
        """Visit pattern with text and placeables."""
        visitor = CountingVisitor()
        pattern = Pattern(
            elements=(
                TextElement(value="Hello, "),
                Placeable(expression=VariableReference(id=Identifier(name="name"))),
                TextElement(value="!"),
            )
        )

        visitor.visit(pattern)

        assert visitor.counts["Pattern"] == 1
        assert visitor.counts["TextElement"] == 2
        assert visitor.counts["Placeable"] == 1
        assert visitor.counts["VariableReference"] == 1


class TestVisitorTextElement:
    """Test visiting TextElement nodes."""

    def test_visit_text_element(self) -> None:
        """Visit text element."""
        visitor = CountingVisitor()
        text = TextElement(value="Hello, World!")

        visitor.visit(text)

        assert visitor.counts["TextElement"] == 1


class TestVisitorPlaceable:
    """Test visiting Placeable nodes."""

    def test_visit_placeable_with_variable(self) -> None:
        """Visit placeable containing variable."""
        visitor = CountingVisitor()
        placeable = Placeable(expression=VariableReference(id=Identifier(name="var")))

        visitor.visit(placeable)

        assert visitor.counts["Placeable"] == 1
        assert visitor.counts["VariableReference"] == 1
        assert visitor.counts["Identifier"] == 1
