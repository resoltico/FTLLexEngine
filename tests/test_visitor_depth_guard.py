"""Tests for visitor depth guard security feature.

Validates that ASTVisitor and ASTTransformer protect against stack overflow
from deeply nested or programmatically constructed adversarial ASTs.
"""

# ruff: noqa: N802 - visit_NodeName follows stdlib ast.NodeVisitor convention

import pytest

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.depth_guard import DepthLimitExceededError
from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    Pattern,
    Placeable,
    Resource,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.visitor import ASTTransformer, ASTVisitor

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_deeply_nested_ast(depth: int) -> Placeable:
    """Create a deeply nested AST structure bypassing parser limits.

    This simulates an adversarial AST that could be programmatically
    constructed to attempt stack overflow attacks.

    Args:
        depth: Number of nested Placeable layers

    Returns:
        Deeply nested Placeable structure
    """
    innermost = VariableReference(id=Identifier(name="x"))
    current: Placeable | VariableReference = innermost

    for _ in range(depth):
        current = Placeable(expression=current)

    return current  # type: ignore[return-value]


# ============================================================================
# DEPTH GUARD TESTS FOR ASTVisitor
# ============================================================================


class TestASTVisitorDepthGuard:
    """Test depth guard protection in ASTVisitor."""

    def test_visitor_accepts_normal_depth(self) -> None:
        """Visitor handles normally nested ASTs without error."""
        # Create moderately nested structure (well under limit)
        nested = create_deeply_nested_ast(10)

        visitor = ASTVisitor()
        # generic_visit returns the node itself (identity)
        result = visitor.generic_visit(nested)
        assert result is nested  # Visitor returns same node

    def test_visitor_rejects_excessive_depth(self) -> None:
        """Visitor raises error for ASTs exceeding depth limit."""
        # Create structure exceeding MAX_DEPTH
        nested = create_deeply_nested_ast(MAX_DEPTH + 10)

        visitor = ASTVisitor()
        with pytest.raises(DepthLimitExceededError):
            visitor.generic_visit(nested)

    def test_visitor_respects_custom_max_depth(self) -> None:
        """Visitor can be configured with custom max depth."""
        nested = create_deeply_nested_ast(15)

        # Should succeed with high limit
        visitor_high = ASTVisitor(max_depth=50)
        visitor_high.generic_visit(nested)

        # Should fail with low limit
        visitor_low = ASTVisitor(max_depth=10)
        with pytest.raises(DepthLimitExceededError):
            visitor_low.generic_visit(nested)

    def test_visitor_depth_guard_resets_between_visits(self) -> None:
        """Depth guard resets after each complete traversal."""
        nested = create_deeply_nested_ast(10)

        visitor = ASTVisitor()

        # Multiple traversals should each start fresh and return the node
        for i in range(5):
            result = visitor.generic_visit(nested)
            assert result is nested, f"Traversal {i + 1} should return same node"

    def test_visitor_subclass_inherits_depth_guard(self) -> None:
        """Visitor subclasses inherit depth guard from parent."""

        class CountingVisitor(ASTVisitor):
            def __init__(self) -> None:
                super().__init__()
                self.count = 0

            def visit_Placeable(self, node: Placeable) -> Placeable:
                self.count += 1
                self.generic_visit(node)
                return node

        nested = create_deeply_nested_ast(MAX_DEPTH + 10)
        visitor = CountingVisitor()

        with pytest.raises(DepthLimitExceededError):
            visitor.visit(nested)

    def test_visitor_subclass_must_call_super_init(self) -> None:
        """Visitor subclasses that skip super().__init__() fail at runtime."""

        # pylint: disable=super-init-not-called
        class BrokenVisitor(ASTVisitor):
            def __init__(self) -> None:
                # Intentionally NOT calling super().__init__()
                self.custom_field = "test"

        visitor = BrokenVisitor()
        node = Identifier(name="test")

        # Should fail when trying to use depth guard (now in visit(), not generic_visit())
        with pytest.raises(AttributeError, match="_depth_guard"):
            visitor.visit(node)


# ============================================================================
# DEPTH GUARD TESTS FOR ASTTransformer
# ============================================================================


class TestASTTransformerDepthGuard:
    """Test depth guard protection in ASTTransformer."""

    def test_transformer_accepts_normal_depth(self) -> None:
        """Transformer handles normally nested ASTs without error."""
        nested = create_deeply_nested_ast(10)

        transformer = ASTTransformer()
        # Transform returns the (potentially modified) node
        result = transformer.transform(nested)
        assert result is not None  # Transformer returns a node (or None for removal)

    def test_transformer_rejects_excessive_depth(self) -> None:
        """Transformer raises error for ASTs exceeding depth limit."""
        nested = create_deeply_nested_ast(MAX_DEPTH + 10)

        transformer = ASTTransformer()
        with pytest.raises(DepthLimitExceededError):
            transformer.transform(nested)

    def test_transformer_respects_custom_max_depth(self) -> None:
        """Transformer can be configured with custom max depth."""
        nested = create_deeply_nested_ast(15)

        # Should succeed with high limit
        transformer_high = ASTTransformer(max_depth=50)
        transformer_high.transform(nested)

        # Should fail with low limit
        transformer_low = ASTTransformer(max_depth=10)
        with pytest.raises(DepthLimitExceededError):
            transformer_low.transform(nested)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestDepthGuardIntegration:
    """Integration tests for depth guard with real AST structures."""

    def test_resource_with_messages_traverses_safely(self) -> None:
        """Normal resource with messages traverses without depth issues."""
        resource = Resource(
            entries=(
                Message(
                    id=Identifier(name="greeting"),
                    value=Pattern(
                        elements=(
                            TextElement(value="Hello, "),
                            Placeable(
                                expression=VariableReference(
                                    id=Identifier(name="name")
                                )
                            ),
                            TextElement(value="!"),
                        )
                    ),
                    attributes=(),
                    comment=None,
                ),
            )
        )

        visitor = ASTVisitor()
        result = visitor.visit(resource)
        assert result is resource  # Visitor returns same node on successful traversal

    def test_depth_guard_consistent_with_other_components(self) -> None:
        """Depth guard uses same MAX_DEPTH as parser, resolver, serializer."""
        # The MAX_DEPTH constant should be used consistently
        assert MAX_DEPTH == 100  # Verify the expected constant

        # Visitor should use this same limit by default
        visitor = ASTVisitor()
        # The depth guard is created in __init__ with MAX_DEPTH
        assert visitor._depth_guard.max_depth == MAX_DEPTH

    def test_custom_visitor_bypass_prevention(self) -> None:
        """Custom visitor using visit() instead of generic_visit() is protected.

        Tests fix for depth guard bypass vulnerability. Previously, if a custom
        visitor called self.visit() on children instead of self.generic_visit(),
        the depth guard was never triggered. Now the guard is in visit() itself,
        so all traversals are protected regardless of custom visitor design.
        """

        class BypassAttemptVisitor(ASTVisitor):
            """Visitor that avoids generic_visit() - was bypass vector."""

            def __init__(self) -> None:
                super().__init__()
                self.visit_count = 0

            def visit_Placeable(self, node: Placeable) -> Placeable:
                self.visit_count += 1
                # Directly call visit() on child, NOT generic_visit()
                if hasattr(node.expression, "__dataclass_fields__"):
                    self.visit(node.expression)
                return node

            def visit_VariableReference(self, node: VariableReference) -> VariableReference:
                self.visit_count += 1
                return node

        # Create deeply nested structure
        nested = create_deeply_nested_ast(MAX_DEPTH + 10)

        visitor = BypassAttemptVisitor()
        # Must raise DepthLimitExceededError even without generic_visit() calls
        with pytest.raises(DepthLimitExceededError):
            visitor.visit(nested)
