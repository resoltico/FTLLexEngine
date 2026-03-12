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
    "complete_graphs",
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
    force_cycle = draw(st.booleans()) if allow_cycles is None else allow_cycles

    acyclic_topologies = ["empty", "linear", "star", "dag"]
    cyclic_topologies = ["ring"]
    all_topologies = [*acyclic_topologies, *cyclic_topologies]

    if force_cycle:
        topology = draw(st.sampled_from(all_topologies))
    else:
        topology = draw(st.sampled_from(acyclic_topologies))

    # Draw topology first, then constrain node count by topology.
    # "empty" is meaningful with one node; every other topology needs at least
    # two nodes to produce structurally distinct adjacency lists and distinct
    # code paths in detect_cycles(). Without this, Hypothesis's shrinker
    # collapses all acyclic topologies to the same single-node empty graph
    # (index 0 of st.sampled_from), skewing the event distribution to ~70%
    # "empty". Conditioning min_size on topology gives the shrinker a reason
    # to keep separate minimal examples for every topology.
    min_nodes = 1 if topology == "empty" else 2
    nodes = draw(
        st.lists(node_names, min_size=min_nodes, max_size=max_nodes, unique=True)
    )
    n = len(nodes)

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

    if force_cycle and n >= 2 and topology != "ring":
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

    Draw composition label first, then generate frozensets conditioned on
    the label. Without this, drawing two independent frozensets (min_size=0)
    causes Hypothesis's shrinker to converge ~66% of examples to the
    ``refs_mixed`` case (both non-empty), starving ``refs_empty``,
    ``refs_msg_only``, and ``refs_term_only``. Conditioning min_size on the
    label gives the shrinker a structural reason to keep all four variants
    alive as distinct minimal examples.
    """
    composition = draw(st.sampled_from(["empty", "msg_only", "term_only", "mixed"]))

    match composition:
        case "empty":
            event("strategy=refs_empty")
            msg_refs: frozenset[str] = frozenset()
            term_refs: frozenset[str] = frozenset()

        case "msg_only":
            event("strategy=refs_msg_only")
            msg_refs = draw(st.frozensets(node_names, min_size=1, max_size=max_refs))
            term_refs = frozenset()

        case "term_only":
            event("strategy=refs_term_only")
            msg_refs = frozenset()
            term_refs = draw(st.frozensets(node_names, min_size=1, max_size=max_refs))

        case "mixed":
            event("strategy=refs_mixed")
            msg_refs = draw(st.frozensets(node_names, min_size=1, max_size=max_refs))
            term_refs = draw(st.frozensets(node_names, min_size=1, max_size=max_refs))

    return msg_refs, term_refs


@composite
def complete_graphs(
    draw: st.DrawFn,
    *,
    max_nodes: int = 10,
) -> dict[str, set[str]]:
    """Generate complete directed graphs K_n for cycle-bound testing.

    Every node points to every other node. Used to verify that
    ``detect_cycles()`` terminates and stays within ``MAX_DETECTED_CYCLES``
    under adversarial dense inputs (previously caused OOM via O(n!) DFS
    work-queue growth before ``MAX_GRAPH_DFS_STACK`` was introduced).

    Args:
        draw: Hypothesis draw function.
        max_nodes: Maximum number of nodes (K_{max_nodes}).

    Events emitted:
        - ``strategy=graph_complete``: K_n complete graph with node count.
    """
    n = draw(st.integers(min_value=2, max_value=max_nodes))
    event("strategy=graph_complete")
    nodes = [f"k{i}" for i in range(n)]
    return {node: {other for other in nodes if other != node} for node in nodes}
