"""AST-only reference extraction helpers.

These helpers operate purely on syntax nodes and therefore live in the syntax
layer, where validation and higher-level introspection code can both depend on
them without introducing upward imports.
"""

from __future__ import annotations

from ftllexengine.constants import MAX_DEPTH

from .ast import Message, MessageReference, Term, TermReference
from .visitor import ASTVisitor

__all__ = [
    "ReferenceExtractor",
    "extract_references",
    "extract_references_by_attribute",
]


class ReferenceExtractor(ASTVisitor[MessageReference | TermReference]):
    """Extract message and term references from AST for dependency analysis."""

    __slots__ = ("message_refs", "term_refs")

    def __init__(self, *, max_depth: int = MAX_DEPTH) -> None:
        super().__init__(max_depth=max_depth)
        self.message_refs: set[str] = set()
        self.term_refs: set[str] = set()

    def visit_MessageReference(  # noqa: N802 - AST visitor dispatch contract
        self, node: MessageReference
    ) -> MessageReference:
        """Collect message reference ID with optional attribute qualification."""
        if node.attribute is not None:
            self.message_refs.add(f"{node.id.name}.{node.attribute.name}")
        else:
            self.message_refs.add(node.id.name)
        return node

    def visit_TermReference(  # noqa: N802 - AST visitor dispatch contract
        self, node: TermReference
    ) -> TermReference:
        """Collect term reference ID and traverse nested call arguments."""
        if node.attribute is not None:
            self.term_refs.add(f"{node.id.name}.{node.attribute.name}")
        else:
            self.term_refs.add(node.id.name)
        with self._depth_guard:
            self.generic_visit(node)
        return node


def extract_references(entry: Message | Term) -> tuple[frozenset[str], frozenset[str]]:
    """Extract message and term references from an AST entry."""
    extractor = ReferenceExtractor()

    if entry.value is not None:
        extractor.visit(entry.value)

    for attr in entry.attributes:
        extractor.visit(attr.value)

    return frozenset(extractor.message_refs), frozenset(extractor.term_refs)


def extract_references_by_attribute(
    entry: Message | Term,
) -> dict[str | None, tuple[frozenset[str], frozenset[str]]]:
    """Extract references per source attribute for attribute-granular analysis."""
    result: dict[str | None, tuple[frozenset[str], frozenset[str]]] = {}

    if entry.value is not None:
        extractor = ReferenceExtractor()
        extractor.visit(entry.value)
        result[None] = (frozenset(extractor.message_refs), frozenset(extractor.term_refs))

    for attr in entry.attributes:
        extractor = ReferenceExtractor()
        extractor.visit(attr.value)
        result[attr.id.name] = (frozenset(extractor.message_refs), frozenset(extractor.term_refs))

    return result
