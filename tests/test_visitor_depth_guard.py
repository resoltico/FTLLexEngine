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
        # Should not raise
        visitor.generic_visit(nested)

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

        # Multiple traversals should each start fresh
        for _ in range(5):
            visitor.generic_visit(nested)

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

        # Should fail when trying to use depth guard
        with pytest.raises(AttributeError, match="_depth_guard"):
            visitor.generic_visit(node)


# ============================================================================
# DEPTH GUARD TESTS FOR ASTTransformer
# ============================================================================


class TestASTTransformerDepthGuard:
    """Test depth guard protection in ASTTransformer."""

    def test_transformer_accepts_normal_depth(self) -> None:
        """Transformer handles normally nested ASTs without error."""
        nested = create_deeply_nested_ast(10)

        transformer = ASTTransformer()
        # Should not raise
        transformer.transform(nested)

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
        visitor.visit(resource)  # Should not raise

    def test_depth_guard_consistent_with_other_components(self) -> None:
        """Depth guard uses same MAX_DEPTH as parser, resolver, serializer."""
        # The MAX_DEPTH constant should be used consistently
        assert MAX_DEPTH == 100  # Verify the expected constant

        # Visitor should use this same limit by default
        visitor = ASTVisitor()
        # The depth guard is created in __init__ with MAX_DEPTH
        assert visitor._depth_guard.max_depth == MAX_DEPTH
