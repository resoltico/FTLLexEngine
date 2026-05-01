# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor.py."""

from tests.syntax_visitor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# BASIC VISITOR TESTS
# ============================================================================


class TestASTVisitorBasic:
    """Test basic visitor functionality."""

    def test_visit_dispatches_to_specific_method(self) -> None:
        """Visitor dispatches to visit_NodeType method."""
        visitor = CountingVisitor()
        node = Identifier(name="test")

        visitor.visit(node)

        assert visitor.counts["Identifier"] == 1

    def test_generic_visit_returns_node(self) -> None:
        """Generic visit returns node unchanged."""
        visitor = ASTVisitor()
        node = Identifier(name="test")

        result = visitor.generic_visit(node)

        assert result is node
