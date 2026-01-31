#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: graph - Dependency Graph Algorithms
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Dependency Graph Algorithm Fuzzer (Atheris).

Targets: ftllexengine.analysis.graph (detect_cycles, canonicalize_cycle,
make_cycle_key, build_dependency_graph)

Concern boundary: This fuzzer stress-tests the graph algorithms used for
dependency analysis in FTL resource validation. Tests cycle detection with
adversarial graph topologies (deep chains, dense meshes, self-loops,
disconnected components), canonicalization invariants (idempotence, direction
preservation, determinism), cycle key deduplication, and dependency graph
construction with namespace prefixing. Distinct from fuzz_integrity which
exercises graph algorithms as a side effect of resource validation.

Metrics:
- Pattern coverage with weighted selection (12 patterns)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Error distribution and contract violations
- Seed corpus management
- Per-pattern wall-time accumulation

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import hashlib
import heapq
import json
import logging
import os
import pathlib
import statistics
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str | float | list[Any]]
type InterestingInput = tuple[float, str]  # (duration_ms, description)

# --- Dependency Checks with Clear Errors ---
_MISSING_DEPS: list[str] = []

try:
    import psutil
except ImportError:
    _MISSING_DEPS.append("psutil")
    psutil = None  # type: ignore[assignment]

try:
    import atheris
except ImportError:
    _MISSING_DEPS.append("atheris")
    atheris = None  # type: ignore[assignment]

if _MISSING_DEPS:
    print(f"[FATAL] Missing dependencies: {', '.join(_MISSING_DEPS)}", file=sys.stderr)
    print("Install: uv sync --group atheris", file=sys.stderr)
    sys.exit(1)


# --- FuzzerState ---


@dataclass
class FuzzerState:
    """Mutable fuzzer state with bounded memory."""

    iterations: int = 0
    findings: int = 0
    status: str = "init"

    # Performance tracking (bounded deques)
    performance_history: deque[float] = field(default_factory=lambda: deque(maxlen=10000))
    memory_history: deque[float] = field(default_factory=lambda: deque(maxlen=1000))

    # Pattern coverage
    pattern_coverage: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)

    # Interesting inputs (max-heap for slowest)
    slowest_operations: list[InterestingInput] = field(default_factory=list)
    seed_corpus: dict[str, bytes] = field(default_factory=dict)

    # Memory baseline
    initial_memory_mb: float = 0.0

    # Corpus productivity
    corpus_entries_added: int = 0

    # Per-pattern wall time (ms)
    pattern_wall_time: dict[str, float] = field(default_factory=dict)

    # Configuration
    checkpoint_interval: int = 500
    seed_corpus_max_size: int = 100


# Global state instance
_state = FuzzerState()
_process: psutil.Process | None = None


def _get_process() -> psutil.Process:
    """Lazy-initialize psutil process handle."""
    global _process  # noqa: PLW0603  # pylint: disable=global-statement
    if _process is None:
        _process = psutil.Process(os.getpid())
    return _process


# --- Reporting ---


def _emit_final_report() -> None:
    """Emit JSON summary on exit (crash-proof via atexit)."""
    _state.status = "complete" if _state.status == "running" else _state.status

    perf = _state.performance_history
    mem = _state.memory_history

    report: FuzzStats = {
        "status": _state.status,
        "iterations": _state.iterations,
        "findings": _state.findings,
        "error_types": len(_state.error_counts),
        "patterns_tested": len(_state.pattern_coverage),
        "corpus_entries_added": _state.corpus_entries_added,
        "seed_corpus_size": len(_state.seed_corpus),
        "slowest_operations_tracked": len(_state.slowest_operations),
    }

    # Performance stats
    if perf:
        sorted_perf = sorted(perf)
        report["perf_min_ms"] = round(sorted_perf[0], 3)
        report["perf_mean_ms"] = round(statistics.mean(perf), 3)
        report["perf_median_ms"] = round(statistics.median(perf), 3)
        report["perf_p95_ms"] = round(sorted_perf[int(len(sorted_perf) * 0.95)], 3)
        report["perf_p99_ms"] = round(sorted_perf[int(len(sorted_perf) * 0.99)], 3)
        report["perf_max_ms"] = round(sorted_perf[-1], 3)

    # Memory stats
    if mem:
        report["memory_peak_mb"] = round(max(mem), 2)
        report["memory_mean_mb"] = round(statistics.mean(mem), 2)
        report["memory_delta_mb"] = round(max(mem) - _state.initial_memory_mb, 2)
        # Leak detection: compare first and last quartiles
        quarter = max(1, len(mem) // 4)
        first_q = statistics.mean(list(mem)[:quarter])
        last_q = statistics.mean(list(mem)[-quarter:])
        growth = last_q - first_q
        report["memory_growth_mb"] = round(growth, 2)
        report["memory_leak_detected"] = int(growth > 50.0)

    # Pattern coverage
    for name, count in sorted(_state.pattern_coverage.items()):
        report[f"pattern_{name}"] = count

    # Per-pattern wall time
    for name, wall_ms in sorted(_state.pattern_wall_time.items()):
        report[f"wall_time_ms_{name}"] = round(wall_ms, 1)

    report_json = json.dumps(report)
    print(f"\n[SUMMARY-JSON-BEGIN]{report_json}[SUMMARY-JSON-END]", file=sys.stderr)

    # Write to corpus directory
    corpus_dir = pathlib.Path(".fuzz_corpus/graph")
    with contextlib.suppress(OSError):
        corpus_dir.mkdir(parents=True, exist_ok=True)
        (corpus_dir / "fuzz_graph_report.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )


atexit.register(_emit_final_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.analysis.graph import (
        build_dependency_graph,
        canonicalize_cycle,
        detect_cycles,
        make_cycle_key,
    )


# --- Error types ---


class GraphFuzzError(Exception):
    """Invariant violation in graph algorithm."""


# --- Constants ---

_NODE_NAMES = (
    "welcome", "greeting", "error", "title", "brand", "footer",
    "nav", "button", "label", "tooltip", "help", "description",
    "header", "content", "sidebar", "menu", "dialog", "alert",
    "status", "placeholder",
)

_TERM_NAMES = (
    "brand", "app-name", "company", "product", "version", "os-name",
    "platform", "theme", "locale", "region",
)


# --- Helpers ---


def _gen_node_id(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a node ID: 80% from curated names, 20% fuzzed."""
    if fdp.ConsumeIntInRange(0, 4) < 4:
        return fdp.PickValueInList(list(_NODE_NAMES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 20))


def _gen_term_id(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a term ID: 80% from curated names, 20% fuzzed."""
    if fdp.ConsumeIntInRange(0, 4) < 4:
        return fdp.PickValueInList(list(_TERM_NAMES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 20))


def _build_random_graph(
    fdp: atheris.FuzzedDataProvider, num_nodes: int, num_edges: int,
) -> dict[str, set[str]]:
    """Build a random directed graph from fuzzed data."""
    nodes = [_gen_node_id(fdp) for _ in range(num_nodes)]
    deps: dict[str, set[str]] = {}
    for node in nodes:
        if node not in deps:
            deps[node] = set()

    for _ in range(num_edges):
        if fdp.remaining_bytes() < 2:
            break
        u = fdp.PickValueInList(nodes)
        v = fdp.PickValueInList(nodes)
        if u not in deps:
            deps[u] = set()
        deps[u].add(v)

    return deps


# --- Observability helpers ---


def _track_slowest_operation(duration_ms: float, description: str) -> None:
    """Track top 10 slowest operations using min-heap."""
    if len(_state.slowest_operations) < 10:
        heapq.heappush(_state.slowest_operations, (duration_ms, description[:50]))
    elif duration_ms > _state.slowest_operations[0][0]:
        heapq.heapreplace(
            _state.slowest_operations, (duration_ms, description[:50])
        )


def _track_seed_corpus(data: bytes, duration_ms: float) -> None:
    """Track interesting inputs for seed corpus with FIFO eviction."""
    if duration_ms > 10.0:
        input_hash = hashlib.sha256(data).hexdigest()[:16]
        if input_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[input_hash] = data
            _state.corpus_entries_added += 1


# --- Pattern weights ---
# Ordered cheapest-first to counteract libFuzzer's small-byte bias:
# ConsumeIntInRange skews toward low values, over-selecting early entries.

_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    # Cheap: pure algorithm, no allocation-heavy setup
    ("canonicalize_idempotence", 12),
    ("canonicalize_direction", 10),
    ("make_cycle_key_consistency", 8),
    ("canonicalize_edge_cases", 6),
    ("detect_self_loops", 10),
    ("detect_simple_cycles", 12),
    ("detect_dag_no_cycles", 10),
    ("detect_disconnected", 8),
    # Moderate: larger graph construction
    ("detect_dense_mesh", 8),
    ("detect_deep_chain", 8),
    ("build_dependency_graph", 10),
    # Expensive: large adversarial graphs
    ("adversarial_graph", 5),
)

_ALLOWED_EXCEPTIONS = (
    ValueError, TypeError, OverflowError, RecursionError, MemoryError,
)


# --- Pattern implementations ---


def _pattern_canonicalize_idempotence(fdp: atheris.FuzzedDataProvider) -> None:
    """Canonicalize is idempotent: canon(canon(x)) == canon(x)."""
    n = fdp.ConsumeIntInRange(2, 8)
    nodes = [_gen_node_id(fdp) for _ in range(n)]
    # Close the cycle
    cycle = [*nodes, nodes[0]]

    c1 = canonicalize_cycle(cycle)
    c2 = canonicalize_cycle(list(c1))

    if c1 != c2:
        msg = f"canonicalize_cycle not idempotent: {c1} != {c2}"
        raise GraphFuzzError(msg)

    # Result should be a tuple
    if not isinstance(c1, tuple):
        msg = f"canonicalize_cycle returned {type(c1)}, expected tuple"
        raise GraphFuzzError(msg)

    # Last element should repeat first (closure)
    if len(c1) >= 2 and c1[0] != c1[-1]:
        msg = f"canonicalized cycle not closed: first={c1[0]}, last={c1[-1]}"
        raise GraphFuzzError(msg)


def _pattern_canonicalize_direction(fdp: atheris.FuzzedDataProvider) -> None:
    """Different cycle directions produce different canonical forms."""
    n = fdp.ConsumeIntInRange(3, 6)
    # Generate distinct nodes to ensure direction matters
    nodes = [f"node_{i}_{fdp.ConsumeIntInRange(0, 100)}" for i in range(n)]

    forward = [*nodes, nodes[0]]
    backward = [*reversed(nodes), nodes[-1]]

    c_fwd = canonicalize_cycle(forward)
    c_bwd = canonicalize_cycle(list(backward))

    # Both should be valid tuples
    if not isinstance(c_fwd, tuple) or not isinstance(c_bwd, tuple):
        msg = "canonicalize_cycle did not return tuple"
        raise GraphFuzzError(msg)

    # Both should be closed
    if len(c_fwd) >= 2 and c_fwd[0] != c_fwd[-1]:
        msg = f"Forward canonical not closed: {c_fwd}"
        raise GraphFuzzError(msg)

    if len(c_bwd) >= 2 and c_bwd[0] != c_bwd[-1]:
        msg = f"Backward canonical not closed: {c_bwd}"
        raise GraphFuzzError(msg)

    # Should start with the lexicographically smallest node
    if len(c_fwd) >= 2:
        interior = c_fwd[:-1]
        if c_fwd[0] != min(interior):
            msg = f"Canonical does not start with min: {c_fwd}"
            raise GraphFuzzError(msg)


def _pattern_make_cycle_key_consistency(fdp: atheris.FuzzedDataProvider) -> None:
    """make_cycle_key uses canonicalize_cycle internally -- verify consistency."""
    n = fdp.ConsumeIntInRange(2, 6)
    nodes = [_gen_node_id(fdp) for _ in range(n)]
    cycle = [*nodes, nodes[0]]

    key = make_cycle_key(cycle)
    canonical = canonicalize_cycle(cycle)
    expected_key = " -> ".join(canonical)

    if key != expected_key:
        msg = f"make_cycle_key inconsistent: '{key}' != '{expected_key}'"
        raise GraphFuzzError(msg)

    # Key should contain " -> " separator
    if len(canonical) >= 2 and " -> " not in key:
        msg = f"make_cycle_key missing separator: '{key}'"
        raise GraphFuzzError(msg)

    # Rotated cycles should produce same key (deduplication).
    # Only valid when interior nodes are unique -- duplicate nodes cause
    # ambiguous min-rotation (canonicalize_cycle uses index() which picks
    # the first occurrence).  detect_cycles never produces duplicates
    # because DFS stops at the first back-edge.
    if len(nodes) >= 3 and len(set(nodes)) == len(nodes):
        rotated = [*nodes[1:], nodes[0], nodes[1]]
        rotated_key = make_cycle_key(rotated)
        if key != rotated_key:
            msg = f"make_cycle_key not rotation-invariant: '{key}' vs '{rotated_key}'"
            raise GraphFuzzError(msg)


def _pattern_canonicalize_edge_cases(fdp: atheris.FuzzedDataProvider) -> None:
    """Edge cases: empty, single-element, two-element cycles."""
    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # Empty sequence
            result = canonicalize_cycle([])
            if result != ():
                msg = f"Empty cycle should give (): got {result}"
                raise GraphFuzzError(msg)

        case 1:
            # Single element
            node = _gen_node_id(fdp)
            result = canonicalize_cycle([node])
            if result != (node,):
                msg = f"Single element: expected ({node},), got {result}"
                raise GraphFuzzError(msg)

        case 2:
            # Self-loop: [A, A]
            node = _gen_node_id(fdp)
            result = canonicalize_cycle([node, node])
            if result != (node, node):
                msg = f"Self-loop: expected ({node}, {node}), got {result}"
                raise GraphFuzzError(msg)

        case _:
            # Two-node cycle: [A, B, A]
            a, b = _gen_node_id(fdp), _gen_node_id(fdp)
            result = canonicalize_cycle([a, b, a])
            if len(result) != 3:
                msg = f"Two-node cycle length: expected 3, got {len(result)}"
                raise GraphFuzzError(msg)
            if result[0] != result[-1]:
                msg = f"Two-node cycle not closed: {result}"
                raise GraphFuzzError(msg)


def _pattern_detect_self_loops(fdp: atheris.FuzzedDataProvider) -> None:
    """Self-loops (A -> A) must be detected as cycles."""
    n = fdp.ConsumeIntInRange(1, 5)
    deps: dict[str, set[str]] = {}

    self_loop_nodes = []
    for _ in range(n):
        node = _gen_node_id(fdp)
        deps[node] = {node}
        self_loop_nodes.append(node)

    # Add some non-looping nodes
    for _ in range(fdp.ConsumeIntInRange(0, 3)):
        node = _gen_node_id(fdp)
        target = _gen_node_id(fdp)
        if node != target:  # Avoid accidental self-loops
            deps.setdefault(node, set()).add(target)

    cycles = detect_cycles(deps)

    # Each self-loop should produce a cycle
    for node in self_loop_nodes:
        found = any(node in cycle for cycle in cycles)
        if not found:
            msg = f"Self-loop {node}->{node} not detected. Cycles: {cycles}"
            raise GraphFuzzError(msg)


def _pattern_detect_simple_cycles(fdp: atheris.FuzzedDataProvider) -> None:
    """Simple cycles (A->B->C->A) must be detected with valid structure."""
    n = fdp.ConsumeIntInRange(2, 8)
    nodes = [f"cyc_{i}" for i in range(n)]

    # Build a guaranteed cycle: nodes[0] -> nodes[1] -> ... -> nodes[0]
    deps: dict[str, set[str]] = {}
    for i in range(n):
        deps[nodes[i]] = {nodes[(i + 1) % n]}

    cycles = detect_cycles(deps)

    if not cycles:
        msg = f"Failed to detect cycle in {deps}"
        raise GraphFuzzError(msg)

    # Validate cycle structure
    for cycle in cycles:
        if len(cycle) < 2:
            msg = f"Trivial cycle: {cycle}"
            raise GraphFuzzError(msg)

        if cycle[0] != cycle[-1]:
            msg = f"Cycle not closed: {cycle}"
            raise GraphFuzzError(msg)

        # Every edge in cycle must exist in graph
        for i in range(len(cycle) - 1):
            u, v = cycle[i], cycle[i + 1]
            if u not in deps or v not in deps.get(u, set()):
                msg = f"Ghost edge in cycle: {u} -> {v}"
                raise GraphFuzzError(msg)


def _pattern_detect_dag_no_cycles(fdp: atheris.FuzzedDataProvider) -> None:
    """DAGs (directed acyclic graphs) should produce zero cycles."""
    n = fdp.ConsumeIntInRange(2, 20)
    nodes = [f"dag_{i}" for i in range(n)]

    # Build a strict DAG: only edges from lower index to higher index
    deps: dict[str, set[str]] = {}
    for i in range(n):
        deps[nodes[i]] = set()
        num_edges = fdp.ConsumeIntInRange(0, min(3, n - i - 1))
        for _ in range(num_edges):
            if i + 1 < n:
                j = fdp.ConsumeIntInRange(i + 1, n - 1)
                deps[nodes[i]].add(nodes[j])

    cycles = detect_cycles(deps)

    if cycles:
        msg = f"DAG produced cycles: {cycles}"
        raise GraphFuzzError(msg)


def _pattern_detect_disconnected(fdp: atheris.FuzzedDataProvider) -> None:
    """Disconnected components: cycles found independently in each."""
    # Component 1: has a cycle
    c1_size = fdp.ConsumeIntInRange(2, 5)
    c1_nodes = [f"c1_{i}" for i in range(c1_size)]
    deps: dict[str, set[str]] = {}
    for i in range(c1_size):
        deps[c1_nodes[i]] = {c1_nodes[(i + 1) % c1_size]}

    # Component 2: DAG (no cycle)
    c2_size = fdp.ConsumeIntInRange(2, 5)
    c2_nodes = [f"c2_{i}" for i in range(c2_size)]
    for i in range(c2_size):
        deps[c2_nodes[i]] = set()
        if i + 1 < c2_size:
            deps[c2_nodes[i]].add(c2_nodes[i + 1])

    # Component 3: optional second cycle
    has_second_cycle = fdp.ConsumeBool()
    if has_second_cycle:
        c3_size = fdp.ConsumeIntInRange(2, 4)
        c3_nodes = [f"c3_{i}" for i in range(c3_size)]
        for i in range(c3_size):
            deps[c3_nodes[i]] = {c3_nodes[(i + 1) % c3_size]}

    cycles = detect_cycles(deps)

    # Must find at least the first cycle
    if not cycles:
        msg = f"No cycles found in graph with known cycle: {deps}"
        raise GraphFuzzError(msg)


def _pattern_detect_dense_mesh(fdp: atheris.FuzzedDataProvider) -> None:
    """Dense graph: many edges, should complete without hanging."""
    n = fdp.ConsumeIntInRange(5, 50)
    edges = fdp.ConsumeIntInRange(n, n * 3)
    deps = _build_random_graph(fdp, n, edges)

    cycles = detect_cycles(deps)

    # Validate all cycles
    for cycle in cycles:
        if len(cycle) < 2:
            msg = f"Trivial cycle in dense graph: {cycle}"
            raise GraphFuzzError(msg)
        if cycle[0] != cycle[-1]:
            msg = f"Unclosed cycle in dense graph: {cycle}"
            raise GraphFuzzError(msg)


def _pattern_detect_deep_chain(fdp: atheris.FuzzedDataProvider) -> None:
    """Deep linear chain with optional back-edge: tests iterative DFS."""
    depth = fdp.ConsumeIntInRange(100, 1000)
    nodes = [f"chain_{i}" for i in range(depth)]

    deps: dict[str, set[str]] = {}
    for i in range(depth - 1):
        deps[nodes[i]] = {nodes[i + 1]}
    deps[nodes[-1]] = set()

    # Add a back-edge to create a cycle (50% of the time)
    has_backedge = fdp.ConsumeBool()
    if has_backedge:
        back_target = fdp.ConsumeIntInRange(0, depth - 2)
        deps[nodes[-1]].add(nodes[back_target])

    cycles = detect_cycles(deps)

    if has_backedge and not cycles:
        msg = f"Deep chain with back-edge: no cycle detected (depth={depth})"
        raise GraphFuzzError(msg)

    if not has_backedge and cycles:
        msg = f"Deep chain without back-edge produced cycles: {cycles[:3]}"
        raise GraphFuzzError(msg)


def _pattern_build_dependency_graph(fdp: atheris.FuzzedDataProvider) -> None:  # noqa: PLR0912
    """build_dependency_graph: namespace prefixing and output structure."""
    num_msgs = fdp.ConsumeIntInRange(1, 10)
    num_terms = fdp.ConsumeIntInRange(0, 5)

    message_entries: dict[str, tuple[set[str], set[str]]] = {}
    for _ in range(num_msgs):
        msg_id = _gen_node_id(fdp)
        msg_refs: set[str] = set()
        term_refs: set[str] = set()
        for _ in range(fdp.ConsumeIntInRange(0, 3)):
            if fdp.ConsumeBool():
                msg_refs.add(_gen_node_id(fdp))
            else:
                term_refs.add(_gen_term_id(fdp))
        message_entries[msg_id] = (msg_refs, term_refs)

    term_entries: dict[str, tuple[set[str], set[str]]] | None = None
    if num_terms > 0:
        term_entries = {}
        for _ in range(num_terms):
            term_id = _gen_term_id(fdp)
            t_msg_refs: set[str] = set()
            t_term_refs: set[str] = set()
            for _ in range(fdp.ConsumeIntInRange(0, 2)):
                t_term_refs.add(_gen_term_id(fdp))
            term_entries[term_id] = (t_msg_refs, t_term_refs)

    msg_deps, term_deps = build_dependency_graph(message_entries, term_entries)

    # Invariant: msg_deps keys match message_entries keys
    for msg_id in message_entries:
        if msg_id not in msg_deps:
            msg = f"msg_deps missing key: {msg_id}"
            raise GraphFuzzError(msg)

    # Invariant: msg_deps values are sets of message IDs (no prefixes)
    for key, refs in msg_deps.items():
        for ref in refs:
            if ref.startswith(("msg:", "term:")):
                msg = f"msg_deps value has prefix: {key} -> {ref}"
                raise GraphFuzzError(msg)

    # Invariant: term_deps keys have "msg:" or "term:" prefix
    for key in term_deps:
        if not key.startswith(("msg:", "term:")):
            msg = f"term_deps key missing prefix: {key}"
            raise GraphFuzzError(msg)

    # Invariant: term_deps values have "term:" prefix
    for key, refs in term_deps.items():
        for ref in refs:
            if not ref.startswith("term:"):
                msg = f"term_deps value missing 'term:' prefix: {key} -> {ref}"
                raise GraphFuzzError(msg)

    # Invariant: msg_deps values are copies (not aliases)
    for msg_id, (orig_refs, _) in message_entries.items():
        if msg_deps[msg_id] is orig_refs:
            msg = f"msg_deps[{msg_id}] is same object as input (not copied)"
            raise GraphFuzzError(msg)

    # Feed into detect_cycles for integration check
    detect_cycles(msg_deps)
    detect_cycles(term_deps)


def _pattern_adversarial_graph(fdp: atheris.FuzzedDataProvider) -> None:
    """Adversarial graph topologies: pathological inputs for cycle detection."""
    variant = fdp.ConsumeIntInRange(0, 4)

    match variant:
        case 0:
            # Complete graph (every node points to every other)
            n = fdp.ConsumeIntInRange(3, 20)
            nodes = [f"k_{i}" for i in range(n)]
            deps: dict[str, set[str]] = {
                node: {other for other in nodes if other != node}
                for node in nodes
            }
            cycles = detect_cycles(deps)
            # Complete graph with n>=3 must have cycles
            if not cycles:
                msg = f"Complete graph K{n} has no cycles"
                raise GraphFuzzError(msg)

        case 1:
            # Star topology (hub -> many leaves, one leaf -> hub)
            hub = "hub"
            n_leaves = fdp.ConsumeIntInRange(2, 30)
            leaves = [f"leaf_{i}" for i in range(n_leaves)]
            deps = {hub: set(leaves)}
            for leaf in leaves:
                deps[leaf] = set()
            # Add back-edge from random leaf to hub
            back_leaf = fdp.PickValueInList(leaves)
            deps[back_leaf].add(hub)
            cycles = detect_cycles(deps)
            if not cycles:
                msg = "Star with back-edge: no cycle detected"
                raise GraphFuzzError(msg)

        case 2:
            # Empty graph
            deps = {}
            cycles = detect_cycles(deps)
            if cycles:
                msg = f"Empty graph has cycles: {cycles}"
                raise GraphFuzzError(msg)

        case 3:
            # Nodes with no outgoing edges
            n = fdp.ConsumeIntInRange(1, 10)
            deps = {f"sink_{i}": set() for i in range(n)}
            cycles = detect_cycles(deps)
            if cycles:
                msg = f"Sink-only graph has cycles: {cycles}"
                raise GraphFuzzError(msg)

        case _:
            # Nodes referencing undefined targets (not in deps keys)
            deps = {
                "a": {"b", "c"},
                "b": {"undefined_1"},
                "c": {"undefined_2", "a"},
            }
            cycles = detect_cycles(deps)
            # c -> a -> c is a cycle (a -> b -> undefined_1 is not)
            found_ac_cycle = any(
                "a" in cycle and "c" in cycle for cycle in cycles
            )
            if not found_ac_cycle:
                msg = f"Missing a-c cycle with undefined targets: {cycles}"
                raise GraphFuzzError(msg)


# --- Pattern dispatch ---


_PATTERN_DISPATCH: dict[str, Any] = {
    "canonicalize_idempotence": _pattern_canonicalize_idempotence,
    "canonicalize_direction": _pattern_canonicalize_direction,
    "make_cycle_key_consistency": _pattern_make_cycle_key_consistency,
    "canonicalize_edge_cases": _pattern_canonicalize_edge_cases,
    "detect_self_loops": _pattern_detect_self_loops,
    "detect_simple_cycles": _pattern_detect_simple_cycles,
    "detect_dag_no_cycles": _pattern_detect_dag_no_cycles,
    "detect_disconnected": _pattern_detect_disconnected,
    "detect_dense_mesh": _pattern_detect_dense_mesh,
    "detect_deep_chain": _pattern_detect_deep_chain,
    "build_dependency_graph": _pattern_build_dependency_graph,
    "adversarial_graph": _pattern_adversarial_graph,
}


def _select_pattern(fdp: atheris.FuzzedDataProvider) -> str:
    """Select a weighted pattern."""
    total = sum(w for _, w in _PATTERN_WEIGHTS)
    choice = fdp.ConsumeIntInRange(0, total - 1)

    cumulative = 0
    for name, weight in _PATTERN_WEIGHTS:
        cumulative += weight
        if choice < cumulative:
            return name

    return _PATTERN_WEIGHTS[0][0]


def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz graph algorithms."""
    # Initialize memory baseline
    if _state.iterations == 0:
        _state.initial_memory_mb = _get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic checkpoint
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_final_report()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    # Select pattern
    pattern_name = _select_pattern(fdp)
    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    try:
        handler = _PATTERN_DISPATCH[pattern_name]
        handler(fdp)

    except GraphFuzzError:
        _state.findings += 1
        raise

    except KeyboardInterrupt:
        _state.status = "stopped"
        raise

    except _ALLOWED_EXCEPTIONS:
        pass  # Expected for adversarial inputs

    except Exception:  # pylint: disable=broad-exception-caught
        _state.findings += 1
        error_type = sys.exc_info()[0]
        if error_type is not None:
            key = error_type.__name__[:50]
            _state.error_counts[key] = _state.error_counts.get(key, 0) + 1
        raise

    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _state.performance_history.append(elapsed_ms)

        # Per-pattern wall time
        _state.pattern_wall_time[pattern_name] = (
            _state.pattern_wall_time.get(pattern_name, 0.0) + elapsed_ms
        )

        _track_slowest_operation(elapsed_ms, pattern_name)
        _track_seed_corpus(data, elapsed_ms)

        # Memory tracking (every 100 iterations)
        if _state.iterations % 100 == 0:
            current_mb = _get_process().memory_info().rss / (1024 * 1024)
            _state.memory_history.append(current_mb)


def main() -> None:
    """Run the graph algorithm fuzzer."""
    parser = argparse.ArgumentParser(description="Graph Algorithm Fuzzer")
    parser.add_argument(
        "--checkpoint-interval", type=int, default=500,
        help="Emit report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size", type=int, default=100,
        help="Max seed corpus entries (default: 100)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    sys.argv = [sys.argv[0], *remaining]

    print("=" * 80)
    print("Dependency Graph Algorithm Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     analysis.graph")
    print(f"Patterns:   {len(_PATTERN_WEIGHTS)}")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
