"""AST normalization and verification utilities for property-based tests.

Provides shared utilities for comparing ASTs semantically, stripping
non-semantic fields like spans and raw values.
"""

from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any

from ftllexengine.syntax.ast import (
    Pattern,
    Placeable,
    Span,
    StringLiteral,
    TextElement,
)


def flatten_pattern(pattern: Pattern) -> list[Any]:
    """Flatten a Pattern's elements for comparison.

    Merges adjacent TextElements and StringLiteral placeables into strings,
    normalizes other expressions recursively.

    Args:
        pattern: Pattern AST node to flatten

    Returns:
        List of strings and normalized expression dicts
    """
    flat: list[Any] = []
    for elem in pattern.elements:
        if isinstance(elem, TextElement):
            val = elem.value
            if flat and isinstance(flat[-1], str):
                flat[-1] += val
            else:
                flat.append(val)
        elif isinstance(elem, Placeable):
            if isinstance(elem.expression, StringLiteral):
                val = elem.expression.value
                if flat and isinstance(flat[-1], str):
                    flat[-1] += val
                else:
                    flat.append(val)
            else:
                flat.append(normalize_ast(elem.expression))
    return flat


def normalize_ast(obj: Any) -> Any:
    """Normalize AST for semantic comparison.

    Strips spans, raw values, and annotations that may differ between
    parse cycles but don't affect semantics. Flattens Pattern elements
    to merge adjacent text.

    Args:
        obj: AST node, list, tuple, or primitive value

    Returns:
        Normalized representation suitable for equality comparison
    """
    if isinstance(obj, (list, tuple)):
        return [normalize_ast(x) for x in obj]

    if isinstance(obj, Pattern):
        return flatten_pattern(obj)

    if is_dataclass(obj):
        processed: dict[str, Any] = {}
        for field_name in obj.__dataclass_fields__:
            if field_name in ("span", "raw", "annotations"):
                continue
            val = getattr(obj, field_name)
            processed[field_name] = normalize_ast(val)
        return processed

    return obj


def verify_spans(node: Any, source: str) -> None:
    """Verify span bounds and non-overlapping for pattern elements.

    Recursively checks that all span values are within source bounds
    and that adjacent pattern elements don't have overlapping spans.

    Args:
        node: AST node to verify
        source: Original source string for bounds checking

    Raises:
        AssertionError: If spans are out of bounds or overlapping
    """
    if is_dataclass(node):
        node_span = getattr(node, "span", None)
        if node_span is not None:
            span: Span = node_span
            assert (
                0 <= span.start <= span.end <= len(source)
            ), f"Span out of bounds: {span} in {len(source)}"

        if isinstance(node, Pattern) and node.elements:
            last_end = -1
            for elem in node.elements:
                elem_span = getattr(elem, "span", None)
                if elem_span:
                    if last_end != -1:
                        assert (
                            elem_span.start >= last_end
                        ), f"Overlapping spans: {last_end} -> {elem_span.start}"
                    last_end = elem_span.end

        for field in node.__dataclass_fields__:
            val = getattr(node, field)
            if isinstance(val, (list, tuple)):
                for item in val:
                    verify_spans(item, source)
            elif is_dataclass(val):
                verify_spans(val, source)
