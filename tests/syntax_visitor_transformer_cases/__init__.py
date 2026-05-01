"""Tests for syntax.visitor: ASTTransformer transformation, validation, and error cases."""

from __future__ import annotations

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    Attribute,
    CallArguments,
    FunctionReference,
    Identifier,
    Message,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.visitor import ASTTransformer, ASTVisitor


class UppercaseIdentifierTransformer(ASTTransformer):
    """Test transformer that uppercases all identifiers."""

    def visit_Identifier(self, node: Identifier) -> Identifier:
        """Uppercase identifier names."""
        return Identifier(name=node.name.upper())


class NoneReturningTransformer(ASTTransformer):
    """Transformer that incorrectly returns None for required scalar fields."""

    def __init__(self, target_node_type: str) -> None:
        super().__init__()
        self.target_node_type = target_node_type

    def visit_Identifier(self, node: Identifier) -> Identifier | None:
        """Return None for Identifier when requested."""
        if self.target_node_type == "Identifier":
            return None
        return node


class ListReturningTransformer(ASTTransformer):
    """Transformer that incorrectly returns lists for scalar fields."""

    def __init__(self, target_node_type: str) -> None:
        super().__init__()
        self.target_node_type = target_node_type

    def visit_Identifier(self, node: Identifier) -> Identifier | list[Identifier]:
        """Return a list of identifiers when requested."""
        if self.target_node_type == "Identifier":
            return [node, Identifier(name="extra")]
        return node

    def visit_Pattern(self, node: Pattern) -> Pattern | list[Pattern]:
        """Return a list of patterns when requested."""
        if self.target_node_type == "Pattern":
            return [node, Pattern(elements=())]
        return self.generic_visit(node)  # type: ignore[return-value]

__all__ = [
    "ASTTransformer",
    "ASTVisitor",
    "Attribute",
    "CallArguments",
    "FunctionReference",
    "Identifier",
    "ListReturningTransformer",
    "Message",
    "MessageReference",
    "NamedArgument",
    "NoneReturningTransformer",
    "NumberLiteral",
    "Pattern",
    "Placeable",
    "Resource",
    "SelectExpression",
    "StringLiteral",
    "Term",
    "TermReference",
    "TextElement",
    "UppercaseIdentifierTransformer",
    "VariableReference",
    "Variant",
    "event",
    "given",
    "pytest",
    "settings",
    "st",
]
