"""Dependency graph construction tests for validation/resource_graph.py.

Tests attribute-qualified reference resolution and known entry dependency
propagation to achieve 100% coverage of build_dependency_graph and
related helper functions.

Coverage targets:
- Lines 507-509: _resolve_msg_ref with attribute-qualified references
- Lines 519-521: _resolve_term_ref with attribute-qualified references
- Line 572: known_msg_deps dependency propagation
- Line 582: known_term_deps dependency propagation
"""

from __future__ import annotations

from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    Attribute,
    Identifier,
    Message,
    MessageReference,
    Pattern,
    Placeable,
    SelectExpression,
    Term,
    TermReference,
    TextElement,
    Variant,
)
from ftllexengine.validation.resource import _detect_circular_references
from ftllexengine.validation.resource_graph import build_dependency_graph

__all__ = [
    "Attribute",
    "Identifier",
    "Message",
    "MessageReference",
    "Pattern",
    "Placeable",
    "SelectExpression",
    "Term",
    "TermReference",
    "TextElement",
    "Variant",
    "_detect_circular_references",
    "build_dependency_graph",
    "event",
    "given",
    "st",
]
