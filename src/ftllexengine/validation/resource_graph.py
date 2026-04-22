"""Dependency-graph validation helpers for resource validation.

Split from ``validation.resource`` so the main validation entry point stays
focused on orchestration while graph construction and traversal remain in one
cohesive unit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.reference_graph import detect_cycles, make_cycle_key
from ftllexengine.diagnostics import ValidationWarning, WarningSeverity
from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.syntax.reference_extraction import extract_references_by_attribute

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from ftllexengine.syntax import Message, Term

__all__ = [
    "_compute_longest_paths",
    "build_dependency_graph",
    "detect_circular_references",
    "detect_long_chains",
]


def detect_circular_references(
    graph: dict[str, set[str]],
    *,
    detect_cycles_fn: Callable[[dict[str, set[str]]], list[list[str]]] = detect_cycles,
    make_cycle_key_fn: Callable[[list[str]], str] = make_cycle_key,
) -> list[ValidationWarning]:
    """Detect circular dependencies in a unified reference graph."""
    warnings: list[ValidationWarning] = []
    seen_cycle_keys: set[str] = set()

    for cycle in detect_cycles_fn(graph):
        cycle_key = make_cycle_key_fn(cycle)
        if cycle_key in seen_cycle_keys:
            continue
        seen_cycle_keys.add(cycle_key)

        formatted_parts: list[str] = []
        for node in cycle:
            if node.startswith("msg:"):
                formatted_parts.append(node[4:])
            elif node.startswith("term:"):
                formatted_parts.append(f"-{node[5:]}")

        cycle_str = " -> ".join(formatted_parts)
        has_messages = any(node.startswith("msg:") for node in cycle)
        has_terms = any(node.startswith("term:") for node in cycle)

        if has_messages and has_terms:
            message = f"Circular cross-reference: {cycle_str}"
        elif has_terms:
            message = f"Circular term reference: {cycle_str}"
        else:
            message = f"Circular message reference: {cycle_str}"

        warnings.append(
            ValidationWarning(
                code=DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE,
                message=message,
                context=cycle_str,
                severity=WarningSeverity.CRITICAL,
            )
        )

    return warnings


def _resolve_reference(
    ref: str,
    prefix: str,
    local_entries: dict[str, Message] | dict[str, Term],
    known_ids: frozenset[str] | None,
) -> str | None:
    """Resolve a reference string to a graph node key."""
    if "." in ref:
        base, attr = ref.split(".", 1)
        if base in local_entries or (known_ids and base in known_ids):
            return f"{prefix}:{base}.{attr}"
    elif ref in local_entries or (known_ids and ref in known_ids):
        return f"{prefix}:{ref}"
    return None


def _add_entry_nodes(
    entries: dict[str, Message] | dict[str, Term],
    prefix: str,
    messages_dict: dict[str, Message],
    terms_dict: dict[str, Term],
    known_messages: frozenset[str] | None,
    known_terms: frozenset[str] | None,
    graph: dict[str, set[str]],
) -> None:
    """Add nodes and edges for a set of entries to the dependency graph."""
    for name, entry in entries.items():
        refs_by_attr = extract_references_by_attribute(entry)

        for attr_name, (msg_refs, term_refs) in refs_by_attr.items():
            node_key = f"{prefix}:{name}" if attr_name is None else f"{prefix}:{name}.{attr_name}"
            deps: set[str] = set()

            for ref in msg_refs:
                resolved = _resolve_reference(ref, "msg", messages_dict, known_messages)
                if resolved is not None:
                    deps.add(resolved)

            for ref in term_refs:
                resolved = _resolve_reference(ref, "term", terms_dict, known_terms)
                if resolved is not None:
                    deps.add(resolved)

            graph[node_key] = deps


def _add_known_entries(
    known_ids: frozenset[str] | None,
    prefix: str,
    known_deps: Mapping[str, frozenset[str]] | None,
    graph: dict[str, set[str]],
) -> None:
    """Add pre-existing bundle entries to the graph."""
    if not known_ids:
        return

    for known_id in known_ids:
        node_key = f"{prefix}:{known_id}"
        if node_key not in graph:
            if known_deps and known_id in known_deps:
                graph[node_key] = set(known_deps[known_id])
            else:
                graph[node_key] = set()


def build_dependency_graph(
    messages_dict: dict[str, Message],
    terms_dict: dict[str, Term],
    *,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
    known_msg_deps: Mapping[str, frozenset[str]] | None = None,
    known_term_deps: Mapping[str, frozenset[str]] | None = None,
) -> dict[str, set[str]]:
    """Build a unified dependency graph for messages and terms."""
    graph: dict[str, set[str]] = {}

    _add_entry_nodes(
        messages_dict,
        "msg",
        messages_dict,
        terms_dict,
        known_messages,
        known_terms,
        graph,
    )
    _add_entry_nodes(
        terms_dict,
        "term",
        messages_dict,
        terms_dict,
        known_messages,
        known_terms,
        graph,
    )

    _add_known_entries(known_messages, "msg", known_msg_deps, graph)
    _add_known_entries(known_terms, "term", known_term_deps, graph)

    return graph


def _compute_longest_paths(
    graph: dict[str, set[str]],
) -> dict[str, tuple[int, list[str]]]:
    """Compute the longest path from each node using memoized iterative DFS."""
    longest_path: dict[str, tuple[int, list[str]]] = {}
    in_stack: set[str] = set()

    for start in graph:
        if start in longest_path:
            continue

        stack: list[tuple[str, int, list[str]]] = [(start, 0, list(graph.get(start, set())))]

        while stack:
            node, phase, children = stack.pop()

            if phase == 0:
                if node in longest_path:
                    continue

                in_stack.add(node)
                stack.append((node, 1, children))
                stack.extend(
                    (child, 0, list(graph.get(child, set())))
                    for child in children
                    if child not in longest_path and child not in in_stack
                )
            else:
                in_stack.discard(node)
                best_depth, best_path = 0, []
                for child in children:
                    if child in longest_path:
                        child_depth, child_path = longest_path[child]
                        if child_depth + 1 > best_depth:
                            best_depth = child_depth + 1
                            best_path = child_path
                longest_path[node] = (best_depth, [node, *best_path])

    return longest_path


def detect_long_chains(
    graph: dict[str, set[str]],
    max_depth: int = MAX_DEPTH,
) -> list[ValidationWarning]:
    """Detect reference chains that exceed the maximum runtime depth."""
    if not graph:
        return []

    longest_paths = _compute_longest_paths(graph)
    exceeding_chains: list[tuple[int, list[str], str]] = []

    for node, (depth, path) in longest_paths.items():
        if depth > max_depth and path and path[0] == node:
            exceeding_chains.append((depth, path, node))

    if not exceeding_chains:
        return []

    exceeding_chains.sort(key=lambda item: item[0], reverse=True)

    warnings: list[ValidationWarning] = []
    for chain_depth, chain_path, _origin in exceeding_chains:
        formatted = [
            node[4:] if node.startswith("msg:") else f"-{node[5:]}"
            for node in chain_path[:10]
        ]
        chain_str = " -> ".join(formatted)
        if len(chain_path) > 10:
            chain_str += f" -> ... ({len(chain_path)} total)"

        warnings.append(
            ValidationWarning(
                code=DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED,
                message=(
                    f"Reference chain depth ({chain_depth}) exceeds maximum ({max_depth}); "
                    f"will fail at runtime with MAX_DEPTH_EXCEEDED"
                ),
                context=chain_str,
                severity=WarningSeverity.WARNING,
            )
        )

    return warnings
