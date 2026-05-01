"""Tests for validation.resource: validate_resource(), graph algorithms, edge cases."""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import DiagnosticCode
from ftllexengine.syntax import (
    Identifier,
    Junk,
    Message,
    MessageReference,
    Pattern,
    Placeable,
    Term,
    TermReference,
    TextElement,
)
from ftllexengine.syntax.cursor import LineOffsetCache
from ftllexengine.validation.resource import (
    _detect_circular_references,
    _extract_syntax_errors,
    validate_resource,
)
from ftllexengine.validation.resource_graph import (
    _compute_longest_paths,
    build_dependency_graph,
)

__all__ = [
    "DiagnosticCode",
    "Identifier",
    "Junk",
    "LineOffsetCache",
    "Message",
    "MessageReference",
    "Pattern",
    "Placeable",
    "Term",
    "TermReference",
    "TextElement",
    "_compute_longest_paths",
    "_detect_circular_references",
    "_extract_syntax_errors",
    "build_dependency_graph",
    "event",
    "given",
    "patch",
    "st",
    "validate_resource",
]
