"""Graph algorithms for dependency analysis.

Provides cycle detection using depth-first search for validating
message/term reference graphs in FTL resources.

Python 3.13+.
"""

from collections.abc import Mapping
from enum import Enum, auto


class _NodeState(Enum):
    """DFS node visitation state for iterative cycle detection."""

    ENTER = auto()  # First visit to node
    EXIT = auto()  # Returning from node (all neighbors processed)


def detect_cycles(dependencies: Mapping[str, set[str]]) -> list[list[str]]:
    """Detect all cycles in a dependency graph using iterative DFS.

    Implements iterative DFS with explicit stack to avoid RecursionError
    on deep graphs (>1000 nodes in linear chain). Uses Tarjan-style
    cycle detection with explicit stack tracking.

    Args:
        dependencies: Mapping from node ID to set of referenced node IDs.
                     Example: {"a": {"b", "c"}, "b": {"c"}, "c": {"a"}}

    Returns:
        List of cycles, where each cycle is a list of node IDs forming
        the cycle path. Empty list if no cycles detected.

    Example:
        >>> deps = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
        >>> cycles = detect_cycles(deps)
        >>> len(cycles)
        1
        >>> "a" in cycles[0] and "b" in cycles[0] and "c" in cycles[0]
        True

    Complexity:
        Time: O(V + E) where V = nodes, E = edges
        Space: O(V) for visited/recursion tracking

    Security:
        Uses iterative DFS to prevent stack overflow attacks via
        deeply nested dependency chains in untrusted FTL resources.
    """
    visited: set[str] = set()
    cycles: list[list[str]] = []
    seen_cycle_keys: set[str] = set()

    # Process each connected component
    for start_node in dependencies:
        if start_node in visited:
            continue

        # Iterative DFS using explicit stack
        # Stack entries: (node, state, iterator)
        # - ENTER state: first visit, add to path and rec_stack
        # - EXIT state: done with neighbors, remove from path and rec_stack
        path: list[str] = []
        rec_stack: set[str] = set()

        # Stack holds (node, state, neighbor_iterator)
        # neighbor_iterator is used to resume iteration after processing a neighbor
        stack: list[tuple[str, _NodeState, list[str]]] = [
            (start_node, _NodeState.ENTER, list(dependencies.get(start_node, set())))
        ]

        while stack:
            node, state, neighbors = stack.pop()

            if state == _NodeState.ENTER:
                if node in visited:
                    # Already fully processed in another traversal
                    continue

                visited.add(node)
                rec_stack.add(node)
                path.append(node)

                # Push exit marker (will be processed after all neighbors)
                stack.append((node, _NodeState.EXIT, []))

                # Process neighbors
                for neighbor in neighbors:
                    if neighbor not in visited:
                        # Push neighbor for exploration
                        stack.append(
                            (
                                neighbor,
                                _NodeState.ENTER,
                                list(dependencies.get(neighbor, set())),
                            )
                        )
                    elif neighbor in rec_stack:
                        # Found cycle - extract cycle path
                        cycle_start = path.index(neighbor)
                        cycle = [*path[cycle_start:], neighbor]

                        # Deduplicate cycles using canonical form (sorted key)
                        cycle_key = " -> ".join(sorted(set(cycle)))
                        if cycle_key not in seen_cycle_keys:  # pragma: no branch
                            # Note: False branch is theoretically possible if same cycle
                            # found multiple times, but canonical key deduplication
                            # ensures each unique cycle set is only reported once.
                            seen_cycle_keys.add(cycle_key)
                            cycles.append(cycle)

            else:  # EXIT state
                # Done processing this node's subtree
                if path and path[-1] == node:  # pragma: no branch
                    # Note: False branch (path empty or path[-1] != node) is defensive.
                    # In normal operation, EXIT is always paired with ENTER which adds
                    # node to path, so this condition should always be True.
                    path.pop()
                rec_stack.discard(node)

    return cycles


def build_dependency_graph(
    entries: Mapping[str, tuple[set[str], set[str]]],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Build separate message and term dependency graphs.

    Args:
        entries: Mapping from entry ID to (message_refs, term_refs) tuple.
                 Message IDs are plain strings, term IDs should NOT include
                 the "-" prefix.

    Returns:
        Tuple of (message_deps, term_deps) where each is a mapping from
        entry ID to set of referenced entry IDs.

    Example:
        >>> entries = {
        ...     "welcome": ({"greeting"}, {"brand"}),
        ...     "greeting": (set(), set()),
        ... }
        >>> msg_deps, term_deps = build_dependency_graph(entries)
        >>> msg_deps["welcome"]
        {'greeting'}
    """
    message_deps: dict[str, set[str]] = {}
    term_deps: dict[str, set[str]] = {}

    for entry_id, (msg_refs, trm_refs) in entries.items():
        # Messages reference other messages
        message_deps[entry_id] = msg_refs.copy()
        # Terms reference other terms (term-to-term deps only)
        term_deps[entry_id] = trm_refs.copy()

    return message_deps, term_deps
