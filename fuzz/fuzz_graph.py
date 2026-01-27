#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: graph - Graph algorithm stress (Cycle detection)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Graph Algorithm Fuzzer (Atheris).

Targets analysis/graph.py: detect_cycles and canonicalize_cycle.
Stress-tests cycle detection with complex, large, and adversarial graphs.

Built for Python 3.13+ using modern PEPs (695, 585, 563).
"""

from __future__ import annotations

import atexit
import json
import logging
import sys

# --- PEP 695 Type Aliases (Python 3.13) ---
type FuzzStats = dict[str, int | str]

# Crash-proof reporting
_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}

def _emit_final_report() -> None:
    """Emit JSON summary on exit."""
    report = json.dumps(_fuzz_stats)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)

atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    print("Error: atheris not found. See docs/FUZZING_GUIDE.md")
    sys.exit(1)

# Suppress logging
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.analysis.graph import canonicalize_cycle, detect_cycles

class GraphAlgoError(Exception):
    """Raised when a graph invariant is breached."""

def test_one_input(data: bytes) -> None:
    """Atheris entry point: generate random graphs and detect cycles."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # 1. Configuration
    num_nodes = fdp.ConsumeIntInRange(1, 1000)
    num_edges = fdp.ConsumeIntInRange(0, 5000)

    # 2. Build Random Graph
    dependencies: dict[str, set[str]] = {}
    node_ids = [f"n{i}" for i in range(num_nodes)]

    for _ in range(num_edges):
        u = fdp.PickValueInList(node_ids)
        v = fdp.PickValueInList(node_ids)
        if u not in dependencies:
            dependencies[u] = set()
        dependencies[u].add(v)

    # 3. Call detect_cycles
    try:
        cycles = detect_cycles(dependencies)
    except Exception as e:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        print(f"\n[FAIL] detect_cycles crashed: {e}")
        msg = f"detect_cycles crashed: {e}"
        raise GraphAlgoError(msg) from e

    # 4. Invariant Verification
    for cycle in cycles:
        # INVARIANT: Each cycle must be at least 2 nodes (A->A counts as [A, A])
        if len(cycle) < 2:
            _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
            msg = f"Trivial cycle found: {cycle}"
            raise GraphAlgoError(msg)

        # INVARIANT: Cycle must close (first == last)
        if cycle[0] != cycle[-1]:
            _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
            msg = f"Cycle does not close: {cycle}"
            raise GraphAlgoError(msg)

        # INVARIANT: Edge sequence in cycle must exist in graph
        for i in range(len(cycle) - 1):
            u, v = cycle[i], cycle[i+1]
            if u not in dependencies or v not in dependencies[u]:
                _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
                msg = f"Ghost edge in cycle: {u} -> {v} not in graph"
                raise GraphAlgoError(msg)

    # 5. Canonicalization Stress
    if cycles:
        try:
            c = cycles[0]
            c1 = canonicalize_cycle(c)
            # Idempotence
            c2 = canonicalize_cycle(list(c1))
            if c1 != c2:
                _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
                msg = f"canonicalize_cycle not idempotent: {c1} != {c2}"
                raise GraphAlgoError(msg)
        except Exception as e:
            _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
            msg = f"canonicalize_cycle crashed: {e}"
            raise GraphAlgoError(msg) from e

def main() -> None:
    """Run the graph algorithm fuzzer."""
    # Note: iterative DFS doesn't strictly need high recursion limit,
    # but we follow the pattern.
    sys.setrecursionlimit(2000)
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()

if __name__ == "__main__":
    main()
