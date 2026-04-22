"""Reference-graph helpers shared across validation and runtime.

Provides bounded dependency-graph algorithms plus the canonical namespace
encoding used for mixed message/term graphs.

Python 3.13+.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from ftllexengine.constants import (
    MAX_DETECTED_CYCLES as _DEFAULT_MAX_DETECTED_CYCLES,
)
from ftllexengine.constants import (
    MAX_GRAPH_DFS_STACK as _DEFAULT_MAX_GRAPH_DFS_STACK,
)

MAX_DETECTED_CYCLES = _DEFAULT_MAX_DETECTED_CYCLES
MAX_GRAPH_DFS_STACK = _DEFAULT_MAX_GRAPH_DFS_STACK

__all__ = [
    "MAX_DETECTED_CYCLES",
    "MAX_GRAPH_DFS_STACK",
    "_canonicalize_cycle",
    "canonicalize_cycle",
    "detect_cycles",
    "entry_dependency_set",
    "make_cycle_key",
]

_ENTERING: Final[bool] = True
_EXITING: Final[bool] = False


def _append_cycle(
    *,
    path: list[str],
    neighbor: str,
    cycles: list[list[str]],
    seen_canonical: set[tuple[str, ...]],
) -> None:
    """Append a newly discovered cycle if its canonical form is unique."""
    cycle_start = path.index(neighbor)
    cycle = [*path[cycle_start:], neighbor]
    canonical = canonicalize_cycle(cycle)
    if canonical in seen_canonical:
        return
    seen_canonical.add(canonical)
    cycles.append(cycle)


def _queue_neighbor(
    *,
    neighbor: str,
    dependencies: Mapping[str, set[str]],
    rec_stack: set[str],
    stack: list[tuple[str, bool, list[str]]],
) -> None:
    """Queue an unvisited neighbor while honoring DFS stack limits."""
    if neighbor in rec_stack or len(stack) >= MAX_GRAPH_DFS_STACK:
        return
    stack.append((neighbor, _ENTERING, list(dependencies.get(neighbor, set()))))


def _visit_entering_node(
    *,
    node: str,
    neighbors: list[str],
    dependencies: Mapping[str, set[str]],
    globally_visited: set[str],
    path: list[str],
    rec_stack: set[str],
    stack: list[tuple[str, bool, list[str]]],
    cycles: list[list[str]],
    seen_canonical: set[tuple[str, ...]],
) -> None:
    """Process the DFS enter phase for one node."""
    if node in rec_stack:  # pragma: no cover
        return

    globally_visited.add(node)
    rec_stack.add(node)
    path.append(node)
    stack.append((node, _EXITING, []))

    for neighbor in neighbors:
        if neighbor in rec_stack:
            _append_cycle(
                path=path,
                neighbor=neighbor,
                cycles=cycles,
                seen_canonical=seen_canonical,
            )
            if len(cycles) >= MAX_DETECTED_CYCLES:
                return
            continue

        _queue_neighbor(
            neighbor=neighbor,
            dependencies=dependencies,
            rec_stack=rec_stack,
            stack=stack,
        )


def _finish_node(*, node: str, path: list[str], rec_stack: set[str]) -> None:
    """Process the DFS exit phase for one node."""
    path.pop()
    rec_stack.discard(node)


def entry_dependency_set(
    message_refs: frozenset[str],
    term_refs: frozenset[str],
) -> frozenset[str]:
    """Build a namespace-prefixed dependency set from reference sets."""
    return frozenset(
        f"{prefix}:{ref}"
        for prefix, refs in (("msg", message_refs), ("term", term_refs))
        for ref in refs
    )


def _canonicalize_cycle(cycle: Sequence[str]) -> tuple[str, ...]:
    """Canonicalize a cycle path by rotating to start with smallest element."""
    if len(cycle) <= 1:
        return tuple(cycle)

    nodes = list(cycle[:-1])
    min_idx = nodes.index(min(nodes))
    rotated = nodes[min_idx:] + nodes[:min_idx]
    return (*rotated, rotated[0])


def canonicalize_cycle(cycle: Sequence[str]) -> tuple[str, ...]:
    """Canonicalize a cycle path into its stable tuple representation."""
    return _canonicalize_cycle(cycle)


def make_cycle_key(cycle: Sequence[str]) -> str:
    """Create a canonical string key from a cycle for display."""
    canonical = canonicalize_cycle(cycle)
    return " -> ".join(canonical)


def detect_cycles(dependencies: Mapping[str, set[str]]) -> list[list[str]]:
    """Detect cycles in a dependency graph using bounded iterative DFS."""
    globally_visited: set[str] = set()
    cycles: list[list[str]] = []
    seen_canonical: set[tuple[str, ...]] = set()

    for start_node in dependencies:
        if start_node in globally_visited:
            continue
        if len(cycles) >= MAX_DETECTED_CYCLES:
            break

        path: list[str] = []
        rec_stack: set[str] = set()
        stack: list[tuple[str, bool, list[str]]] = [
            (start_node, _ENTERING, list(dependencies.get(start_node, set())))
        ]

        while stack and len(cycles) < MAX_DETECTED_CYCLES:
            node, entering, neighbors = stack.pop()

            if not entering:
                _finish_node(node=node, path=path, rec_stack=rec_stack)
                continue

            _visit_entering_node(
                node=node,
                neighbors=neighbors,
                dependencies=dependencies,
                globally_visited=globally_visited,
                path=path,
                rec_stack=rec_stack,
                stack=stack,
                cycles=cycles,
                seen_canonical=seen_canonical,
            )

    return cycles
