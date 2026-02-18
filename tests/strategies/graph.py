"""Hypothesis strategies for dependency graph generation.

Provides reusable strategies for generating graph data structures
used by ``ftllexengine.analysis.graph``. Strategies produce adjacency
lists, cycle paths, and namespace-prefixed dependency sets.

Event-Emitting Strategies (HypoFuzz-Optimized):
    - dependency_graphs: Emits ``strategy=graph_{topology}``
    - cycle_paths: Emits ``strategy=cycle_{shape}``
    - namespace_ref_pairs: Emits ``strategy=refs_{composition}``

Python 3.13+.
"""

from __future__ import annotations

from hypothesis import event
from hypothesis import strategies as st
from hypothesis.strategies import composite

__all__ = [
    "cycle_paths",
    "dependency_graphs",
    "namespace_ref_pairs",
    "node_names",
]

# Constrained alphabet avoids slow text generation while covering
# enough variety for meaningful graph exploration.
node_names: st.SearchStrategy[str] = st.text(
    alphabet=st.sampled_from("abcdefghij"),
    min_size=1,
    max_size=4,
)


@composite
def dependency_graphs(  # noqa: PLR0912 - topology dispatch + cycle injection
    draw: st.DrawFn,
    *,
    max_nodes: int = 8,
    allow_cycles: bool | None = None,
) -> dict[str, set[str]]:
    """Generate dependency graphs as adjacency lists.

    Args:
        draw: Hypothesis draw function.
        max_nodes: Maximum number of nodes.
        allow_cycles: ``True`` forces at least one cycle, ``False``
            guarantees acyclic, ``None`` draws randomly.

    Events emitted:
        - ``strategy=graph_{topology}``: Graph topology category.
    """
    nodes = draw(
        st.lists(node_names, min_size=1, max_size=max_nodes, unique=True)
    )
    n = len(nodes)

    force_cycle = draw(st.booleans()) if allow_cycles is None else allow_cycles

    acyclic_topologies = ["empty", "linear", "star", "dag"]
    cyclic_topologies = ["ring"]
    all_topologies = [*acyclic_topologies, *cyclic_topologies]

    if force_cycle:
        topology = draw(st.sampled_from(all_topologies))
    else:
        topology = draw(st.sampled_from(acyclic_topologies))

    graph: dict[str, set[str]] = {node: set() for node in nodes}

    match topology:
        case "empty":
            event("strategy=graph_empty")

        case "linear":
            event("strategy=graph_linear")
            for i in range(n - 1):
                graph[nodes[i]].add(nodes[i + 1])

        case "ring":
            event("strategy=graph_ring")
            for i in range(n):
                graph[nodes[i]].add(nodes[(i + 1) % n])

        case "star":
            event("strategy=graph_star")
            if n > 1:
                hub = nodes[0]
                for spoke in nodes[1:]:
                    graph[hub].add(spoke)

        case "dag":
            event("strategy=graph_dag")
            if n >= 2:
                edge_count = draw(
                    st.integers(min_value=0, max_value=n * 2)
                )
                for _ in range(edge_count):
                    src_idx = draw(
                        st.integers(min_value=0, max_value=n - 2)
                    )
                    dst_idx = draw(
                        st.integers(
                            min_value=src_idx + 1, max_value=n - 1
                        )
                    )
                    graph[nodes[src_idx]].add(nodes[dst_idx])

    if force_cycle and n >= 2 and topology not in ("ring",):
        i = draw(st.integers(min_value=0, max_value=n - 2))
        j = draw(st.integers(min_value=i + 1, max_value=n - 1))
        graph[nodes[j]].add(nodes[i])
        for k in range(i, j):
            graph[nodes[k]].add(nodes[k + 1])

    return graph


@composite
def cycle_paths(
    draw: st.DrawFn,
    *,
    max_length: int = 6,
) -> list[str]:
    """Generate cycle paths in ``[A, B, C, A]`` closed format.

    Args:
        draw: Hypothesis draw function.
        max_length: Maximum number of distinct nodes in cycle.

    Events emitted:
        - ``strategy=cycle_{shape}``: Cycle shape category.
    """
    shape = draw(st.sampled_from(["self_loop", "pair", "ring"]))

    match shape:
        case "self_loop":
            event("strategy=cycle_self_loop")
            node = draw(node_names)
            return [node, node]

        case "pair":
            event("strategy=cycle_pair")
            pair = draw(
                st.lists(node_names, min_size=2, max_size=2, unique=True)
            )
            return [pair[0], pair[1], pair[0]]

        case "ring":
            event("strategy=cycle_ring")
            nodes = draw(st.lists(
                node_names,
                min_size=3,
                max_size=max_length,
                unique=True,
            ))
            return [*nodes, nodes[0]]

        case _:  # pragma: no cover
            msg = f"unexpected shape: {shape}"
            raise AssertionError(msg)


@composite
def namespace_ref_pairs(
    draw: st.DrawFn,
    *,
    max_refs: int = 5,
) -> tuple[frozenset[str], frozenset[str]]:
    """Generate (message_refs, term_refs) pairs for entry_dependency_set.

    Args:
        draw: Hypothesis draw function.
        max_refs: Maximum number of references per namespace.

    Events emitted:
        - ``strategy=refs_{composition}``: Reference composition.
    """
    msg_refs = draw(
        st.frozensets(node_names, min_size=0, max_size=max_refs)
    )
    term_refs = draw(
        st.frozensets(node_names, min_size=0, max_size=max_refs)
    )

    has_msgs = len(msg_refs) > 0
    has_terms = len(term_refs) > 0

    if has_msgs and has_terms:
        event("strategy=refs_mixed")
    elif has_msgs:
        event("strategy=refs_msg_only")
    elif has_terms:
        event("strategy=refs_term_only")
    else:
        event("strategy=refs_empty")

    return msg_refs, term_refs
