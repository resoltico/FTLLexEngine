# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor.py."""

from tests.syntax_visitor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# HELPER VISITORS
# ============================================================================


class CountingVisitor(ASTVisitor):
    """Counts visits to each node type."""

    def __init__(self) -> None:
        """Initialize counters."""
        super().__init__()
        self.counts: dict[str, int] = {}

    def visit(self, node: Any) -> Any:
        """Track each visit."""
        node_type = type(node).__name__
        self.counts[node_type] = self.counts.get(node_type, 0) + 1
        return super().visit(node)


class CollectingVisitor(ASTVisitor):
    """Collects all identifiers visited."""

    def __init__(self) -> None:
        """Initialize collection."""
        super().__init__()
        self.identifiers: list[str] = []

    def visit_Identifier(self, node: Identifier) -> Any:
        """Collect identifier names."""
        self.identifiers.append(node.name)
        return self.generic_visit(node)


class TransformingVisitor(ASTVisitor):
    """Transforms text to uppercase."""

    def visit_TextElement(self, node: TextElement) -> TextElement:
        """Transform text to uppercase."""
        return TextElement(value=node.value.upper())
