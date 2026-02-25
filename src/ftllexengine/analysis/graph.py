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
        f"{prefix}:{r}"
        for prefix, refs in (("msg", message_refs), ("term", term_refs))
        for r in refs
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
        Time: O(V * E) in the worst case (sparse graphs common in FTL
        resources are well within practical bounds). Each node may be
        explored once per distinct incoming path; cycles deduplicated via
        canonical tuple.
        Space: O(V) for path and recursion tracking.

    Correctness:
        The ``visited`` guard used in a simple DFS causes false negatives
        when a graph has multiple paths to the same intermediate node that
        closes a cycle. Example: A→B→D→A and A→C→D→A share node D; the
        second cycle is missed if D is marked globally visited after the
        first traversal. This implementation avoids that defect by NOT
        applying a global visited guard on neighbors. Instead:
        - ``rec_stack`` prevents re-entering nodes already on the current
          DFS path (back-edge detection and termination guarantee).
        - ``globally_visited`` tracks only start nodes whose reachable
          subgraphs have been fully explored, safely pruning the outer
          for-loop without suppressing intra-DFS re-exploration.

    Security:
        Uses iterative DFS to prevent stack overflow attacks via
        deeply nested dependency chains in untrusted FTL resources.
    """
    globally_visited: set[str] = set()
    cycles: list[list[str]] = []
    seen_canonical: set[tuple[str, ...]] = set()

    for start_node in dependencies:
        if start_node in globally_visited:
            continue

        path: list[str] = []
        rec_stack: set[str] = set()

        stack: list[tuple[str, bool, list[str]]] = [
            (start_node, _ENTERING, list(dependencies.get(start_node, set())))
        ]

        while stack:
            node, entering, neighbors = stack.pop()

            if entering:
                # Prevent re-entering a node already on the current DFS path.
                # Without this guard the same node could be pushed repeatedly,
                # creating an infinite exploration loop through the cycle.
                if node in rec_stack:
                    continue

                globally_visited.add(node)
                rec_stack.add(node)
                path.append(node)

                stack.append((node, _EXITING, []))

                for neighbor in neighbors:
                    if neighbor in rec_stack:
                        # Back edge: neighbor is an ancestor in the current path.
                        cycle_start = path.index(neighbor)
                        cycle = [*path[cycle_start:], neighbor]
                        canonical = _canonicalize_cycle(cycle)
                        if canonical not in seen_canonical:
                            seen_canonical.add(canonical)
                            cycles.append(cycle)
                    else:
                        # Push neighbor for exploration.
                        # No globally_visited guard here: nodes reachable from
                        # multiple branches of the current path must be explored
                        # via each branch independently to find all cycles
                        # (e.g., A→B→D→A and A→C→D→A both require exploring D).
                        stack.append((
                            neighbor,
                            _ENTERING,
                            list(dependencies.get(neighbor, set())),
                        ))

            else:
                path.pop()
                rec_stack.discard(node)

    return cycles
