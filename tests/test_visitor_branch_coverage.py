"""Tests for visitor.py branch coverage edge cases.

Covers defensive branches for non-ASTNode values in fields.
"""



from dataclasses import dataclass

from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    Pattern,
    TextElement,
)
from ftllexengine.syntax.visitor import ASTVisitor


@dataclass(frozen=True)
class MockFieldContainer:
    """Mock container without __dataclass_fields__ for testing defensive branches."""

    value: str


class PlainObject:
    """Plain object without dataclass fields for testing defensive branches."""

    def __init__(self, data: str) -> None:
        """Initialize with data."""
        self.data = data


class TestGenericVisitDefensiveBranches:
    """Test defensive branches in generic_visit for non-ASTNode values."""

    def test_generic_visit_tuple_with_non_dataclass_items(self) -> None:
        """Test line 214->212: tuple containing items without __dataclass_fields__.

        This tests the defensive branch where a tuple field contains items that
        are not ASTNodes (don't have __dataclass_fields__).
        """

        class CountingVisitor(ASTVisitor):
            """Visitor that counts visits."""

            def __init__(self) -> None:
                """Initialize visitor."""
                super().__init__()
                self.visit_count = 0

            def visit(self, node):
                """Count each visit."""
                self.visit_count += 1
                return super().visit(node)

        # Create a message with normal structure
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )

        # Monkey-patch the elements tuple to include a non-ASTNode item
        # This is testing a defensive code path that shouldn't happen in normal usage
        # but guards against malformed AST structures
        modified_elements = (
            TextElement(value="First"),
            MockFieldContainer(value="not_an_astnode"),  # No __dataclass_fields__
            TextElement(value="Last"),
        )

        # Use object.__setattr__ to bypass frozen dataclass protection
        object.__setattr__(msg.value, "elements", modified_elements)

        visitor = CountingVisitor()
        visitor.generic_visit(msg)

        # The visitor should visit the Message, Pattern, Identifier, and the two TextElements
        # but NOT the MockFieldContainer (it lacks __dataclass_fields__)
        # Visit count: Message (1) + Identifier (1) + Pattern (1) + 2 TextElements (2) = 5
        assert visitor.visit_count == 5

    def test_generic_visit_tuple_with_mixed_items(self) -> None:
        """Test tuple containing mix of ASTNodes and non-ASTNodes.

        This comprehensively tests the line 214 branch logic where we check
        each tuple item for __dataclass_fields__.
        """

        class VisitOrderTracker(ASTVisitor):
            """Track order of visits."""

            def __init__(self) -> None:
                """Initialize tracker."""
                super().__init__()
                self.visit_order: list[str] = []

            def visit(self, node):
                """Record visit order."""
                node_name = type(node).__name__
                if node_name == "TextElement":
                    text_value = getattr(node, "value", "")
                    self.visit_order.append(f"TextElement:{text_value}")
                else:
                    self.visit_order.append(node_name)
                return super().visit(node)

        # Create pattern with mixed elements
        pattern = Pattern(
            elements=(
                TextElement(value="A"),
                TextElement(value="B"),
            )
        )

        # Inject non-ASTNode items into the tuple
        mixed_elements = (
            TextElement(value="A"),
            "string_value",  # Not an ASTNode, will be skipped
            TextElement(value="B"),
            123,  # int, will be skipped by primitive check
        )

        object.__setattr__(pattern, "elements", mixed_elements)

        visitor = VisitOrderTracker()
        visitor.generic_visit(pattern)

        # Should visit TextElement:A and TextElement:B, skipping string and int
        assert "TextElement:A" in visitor.visit_order
        assert "TextElement:B" in visitor.visit_order
        # String and int should not appear
        assert "str" not in visitor.visit_order
        assert "int" not in visitor.visit_order

    def test_generic_visit_non_tuple_non_dataclass_field(self) -> None:
        """Test line 217->203: single field that is an object without __dataclass_fields__.

        This tests the defensive else branch where a field value is:
        - Not None
        - Not a primitive (str, int, float, bool)
        - Not a tuple
        - Not an ASTNode (no __dataclass_fields__)
        """
        # Create a message
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )

        # Replace the 'comment' field (normally None or Comment ASTNode) with a
        # plain object that doesn't have __dataclass_fields__
        plain_obj = PlainObject(data="test")
        object.__setattr__(msg, "comment", plain_obj)

        class VisitorTracker(ASTVisitor):
            """Track what gets visited."""

            def __init__(self) -> None:
                """Initialize tracker."""
                super().__init__()
                self.visited_types: set[str] = set()

            def visit(self, node):
                """Track visits."""
                self.visited_types.add(type(node).__name__)
                return super().visit(node)

        visitor = VisitorTracker()
        visitor.generic_visit(msg)

        # Should have visited Message's children (Identifier, Pattern, TextElement)
        # but NOT the PlainObject (it doesn't have __dataclass_fields__)
        assert "Identifier" in visitor.visited_types
        assert "Pattern" in visitor.visited_types
        assert "TextElement" in visitor.visited_types
        assert "PlainObject" not in visitor.visited_types
