"""Graph algorithms for dependency analysis.

Provides cycle detection using iterative depth-first search and
namespace-prefixed dependency set construction for validating
message/term reference graphs in FTL resources.

Python 3.13+.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

__all__ = [
    "detect_cycles",
    "entry_dependency_set",
    "make_cycle_key",
]

_ENTERING = True
_EXITING = False


def entry_dependency_set(
    message_refs: frozenset[str],
    term_refs: frozenset[str],
) -> frozenset[str]:
    """Build a namespace-prefixed dependency set from reference sets.

    Combines message and term references into a single frozenset with
    ``msg:`` and ``term:`` prefixes. This is the canonical key format
    used by ``detect_cycles`` for cross-namespace cycle detection.

    Args:
        message_refs: Message IDs referenced by the entry.
        term_refs: Term IDs referenced by the entry.

    Returns:
        Frozenset of prefixed dependency keys
        (e.g., ``frozenset({"msg:welcome", "term:brand"})``).
    """
    return frozenset(
        {f"msg:{r}" for r in message_refs}
        | {f"term:{r}" for r in term_refs}
    )


def _canonicalize_cycle(cycle: Sequence[str]) -> tuple[str, ...]:
    """Canonicalize a cycle path by rotating to start with smallest element.

    Preserves directional information (A->B->C vs A->C->B remain distinct)
    while normalizing the starting point for deduplication.

    The input cycle has the format ``[A, B, C, A]`` where the last element
    repeats the first to close the cycle.

    Args:
        cycle: Cycle path with closing repeat
               (e.g., ``["A", "B", "C", "A"]``).

    Returns:
        Canonicalized cycle as tuple, rotated to start with
        lexicographically smallest element. Closing repeat preserved.
    """
    if len(cycle) <= 1:
        return tuple(cycle)

    nodes = list(cycle[:-1])
    min_idx = nodes.index(min(nodes))
    rotated = nodes[min_idx:] + nodes[:min_idx]
    return (*rotated, rotated[0])


def make_cycle_key(cycle: Sequence[str]) -> str:
    """Create a canonical string key from a cycle for display.

    Args:
        cycle: Cycle path as sequence of node IDs.

    Returns:
        Canonical string key in format ``"A -> B -> C -> A"``.
    """
    canonical = _canonicalize_cycle(cycle)
    return " -> ".join(canonical)


def detect_cycles(dependencies: Mapping[str, set[str]]) -> list[list[str]]:
    """Detect all cycles in a dependency graph using iterative DFS.

    Implements iterative DFS with explicit stack to avoid RecursionError
    on deep graphs (>1000 nodes in linear chain).

    Args:
        dependencies: Mapping from node ID to set of referenced node IDs.
                     Example: ``{"a": {"b", "c"}, "b": {"c"}, "c": {"a"}}``

    Returns:
        List of cycles, where each cycle is a list of node IDs forming
        the cycle path (closed: last element repeats first). Empty list
        if no cycles detected. Cycles are deduplicated via canonical
        tuple form.

    Complexity:
        Time: O(V + E) where V = nodes, E = edges.
        Space: O(V) for visited/recursion tracking.

    Security:
        Uses iterative DFS to prevent stack overflow attacks via
        deeply nested dependency chains in untrusted FTL resources.
    """
    visited: set[str] = set()
    cycles: list[list[str]] = []
    seen_canonical: set[tuple[str, ...]] = set()

    for start_node in dependencies:
        if start_node in visited:
            continue

        path: list[str] = []
        rec_stack: set[str] = set()

        stack: list[tuple[str, bool, list[str]]] = [
            (start_node, _ENTERING, list(dependencies.get(start_node, set())))
        ]

        while stack:
            node, entering, neighbors = stack.pop()

            if entering:
                if node in visited:
                    continue

                visited.add(node)
                rec_stack.add(node)
                path.append(node)

                stack.append((node, _EXITING, []))

                for neighbor in neighbors:
                    if neighbor not in visited:
                        stack.append((
                            neighbor,
                            _ENTERING,
                            list(dependencies.get(neighbor, set())),
                        ))
                    elif neighbor in rec_stack:
                        cycle_start = path.index(neighbor)
                        cycle = [*path[cycle_start:], neighbor]

                        canonical = _canonicalize_cycle(cycle)
                        # pragma: no branch -- DFS guarantees each edge (node → neighbor)
                        # in rec_stack is visited at most once per DFS start node.
                        # The False branch (canonical already seen) is unreachable for
                        # a single DFS pass; only reachable with a separate pre-loaded
                        # seen_canonical, which this function never does.
                        if canonical not in seen_canonical:  # pragma: no branch
                            seen_canonical.add(canonical)
                            cycles.append(cycle)

            else:
                path.pop()
                rec_stack.discard(node)

    return cycles
